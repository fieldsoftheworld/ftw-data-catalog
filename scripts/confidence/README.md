# `confidence/` — A3: confidence + per-country PMTiles

Enriches `…/results-by-admin/` into **`…/results-by-admin-conf/`**: appends a
per-polygon `confidence` (0–100) column and builds a per-country PMTiles (with
`2024`/`2025` year layers). This is the current, reusable processing step (it powers
the `vectors` collection alpha release), run on the **rails** box.

| Script | Does | Run |
|---|---|---|
| `run_rails.sh` | Driver: build a manifest of the `results-by-admin/` parquets, filter to a subset or `--all`, run N partitions in parallel (idempotent). | `bash scripts/confidence/run_rails.sh AD FR` · `… --all -j 4` |
| `process_partition.sh` | One partition: download → `add_confidence.py` → `make_pmtiles.py` → upload both to `results-by-admin-conf/`. | (invoked by `run_rails.sh`) |
| `add_confidence.py` | Append a `confidence` (0–100) column: centroid point-on-surface sample of the 500 m confidence COG, rescaled `raw/0.578178×100` (clamped), nodata→null. Streams by row-group (bounded memory). Unit-tested (`tests/test_add_confidence.py`). | `python3 scripts/confidence/add_confidence.py IN.parquet OUT.parquet [--cog URL]` |
| `make_pmtiles.py` | Build PMTiles via duckdb → GeoJSONSeq → tippecanoe, **one layer per prediction year** (`2024`/`2025`, from `determination:datetime`). Bounded duckdb memory. Workaround for the gpio streaming-geometry crash (geoparquet-io #511). | `python3 scripts/confidence/make_pmtiles.py IN.parquet OUT.pmtiles` |
| `copy_2024_pmtiles.sh` | Stream the 264 GB `2024_with_confidence.pmtiles` from Azure into the collection's S3 path. | `bash scripts/confidence/copy_2024_pmtiles.sh` |

## Running on rails

1. From your laptop, `ssh rails` once (Kerberos + Duo) to open the ControlMaster.
2. Deploy these scripts (toolchain is a `micromamba` env on shared `/u` with
   `tippecanoe`/`rasterio`/`duckdb`/`gpio@main` + `awscli`):
   ```
   rsync -av scripts/confidence/ rails:~/ftw-conf/
   ```
3. **Submit via Slurm** — do NOT run on the login node (it reaps heavy jobs mid-run):
   ```
   ssh rails 'cd ~/ftw-conf && sbatch run_rails.sbatch'   # exclusive compute node, -j 4
   ssh rails 'squeue -u $USER'
   ```
   `run_rails.sbatch` runs `run_rails.sh --all -j 4` on a dedicated node. Idempotent
   (skip-existing), so re-submitting sweeps any stragglers. Bound memory with
   `DUCKDB_MEM` (default 24 GB/worker). See the root `scripts/README.md` "Running on
   TGI rails" for the full Slurm recipe.

`add_confidence.py` ordering note: ideally this runs at the `fiboa/` stage (before
admin partitioning) — see the root `scripts/README.md`. Next stage:
[`../catalog/`](../catalog/).
