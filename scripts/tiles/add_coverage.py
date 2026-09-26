#!/usr/bin/env python3
"""Add pct_covered (100 * sum_area / spheroid cell area) to an a5 cells file.

Output is plain parquet (DuckDB drops the GeoParquet 'geo' key); run
`gpio convert geoparquet ... --geoparquet-version 2.0` on it afterwards.
"""
import sys

import duckdb

src, dst = sys.argv[1], sys.argv[2]
con = duckdb.connect()
con.execute("INSTALL spatial; LOAD spatial;")
con.execute("SET memory_limit='48GB'; SET preserve_insertion_order=false;")
con.execute(f"""
    COPY (
      SELECT *,
             round(100 * sum_area / ST_Area_Spheroid(geometry), 2) AS pct_covered
      FROM '{src}'
    ) TO '{dst}' (FORMAT PARQUET, COMPRESSION zstd, ROW_GROUP_SIZE 65536)
""")
n = con.execute(f"SELECT count(*) FROM '{dst}'").fetchone()[0]
print(f"{dst}: {n:,} cells", flush=True)
