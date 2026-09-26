#!/usr/bin/env python3
"""Add pct_covered (100 * sum_area / a5 cell area) to an a5 cells file.

a5 is an equal-area grid, so the denominator is one constant per resolution.
We self-calibrate it by measuring a sample of cells geodesically with pyproj
(r7 = 2,075.5 km², spread <0.1%). DuckDB's ST_Area_Spheroid is NOT usable
here: it returns NaN for 38% of the cell polygons and areas off by up to
100x on the rest (duckdb-spatial bug, observed 2026-09-26 v1.1.x).

Output is plain parquet (DuckDB drops the GeoParquet 'geo' key); run
`gpio convert geoparquet ... --geoparquet-version 2.0` on it afterwards.
"""
import statistics
import sys

import duckdb
from pyproj import Geod
from shapely import wkb
from shapely.affinity import translate
from shapely.geometry import box
from shapely.ops import unary_union

WORLD = box(-180.0, -90.0, 180.0, 90.0)


def wrap_antimeridian(g: bytes) -> bytes:
    """a5 cells touching the dateline have vertices past +/-180 (up to ~0.6
    degrees over), which tile exporters drop as outside the CRS range. Split
    them into a MultiPolygon with the overflow wrapped to the other side."""
    geom = wkb.loads(bytes(g))
    minx, _, maxx, _ = geom.bounds
    if minx >= -180.0 and maxx <= 180.0:
        return bytes(g)
    parts = [geom.intersection(WORLD),
             translate(geom, xoff=360.0).intersection(WORLD),
             translate(geom, xoff=-360.0).intersection(WORLD)]
    return unary_union([p for p in parts if not p.is_empty]).wkb

src, dst = sys.argv[1], sys.argv[2]
con = duckdb.connect()
con.execute("INSTALL spatial; LOAD spatial;")
con.execute("SET memory_limit='48GB'; SET preserve_insertion_order=false;")

geod = Geod(ellps="WGS84")
sample = con.execute(
    f"SELECT ST_AsWKB(geometry) FROM '{src}' USING SAMPLE 200").fetchall()
areas = [abs(geod.geometry_area_perimeter(wkb.loads(bytes(g)))[0])
         for (g,) in sample]
cell_area = statistics.median(areas)
spread = (max(areas) - min(areas)) / cell_area * 100
print(f"cell area: {cell_area / 1e6:,.1f} km2 (sample spread {spread:.2f}%)",
      flush=True)
if spread > 2:
    raise SystemExit("cell areas not constant — is this really an a5 grid?")

# Rounded output (area to whole hectares, 1dp elsewhere): full-double
# attributes nearly double tile weights — rounding is what gets the worst
# z2 tile from 874 KB to 543 KB, under the 600 KB budget. 1 ha / 0.1
# precision is far beyond the data's real accuracy anyway.
con.create_function("wrap_am", wrap_antimeridian,
                    [duckdb.typing.BLOB], duckdb.typing.BLOB)
con.execute(f"""
    COPY (
      SELECT a5_cell, count,
             CAST(round(sum_area / 1e4) AS BIGINT)          AS area_ha,
             round(avg_confidence, 1)                       AS avg_confidence,
             round(100 * sum_area / {cell_area!r}, 1)       AS pct_covered,
             ST_GeomFromWKB(wrap_am(ST_AsWKB(geometry)))    AS geometry
      FROM '{src}'
    ) TO '{dst}' (FORMAT PARQUET, COMPRESSION zstd, ROW_GROUP_SIZE 65536)
""")
n = con.execute(f"SELECT count(*) FROM '{dst}'").fetchone()[0]
print(f"{dst}: {n:,} cells", flush=True)
