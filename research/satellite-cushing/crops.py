"""Cut the Cushing window out of selected Sentinel-2 true-colour scenes and save upscaled PNGs.

Reads only the needed window from the cloud-optimised GeoTIFF (no full-tile download).
Usage: crops.py <out_dir> <item_id> [<item_id> ...]
"""

import sys
from pathlib import Path

import numpy as np
import planetary_computer
import pystac_client
import rasterio
from PIL import Image
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

BBOX = (-96.795, 35.935, -96.715, 35.995)
SCALE = 4

out = Path(sys.argv[1])
cat = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1", modifier=planetary_computer.sign_inplace
)
for item_id in sys.argv[2:]:
    item = cat.get_collection("sentinel-2-l2a").get_item(item_id)
    with rasterio.open(item.assets["visual"].href) as src:
        win = from_bounds(*transform_bounds("EPSG:4326", src.crs, *BBOX), src.transform)
        rgb = src.read(window=win, boundless=False)  # 3 x H x W uint8
        np.save(out / f"{item_id[:30]}_visual.npy", rgb)
    img = Image.fromarray(np.moveaxis(rgb, 0, -1))
    img = img.resize((img.width * SCALE, img.height * SCALE), Image.NEAREST)
    path = out / f"{item.properties['datetime'][:10]}.png"
    img.save(path)
    print(path.name, rgb.shape, f"sun {90 - item.properties['s2:mean_solar_zenith']:.0f} deg")
