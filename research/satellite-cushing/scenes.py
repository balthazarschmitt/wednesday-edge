"""List clear Sentinel-2 L2A scenes over the Cushing tank farms, with sun elevation."""

import json
import sys

import planetary_computer
import pystac_client

BBOX = [-96.80, 35.93, -96.71, 36.00]
out = sys.argv[1]

cat = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1", modifier=planetary_computer.sign_inplace
)
items = cat.search(
    collections=["sentinel-2-l2a"],
    bbox=BBOX,
    datetime="2024-10-01/2026-10-20",
    query={"eo:cloud_cover": {"lt": 3}},
).item_collection()
rows = []
for it in items:
    p = it.properties
    rows.append(
        {
            "id": it.id,
            "date": p["datetime"][:10],
            "time": p["datetime"][11:16],
            "cloud": p["eo:cloud_cover"],
            "sun_elev": round(90 - p["s2:mean_solar_zenith"], 1),
            "sun_az": round(p["s2:mean_solar_azimuth"], 1),
            "tile": p["s2:mgrs_tile"],
        }
    )
rows.sort(key=lambda r: r["date"])
with open(out, "w") as fh:
    json.dump(rows, fh, indent=1)
print(len(rows), "scenes")
for r in rows:
    print(r)
