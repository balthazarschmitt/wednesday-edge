"""Side-by-side zoom of the same window on two dates.

Usage: zoom.py <dir> <out.png> r0 r1 c0 c1 <npyA> <npyB>
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

SCALE = 8

d = Path(sys.argv[1])
r0, r1, c0, c1 = map(int, sys.argv[3:7])
tiles = []
for name in sys.argv[7:]:
    a = np.moveaxis(np.load(d / name), 0, -1)[r0:r1, c0:c1].astype(float)
    lo, hi = np.percentile(a, 1), np.percentile(a, 99.5)
    a = np.clip((a - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)
    im = Image.fromarray(a).resize(((c1 - c0) * SCALE, (r1 - r0) * SCALE), Image.NEAREST)
    ImageDraw.Draw(im).text((8, 8), name[11:19], fill=(255, 255, 0))
    tiles.append(im)
width = sum(t.width for t in tiles) + 10 * (len(tiles) - 1)
out = Image.new("RGB", (width, tiles[0].height), (40, 40, 40))
x = 0
for t in tiles:
    out.paste(t, (x, 0))
    x += t.width + 10
out.save(sys.argv[2])
print(out.size)
