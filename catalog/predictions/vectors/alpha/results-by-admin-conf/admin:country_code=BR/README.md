# Brazil — field boundary predictions

Field-boundary predictions for Brazil, split into 45 admin-subdivision partitions. Part of [Fields of the World](https://fieldsofthe.world) — agricultural field boundaries delineated by the PRUE model from Sentinel-2 imagery. A GeoParquet vector dataset is derived from the [prediction Zarr](https://data.source.coop/ftw/global-data/predictions/zarr/collection.json) by thresholding the softmax outputs for [non_field_background, field, field_boundaries] at 0.5 and polygonizing.

## License

Released under **CC-BY-4.0**.

## Provenance

Part of [Fields of the World](https://fieldsofthe.world); field-boundary predictions from the PRUE model over global Sentinel-2 composites. Produced by the Taylor Geospatial Institute and collaborators, hosted on [Source Cooperative](https://source.coop/ftw/global-data).
