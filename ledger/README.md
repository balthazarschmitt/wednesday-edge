# Forecast Ledger

This ledger is **append-only**. CI (`wedge ledger-check`) rejects any commit that modifies or deletes an existing file in this folder. Only README files may change.

| Path | Contents | Written by |
|---|---|---|
| `forecasts/{week}-crude.json` | The forecast (point, P10/P50/P90, P(build), shadow models, inputs hash), or a `missed` record | Forecast job, before the deadline |
| `scores/{week}-crude.json` | The actual, plus errors for the model, shadow models, baselines, and benchmarks | Score job, after the EIA release |
| `overrides/{week}-crude.json` | A human override with a reason. It must be logged before the deadline and is scored separately | `wedge override` |
| `consensus/{week}-api.json` | The American Petroleum Institute (API) print, with a source URL | `wedge log api` |
| `consensus/{week}-consensus-{source}.json` | Analyst consensus, with a source URL | `wedge log consensus` |

`{week}` is the Friday the EIA data week ends. Values are in thousand barrels (kb). A week with no forecast entry once its deadline passes is recorded as `missed` by the score job, so gaps are never silent.

`shadow/` uses the same layout and holds the pre-launch shadow-mode record (Phase 8). Shadow results are kept but are not part of the public track record.
