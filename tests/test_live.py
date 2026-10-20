import json
import shutil
import subprocess
from datetime import date, datetime

import numpy as np
import pytest
from test_features import synthetic_obs

from wedge import backtest, features, forecast, ledger, manual, releases, score, store
from wedge.ingest import IngestError, Pull
from wedge.ingest.eia import EIAError, fetch_weekly
from wedge.models.flows import FlowsModel
from wedge.releases import ET

# Columbus Day week: data for the week ending Oct 9 2026 is released Thu Oct 15 at 12:00 ET.
TARGET = date(2026, 10, 9)
OBS = synthetic_obs(first=date(2012, 1, 6), last=date(2026, 10, 23))
FETCHED = datetime(2026, 10, 8, 16, 0)  # naive UTC, after the Oct 2 week was released


def at(*args):
    t = datetime(*args, tzinfo=ET)
    return lambda: t


def seed_db(path, through=date(2026, 10, 2), fetched=FETCHED):
    con = store.connect(path)
    store.write_pull(con, Pull("eia_api", fetched, OBS[OBS["period"] <= through]))
    con.close()


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "wedge.duckdb"
    seed_db(path)
    return path


@pytest.fixture
def env(seeded, tmp_path):
    db = tmp_path / "wedge.duckdb"
    shutil.copy(seeded, db)
    return db, tmp_path / "ledger"


def run_forecast(env, clock, **kw):
    db, root = env
    return forecast.run(do_ingest=False, clock=clock, db_path=db, ledger_root=root, **kw)


def test_forecast_writes_one_valid_entry_and_is_idempotent(env):
    out = run_forecast(env, at(2026, 10, 13, 18, 0))
    assert out.status == "forecast" and out.target == TARGET
    entry = ledger.read(out.path)
    assert entry["status"] == "forecast"
    assert entry["model"]["version"] == forecast.MODEL_VERSION
    assert set(entry["shadow"]) == {"gbm", "ensemble", "zero", "last_week", "seasonal_5y"}
    f = entry["forecast"]
    assert f["p10"] <= f["p50"] <= f["p90"] and 0 <= f["p_build"] <= 1
    assert entry["data"]["last_period"] == "2026-10-02" and entry["data"]["weeks_stale"] == 0
    assert ledger.check_entry("ledger/forecasts/x.json", entry) == []
    again = run_forecast(env, at(2026, 10, 13, 21, 0))
    assert again.status == "exists"


def test_too_early_writes_nothing(env):
    out = run_forecast(env, at(2026, 10, 13, 11, 59))
    assert out.status == "too_early" and out.path is None
    assert not (env[1] / "forecasts").exists()


def test_after_deadline_records_missed(env):
    out = run_forecast(env, at(2026, 10, 15, 11, 50))
    assert out.status == "missed"
    assert ledger.read(out.path)["status"] == "missed"


def test_actual_already_published_records_missed(env):
    db, _ = env
    con = store.connect(db)
    store.write_pull(con, Pull("eia_api", datetime(2026, 10, 13, 15, 0), OBS))
    con.close()
    out = run_forecast(env, at(2026, 10, 13, 18, 0))
    assert out.status == "missed" and "already published" in out.message


def test_failed_ingest_still_forecasts_and_flags_it(env):
    db, root = env

    def broken():
        raise IngestError("api: down; xls: down")

    out = forecast.run(
        clock=at(2026, 10, 13, 18, 0), db_path=db, ledger_root=root, ingest_fn=broken
    )
    assert out.status == "forecast"
    assert out.entry["data"]["ingest_error"] == "api: down; xls: down"


def test_dry_run_writes_nothing(env):
    out = run_forecast(env, at(2026, 10, 12, 9, 0), dry_run=True)  # before the window: allowed
    assert out.status == "dry_run" and out.entry["forecast"]
    assert not (env[1] / "forecasts").exists()


def test_live_path_equals_backtest_path():
    wide = features.to_wide(OBS)
    t = date(2025, 6, 6)
    live = forecast.predict_all(wide, releases.decision_time(t), t, {"flows": FlowsModel})
    history = [p for p in backtest.fridays(backtest.HISTORY_START, t) if p in wide.index]
    X, y = backtest.dataset(wide, history)
    bt = backtest.walk_forward(FlowsModel, X, y, [t]).iloc[0]
    for k, v in live["predictions"]["flows"].items():
        assert v == pytest.approx(bt[k])


def _add_week(db, through, fetched):
    con = store.connect(db)
    store.write_pull(con, Pull("eia_api", fetched, OBS[OBS["period"] <= through]))
    con.close()


