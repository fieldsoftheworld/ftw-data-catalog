# `scripts/` — FTW prediction-vectors pipeline & catalog tooling

These scripts take the raw **Fields of the World (FTW)** global field-boundary
predictions all the way to the published Portolan/STAC catalog. They fall into two
groups:

- **A. Data pipeline** — raw predictions → refined, confidence-enriched,
  admin-partitioned GeoParquet + per-country PMTiles on Source Cooperative. Heavy
  steps run on the **NCSA rails** box (`rails_*`); see *Environment* below.
- **B. Catalog tooling** — generate STAC metadata, READMEs, thumbnails, styles, and
  publish the `catalog/` tree to Source Cooperative.

Nothing here is a package — each script is run directly (`python3 scripts/x.py` /
`bash scripts/x.sh`) and is `argparse`/env-parameterized. Most are resumable
(skip-existing). Source-bucket reads are anonymous; writes use default AWS creds.

These are currently a bit more of a record of the various learnings to process the data, 
and in that process we improved geoparquet-io a lot.  When we get a 1.1 release of 
predictions with smoother boundaries and other improvements we should consolidate these
into a much cleaner / smaller set of scripts.

## End-to-end pipeline

```
predictions zarr ──(Wherobots, not yet scripted here)──▶ results/  (snappy, raw, has non-fields)
   │
   │  A1. results/ ─▶ results-fiboa/   (fiboa-refined: fields only, schemas, metrics, determination)
   │      convert_ftw_simple.py  ▶  ftw_fiboa_improve.py  ▶  ftw_upload_and_clean.sh
   │
   │  A2. results-fiboa/ ─▶ results-by-admin/   (Vecorel admin cols, partitioned by country)
   │      rails_addadmin_all.sh ▶ rails_partition_batched.sh ▶ rails_relayout.py(/_all.sh)
   │      ▶ rails_hive_reorg.py ▶ rails_unnest_s3.sh   (+ rails_country_names.py, rails_verify_final.py)
   │
   │  A3. results-by-admin/ ─▶ results-by-admin-conf/   (per-polygon confidence 0–100 + per-country PMTiles)
   │      run_rails.sh ▶ process_partition.sh ▶ { add_confidence.py , make_pmtiles.py }
   │      copy_2024_pmtiles.sh  (collection-level 2024 PMTiles)
   │
   └─ B. catalog/ STAC + publish
          build_vector_items.py   (vectors collection: items, sub-catalogs, styles, llms)
          build_items.py + make_llms.py + make_thumbnails.py   (confidence raster collection)
          publish.py              (catalog/ ─▶ Source Cooperative, 1:1)
```

> **Note on ordering:** confidence (`add_confidence.py`) is currently applied at
> **A3**, per admin partition. Ideally it would run at **A1** (before admin
> partitioning) so confidence is intrinsic to every downstream product — a future
> consolidation when the whole chain (zarr → refined) is scripted.

## A. Data pipeline

### A1 — results/ → fiboa-refined  (preferred "simple" CLI pipeline)
| Script | Does | Run |
|---|---|---|
| `convert_ftw_simple.py` | `gpio extract geoparquet` straight from the S3 `results/` parts, filter to `label = 'field'`, drop `label`/`bbox`, write GeoParquet 2.0 (zstd-22). Parallel; uploads each result. | `python3 scripts/convert_ftw_simple.py [--start N --end M --parallel P] [--skip-upload]` |
| `ftw_fiboa_improve.py` | `gpio fiboa improve` on stage-1 output: adds fiboa schemas, geometry metrics (`metrics:area`/`perimeter`), and `determination:*` columns. Deletes each input after success. | `python3 scripts/ftw_fiboa_improve.py [--parallel P] [--keep-input]` |
| `ftw_upload_and_clean.sh` | `aws s3 cp` the improved files to `…/results-fiboa/`, `rm` on success. | `bash scripts/ftw_upload_and_clean.sh` |


