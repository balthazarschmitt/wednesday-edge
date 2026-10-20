from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from test_features import synthetic_obs

from wedge import backtest, features, metrics, releases
from wedge.models import PRED_COLUMNS
from wedge.models.baselines import BASELINES, FeatureBaseline, InsufficientHistory


@pytest.fixture(scope="module")
def wide():
    return features.to_wide(synthetic_obs(first=date(2012, 1, 6)))


@pytest.fixture(scope="module")
def data(wide):
    return backtest.dataset(wide, backtest.fridays(date(2012, 1, 1), date(2026, 10, 9)))


def test_baseline_intervals_from_errors():
    idx = list(range(100))
    X = pd.DataFrame({"d_stocks_lag1": np.zeros(100)}, index=idx)
    y = pd.Series(np.arange(100, dtype=float) - 49.5, index=idx)
    m = FeatureBaseline(name="last_week", column="d_stocks_lag1")
    m.fit(X, y)
    p = m.predict(X.iloc[:1])
    assert list(p.columns) == PRED_COLUMNS
    assert p["p10"].iloc[0] < p["p50"].iloc[0] < p["p90"].iloc[0]
    assert p["p_build"].iloc[0] == pytest.approx(0.5)


def test_baseline_needs_history():
    X = pd.DataFrame({"x": [0.0] * 10})
    with pytest.raises(InsufficientHistory):
        FeatureBaseline().fit(X, pd.Series([1.0] * 10))


def test_walk_forward_trains_only_on_released_weeks(data):
    X, y = data
    seen = []

    class Spy(FeatureBaseline):
        def fit(self, X_train, y_train):
            seen.append((target_holder[0], X_train.index.max(), y_train.index.max()))
            super().fit(X_train, y_train)

    target_holder = [None]
    tests = backtest.fridays(date(2024, 1, 1), date(2024, 12, 31))
    for t in tests:
        target_holder[0] = t
        backtest.walk_forward(Spy, X, y, [t])
    for target, last_x, last_y in seen:
        assert last_x < target and last_y < target
        assert releases.release_time(last_y) <= releases.decision_time(target)
        assert last_y == target - timedelta(weeks=1)  # last week is out by Tuesday evening


def test_walk_forward_ignores_future_labels(data):
    X, y = data
    tests = backtest.fridays(date(2023, 1, 1), date(2023, 12, 31))
    clean = backtest.walk_forward(BASELINES["seasonal_5y"], X, y, tests)
    y_dirty = y.copy()
    y_dirty[y_dirty.index > tests[-1]] = 1e9
    X_dirty = X.copy()
    X_dirty[X_dirty.index > tests[-1]] = -1e9
    dirty = backtest.walk_forward(BASELINES["seasonal_5y"], X_dirty, y_dirty, tests)
    pd.testing.assert_frame_equal(clean, dirty)


def test_refit_every_matches_when_one(data):
    X, y = data
    tests = backtest.fridays(date(2022, 1, 1), date(2022, 6, 30))
    a = backtest.walk_forward(BASELINES["zero"], X, y, tests, refit_every=1)
    b = backtest.walk_forward(BASELINES["zero"], X, y, tests, refit_every=13)
    assert a.index.equals(b.index)
    assert (a["point"] == 0).all()
    assert not a.equals(b)  # intervals go stale between refits


def test_run_and_report(wide, tmp_path, monkeypatch):
    monkeypatch.setattr(backtest, "REPORT_DIR", tmp_path)
    start, end = date(2023, 1, 1), date(2024, 12, 31)
    result = backtest.run(wide, start, end, BASELINES)
    summary = result.summary()
    assert set(summary.index) == set(BASELINES)
    assert summary.loc["seasonal_5y", "skill"] == pytest.approx(0.0)
    assert (summary["n"] == len(backtest.fridays(start, end))).all()
    for pred in result.predictions.values():
        assert np.isfinite(pred.to_numpy()).all()
    md = backtest.write_report(result, "baselines", start, end, "Test").read_text()
    assert "## Selection window" in md and "seasonal_5y" in md
    csv = pd.read_csv(tmp_path / "baselines_predictions.csv")
    assert len(csv) == 3 * len(backtest.fridays(start, end))
    assert {"model", "target", "actual", *PRED_COLUMNS} <= set(csv.columns)


def test_metrics_known_values():
    idx = [date(2026, 1, 2), date(2026, 1, 9)]
    pred = pd.DataFrame(
        {
            "point": [1.0, -1.0],
            "p10": [0.0, -2.0],
            "p50": [1.0, -1.0],
            "p90": [2.0, 0.0],
            "p_build": [0.9, 0.2],
        },
        index=idx,
    )
    y = pd.Series([3.0, -1.0], index=idx)
    s = metrics.score(pred, y, reference_mae=2.0)
    assert s["mae"] == 1.0
    assert s["bias"] == 1.0
    assert s["hit_rate"] == 1.0
    assert s["coverage_80"] == 0.5
    assert s["brier"] == pytest.approx((0.1**2 + 0.2**2) / 2)
    assert s["skill"] == 0.5
