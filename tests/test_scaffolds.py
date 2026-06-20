import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "staging"
CATALOG = ROOT / "catalog"
# Remaining scaffolds (predictions/vectors has been promoted into catalog/).
EXPECTED = {
    "predictions/zarr": "predictions-zarr",
    "features/cogs": "features-cogs",
    "features/zarr": "features-zarr",
}
errs = []
for path, cid in EXPECTED.items():
    cj = STAGING / path / "collection.json"
    if not cj.exists():
        errs.append(f"missing {cj}"); continue
    doc = json.loads(cj.read_text())
    if doc.get("type") != "Collection":
        errs.append(f"{cj}: type != Collection")
    if doc.get("id") != cid:
        errs.append(f"{cj}: id {doc.get('id')} != {cid}")
    if doc.get("license") != "CC-BY-4.0":
        errs.append(f"{cj}: license != CC-BY-4.0")
    if "extent" not in doc:
        errs.append(f"{cj}: no extent")

cat = json.loads((CATALOG / "catalog.json").read_text())
children = {l["href"] for l in cat.get("links", []) if l.get("rel") == "child"}
for path in EXPECTED:
    href = f"./{path}/collection.json"
    if href in children:
        errs.append(f"catalog.json still links staged collection {href}")
if errs:
    print("\n".join(errs)); sys.exit(1)
print("OK: 3 scaffold collections staged and unlinked from published catalog")
