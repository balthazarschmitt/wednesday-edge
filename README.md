# Wednesday Edge

Every week, before the U.S. Energy Information Administration (EIA) releases its Weekly Petroleum Status Report, this project publishes a forecast of the weekly change in U.S. commercial crude oil inventories. Each forecast is committed to this repository with a timestamp. Once EIA publishes the actual number, the forecast is scored automatically against it, against naive baselines, and against the analyst consensus.

> **Status:** under construction (Phase 0, scaffold). The public track record starts at launch, targeted for early December 2026.

## The rules

1. **Forecasts are committed before the EIA release.** The git commit timestamp is the proof.
2. **The ledger is append-only.** CI rejects any change to a past forecast.
3. **Misses stay.** The track record is never reset, and a week the pipeline fails to forecast is recorded as `missed`.
4. **Human overrides are logged and scored separately** from the model.
5. **Model changes are versioned.** Scores are reported for each model version and for the whole record.

## Quick start

```bash
uv sync
cp .env.example .env    # add your free EIA API key
uv run pytest
uv run wedge --help
```

## Repository layout

| Path | Contents |
|---|---|
| `src/wedge/` | The pipeline: ingest, features, models, forecast, score |
| `ledger/` | The append-only record of forecasts, overrides, and logged consensus |
| `pm/` | Project charter, risk register, milestones, and architecture decision records |
| `site/` | The static dashboard, served on GitHub Pages |

## AI use

The code is written with Claude Code. I design the model, make the methodology calls, log and justify every override, and own the results.
