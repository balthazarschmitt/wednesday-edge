"""The live forecast job: ingest, guard the deadline, forecast, and write one ledger entry.

It is idempotent (an existing entry for the week means exit), refuses to forecast a week whose
actual is already published or whose deadline has passed (recording it as missed instead), and
never lets a failed ingest stop the forecast: it uses the stored data and flags staleness.
The live model path is the backtest path (`predict_all` trains exactly like `walk_forward`).
"""

import hashlib
import logging
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from wedge import backtest, config, features, ledger, releases, store
from wedge.models.baselines import BASELINES

log = logging.getLogger(__name__)

PRIMARY = "flows"
MODEL_VERSION = "flows-v1"  # ADR 0006
SHADOW_MODELS = {"gbm": backtest.CANDIDATES["gbm"], "ensemble": backtest.CANDIDATES["ensemble"]}
MODELS = {PRIMARY: backtest.CANDIDATES[PRIMARY], **SHADOW_MODELS, **BASELINES}
WEEK = timedelta(weeks=1)


def utc_now() -> datetime:
    return datetime.now(releases.UTC)


@dataclass
class Outcome:
    status: str  # forecast | missed | exists | too_early | dry_run
    target: date
    path: Path | None
    message: str
    entry: dict | None = None


def predict_all(wide: pd.DataFrame, as_of: datetime, target: date, models=MODELS) -> dict:
    """Fit every model on weeks released by `as_of` and predict `target`."""
    history = [
        t for t in backtest.fridays(backtest.HISTORY_START, target - WEEK) if t in wide.index
    ]
    X, y = backtest.dataset(wide, history)
    released = np.array([releases.release_time(t) <= as_of for t in X.index])
    train = X.index[released].intersection(y.index)
    x_now = features.build(wide, as_of, target).to_frame().T
    out = {}
    for name, factory in models.items():
        model = factory()
        model.fit(X.loc[train], y.loc[train])
        out[name] = model.predict(x_now).iloc[0].to_dict()
    return {"predictions": out, "features": x_now.iloc[0].to_dict(), "train_weeks": len(train)}


def _git_sha() -> str:
    if sha := os.environ.get("GITHUB_SHA"):
        return sha
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=config.REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _input_hash(wide: pd.DataFrame, as_of: datetime) -> str:
    known = wide[wide["released_at"] <= pd.Timestamp(as_of)].drop(columns="released_at")
    return hashlib.sha256(known.to_csv(lineterminator="\n").encode()).hexdigest()


def _rounded(pred: dict) -> dict:
    return {k: round(float(v), 4 if k == "p_build" else 1) for k, v in pred.items()}


def _missed(path: Path, target: date, now: datetime, reason: str) -> Outcome:
    entry = {
        "target_period": str(target),
        "commodity": ledger.COMMODITY,
        "status": "missed",
        "reason": reason,
        "recorded_at": ledger.iso(now),
        "deadline": ledger.iso(releases.deadline(target)),
    }
    ledger.write_once(path, entry)
    return Outcome("missed", target, path, reason, entry)


def run(
    *,
    shadow: bool = True,
    do_ingest: bool = True,
    dry_run: bool = False,
    clock: Callable[[], datetime] = utc_now,
    db_path: Path | str = config.DB_PATH,
    ledger_root: Path | None = None,
    ingest_fn: Callable[[], object] | None = None,
) -> Outcome:
    base = ledger_root or ledger.root(shadow)
    now = clock()
    target = releases.target_period(now)
    path = ledger.forecast_path(base, target)

    if path.exists():
        return Outcome("exists", target, path, f"{path.name} already in the ledger")
    if now < releases.window_opens(target) and not dry_run:
        opens = releases.window_opens(target)
        return Outcome("too_early", target, None, f"window opens {opens:%a %Y-%m-%d %H:%M %Z}")
    try:
        releases.check_open(target, now)
    except releases.DeadlineMissed as exc:
        if dry_run:
            return Outcome("dry_run", target, None, str(exc))
        return _missed(path, target, now, str(exc))

    ingest_error = None
    if do_ingest:
        from wedge.ingest import IngestError
        from wedge.pipeline import ingest
        from wedge.validate import ValidationError

        try:
            (ingest_fn or (lambda: ingest(db_path=db_path)))()
        except (IngestError, ValidationError) as exc:
            ingest_error = str(exc)
            log.warning("ingest failed, forecasting from stored data: %s", exc)

    as_of = clock()
    con = store.connect(db_path)
    try:
        wide = features.load_wide(con, as_of)
        last_fetch = store.status(con)["last_fetch"].max()
    finally:
        con.close()

    if target in wide.index and not np.isnan(wide.at[target, "crude_commercial"]):
        reason = "the actual for this week was already published when the job ran"
        if dry_run:
            return Outcome("dry_run", target, None, reason)
        return _missed(path, target, as_of, reason)

    result = predict_all(wide, as_of, target)
    try:  # modelling can take minutes; re-check before committing to the ledger
        releases.check_open(target, clock())
    except releases.DeadlineMissed as exc:
        if dry_run:
            return Outcome("dry_run", target, None, str(exc))
        return _missed(path, target, clock(), f"{exc} (job finished too late)")

    preds = result["predictions"]
    feats = result["features"]
    entry = {
        "target_period": str(target),
        "commodity": ledger.COMMODITY,
        "status": "forecast",
        "unit": "thousand barrels (weekly change in US commercial crude stocks)",
        "created_at": ledger.iso(clock()),
        "deadline": ledger.iso(releases.deadline(target)),
        "release_time": ledger.iso(releases.release_time(target)),
        "model": {"name": PRIMARY, "version": MODEL_VERSION, "git_sha": _git_sha()},
        "forecast": _rounded(preds[PRIMARY]),
        "shadow": {name: _rounded(p) for name, p in preds.items() if name != PRIMARY},
        "data": {
            "as_of": ledger.iso(as_of),
            "last_period": str(wide["crude_commercial"].last_valid_index()),
            "weeks_stale": float(feats["weeks_stale"]),
            "last_fetch_utc": str(last_fetch),
            "ingest_error": ingest_error,
            "train_weeks": result["train_weeks"],
            "input_sha256": _input_hash(wide, as_of),
        },
        "features": {k: (None if np.isnan(v) else round(float(v), 3)) for k, v in feats.items()},
    }
    if dry_run:
        return Outcome("dry_run", target, None, "dry run: nothing written", entry)
    ledger.write_once(path, entry)
    return Outcome("forecast", target, path, f"wrote {path.name}", entry)
