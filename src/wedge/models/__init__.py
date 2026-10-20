"""Forecast models. Every model fits on (features, actuals) and predicts a distribution.

`predict` returns one row per target with columns PRED_COLUMNS: the point forecast, the
P10/P50/P90 quantiles, and the probability of a stock build (change > 0), all in kb.
"""

from typing import Protocol

import pandas as pd

PRED_COLUMNS = ["point", "p10", "p50", "p90", "p_build"]


class Model(Protocol):
    name: str

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None: ...

    def predict(self, X: pd.DataFrame) -> pd.DataFrame: ...
