#!/usr/bin/env python3
"""Append a per-polygon `confidence` column to an FTW field-boundary GeoParquet.

Confidence is centroid-sampled (point-on-surface) from the 500 m PRUE confidence
COG and scaled to a 0-100 percentage using 0.578178 as 100% — matching the
ftw-inference-app legend (raw 0.404->70, 0.463->80, 0.521->90, 0.578->100).
Raster nodata (-1) and any negative/NaN become null. The original GeoParquet
schema and its `geo` metadata are preserved; only the one column is added.

The COG window covering the parquet's points is read once (the global COG is far
too large to read whole), so this stays cheap even for big country parquets.

Usage:
    python3 add_confidence.py IN.parquet OUT.parquet [--cog URL]
"""
from __future__ import annotations

import argparse
import json
import sys

# 100% point of the modeled confidence range (see confidence collection / app).
CONF_MAX = 0.578178
DEFAULT_COG = (
    "https://data.source.coop/ftw/global-data/predictions/confidence/"
    "confidence/prue_v1_confidence_global.tif"
)


def raw_to_confidence(raw, nodata: float = -1.0):
    """Scale a raw COG value to 0-100, or None for nodata/invalid."""
    if raw is None:
        return None
    val = float(raw)
    if val != val:  # NaN
        return None
    if val == nodata or val < 0:
        return None
    return min(val / CONF_MAX * 100.0, 100.0)


def sample_points(xs, ys, array, transform, nodata: float = -1.0):
    """Look up each (x, y) in `array` (with affine `transform`), returning a
    list of scaled confidence values (None when out of bounds or nodata)."""
    inv = ~transform
    h, w = array.shape
    out = []
    for x, y in zip(xs, ys):
        fcol, frow = inv * (x, y)
        col, row = int(fcol), int(frow)
        if row < 0 or row >= h or col < 0 or col >= w:
            out.append(None)
            continue
        out.append(raw_to_confidence(array[row, col], nodata))
    return out


def representative_points(wkb_list):
    """Point-on-surface (guaranteed inside the polygon) x/y arrays from WKB."""
    import shapely
    geoms = shapely.from_wkb(wkb_list)
    pts = shapely.point_on_surface(geoms)
    return shapely.get_x(pts), shapely.get_y(pts)


def enrich(in_path: str, cog_path: str, out_path: str) -> int:
    """Read IN, sample confidence, write OUT with a `confidence` float32 column.
    Returns the count of non-null confidence values."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    import math

    import rasterio
    from rasterio.windows import Window, from_bounds

    pf = pq.ParquetFile(in_path)
    # Full dataset bbox from the GeoParquet metadata (footer only) -> one COG read.
    geo = json.loads(pf.schema_arrow.metadata[b"geo"])
    minx, miny, maxx, maxy = geo["columns"][geo["primary_column"]]["bbox"]

    with rasterio.open(cog_path) as ds:
        nodata = ds.nodata if ds.nodata is not None else -1.0
        win = from_bounds(minx, miny, maxx, maxy, ds.transform)
        col_off = math.floor(win.col_off) - 1
        row_off = math.floor(win.row_off) - 1
        width = math.ceil(win.width) + 2
        height = math.ceil(win.height) + 2
        win = Window(col_off, row_off, width, height).intersection(
            Window(0, 0, ds.width, ds.height))
        array = ds.read(1, window=win)
        wtransform = ds.window_transform(win)

    out_schema = pf.schema_arrow.append(pa.field("confidence", pa.float32()))
    n_nonnull = 0
    writer = pq.ParquetWriter(out_path, out_schema)
    try:
        # Stream by row group so peak memory stays ~one batch, not the whole file.
        for batch in pf.iter_batches():
            xs, ys = representative_points(batch.column("geometry").to_pylist())
            conf = sample_points(xs, ys, array, wtransform, nodata)
            n_nonnull += sum(1 for c in conf if c is not None)
            cols = list(batch.columns) + [pa.array(conf, pa.float32())]
            writer.write_batch(pa.RecordBatch.from_arrays(cols, schema=out_schema))
    finally:
        writer.close()
    return n_nonnull


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("in_parquet")
    ap.add_argument("out_parquet")
    ap.add_argument("--cog", default=DEFAULT_COG, help="confidence COG path/URL")
    args = ap.parse_args(argv)
    n = enrich(args.in_parquet, args.cog, args.out_parquet)
    print(f"OK: wrote {args.out_parquet} ({n} non-null confidence values)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
