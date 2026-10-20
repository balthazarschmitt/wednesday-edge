"""Forecast scoring. Predictions follow models.PRED_COLUMNS; actuals are weekly changes in kb."""

import numpy as np
import pandas as pd

QUANTILES = {"p10": 0.1, "p50": 0.5, "p90": 0.9}


def pinball(y: np.ndarray, q_pred: np.ndarray, q: float) -> float:
    diff = y - q_pred
    return float(np.mean(np.maximum(q * diff, (q - 1) * diff)))


def score(pred: pd.DataFrame, y: pd.Series, reference_mae: float | None = None) -> dict:
    """Summary metrics over the weeks where both a prediction and an actual exist (kb)."""
    df = pred.join(y.rename("actual"), how="inner").dropna()
    if df.empty:
        raise ValueError("no overlapping weeks to score")
    a = df["actual"].to_numpy()
    err = a - df["point"].to_numpy()
    build = a > 0
    mae = float(np.mean(np.abs(err)))
    out = {
        "n": len(df),
        "mae": mae,
        "rmse": float(np.sqrt(np.mean(err**2))),
        "bias": float(np.mean(err)),
        # Directional call = P(build) >= 0.5, so models that predict zero still make a call.
        "hit_rate": float(np.mean((df["p_build"].to_numpy() >= 0.5) == build)),
        "coverage_80": float(np.mean((df["p10"] <= df["actual"]) & (df["actual"] <= df["p90"]))),
        "pinball": float(np.mean([pinball(a, df[c].to_numpy(), q) for c, q in QUANTILES.items()])),
        "brier": float(np.mean((df["p_build"].to_numpy() - build) ** 2)),
    }
    out["skill"] = 1 - mae / reference_mae if reference_mae else np.nan
    return out
