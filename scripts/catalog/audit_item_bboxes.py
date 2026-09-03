#!/usr/bin/env python3
"""Audit the item bboxes of the vector partitions against the real data extent.

`build_vector_items.py` takes each item's bbox from the parquet's GeoParquet `geo`
metadata. When a writer records a wrong bbox there (e.g. one feature's extent rather
than the file's), the STAC item inherits it and the browser zooms to a few metres of
nowhere — the symptom that turned up on the ZZ partition, which advertises
`[-61.117, 13.2945, -61.1165, 13.2979]` (a couple of buildings on St Vincent) for a
46 M-polygon global file.

Ground truth here is the `bbox` struct column's own Parquet statistics, min/max'd
across row groups. Both that and the `geo` metadata live in the footer, so this reads
only a few KB per partition and never touches the data.

Usage:
    python3 audit_item_bboxes.py                 # every partition on S3
    python3 audit_item_bboxes.py --tolerance 0.01
    python3 audit_item_bboxes.py --json out.json
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor

S3BASE = ("us-west-2.opendata.source.coop/tge-labs/ftw-global-data/"
          "predictions/vectors/alpha/results-by-admin-conf")


def _fs():
    from pyarrow import fs as pafs
    return pafs.S3FileSystem(region="us-west-2", anonymous=True)


def stats_bbox(pf):
    """True extent from the `bbox` struct column statistics, or None."""
    md = pf.metadata
    paths = [md.schema.column(i).path for i in range(md.num_columns)]
    want = {f"bbox.{k}": None for k in ("xmin", "ymin", "xmax", "ymax")}
    idx = {p: i for i, p in enumerate(paths) if p in want}
    if len(idx) != 4:
        return None
    lo = {"bbox.xmin": None, "bbox.ymin": None}
    hi = {"bbox.xmax": None, "bbox.ymax": None}
    for rg in range(md.num_row_groups):
        for p, i in idx.items():
            st = md.row_group(rg).column(i).statistics
            if st is None or not st.has_min_max:
                continue
            if p in lo:
                lo[p] = st.min if lo[p] is None else min(lo[p], st.min)
            else:
                hi[p] = st.max if hi[p] is None else max(hi[p], st.max)
    if any(v is None for v in (*lo.values(), *hi.values())):
        return None
    return [lo["bbox.xmin"], lo["bbox.ymin"], hi["bbox.xmax"], hi["bbox.ymax"]]


def geo_bbox(pf):
    md = pf.metadata.metadata or {}
    if b"geo" not in md:
        return None
    geo = json.loads(md[b"geo"])
    col = geo["columns"][geo["primary_column"]]
    return col.get("bbox")


def check(key):
    import pyarrow.parquet as pq
    fs = _fs()
    try:
        with fs.open_input_file(f"{S3BASE}/{key}") as f:
            pf = pq.ParquetFile(f)
            return {"key": key, "rows": pf.metadata.num_rows,
                    "geo": geo_bbox(pf), "true": stats_bbox(pf)}
    except Exception as e:  # noqa: BLE001 - report, don't abort the sweep
        return {"key": key, "error": f"{type(e).__name__}: {e}"}


def area(b):
    return abs(b[2] - b[0]) * abs(b[3] - b[1])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tolerance", type=float, default=0.001,
                    help="degrees of slack before a corner counts as wrong")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--json", help="write full results here")
    a = ap.parse_args()

    fs = _fs()
    from pyarrow import fs as pafs
    keys = [f.path.split(f"{S3BASE}/", 1)[1]
            for f in fs.get_file_info(pafs.FileSelector(S3BASE, recursive=True))
            if f.path.endswith(".parquet")]
    print(f"auditing {len(keys)} partitions\n")

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        results = list(ex.map(check, sorted(keys)))

    bad, missing, errs = [], [], []
    for r in results:
        if "error" in r:
            errs.append(r); continue
        if r["geo"] is None:
            missing.append(r); continue
        if r["true"] is None:
            continue
        if any(abs(g - t) > a.tolerance for g, t in zip(r["geo"], r["true"])):
            r["shrink"] = (area(r["true"]) / area(r["geo"])) if area(r["geo"]) else float("inf")
            bad.append(r)

    if bad:
        print(f"{len(bad)} partition(s) whose advertised bbox does not match the data:\n")
        print(f"{'partition':<52}{'rows':>12}  advertised -> true")
        for r in sorted(bad, key=lambda r: -r["shrink"]):
            g, t = r["geo"], r["true"]
            print(f"  {r['key']:<50}{r['rows']:>12,}")
            print(f"      geo : [{g[0]:.4f}, {g[1]:.4f}, {g[2]:.4f}, {g[3]:.4f}]"
                  f"  (area {area(g):.6g})")
            print(f"      true: [{t[0]:.4f}, {t[1]:.4f}, {t[2]:.4f}, {t[3]:.4f}]"
                  f"  (area {area(t):.6g})  x{r['shrink']:.3g}")
    else:
        print("all advertised bboxes match the data")

    if missing:
        print(f"\n{len(missing)} partition(s) with no bbox in `geo` metadata:")
        for r in missing:
            print(f"  {r['key']}")
    if errs:
        print(f"\n{len(errs)} unreadable:")
        for r in errs:
            print(f"  {r['key']}: {r['error']}")

    print(f"\n{len(results) - len(bad) - len(missing) - len(errs)} of {len(results)} OK")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(results, f, indent=2)
        print(f"wrote {a.json}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
