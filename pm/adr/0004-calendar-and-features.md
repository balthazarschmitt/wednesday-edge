# ADR 0004: Release calendar and point-in-time features

**Date:** 2026-10-19
**Status:** Accepted

## Decision
- **Release calendar (`releases.py`).**
  - Data for week ending Friday F is released Wednesday 10:30 ET.
  - If a federal holiday falls Monday through Wednesday of that week, the release moves to Thursday 12:00 ET.
  - Federal holidays are computed in code, with Saturday/Sunday observance rules, so no extra dependency is needed.
  - EIA's published 2026 table takes precedence over the rule. A test checks that the rule alone reproduces all six published exceptions.
  - All times are timezone-aware (America/New_York), and the DST changeover is tested.
- **Deadline guard.** `check_open` raises `DeadlineMissed` from 15 minutes before release onward. The forecast job (Phase 6) records that week as *missed* and never backfills.
- **Decision time.** Backtests simulate the forecast on Tuesday at 18:00 ET, after the API print.
- **Point-in-time features (`features.build(wide, as_of)`).**
  - A week is visible only once its release time is ≤ `as_of`.
  - Rows are filtered *before* any diff or rolling window, so a derived value cannot reach forward.
  - `build_many` builds backtest matrices by calling `build` once per week at that week's decision time. There is no separate vectorised path that could drift from the live path.
- **Vintages.** Live and audit use `point_in_time`: only pulls fetched by `as_of`. Historical backtests use `latest` values, because we hold no older vintages (risk R13). The release filter applies either way.

## Features (31)
- **Stock changes:** lags 1–4.
- **Implied flow balance and residual:** `7 × (production + imports − exports − runs)`, and the residual as a lag plus 4- and 13-week means.
- **Each flow:** level, 1-week change, and 4-week mean.
- **Refinery utilisation:** level and 4-week change.
- **Stock levels:** stock level vs. its 5-year same-week average, and Cushing.
- **Seasonal mean:** 5-year same-week mean change.
- **Calendar flags:** week of year, hurricane season, holiday in the data week, shifted release.
- **Data quality:** weeks stale.

## Verification
- **Leakage tests.** Two kinds:
  1. Setting every row released after `as_of` to ±1e9, and appending fake future weeks, leaves the features unchanged.
  2. A 60-week backtest matrix is identical with and without future rows.
- **Mutation check.** With the release filter removed, all six leakage tests fail.
- **Real data, 2015-01 to 2026-10.** 615 weeks build in 5 seconds with zero missing cells.
- **First look at baselines (MAE, Phase 4 will formalise):**

  | Baseline | MAE |
  |---|---|
  | Zero change | 4.26 mb |
  | Last week's change | 5.05 mb |
  | 5-year seasonal mean | 4.23 mb |

  The seasonal mean barely beats zero. The lag-1 residual has σ ≈ 4.7 mb, against σ ≈ 5.4 mb for the weekly change itself. That confirms R10: the unexplained "adjustment" term is most of the problem, which is where the API print and flow models have to earn their keep.
