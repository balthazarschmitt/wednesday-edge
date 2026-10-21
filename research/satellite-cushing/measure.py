"""Rough feasibility test: does tank-roof shadow at Cushing track EIA's weekly Cushing stocks?

1. Tank mask from a summer scene (sun high, so roofs are bright, shadow-free discs).
2. For each low-sun scene, shadow fraction = share of tank pixels much darker than in summer.
3. Shadow width ~ roof depth x cot(sun elevation), so depth index = shadow fraction / cot(elev).
4. Compare with EIA Cushing stocks for the week containing the image date.

Usage: measure.py <data_dir>
"""

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import planetary_computer
import pystac_client
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from scipy import ndimage

BBOX = (-96.795, 35.935, -96.715, 35.995)
FARM_ROW0 = 380  # rows above this are the town, not tank farms
d = Path(sys.argv[1])

cat = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1", modifier=planetary_computer.sign_inplace
)
coll = cat.get_collection("sentinel-2-l2a")


def load(item_id):
    cache = d / f"{item_id}.npy"
    if cache.exists():
        return np.load(cache)
    item = coll.get_item(item_id)
    with rasterio.open(item.assets["visual"].href) as src:
        win = from_bounds(*transform_bounds("EPSG:4326", src.crs, *BBOX), src.transform)
        a = src.read(window=win).mean(axis=0)
    np.save(cache, a)
    return a


scenes = [s for s in json.loads((d / "scenes.json").read_text()) if s["tile"] == "14SPE"]
ref = load("S2B_MSIL2A_20260617T170849_R112_T14SPE_20260617T205508")
farm = np.zeros_like(ref, bool)
farm[FARM_ROW0:] = True
bright = (ref > np.percentile(ref[farm], 97)) & farm
lab, n = ndimage.label(bright)
sizes = ndimage.sum(bright, lab, range(1, n + 1))
keep = np.isin(lab, 1 + np.flatnonzero((sizes >= 8) & (sizes <= 250)))
mask = ndimage.binary_dilation(keep, iterations=1)  # include the rim, where shadow starts
print(f"tank components kept: {int(((sizes >= 8) & (sizes <= 250)).sum())}, mask px: {mask.sum()}")

cush = pd.read_csv(d / "cushing.csv", index_col=0, parse_dates=True)["cushing_kb"]
rows = []
seen = set()
for s in scenes:
    if s["sun_elev"] > 50 or s["date"] in seen:
        continue
    seen.add(s["date"])
    a = load(s["id"])
    if a.shape != ref.shape:
        continue
    ratio = a[mask] / np.maximum(ref[mask], 1)
    shadow = float((ratio < 0.55).mean())
    cot = 1 / math.tan(math.radians(s["sun_elev"]))
    date = pd.Timestamp(s["date"])
    week_end = date + pd.Timedelta(days=(4 - date.weekday()) % 7)  # EIA week ends Friday
    rows.append(
        {
            "date": s["date"],
            "sun": s["sun_elev"],
            "shadow_frac": round(shadow, 4),
            "depth_index": round(shadow / cot, 4),
            "cushing_mb": cush.get(week_end, np.nan) / 1000,
        }
    )
df = pd.DataFrame(rows).dropna()
df.to_csv(d / "measure.csv", index=False)
print(df.to_string(index=False))
print("\ncorr(depth_index, cushing):", round(df["depth_index"].corr(df["cushing_mb"]), 3))
print("corr(shadow_frac, cushing):", round(df["shadow_frac"].corr(df["cushing_mb"]), 3))
cot_sun = 1 / np.tan(np.radians(df["sun"]))
print("corr(shadow_frac, cot(sun)):", round(df["shadow_frac"].corr(cot_sun), 3))
import statsmodels.api as sm  # noqa: E402

X = sm.add_constant(pd.DataFrame({"cot": cot_sun, "cushing": df["cushing_mb"]}))
print(sm.OLS(df["shadow_frac"], X).fit().summary().tables[1])
