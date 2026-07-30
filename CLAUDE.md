# ftw-data-catalog — developer guide

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
- `scripts/`, `tests/`, `docs/`, `CLAUDE.md`, root `README.md`, `catalog.publish.yaml` — tooling/docs, never published.
- Gitignored (never in repo): data files (`*.tif`, `*.parquet`, `*.zarr`), `.env`, caches.

## READMEs
- Root `README.md` — GitHub front door (not published).
- `catalog/README.md` — the README rendered on Source Cooperative (published).
- `catalog/README_next.md` — published preview of the proposed next catalog README (for sharing/feedback); promote by copying it over `catalog/README.md`.

## Publish workflow
Edit metadata under `catalog/` -> commit -> publish:
```
python3 scripts/catalog/publish.py            # dry run (what would change)
python3 scripts/catalog/publish.py --confirm  # upload (needs AWS creds)
```
`publish.py` syncs `catalog/` 1:1, skipping only Portolan-internal `.portolan/config.yaml`
and `.portolan/state.json`. Config (write_prefix, public_base, region, publish_dir) lives in
`catalog.publish.yaml`.

**Change detection:** objects whose bytes already match S3 are skipped (local size+MD5 vs the
object's size+ETag), so a typical publish uploads only what you edited and a no-op run takes
~25 s instead of re-writing all 3.7 k objects. The remote side is read by listing each of the
~213 directories the catalog occupies **non-recursively** (`--delimiter /`), 16 at a time — a
plain recursive listing of `write_prefix` would walk every zarr chunk and COG sharing it
(~709 k keys, ~3 min). Caveats:
- A listing carries no ContentType, so a file whose *bytes* are unchanged but whose
  content-type mapping changed is skipped — run `--force` after editing `_content_type()`.
- `--force` re-uploads everything and skips the listing entirely.
- If listing fails (no creds), it warns and treats every file as changed, so a dry run still
  works offline; it never silently skips.

## Add / promote a collection
1. Build it under `staging/<group>/<name>/` (collection.json + `.portolan/metadata.yaml`); hrefs use the public base.
2. When ready: `git mv staging/<group>/<name> catalog/<group>/<name>`.
3. Add a `child` link to `catalog/catalog.json`.
4. `python3 tests/test_links.py && python3 scripts/catalog/publish.py` to verify.

## Tests (dependency-free; run with python3)
`tests/test_links.py`, `tests/test_git_ext.py`, `tests/test_publish.py`, `tests/test_scaffolds.py`.
`tests/test_stac_valid.py` validates every STAC object under `catalog/` against the official
schemas using `stac-check` (per file — recursive mode hits a stac-validator bug on relative
links, and stac-validator also can't process the Portolan *profile* schema, downgraded to a
warning there), reporting best-practice notes as non-fatal warnings.
`tests/test_portolan_conformance.py` runs `rashid check catalog --no-data --json` and fails on any
error outside a documented allow-list (rashid#61, the deferred zarr collections, and remote-asset
checksums pending the in-region backfill). Both SKIP when `stac-check`/`rashid` aren't installed, so
local runs stay zero-setup; CI (`.github/workflows/ci.yml`) installs both and runs all six, so
invalid STAC or non-conformant metadata fails the build on push/PR.

## Portolan 0.1 conformance
The catalog targets **Portolan 0.1** (spec `~/repos/portolan-spec`, checker `rashid`).
- The sole conformance signal is the schema URI `https://schemas.portolan-sdi.org/portolan/v0.1.0/schema.json`
  in `stac_extensions`, declared on **catalogs and collections only** (items inherit). There is **no
  `conformsTo`**, and 0.1 defines **no `portolan:`-prefixed fields** (styles are found via `roles:["style"]`
  assets; the non-standard `portolan:styles` field is retained, rashid-neutral, to drive the browser).
- Every asset MUST carry `file:size` and a multihash `file:checksum` (`1220`+sha256hex, **not** a
  `sha256:` prefix), regenerated at publish time (PORTO-CORE-030). Backfill with
  `scripts/migrate/backfill_file_meta.py` (`--local-only` for in-repo files; the remote pass hashes
  the S3 data — run it in-region/on Rails with `--via https --workers 16`; `--skip-href <substr>`
  defers specific assets). All vector/confidence assets are done; **deferred**: the two ~265 GB
  global vector PMTiles (`pmtiles_2025`, `pmtiles_2024_confidence` — too large to hash now / being
  regenerated) and the zarr collections. The conformance gate tolerates these as remote-pending.
- Providers: exactly one `host`, listed last. FTW models **Source Cooperative** as `host` and Taylor
  Geospatial as producer/licensor/processor → each collection is a "mirror" in rashid's taxonomy, so
  it carries a `rel:via` (text/html) and top-level `updated`.
- Known-accepted rashid findings: **PTL-LNK-006** on large-country subdivision items is a rashid
  over-strictness vs core.md:168-170 (tracked in https://github.com/portolan-sdi/rashid/issues/61);
  the two zarr collections are excluded pending regeneration.
- One-shot migration lives in `scripts/migrate/upgrade_to_0_1.py` (idempotent).
- **Generated (S3-only) feature items:** `scripts/features/build_features_items.py` emits 0.1-conformant
  collections/catalog and per-tile items (relative links, no `self`, file extension, `file:size` via
  HTTP HEAD). **`file:checksum` on the ~90k feature COGs (~tens of TB) is deferred** — impractical to
  backfill post-hoc; per PORTO-CORE-030 it belongs in the COG generation/upload pipeline. Re-run
  `items 2024`/`2025` on rails to republish the conformant items; re-run `backfill_file_meta.py
  --local-only` after `collections` to restore `file:` on in-repo assets.

## Git extension (portolan-cli#485)
`catalog/catalog.json` hand-carries `git:repository`, `git:ref`, `git:provider` plus `vcs`/`issues`
links, pending CLI support. These are non-spec extras (0.1 defines no git extension); rashid ignores them.
