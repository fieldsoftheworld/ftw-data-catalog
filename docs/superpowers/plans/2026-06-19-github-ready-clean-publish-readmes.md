# GitHub-ready repo: clean publish model + three READMEs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the repo into a clean 1:1-published `catalog/` directory, simplify publishing to a directory walk, and add three distinct READMEs (GitHub front door, live catalog render, staged next render).

**Architecture:** Everything in `catalog/` publishes to Source Cooperative 1:1; everything outside it (tooling, drafts, the GitHub README, staged collections) never publishes. Scaffold collections move to `staging/` and lose their `catalog.json` child links until promoted. `publish.py` walks `catalog/` instead of consulting an allowlist.

**Tech Stack:** Python 3 (stdlib only — no third-party deps), `aws s3 cp`, dependency-free assertion tests run via `python3 tests/<file>.py`.

## Global Constraints

- Zero third-party Python dependencies in `scripts/` and `tests/` (stdlib only; optional `yaml` import must keep a fallback).
- Data files (`*.tif`, `*.parquet`, `*.zarr`) are NEVER added to the repo and NEVER published.
- Write target (S3): `s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data`
- Public href base: `https://data.source.coop/ftw/global-data`
- Region: `us-west-2`
- Portolan browser render URL: `https://browser.portolan-sdi.org/#/external/data.source.coop/ftw/global-data/catalog.json`
- GitHub repo: `https://github.com/fieldsoftheworld/ftw-portolan`
- Paper: `https://arxiv.org/abs/2605.11055`
- All tests must pass at the end of every task: `python3 tests/test_links.py && python3 tests/test_git_ext.py && python3 tests/test_publish.py && python3 tests/test_scaffolds.py`

## File structure (after this plan)

```
ftw-portolan/
├── README.md                       # NEW content: GitHub front door
├── README_next.md                  # NEW: staged draft of next catalog/README.md
├── CLAUDE.md                       # updated to clean-dir model
├── catalog.publish.yaml            # simplified: write_prefix/public_base/region/publish_dir
├── scripts/publish.py              # walks catalog/
├── tests/{test_links,test_git_ext,test_publish,test_scaffolds}.py  # updated
├── staging/
│   ├── features/{cogs,zarr}/
│   └── predictions/{vectors,zarr}/
└── catalog/
    ├── .portolan/{config.yaml,metadata.yaml}
    ├── catalog.json                # scaffold child links removed
    ├── README.md                   # NEW: verbatim current live Source Coop content
    ├── llms.txt
    ├── versions.json
    └── predictions/confidence/…
```

---

### Task 1: Restructure into `catalog/` + `staging/`, drop scaffold child links, fix structural tests

**Files:**
- Move (git mv): `catalog.json`, `llms.txt`, `versions.json`, `.portolan/`, `predictions/confidence/` → under `catalog/`
- Move (git mv): `predictions/vectors`, `predictions/zarr`, `features/cogs`, `features/zarr` → under `staging/`
- Modify: `catalog/catalog.json` (remove 4 scaffold `child` links)
- Modify: `tests/test_links.py`, `tests/test_git_ext.py`, `tests/test_scaffolds.py`

**Interfaces:**
- Produces: published catalog rooted at `catalog/`; staged collections at `staging/<group>/<name>/`; `catalog/catalog.json` whose only `child` link is `./predictions/confidence/collection.json`.

- [ ] **Step 1: Move catalog files and scaffolds**

```bash
cd /Users/cholmes/repos/ftw-portolan
mkdir -p catalog/predictions staging/predictions staging/features
git mv catalog.json catalog/
git mv llms.txt catalog/
git mv versions.json catalog/
git mv .portolan catalog/
git mv predictions/confidence catalog/predictions/
git mv predictions/vectors staging/predictions/
git mv predictions/zarr staging/predictions/
git mv features/cogs staging/features/
git mv features/zarr staging/features/
rmdir predictions features
```

- [ ] **Step 2: Remove the four scaffold `child` links from `catalog/catalog.json`**

Delete exactly these four link objects (the `predictions/vectors`, `predictions/zarr`, `features/cogs`, `features/zarr` children). Keep `root`, `self`, the `predictions/confidence` child, `about`, `cite-as`, `vcs`, `issues`, and all `git:*` fields. The `links` array should end after the `issues` link. Resulting `links` (order preserved) contains rels: `root`, `self`, `child` (confidence), `about`, `cite-as`, `vcs`, `issues`.

