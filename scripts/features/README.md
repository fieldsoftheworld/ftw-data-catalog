# `features/` — Sentinel-2 planting/harvest composite collections

Builds the STAC for the FTW model-input **features**: the Sentinel-2 planting- and
harvest-season median composites (`features/cogs/alpha`, `features/zarr/alpha`). One
**collection per year** (`s2-planting-harvest-composites-2024` / `-2025`).

`build_features_items.py` has two modes:

| Command | Output | Committed? |
|---|---|---|
| `collections` | The 2 `catalog/features/<year>/collection.json` + `README.md` + `llms.txt`. Each collection carries the global **Zarr** mosaic as a `data` asset and a **STAC-GeoParquet** asset (`items.parquet`) as the item index. | **Yes** (in the repo) |
| `items <year>` | Per-tile STAC items (one per MGRS tile, with `planting` + `harvest` COG assets) and the `items.parquet` STAC-GeoParquet. Written under `features/<year>/items/…` and `features/<year>/items.parquet` **on S3**. | **No — S3-only, `.gitignore`d** |

## Why items are S3-only

There are ~22.7k tiles per year. Committing ~45k item JSONs to git is impractical, so —
like the prediction `vectors` data — the **items and the stac-geoparquet live only on
Source Cooperative (S3)**, produced by this script and `.gitignore`d locally
(`catalog/features/*/items/`, and `*.parquet`). The committed collection points at the
`items.parquet` STAC-GeoParquet as the scalable item index; clients read that instead of
tens of thousands of item links. `scripts/catalog/publish.py` only publishes the repo's
`catalog/` tree, so it never touches these S3-only artifacts.

## Item shape (best-practice STAC for COGs)

Each item = one MGRS tile/year: lowercase id (`01fbe_2024`), the [grid extension](https://github.com/stac-extensions/grid)
`grid:code` (`MGRS-01FBE`), populated `datetime` + season range, item-level `proj:` (read
from the COG header), unified STAC 1.1 `bands` (eo) with `data_type`/`gsd` at the asset,
COG media type, a markdown description with links, and a `derived_from` link to the
official ESA **Copernicus Data Space Ecosystem** Sentinel-2 L2A collection (plus a `via`
to the AWS/Earth Search L2A COGs actually used).

## Run

```bash
# in the repo (writes the committed collections)
python3 scripts/features/build_features_items.py collections

# on rails (anonymous S3 read for COG headers + index.parquet; AWS creds to upload)
python3 scripts/features/build_features_items.py items 2024
python3 scripts/features/build_features_items.py items 2025
# test first: --limit 5 --no-upload
```

Needs `duckdb`, `rasterio`, `pyarrow`, `aws`, and (for a proper stac-geoparquet)
`stac-geoparquet`; falls back to a minimal index parquet if that isn't installed.
