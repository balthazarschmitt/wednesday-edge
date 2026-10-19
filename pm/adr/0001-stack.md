# ADR 0001: Python pipeline, static site, GitHub Actions scheduler

**Date:** 2026-10-19
**Status:** Accepted

## Context
The project needs a reliable weekly pipeline, an auditable record of forecasts, and a public dashboard. It must cost $0.

## Decision
- **Python 3.12+** (managed with uv) for data ingest, modeling, and backtesting. It is the standard on buy-side data teams and has the best libraries for this work: pandas, DuckDB, statsmodels, and LightGBM.
- **DuckDB** as the local analytical store. Raw API responses are kept as timestamped vintages so any past state can be rebuilt.
- **Git as the forecast ledger.** Forecasts go in as append-only JSON files, and commit timestamps prove when each was made.
- **GitHub Actions** as the scheduler, with redundant crons and idempotent jobs.
- **A static site on GitHub Pages** for the dashboard. It never sleeps, has no server to maintain, and is free.
- **LLM steps run locally only** (Claude Code under a Pro plan). They are optional and never part of the critical path.

## Alternatives rejected
- **Streamlit Community Cloud:** apps sleep when idle, so a recruiter could land on a wake-up screen.
- **Next.js on Vercel:** adds a second language and more moving parts without making the forecasts any more credible.
- **Hosted Claude API in the pipeline:** recurring cost, and it would add a failure mode to the critical path.
