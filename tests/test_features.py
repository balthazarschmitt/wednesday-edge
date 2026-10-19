from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from wedge import config, features, releases, store
from wedge.ingest.types import Pull, normalize_rows
from wedge.releases import ET

FIRST = date(2015, 1, 2)
LAST = date(2026, 10, 9)


def synthetic_obs(first=FIRST, last=LAST, seed=7) -> pd.DataFrame:
    """Random-walk stocks and noisy flows for every series, one row per Friday."""
    rng = np.random.default_rng(seed)
    n = (last - first).days // 7 + 1
    periods = [first + timedelta(weeks=i) for i in range(n)]
    levels = {
        "crude_commercial": 430_000 + np.cumsum(rng.normal(0, 4_000, n)),
        "production": 12_000 + rng.normal(0, 200, n),
        "imports_commercial": 6_000 + rng.normal(0, 600, n),
        "exports": 3_500 + rng.normal(0, 700, n),
        "refinery_input": 16_000 + rng.normal(0, 400, n),
        "refinery_utilization": 90 + rng.normal(0, 3, n),
    }
    for name in config.ALL_SERIES:
        levels.setdefault(name, 1_000 + rng.normal(0, 10, n))
    return normalize_rows(
        [
            {"series_id": config.ALL_SERIES[name], "period": p, "value": float(v)}
            for name, vals in levels.items()
            for p, v in zip(periods, vals, strict=True)
        ]
    )


@pytest.fixture(scope="module")
def wide():
    return features.to_wide(synthetic_obs())


def corrupt_after(wide: pd.DataFrame, as_of: datetime, extra_weeks: int = 8) -> pd.DataFrame:
    """Replace everything released after `as_of` with garbage and append fake future weeks."""
    out = wide.copy()
    future = out["released_at"] > pd.Timestamp(as_of)
    value_cols = [c for c in out.columns if c != "released_at"]
    out.loc[future, value_cols] = -1e9
    last = out.index[-1]
    extra = pd.DataFrame(
        1e9,
        index=[last + timedelta(weeks=i) for i in range(1, extra_weeks + 1)],
        columns=value_cols,
    )
    extra["released_at"] = [features._released_at(p) for p in extra.index]
    return pd.concat([out, extra])


TARGETS = [
    date(2016, 1, 1),  # New Year's Day is the period end
    date(2020, 3, 20),
    date(2024, 12, 27),  # holiday-shifted release (Jan 1 2025 was a Wednesday)
    date(2026, 9, 4),  # Labor Day week
    date(2026, 10, 9),  # Columbus Day week, last week of data
]


@pytest.mark.parametrize("target", TARGETS)
def test_leakage_future_data_cannot_change_features(wide, target):
    as_of = releases.decision_time(target)
    clean = features.build(wide, as_of, target)
    dirty = features.build(corrupt_after(wide, as_of), as_of, target)
    pd.testing.assert_series_equal(clean, dirty)


def test_leakage_backtest_matrix_identical_without_future_rows(wide):
    targets = [date(2024, 1, 5) + timedelta(weeks=i) for i in range(60)]
    full = features.build_many(wide, targets)
    cutoff = pd.Timestamp(releases.decision_time(targets[-1]))
    truncated = features.build_many(wide[wide["released_at"] <= cutoff], targets)
    pd.testing.assert_frame_equal(full, truncated)
    assert full.notna().all().all()


def test_release_boundary(wide):
    period = date(2026, 9, 25)
    released = releases.release_time(period)
    before = features.build(wide, released - timedelta(minutes=1))
    after = features.build(wide, released)
    assert before.name == period
    assert after.name == period + timedelta(weeks=1)
    assert after["d_stocks_lag1"] == pytest.approx(features.actual_change(wide, period))
    assert before["d_stocks_lag1"] == pytest.approx(
        features.actual_change(wide, period - timedelta(weeks=1))
    )


def test_holiday_week_uses_thursday_release(wide):
    # Wednesday Oct 14 2026: the Columbus-Day-delayed week ending Oct 9 is not out yet.
    f = features.build(wide, datetime(2026, 10, 14, 18, 0, tzinfo=ET))
    assert f.name == date(2026, 10, 9)
    assert f["release_shifted"] == 1.0
    assert f["holiday_in_week"] == 0.0  # Columbus Day is in the release week, not the data week


def test_already_released_target_rejected(wide):
    with pytest.raises(ValueError, match="already released"):
        features.build(wide, datetime(2026, 10, 20, 18, 0, tzinfo=ET), date(2026, 10, 9))


def test_naive_as_of_rejected(wide):
    with pytest.raises(ValueError, match="timezone-aware"):
        features.build(wide, datetime(2026, 10, 20, 18, 0))


def test_balance_and_seasonal_values(wide):
    target = date(2026, 10, 16)
    f = features.build(wide, releases.decision_time(target), target)
    p = target - timedelta(weeks=1)
    row = wide.loc[p]
    implied = 7 * (
        row["production"] + row["imports_commercial"] - row["exports"] - row["refinery_input"]
    )
    assert f["implied_lag1"] == pytest.approx(implied)
    assert f["residual_lag1"] == pytest.approx(f["d_stocks_lag1"] - implied)
    expected = np.mean(
        [features.actual_change(wide, features.same_week(target, y)) for y in range(1, 6)]
    )
    assert f["seasonal_5y"] == pytest.approx(expected)
    assert f["weeks_stale"] == 0
    assert f["hurricane_season"] == 1.0


def test_missing_week_is_nan_and_flagged():
    obs = synthetic_obs()
    gap = date(2026, 10, 9)
    obs = obs[obs["period"] != gap]
    wide = features.to_wide(obs)
    assert len(wide) == (LAST - FIRST).days // 7  # trailing gap removed, not padded
    f = features.build(wide, releases.decision_time(date(2026, 10, 16)), date(2026, 10, 16))
    assert np.isnan(f["d_stocks_lag1"])
    assert f["weeks_stale"] == 1


@pytest.mark.parametrize(
    ("period", "years", "expected"),
    [
        (date(2026, 10, 16), 1, date(2025, 10, 17)),
        (date(2026, 10, 16), 5, date(2021, 10, 15)),
        (date(2008, 2, 29), 1, date(2007, 3, 2)),
    ],
)
def test_same_week(period, years, expected):
    assert features.same_week(period, years) == expected
    assert expected.weekday() == releases.FRIDAY


def test_load_wide_point_in_time_ignores_later_revisions():
    con = store.connect(":memory:")
    obs = synthetic_obs(first=date(2026, 1, 2))
    store.write_pull(con, Pull("eia_api", datetime(2026, 10, 15, 17, 0), obs))
    revised = obs.copy()
    sid = config.ALL_SERIES["crude_commercial"]
    mask = (revised["series_id"] == sid) & (revised["period"] == LAST)
    revised.loc[mask, "value"] += 5_000
    store.write_pull(con, Pull("eia_api", datetime(2026, 10, 22, 15, 0), revised))

    as_of = datetime(2026, 10, 20, 18, 0, tzinfo=ET)
    pit = features.load_wide(con, as_of)
    now = features.load_wide(con, vintage="latest")
    assert now.at[LAST, "crude_commercial"] - pit.at[LAST, "crude_commercial"] == 5_000
    with pytest.raises(ValueError, match="needs as_of"):
        features.load_wide(con)
