# Project Charter: Wednesday Edge

**Owner:** Balthazar Schmitt
**Start date:** 2026-10-19
**Target public launch:** early December 2026 (after 2 weeks of shadow mode)

## Objective
Publish a weekly forecast of the change in U.S. commercial crude inventories (EIA series WCESTUS1). Each forecast is timestamped and committed to git before the EIA release, then scored automatically and in public against the actual figure, naive baselines, and analyst consensus.

## Success metrics
| Metric | Target |
|---|---|
| Weekly forecasts committed before the deadline | 100% after launch, with any miss recorded and explained |
| Out-of-sample skill versus the 5-year seasonal baseline (2022–2025 walk-forward) | MAE lower than the baseline |
| Live MAE versus logged consensus | Reported honestly; the target is parity or better within 26 weeks |
| P10–P90 interval coverage | 70–90% |
| Pipeline uptime (scheduled runs succeeding without manual help) | ≥ 95% |

## In scope
- Commercial crude inventory forecasts. Gasoline, distillate, and Cushing come after launch.
- A data pipeline, models, an append-only ledger, a scorer, and a static dashboard.
- A local, optional workflow for drafting notes with an LLM.

## Out of scope (for now)
- Paid data.
- Live trading or price-signal claims.
- A Substack or LinkedIn automation. The design leaves hooks for these.

## Constraints
- $0 budget: free data, GitHub Actions, and GitHub Pages.
- No more than about 15 minutes of manual work per week once live.
- Forecasts must not depend on manual inputs. If the API print or consensus has not been logged, the pipeline still runs.

## Key stakeholders
- **Owner/operator:** me.
- **Audience:** recruiters and interviewers in asset management, wealth management, and commodities.
