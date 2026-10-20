"""Balance-of-flows model: a ridge regression on the weekly crude balance.

Commercial stocks change by 7 x (production + imports - exports - refinery input) plus an
unexplained adjustment. The model regresses next week's change on last week's implied flow
balance, the persistence of the adjustment residual, flow momentum, SPR movements, and
seasonality, so every coefficient has a physical reading (see `coefficients`).
Intervals and P(build) come from trailing in-sample errors, as for the baselines.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

from wedge.models.baselines import EmpiricalIntervals

FLOW_FEATURES = [
    "implied_lag1",
    "implied_mean4",
    "residual_lag1",
    "residual_mean4",
    "residual_mean13",
    "d_stocks_lag1",
    "production_chg1",
    "imports_commercial_chg1",
    "exports_chg1",
    "refinery_input_chg1",
    "utilization_chg4",
    "spr_chg1",
    "spr_chg_mean4",
    "stocks_vs_5y",
    "seasonal_5y",
]
TRAIN_WEEKS = 520  # trailing 10 years; fixed on the 2015-2021 dev window (ADR 0006)
ALPHA = 100.0


@dataclass
class FlowsModel(EmpiricalIntervals):
    name: str = "flows"
    train_weeks: int | None = TRAIN_WEEKS
    alpha: float = ALPHA
    refit_every: int = 1
    _pipe: Pipeline | None = field(init=False, repr=False, default=None)
    _fill: pd.Series | None = field(init=False, repr=False, default=None)

    def fit_point(self, X: pd.DataFrame, y: pd.Series) -> None:
        df = X[FLOW_FEATURES].join(y.rename("y")).dropna().sort_index()
        if self.train_weeks:
            df = df.tail(self.train_weeks)
        self._fill = df[FLOW_FEATURES].median()
        self._pipe = make_pipeline(StandardScaler(), Ridge(alpha=self.alpha))
        self._pipe.fit(df[FLOW_FEATURES], df["y"])

    def point(self, X: pd.DataFrame) -> pd.Series:
        if self._pipe is None:
            raise RuntimeError("fit before predict")
        Xf = X[FLOW_FEATURES].fillna(self._fill)
        return pd.Series(self._pipe.predict(Xf), index=X.index)

    def coefficients(self) -> pd.Series:
        """Effect on the forecast (kb) of a one-standard-deviation move in each feature."""
        ridge = self._pipe[-1]
        return pd.Series(ridge.coef_, index=FLOW_FEATURES).sort_values(key=np.abs, ascending=False)
