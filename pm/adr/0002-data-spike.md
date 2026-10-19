# ADR 0002: Phase 1 data spike findings

**Date:** 2026-10-19
**Status:** Accepted

## EIA API v2
- **Route:** `petroleum/sum/sndw` (weekly supply and disposition) contains 608 series. These include all stock series that also appear under `petroleum/stoc/wstk`, so a single route covers everything we need.
- **Confirmed series:**

| Key | Series ID | Units |
|---|---|---|
| Commercial crude stocks (target) | WCESTUS1 | kb |
| SPR stocks | WCSSTUS1 | kb |
| Cushing stocks | W_EPC0_SAX_YCUOK_MBBL | kb |
| Field production | WCRFPUS2 | kb/d |
| Commercial imports (excluding SPR) | WCEIMUS2 | kb/d |
| Exports | WCREXUS2 | kb/d |
| Refiner net input | WCRRIUS2 | kb/d |
| Refinery utilization | WPULEUS3 | % |
| Gasoline / distillate / jet / propane stocks | WGTSTUS1 / WDISTUS1 / WKJSTUS1 / WPRSTUS1 | kb |

- **History:** WCESTUS1 runs from 1982-08-20 to 2026-10-09, 2,298 weekly rows. That fits in one request, under the 5,000-row cap.
- **No crude "adjustment" series** (`WCRAUS2` returns 0 rows). We derive it as a residual:
  `residual = Δstocks − 7 × (production + commercial imports − exports − refinery input)`.

## The residual dominates
Over the 71 weeks from June 2025 to October 2026:
- the standard deviation of the residual is **4.2 mb/week**;
- the standard deviation of Δstocks is **5.6 mb/week**;
- the residual was persistently positive in Aug–Sep 2026, ranging from +1 to +12 mb/week.

**Implications:**
1. A model built only on flows will be noisy.
2. The residual's level and persistence need their own model.
3. Predicting a distribution matters as much as predicting a point.

This finding is also a core part of the methodology write-up.

## Reliability
- One request timed out after 60 seconds with no response.
- Request latency rose from 6 seconds to 44 seconds across about 9 sequential calls.

**Decisions:**
- Use a 120-second timeout with exponential backoff.
- Batch every series into a single request with repeated `facets[series][]` parameters.
- Keep the cached-vintage fallback.

## Release calendar
The EIA holiday schedule page (eia.gov/petroleum/supply/weekly/schedule.php) lists six 2026 exceptions. Each moves the release to **Thursday at 12:00 ET**: MLK Day, Presidents' Day, Memorial Day, Labor Day, Columbus Day, and Veterans Day (Thu Nov 12).

Every listed exception is a federal holiday falling Monday through Wednesday of the release week. So the calendar applies that rule, and a test checks it against this published 2026 list.

Some holidays are not on the list: Thanksgiving falls on a Thursday, and Christmas and New Year's fall on Fridays in 2026. None of them move the release.

## IMF PortWatch
- **Endpoint:** ArcGIS FeatureServer at `services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/{Daily_Ports_Data,Daily_Chokepoints_Data}/FeatureServer/0`.
  - The service caps each response at 1,000 records.
  - Field names must be valid; an invalid name returns a generic "Invalid query parameters" error.
- **Ports data:** daily port calls plus import and export tonnage by vessel type, including `import_tanker` and `export_tanker` in metric tonnes. It covers Beaumont, Port Arthur, Texas City and Corpus Christi. Houston is not under that name, so this needs checking.
- **Lag:** on 2026-10-19 the latest date available was 2026-10-11, about 8 days behind. At forecast time (Tuesday), PortWatch does **not** yet cover the target week, which ends the previous Friday.

**Decision:** PortWatch stays a post-launch feature experiment (Phase 10). It is useful only if the previous week's tanker activity predicts EIA's import and export estimates. That has to be tested walk-forward before it enters any model.
