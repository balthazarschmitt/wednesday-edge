# ADR 0005: Baselines, backtest protocol, and the pre-registered selection rule

**Date:** 2026-10-19
**Status:** Accepted. This rule is fixed before any Phase 5 model is fitted, and changing it requires a new ADR.

## Backtest protocol
- **Walk-forward.** Each week from 2015 to 2025 is forecast as of Tuesday 18:00 ET, using only data that had been released by then (`features.build_many`). The model is trained only on weeks whose actual change had been released by that time, which the release calendar enforces.
- **Refitting.** Baselines are refitted every week. Heavier models may refit less often (`refit_every`), but never more often than weekly.
- **Same treatment for every model.** Baselines get prediction intervals and P(build) from the quantiles of their own last 156 weeks of errors. This puts them on the same footing as the real models.
- **Leakage checks.** Tests confirm that training never sees a week released after the decision time, and that corrupting future features or labels leaves the predictions unchanged.

## Baseline results (`reports/backtest/baselines.md`)
| Window | Zero | Last week | Seasonal 5y |
|---|---|---|---|
| 2015–2025 MAE (mb) | 4.22 | 5.03 | **4.18** |
| 2022–2025 MAE (mb) | **4.04** | 5.50 | 4.34 |

**Finding:** since 2022 the 5-year seasonal average has done *worse* than forecasting no change. Likely causes:
- the 2022–2023 SPR drawdown and the exchanges that pushed barrels into commercial stocks;
- record exports;
- a 5-year window that includes 2020.

Phase 5 will add SPR-change features to address this. Every baseline's 80% intervals cover 77–83% of outcomes, so the error-based interval method is roughly calibrated.

## Selection rule (pre-registered)
1. **Window.** Walk-forward over 2022-01-01 to 2025-12-31 (208 weeks).
2. **Bar.** A candidate must beat the **best naive baseline** in that window on MAE. Today that is *zero change*, at 4.04 mb. The bar was raised from the plan's original "beat seasonal", because seasonal is no longer the strongest naive forecast.
3. **Calibration.** 80% interval coverage must fall between 72% and 88%, and the Brier score must be no worse than the best baseline's.
4. **Choosing among candidates.** The lowest MAE wins. If two are within 2% of each other, pick the simpler one: baseline, then flows model, then LightGBM, then ensemble.
5. **If nothing passes.** Launch the candidate with the best MAE anyway, labelled honestly on the site as not beating the naive bar (risk R5).
6. **After launch.** The chosen model is frozen. Any change becomes a new version with its own ADR, and scores are reported both per version and for the full record.

The API-print baseline cannot be backtested, because there is no free history. It will be scored live from Phase 6 onward.