- [ ] **Step 3: Point `tests/test_links.py` and `tests/test_git_ext.py` at `catalog/`**

In `tests/test_links.py` change line 5:
```python
ROOT = Path(__file__).resolve().parents[1] / "catalog"
```
In `tests/test_git_ext.py` change line 4:
```python
ROOT = Path(__file__).resolve().parents[1] / "catalog"
```

- [ ] **Step 4: Rewrite `tests/test_scaffolds.py` for the staging model**

Replace the whole file with:
```python
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "staging"
CATALOG = ROOT / "catalog"
EXPECTED = {
    "predictions/vectors": "vectors",
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
print("OK: 4 scaffold collections staged and unlinked from published catalog")
```

- [ ] **Step 5: Run the structural tests (test_publish is unchanged and still passes — it uses a tmpdir fixture)**

Run: `cd /Users/cholmes/repos/ftw-portolan && python3 tests/test_links.py && python3 tests/test_git_ext.py && python3 tests/test_scaffolds.py && python3 tests/test_publish.py`
Expected: four `OK:` lines, no errors.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Restructure into clean catalog/ + staging/; drop scaffold child links

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Switch publishing to a 1:1 walk of `catalog/` (TDD)

**Files:**
- Test: `tests/test_publish.py` (rewrite)
- Modify: `scripts/publish.py` (`collect_uploads`)
- Modify: `catalog.publish.yaml` (simplify)

**Interfaces:**
- Consumes: `Upload(local: Path, s3_uri: str, content_type: str)` dataclass and `_content_type(p)` (unchanged in `scripts/publish.py`).
- Produces: `collect_uploads(manifest: dict, root: Path) -> list[Upload]` that walks `root / manifest["publish_dir"]`, emits one `Upload` per file with `s3_uri = write_prefix + "/" + <path relative to publish_dir>`, and skips `.portolan/config.yaml` and `.portolan/state.json`.

- [ ] **Step 1: Rewrite the failing test** — replace all of `tests/test_publish.py` with:

```python
"""Dependency-free test of publisher file selection. Run: python3 tests/test_publish.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from publish import collect_uploads  # noqa: E402


def build_tree(tmp: Path):
    # Repo-root files that must NOT publish (outside catalog/)
    (tmp / "README.md").write_text("github")
    (tmp / "README_next.md").write_text("draft")
    (tmp / "scripts").mkdir()
    (tmp / "scripts/foo.py").write_text("x")
    (tmp / "staging/predictions/vectors").mkdir(parents=True)
    (tmp / "staging/predictions/vectors/collection.json").write_text("{}")
    # The published catalog tree
    cat = tmp / "catalog"
    (cat / ".portolan").mkdir(parents=True)
    (cat / "catalog.json").write_text("{}")
    (cat / "llms.txt").write_text("x")
    (cat / "README.md").write_text("x")
    (cat / "versions.json").write_text("{}")
    (cat / ".portolan/metadata.yaml").write_text("x")
    (cat / ".portolan/config.yaml").write_text("x")   # internal, must NOT publish
    (cat / ".portolan/state.json").write_text("{}")    # internal, must NOT publish
    c = cat / "predictions/confidence"
    (c / "confidence").mkdir(parents=True)
    (c / "collection.json").write_text("{}")
    (c / "README.md").write_text("x")
    (c / "thumbnail.png").write_text("x")
    (c / "confidence/confidence.json").write_text("{}")


def main():
    import tempfile
    manifest = {
        "write_prefix": "s3://bucket/ftw-global-data",
        "public_base": "https://data.source.coop/ftw/global-data",
        "region": "us-west-2",
        "publish_dir": "catalog",
    }
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        build_tree(tmp)
        uploads = collect_uploads(manifest, tmp)
        rels = {u.local.relative_to(tmp / "catalog").as_posix() for u in uploads}

    expected = {
        "catalog.json", "llms.txt", "README.md", "versions.json",
        ".portolan/metadata.yaml",
        "predictions/confidence/collection.json",
        "predictions/confidence/README.md",
        "predictions/confidence/thumbnail.png",
        "predictions/confidence/confidence/confidence.json",
    }
    forbidden = {".portolan/config.yaml", ".portolan/state.json"}
    assert expected == rels, f"missing: {expected - rels}; leaked: {rels - expected}"
    assert not (forbidden & rels), f"leaked internal: {forbidden & rels}"

    by_rel = {u.local.relative_to(tmp / "catalog").as_posix(): u for u in uploads}
    assert by_rel["catalog.json"].s3_uri == "s3://bucket/ftw-global-data/catalog.json"
    assert by_rel["catalog.json"].content_type == "application/json"
    assert by_rel["predictions/confidence/confidence/confidence.json"].content_type == "application/geo+json"
    assert by_rel["predictions/confidence/thumbnail.png"].content_type == "image/png"
    assert by_rel["predictions/confidence/README.md"].content_type.startswith("text/markdown")
    print("OK: publisher walks catalog/ 1:1, excludes root/staging/scripts and .portolan internals")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/cholmes/repos/ftw-portolan && python3 tests/test_publish.py`
