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

These are a record of the one-time admin run — see the repo root `scripts/README.md`
for the gotchas (gpio branches, 64 GB cgroup OOM, NFS). Next stage:
[`../confidence/`](../confidence/).
