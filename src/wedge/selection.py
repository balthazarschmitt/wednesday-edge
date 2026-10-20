"""The pre-registered model selection rule (pm/adr/0005-baselines-and-selection-rule.md).

1. Window: walk-forward 2022-01-01 to 2025-12-31.
2. A candidate must beat the best naive baseline's MAE in that window.
3. 80% interval coverage within [72%, 88%], and Brier no worse than that baseline's.
4. Lowest MAE wins; within 2% of it, the simplest model wins.
5. If no candidate passes, the best-MAE candidate launches, labelled as not passing.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from wedge.backtest import BacktestResult
from wedge.models.baselines import BASELINES

WINDOW = (date(2022, 1, 1), date(2025, 12, 31))
COVERAGE = (0.72, 0.88)
TIE_TOLERANCE = 0.02
SIMPLICITY = ["flows", "gbm", "ensemble"]  # simplest first


@dataclass
class Selection:
    chosen: str
    passed: bool
    bar_model: str
    bar_mae: float
    table: pd.DataFrame  # window metrics plus per-check columns, candidates only

    def explain(self) -> str:
        verdict = "passes" if self.passed else "does NOT pass"
        return (
            f"Selected `{self.chosen}`, which {verdict} the pre-registered rule. "
            f"Bar: `{self.bar_model}` at {self.bar_mae / 1000:.2f} mb MAE "
            f"({WINDOW[0]} to {WINDOW[1]})."
        )


def select(result: BacktestResult) -> Selection:
    summary = result.summary(*WINDOW)
    baselines = summary.loc[summary.index.isin(BASELINES)]
    candidates = summary.loc[[m for m in SIMPLICITY if m in summary.index]].copy()
    if baselines.empty or candidates.empty:
        raise ValueError("selection needs at least one baseline and one candidate")
    bar_model = baselines["mae"].idxmin()
    bar = baselines.loc[bar_model]

    candidates["beats_bar"] = candidates["mae"] < bar["mae"]
    candidates["calibrated"] = candidates["coverage_80"].between(*COVERAGE)
    candidates["brier_ok"] = candidates["brier"] <= bar["brier"]
    candidates["passes"] = candidates[["beats_bar", "calibrated", "brier_ok"]].all(axis=1)

    pool = candidates[candidates["passes"]]
    passed = not pool.empty
    if not passed:
        pool = candidates
    best = pool["mae"].min()
    near = [
        m for m in SIMPLICITY if m in pool.index and pool.at[m, "mae"] <= best * (1 + TIE_TOLERANCE)
    ]
    return Selection(near[0], passed, bar_model, float(bar["mae"]), candidates)
