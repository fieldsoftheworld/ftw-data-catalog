#!/usr/bin/env python3
"""Re-lay-out final_partitions -> results_by_admin/admin:<CC>/...
- small/medium country (<=4GB): clean+merge pieces -> admin:CC/<CountryName>.parquet
- giant (>4GB): already subdivision-split -> clean each piece -> admin:CC/<CC>_<sub>.parquet
Cleans: drops __gpio_part* stray columns + org.apache.spark.* metadata; preserves
non-nullability, geo, collection. Usage: python rails_relayout.py [--move] [CC ...]
"""
import sys, os, glob, json
import pyarrow as pa, pyarrow.parquet as pq

WORK = "/u/cholmes/ftw-crs-fix"
SRC = f"{WORK}/final_partitions"
OUT = f"{WORK}/results_by_admin"
CAP = 4 * 1024**3
GB = 1024**3
DROP = ("__gpio_part", "__pk")

args = sys.argv[1:]
MOVE = "--move" in args
only = [a for a in args if not a.startswith("--")]
names = json.load(open(f"{WORK}/country_names.json"))

def clean_schema(path):
    s = pq.ParquetFile(path).schema_arrow
    keep = [n for n in s.names if not n.startswith(DROP)]
    md = {k: v for k, v in (s.metadata or {}).items() if not k.startswith(b"org.apache.spark")}
    return pa.schema([s.field(n) for n in keep], metadata=md), keep

def union_geo_bbox(src_files, schema):
    """Schema whose GeoParquet `bbox` covers *all* the inputs, not just the first.

    clean_schema() reads one file, so a country merged from many batch pieces used to
    inherit piece[0]'s `geo` metadata verbatim — advertising that piece's extent for
    the whole country. 397 of 574 published partitions carry a wrong bbox because of
    this; ZZ advertises a couple of buildings on St Vincent for a global file, which
    is what makes the Portolan browser zoom to nowhere. The union is taken from each
    input's own `geo` bbox (footer-only, no data read).
    """
    md = dict(schema.metadata or {})
    if b"geo" not in md:
        return schema
    geo = json.loads(md[b"geo"])
    prim = geo.get("primary_column")
    if not prim or prim not in geo.get("columns", {}):
        return schema
    box = None
    for p in src_files:
        fmd = pq.ParquetFile(p).metadata.metadata or {}
        if b"geo" not in fmd:
            continue
        b = json.loads(fmd[b"geo"])["columns"].get(prim, {}).get("bbox")
        if not b or len(b) != 4:
            continue
        box = b[:] if box is None else [min(box[0], b[0]), min(box[1], b[1]),
                                        max(box[2], b[2]), max(box[3], b[3])]
    if box is None:
        return schema
    geo["columns"][prim]["bbox"] = box
    md[b"geo"] = json.dumps(geo).encode()
    return schema.with_metadata(md)

def clean_write(src_files, out_path, schema, keep):
    schema = union_geo_bbox(src_files, schema)
    w = pq.ParquetWriter(out_path, schema, compression="zstd", compression_level=9)
    rows = 0
    for p in src_files:
        pf = pq.ParquetFile(p)
        for rg in range(pf.num_row_groups):
            t = pf.read_row_group(rg, columns=keep).replace_schema_metadata(schema.metadata)
            w.write_table(t); rows += t.num_rows
    w.close()
    return rows

codes = only or sorted(names)
for cc in codes:
    pieces = sorted(glob.glob(f"{SRC}/{cc}.parquet") + glob.glob(f"{SRC}/{cc}_*.parquet"))
    if not pieces:
        print(f"{cc}: NO PIECES"); continue
    size = sum(os.path.getsize(p) for p in pieces)
    d = f"{OUT}/admin:{cc}"
    if os.path.exists(f"{d}/.done"):
        print(f"{cc}: already done"); continue
    os.makedirs(d, exist_ok=True)
    # clear any partial output from a prior interrupted run
    for old in glob.glob(f"{d}/*.parquet"):
        os.remove(old)
    sch, keep = clean_schema(pieces[0])
    if size > CAP:  # giant: clean each subdivision piece, keep its name
        tot = 0
        for p in pieces:
            tot += clean_write([p], f"{d}/{os.path.basename(p)}", sch, keep)
        print(f"{cc} {names[cc]}: GIANT {size/GB:.1f}GB -> {len(pieces)} cleaned subdivision files, rows={tot}")
    else:  # merge to one named file
        out = f"{d}/{names[cc]}.parquet"
        rows = clean_write(pieces, out, sch, keep)
        print(f"{cc} {names[cc]}: {size/GB:.2f}GB {len(pieces)} pieces -> {names[cc]}.parquet rows={rows}")
    open(f"{d}/.done", "w").close()
    if MOVE:
        for p in pieces:
            os.remove(p)
print("RELAYOUT_DONE")
