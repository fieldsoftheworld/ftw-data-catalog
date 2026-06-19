# FTW Global Data — Git-Backed Portolan Catalog

**Date:** 2026-06-19
**Status:** Approved design
**Repo:** `https://github.com/fieldsoftheworld/ftw-portolan`

## Summary

Build `ftw-portolan`, a git repository that is the source of truth for the STAC/Portolan
metadata describing the **Fields of the World (FTW) Global** datasets. The actual data
(billions of polygons, COGs, Zarr stores — hundreds of GB) already lives on Source
Cooperative and is **not** managed, stored, or uploaded by this repo. This is a
"data-as-code" model: metadata is versioned in git; a metadata-only publish script
mirrors that metadata to object storage colocated with the data.

This realizes the git-backed catalog concept from
[portolan-cli#485](https://github.com/portolan-sdi/portolan-cli/issues/485) by
hand-adding the proposed `git:*` STAC extension fields, since the CLI (`1.0.0a0`) does
not yet implement them.

## Goals

- A clean, well-structured git repo that can be used to push metadata updates over time.
- Catalog **all five** FTW global-data product groups: confidence (done), prediction
  vectors, prediction zarr, feature COGs, feature zarr. Confidence works end-to-end;
  the other four are scaffolded for incremental completion.
- Hand-add the `git:*` extension fields per #485 so this is a reference implementation
  of the proposal.
- Keep helper scripts in the repo but structurally prevent them from ever being
  published into the catalog.

## Non-Goals

- Uploading, moving, or managing the underlying data (it lives on Source Cooperative).
- Implementing the git extension in portolan-cli itself.
- Adopting `monitor` link rel or `git:edit_url` (open questions in the proposal; deferred).
- Using `portolan push`/`sync` for publishing (it expects to manage local data assets;
  fights the metadata-only model). A custom metadata-only script is used instead.

## Source / Target Mapping

Source Cooperative aligns a public URL namespace to an S3 bucket prefix:

- **Write target (S3):** `s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data/`
- **Public href base:** `https://data.source.coop/ftw/global-data/`
- **Region:** `us-west-2`

All hrefs in STAC metadata use the public `data.source.coop/ftw/global-data` base.
Uploads are written to the `tge-labs/ftw-global-data` prefix. Source Cooperative serves
the former from the latter.

## Repository Layout

```
ftw-portolan/                          # git root
├── CLAUDE.md                          # repo guide for future sessions
├── README.md                          # human intro (metadata-only repo)
├── .gitignore                         # .env, *.tif, *.parquet, *.zarr, __pycache__, *.pyc, .DS_Store
├── .portolan/
│   ├── config.yaml                    # remote config
│   └── metadata.yaml                  # contact + license defaults
├── catalog.json                       # root STAC + git:* fields
├── versions.json
├── llms.txt
├── catalog.publish.yaml               # publish manifest (write-prefix, public-base, globs, enabled collections)
├── scripts/                           # tracked in git, NEVER published to catalog
│   ├── build_items.py
│   ├── make_llms.py
│   ├── make_thumbnails.py
│   ├── publish_metadata.sh            # metadata-only S3 upload, manifest-driven
│   └── restructure_s3.sh              # one-off server-side COG relocation
├── docs/superpowers/specs/            # design docs
├── predictions/
│   ├── confidence/                    # WORKING — collection.json + 5 COG items
│   ├── vectors/                       # SCAFFOLD — field boundaries (GeoParquet + PMTiles)
│   └── zarr/                          # SCAFFOLD — Zarr predictions
└── features/
    ├── cogs/                          # SCAFFOLD — COG features + index.parquet
    └── zarr/                          # SCAFFOLD — Zarr features
```

### Three file categories (the core idea)

1. **Tracked in git, published to S3:** all STAC JSON, `README.md`, `llms.txt`,
   `thumbnail.png`, `.portolan/metadata.yaml`.
2. **Tracked in git, NOT published:** `scripts/`, `CLAUDE.md`, repo `README.md`,
   `catalog.publish.yaml`, `.portolan/config.yaml`, `docs/`.
3. **Neither (gitignored):** data files (`*.parquet`, `*.tif`, `*.zarr`), `.env`, caches.

The publish script uploads only files matching an explicit allowlist of globs within
enabled collections, so category-2 files are structurally unreachable by publishing.

## Catalog Structure

| Path | Type | Data location (under public base) | Status |
|---|---|---|---|
| `predictions/confidence/` | COG items (5) | `predictions/confidence/<item>/*.tif` | working |
| `predictions/vectors/` | GeoParquet + PMTiles | `predictions/vectors/alpha/...` | scaffold |
| `predictions/zarr/` | Zarr | `predictions/zarr/alpha/global.zarr` | scaffold |
| `features/cogs/` | COG + index.parquet | `features/cogs/alpha/...` | scaffold |
| `features/zarr/` | Zarr | `features/zarr/alpha/global.zarr` | scaffold |

Each scaffold collection.json carries id/title/description/license/providers/extent
(sourced from the public catalog), with asset hrefs pointing at real `data.source.coop`
URLs and a `metadata.yaml`. Items/thumbnails/llms.txt are fleshed out later per
collection. Root `catalog.json` gains `child` links to all five collections.

**Zarr handling:** Zarr is not a Portolan core cloud-native format (GeoParquet / COG /
COPC / PMTiles). The two Zarr collections reference their stores as plain STAC assets
with an appropriate media type, not Portolan-managed assets.

## Git Extension Fields (#485)

Hand-added to `catalog.json` (collections inherit the concept):

```jsonc
"git:repository": "https://github.com/fieldsoftheworld/ftw-portolan",
"git:ref": "main",
"git:provider": "github",
// links array gains:
{ "rel": "vcs",    "href": "https://github.com/fieldsoftheworld/ftw-portolan" },
{ "rel": "issues", "href": "https://github.com/fieldsoftheworld/ftw-portolan/issues" }
```

Deferred: `monitor` link rel and `git:edit_url` (unsettled in the proposal).

## Publishing Workflow

`catalog.publish.yaml` drives a generalized `scripts/publish_metadata.sh`:

```yaml
write_prefix:  s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data
public_base:   https://data.source.coop/ftw/global-data
region:        us-west-2
publish_globs: ["**/*.json", "**/README.md", "**/llms.txt", "**/thumbnail.png", "**/.portolan/metadata.yaml"]
collections:
  - predictions/confidence   # only enabled collections are pushed
```

Behavior:

- Uploads only files matching `publish_globs` within enabled collections, plus root
  metadata (`catalog.json`, root `llms.txt`, root `README.md`).
- **Dry-run by default** (`--dryrun`); `CONFIRM=1` executes. Preserves the existing
  safety model.
- A collection is published only after being added to `collections:`, so scaffolds stay
  local until ready.
- `restructure_s3.sh` remains a one-off, per-collection server-side COG-relocation tool.

"Pushing an update" = edit metadata → commit to git → `CONFIRM=1 ./scripts/publish_metadata.sh`.
Git is the source of truth; S3 is a publish target.

## Migration Steps (from existing `ftw-global-data-catalog`)

1. `git init` at `/Users/cholmes/repos/ftw-portolan` (done — hosts this spec).
2. Copy `catalog.json`, `versions.json`, `llms.txt`, `.portolan/`, and the
   `predictions/confidence/` tree from `ftw-global-data-catalog`.
3. Move `build_items.py`, `make_llms.py`, `make_thumbnails.py`, `publish_metadata.sh`,
   `restructure_s3.sh` into `scripts/`.
4. Add `catalog.publish.yaml`, generalize `publish_metadata.sh` to read it.
5. Add `git:*` fields + `vcs`/`issues` links to `catalog.json`.
6. Scaffold the four new collections.
7. Add `.gitignore`, `CLAUDE.md`, repo `README.md`.
8. Initial commit.

## Open / Deferred

- Filling in item-level metadata, thumbnails, and llms.txt for the four scaffolded
  collections (incremental, post-MVP).
- Whether to later drive CLI implementation of #485.
