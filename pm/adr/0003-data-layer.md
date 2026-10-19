# ADR 0003: Data layer (ingest, vintages, revision log)

**Date:** 2026-10-19
**Status:** Accepted

## Decision
- **One batched API request per pull.** All 12 series go in a single request, paginated at 5,000 rows. Sorting is by `period` and then by `series`. The client checks that the row count matches EIA's `total` and that no row is repeated.
- **Retry with backoff.** Up to 5 attempts with exponential backoff (3s, 6s, 12s, 24s) on HTTP 429/5xx, transport errors, and responses that aren't JSON. Any other 4xx fails immediately.
- **Fallback to EIA's legacy per-series XLS workbooks.** These need no API key. Each sheet's `Sourcekey` is checked against the series ID we requested.
- **Validation before anything is stored.**
  - Hard errors: missing series, duplicates, periods that aren't Fridays, negative values, refinery utilization above 105%.
  - Warnings: weekly stock moves larger than 30 mb, stale data.
- **Vintage CSVs committed to git** under `data/raw/eia/YYYY/`. We write our own normalized rows, never EIA's response body, and refuse to write any file containing the API key. These files are the source of truth. The DuckDB database is gitignored and can be rebuilt with `wedge rebuild-db`.
- **`observations` is a revision log.** A row is inserted only when its value differs from the latest stored value for that series and period. `known_as_of(t)` reconstructs exactly what we knew at time t.

## Incidents found while building (2026-10-19)
1. **EIA instability.** We saw a 60-second timeout, 502 and 504 errors, and latency of 44 seconds or more. Retries absorbed every failure in the final runs.
2. **Unstable pagination.** Sorting by `period` alone produced 5 duplicate rows across pages, and presumably as many silently missing rows. Validation rejected the pull, so nothing bad was stored. The fix was a tiebreaker sort plus a count check, now covered by a regression test.
3. **API key exposed in logs.** httpx logs every request URL at INFO level, and EIA requires the key in the URL, so one local run printed the key to the terminal. It was never written to a file or committed. The fix raises the httpx and httpcore log level to WARNING, and a regression test asserts the key never appears in logs. GitHub Actions also masks secrets in its logs.

## Validation results
- **Full backfill:** 24,396 rows, 12 series, from 1982-08-20 to 2026-10-09.
- **Cross-source check:** an incremental XLS pull and an incremental API pull matched the stored backfill exactly. Both inserted 0 new rows.
- **Rebuild:** `rebuild-db` from the 3 vintage files reproduces the database.
- **Propane (WPRSTUS1):** 8 historical weekly moves above 30 mb raise a warning. These come from changes in how EIA defines the series. Propane is not a target, so we accept the warning.
