# Forecast Ledger

This ledger is **append-only**. CI rejects any commit that modifies or deletes an existing file in this folder.

- `forecasts/`: one JSON file per forecast, committed before the EIA release
- `overrides/`: human overrides, committed before the deadline and scored separately
- `consensus/`: manually logged analyst consensus and API prints, each with a source URL
