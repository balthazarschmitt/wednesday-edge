# ADR 0008: Satellite tank-shadow signal at Cushing (feasibility)

**Date:** 2026-10-21
**Status:** Feasibility done. Signal is visible but weak with a crude method. A full study is proposed for Phase 10. Nothing feeds the launch model.

## Question
Most large crude tanks have floating roofs. The tank wall casts a crescent-shaped shadow on the roof, and the lower the roof (the emptier the tank), the larger the crescent. Commercial providers sell fill estimates built this way from sub-metre imagery. Can **free 10 m Sentinel-2 imagery** see the same signal at Cushing, Oklahoma, where EIA publishes weekly stocks we can check against?

## Geometry
- Cushing's large tanks are about 60–110 m across, or 6–11 pixels.
- With a roof 15 m below the rim, the shadow is `15 m × cot(sun elevation)` long.
- Sentinel-2 passes over Cushing at about 11:10 local time. The sun is then about 29° up in late December (shadow about 27 m, or 2.7 px) and about 71° up in late June (about 5 m, or 0.5 px).
- So the signal can only exist from roughly **October to March**.

## What was done
Code and outputs are in `research/satellite-cushing/`.
1. **Scenes.** 84 Sentinel-2 L2A scenes under 3% cloud over Cushing, Oct 2024 to Oct 2026, from Microsoft Planetary Computer (free, no account needed). Cloud cover is not a constraint.
2. **Visual check.** A low-sun scene (2025-12-26) and a high-sun one (2026-06-17) of the same tank farm show clear crescents of **different sizes on different tanks** in winter and none in summer (`winter_vs_summer.png`).
3. **Crude measurement.**
   - Tank pixels were taken from the summer scene: about 240 bright discs.
   - For each of 29 low-sun dates, "shadow fraction" is the share of tank pixels under 55% of their summer brightness.
   - This was compared with EIA weekly Cushing stocks for the week containing the image.

## Results (29 scenes)
- **Sun angle dominates:** corr(shadow, cot(sun elevation)) = **0.88**.
- **Stocks pull the right way.** Regressing shadow on cot(sun) and Cushing stocks gives a Cushing coefficient of −0.006 per mb (more oil, less shadow), with **p = 0.15**. It is not significant at this sample size and with this method.
- **Matched-sun dates are suggestive:**

  | Date | Sun | Shadow | EIA Cushing |
  |---|---|---|---|
  | 2024-12-29 | 29° | 26% | 20.0 mb |
  | 2025-12-26 | 29° | 24% | 22.1 mb |
  | 2026-01-03 | 29° | 17% | 23.6 mb |
  | 2025-01-13 | 30° | 20% | 20.7 mb |
  | 2026-01-13 | 30° | 18% | 25.1 mb |

- **Known problems:**
  - Snow: 2026-01-28 shows almost no shadow, likely snow cover.
  - The crop missed parts of the southern and eastern farms.
  - Counting dark pixels is crude; it does not measure each tank's crescent.
  - Fixed-roof tanks and pipeline fill are invisible.

## Decision
- **Not a model input now.** The launch model (`flows-v1`) is unchanged.
- **Proposed Phase 10 study.** The success test below must be committed before the run, as in ADR 0005.
  - **Tank map:** full outlines from OpenStreetMap (`man_made=storage_tank`). The Overpass API was overloaded during this check.
  - **Measurement:** per tank, sub-pixel crescent width along the sun azimuth, converted to roof depth with the scene's sun elevation.
  - **Filtering:** drop snow and haze scenes (Sentinel-2 snow probability and SCL bands).
  - **History:** Sentinel-2 L2A back to 2017, giving about 8 winters.
  - **Pre-registered test:** in Oct–Mar weeks, the satellite estimate of the **weekly change** in Cushing stocks must beat a last-week persistence baseline out of sample. Otherwise the result is recorded as negative and the idea is closed.
- **Scope note.** Cushing is about 5% of US commercial stocks, and the method is seasonal. Even a success would mainly support a Cushing forecast, with a small effect on the national number.

## Attribution
Contains modified Copernicus Sentinel data (2024–2026), accessed via Microsoft Planetary Computer.
