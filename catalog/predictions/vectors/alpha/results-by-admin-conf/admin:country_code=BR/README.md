# Brazil — field boundary predictions

Field-boundary predictions for Brazil, split into 45 admin-subdivision partitions. Part of [Fields of the World](https://fieldsofthe.world) — agricultural field boundaries delineated by the PRUE model from Sentinel-2 imagery. A GeoParquet vector dataset is derived from the [prediction Zarr](https://data.source.coop/ftw/global-data/predictions/zarr/collection.json) by thresholding the softmax outputs for [non_field_background, field, field_boundaries] at 0.5 and polygonizing.

## Country-wide tiles

[`BR.pmtiles`](./BR.pmtiles) (7.5 GB) renders the whole country in one archive:
A5 grid-cell aggregates at zooms 0–8 (`aggregate` layer — resolution 5 then 8, with per-cell
`count`, `sum_area`, `avg_area`, `max_area`, `avg_perimeter`, `count_2024`/`count_2025` and
per-subdivision counts) handing over to the individual field polygons at zooms 9–13
(`features` layer). [`BR.style.json`](./BR.style.json) is a ready-made MapLibre style for it.
Built with [geoparquet-io](https://github.com/geoparquet-io/geoparquet-io) A5 aggregation and
[tylertoo](https://github.com/geoparquet-io/tylertoo) tiling; per-state archives below remain the
full-detail 2024/2025 layers.

## License

Released under **CC-BY-4.0**.

## Provenance

Part of [Fields of the World](https://fieldsofthe.world); field-boundary predictions from the PRUE model over global Sentinel-2 composites. Produced by the Taylor Geospatial Institute and collaborators, hosted on [Source Cooperative](https://source.coop/ftw/global-data).
