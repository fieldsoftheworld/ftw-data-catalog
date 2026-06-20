import glob, os, json
import pyarrow.parquet as pq

OUT = "/u/cholmes/ftw-crs-fix/results_by_admin"
files = glob.glob(f"{OUT}/**/*.parquet", recursive=True)
print("total files:", len(files))
print("country dirs:", len(glob.glob(f"{OUT}/admin:country_code=*")))
nested = [f for f in files if "admin:subdivision_code=" in f]
print("flat (small):", len(files) - len(nested), "| nested (giant subdiv):", len(nested))

total_rows = 0
bad = []
total_bytes = 0
for f in files:
    total_bytes += os.path.getsize(f)
    pf = pq.ParquetFile(f); md = pf.schema_arrow.metadata or {}
    sch = pf.schema_arrow
    total_rows += pf.metadata.num_rows
    stray = [n for n in sch.names if n.startswith("__")]
    coll = b"collection" in md
    crs_absent = "crs" not in json.loads(md[b"geo"])["columns"]["geometry"] if b"geo" in md else False
    nn = all(not sch.field(c).nullable for c in ["id", "geometry", "admin:country_code"])
    spark = any(k.startswith(b"org.apache.spark") for k in md)
    if stray or not coll or not crs_absent or not nn or spark:
        bad.append((os.path.relpath(f, OUT), stray, coll, crs_absent, nn, spark))

print(f"total_rows: {total_rows:,}  (expected 3,206,414,367, match={total_rows==3206414367})")
print(f"total_size: {total_bytes/1024**3:.1f} GB")
print(f"files failing checks: {len(bad)}")
for b in bad[:10]:
    print("  BAD:", b)
