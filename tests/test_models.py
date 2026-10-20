from datetime import date

import numpy as np
import pandas as pd
import pytest
from test_features import synthetic_obs

from wedge import backtest, features, selection
from wedge.backtest import BacktestResult
from wedge.models import PRED_COLUMNS
from wedge.models.ensemble import EnsembleModel
from wedge.models.flows import FLOW_FEATURES, FlowsModel
from wedge.models.gbm import GBMModel


@pytest.fixture(scope="module")
def data():
    wide = features.to_wide(synthetic_obs(first=date(2008, 1, 4)))
    return backtest.dataset(wide, backtest.fridays(date(2008, 1, 1), date(2026, 10, 9)))


@pytest.mark.parametrize("factory", [FlowsModel, GBMModel, EnsembleModel])
def test_candidate_predictions_are_well_formed(data, factory):
    X, y = data
    train, test = X.index[X.index < date(2025, 1, 1)], X.index[X.index >= date(2025, 1, 1)]
    m = factory()
    m.fit(X.loc[train], y.loc[train])
    p = m.predict(X.loc[test])
    assert list(p.columns) == PRED_COLUMNS
    assert np.isfinite(p.to_numpy()).all()
    assert (p["p10"] <= p["p50"]).all() and (p["p50"] <= p["p90"]).all()
    assert p["p_build"].between(0, 1).all()


def test_flows_model_learns_the_balance():
    """If next week's change is exactly last week's implied balance, the ridge finds it."""
    rng = np.random.default_rng(0)
    n = 600
    X = pd.DataFrame(rng.normal(0, 1000, (n, len(FLOW_FEATURES))), columns=FLOW_FEATURES)
    y = X["implied_lag1"] + rng.normal(0, 50, n)
    m = FlowsModel(alpha=1.0)
    m.fit(X, y)
    assert m.coefficients().index[0] == "implied_lag1"
    assert np.abs(m.point(X) - y).mean() < 100


def test_models_are_deterministic(data):
    X, y = data
    tests = backtest.fridays(date(2025, 1, 1), date(2025, 3, 31))
    a = backtest.walk_forward(GBMModel, X, y, tests)
    b = backtest.walk_forward(GBMModel, X, y, tests)
    pd.testing.assert_frame_equal(a, b)


def _fake_result(maes: dict[str, float], coverage: dict[str, float] | None = None):
    idx = backtest.fridays(*selection.WINDOW)
    y = pd.Series(np.where(np.arange(len(idx)) % 2 == 0, 1.0, -1.0) * 1000, index=idx)
    preds = {}
    for name, mae in maes.items():
        point = y + mae  # constant error = MAE
        # Wide intervals on 4 weeks out of 5 give 80% coverage; zero width gives 0%.
        covered = np.arange(len(idx)) % 5 != 0 if (coverage or {}).get(name, 0.8) else False
        width = np.where(covered, 1e9, 0.0)
        preds[name] = pd.DataFrame(
            {
                "point": point,
                "p10": point - width,
                "p50": point,
                "p90": point + width,
                "p_build": (y > 0).astype(float) * 0.9 + 0.05,
            },
            index=idx,
        )
    return BacktestResult(preds, y)


def test_selection_picks_lowest_passing_mae():
    r = _fake_result({"zero": 4000, "seasonal_5y": 4300, "flows": 3700, "gbm": 3500})
    s = selection.select(r)
    assert s.bar_model == "zero" and s.passed and s.chosen == "gbm"


def test_selection_prefers_simpler_within_tolerance():
    r = _fake_result({"zero": 4000, "flows": 3560, "gbm": 3500})
    assert selection.select(r).chosen == "flows"  # within 2% of gbm


def test_selection_rejects_uncalibrated_and_reports_failure():
    r = _fake_result({"zero": 4000, "flows": 4100, "gbm": 3500}, coverage={"gbm": 0.0})
    s = selection.select(r)
    assert not s.table.at["gbm", "calibrated"]
    assert not s.passed and s.chosen == "gbm"  # nothing passes: best MAE, labelled as failing
    assert "does NOT pass" in s.explain()
