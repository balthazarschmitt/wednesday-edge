# ADR 0007: Live forecast and score jobs

**Date:** 2026-10-19
**Status:** Accepted

## Forecast job (`wedge forecast`, `.github/workflows/forecast.yml`)
- **Schedule.** Five staggered crons:
  - three on Tuesday evening ET, after the American Petroleum Institute (API) print;
  - a Wednesday 08:17 ET last resort;
  - a Thursday morning run for holiday weeks.
- **Idempotent.** If an entry for the week already exists, the job exits 0.
- **Forecast window.** Forecasts open Tuesday 12:00 ET. Without this, the Thursday run in a normal week would forecast *next* week days early, and the idempotency rule would then lock that early forecast in.
- **Two-sided deadline guard.** The job refuses to write a forecast in two cases:
  - it is past `deadline` (15 minutes before release);
  - the week's actual is already in the data.

  It re-checks the deadline after modelling, before writing. A refusal writes a `missed` record and exits 1, so GitHub emails the owner.
- **Ingest failure.** If ingest fails (API, then XLS), the job still forecasts from stored data and records `ingest_error` and `weeks_stale`. A missing API key now falls back to the XLS source instead of crashing.
- **Each entry records:**
  - the model version (`flows-v1`) and git SHA;
  - the forecast, plus every shadow model and baseline;
  - all features;
  - a SHA-256 of the input data, so any forecast can be audited against the committed vintages.
- **Same path as the backtest.** The live path is the backtest path: a test asserts that `predict_all` at a week's decision time equals `walk_forward` for that week.

## Score job (`wedge score`, `.github/workflows/score.yml`)
- **Polling.** Polls Wednesday through Friday and waits until the actual exists, so holiday shifts need no special case.
- **Scored once.** Each week gets one score file, which is never rewritten.
- **Validity.** A forecast created at or after the release time is marked `invalid`, not scored.
- **What gets scored:**
  - the API print, consensus, and override entries, when logged;
  - weeks inside the ledger's span with no entry, which become `missed`.

## Integrity
- **CI check.** `wedge ledger-check` runs on every push and PR. It diffs the ledger against the previous commit and rejects anything other than added files. It also rejects any new forecast or override created after its deadline.
- **Concurrency.** Both workflows share the `ledger` concurrency group and rebase before pushing, so they never race.

## Shadow mode
- **Where entries go.** Jobs write to `ledger/shadow/` until the repository variable `WEDGE_LIVE` is set to `true` at launch (Phase 9).
- **Starting early.** Shadow mode can start this week, ahead of the planned November 17 start, which buys extra cycles to shake out timing bugs.

## Manual inputs (about 5 minutes a week, all optional)
```bash
uv run wedge log api --change -2.1 --url <article>
uv run wedge log consensus --change -1.0 --source "S&P Global poll" --url <article>
uv run wedge override --change -0.5 --reason "..."   # before the deadline only
```
- Values are entered in mb, as news reports print them. Every entry needs a URL.
- Consensus entries may be backfilled, and are flagged with `logged_before_deadline`.
