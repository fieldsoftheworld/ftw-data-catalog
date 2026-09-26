# Global FTW PMTiles pipeline

Turns the `results-by-admin-conf` prediction parquets into PMTiles archives
with [tylertoo](https://github.com/cholmes/tylertoo) and
[gpio](https://github.com/geoparquet-io/geoparquet-io), on the TGI RAILS
Slurm cluster. Two products per year:

1. **Field boundaries** (`fields-<year>.pmtiles`) — every predicted field,
   z0–13, standard tylertoo density thinning at low zooms.
2. **a5 cell aggregates** (`fields-<year>-a5r7.pmtiles`) — a single a5 r7
   layer, every cell verbatim at z0–8, with per-cell `count`, `sum_area`
   (m²), `pct_covered`, `avg_confidence`. The low-zoom exploration layer.

## Running it

```bash
rsync -av scripts/tiles/ rails:ftw-pipeline/
ssh rails
cd ~/ftw-pipeline

# 1. Stage both years (deduped, UTC-correct), merge, convert to GeoParquet 2.0
sbatch stage.sbatch                       # ~380 GB scanned once; hours

# 2. Field archives — native sharded workflow (~8h wall per year at 2025 scale)
YEAR=2025 MODE=plan   sbatch --export=ALL tile_fields.sbatch
YEAR=2025 MODE=coarse sbatch --export=ALL --mem=360G tile_fields.sbatch
for i in $(seq 0 7); do YEAR=2025 MODE=shard IDX=$i sbatch --export=ALL tile_fields.sbatch; done
YEAR=2025 MODE=merge  sbatch --export=ALL tile_fields.sbatch

# 3. Cell archives (giant-field cutoff applied at aggregate input)
YEAR=2025 MAX_AREA_KM2=350 sbatch --export=ALL aggregate_cells.sbatch
YEAR=2025 sbatch --export=ALL tile_cells.sbatch     # prints tile-weight report
```

Env vars go through the shell + `--export=ALL` (a value inside
`--export=A=x,B=y` gets comma-split by sbatch).

## Data correctness notes

- **Dedupe (issue #9):** fields straddling admin subdivision boundaries are
  duplicated in the source (same `id`/geometry/area, one row per
  subdivision). Staging keeps one row per `(id, area)` within a country —
  without this, low-zoom rendering double-draws and aggregates double-count.
- **Timezone:** `determination:datetime` values are midnight-UTC year
  markers; deriving the year in a non-UTC session shifts it down one.
  `stage_global.py` sets `TimeZone='UTC'`.
- **Giant "fields":** the ≥100 km² bucket (7,127 features, 10% of global
  field area) is dominated by low-confidence Sahara artifacts (up to
  25,354 km², confidence ≈34). Staging is kept unfiltered; the decided
  cutoff (350 km² — everything above the largest legit 331 km² complex is
  junk) is applied per product via `MAX_AREA_KM2=350` on
  `aggregate_cells.sbatch` (or on `stage.sbatch` to drop at staging time).
- **`pct_covered`** can slightly exceed 100: a field is assigned wholly to
  one cell, so boundary fields contribute their full area there.

## Cluster gotchas (all learned the hard way)

- `/tmp` is tmpfs and counts against the job cgroup — always point `TMPDIR`
  at `/u` (the scripts do).
- DuckDB `s3://` URLs hang on compute nodes (blackholed EC2 metadata probe);
  use `https://data.source.coop/...`.
- A plain DuckDB `COPY` of GeoParquet drops the `geo` metadata key — merge
  with `gpio extract`, and follow any DuckDB rewrite with
  `gpio convert geoparquet ... --geoparquet-version 2.0`.
- tylertoo must be built ON the cluster (glibc 2.28): clone to
  `~/tylertoo-src`, `PROTOC=/u/cholmes/micromamba/envs/ftw/bin/protoc cargo
  build --release`.
- GeoParquet 2.0 conversion is what enables tylertoo's row-group pruning
  (native geo stats) — shard jobs then read ~2% of row groups instead of
  the whole file.

## Measured reference points (global 2025, 1.58B fields)

| step | wall |
|---|---|
| stage (598 files, one year) | ~6 h |
| coarse (z0–8 + convert plan, 360 G) | 4 h 12 m |
| 8 shards (z9–13, parallel) | 0.9–3.5 h |
| merge | 8.6 min |
| **fields archive total** | **~7 h 50 m** (115.5 GB) |
