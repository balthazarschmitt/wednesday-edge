"""Point-in-time features. `build` is the only path from stored data to model inputs.

A week's data counts as known at `as_of` only once EIA has released it (releases.release_time),
so the features for target week T can only use weeks released before the decision time. Rows
are filtered *before* anything is derived, so no rolling window or diff can see the future.

Units: stocks in thousand barrels (kb), flows in kb/d, weekly changes in kb.
"""

from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Literal

import duckdb
import numpy as np
import pandas as pd

from wedge import config, releases, store

FLOWS = ["production", "imports_commercial", "exports", "refinery_input"]
SEASONAL_YEARS = 5
DAYS_PER_WEEK = 7
WEEK = timedelta(weeks=1)


@lru_cache(maxsize=8192)
def _released_at(period: date) -> pd.Timestamp:
    return pd.Timestamp(releases.release_time(period)).tz_convert("UTC")


def to_wide(obs: pd.DataFrame) -> pd.DataFrame:
    """Long (series_id, period, value) rows -> one row per Friday, one column per series.

    The index is a gap-free run of Fridays, so missing weeks are NaN rather than skipped, and a
    `released_at` column (UTC) records when each week became public.
    """
    obs = obs[obs["series_id"].isin(config.SERIES_NAMES)]
    if obs.empty:
        raise ValueError("no recognised series in observations")
    wide = (
        obs.assign(name=obs["series_id"].map(config.SERIES_NAMES))
        .pivot(index="period", columns="name", values="value")
        .reindex(columns=list(config.ALL_SERIES))
    )
    first, last = min(wide.index), max(wide.index)
    fridays = [first + i * WEEK for i in range((last - first).days // DAYS_PER_WEEK + 1)]
    wide = wide.reindex(fridays)
    wide.index.name = "period"
    wide["released_at"] = [_released_at(p) for p in wide.index]
    return wide


def _derive(known: pd.DataFrame) -> pd.DataFrame:
    """Weekly crude balance: change in stocks, implied flow change, and the residual plug."""
    d = known.copy()
    d["d_stocks"] = d["crude_commercial"].diff()
    d["implied"] = DAYS_PER_WEEK * (
        d["production"] + d["imports_commercial"] - d["exports"] - d["refinery_input"]
    )
    d["residual"] = d["d_stocks"] - d["implied"]
    return d


def same_week(period: date, years_back: int) -> date:
    """The Friday nearest the same calendar date `years_back` years earlier."""
    year = period.year - years_back
    try:
        anchor = period.replace(year=year)
    except ValueError:  # Feb 29
        anchor = date(year, 2, 28)
    return anchor + timedelta(days=(releases.FRIDAY - anchor.weekday() + 3) % 7 - 3)


def _week_has_holiday(period: date) -> bool:
    return any(releases.is_holiday(period - timedelta(days=i)) for i in range(DAYS_PER_WEEK))


def _hurricane_season(period: date) -> bool:
    return 6 <= period.month <= 11


def build(wide: pd.DataFrame, as_of: datetime, target: date | None = None) -> pd.Series:
    """Features for forecasting `target` (default: the next unreleased week) as known at `as_of`."""
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    target = target or releases.target_period(as_of)
    if releases.release_time(target) <= as_of:
        raise ValueError(f"week {target} was already released at {as_of}; that is not a forecast")

    known = wide[wide["released_at"] <= pd.Timestamp(as_of)]
    if known.empty:
        raise ValueError(f"no data released by {as_of}")
    d = _derive(known.drop(columns="released_at"))

    def at_period(col: str, p: date) -> float:
        return float(d.at[p, col]) if p in d.index else np.nan

    def at(col: str, lag: int) -> float:
        return at_period(col, target - lag * WEEK)

    def trailing_mean(col: str, n: int) -> float:
        return float(d.loc[: target - WEEK, col].tail(n).mean())

    def seasonal(col: str, lag: int) -> float:
        """Mean of `col` in the same week of the previous SEASONAL_YEARS years."""
        base = target - lag * WEEK
        vals = [at_period(col, same_week(base, y)) for y in range(1, SEASONAL_YEARS + 1)]
        return float(np.nanmean(vals)) if not np.isnan(vals).all() else np.nan

    f: dict[str, float] = {}
    for lag in range(1, 5):
        f[f"d_stocks_lag{lag}"] = at("d_stocks", lag)
    f["implied_lag1"] = at("implied", 1)
    f["residual_lag1"] = at("residual", 1)
    f["residual_mean4"] = trailing_mean("residual", 4)
    f["residual_mean13"] = trailing_mean("residual", 13)
    for flow in FLOWS:
        f[f"{flow}_lag1"] = at(flow, 1)
        f[f"{flow}_chg1"] = at(flow, 1) - at(flow, 2)
        f[f"{flow}_mean4"] = trailing_mean(flow, 4)
    f["utilization_lag1"] = at("refinery_utilization", 1)
    f["utilization_chg4"] = at("refinery_utilization", 1) - at("refinery_utilization", 5)
    f["stocks_lag1"] = at("crude_commercial", 1)
    f["stocks_vs_5y"] = f["stocks_lag1"] - seasonal("crude_commercial", 1)
    f["cushing_lag1"] = at("cushing", 1)
    f["seasonal_5y"] = seasonal("d_stocks", 0)
    f["week_of_year"] = target.isocalendar().week
    f["hurricane_season"] = float(_hurricane_season(target))
    f["holiday_in_week"] = float(_week_has_holiday(target))
    f["release_shifted"] = float(releases.release_time(target).weekday() != 2)
    last_known = d["crude_commercial"].last_valid_index()
    f["weeks_stale"] = (target - WEEK - last_known).days / DAYS_PER_WEEK

    return pd.Series(f, name=target, dtype=float)


def build_many(wide: pd.DataFrame, targets: list[date]) -> pd.DataFrame:
    """Backtest feature matrix: each target's features as of its own Tuesday decision time."""
    rows = [build(wide, releases.decision_time(t), t) for t in targets]
    out = pd.DataFrame(rows)
    out.index.name = "target"
    return out


def actual_change(wide: pd.DataFrame, period: date) -> float:
    """The realised weekly change in commercial crude stocks (kb). For scoring only."""
    prev = period - WEEK
    if period not in wide.index or prev not in wide.index:
        return np.nan
    return float(wide.at[period, "crude_commercial"] - wide.at[prev, "crude_commercial"])


def load_wide(
    con: duckdb.DuckDBPyConnection,
    as_of: datetime | None = None,
    *,
    vintage: Literal["point_in_time", "latest"] = "point_in_time",
) -> pd.DataFrame:
    """Wide data from the store.

    `point_in_time` uses only pulls fetched by `as_of` (live forecasts and audits). `latest` uses
    current values and is for historical backtests, where we hold no old vintages; the release
    filter in `build` still applies. EIA rarely revises weekly data (risk R13).
    """
    if vintage == "latest":
        return to_wide(store.latest(con))
    if as_of is None:
        raise ValueError("point_in_time vintage needs as_of")
    return to_wide(store.known_as_of(con, releases.to_utc_naive(as_of)))
