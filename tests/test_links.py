"""Verify every relative href in catalog/collection/item JSON resolves to a file.

One documented exemption: the features MGRS browse tree. The ~45k per-tile items and
the 700 grid catalogs per year are generated straight to S3 by
scripts/features/build_features_items.py (too many to commit; see that script's README),
so the per-year collections carry relative `child` links — relative is a Portolan MUST,
PTL-LNK-004 — to zone catalogs that exist only in the published catalog. Those specific
links are counted and reported rather than resolved.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "catalog"

# catalog/features/<year>/collection.json -> ./<utm zone>/catalog.json (generated to S3)
GENERATED_TREE = (re.compile(r"^features/(2024|2025)/collection\.json$"),
                  re.compile(r"^\./[0-6][0-9]/catalog\.json$"))

def stac_json_files():
    for name in ("catalog.json",):
        p = ROOT / name
        if p.exists():
            yield p
    yield from ROOT.glob("**/collection.json")
    yield from ROOT.glob("**/*/*.json")  # item jsons live in item subdirs

def check():
    errors = []
    seen = set()
    generated = 0
    for jf in stac_json_files():
        if jf in seen:
            continue
        seen.add(jf)
        try:
            doc = json.loads(jf.read_text())
        except json.JSONDecodeError as e:
            errors.append(f"{jf}: invalid JSON: {e}")
            continue
        for link in doc.get("links", []):
            href = link.get("href", "")
            if href.startswith("http") or href.startswith("#"):
                continue
            rel_path = jf.relative_to(ROOT).as_posix()
            if GENERATED_TREE[0].match(rel_path) and GENERATED_TREE[1].match(href):
                generated += 1
                continue
            target = (jf.parent / href).resolve()
            if not target.exists():
                errors.append(f"{jf}: link rel={link.get('rel')} -> missing {href}")
    if errors:
        print("\n".join(errors)); sys.exit(1)
    print(f"OK: {len(seen)} STAC files, all relative links resolve "
          f"({generated} links into the S3-only features grid exempted)")

if __name__ == "__main__":
    check()
