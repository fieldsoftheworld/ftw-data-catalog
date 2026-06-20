# `scripts/` — FTW prediction pipeline & catalog tooling

These scripts take the raw **Fields of the World (FTW)** global field-boundary
predictions all the way to the published Portolan/STAC catalog. They're grouped by
pipeline stage, each folder with its own README:

| Folder | Stage | What it does |
|---|---|---|
| [`fiboa/`](fiboa/) | A1 | `results/` (raw Wherobots snappy) → **fiboa-refined** GeoParquet (fields only, schemas, geometry metrics, determination). |
| [`admin/`](admin/) | A2 | fiboa → **admin-partitioned** (`results-by-admin/`): add Vecorel admin columns, partition by country (Hive), + the rails env bootstrap. |
| [`confidence/`](confidence/) | A3 | admin → **`results-by-admin-conf/`**: per-polygon `confidence` (0–100) + per-country PMTiles (2024/2025 layers). The current, reusable step. |
| [`catalog/`](catalog/) | B | Generate STAC metadata / READMEs / thumbnails / styles and **publish** the `catalog/` tree to Source Cooperative. |

Nothing here is a package — each script is run directly (`python3 scripts/<folder>/x.py`
/ `bash scripts/<folder>/x.sh`) and is `argparse`/env-parameterized. Most are resumable
(skip-existing). Source-bucket reads are anonymous; writes use default AWS creds.

These are currently a bit more of a record of the various learnings to process the data,
and in that process we improved geoparquet-io a lot.  When we get a 1.1 release of
predictions with smoother boundaries and other improvements we should consolidate these
into a much cleaner / smaller set of scripts.

## End-to-end pipeline

```
predictions zarr ──(Wherobots, not yet scripted here)──▶ results/  (snappy, raw, has non-fields)
   │
   │  A1 fiboa/       results/ ─▶ results-fiboa/
   │     convert_ftw_simple.py  ▶  ftw_fiboa_improve.py  ▶  ftw_upload_and_clean.sh
   │
   │  A2 admin/       results-fiboa/ ─▶ results-by-admin/
   │     rails_addadmin_all.sh ▶ rails_partition_batched.sh ▶ rails_relayout.py(/_all.sh)
   │     ▶ rails_hive_reorg.py ▶ rails_unnest_s3.sh   (+ rails_country_names.py, rails_verify_final.py)
   │
   │  A3 confidence/  results-by-admin/ ─▶ results-by-admin-conf/  (+ per-country PMTiles)
   │     run_rails.sh ▶ process_partition.sh ▶ { add_confidence.py , make_pmtiles.py }
   │     copy_2024_pmtiles.sh  (collection-level 2024 PMTiles)
   │
   └─ B  catalog/     catalog/ STAC + publish
          build_vector_items.py   (vectors collection: items, sub-catalogs, styles, llms)
          build_items.py + make_llms.py + make_thumbnails.py   (confidence raster collection)
          publish.py              (catalog/ ─▶ Source Cooperative, 1:1)
```

> **Ordering note:** confidence (`confidence/add_confidence.py`) is currently applied at
> **A3**, per admin partition. Ideally it would run at **A1** (before admin
> partitioning) so confidence is intrinsic to every downstream product — a target for
> the post-1.1 consolidation, once the whole chain (zarr → refined) is scripted.

## Environment & gotchas (apply to all folders)

- **`gpio` = geoparquet-io CLI.** Several scripts hardcode a `GPIO` path — update it for
  the host. We often run **branches**, so check `gpio … --help` rather than released docs.
- **rails:** SSH needs Duo MFA (use an SSH ControlMaster; the user opens it once with
  `ssh rails`). There's a **64 GB per-user cgroup cap** (not the 251 GB physical RAM), and
  **NFS page cache counts against it** → big duckdb/COPY jobs get OOM-killed; keep memory
  bounded, stage I/O on `/tmp` (tmpfs), write final files to `/u` once.
- S3 paths (`results/`, `results-fiboa/`, `results-by-admin/`, `results-by-admin-conf/`)
  and `~/ftw-crs-fix` working dirs are duplicated at the top of the `rails_*` scripts.
- Reads are anonymous; writes need default AWS creds. Run long jobs detached
  (`nohup`/`setsid`); rely on skip-existing for resumability.
