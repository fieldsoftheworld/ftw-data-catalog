import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
doc = json.loads((ROOT / "catalog.json").read_text())

errs = []
if doc.get("git:repository") != "https://github.com/fieldsoftheworld/ftw-portolan":
    errs.append("git:repository missing/wrong")
if doc.get("git:ref") != "main":
    errs.append("git:ref missing/wrong")
if doc.get("git:provider") != "github":
    errs.append("git:provider missing/wrong")
rels = {l.get("rel"): l.get("href") for l in doc.get("links", [])}
if rels.get("vcs") != "https://github.com/fieldsoftheworld/ftw-portolan":
    errs.append("vcs link missing/wrong")
if rels.get("issues") != "https://github.com/fieldsoftheworld/ftw-portolan/issues":
    errs.append("issues link missing/wrong")
if errs:
    print("\n".join(errs)); sys.exit(1)
print("OK: git extension fields present")
