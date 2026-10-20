"""Equal-weight ensemble of the flows and LightGBM models.

Quantiles are averaged (quantile averaging keeps them ordered), as are the point forecast
and P(build). Equal weights are fixed in advance rather than fitted (ADR 0006).
"""

from dataclasses import dataclass, field

import pandas as pd

from wedge.models import PRED_COLUMNS
from wedge.models.flows import FlowsModel
from wedge.models.gbm import GBMModel


@dataclass
class EnsembleModel:
    name: str = "ensemble"
    refit_every: int = 4
    members: list = field(default_factory=lambda: [FlowsModel(), GBMModel()])

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        for m in self.members:
            m.fit(X, y)

    def predict(self, X: pd.DataFrame) -> pd.DataFrame:
        preds = [m.predict(X)[PRED_COLUMNS] for m in self.members]
        return sum(preds) / len(preds)
