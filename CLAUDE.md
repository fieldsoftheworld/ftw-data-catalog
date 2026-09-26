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
- **The features MGRS browse tree (S3-only).** The ~22.7k items/year are browsable as
  collection → UTM zone (60) → grid zone `35U` (641 cells, median 36 items) → item, with node titles
  naming the countries each cell covers (`mgrs_places.json`, rebuilt by the `places` subcommand from
  Natural Earth). The tree — items *and* the ~700 catalogs/year above them — is generated straight to
  S3 and never committed. For a metadata-only change use `items <year> --from-parquet`, which rebuilds
  everything from the published `items.parquet` in minutes anywhere instead of ~8 h of COG-header
  reads on rails.
  **Consequence:** the committed collections carry relative `child` links into a tree that is absent
  from a git checkout (relative is required — PTL-LNK-004 — and they resolve once published). So
  `tests/test_links.py` and `tests/test_portolan_conformance.py` each carry a narrow, documented
  exemption for those links only; conformance of the tree itself is verified against the **published**
  catalog, not the checkout. Chris (the Portolan spec author) is evolving the spec to cover a catalog
  whose generated parts live only at the publish base — rashid would resolve such links against it,
  cf. `--live-base-url`. Note `structure.md:87` ("flat hierarchy … no nested sub-collections") and the
  stale `core.md:168-170` citation below both predate that.
- **Known data gap (pre-existing):** 26 items in 2024 and 21 in 2025 advertise a `planting` or
  `harvest` COG that is not on S3 (e.g. `s2med_planting/57KTV/20240101.tif` — the tile has 2025 but no
  2024 planting composite). Those assets carry no `file:size`; the fix belongs in the COG pipeline.

## Tiles pipeline (`scripts/tiles/`)

GeoParquet → PMTiles for the global field predictions, run on the TGI RAILS Slurm
cluster with gpio + tylertoo. `scripts/tiles/README.md` documents the full chain
(stage → GeoParquet 2.0 → sharded field builds → a5 cell aggregates) with measured
timings; deploy with `rsync -av scripts/tiles/ rails:ftw-pipeline/`.

**Rails cluster (account `bgtj-tgirails`):**
- Partitions: `cpu` (rails01–06, 192c, 512G/2TB) and `cpu_amd` (rails07–15, 112–128c,
  ~256G) — cpu_amd is often idle when cpu is saturated; 192G jobs fit there, 360G
  (the fields coarse job, tylertoo#543) does not.
- `/tmp` is tmpfs and counts against the job cgroup — always `TMPDIR` on `/u`.
- sbatch spools `$0`, so scripts `cd $SLURM_SUBMIT_DIR`; pass env via exported shell
  vars + `--export=ALL` (values in `--export=A=x,B=y` get comma-split).
- tylertoo must be built ON the cluster (glibc 2.28): `~/tylertoo-src`, build with
  `PROTOC=/u/cholmes/micromamba/envs/ftw/bin/protoc cargo build --release`.
- Python: `~/ftw-us-tiles/venv` (duckdb, gpio, pmtiles, shapely, pyproj);
  aws CLI in `/u/cholmes/micromamba/envs/ftw/bin`.

**Data gotchas (all learned the hard way):**
- `determination:datetime` year markers are midnight-UTC — derive years with
  `SET TimeZone='UTC'` or every year shifts down on rails (America/Chicago).
- Boundary-straddling fields are duplicated upstream, one row per subdivision
  (issue #9) — staging dedupes on `(id, area)` per country.
- Giant "fields" are artifacts: >350 km² is 100% junk (largest legit complex is a
  331 km² conf-98.7 Russian grain block); 100–350 km² is ~91% junk by area but
  confidence can't cleanly separate it (AU's real paddocks sit at conf ≈33, and
  CN/MX have no confidence at all).
- a5 is equal-area: r5 ≈ 33,208 km², r7 ≈ 2,075.5 km², r8 ≈ 518.9 km² per cell.
  DuckDB's `ST_Area_Spheroid` is broken on a5 cell polygons (NaN or 100× off) —
  use the constant (add_coverage.py self-calibrates via pyproj). Dateline cells
  have vertices past ±180 and must be wrapped or tile exporters drop them.
- A plain DuckDB `COPY` of GeoParquet drops the `geo` metadata key — merge with
  `gpio extract`, follow DuckDB rewrites with `gpio convert geoparquet ...
  --geoparquet-version 2.0` (2.0 native stats also enable tylertoo row-group pruning).
- DuckDB `s3://` URLs hang on rails compute nodes (blackholed IMDS); use
  `https://data.source.coop/...`, and set a browser-ish User-Agent (the list API
  403s python-urllib).

**Uploads:** data files (pmtiles/parquet) via `aws s3 cp` from rails to the write
target; catalog metadata via `scripts/catalog/publish.py` as above (direct s3 cp of
committed catalog files is byte-equivalent and publish.py will skip them).

## Git extension (portolan-cli#485)
`catalog/catalog.json` hand-carries `git:repository`, `git:ref`, `git:provider` plus `vcs`/`issues`
links, pending CLI support. These are non-spec extras (0.1 defines no git extension); rashid ignores them.
