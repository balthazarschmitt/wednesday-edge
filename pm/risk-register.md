# Risk Register

Probability (P) and Impact (I) are each scored 1–3. Review this register weekly.

| ID | Risk | P | I | Response | Status |
|---|---|---|---|---|---|
| R1 | A GitHub Actions cron is delayed or skipped, so a forecast misses the deadline | 2 | 3 | Run three staggered crons with idempotent jobs, plus a manual `workflow_dispatch` or local fallback | Open |
| R2 | The EIA API is down or the key fails | 3 | 3 | Retry with backoff, fall back to the dnav XLS, then to the cached vintage, with a staleness flag. **Occurred 2026-10-19:** one 60s timeout, and latency climbed to 44s. Raised P to 3; batch series into one request | Open |
| R3 | A holiday shifts the release, and the scorer or deadline logic breaks | 3 | 2 | Calendar logic never assumes Wednesday; the scorer polls until data appears; holiday cases are tested. Rule reproduces all six published 2026 exceptions; the published table overrides the rule | Mitigated |
| R4 | Look-ahead leakage inflates the backtest | 2 | 3 | One `as_of` path for building features, plus leakage tests in CI. Six leakage tests, all shown to fail when the release filter is removed | Mitigated |
| R5 | The model fails to beat the best naive baseline | 3 | 2 | Fix the selection rule in advance, launch the best model anyway, and write up the result honestly. P raised to 3: in 2022–2025, zero change beats the seasonal baseline (ADR 0005) | Open |
| R6 | Consensus data is unavailable for some weeks | 3 | 1 | Log it by hand through the CLI; report comparisons only on weeks with both values | Open |
| R7 | The weekly routine gets skipped (owner fatigue) | 2 | 2 | The pipeline runs fully without manual input, and manual steps stay under 15 minutes | Open |
| R8 | EIA series IDs or facets differ from assumptions | 2 | 2 | Phase 1 data spike, with findings recorded in an ADR | Closed: all IDs confirmed; adjustment is derived (ADR 0002) |
| R11 | The API key leaks through logs or committed files | 2 | 3 | httpx logging is held at WARNING, the code refuses to write vintages containing the key, regression tests cover both, and Actions secrets are masked. **Occurred 2026-10-19 (local terminal only)** | Mitigated |
| R12 | Unstable EIA pagination silently drops or repeats rows | 2 | 3 | A tiebreaker sort, a row-count check against `total`, and duplicate validation. **Occurred 2026-10-19; caught by validation** | Mitigated |
| R10 | The derived adjustment residual (σ ≈ 4.2 mb/wk) dominates forecast error | 3 | 2 | Model the residual explicitly, publish intervals, and explain it on the methodology page | Open |
| R9 | Scheduled workflows are disabled after 60 days without commits | 1 | 3 | Weekly ledger commits keep the repo active | Open |
| R13 | Backtests use today's values, not those first published, so revisions flatter history slightly | 1 | 1 | Weekly EIA data is rarely revised; live forecasts use true point-in-time vintages; disclosed on the methodology page | Accepted |
