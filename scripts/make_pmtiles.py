#!/usr/bin/env python3
"""Build PMTiles from a GeoParquet: duckdb (spatial) -> GeoJSONSeq -> tippecanoe.

Used instead of `gpio pmtiles create` because gpio's streaming geometry path
crashes on large inputs inside geoarrow-c (`GeoArrowKernel<as_geoarrow>::
push_batch() failed`). duckdb + tippecanoe handle the full FTW country files.

Keeps only the attributes needed for styling (confidence, metrics:area) plus the
geometry. Emits one layer per prediction year (e.g. `2024`, `2025`), split by the
year of `determination:datetime` (in UTC). Source CRS is OGC:CRS84 / EPSG:4326
(lon-lat), so no reprojection. Falls back to a single `--layer` if no usable
determination dates are present.

Usage:
    python3 make_pmtiles.py IN.parquet OUT.pmtiles [--layer fields]
                            [--cols confidence,metrics:area] [--tmpdir DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

# Bound duckdb so concurrent workers don't collectively OOM the node.
DUCKDB_MEM = os.environ.get("DUCKDB_MEM", "24GB")
DUCKDB_THREADS = os.environ.get("DUCKDB_THREADS", "8")


def build(in_parquet: str, out_pmtiles: str, layer: str = "fields",
          cols=("confidence", "metrics:area"), tmpdir: str | None = None,
          year_col: str = "determination:datetime") -> None:
    import duckdb

    d = tmpdir or os.path.dirname(os.path.abspath(out_pmtiles)) or "."
    os.makedirs(d, exist_ok=True)
    base = os.path.basename(out_pmtiles)
    sel = ", ".join(f'"{c}"' for c in cols)

    con = duckdb.connect()
    # Bound memory so N concurrent workers don't each grab ~80% of RAM (OOM).
    # Spill to the scratch tmpdir rather than RAM. Years resolved in UTC.
    con.execute(f"SET temp_directory='{d}'")
    con.execute(f"SET memory_limit='{DUCKDB_MEM}'")
    con.execute(f"SET threads={DUCKDB_THREADS}")
    con.execute("SET TimeZone='UTC'")
    con.execute("INSTALL spatial; LOAD spatial;")

    years = [r[0] for r in con.execute(
        f'SELECT DISTINCT EXTRACT(year FROM "{year_col}")::INT AS y '
        f"FROM read_parquet('{in_parquet}') WHERE \"{year_col}\" IS NOT NULL "
        "ORDER BY y").fetchall()]

    written, layer_args = [], []
    if years:
        # one GeoJSONSeq + tippecanoe layer per prediction year
        for y in years:
            gj = os.path.join(d, f"{base}.{y}.geojsonl")
            con.execute(
                f"COPY (SELECT {sel}, geometry FROM read_parquet('{in_parquet}') "
                f'WHERE EXTRACT(year FROM "{year_col}")={y}) '
                f"TO '{gj}' WITH (FORMAT GDAL, DRIVER 'GeoJSONSeq', SRS 'EPSG:4326')")
            written.append(gj)
            layer_args += ["-L", json.dumps({"file": gj, "layer": str(y)})]
    else:
        gj = os.path.join(d, f"{base}.geojsonl")
        con.execute(
            f"COPY (SELECT {sel}, geometry FROM read_parquet('{in_parquet}')) "
            f"TO '{gj}' WITH (FORMAT GDAL, DRIVER 'GeoJSONSeq', SRS 'EPSG:4326')")
        written.append(gj)
        layer_args += ["-L", json.dumps({"file": gj, "layer": layer})]
    con.close()

    try:
        # -z13 bounds work; --drop-densest-as-needed keeps tile sizes sane;
        # -L gives one named layer per year.
        subprocess.run(
            ["tippecanoe", "-o", out_pmtiles, "--force", "--quiet",
             "-z13", "--drop-densest-as-needed", *layer_args],
            check=True,
        )
    finally:
        for gj in written:
            if os.path.exists(gj):
                os.remove(gj)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("in_parquet")
    ap.add_argument("out_pmtiles")
    ap.add_argument("--layer", default="fields")
    ap.add_argument("--cols", default="confidence,metrics:area")
    ap.add_argument("--tmpdir", default=None)
    args = ap.parse_args(argv)
    build(args.in_parquet, args.out_pmtiles, args.layer,
          tuple(c for c in args.cols.split(",") if c), args.tmpdir)
    print(f"OK: wrote {args.out_pmtiles}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
