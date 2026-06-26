# FTW Global — Sentinel-2 Planting & Harvest Composites — Zarr mosaic (2024 & 2025)

![Sentinel-2 composite preview](https://data.source.coop/ftw/global-data/features/thumbnail.png)

The FTW Sentinel-2 planting/harvest composites as a single global EPSG:4326 **Zarr mosaic** (Zarr V3, ~10 m), with a `time` dimension over 2024 & 2025 — the **same data** as the per-tile COG collections ([COGs 2024](https://source.coop/ftw/global-data/features/2024), [COGs 2025](https://source.coop/ftw/global-data/features/2025)), in datacube form. Bands B02/B03/B04/B08 + N_VALID_PIXELS; the model-input features for the FTW [field-boundary predictions](https://source.coop/ftw/global-data/predictions).

## Access

```python
import xarray as xr, rasterix
ds = xr.open_zarr("https://data.source.coop/ftw/global-data/features/zarr/alpha/global.zarr").pipe(rasterix.assign_index)
```

This is a GeoZarr that does not yet implement multiscales, so it is not yet directly web-tileable (work in progress).

## License

CC-BY-4.0. Sentinel-2 imagery © Copernicus/ESA; composites by the Taylor Geospatial Institute and Microsoft AI for Good Research Lab.
