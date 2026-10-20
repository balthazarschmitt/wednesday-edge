"""Naive baselines. Each reads its point forecast from one feature (or predicts zero) and gets
its distribution from its own recent errors, so baselines are scored on the same terms as models.

The API-print baseline is live-only (no free history) and is added with the ledger in Phase 6.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from wedge.models import PRED_COLUMNS

ERROR_WINDOW = 156  # weeks of past errors used for intervals (3 years)
MIN_HISTORY = 52


class InsufficientHistory(ValueError):
    pass


@dataclass
class EmpiricalIntervals:
    """Point forecast plus quantiles of the trailing training errors (y - point)."""

    window: int = ERROR_WINDOW
    min_history: int = MIN_HISTORY
    _errors: np.ndarray = field(init=False, repr=False, default_factory=lambda: np.array([]))

    def point(self, X: pd.DataFrame) -> pd.Series:
        raise NotImplementedError

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        errors = (y - self.point(X)).dropna().sort_index().tail(self.window)
        if len(errors) < self.min_history:
            raise InsufficientHistory(f"{len(errors)} usable weeks < {self.min_history}")
        self._errors = errors.to_numpy()

    def predict(self, X: pd.DataFrame) -> pd.DataFrame:
        if self._errors.size == 0:
            raise RuntimeError("fit before predict")
        point = self.point(X).to_numpy()
        q10, q50, q90 = np.quantile(self._errors, [0.1, 0.5, 0.9])
        p_build = (point[:, None] + self._errors[None, :] > 0).mean(axis=1)
        out = pd.DataFrame(
            {
                "point": point,
                "p10": point + q10,
                "p50": point + q50,
                "p90": point + q90,
                "p_build": p_build,
            },
            index=X.index,
        )
        return out[PRED_COLUMNS]


@dataclass
class FeatureBaseline(EmpiricalIntervals):
    """Predict the value of one feature column, or zero when `column` is None."""

    name: str = "zero"
    column: str | None = None

    def point(self, X: pd.DataFrame) -> pd.Series:
        if self.column is None:
            return pd.Series(0.0, index=X.index)
        return X[self.column].astype(float)


BASELINES = {
    "zero": lambda: FeatureBaseline(name="zero"),
    "last_week": lambda: FeatureBaseline(name="last_week", column="d_stocks_lag1"),
    "seasonal_5y": lambda: FeatureBaseline(name="seasonal_5y", column="seasonal_5y"),
}