### A2 — fiboa → admin-partitioned  (the one-time run that built `results-by-admin/`)
| Script | Does |
|---|---|
| `rails_addadmin_all.sh` | Step A: `gpio add admin-divisions --vecorel` per part (adds `admin:country_code`/`admin:subdivision_code` via Overture). Needs the maritime-overlap land-filter fix (gpio #474). 8-way, outputs stay on `/u`. |
| `rails_partition_batched.sh` | Step B: memory-safe (64 GB cgroup) size-adaptive partition — split a country by subdivision only when large; batched + per-country merge; vec-valid output. |
| `rails_relayout.py` / `rails_relayout_all.sh` | Step C: merge small countries to one file per country (named via `pycountry`), keep giants' subdivision files; drop the leaked `__gpio_part*` columns (gpio #490) + Spark junk metadata; zstd-9. |
| `rails_hive_reorg.py` | Step D: rename into Hive dirs `admin:country_code=<CC>/…` (cheap `os.rename`). |
| `rails_unnest_s3.sh` | Step D: flatten giants' subdivision files to `<CC>_<sub>.parquet` via server-side `aws s3 mv`. |
| `rails_country_names.py` | Helper: map ISO codes → country names (`pycountry`) → `country_names.json`. |
| `rails_verify_final.py` | Verify the final layout (file/country counts, flat vs nested). |

### A3 — confidence + per-country PMTiles  (the `vectors` alpha run, this repo)
| Script | Does | Run |
|---|---|---|
| `run_rails.sh` | Driver: build a manifest of the `results-by-admin/` parquets, filter to a subset or `--all`, run N partitions in parallel (idempotent). | `bash scripts/run_rails.sh AD FR` · `… --all -j 4` |
| `process_partition.sh` | One partition: download → `add_confidence.py` → `make_pmtiles.py` → upload both to `results-by-admin-conf/`. | (invoked by `run_rails.sh`) |
| `add_confidence.py` | Append a `confidence` (0–100) column: centroid point-on-surface sample of the 500 m confidence COG, rescaled `raw/0.578178×100` (clamped), nodata→null. Streams by row-group. Unit-tested. | `python3 scripts/add_confidence.py IN.parquet OUT.parquet [--cog URL]` |
| `make_pmtiles.py` | Build PMTiles via duckdb → GeoJSONSeq → tippecanoe, with **one layer per prediction year** (`2024`/`2025`, from `determination:datetime`). Bounded duckdb memory. (Workaround for gpio #511.) | `python3 scripts/make_pmtiles.py IN.parquet OUT.pmtiles` |
| `copy_2024_pmtiles.sh` | Stream the 264 GB `2024_with_confidence.pmtiles` from Azure into the collection's S3 path. | `bash scripts/copy_2024_pmtiles.sh` |

## B. Catalog tooling

| Script | Does | Run |
|---|---|---|
| `build_vector_items.py` | Generate the `vectors` collection: one STAC item per parquet (id = filename stem), split-country sub-catalogs, glob `data` asset, two collection PMTiles, `table:columns` (fiboa/vecorel wording), per-country year-toggle MapLibre styles, and `llms.txt` per country. | `python3 scripts/build_vector_items.py [--keys file]` |
| `build_items.py` | Generate the 5 STAC items for the `confidence` raster collection (reads COG headers). | `python3 scripts/build_items.py` |
| `make_llms.py` | Generate `llms.txt` for the confidence collection + items. | `python3 scripts/make_llms.py` |
| `make_thumbnails.py` | Render `thumbnail.png` for the confidence collection/items from COG overviews. | `python3 scripts/make_thumbnails.py` |
| `publish.py` | **Canonical publisher.** Walk `catalog/` and upload 1:1 to Source Cooperative (per-file content-types; skips `.portolan/config.yaml`/`state.json`). Config in `catalog.publish.yaml`. | `python3 scripts/publish.py` (dry run) · `--confirm` |
| `restructure_s3.sh`, `publish_metadata.sh` | Legacy one-offs (server-side moves; older targeted publisher) — superseded by `publish.py`. | — |

### Environment bootstrap
| Script | Does |
|---|---|
| `rails_install.sh` | Bootstrap on rails: `module load python/3.11`, venv, install the needed `geoparquet-io` branch + `awscli` + `vecorel-cli`. (For the alpha run we used a `micromamba` env with `tippecanoe`/`rasterio`/`duckdb`/`gpio@main` instead.) |

## Environment & gotchas

- **`gpio` = geoparquet-io CLI.** Several scripts hardcode a `GPIO` path (e.g.
  `/Users/cholmes/miniforge3/envs/g/bin/gpio`) — update it for the host. We often run
  **branches**, so check `gpio … --help` rather than released docs.
- **rails:** SSH needs Duo MFA (use an SSH ControlMaster; the user opens it once with
  `ssh rails`). There's a **64 GB per-user cgroup cap** (not the 251 GB physical RAM),
  and **NFS page cache counts against it** → big duckdb/COPY jobs get OOM-killed; keep
  memory bounded, stage I/O on `/tmp` (tmpfs), write final files to `/u` once.
- **S3 paths** (`results/`, `results-fiboa/`, `results-by-admin/`,
  `results-by-admin-conf/`) and `~/ftw-crs-fix` working dirs are duplicated at the top
  of the `rails_*` scripts — adjust there.
- Reads are anonymous; writes need default AWS creds. Run long jobs detached
  (`nohup`/`setsid`) and rely on skip-existing for resumability.
- The `rails_*` scripts are a **record of the one-time admin run**; the `vectors`
  alpha confidence/PMTiles step (`run_rails.sh` + friends) is the current, reusable
  path. Provenance and field definitions are documented in
  `catalog/predictions/vectors/README.md` and the collection STAC.
