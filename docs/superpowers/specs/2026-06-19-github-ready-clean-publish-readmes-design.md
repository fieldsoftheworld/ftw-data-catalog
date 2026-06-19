# GitHub-ready repo: clean publish model + three READMEs

**Date:** 2026-06-19
**Status:** Approved (design)

## Problem

The `ftw-portolan` repo is the metadata-only source of truth for the FTW Global
catalog. We want to put it on GitHub cleanly. Today the repo `README.md` serves
double duty — it is both the developer/GitHub README *and* the file published to
Source Cooperative as the catalog's `README.md` — so the two cannot differ. The
publishing mechanism is a maintained allowlist (`root_files` + `publish_globs` +
`collections` in `catalog.publish.yaml`), which is easy to get out of sync and is
the root cause of the README collision.

We want:

1. A `README.md` that is the **GitHub repo front door** (not published).
2. A README **published to Source Cooperative** as the directory render (`README.md`),
   which for now is exactly the current live content at
   `https://data.source.coop/ftw/global-data/README.md`.
3. A `README_next.md` — the **full Portolan README** that merges the best of the
   current content with links to the agent directions (`llms.txt`), the STAC
   catalog, and the Portolan browser render. Staged as a draft until promoted.

## Decisions

- **Adopt a clean publish-directory model.** A single `catalog/` directory is the
  catalog, published 1:1 to S3. Everything outside `catalog/` (tooling, the GitHub
  README, staged collections) is never published. This is WYSIWYG, removes the
  allowlist, is Portolan-native (the `portolan` CLI operates on `catalog/`), and
  resolves the README collision for free.
- **Scaffold collections stay out of the published catalog.** `features/*`,
  `predictions/vectors`, `predictions/zarr` move to `staging/` and their `child`
  links are removed from the published `catalog.json` until each is ready (avoids
  dangling links in the live catalog). Promotion = move `staging/<g>/<c>` into
  `catalog/<g>/<c>` and add the child link.
- **Publishing is a 1:1 sync of `catalog/`,** not `portolan push` (the design for
  this repo intentionally avoids `portolan push`, which expects to manage local
  data assets; see the prior spec). A small dependency-free `publish.py` walks
  `catalog/` and uploads every file with correct content-types, skipping only
  Portolan-internal `.portolan/config.yaml` and `.portolan/state.json`.

## Target repo structure

```
ftw-portolan/                       # git root — NEVER published
├── README.md                       # GitHub front door (rewritten)
├── README_next.md                  # staged draft of the next catalog/README.md
├── CLAUDE.md                       # dev guide (paths updated)
├── catalog.publish.yaml            # simplified: remote + publish_dir
├── .gitignore
├── docs/  scripts/  tests/         # tooling (paths updated)
├── staging/                        # git-tracked, not-yet-published collections
│   ├── features/cogs/   features/zarr/
│   └── predictions/vectors/   predictions/zarr/
└── catalog/                        # THE published catalog — synced 1:1 to S3
    ├── .portolan/{config.yaml,metadata.yaml}
    ├── catalog.json                # scaffold child links removed
    ├── README.md                   # current live Source Coop content (verbatim)
    ├── llms.txt
    ├── versions.json
    └── predictions/confidence/…    # live collection (collection.json, items,
                                     #   README.md, llms.txt, thumbnails,
                                     #   .portolan/metadata.yaml)
```

File moves:
- Into `catalog/`: `catalog.json`, `llms.txt`, `versions.json`, `.portolan/`,
  `predictions/confidence/`.
- Into `staging/`: `features/cogs`, `features/zarr`, `predictions/vectors`,
  `predictions/zarr`.
- Stay at root: `README.md`, `CLAUDE.md`, `catalog.publish.yaml`, `scripts/`,
  `tests/`, `docs/`, `.gitignore`.

## The three READMEs

### `README.md` (root, GitHub front door) — rewrite

Audience: developers/contributors on GitHub. Contents:
- What this repo is: git-backed Portolan/STAC catalog that is the source of truth
  for **metadata only**; the data (hundreds of GB) lives on Source Cooperative and
  is never stored or uploaded here.
- How it relates to the published catalog: `catalog/` is synced 1:1 to
  `s3://…/tge-labs/ftw-global-data/`, served at
  `https://data.source.coop/ftw/global-data/`.
