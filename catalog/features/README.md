# FTW Global — Sentinel-2 Planting & Harvest Composites

Sentinel-2 **planting- and harvest-season median composites** at 10 m — the model-input features for the FTW Global field-boundary predictions. For each grid tile and season, ~5–10 quality-masked Sentinel-2 scenes (selected by latitude-based day-of-year heuristics) are reduced to a per-pixel median; bands are B02/B03/B04/B08 plus N_VALID_PIXELS, in the tile's native UTM zone. Part of [Fields of the World](https://fieldsofthe.world). These composites feed the **PRUE** U-Net model ([Muhawenayo et al. 2026](https://arxiv.org/abs/2603.27101); 76% IoU / 47% object-F1 on the [Fields of the World benchmark](https://source.coop/kerner-lab/fields-of-the-world) of 70,462 Sentinel-2 samples across 24 countries, [Kerner et al. 2025](https://arxiv.org/abs/2409.16252)), whose outputs are the `predictions` collections. Also available as a single global EPSG:4326 Zarr mosaic (collection `data` asset), stackable with the prediction Zarr.

**Items & index:** ~22.7k per-tile items (each with a `planting` and `harvest` COG asset) are indexed by the collection's STAC-GeoParquet asset (`items.parquet`); query that rather than enumerating item links.

## Browse by year

- [**2024 composites**](./2024/) — per-tile planting + harvest COGs, a global Zarr mosaic, and a STAC-GeoParquet item index.
- [**2025 composites**](./2025/)

Each year is a STAC Collection; see its `collection.json` / `README.md` for the assets and access snippets. Source imagery: [Sentinel-2 L2A](https://sentinels.copernicus.eu/web/sentinel/missions/sentinel-2) (ESA / Copernicus). License: CC-BY-4.0.
