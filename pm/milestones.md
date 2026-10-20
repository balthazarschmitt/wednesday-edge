# Milestones: Planned vs Actual

| Phase | Deliverable | Planned | Actual | Notes |
|---|---|---|---|---|
| 0 | Scaffold, CI, charter, risk register | 2026-10-19 | 2026-10-19 | CI green on GitHub |
| 1 | Data spike: verify series IDs, holiday schedule, PortWatch | 2026-10-22 | 2026-10-19 | See ADR 0002; residual finding |
| 2 | Ingest, DuckDB store, vintages, fallback, validation | 2026-10-27 | 2026-10-19 | ADR 0003; 3 incidents caught and fixed |
| 3 | Calendar/deadline logic, point-in-time features, leakage tests | 2026-10-31 | 2026-10-19 | ADR 0004; leakage tests mutation-checked |
| 4 | Baselines, walk-forward backtest, metrics report | 2026-11-04 | 2026-10-19 | ADR 0005; selection rule pre-registered; bar raised to best baseline |
| 5 | Flows model, LightGBM, quantiles, fixed selection rule | 2026-11-10 | 2026-10-19 | ADR 0006; `flows` selected: 3.92 mb vs 4.04 bar |
| 6 | Live forecast and score jobs, ledger integrity, crons, manual CLI | 2026-11-14 | 2026-10-19 | ADR 0007; live path = backtest path (tested) |
| 7 | Static site on GitHub Pages | 2026-11-18 | | |
| 8 | Shadow mode (2 weekly cycles) | 2026-11-17 to 2026-12-02 | | Can start week of 2026-10-20; includes Veterans Day (Thu release) |
| 9 | Public launch | 2026-12-08 | | First public forecast |