- Repo layout (catalog/ vs staging/ vs scripts/ vs docs/).
- Contribute & publish workflow (edit metadata in `catalog/` → commit → publish).
- Links: live catalog README, `catalog.json`, Portolan browser render, `llms.txt`,
  the paper, `CLAUDE.md`.
- Concise — a front door, not the dataset manual.

### `catalog/README.md` (published directory render) — new file, verbatim current content

The **current live content** of `https://data.source.coop/ftw/global-data/README.md`,
copied verbatim. It is the data-product README (Features COGs/Zarr, Predictions
Zarr/GeoParquet/PMTiles, Appendix, License, Contact, Cite) with code examples and
images. Images reference absolute `https://data.source.coop/ftw/global-data/docs/*`
assets owned by the data team — kept as-is (not hosted in this repo). Publishing
under the new model therefore leaves the live render byte-for-byte unchanged.

### `README_next.md` (root, staged) — new file

The full Portolan README, merging the best of the current content with portolan-nl
conventions. Sections:
- Hero/title, one-line description, paper link, optional badges.
- **STAC catalog**: link `catalog.json`; the Portolan browser render
  `https://browser.portolan-sdi.org/#/external/data.source.coop/ftw/global-data/catalog.json`;
  per-collection links.
- **AI / Agent friendly**: link root `llms.txt` and per-collection `llms.txt`;
  "point Claude Code / Gemini CLI at `llms.txt`" framing (portolan-nl style).
- Collections table (confidence live; others noted as coming).
- Data products & access: the current README's COG/Zarr/GeoParquet/PMTiles sections
  and code examples (the best, most useful content).
- Caveats, License, Cite, Contact.

`portolan readme` output (run inside `catalog/`) is consulted as a baseline; the
file itself is curated, not auto-generated. Stays a draft until promoted to
`catalog/README.md`.

## Supporting changes

### `catalog/catalog.json`
- Remove the four scaffold `child` links: `features/cogs`, `features/zarr`,
  `predictions/vectors`, `predictions/zarr`.
- Keep: `root`, `self`, the `predictions/confidence` child, `about`, `cite-as`,
  `vcs`, `issues`, and the `git:*` fields.
- Relative hrefs unchanged (the whole tree moves together into `catalog/`);
  absolute hrefs unchanged.

### `catalog.publish.yaml`
Replace the allowlist with:
```yaml
write_prefix: s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data
public_base: https://data.source.coop/ftw/global-data
region: us-west-2
publish_dir: catalog
```

### `scripts/publish.py`
- Walk `publish_dir` (`catalog/`) recursively; build one `Upload` per file with the
  S3 URI = `write_prefix/<path relative to catalog/>`.
- Keep content-type detection (catalog.json/collection.json → `application/json`;
  other `.json` → `application/geo+json`; `.md`/`.txt` → `text/markdown`; `.png`,
  `.yaml`).
- Skip Portolan-internal files: `.portolan/config.yaml`, `.portolan/state.json`.
- Keep dry-run default / `--confirm` to execute / zero third-party deps (retain the
  minimal YAML fallback loader, simplified for the new keys).

### Tests (TDD — written/updated before the code)
- `tests/test_publish.py`: rewrite for the walk-`catalog/` model. Asserts:
  `catalog/README.md` and `catalog/predictions/confidence/collection.json` are in
  the upload set; root `README.md`, `README_next.md`, `scripts/`, `docs/`,
  `staging/` are NOT; `.portolan/config.yaml`/`state.json` are skipped;
  content-types correct; S3 URIs preserve the relative path under `catalog/`.
- `tests/test_links.py`: update to resolve from `catalog/`; assert every `child`
  href resolves to an existing file (no dangling scaffold links).
- `tests/test_scaffolds.py`, `tests/test_git_ext.py`: update paths to `catalog/`
  and `staging/`.

### `CLAUDE.md`
Update the path mapping, three-file-categories, publish workflow, and add-a-collection
sections to the clean-directory model.

## Out of scope
- No changes to the actual data on Source Cooperative.
- No promotion of `README_next.md` to live (separate, user-triggered step).
- No promotion of staged collections to live.
- Not switching to `portolan push` for publishing.

## Verification
- `python3 tests/test_links.py && python3 tests/test_git_ext.py && python3 tests/test_publish.py && python3 tests/test_scaffolds.py` all pass.
- `python3 scripts/publish.py` (dry run) lists exactly the `catalog/` tree mapped to
  the correct S3 URIs, and nothing from root/`staging/`/`scripts/`.
- Portolan browser render URL loads the catalog.
```
