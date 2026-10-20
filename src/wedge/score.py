"""The scoring job: once EIA publishes a week, score every forecast for it, once.

Runs several times Wednesday to Friday and simply waits while the actual is not out yet, so a
holiday-shifted release needs no special handling. A week inside the ledger's span that has no
forecast entry once its deadline passes is recorded as missed: gaps are never silent.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from wedge import config, features, ledger, releases, store
from wedge.forecast import utc_now

log = logging.getLogger(__name__)
WEEK = timedelta(weeks=1)


@dataclass
class Scored:
    target: date
    status: str  # scored | missed | invalid
    path: Path


def score_prediction(pred: dict, actual: float) -> dict:
    error = actual - pred["point"]
    return {
        "point": pred["point"],
        "error": round(error, 1),
        "abs_error": round(abs(error), 1),
        "direction_hit": bool((pred["p_build"] >= 0.5) == (actual > 0)),
        "in_80": bool(pred["p10"] <= actual <= pred["p90"]),
        "brier": round((pred["p_build"] - float(actual > 0)) ** 2, 4),
    }


def _point_score(value_kb: float, actual: float) -> dict:
    error = actual - value_kb
    return {
        "point": value_kb,
        "error": round(error, 1),
        "abs_error": round(abs(error), 1),
        "direction_hit": bool((value_kb > 0) == (actual > 0)),
    }


def _benchmarks(base: Path, period: date, actual: float) -> dict:
    """Score the logged API print, analyst consensus, and any human override."""
    out = {}
    if (p := ledger.api_path(base, period)).exists():
        entry = ledger.read(p)
        out["api_print"] = {**_point_score(entry["change_kb"], actual), "source": entry["url"]}
    consensus = sorted((base / "consensus").glob(f"{period}-consensus-*.json"))
    if consensus:
        out["consensus"] = {}
        for p in consensus:
            entry = ledger.read(p)
            out["consensus"][entry["source"]] = {
                **_point_score(entry["change_kb"], actual),
                "logged_before_deadline": entry["logged_before_deadline"],
            }
    if (p := ledger.override_path(base, period)).exists():
        entry = ledger.read(p)
        out["override"] = {**_point_score(entry["change_kb"], actual), "reason": entry["reason"]}
    return out


def _record_gaps(base: Path, released: list[date], now: datetime) -> None:
    """Weeks between the first forecast and the latest release that have no entry are misses."""
    existing = sorted(ledger.period_of(p) for p in (base / "forecasts").glob("*.json"))
    if not existing:
        return
    period = existing[0]
    while period <= max(released, default=period):
        path = ledger.forecast_path(base, period)
        if not path.exists() and now >= releases.deadline(period):
            ledger.write_once(
                path,
                {
                    "target_period": str(period),
                    "commodity": ledger.COMMODITY,
                    "status": "missed",
                    "reason": "no forecast was committed before the deadline",
                    "recorded_at": ledger.iso(now),
                    "deadline": ledger.iso(releases.deadline(period)),
                },
            )
            log.warning("recorded missed week %s", period)
        period += WEEK


def run(
    *,
    shadow: bool = True,
    do_ingest: bool = True,
    clock: Callable[[], datetime] = utc_now,
    db_path: Path | str = config.DB_PATH,
    ledger_root: Path | None = None,
    ingest_fn: Callable[[], object] | None = None,
) -> list[Scored]:
    base = ledger_root or ledger.root(shadow)
    if do_ingest:
        from wedge.pipeline import ingest

        (ingest_fn or (lambda: ingest(db_path=db_path)))()  # no data, no scores: let it raise
    now = clock()
    con = store.connect(db_path)
    try:
        wide = features.load_wide(con, now)
    finally:
        con.close()
    released = [p for p in wide.index if not np.isnan(wide.at[p, "crude_commercial"])]
    _record_gaps(base, released, now)

    results = []
    for path in sorted((base / "forecasts").glob("*.json")):
        period = ledger.period_of(path)
        out_path = ledger.score_path(base, period)
        actual = features.actual_change(wide, period)
        if out_path.exists() or np.isnan(actual):
            continue
        entry = ledger.read(path)
        score = {
            "target_period": str(period),
            "commodity": ledger.COMMODITY,
            "actual_kb": round(actual, 1),
            "scored_at": ledger.iso(now),
            "forecast_status": entry["status"],
        }
        status = entry["status"]
        if status == "forecast":
            created = ledger.parse_iso(entry["created_at"])
            if created >= releases.release_time(period):
                status = "invalid"
                score["problem"] = "forecast created after the release; not scored"
            else:
                score["model"] = entry["model"]
                score["primary"] = score_prediction(entry["forecast"], actual)
                score["shadow"] = {
                    name: score_prediction(p, actual) for name, p in entry["shadow"].items()
                }
        score["status"] = "scored" if status == "forecast" else status
        score["benchmarks"] = _benchmarks(base, period, actual)
        ledger.write_once(out_path, score)
        results.append(Scored(period, score["status"], out_path))
    return results


def track_record(base: Path) -> pd.DataFrame:
    """One row per scored week: primary error and baseline errors (kb)."""
    rows = []
    for p in sorted((base / "scores").glob("*.json")):
        s = ledger.read(p)
        row = {"target": s["target_period"], "status": s["status"], "actual": s["actual_kb"]}
        if s["status"] == "scored":
            row["primary_abs_error"] = s["primary"]["abs_error"]
            for name, sc in s["shadow"].items():
                row[f"{name}_abs_error"] = sc["abs_error"]
        rows.append(row)
    return pd.DataFrame(rows)
