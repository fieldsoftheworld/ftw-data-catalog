# Fields of the World — Global

Global agricultural field boundaries and prediction-quality layers at 10 m resolution,
produced by applying the PRUE field-boundary segmentation model to global Sentinel-2
mosaics ([Robinson et al. 2026](https://arxiv.org/abs/2605.11055)). Published openly
under CC-BY-4.0 by Taylor Geospatial and collaborators.

This catalog (STAC 1.1.0 / Portolan) describes:

- **predictions/confidence** — 500 m prediction confidence & quality layers (COG)
- **predictions/vectors** — field-boundary polygons (GeoParquet) + PMTiles
- **predictions/zarr** — prediction probabilities (Zarr)
- **features/cogs** — Sentinel-2 planting/harvest composites (COG)
- **features/zarr** — Sentinel-2 feature mosaic (Zarr)

Data is hosted on [Source Cooperative](https://source.coop/ftw/global-data/). Catalog
metadata is maintained as code at
[github.com/fieldsoftheworld/ftw-portolan](https://github.com/fieldsoftheworld/ftw-portolan)
— corrections and additions welcome via pull request.
