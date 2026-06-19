# FTW Git-Backed Portolan Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `ftw-portolan`, a git repo that is the source of truth for FTW Global STAC/Portolan metadata, with a metadata-only publisher to Source Cooperative.

**Architecture:** Data-as-code. Git holds all metadata; data stays on Source Cooperative and is never uploaded. A manifest (`catalog.publish.yaml`) drives a Python publisher that uploads only metadata files for enabled collections. The `confidence` collection is migrated working; four more are scaffolded. The `git:*` STAC extension fields (portolan-cli#485) are hand-added.

**Tech Stack:** STAC 1.1.0 / Portolan, Python 3 (stdlib only), AWS CLI, git.

## Global Constraints

- Write target (S3): `s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data` — region `us-west-2`.
- Public href base: `https://data.source.coop/ftw/global-data` — used in ALL STAC hrefs.
- NEVER upload data files (`*.tif`, `*.parquet`, `*.zarr`); they live only on Source Cooperative.
- `scripts/`, `docs/`, `CLAUDE.md`, `catalog.publish.yaml`, `.portolan/config.yaml` are tracked in git but NEVER published to the catalog.
- Git extension owner: GitHub org `fieldsoftheworld`, repo `ftw-portolan`, ref `main`.
- Source repo to migrate from: `/Users/cholmes/repos/ftw-global-data-catalog` (the "old repo").
- New repo root: `/Users/cholmes/repos/ftw-portolan` (already `git init`'d; contains this plan + the design spec).
- STAC version: `1.1.0`. License: `CC-BY-4.0`.
- Publisher is `python3 scripts/publish.py` (dry-run by default; `--confirm` to upload). Note: this supersedes the spec's `publish_metadata.sh` name — Python is testable; the old bash scripts are migrated for reference.

## File Structure

- `catalog.json` — root STAC catalog + `git:*` fields + `vcs`/`issues` links + `child` links to all 5 collections.
- `versions.json`, `llms.txt`, `.portolan/` — migrated as-is.
- `catalog.publish.yaml` — publish manifest (write_prefix, public_base, region, root_files, publish_globs, enabled collections).
- `scripts/publish.py` — manifest-driven metadata-only publisher (logic + CLI).
- `scripts/build_items.py`, `scripts/make_llms.py`, `scripts/make_thumbnails.py`, `scripts/publish_metadata.sh`, `scripts/restructure_s3.sh` — migrated helper scripts.
- `tests/test_publish.py` — dependency-free unit test for the publisher's file-selection logic.
- `predictions/confidence/` — migrated working collection (5 COG items).
- `predictions/vectors/`, `predictions/zarr/`, `features/cogs/`, `features/zarr/` — scaffold `collection.json` + `.portolan/metadata.yaml`.
- `README.md` — public catalog README (about the dataset; published). `CLAUDE.md` — developer guide (not published).

---

### Task 1: Migrate the working confidence collection into the new repo

**Files:**
- Create (copy from old repo): `catalog.json`, `versions.json`, `llms.txt`, `.portolan/config.yaml`, `.portolan/metadata.yaml`, `predictions/confidence/**`
- Create: `scripts/` (move helper scripts in)
- Already present: `.gitignore`

**Interfaces:**
- Produces: a valid STAC tree rooted at `catalog.json` whose relative `child`/item hrefs all resolve to existing files. Later tasks edit `catalog.json` and add sibling collections.

- [ ] **Step 1: Copy metadata + confidence tree from the old repo**

```bash
cd /Users/cholmes/repos/ftw-portolan
OLD=/Users/cholmes/repos/ftw-global-data-catalog
cp "$OLD/catalog.json" "$OLD/versions.json" "$OLD/llms.txt" .
mkdir -p .portolan
cp "$OLD/.portolan/config.yaml" "$OLD/.portolan/metadata.yaml" .portolan/
mkdir -p predictions
cp -R "$OLD/predictions/confidence" predictions/
# drop any stray data/OS files that may have been copied
find predictions -name '.DS_Store' -delete
```

- [ ] **Step 2: Move helper scripts into scripts/**

```bash
cd /Users/cholmes/repos/ftw-portolan
OLD=/Users/cholmes/repos/ftw-global-data-catalog
mkdir -p scripts
cp "$OLD/build_items.py" "$OLD/make_llms.py" "$OLD/make_thumbnails.py" \
   "$OLD/publish_metadata.sh" "$OLD/restructure_s3.sh" scripts/
```

- [ ] **Step 3: Write the link-resolution check (the test)**

Create `tests/test_links.py`:

```python
"""Verify every relative href in catalog/collection/item JSON resolves to a file."""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

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
            target = (jf.parent / href).resolve()
            if not target.exists():
                errors.append(f"{jf}: link rel={link.get('rel')} -> missing {href}")
    if errors:
        print("\n".join(errors)); sys.exit(1)
    print(f"OK: {len(seen)} STAC files, all relative links resolve")

if __name__ == "__main__":
    check()
```

- [ ] **Step 4: Run the check — expect PASS**

Run: `cd /Users/cholmes/repos/ftw-portolan && python3 tests/test_links.py`
Expected: `OK: N STAC files, all relative links resolve`. If a link fails, fix the copied file or path before continuing.

- [ ] **Step 5: Commit**

```bash
cd /Users/cholmes/repos/ftw-portolan
git add -A
git commit -m "Migrate confidence collection and helper scripts into ftw-portolan"
```

---

### Task 2: Add git:* extension fields and vcs/issues links to catalog.json

**Files:**
- Modify: `catalog.json`

**Interfaces:**
- Consumes: existing `catalog.json` `links` array from Task 1.
- Produces: `catalog.json` with top-level keys `git:repository`, `git:ref`, `git:provider` and two new links (`rel: vcs`, `rel: issues`). Task 4 appends `child` links to the same array.

- [ ] **Step 1: Write the git-fields assertion (the test)**

Create `tests/test_git_ext.py`:

```python
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
```

- [ ] **Step 2: Run the test — expect FAIL**

Run: `cd /Users/cholmes/repos/ftw-portolan && python3 tests/test_git_ext.py`
Expected: FAIL listing `git:repository missing/wrong` etc.

- [ ] **Step 3: Add the fields via a one-shot edit script**

Run:

```bash
cd /Users/cholmes/repos/ftw-portolan
python3 - <<'PY'
import json
from pathlib import Path
p = Path("catalog.json")
doc = json.loads(p.read_text())
# insert git:* fields after "description"
new = {}
for k, v in doc.items():
    new[k] = v
    if k == "description":
        new["git:repository"] = "https://github.com/fieldsoftheworld/ftw-portolan"
        new["git:ref"] = "main"
        new["git:provider"] = "github"
doc = new
links = doc.setdefault("links", [])
have = {l.get("rel") for l in links}
if "vcs" not in have:
    links.append({"rel": "vcs", "href": "https://github.com/fieldsoftheworld/ftw-portolan",
                  "title": "Source repository"})
if "issues" not in have:
    links.append({"rel": "issues", "href": "https://github.com/fieldsoftheworld/ftw-portolan/issues",
                  "title": "Issue tracker"})
p.write_text(json.dumps(doc, indent=2) + "\n")
print("updated catalog.json")
PY
```

- [ ] **Step 4: Run both tests — expect PASS**

Run: `cd /Users/cholmes/repos/ftw-portolan && python3 tests/test_git_ext.py && python3 tests/test_links.py`
Expected: `OK: git extension fields present` and `OK: ... all relative links resolve`.

- [ ] **Step 5: Commit**

```bash
cd /Users/cholmes/repos/ftw-portolan
git add catalog.json tests/test_git_ext.py
git commit -m "Add git:* extension fields and vcs/issues links (portolan-cli#485)"
```

---

### Task 3: Manifest-driven metadata-only publisher

**Files:**
- Create: `catalog.publish.yaml`
- Create: `scripts/publish.py`
- Test: `tests/test_publish.py`

**Interfaces:**
- Produces: `collect_uploads(manifest: dict, root: Path) -> list[Upload]` where `Upload` is a `dataclass` with fields `local: Path`, `s3_uri: str`, `content_type: str`. The CLI `python3 scripts/publish.py [--confirm]` calls it and runs `aws s3 cp` (dry-run unless `--confirm`).

- [ ] **Step 1: Write the manifest**

Create `catalog.publish.yaml`:

```yaml
# What publishes, and where. Data files are NEVER listed here.
write_prefix: s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data
public_base: https://data.source.coop/ftw/global-data
region: us-west-2

# Files published from the repo root (if present).
root_files:
  - catalog.json
  - llms.txt
  - README.md
  - .portolan/metadata.yaml

# Within each enabled collection dir, these glob patterns are published.
publish_globs:
  - "**/*.json"
  - "**/README.md"
  - "**/llms.txt"
  - "**/thumbnail.png"
  - "**/.portolan/metadata.yaml"

# Only collections listed here are published. Scaffolds stay local until added.
collections:
  - predictions/confidence
```

- [ ] **Step 2: Write the failing unit test**

Create `tests/test_publish.py`:

```python
"""Dependency-free test of publisher file selection. Run: python3 tests/test_publish.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from publish import collect_uploads  # noqa: E402

def build_tree(tmp: Path):
    (tmp / "catalog.json").write_text("{}")
    (tmp / "llms.txt").write_text("x")
    (tmp / "README.md").write_text("x")
    (tmp / ".portolan").mkdir()
    (tmp / ".portolan/metadata.yaml").write_text("x")
    (tmp / ".portolan/config.yaml").write_text("x")  # must NOT publish
    (tmp / "scripts").mkdir()
    (tmp / "scripts/foo.py").write_text("x")          # must NOT publish
    c = tmp / "predictions/confidence"
    (c / "confidence").mkdir(parents=True)
    (c / "collection.json").write_text("{}")
    (c / "README.md").write_text("x")
    (c / "thumbnail.png").write_text("x")
    (c / "confidence/confidence.json").write_text("{}")
    v = tmp / "predictions/vectors"                    # scaffold, NOT enabled
    v.mkdir(parents=True)
    (v / "collection.json").write_text("{}")

def main():
    import tempfile
    manifest = {
        "write_prefix": "s3://bucket/ftw-global-data",
        "public_base": "https://data.source.coop/ftw/global-data",
        "region": "us-west-2",
        "root_files": ["catalog.json", "llms.txt", "README.md", ".portolan/metadata.yaml"],
        "publish_globs": ["**/*.json", "**/README.md", "**/llms.txt",
                          "**/thumbnail.png", "**/.portolan/metadata.yaml"],
        "collections": ["predictions/confidence"],
    }
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        build_tree(tmp)
        uploads = collect_uploads(manifest, tmp)
        rels = {u.local.relative_to(tmp).as_posix() for u in uploads}

    expected = {
        "catalog.json", "llms.txt", "README.md", ".portolan/metadata.yaml",
        "predictions/confidence/collection.json",
        "predictions/confidence/README.md",
        "predictions/confidence/thumbnail.png",
        "predictions/confidence/confidence/confidence.json",
    }
    forbidden = {
        ".portolan/config.yaml", "scripts/foo.py",
        "predictions/vectors/collection.json",  # not enabled
    }
    assert expected <= rels, f"missing: {expected - rels}"
    assert not (forbidden & rels), f"leaked: {forbidden & rels}"

    by_rel = {u.local.relative_to(tmp).as_posix(): u for u in uploads}
    assert by_rel["catalog.json"].s3_uri == "s3://bucket/ftw-global-data/catalog.json"
    assert by_rel["catalog.json"].content_type == "application/json"
    assert by_rel["predictions/confidence/confidence/confidence.json"].content_type == "application/geo+json"
    assert by_rel["predictions/confidence/thumbnail.png"].content_type == "image/png"
    assert by_rel["predictions/confidence/README.md"].content_type.startswith("text/markdown")
    print("OK: publisher selects metadata, excludes scripts/config/scaffolds")

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the test — expect FAIL (ImportError)**

Run: `cd /Users/cholmes/repos/ftw-portolan && python3 tests/test_publish.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'publish'`.

- [ ] **Step 4: Implement the publisher**

Create `scripts/publish.py`:

```python
#!/usr/bin/env python3
"""Metadata-only publisher for the FTW Portolan catalog.

Reads catalog.publish.yaml and uploads ONLY catalog metadata (STAC JSON, README,
llms.txt, thumbnails, .portolan/metadata.yaml) for enabled collections to S3.
Never uploads data (*.tif/*.parquet/*.zarr), scripts/, or config.

Usage:
  python3 scripts/publish.py            # dry run (prints planned uploads)
  python3 scripts/publish.py --confirm  # execute aws s3 cp
"""
from __future__ import annotations
import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_CT_BY_NAME = {"catalog.json": "application/json", "collection.json": "application/json"}
_CT_BY_SUFFIX = {
    ".json": "application/geo+json",  # items; catalog/collection overridden by name
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/markdown; charset=utf-8",  # llms.txt
    ".png": "image/png",
    ".yaml": "text/yaml; charset=utf-8",
    ".yml": "text/yaml; charset=utf-8",
}


@dataclass(frozen=True)
class Upload:
    local: Path
    s3_uri: str
    content_type: str


def _content_type(p: Path) -> str:
    if p.name in _CT_BY_NAME:
        return _CT_BY_NAME[p.name]
    return _CT_BY_SUFFIX.get(p.suffix, "application/octet-stream")


def collect_uploads(manifest: dict, root: Path) -> list[Upload]:
    write_prefix = manifest["write_prefix"].rstrip("/")
    selected: dict[Path, None] = {}  # ordered dedupe

    for rel in manifest.get("root_files", []):
        p = root / rel
        if p.is_file():
            selected[p] = None

    for coll in manifest.get("collections", []):
        cdir = root / coll
        if not cdir.is_dir():
            continue
        for pattern in manifest.get("publish_globs", []):
            for p in cdir.glob(pattern):
                if p.is_file():
                    selected[p] = None

    uploads = []
    for p in selected:
        rel = p.relative_to(root).as_posix()
        uploads.append(Upload(local=p, s3_uri=f"{write_prefix}/{rel}",
                              content_type=_content_type(p)))
    return uploads


def _load_manifest(root: Path) -> dict:
    import json
    text = (root / "catalog.publish.yaml").read_text()
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except ModuleNotFoundError:
        pass
    # Minimal YAML fallback (flat scalars + simple "- item" lists) so the
    # publisher has zero third-party dependencies.
    data: dict = {}
    key = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("- "):
            item = line.lstrip()[2:].strip().strip('"')
            data.setdefault(key, []).append(item)
        elif ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            key = k.strip()
            v = v.strip()
            data[key] = json.loads(v) if v.startswith("[") else (v.strip('"') if v else [])
    return data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--confirm", action="store_true", help="execute uploads (default: dry run)")
    args = ap.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    manifest = _load_manifest(root)
    region = manifest.get("region", "us-west-2")
    uploads = collect_uploads(manifest, root)

    if not uploads:
        print("No files to publish (check enabled collections in catalog.publish.yaml).")
        return 0

    for u in uploads:
        if args.confirm:
            print(f"upload: {u.local.relative_to(root)} -> {u.s3_uri}")
            subprocess.run(
                ["aws", "s3", "cp", str(u.local), u.s3_uri,
                 "--region", region, "--content-type", u.content_type],
                check=True,
            )
        else:
            print(f"DRYRUN {u.s3_uri}  ({u.content_type})")
    if not args.confirm:
        print(f"\n{len(uploads)} files. Re-run with --confirm to upload.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the unit test — expect PASS**

Run: `cd /Users/cholmes/repos/ftw-portolan && python3 tests/test_publish.py`
Expected: `OK: publisher selects metadata, excludes scripts/config/scaffolds`.

- [ ] **Step 6: Smoke-test the real dry run — expect confidence files, no scripts/data**

Run: `cd /Users/cholmes/repos/ftw-portolan && python3 scripts/publish.py`
Expected: lines for `catalog.json`, `predictions/confidence/collection.json`, the 5 item JSONs, README/llms.txt/thumbnails; NO `scripts/`, NO `*.tif`, NO `predictions/vectors`. Ends with "Re-run with --confirm to upload."

- [ ] **Step 7: Commit**

```bash
cd /Users/cholmes/repos/ftw-portolan
git add catalog.publish.yaml scripts/publish.py tests/test_publish.py
git commit -m "Add manifest-driven metadata-only publisher with unit test"
```

---

### Task 4: Scaffold the four remaining collections and link them from the root

**Files:**
- Create: `predictions/vectors/collection.json`, `predictions/vectors/.portolan/metadata.yaml`
- Create: `predictions/zarr/collection.json`, `predictions/zarr/.portolan/metadata.yaml`
- Create: `features/cogs/collection.json`, `features/cogs/.portolan/metadata.yaml`
- Create: `features/zarr/collection.json`, `features/zarr/.portolan/metadata.yaml`
- Modify: `catalog.json` (add four `child` links)

**Interfaces:**
- Consumes: `catalog.json` from Task 2.
- Produces: four valid STAC Collections with global extent and at least one asset href under the public base; four new `child` links in `catalog.json`. These collections are NOT added to `catalog.publish.yaml` (stay local until fleshed out).

- [ ] **Step 1: Write the scaffold-existence test**

Create `tests/test_scaffolds.py`:

```python
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "predictions/vectors": "vectors",
    "predictions/zarr": "predictions-zarr",
    "features/cogs": "features-cogs",
    "features/zarr": "features-zarr",
}
errs = []
for path, cid in EXPECTED.items():
    cj = ROOT / path / "collection.json"
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

cat = json.loads((ROOT / "catalog.json").read_text())
children = {l["href"] for l in cat.get("links", []) if l.get("rel") == "child"}
for path in EXPECTED:
    href = f"./{path}/collection.json"
    if href not in children:
        errs.append(f"catalog.json missing child link {href}")
if errs:
    print("\n".join(errs)); sys.exit(1)
print("OK: 4 scaffold collections present and linked")
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `cd /Users/cholmes/repos/ftw-portolan && python3 tests/test_scaffolds.py`
Expected: FAIL listing missing collection.json files.

- [ ] **Step 3: Generate the four scaffolds**

Run:

```bash
cd /Users/cholmes/repos/ftw-portolan
python3 - <<'PY'
import json
from pathlib import Path

BASE = "https://data.source.coop/ftw/global-data"
EXTENT = {
    "spatial": {"bbox": [[-180.0, -60.0, 180.0, 84.0]]},
    "temporal": {"interval": [["2024-01-01T00:00:00Z", "2025-12-31T23:59:59Z"]]},
}
PROVIDERS = [
    {"name": "Taylor Geospatial Institute", "roles": ["producer", "licensor"],
     "url": "https://taylorgeospatial.org/"},
    {"name": "Microsoft AI for Good Research Lab", "roles": ["producer", "processor"],
     "url": "https://www.microsoft.com/en-us/research/group/ai-for-good-research-lab/"},
]
COG_T = "image/tiff; application=geotiff; profile=cloud-optimized"
ZARR_T = "application/vnd+zarr"
PARQUET_T = "application/vnd.apache.parquet"
PMTILES_T = "application/vnd.pmtiles"

SCAFFOLDS = {
    "predictions/vectors": dict(
        id="vectors",
        title="FTW Global — Field Boundary Predictions (vector)",
        description=("Global agricultural field-boundary polygons predicted by the PRUE model "
                     "(~8.2 billion polygons), as cloud-native GeoParquet, with a derived PMTiles "
                     "layer for web visualization. SCAFFOLD: metadata pending."),
        assets={
            "data": {"href": f"{BASE}/predictions/vectors/alpha/results/",
                     "type": PARQUET_T, "title": "Field-boundary polygons (GeoParquet)",
                     "roles": ["data"]},
            "pmtiles": {"href": f"{BASE}/predictions/vectors/alpha/global.pmtiles",
                        "type": PMTILES_T, "title": "Field boundaries (PMTiles)",
                        "roles": ["visual"]},
        },
    ),
    "predictions/zarr": dict(
        id="predictions-zarr",
        title="FTW Global — Predictions (Zarr)",
        description=("PRUE model output probabilities (non_field_background, field, field_boundaries) "
                     "on the global grid as a Zarr store. SCAFFOLD: metadata pending."),
        assets={
            "data": {"href": f"{BASE}/predictions/zarr/alpha/global.zarr",
                     "type": ZARR_T, "title": "Prediction probabilities (Zarr)",
                     "roles": ["data"]},
        },
    ),
    "features/cogs": dict(
        id="features-cogs",
        title="FTW Global — Sentinel-2 Feature Composites (COG)",
        description=("Median Sentinel-2 planting and harvest composites (B02, B03, B04, B08, "
                     "N_VALID_PIXELS) as Cloud-Optimized GeoTIFFs, with a Parquet discovery index. "
                     "SCAFFOLD: metadata pending."),
        assets={
            "index": {"href": f"{BASE}/features/cogs/alpha/index.parquet",
                      "type": PARQUET_T, "title": "COG discovery index", "roles": ["metadata"]},
        },
    ),
    "features/zarr": dict(
        id="features-zarr",
        title="FTW Global — Sentinel-2 Feature Mosaic (Zarr)",
        description=("Unified global Sentinel-2 feature mosaic (time, band, y, x) reprojected to "
                     "EPSG:4326 at ~10 m as a Zarr store. SCAFFOLD: metadata pending."),
        assets={
            "data": {"href": f"{BASE}/features/zarr/alpha/global.zarr",
                     "type": ZARR_T, "title": "Feature mosaic (Zarr)", "roles": ["data"]},
        },
    ),
}

for path, s in SCAFFOLDS.items():
    d = Path(path)
    (d / ".portolan").mkdir(parents=True, exist_ok=True)
    coll = {
        "type": "Collection",
        "stac_version": "1.1.0",
        "id": s["id"],
        "title": s["title"],
        "description": s["description"],
        "license": "CC-BY-4.0",
        "keywords": ["agriculture", "field boundaries", "Fields of the World", "FTW", "global"],
        "providers": PROVIDERS,
        "extent": EXTENT,
        "assets": s["assets"],
        "links": [
            {"rel": "root", "href": "../../catalog.json", "type": "application/json",
             "title": "Fields of the World — Global"},
            {"rel": "parent", "href": "../../catalog.json", "type": "application/json"},
            {"rel": "self",
             "href": f"{BASE}/{path}/collection.json", "type": "application/json"},
        ],
    }
    (d / "collection.json").write_text(json.dumps(coll, indent=2) + "\n")
    (d / ".portolan/metadata.yaml").write_text(
        "contact:\n  name: \"\"\n  email: \"\"\nlicense: \"CC-BY-4.0\"\n"
        "license_url: \"https://creativecommons.org/licenses/by/4.0/\"\n")
    print("wrote", path)
PY
```

- [ ] **Step 4: Add the four child links to catalog.json**

Run:

```bash
cd /Users/cholmes/repos/ftw-portolan
python3 - <<'PY'
import json
from pathlib import Path
p = Path("catalog.json")
doc = json.loads(p.read_text())
links = doc.setdefault("links", [])
existing = {(l.get("rel"), l.get("href")) for l in links}
children = [
    ("./predictions/vectors/collection.json", "FTW Global — Field Boundary Predictions (vector)"),
    ("./predictions/zarr/collection.json", "FTW Global — Predictions (Zarr)"),
    ("./features/cogs/collection.json", "FTW Global — Sentinel-2 Feature Composites (COG)"),
    ("./features/zarr/collection.json", "FTW Global — Sentinel-2 Feature Mosaic (Zarr)"),
]
for href, title in children:
    if ("child", href) not in existing:
        links.append({"rel": "child", "href": href, "type": "application/json", "title": title})
p.write_text(json.dumps(doc, indent=2) + "\n")
print("added child links")
PY
```

- [ ] **Step 5: Run scaffolds + links + git tests — expect PASS**

Run: `cd /Users/cholmes/repos/ftw-portolan && python3 tests/test_scaffolds.py && python3 tests/test_links.py && python3 tests/test_git_ext.py`
Expected: all three print `OK: ...`.

- [ ] **Step 6: Verify scaffolds do NOT publish (still only confidence)**

Run: `cd /Users/cholmes/repos/ftw-portolan && python3 scripts/publish.py | grep -E 'vectors|features/|predictions/zarr' || echo "GOOD: no scaffolds in publish set"`
Expected: `GOOD: no scaffolds in publish set`.

- [ ] **Step 7: Commit**

```bash
cd /Users/cholmes/repos/ftw-portolan
git add predictions/vectors predictions/zarr features catalog.json tests/test_scaffolds.py
git commit -m "Scaffold vectors/zarr/features collections and link from root catalog"
```

---

### Task 5: Repo documentation (CLAUDE.md + public README) and final verification

**Files:**
- Create: `CLAUDE.md` (developer guide — NOT published)
- Create: `README.md` (public catalog README — published)

**Interfaces:**
- Consumes: everything above. No code depends on this task.

- [ ] **Step 1: Write CLAUDE.md**

Create `CLAUDE.md`:

```markdown
# ftw-portolan — developer guide

Git-backed Portolan/STAC catalog for the **Fields of the World (FTW) Global** datasets.
This repo is the **source of truth for metadata only**. The data (billions of polygons,
COGs, Zarr — hundreds of GB) lives on Source Cooperative and is **never** stored or
uploaded by this repo.

## Path mapping (Source Cooperative)
- Write target (uploads): `s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data/`
- Public href base (all STAC hrefs): `https://data.source.coop/ftw/global-data/`
- Source Cooperative serves the public `ftw/global-data` path from the `tge-labs/...` prefix.

## Three file categories
1. Tracked + published: STAC JSON, README.md, llms.txt, thumbnail.png, `.portolan/metadata.yaml`.
2. Tracked, NOT published: `scripts/`, `docs/`, `CLAUDE.md`, `catalog.publish.yaml`, `.portolan/config.yaml`.
3. Gitignored (never in repo): data files (`*.tif`, `*.parquet`, `*.zarr`), `.env`, caches.

## Publish workflow
Edit metadata -> commit -> publish:
```
python3 scripts/publish.py            # dry run
python3 scripts/publish.py --confirm  # upload (needs AWS creds)
```
Only collections listed under `collections:` in `catalog.publish.yaml` are published.

## Add a collection
1. Create `<group>/<name>/collection.json` (+ `.portolan/metadata.yaml`); hrefs use the public base.
2. Add a `child` link in `catalog.json`.
3. When ready to go live, add its path to `collections:` in `catalog.publish.yaml`.
4. `python3 tests/test_links.py && python3 scripts/publish.py` to verify.

## Tests (dependency-free; run with python3)
`tests/test_links.py`, `tests/test_git_ext.py`, `tests/test_publish.py`, `tests/test_scaffolds.py`.

## Git extension (portolan-cli#485)
`catalog.json` hand-carries `git:repository`, `git:ref`, `git:provider` plus `vcs`/`issues`
links, pending CLI support.
```

- [ ] **Step 2: Write the public README.md**

Create `README.md`:

```markdown
# Fields of the World — Global

Global agricultural field boundaries and prediction-quality layers at 10 m resolution,
produced by applying the PRUE field-boundary segmentation model to global Sentinel-2
mosaics ([Robinson et al. 2026](https://arxiv.org/abs/2605.11055)). Published openly
under CC-BY-4.0 by Taylor Geospatial and collaborators.

This catalog (STAC 1.1.0 / Portolan) describes:

- **predictions/confidence** — 500 m prediction confidence & quality layers (COG)
- **predictions/vectors** — field-boundary polygons (GeoParquet) + PMTiles
- **predictions/zarr** — prediction probabilities (Zarr)
- **features/cogs** — Sentinel-2 planting/harvest composites (COG)
- **features/zarr** — Sentinel-2 feature mosaic (Zarr)

Data is hosted on [Source Cooperative](https://source.coop/ftw/global-data/). Catalog
metadata is maintained as code at
[github.com/fieldsoftheworld/ftw-portolan](https://github.com/fieldsoftheworld/ftw-portolan)
— corrections and additions welcome via pull request.
```

- [ ] **Step 3: Run the full test suite — expect all PASS**

Run:
```bash
cd /Users/cholmes/repos/ftw-portolan
for t in tests/test_links.py tests/test_git_ext.py tests/test_publish.py tests/test_scaffolds.py; do
  python3 "$t" || { echo "FAILED: $t"; break; }
done
```
Expected: four `OK: ...` lines, no `FAILED`.

- [ ] **Step 4: Confirm README publishes but CLAUDE.md does not**

Run: `cd /Users/cholmes/repos/ftw-portolan && python3 scripts/publish.py | grep -E 'README.md|CLAUDE.md'`
Expected: a line for `.../README.md`; NO line for `CLAUDE.md`.

- [ ] **Step 5: Commit**

```bash
cd /Users/cholmes/repos/ftw-portolan
git add CLAUDE.md README.md
git commit -m "Add developer guide (CLAUDE.md) and public catalog README"
```

---

## Post-plan (not in scope; do not implement now)

- Create the GitHub repo under `fieldsoftheworld/ftw-portolan` and push.
- Run `python3 scripts/publish.py --confirm` to publish the root catalog + confidence (requires AWS creds; first real upload of the root `catalog.json`).
- Flesh out item-level metadata, thumbnails, and llms.txt for the four scaffolded collections, then enable each in `catalog.publish.yaml`.
