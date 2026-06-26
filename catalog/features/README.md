# FTW Global — Sentinel-2 Planting & Harvest Composites

<img src="https://data.source.coop/ftw/global-data/features/thumbnail.png" width="600" alt="Sentinel-2 composite preview">

Sentinel-2 **planting- and harvest-season median composites** at 10 m — the model-input features for the FTW Global field-boundary predictions. For each grid tile and season, ~5–10 quality-masked Sentinel-2 scenes (selected by latitude-based day-of-year heuristics) are reduced to a per-pixel median; bands are B02/B03/B04/B08 plus N_VALID_PIXELS, in the tile's native UTM zone. Part of [Fields of the World](https://fieldsofthe.world). These composites feed the **PRUE** U-Net model ([Muhawenayo et al. 2026](https://arxiv.org/abs/2603.27101); 76% IoU / 47% object-F1 on the [Fields of the World benchmark](https://source.coop/kerner-lab/fields-of-the-world) of 70,462 Sentinel-2 samples across 24 countries, [Kerner et al. 2025](https://arxiv.org/abs/2409.16252)), whose outputs are the [field-boundary predictions](https://source.coop/ftw/global-data/predictions). The same composites are published in two equivalent formats: per-tile **COGs** (these per-year collections) and a single global EPSG:4326 **[Zarr mosaic](https://source.coop/ftw/global-data/features/zarr)** (its own collection), stackable with the prediction Zarr.

**Items & index:** ~22.7k per-tile items (each with a `planting` and `harvest` COG asset) are indexed by the collection's STAC-GeoParquet asset (`items.parquet`); query that rather than enumerating item links.

## Collections

- [**COGs — 2024**](https://source.coop/ftw/global-data/features/2024) — per-tile planting + harvest COGs + a STAC-GeoParquet item index.
- [**COGs — 2025**](https://source.coop/ftw/global-data/features/2025)
- [**Zarr mosaic (2024 & 2025)**](https://source.coop/ftw/global-data/features/zarr) — the same composites as one global datacube.

## Folder layout

- `cogs/` — the actual per-tile **COG** files (GeoTIFF) plus their `index.parquet`.
- `zarr/alpha/global.zarr` — the global **Zarr** mosaic data.
- `2024/`, `2025/`, `zarr/` — the **STAC metadata** (a `collection.json`, `README.md`, item index). The `2024/` and `2025/` folders hold metadata only — the imagery itself lives under `cogs/` (and `zarr/`).

Source imagery: [Sentinel-2 L2A](https://sentinels.copernicus.eu/web/sentinel/missions/sentinel-2) (ESA / Copernicus). License: CC-BY-4.0.
