# `admin/` — A2: fiboa → admin-partitioned (`results-by-admin/`)

The one-time run that produced the Vecorel-admin-partitioned dataset
(`…/results-by-admin/`): adds `admin:country_code`/`admin:subdivision_code`, then
partitions by country in Hive layout (`admin:country_code=<CC>/`), splitting a country
by subdivision only when it's large. 574 objects, 195 countries, every file
vec-valid. All heavy steps ran on the **rails** box. Plus the rails environment
bootstrap.

| Script | Does |
|---|---|
| `rails_addadmin_all.sh` | Step A: `gpio add admin-divisions --vecorel` per part (adds admin codes via Overture). Needs the maritime-overlap land-filter fix (gpio #474). 8-way; outputs stay on `/u`. |
| `rails_partition_batched.sh` | Step B: memory-safe (64 GB cgroup) size-adaptive partition — split a country by subdivision only when large; batched + per-country merge; vec-valid output. |
| `rails_relayout.py` / `rails_relayout_all.sh` | Step C: merge small countries to one file per country (named via `pycountry`), keep giants' subdivision files; drop the leaked `__gpio_part*` columns (gpio #490) + Spark junk metadata; zstd-9. |
| `rails_hive_reorg.py` | Step D: rename into Hive dirs `admin:country_code=<CC>/…` (cheap `os.rename`). |
| `rails_unnest_s3.sh` | Step D: flatten giants' subdivision files to `<CC>_<sub>.parquet` via server-side `aws s3 mv`. |
| `rails_country_names.py` | Helper: map ISO codes → country names (`pycountry`) → `country_names.json`. |
| `rails_verify_final.py` | Verify the final layout (file/country counts, flat vs nested). |
| `rails_install.sh` | **Env bootstrap** on rails: `module load python/3.11`, venv, install the needed `geoparquet-io` branch + `awscli` + `vecorel-cli`. (Shared with `fiboa/`.) |
| `recover_dependencies.py` | **Follow-up fix** (not part of the original run): recover the Overture *dependency* territories that step A dropped into `ZZ`. See below. |

## The dependency fix — `recover_dependencies.py`

Step A attributed countries with `gpio add admin-divisions --vecorel`, and gpio built
its Overture country cache with `subtype = 'country'`. That matches only the 219
sovereign states. Overture files the 53 **dependent territories** — French Guiana,
Puerto Rico, Réunion, Guadeloupe, Mayotte, New Caledonia, Greenland, Hong Kong, Macao,
Guam, the Channel Islands and the rest — under `subtype = 'dependency'`, so every
field in them matched no polygon and was coalesced to `admin:country_code = 'ZZ'`.
That is a large part of why the `ZZ`/Unknown partition held 46.4 M polygons, and why
`GF` had no partition at all despite 63 k fields in French Guiana.

Fixed upstream in **[geoparquet-io#820](https://github.com/geoparquet/geoparquet-io/pull/820)**
(issue [#819](https://github.com/geoparquet/geoparquet-io/issues/819)): the country
level now draws on `subtype IN ('country', 'dependency')`. `recover_dependencies.py`
applies that to the already-published data without re-running the ~3.2 B-polygon
pipeline — only the country level changes, and only inside a dependency:

```
python3 recover_dependencies.py --zz Unknown.parquet --out work/ \
        --gpio "uv run --directory ~/repos/geoparquet-io gpio"
```

Three resumable stages, and **the two that decide anything are the same gpio commands
the original run used** — `gpio add admin-divisions --vecorel` (step A) to re-attribute
and `gpio partition string --column admin:country_code --hive` (step B) to split.
DuckDB only prepares and tidies around them: **split** carves out the candidates (rows
whose bbox overlaps one of the 50 dependency bboxes — ~5.9 M of 46.4 M, an optimisation
that leaves the answer unchanged), **attribute** runs gpio, and **emit** normalises,
partitions, renames to the catalog's `<Country_Name>.parquet` convention (steps C/D)
and rewrites `Unknown.parquet`, asserting row conservation.

A **future from-scratch run needs none of this.** With the fix in gpio, the existing
`rails_addadmin_all.sh` → `rails_partition_batched.sh` → `rails_relayout.py` chain
produces the dependency partitions by itself. This script exists only to patch data
that is already published.

Until the fix ships in a gpio release, point `--gpio` at a checkout of the branch —
`gpio --version` reports `1.4.0` either way, so the script probes
`_OVERTURE_LEVEL_CACHE_CONFIG` directly and **refuses to run** against a gpio without
the fix (which would otherwise silently recover nothing). It records the version,
branch, commit and dirty flag in `manifest.json` for provenance.

Three things the script has to work around, all verified against the real data:

- **Move the existing `admin:*` columns out of the way before calling gpio.** gpio
  selects `a.*` alongside its computed columns, so leaving them in yields duplicate
  names that DuckDB silently suffixes (`admin:country_code_1`) — the output looks
  unchanged because the stale `'ZZ'` column wins. The published
  `admin:subdivision_code` rides through as `__orig_subdivision` and is restored at
  the end, so a newer Overture release cannot perturb subdivision codes.
- **De-duplicate after the region join.** The country join is 1:1 (Overture's country
  and dependency polygons do not overlap — the only intersections are six zero-area
  shared borders), but a feature sitting between two adjacent *regions* matches both.
  Pre-existing gpio behaviour, unrelated to the fix.
- **No positional key back to the source.** `row_number() OVER ()` is not guaranteed
  to number two queries over the same parquet alike, and `id` is only unique within
  its original tile (3.86 M distinct across 46.4 M rows), so a recovered row is
  written entirely from the attributed file, which carries every published column.

Recovered territories get `admin:subdivision_code = 'ZZ'`. That is correct: Overture
has region rows for them (French Guiana has Cayenne, Saint-Georges and
Saint-Laurent-du-Maroni) but their `region` field is NULL, so there is no ISO 3166-2
code to record.

`publish_recovered.sh` then builds PMTiles for each recovered partition and uploads
the parquet + pmtiles to `results-by-admin-conf/`. The STAC beside them is regenerated
afterwards by `scripts/catalog/build_vector_items.py` and shipped with
`scripts/catalog/publish.py`.



## Where these ran — TGI rails

The `rails_*` scripts were written to run on **[TGI rails](https://www.ncsa.illinois.edu/research/project-highlights/tgi-rails/)**,
the Taylor Geospatial Institute's research computing environment operated by NCSA
(the National Center for Supercomputing Applications at the University of Illinois).
rails gives TGI researchers a large shared Linux box with a very fast network path to
cloud object storage — ideal for streaming hundreds of GB to/from Source Cooperative
without paying egress through a laptop.

The scripts therefore encode a few rails-specific facts: SSH needs Kerberos + Duo MFA
(driven via an SSH ControlMaster), there's a **64 GB per-user cgroup cap** (with NFS
page cache counting against it, so memory must be kept bounded), `/u` is NFS while
`/tmp` is RAM-backed tmpfs, and the toolchain is bootstrapped per-user
(`rails_install.sh`).

> **Run via Slurm, not the login node.** rails is a Slurm cluster and its `railsl*`
> login node reaps heavy jobs (they die mid-run even with `nohup`). These `rails_*`
> steps predate that lesson; run them on a compute node with `sbatch` — see the root
> `scripts/README.md` "Running on TGI rails" and the ready-made templates
> `scripts/confidence/run_rails.sbatch` / `scripts/features/features_items.sbatch`.

None of that is essential — these are ordinary `gpio` + `aws` + Python steps and
**adapt easily to any cloud computing environment** (an EC2/GCE VM, a batch job, etc.).
To run elsewhere, adjust the hardcoded paths/working dirs at the top of each script,
relax the memory bounds to match your machine, and install the toolchain however you
like (the `vectors` confidence/PMTiles step, for example, used a `micromamba` env
instead of rails' modules). A box with a fat pipe to the data store is the only real
requirement.

These are a record of the one-time admin run — see the repo root `scripts/README.md`
for the gotchas (gpio branches, 64 GB cgroup OOM, NFS). Next stage:
[`../confidence/`](../confidence/).
