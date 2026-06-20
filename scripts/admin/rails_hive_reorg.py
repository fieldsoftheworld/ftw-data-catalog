#!/usr/bin/env python3
"""Reorganize results_by_admin/admin:<CC>/* (flat) into proper Hive:
  small:  admin:country_code=<CC>/<CountryName>.parquet
  giant:  admin:country_code=<CC>/admin:subdivision_code=<sub>/<CountryName>.parquet
All cheap os.rename (no data rewrite). Idempotent-ish: skips already-hive dirs.
"""
import os, glob, json, re, shutil

WORK = "/u/cholmes/ftw-crs-fix"
OUT = f"{WORK}/results_by_admin"
names = json.load(open(f"{WORK}/country_names.json"))

src_dirs = [d for d in glob.glob(f"{OUT}/admin:*")
            if os.path.isdir(d) and re.fullmatch(r"admin:[A-Z]{2}", os.path.basename(d))]
print(f"reorganizing {len(src_dirs)} country dirs")

moved_flat = moved_nested = 0
for d in sorted(src_dirs):
    cc = os.path.basename(d).split("admin:")[-1]
    name = names.get(cc, cc)
    for f in glob.glob(f"{d}/*.parquet"):
        base = os.path.basename(f)[:-len(".parquet")]
        if base.startswith(cc + "_"):                       # giant subdivision file CC_<sub>
            sub = base[len(cc) + 1:]
            dst = f"{OUT}/admin:country_code={cc}/admin:subdivision_code={sub}"
            os.makedirs(dst, exist_ok=True)
            os.rename(f, f"{dst}/{name}.parquet"); moved_nested += 1
        else:                                               # small country, single file
            dst = f"{OUT}/admin:country_code={cc}"
            os.makedirs(dst, exist_ok=True)
            os.rename(f, f"{dst}/{name}.parquet"); moved_flat += 1
    # drop the now-empty old dir (and its .done marker)
    shutil.rmtree(d, ignore_errors=True)

print(f"moved_flat(small)={moved_flat} moved_nested(giant-subdiv)={moved_nested}")
print(f"country_code dirs now: {len(glob.glob(f'{OUT}/admin:country_code=*'))}")
print("HIVE_REORG_DONE")
