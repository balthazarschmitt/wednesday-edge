import json
from datetime import datetime

import pytest
from test_live import OBS, TARGET, _add_week, at, env, run_forecast, seeded  # noqa: F401

from wedge import features, score, site_export
from wedge.releases import ET


def build(env, clock):  # noqa: F811
    db, root = env
    return site_export.build(shadow=True, now=clock(), db_path=db, ledger_root=root)


def test_empty_ledger_exports_json_safe_site(env):  # noqa: F811
    site = build(env, at(2026, 10, 13, 9, 0))
    json.dumps(site, allow_nan=False)  # NaN would break the browser's JSON.parse
    assert site["latest"] is None and site["weeks"] == []
    assert site["meta"]["mode"] == "shadow"
    assert site["scoreboard"]["weeks_scored"] == 0 and site["scoreboard"]["rows"] == []
    h = site["health"]
    assert h["next_target"] == str(TARGET) and not h["next_forecast_committed"]
    assert h["next_release"].startswith("2026-10-15T16:00")  # Columbus Day: Thu 12:00 ET
    assert len(site["recent_actuals"]) == site_export.RECENT_WEEKS
    assert site["recent_actuals"][-1][0] == "2026-10-02"


def test_scored_week_flows_through_to_scoreboard(env):  # noqa: F811
    db, root = env
    run_forecast(env, at(2026, 10, 13, 18, 0))
    pending = build(env, at(2026, 10, 13, 19, 0))
    assert pending["latest"]["week"] == str(TARGET)
    assert pending["health"]["next_forecast_committed"]
    assert pending["weeks"][0]["p10"] <= pending["weeks"][0]["point"] <= pending["weeks"][0]["p90"]

    _add_week(db, TARGET, datetime(2026, 10, 15, 16, 5))
    score.run(do_ingest=False, clock=at(2026, 10, 15, 12, 30), db_path=db, ledger_root=root)
    site = build(env, at(2026, 10, 15, 13, 0))
    json.dumps(site, allow_nan=False)
    week = site["weeks"][0]
    actual_mb = features.actual_change(features.to_wide(OBS), TARGET) / 1000
    assert week["actual"] == pytest.approx(actual_mb, abs=1e-3)
    assert week["error"] == pytest.approx(actual_mb - week["point"], abs=1e-3)
    board = site["scoreboard"]
    assert board["weeks_scored"] == 1 and board["mae"] == pytest.approx(abs(week["error"]))
    assert [r["name"] for r in board["rows"]][:3] == [
        "Wednesday Edge (flows-v1)",
        "Zero change",
        "5-year seasonal",
    ]


def test_backtest_section_matches_committed_report():
    bt = site_export._backtest()
    assert bt is not None
    sel = {r["model"]: r for r in bt["selection"]}
    assert sel["flows"]["mae"] == pytest.approx(3.92, abs=0.005)  # reports/backtest/all.md
    assert sel["zero"]["mae"] == pytest.approx(4.04, abs=0.005)
    assert set(bt["rolling_mae"]) == {"flows", "zero", "seasonal_5y"}


def test_health_goes_stale_when_data_stops(env):  # noqa: F811
    site = build(env, at(2026, 10, 27, 9, 0))  # Oct 16 week should be out by now
    assert site["health"]["state"] == "stale"
    assert datetime.fromisoformat(site["meta"]["generated_at"]).astimezone(ET).day == 27
