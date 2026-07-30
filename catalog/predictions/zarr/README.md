# FTW Global — Field Prediction Probabilities (Zarr)

Per-pixel class probabilities from the **PRUE model**
([wherobots/prue-pt2](https://huggingface.co/wherobots/prue-pt2)), run over the FTW
global Sentinel-2 feature mosaics, as a single cloud-native **Zarr V3** datacube. Part
of [Fields of the World](https://fieldsofthe.world); accompanying paper:
<https://aka.ms/ftw-global-paper>.

<img src="https://data.source.coop/ftw/global-data/docs/prediction_mosaic.png" width="600" alt="Prediction Zarr opened in xarray">

*The prediction Zarr opened in xarray (`xr.open_zarr`) — dimensions, bands, and chunking.*

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

## Multiscales

This is a GeoZarr-style store (CF-1.8 plus the emerging Zarr `proj:` / `spatial:`
geo-conventions) and it **implements multiscales**, so it can be read at any zoom and
tiled for web display as well as consumed analytically.

The root group declares a `multiscales` attribute against the **`WGS84Quad`** tile
matrix set, with **14 `average`-resampled levels**. Full resolution lives at the root
(`path: "."`); each overview is a sibling group named by its decimation factor:

| Level | Path | Shape (y, x) |
|---|---|---|
| 1× | `.` | 1,566,049 × 4,007,517 |
| 2× | `2x` | 783,025 × 2,003,759 |
| 4× | `4x` | 391,513 × 1,001,880 |
| … | … | … |
| 4096× | `4096x` | 383 × 979 |
| 8192× | `8192x` | 192 × 490 |

Every level is a complete group — same `(time, band, y, x)` layout, its own coordinate
arrays and `spatial:transform`. Open an overview directly by pointing `xr.open_zarr` at
its group:

```python
overview = xr.open_zarr(
    "https://data.source.coop/ftw/global-data/predictions/zarr/alpha/global.zarr",
    group="64x",
).pipe(rasterix.assign_index)
```

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
