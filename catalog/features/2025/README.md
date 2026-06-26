# FTW Global — Sentinel-2 Planting & Harvest Composites — COGs (2025)

![Sentinel-2 composite preview](https://data.source.coop/ftw/global-data/features/thumbnail.png)

Sentinel-2 **planting- and harvest-season median composites** at 10 m — the model-input features for the FTW Global field-boundary predictions. For each grid tile and season, ~5–10 quality-masked Sentinel-2 scenes (selected by latitude-based day-of-year heuristics) are reduced to a per-pixel median; bands are B02/B03/B04/B08 plus N_VALID_PIXELS, in the tile's native UTM zone. Part of [Fields of the World](https://fieldsofthe.world). These composites feed the **PRUE** U-Net model ([Muhawenayo et al. 2026](https://arxiv.org/abs/2603.27101); 76% IoU / 47% object-F1 on the [Fields of the World benchmark](https://source.coop/kerner-lab/fields-of-the-world) of 70,462 Sentinel-2 samples across 24 countries, [Kerner et al. 2025](https://arxiv.org/abs/2409.16252)), whose outputs are the [field-boundary predictions](https://source.coop/ftw/global-data/predictions). The same composites are published in two equivalent formats: per-tile **COGs** (these per-year collections) and a single global EPSG:4326 **[Zarr mosaic](https://source.coop/ftw/global-data/features/zarr)** (its own collection), stackable with the prediction Zarr.

**Items & index:** ~22.7k per-tile items (each with a `planting` and `harvest` COG asset) are indexed by the collection's STAC-GeoParquet asset (`items.parquet`); query that rather than enumerating item links.

## Access (COGs)

Per-tile COGs are indexed by the STAC-GeoParquet item index (`https://data.source.coop/ftw/global-data/features/2025/items.parquet`); each item has a `planting` and a `harvest` 5-band COG (B02/B03/B04/B08/N_VALID_PIXELS) in its native UTM zone. The **same data** is also published as a global [Zarr mosaic](https://source.coop/ftw/global-data/features/zarr), and these composites are the model inputs for the [field-boundary predictions](https://source.coop/ftw/global-data/predictions).

## License

CC-BY-4.0. Sentinel-2 imagery © Copernicus/ESA; composites by the Taylor Geospatial Institute and Microsoft AI for Good Research Lab.
