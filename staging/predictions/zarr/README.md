# FTW Global — Field Prediction Probabilities (Zarr)

Per-pixel class probabilities from the **PRUE model**
([wherobots/prue-pt2](https://huggingface.co/wherobots/prue-pt2)), run over the FTW
global Sentinel-2 feature mosaics, as a single cloud-native **Zarr V3** datacube. Part
of [Fields of the World](https://fieldsofthe.world); accompanying paper:
<https://aka.ms/ftw-global-paper>.

## What's here

A single store: `…/predictions/zarr/alpha/global.zarr`, with dimensions
`(time, band, y, x)`:

| Dim | Size | Values |
|---|---|---|
| `time` | 2 | 2024, 2025 (CF: *days since 2024-01-01*) |
| `band` | 3 | `non_field_background`, `field`, `field_boundaries` (softmax probabilities) |
| `y` | 1,566,049 | latitude, ~10 m (`8.983119e-5°`), 83.748345 → −56.9317 |
| `x` | 4,007,517 | longitude, ~10 m, −180 → 180 |

- **`variables`** — float32 softmax probability per class, shape `(2, 3, 1566049, 4007517)`,
  chunked `(1, 3, 8192, 8192)`, NaN fill. CRS **EPSG:4326** (WGS84), CF-1.8.
- Shares the **exact grid** of the `features/zarr` mosaic, so features and predictions
  are directly **stackable**.
- The `vectors` (field-boundary polygons) and `confidence` (raster) collections are
  **derived** from these probabilities.

## Status — not yet web-viewable

This is a GeoZarr-style store (CF-1.8 plus the emerging Zarr `proj:` / `spatial:`
geo-conventions), but it **does not yet implement multiscales / overviews**, so it
cannot be served as map tiles yet. That work is **in progress**. For now, consume it
analytically with xarray/Zarr.

## Using the data

```python
import xarray as xr
import rasterix

predictions = xr.open_zarr(
    "https://data.source.coop/ftw/global-data/predictions/zarr/alpha/global.zarr"
).pipe(rasterix.assign_index)

# field probability for 2024 over a small window (lazy; only needed chunks load)
field_2024 = predictions["variables"].sel(time="2024-01-01", band="field")
aoi = field_2024.sel(x=slice(2.0, 3.0), y=slice(48.5, 47.5))  # Beauce, France
print(aoi.shape)
```

Features and predictions can be opened side-by-side (same grid) to inspect inputs vs.
outputs.

## License

CC-BY-4.0. Produced by the Taylor Geospatial Institute and the Microsoft AI for Good
Research Lab.
