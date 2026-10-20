# ADR 0006: Candidate models and the selected launch model

**Date:** 2026-10-19
**Status:** Accepted. The launch model is `flows` v1.

## Protocol (in order, each step committed before the next)
1. **The rule.** ADR 0005 fixed the selection rule, the 2022–2025 selection window, and the "best naive baseline" bar (commit `13f2da8`).
2. **The settings.** Model settings were chosen using only the **2015–2021 dev window**. The data was hard-cut at 2021-12-31 for this step.
3. **The freeze.** The models were frozen in commit `e471069`, which predates any score on the selection window.
4. **The run.** One full run of `wedge backtest --models all` (report: `reports/backtest/all.md`). Nothing was retuned afterwards.

## Candidates
- **`flows`: a ridge regression on the weekly crude balance.**
  - Inputs: the implied flow balance `7 × (production + imports − exports − runs)`, the persistence of the adjustment residual, flow momentum, SPR changes, stock levels against their 5-year average, and the seasonal mean (15 features in all).
  - Trained on a trailing 10-year window and refitted every week.
  - Intervals come from its own trailing errors.
- **`gbm`: LightGBM.**
  - Three quantile regressors (P10, P50, P90) plus a build classifier, on 26 features.
  - Shallow, regularised trees. Expanding training window from 1995, refitted every 4 weeks.
- **`ensemble`:** the equal-weight average of the two.

### Dev-window choices (2015–2021, MAE in mb)
| Variant | MAE | 80% coverage |
|---|---|---|
| flows, 10-year window, α = 10 | 3.69 | 72.4% |
| **flows, 10-year window, α = 100** | **3.66** | 73.8% |
| flows, all history, α = 10 | 3.68 | 71.0% |
| flows, all history, α = 100 | 3.69 | 71.9% |
| **gbm, all history** | **3.78** | 69.7% |
| gbm, 10-year window | 3.82 | 63.9% |
| seasonal_5y (reference) | 4.10 | 74.3% |

## Selection-window results (2022–2025, 208 weeks)
| Model | MAE (mb) | Coverage | Brier | Passes |
|---|---|---|---|---|
| zero (the bar) | 4.04 | 82.7% | 0.252 | n/a |
| seasonal_5y | 4.34 | 82.2% | 0.264 | n/a |
| **flows** | **3.92** | 79.8% | 0.247 | **yes** |
| gbm | 3.90 | 78.8% | 0.229 | yes |
| ensemble | 3.87 | 79.8% | 0.232 | yes |

**Decision.** All three candidates pass. The ensemble has the lowest MAE, and `flows` is within 2% of it (3.92 ≤ 3.87 × 1.02). Under the tie-break the simpler model wins, so **`flows` launches**.

## Honest reading
- **Against the bar.** The selected model beats the strongest naive forecast by 3% (3.92 vs. 4.04 mb). Against the conventional seasonal baseline the margin is 10%, and the same holds over 2015–2025 as a whole (skill 10.3%).
- **The ceiling.** The adjustment residual (R10) caps what any flows-based model can do. The live American Petroleum Institute (API) print, a Phase 6 input, is the obvious next source of skill.
- **2022.** `flows` lost to zero change that year, during the SPR drawdown. The SPR features help, but they do not fully capture the release/exchange regime.
- **What the model learned** (fitted to 2015–2026, effect on the forecast in mb per one-standard-deviation move):

  | Feature | Effect | Reading |
  |---|---|---|
  | Refinery utilisation, 4-week change | −0.96 | Rising runs mean crude draws |
  | Implied balance, 4-week mean | +0.92 | Flow imbalances persist |
  | Seasonal mean | +0.75 | |
  | Residual, 4-week mean | +0.57 | The adjustment plug is sticky |
  | Last week's import change | −0.50 | Lumpy cargo arrivals reverse |
  | Stocks against 5-year average | −0.42 | Levels mean-revert |
  | Last week's residual | −0.35 | Last week's plug partly unwinds |
  | SPR change, 4-week mean | −0.23 | SPR releases land in commercial stocks |

## Consequences
- `flows` v1 is frozen for launch. `gbm` and `ensemble` will run in shadow and be scored alongside it publicly. Promoting either requires a new ADR and a new version (ADR 0005, step 6).