Expected: FAIL — `collect_uploads` still keys off `root_files`/`collections`, so `rels` won't match (assertion error or `KeyError`).

- [ ] **Step 3: Rewrite `collect_uploads` in `scripts/publish.py`**

Replace the existing `collect_uploads` function (lines 43–66) with:
```python
def collect_uploads(manifest: dict, root: Path) -> list[Upload]:
    write_prefix = manifest["write_prefix"].rstrip("/")
    pub_dir = root / manifest.get("publish_dir", "catalog")
    skip = {".portolan/config.yaml", ".portolan/state.json"}

    uploads = []
    if not pub_dir.is_dir():
        return uploads
    for p in sorted(pub_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(pub_dir).as_posix()
        if rel in skip:
            continue
        uploads.append(Upload(local=p, s3_uri=f"{write_prefix}/{rel}",
                              content_type=_content_type(p)))
    return uploads
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /Users/cholmes/repos/ftw-portolan && python3 tests/test_publish.py`
Expected: `OK: publisher walks catalog/ 1:1, excludes root/staging/scripts and .portolan internals`

- [ ] **Step 5: Simplify `catalog.publish.yaml`** — replace the whole file with:

```yaml
# What publishes, and where. Everything under publish_dir is uploaded 1:1.
# Data files are NEVER placed in publish_dir, so they cannot be published.
write_prefix: s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data
public_base: https://data.source.coop/ftw/global-data
region: us-west-2

# The catalog directory, synced 1:1 to write_prefix.
publish_dir: catalog
```

- [ ] **Step 6: Verify the real dry run lists only the catalog/ tree**

Run: `cd /Users/cholmes/repos/ftw-portolan && python3 scripts/publish.py`
Expected: `DRYRUN` lines for `catalog.json`, `llms.txt`, `versions.json`, `.portolan/metadata.yaml`, and the `predictions/confidence/...` files mapped under `s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data/`; NO lines for `.portolan/config.yaml`, `scripts/`, `staging/`, or root files.

- [ ] **Step 7: Commit**

