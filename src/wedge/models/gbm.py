"""LightGBM: quantile regressors for P10/P50/P90 and a classifier for P(build).

Hyperparameters are fixed and deliberately conservative (shallow trees, strong regularisation)
because a weekly series gives only ~50 new rows a year. They were chosen on the 2015-2021 dev
window and never on the 2022-2025 selection window (ADR 0006).
"""

from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np
import pandas as pd

from wedge.models import PRED_COLUMNS

GBM_FEATURES = [
    "d_stocks_lag1",
    "d_stocks_lag2",
    "d_stocks_lag3",
    "d_stocks_lag4",
    "implied_lag1",
    "implied_mean4",
    "residual_lag1",
    "residual_mean4",
    "residual_mean13",
    "production_chg1",
    "imports_commercial_lag1",
    "imports_commercial_chg1",
    "imports_commercial_mean4",
    "exports_lag1",
    "exports_chg1",
    "exports_mean4",
    "refinery_input_chg1",
    "utilization_lag1",
    "utilization_chg4",
    "spr_chg1",
    "spr_chg_mean4",
    "stocks_vs_5y",
    "seasonal_5y",
    "week_of_year",
    "hurricane_season",
    "holiday_in_week",
]
PARAMS = dict(
    n_estimators=300,
    learning_rate=0.03,
    num_leaves=7,
    max_depth=3,
    min_child_samples=40,
    subsample=0.8,
    subsample_freq=1,
    colsample_bytree=0.8,
    reg_lambda=5.0,
    random_state=0,
    n_jobs=1,
    deterministic=True,
    verbose=-1,
)
QUANTILES = {"p10": 0.1, "p50": 0.5, "p90": 0.9}
TRAIN_WEEKS = None  # expanding window from 1995; fixed on the dev window (ADR 0006)


@dataclass
class GBMModel:
    name: str = "gbm"
    train_weeks: int | None = TRAIN_WEEKS
    refit_every: int = 4
    _quantile: dict = field(init=False, repr=False, default_factory=dict)
    _classifier: lgb.LGBMClassifier | None = field(init=False, repr=False, default=None)

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        df = X[GBM_FEATURES].join(y.rename("y"), how="inner").dropna(subset=["y"]).sort_index()
        if self.train_weeks:
            df = df.tail(self.train_weeks)
        Xt, yt = df[GBM_FEATURES], df["y"]
        self._quantile = {
            col: lgb.LGBMRegressor(objective="quantile", alpha=q, **PARAMS).fit(Xt, yt)
            for col, q in QUANTILES.items()
        }
        self._classifier = lgb.LGBMClassifier(objective="binary", **PARAMS).fit(Xt, yt > 0)

    def predict(self, X: pd.DataFrame) -> pd.DataFrame:
        if self._classifier is None:
            raise RuntimeError("fit before predict")
        Xf = X[GBM_FEATURES]
        q = np.sort(np.column_stack([self._quantile[c].predict(Xf) for c in QUANTILES]), axis=1)
        out = pd.DataFrame(q, index=X.index, columns=list(QUANTILES))
        out["point"] = out["p50"]
        out["p_build"] = self._classifier.predict_proba(Xf)[:, 1]
        return out[PRED_COLUMNS]