def test_score_once_actual_is_out_with_benchmarks(env):
    db, root = env
    run_forecast(env, at(2026, 10, 13, 18, 0))
    tue = datetime(2026, 10, 13, 17, 0, tzinfo=ET)
    manual.log_api(root, -2.1, "https://example.com/api", tue)
    manual.log_consensus(root, -1.0, "S&P Global poll", "https://example.com/sp", tue)
    manual.log_override(root, -3.0, "Gulf fog delayed imports", tue)

    early = score.run(do_ingest=False, clock=at(2026, 10, 15, 11, 0), db_path=db, ledger_root=root)
    assert early == []  # holiday week: actual not out yet, so the scorer just waits

    _add_week(db, TARGET, datetime(2026, 10, 15, 16, 5))
    done = score.run(do_ingest=False, clock=at(2026, 10, 15, 12, 30), db_path=db, ledger_root=root)
    assert [r.status for r in done] == ["scored"]
    s = ledger.read(done[0].path)
    wide = features.to_wide(OBS)
    actual = features.actual_change(wide, TARGET)
    assert s["actual_kb"] == pytest.approx(actual, abs=0.1)
    fc = ledger.read(ledger.forecast_path(root, TARGET))["forecast"]
    assert s["primary"]["error"] == pytest.approx(actual - fc["point"], abs=0.2)
    assert set(s["benchmarks"]) == {"api_print", "consensus", "override"}
    assert s["benchmarks"]["consensus"]["S&P Global poll"]["point"] == -1000.0
    again = score.run(do_ingest=False, clock=at(2026, 10, 15, 13, 0), db_path=db, ledger_root=root)
    assert again == []


def test_scorer_records_weeks_with_no_forecast_as_missed(env):
    db, root = env
    run_forecast(env, at(2026, 10, 13, 18, 0))
    _add_week(db, date(2026, 10, 23), datetime(2026, 10, 28, 15, 0))
    done = score.run(do_ingest=False, clock=at(2026, 10, 28, 12, 0), db_path=db, ledger_root=root)
    by_week = {r.target: r.status for r in done}
    assert by_week == {TARGET: "scored", date(2026, 10, 16): "missed", date(2026, 10, 23): "missed"}
    gap = ledger.read(ledger.forecast_path(root, date(2026, 10, 16)))
    assert gap["status"] == "missed" and "no forecast" in gap["reason"]
    record = score.track_record(root)
    assert list(record["status"]) == ["scored", "missed", "missed"]


def test_manual_inputs_rules(tmp_path):
    tue = datetime(2026, 10, 20, 17, 0, tzinfo=ET)
    with pytest.raises(ledger.LedgerError, match="URL"):
        manual.log_api(tmp_path, -2.0, "not a url", tue)
    with pytest.raises(releases.DeadlineMissed):
        manual.log_override(
            tmp_path, -2.0, "too late to matter", datetime(2026, 10, 21, 10, 20, tzinfo=ET)
        )
    with pytest.raises(ledger.LedgerError, match="reason"):
        manual.log_override(tmp_path, -2.0, "hunch", tue)
    manual.log_api(tmp_path, -2.0, "https://example.com", tue)
    with pytest.raises(ledger.LedgerError, match="append-only"):
        manual.log_api(tmp_path, -2.5, "https://example.com", tue)
    late = manual.log_consensus(
        tmp_path, -1.2, "Reuters poll", "https://example.com", tue, period=date(2025, 1, 3)
    )
    assert ledger.read(late)["logged_before_deadline"] is False


def _git(repo, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def test_ledger_integrity_check(tmp_path):
    _git(tmp_path, "init", "-q")
    good = {
        "schema_version": 1,
        "target_period": "2026-10-16",
        "status": "forecast",
        "created_at": "2026-10-20T22:00:00Z",
    }
    f = tmp_path / "ledger" / "forecasts" / "2026-10-16-crude.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps(good))
    (tmp_path / "ledger" / "README.md").write_text("rules")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "first")
    assert ledger.integrity_violations(None, repo=tmp_path) == []

    (tmp_path / "ledger" / "README.md").write_text("rules, edited")  # docs may change
    late = {**good, "target_period": "2026-10-23", "created_at": "2026-10-28T15:00:00Z"}
    (f.parent / "2026-10-23-crude.json").write_text(json.dumps(late))
    f.write_text(json.dumps({**good, "status": "missed"}))  # rewriting history
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "tamper")
    problems = ledger.integrity_violations("HEAD~1", repo=tmp_path)
    assert len(problems) == 2
    assert any("2026-10-16-crude.json: M" in p for p in problems)
    assert any("after its deadline" in p for p in problems)


def test_missing_key_falls_back_instead_of_crashing():
    with pytest.raises(EIAError, match="EIA_API_KEY"):
        fetch_weekly(["WCESTUS1"])


def test_window_opens_tuesday_noon():
    assert releases.window_opens(TARGET) == datetime(2026, 10, 13, 12, 0, tzinfo=ET)
    assert releases.window_opens(TARGET) < releases.deadline(TARGET)


def test_rounded_entries_are_json_safe():
    pred = {"point": np.float64(-1234.56), "p_build": np.float64(0.123456)}
    assert json.dumps(forecast._rounded(pred)) == '{"point": -1234.6, "p_build": 0.1235}'
