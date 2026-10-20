"""Build `site/data/site.json`, the one file the static site reads.

Everything shown on the site is derived here from committed sources: the ledger, the data
vintages (via the rebuilt database), and the backtest predictions. The site does no maths
beyond formatting, so what it shows can be checked against the repository.
"""

import json
import math
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from wedge import config, features, forecast, ledger, metrics, releases, selection, store

WEEK = timedelta(weeks=1)
RECENT_WEEKS = 52
ROLLING_WEEKS = 52
BACKTEST_MODELS = ["flows", "gbm", "ensemble", "zero", "seasonal_5y", "last_week"]


def _clean(obj):
    """JSON-safe: NaN/inf become null, numpy scalars become Python numbers."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        return None if not math.isfinite(obj) else round(float(obj), 4)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


def _mb(kb):
    return None if kb is None or (isinstance(kb, float) and math.isnan(kb)) else kb / 1000


def _blob_url(path: Path) -> str | None:
    try:
        rel = path.resolve().relative_to(config.REPO_ROOT.resolve()).as_posix()
    except ValueError:  # a ledger outside the repo (tests)
        return None
    return f"{config.REPO_URL}/blob/main/{rel}"


def _ledger_weeks(base: Path) -> list[dict]:
    """One row per ledger week: forecast (or miss) joined with its score and benchmarks."""
    rows = []
    for path in sorted((base / "forecasts").glob("*.json")):
        f = ledger.read(path)
        period = ledger.period_of(path)
        row = {
            "week": str(period),
            "status": f["status"],
            "file": _blob_url(path),
            "release_time": ledger.iso(releases.release_time(period)),
        }
        if f["status"] == "forecast":
            fc = f["forecast"]
            row |= {
                "created_at": f["created_at"],
                "model": f["model"]["version"],
                "point": _mb(fc["point"]),
                "p10": _mb(fc["p10"]),
                "p90": _mb(fc["p90"]),
                "p_build": fc["p_build"],
            }
        else:
            row["reason"] = f.get("reason")
        if (sp := ledger.score_path(base, period)).exists():
            s = ledger.read(sp)
            row["actual"] = _mb(s["actual_kb"])
            row["score_status"] = s["status"]
            if s["status"] == "scored":
                row["error"] = _mb(s["primary"]["error"])
                row["in_80"] = s["primary"]["in_80"]
                row["direction_hit"] = s["primary"]["direction_hit"]
                row["shadow_abs_error"] = {k: _mb(v["abs_error"]) for k, v in s["shadow"].items()}
            bench = s.get("benchmarks", {})
            if "api_print" in bench:
                row["api_print"] = _mb(bench["api_print"]["point"])
            if bench.get("consensus"):
                row["consensus"] = _mb(np.mean([c["point"] for c in bench["consensus"].values()]))
            if "override" in bench:
                row["override"] = _mb(bench["override"]["point"])
        else:  # not scored yet: show whatever benchmarks were logged
            if (p := ledger.api_path(base, period)).exists():
                row["api_print"] = _mb(ledger.read(p)["change_kb"])
            cons = list((base / "consensus").glob(f"{period}-consensus-*.json"))
            if cons:
                row["consensus"] = _mb(np.mean([ledger.read(p)["change_kb"] for p in cons]))
        rows.append(row)
    return rows


def _scoreboard(weeks: list[dict]) -> dict:
    """Live track-record summary. Benchmarks are compared only on weeks where both exist."""
    scored = [w for w in weeks if w.get("score_status") == "scored"]
    out = {
        "weeks_forecast": sum(w["status"] == "forecast" for w in weeks),
        "weeks_missed": sum(w["status"] == "missed" for w in weeks),
        "weeks_scored": len(scored),
        "rows": [],
    }
    if not scored:
        return out
    model_err = np.array([abs(w["error"]) for w in scored])
    out["mae"] = float(model_err.mean())
    out["hit_rate"] = float(np.mean([w["direction_hit"] for w in scored]))
    out["coverage_80"] = float(np.mean([w["in_80"] for w in scored]))
    rows = [{"name": "Wednesday Edge (flows-v1)", "n": len(scored), "mae": out["mae"]}]
    for name, label in [("zero", "Zero change"), ("seasonal_5y", "5-year seasonal")]:
        errs = [w["shadow_abs_error"][name] for w in scored]
        rows.append({"name": label, "n": len(errs), "mae": float(np.mean(errs))})
    for key, label in [("consensus", "Analyst consensus"), ("api_print", "API print")]:
        both = [w for w in scored if w.get(key) is not None]
        if both:
            rows.append(
                {
                    "name": label,
                    "n": len(both),
                    "mae": float(np.mean([abs(w["actual"] - w[key]) for w in both])),
                    "model_mae_same_weeks": float(np.mean([abs(w["error"]) for w in both])),
                }
            )
    out["rows"] = rows
    return out


def _backtest() -> dict | None:
    path = config.REPORT_DIR / "backtest" / "all_predictions.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["target"])
    df["target"] = df["target"].dt.date
    preds = {
        m: g.set_index("target").drop(columns=["model", "actual"])
        for m, g in df.groupby("model")
        if m in BACKTEST_MODELS
    }
    actual = df.drop_duplicates("target").set_index("target")["actual"]

    def table(start, end):
        y = actual.loc[start:end]
        ref = metrics.score(preds["seasonal_5y"].loc[start:end], y)["mae"]
        rows = []
        for m in BACKTEST_MODELS:
            s = metrics.score(preds[m].loc[start:end], y, ref)
            rows.append(
                {"model": m, **{k: s[k] for k in ("n", "mae", "hit_rate", "coverage_80", "skill")}}
            )
        for r in rows:
            r["mae"] = r["mae"] / 1000
        return rows

    rolling = {}
    for m in ["flows", "zero", "seasonal_5y"]:
        err = (actual - preds[m]["point"]).abs().rolling(ROLLING_WEEKS).mean() / 1000
        err = err.dropna().iloc[::4]  # monthly points keep the file small
        rolling[m] = [[str(t), v] for t, v in err.items()]
    first, last = min(actual.index), max(actual.index)
    return {
        "period": [str(first), str(last)],
        "selection_window": [str(d) for d in selection.WINDOW],
        "full": table(first, last),
        "selection": table(*selection.WINDOW),
        "rolling_mae": rolling,
    }


def _recent_actuals(wide: pd.DataFrame) -> list:
    last = wide["crude_commercial"].last_valid_index()
    weeks = [last - i * WEEK for i in range(RECENT_WEEKS - 1, -1, -1)]
    return [[str(w), _mb(features.actual_change(wide, w))] for w in weeks]


def _health(weeks: list[dict], wide: pd.DataFrame, now: datetime, last_fetch) -> dict:
    target = releases.target_period(now)
    last_period = wide["crude_commercial"].last_valid_index()
    expected = target - WEEK  # the latest week EIA should have released by now
    have_target = any(w["week"] == str(target) for w in weeks)
    recent_misses = [w["week"] for w in weeks[-4:] if w["status"] == "missed"]
    if last_period < expected:
        state, note = "stale", f"data ends {last_period}; week {expected} should be out"
    elif recent_misses:
        state, note = "warn", f"missed week(s) {', '.join(recent_misses)}"
    else:
        state, note = "ok", "pipeline healthy"
    return {
        "state": state,
        "note": note,
        "checked_at": ledger.iso(now),
        "next_target": str(target),
        "next_window_opens": ledger.iso(releases.window_opens(target)),
        "next_deadline": ledger.iso(releases.deadline(target)),
        "next_release": ledger.iso(releases.release_time(target)),
        "next_forecast_committed": have_target,
        "last_data_period": str(last_period),
        "last_fetch_utc": str(last_fetch),
    }


def build(
    *,
    shadow: bool | None = None,
    now: datetime | None = None,
    db_path=config.DB_PATH,
    ledger_root: Path | None = None,
) -> dict:
    if shadow is None:
        shadow = os.environ.get("WEDGE_LIVE", "").lower() != "true"
    now = now or forecast.utc_now()
    base = ledger_root or ledger.root(shadow)
    con = store.connect(db_path)
    try:
        wide = features.load_wide(con, vintage="latest")
        last_fetch = store.status(con)["last_fetch"].max()
    finally:
        con.close()
    weeks = _ledger_weeks(base)
    latest = next((w for w in reversed(weeks) if w["status"] == "forecast"), None)
    if latest:
        f = ledger.read(ledger.forecast_path(base, date.fromisoformat(latest["week"])))
        latest = latest | {
            "shadow": {
                k: {kk: _mb(vv) if kk != "p_build" else vv for kk, vv in v.items()}
                for k, v in f["shadow"].items()
            },
            "data": f["data"],
            "features": {
                k: f["features"].get(k)
                for k in (
                    "d_stocks_lag1",
                    "implied_lag1",
                    "residual_mean4",
                    "utilization_chg4",
                    "spr_chg_mean4",
                    "seasonal_5y",
                    "stocks_vs_5y",
                )
            },
        }
    return _clean(
        {
            "meta": {
                "generated_at": ledger.iso(now),
                "mode": "shadow" if shadow else "live",
                "model_version": forecast.MODEL_VERSION,
                "repo": config.REPO_URL,
                "git_sha": forecast._git_sha(),
            },
            "health": _health(weeks, wide, now, last_fetch),
            "latest": latest,
            "weeks": weeks,
            "scoreboard": _scoreboard(weeks),
            "recent_actuals": _recent_actuals(wide),
            "backtest": _backtest(),
        }
    )


def export(out_dir: Path = config.SITE_DIR / "data", **kw) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "site.json"
    path.write_text(json.dumps(build(**kw), indent=1), encoding="utf-8", newline="\n")
    return path