```bash
git add scripts/publish.py catalog.publish.yaml tests/test_publish.py
git commit -m "Publish by walking catalog/ 1:1 instead of an allowlist

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: GitHub README + verbatim live catalog README

**Files:**
- Create: `catalog/README.md` (verbatim current live content)
- Modify: `README.md` (replace with GitHub front door content)

**Interfaces:**
- Produces: `catalog/README.md` (now in the publish set) and a root `README.md` that is never published.

- [ ] **Step 1: Fetch the current live Source Coop README verbatim into `catalog/README.md`**

```bash
cd /Users/cholmes/repos/ftw-portolan
curl -fsSL https://data.source.coop/ftw/global-data/README.md -o catalog/README.md
```
Verify it is non-empty and starts with the FTW hero `<div>`:
```bash
head -3 catalog/README.md
```
Expected: the leading `<div style="display:flex; …">` block. (This keeps the live render byte-for-byte unchanged on first publish. Its images point at absolute `data.source.coop/.../docs/*` assets owned by the data team — leave them as-is.)

- [ ] **Step 2: Replace root `README.md` with the GitHub front door**

Overwrite `README.md` with exactly:
````markdown
# ftw-portolan

Git-backed [Portolan](https://portolan-sdi.org)/STAC catalog for the **Fields of the World (FTW) Global** datasets — global agricultural field boundaries and prediction-quality layers at 10 m resolution.

**This repository is the source of truth for catalog _metadata_ only.** The data itself — billions of field polygons, COGs, and Zarr stacks (hundreds of GB) — lives on [Source Cooperative](https://source.coop/ftw/global-data) and is never stored in or uploaded by this repo.

- 🌍 **Live catalog & data:** <https://data.source.coop/ftw/global-data/>
- 🧭 **Browse the STAC catalog:** [Portolan browser](https://browser.portolan-sdi.org/#/external/data.source.coop/ftw/global-data/catalog.json)
- 🤖 **For AI agents:** [`llms.txt`](https://data.source.coop/ftw/global-data/llms.txt)
- 📄 **Paper:** Robinson et al. 2026, [arXiv:2605.11055](https://arxiv.org/abs/2605.11055)

## How this repo works

The [`catalog/`](./catalog/) directory **is** the published catalog: it is synced 1:1 to
`s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data/`, which Source Cooperative
serves at `https://data.source.coop/ftw/global-data/`. What you see in `catalog/` is exactly
what is live. Everything outside `catalog/` is never published.

```
catalog/        the published STAC/Portolan catalog (1:1 with Source Cooperative)
staging/        collections being prepared, not yet published
scripts/        publishing + build tooling
tests/          dependency-free catalog validation
docs/           design specs and plans
README_next.md  draft of the next published catalog README
CLAUDE.md       developer / agent guide
```

## Editing & publishing

1. Edit metadata under `catalog/` (STAC JSON, `README.md`, `llms.txt`, `.portolan/metadata.yaml`).
2. Validate: `python3 tests/test_links.py && python3 tests/test_publish.py`
3. Commit.
4. Publish: `python3 scripts/publish.py` (dry run), then `python3 scripts/publish.py --confirm` (needs AWS credentials).

See [CLAUDE.md](./CLAUDE.md) for the full developer guide. Corrections and additions welcome via pull request.

## License

Catalog metadata and data are published under CC-BY-4.0 by Taylor Geospatial and collaborators.
````

- [ ] **Step 3: Verify the publish set now includes the catalog README but not the root one**

Run: `cd /Users/cholmes/repos/ftw-portolan && python3 scripts/publish.py | grep -E 'README'`
Expected: exactly one line, ending `/README.md` under the write prefix (the `catalog/README.md`); the root `README.md` and `README_next.md` do not appear.

- [ ] **Step 4: Commit**

```bash
git add README.md catalog/README.md
git commit -m "Add GitHub README and publish verbatim live catalog README

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: `README_next.md` — staged full Portolan catalog README

**Files:**
- Create: `README_next.md`

**Interfaces:**
- Produces: a root-level draft (not published) intended to later overwrite `catalog/README.md`.

- [ ] **Step 1: Write `README_next.md`** with exactly:

````markdown
<div style="display:flex; gap:16px; align-items:center;">
  <a href="https://fieldsofthe.world/">
    <img src="https://data.source.coop/ftw/global-data/docs/ftw_hero.svg" alt="Fields of the World" width="100%" />
  </a>
</div>

# Fields of the World — Global

The first global, wall-to-wall agricultural field-boundary dataset at 10 m resolution:
**3.17 billion field polygons across 241 countries and territories** for 2024–2025, produced by
applying the [PRUE field-boundary segmentation model](https://huggingface.co/wherobots/prue-pt2)
(a U-Net with an EfficientNet-B7 encoder, trained on the Fields of The World benchmark) to
cloud-free Sentinel-2 mosaics. Published openly under CC-BY-4.0 by Taylor Geospatial and
collaborators (Microsoft AI for Good, ASU, WashU in St. Louis, Oregon State, Clark).

Paper: Robinson et al. 2026, *The first global agricultural field boundary map at 10 m resolution*
([arXiv:2605.11055](https://arxiv.org/abs/2605.11055)).

## Explore this catalog

- **STAC catalog (root):** <https://data.source.coop/ftw/global-data/catalog.json>
- **Browse interactively:** [Portolan browser](https://browser.portolan-sdi.org/#/external/data.source.coop/ftw/global-data/catalog.json)
- **For AI agents:** [`llms.txt`](https://data.source.coop/ftw/global-data/llms.txt) — a machine-readable
  description of the whole dataset. Point [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
  or [Gemini CLI](https://github.com/google-gemini/gemini-cli) at it and ask it to query the data,
  build interactive maps, or generate charts. Each collection also has its own `llms.txt`.
- **Source repository:** <https://github.com/fieldsoftheworld/ftw-portolan>

Storage: the public URL base `https://data.source.coop/ftw/global-data/` is physically backed by
`s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data/` (anonymous read).

## Collections

| Collection | Format | Description |
|---|---|---|
| [Prediction Confidence & Quality (500 m)](https://data.source.coop/ftw/global-data/predictions/confidence/collection.json) | COG | Global 500 m rasters quantifying where the field predictions can be trusted ([llms.txt](https://data.source.coop/ftw/global-data/predictions/confidence/llms.txt)) |

*More products — vector field boundaries (fiboa GeoParquet + PMTiles), prediction & feature Zarr
stacks, and Sentinel-2 composites (COG) — are already on Source Cooperative and are being added to
the STAC catalog incrementally (see [Data products](#data-products) below).*

## Key facts

- 3.17 billion field polygons (1.62 B in 2024, 1.55 B in 2025); 241 countries/territories; 10 m resolution.
- Model: PRUE (U-Net / EfficientNet-B7), trained on the CC-BY subset of Fields of The World (24 countries).
- A field here is a *remote-sensing field unit* (a connected component of predicted field-interior
  pixels), **not** a cadastral/legal parcel. This is not a land-tenure product.
- Outputs are fiboa-compliant GeoParquet (vectors) and Cloud-Optimized GeoTIFFs (rasters).
- Validation: mean pixel-level recall 0.85 over 24 countries (14 > 0.90); confidence-model LOCO mean AUC 0.842.

## Data products

All files are anonymous-read on Source Cooperative and work directly over HTTP — no account or API key.

### Prediction confidence & quality (500 m) — in the STAC catalog

Global 500 m rasters quantifying where the 10 m field predictions can be trusted (confidence,
field/boundary density, entropy, cropland consensus, precision/recall). Read a window of the
confidence COG — only the needed bytes are fetched:

```python
import rasterio
from rasterio.windows import from_bounds

url = "https://data.source.coop/ftw/global-data/predictions/confidence/confidence/prue_v1_confidence_global.tif"
with rasterio.open(url) as ds:
    conf = ds.read(1, window=from_bounds(2.0, 47.5, 3.0, 48.5, ds.transform), masked=True)
```

Or load the whole collection lazily as an xarray stack:

```python
import pystac, odc.stac
col = pystac.Collection.from_file(
    "https://data.source.coop/ftw/global-data/predictions/confidence/collection.json")
ds = odc.stac.load(list(col.get_items()), chunks={})
```

### Features — Sentinel-2 composites (COG & Zarr)

Planting/harvest median composites over ~5–10 Sentinel-2 scenes, as COGs and a single EPSG:4326
Zarr V3 mosaic at `8.983119e-5°` (~10 m at the equator).

```python
import rasterix
import xarray as xr

features = xr.open_zarr(
    "s3://us-west-2.opendata.source.coop/ftw/global-data/features/zarr/alpha/global.zarr"
).pipe(rasterix.assign_index)
```

### Predictions — Zarr, GeoParquet, PMTiles

The PRUE model runs over the feature Zarr to produce a prediction Zarr with bands
`[non_field_background, field, field_boundaries]` (same grid, so they stack). Vectors are derived by
thresholding at `0.5` and polygonizing into fiboa GeoParquet v1.1.0 (~8.2 B rows, ~629 GB) and a
PMTiles archive for web maps. Query the vectors with DuckDB:

```python
import duckdb

con = duckdb.connect()
con.execute("INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs;")
con.execute("""
SELECT geometry, time, label, bbox
FROM read_parquet('s3://us-west-2.opendata.source.coop/ftw/global-data/predictions/vectors/alpha/results/*.parquet')
WHERE label = 'field'
  AND struct_extract(bbox, 'xmax') >= -93.71488
  AND struct_extract(bbox, 'xmin') <= -93.06492
  AND struct_extract(bbox, 'ymax') >=  41.78201
  AND struct_extract(bbox, 'ymin') <=  42.09459
""").df()
```

## Caveats

- Temporal year (2025) is inferred from the paper and pending author confirmation.
- The field-density `_filtered` variant's exact threshold/method is pending author confirmation.
- The confidence layer is conservative outside the FTW training distribution (e.g. smallholder
  systems): real fields there may receive low confidence. Prefer the unfiltered density + continuous
  confidence over the default 0.4 threshold in such regions.
- Polygons are remote-sensing field units, not legal parcels; one parcel may map to many polygons or none.

## License

CC-BY-4.0.

## Cite

Robinson, C., Muhawenayo, G., Khanal, S., Fang, Z., Corley, I., Tárano, A. M., Estes, L., Marcus, J.,
Jacobs, N., Kerner, H., Becker-Reshef, I., & Lavista Ferres, J. M. (2026). *The first global
agricultural field boundary map at 10 m resolution.* arXiv:2605.11055.

## Contact

`isaac.corley@taylorgeospatial.org`

---

*Published with [Portolan](https://portolan-sdi.org).*
````

- [ ] **Step 2: Confirm `README_next.md` does NOT publish**

Run: `cd /Users/cholmes/repos/ftw-portolan && python3 scripts/publish.py | grep -c 'README_next' || true`
Expected: `0`

- [ ] **Step 3: Commit**

```bash
git add README_next.md
git commit -m "Add staged full Portolan catalog README (README_next.md)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Update `CLAUDE.md` to the clean-directory model

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Produces: developer guide consistent with the new structure (no consumers).

- [ ] **Step 1: Replace `CLAUDE.md`** with exactly:

````markdown
# ftw-portolan — developer guide

Git-backed Portolan/STAC catalog for the **Fields of the World (FTW) Global** datasets.
This repo is the **source of truth for catalog metadata only**. The data (billions of
polygons, COGs, Zarr — hundreds of GB) lives on Source Cooperative and is **never** stored
or uploaded by this repo.

## Clean publish-directory model
`catalog/` **is** the published catalog — synced 1:1 to Source Cooperative. Everything in
`catalog/` is published; everything outside it never is.

- Write target (uploads): `s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data/`
- Public href base (all STAC hrefs): `https://data.source.coop/ftw/global-data/`
- Source Cooperative serves the public `ftw/global-data` path from the `tge-labs/...` prefix.

## Layout
- `catalog/` — the published catalog (STAC JSON, README.md, llms.txt, thumbnails, `.portolan/metadata.yaml`). Synced 1:1 to S3.
- `staging/` — collections being prepared; git-tracked but NOT published.
- `scripts/`, `tests/`, `docs/`, `CLAUDE.md`, root `README.md`, `README_next.md`, `catalog.publish.yaml` — tooling/docs, never published.
- Gitignored (never in repo): data files (`*.tif`, `*.parquet`, `*.zarr`), `.env`, caches.

## READMEs
- Root `README.md` — GitHub front door (not published).
- `catalog/README.md` — the README rendered on Source Cooperative (published).
- `README_next.md` — draft of the next `catalog/README.md`; promote by copying it over `catalog/README.md`.

## Publish workflow
Edit metadata under `catalog/` -> commit -> publish:
```
python3 scripts/publish.py            # dry run (lists the catalog/ tree -> S3)
python3 scripts/publish.py --confirm  # upload (needs AWS creds)
```
`publish.py` uploads every file in `catalog/` 1:1, skipping only Portolan-internal
`.portolan/config.yaml` and `.portolan/state.json`. Config lives in `catalog.publish.yaml`.

## Add / promote a collection
1. Build it under `staging/<group>/<name>/` (collection.json + `.portolan/metadata.yaml`); hrefs use the public base.
2. When ready: `git mv staging/<group>/<name> catalog/<group>/<name>`.
3. Add a `child` link to `catalog/catalog.json`.
4. `python3 tests/test_links.py && python3 scripts/publish.py` to verify.

## Tests (dependency-free; run with python3)
`tests/test_links.py`, `tests/test_git_ext.py`, `tests/test_publish.py`, `tests/test_scaffolds.py`.

## Git extension (portolan-cli#485)
`catalog/catalog.json` hand-carries `git:repository`, `git:ref`, `git:provider` plus `vcs`/`issues`
links, pending CLI support.
````

- [ ] **Step 2: Run the full test suite**

Run: `cd /Users/cholmes/repos/ftw-portolan && python3 tests/test_links.py && python3 tests/test_git_ext.py && python3 tests/test_publish.py && python3 tests/test_scaffolds.py`
Expected: four `OK:` lines.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "Update CLAUDE.md to clean publish-directory model

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-review notes

- **Spec coverage:** clean `catalog/` model (Task 1, 2); scaffolds to `staging/` + child links dropped (Task 1, test in Task 1); 1:1 walk publisher + simplified manifest (Task 2); GitHub README (Task 3); verbatim live `catalog/README.md` (Task 3); `README_next.md` with STAC/browser/agent links + best data-product content (Task 4); `catalog.json` link cleanup (Task 1); tests updated incl. TDD for publisher (Task 1, 2); CLAUDE.md (Task 5). All spec sections mapped.
- **Behavior change flagged in spec:** `versions.json` now publishes (it lives in `catalog/`); covered by Task 2 test expectation.
- **Type consistency:** `collect_uploads(manifest, root)` signature unchanged; `Upload`/`_content_type` reused; `publish_dir` key used consistently in manifest, test, and `collect_uploads`.
- **No placeholders:** every code/content step is complete; verbatim catalog README is fetched deterministically via `curl` from the live source.
