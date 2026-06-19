#!/usr/bin/env python3
"""Render a thumbnail per item (+ a collection thumbnail) from each COG's overview.

Reads a decimated overview over the network (no full download), masks nodata to transparency,
applies a colour ramp (confidence/density match the FTW inference app), composites over the dark
teal app background, and writes thumbnail.png into each item dir. Rerunnable.
"""
from __future__ import annotations
import os
from pathlib import Path

import numpy as np
import rasterio
import matplotlib
matplotlib.use("Agg")
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.cm as cm
from PIL import Image

os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")

ROOT = Path(__file__).resolve().parents[1]  # repo root (scripts/ -> ..)
COLL = ROOT / "predictions" / "confidence"
# COGs are still at the flat (pre-restructure) location; read from there.
CUR_BASE = "https://data.source.coop/ftw/global-data/predictions/confidence"
BG = (11, 20, 20)  # #0b1414, the app's dark background
WIDTH = 1280

magenta_green = LinearSegmentedColormap.from_list("magenta_green", ["#ff00ee", "#00ff00"])

# item_id -> (filename, band, colormap, vmin, vmax_or_None_for_p98, nodata)
SPECS = {
    "confidence": ("prue_v1_confidence_global.tif", 1, cm.get_cmap("RdYlGn"), 0.0, 0.578178, -1.0),
    "field-density": ("prue_v1_field_area_500m_fieldsonly.tif", 1, magenta_green, 0.0, None, 0.0),
    "entropy": ("prue_v1_entropy_500m.tif", 1, cm.get_cmap("magma"), 0.0, None, None),
    "crop-consensus": ("prue_v1_crop_count_mean_500m.tif", 1, cm.get_cmap("YlGn"), 0.0, 8.0, 0.0),
    "precision-recall": ("prue_v1_precision_recall_500m.tif", 1, cm.get_cmap("viridis"), 0.0, 1.0, None),
}


def render(item_id, fname, band, cmap, vmin, vmax, nodata):
    url = f"{CUR_BASE}/{fname}"
    with rasterio.open(url) as ds:
        h = max(1, round(WIDTH * ds.height / ds.width))
        arr = ds.read(band, out_shape=(h, WIDTH), masked=True).astype("float64")
        nd = nodata if nodata is not None else ds.nodatavals[band - 1]
    data = np.ma.masked_invalid(arr)
    if nd is not None:
        data = np.ma.masked_equal(data, nd)
    valid = data.compressed()
    if vmax is None:
        vmax = float(np.percentile(valid, 98)) if valid.size else 1.0
        if vmax <= vmin:
            vmax = vmin + 1.0
    norm = np.clip((data.filled(vmin) - vmin) / (vmax - vmin), 0, 1)
    rgba = (cmap(norm) * 255).astype("uint8")  # HxWx4
    # alpha: transparent where masked
    mask = np.ma.getmaskarray(data)
    rgba[..., 3] = np.where(mask, 0, 255)
    fg = Image.fromarray(rgba, "RGBA")
    bg = Image.new("RGBA", fg.size, BG + (255,))
    out = Image.alpha_composite(bg, fg).convert("RGB")
    dest = COLL / item_id / "thumbnail.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.save(dest, optimize=True)
    print(f"  {item_id}: {out.size} -> {dest.relative_to(ROOT)} (vmax={vmax:.3g})")
    return dest


def main():
    last = None
    for item_id, (fname, band, cmap, vmin, vmax, nodata) in SPECS.items():
        print(f"Rendering {item_id}")
        last = render(item_id, fname, band, cmap, vmin, vmax, nodata)
    # collection thumbnail = confidence thumbnail
    coll_thumb = COLL / "thumbnail.png"
    Image.open(COLL / "confidence" / "thumbnail.png").save(coll_thumb)
    print(f"collection thumbnail -> {coll_thumb.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
