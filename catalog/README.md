<div style="display:flex; gap:16px; align-items:center;">
  <a href="https://fieldsofthe.world/">
    <img src="https://data.source.coop/ftw/global-data/docs/ftw_hero.svg" alt="Fields of the World" width="100%" />
  </a>
</div>

# Global Fields of The World (FTW)

Global mosaics and agricultural field predictions for 2024 and 2025, from Taylor Geospatial.

Accompanying paper: <https://aka.ms/ftw-global-paper>

## Data Products

- `features` (version `alpha`)
    - Planting and harvest median composites over 5–10 Sentinel-2 scenes.
    - Distributed as COGs and as a single `EPSG:4326` Zarr V3 mosaic.
- `predictions` (version `alpha`)
    - Outputs of the [PRUE model](https://huggingface.co/wherobots/prue-pt2) run on the features above.
    - Distributed as Zarr V3, GeoParquet v1.1.0 (with covering), and PMTiles.

---

## Features (COGs)

**Location**: `s3://us-west-2.opendata.source.coop/ftw/global-data/features/cogs/alpha/`.

Features are defined by selecting DOY ranges as planting/harvest heuristics and computing the median
of masked pixels across ~5–10 scenes. See [Appendix](#appendix) for the heuristics and masking details.

- `s2med_harvest/*`:
    - Contains bands `["B02", "B03", "B04", "B08", "N_VALID_PIXELS"]`
    - Each band is the median over the respective Sentinel-2 scenes.
    - `N_VALID_PIXELS` is the number of valid scenes after quality-flag masking.

- `s2med_planting/*`:
    - Contains bands `["B02", "B03", "B04", "B08", "N_VALID_PIXELS"]`
    - Each band is the median over the respective Sentinel-2 scenes.
    - `N_VALID_PIXELS` is the number of valid scenes after quality-flag masking.

- `index.parquet`:
```python
import geopandas as gpd

gpd.read_parquet("s3://us-west-2.opendata.source.coop/ftw/global-data/features/cogs/alpha/index.parquet")
```

<img src="https://data.source.coop/ftw/global-data/docs/cog_index.png" alt="cog index" width="80%" />
<img src="https://data.source.coop/ftw/global-data/docs/cog_explore.png" alt="cog explore" width="80%" />

--- 

## Features (Zarr)

**Location**: `s3://us-west-2.opendata.source.coop/ftw/global-data/features/zarr/alpha/global.zarr`

All feature COGs are reprojected and resampled to `EPSG:4326` at `8.983119e-5°` (~10 m at the equator)
using GDAL cubic resampling, producing a single Zarr mosaic with dimensions `(time, band, y, x)`.

```python
import rasterix
import xarray as xr

features = xr.open_zarr(
    "s3://us-west-2.opendata.source.coop/ftw/global-data/features/zarr/alpha/global.zarr"
).pipe(rasterix.assign_index)
features
```

<img src="https://data.source.coop/ftw/global-data/docs/features_mosaic.png" alt="features mosaic" width="80%" />

--- 

## Predictions (Zarr)

**Location**: `s3://us-west-2.opendata.source.coop/ftw/global-data/predictions/zarr/alpha/global.zarr`

The PRUE model is run over `features/zarr/alpha/global.zarr` to produce a Zarr dataset with bands
`[non_field_background, field, field_boundaries]`. Feature and prediction Zarrs share the same grid,
so they are stackable.

```python
predictions = xr.open_zarr(
    "s3://us-west-2.opendata.source.coop/ftw/global-data/predictions/zarr/alpha/global.zarr"
).pipe(rasterix.assign_index)
predictions
```

<img src="https://data.source.coop/ftw/global-data/docs/prediction_mosaic.png" alt="prediction mosaic" width="80%" />

### Features and Predictions

We can inspect inputs and outputs side-by-side since they are stackable. This enables researchers
to validate inputs to better understand their influence in model outputs.

```python
planting_bands = ["s2med_planting:B04", "s2med_planting:B03", "s2med_planting:B02"]
harvest_bands = ["s2med_harvest:B04", "s2med_harvest:B03", "s2med_harvest:B02"]
xmin, ymin, xmax, ymax = -93.75, 41.5, -93.5, 41.75
year = "2024"

fig, axs = plt.subplots(1, 3, figsize=(15, 5))

features["variables"].sel(
    band=planting_bands, time=year, y=slice(ymax, ymin), x=slice(xmin, xmax)
)[0].plot.imshow(robust=True, ax=axs[0])
axs[0].axis("off")
axs[0].set_title("Planting")

features["variables"].sel(
    band=harvest_bands, time=year, y=slice(ymax, ymin), x=slice(xmin, xmax)
)[0].plot.imshow(robust=True, ax=axs[1])
axs[1].axis("off")
axs[1].set_title("Harvest")

predictions["variables"].sel(band="field", time=year, y=slice(ymax, ymin), x=slice(xmin, xmax))[
    0
].plot.imshow(ax=axs[2])
axs[2].axis("off")
axs[2].set_title("Predictions")

plt.tight_layout()
plt.show()
```

<img src="https://data.source.coop/ftw/global-data/docs/comparison.png" alt="comparison" width="100%" />

---

## Predictions (GeoParquet)

**Location**: `s3://us-west-2.opendata.source.coop/ftw/global-data/predictions/vectors/alpha/results/`

A GeoParquet vector dataset is derived from the prediction Zarr by thresholding the softmax outputs
for `[non_field_background, field, field_boundaries]` at `0.5` and polygonizing.

Files follow the [GeoParquet v1.1.0 spec](https://geoparquet.org/releases/v1.1.0): ~8.2B rows across
1,001 files, ~629 GB on S3, with the following schema:

```bash
┌─────────────┬────────────────────────────────────────────────────────────┬─────────┬─────────┬─────────┬─────────┐
│ column_name │                        column_type                         │  null   │   key   │ default │  extra  │
│   varchar   │                          varchar                           │ varchar │ varchar │ varchar │ varchar │
├─────────────┼────────────────────────────────────────────────────────────┼─────────┼─────────┼─────────┼─────────┤
│ geometry    │ GEOMETRY                                                   │ YES     │ NULL    │ NULL    │ NULL    │
│ time        │ TIMESTAMP                                                  │ YES     │ NULL    │ NULL    │ NULL    │
│ label       │ VARCHAR                                                    │ YES     │ NULL    │ NULL    │ NULL    │
│ bbox        │ STRUCT(xmax DOUBLE, xmin DOUBLE, ymax DOUBLE, ymin DOUBLE) │ YES     │ NULL    │ NULL    │ NULL    │
└─────────────┴────────────────────────────────────────────────────────────┴─────────┴─────────┴─────────┴─────────┘
```

Query with DuckDB and visualize with Lonboard:

```python
import duckdb
from lonboard import Map, PolygonLayer
from lonboard.basemap import CartoStyle

con = duckdb.connect()
con.execute("INSTALL spatial; LOAD spatial;")
con.execute("INSTALL httpfs; LOAD httpfs;")

q = """
SELECT geometry AS geometry, time, label, bbox
FROM read_parquet('s3://us-west-2.opendata.source.coop/ftw/global-data/predictions/vectors/alpha/results/*.parquet')
WHERE label = 'field'
  AND struct_extract(bbox, 'xmax') >= -93.71488
  AND struct_extract(bbox, 'xmin') <= -93.06492
  AND struct_extract(bbox, 'ymax') >= 41.78201
  AND struct_extract(bbox, 'ymin') <= 42.09459
"""

layer = PolygonLayer.from_duckdb(q, con, get_fill_color=[0, 0, 139])
m = Map(layer, height=700, basemap_style=CartoStyle.Positron)
m
```

<img src="https://data.source.coop/ftw/global-data/docs/lonboard_gpq_example.png" alt="gpq example" width="100%" />

---

## Predictions (PMTiles)

**Location**: `s3://us-west-2.opendata.source.coop/ftw/global-data/predictions/vectors/alpha/global.pmtiles`

[PMTiles](https://guide.cloudnativegeo.org/pmtiles/intro.html) built from the GeoParquet above for
scalable browser-side visualization.

```python
import leafmap.foliumap as leafmap

url = "s3://us-west-2.opendata.source.coop/ftw/global-data/predictions/vectors/alpha/global.pmtiles"

metadata = leafmap.pmtiles_metadata(url)
m = leafmap.Map(center=[0, 20], zoom=2, height="800px")
m.add_basemap("SATELLITE", visible=True)
style = leafmap.pmtiles_style(url, layers="field-2024-01-01 00:00:00", opacity=0.7)
m.add_pmtiles(url, style=style)
m
```

<img src="https://data.source.coop/ftw/global-data/docs/kenya_pmtile_view.png" alt="kenya view" width="100%" />

--- 

## Appendix

### Season Heuristics (`alpha`)

Relevant Sentinel-2 scenes are selected by acquisition DOY using the following functions:

```python
def tile_to_planting_season_heuristic_doy(point: Point) -> tuple[int, int]:
    lat = point.y
    abs_lat = abs(lat)
    if abs_lat > 45:
        start_doy, end_doy = (91, 151) if lat > 0 else (274, 334)  # Apr-May or Oct-Nov
    elif 20 < abs_lat <= 45:
        start_doy, end_doy = (60, 120) if lat > 0 else (244, 334)  # Mar-Apr or Sep-Nov
    elif 5 < abs_lat <= 20:
        start_doy, end_doy = (121, 212) if lat > 0 else (305, 365)  # May-Jul or Nov-Dec
    else:  # Equatorial
        start_doy, end_doy = (60, 121)  # Approx. Mar-Apr and Sep-Oct (simplified)
    return start_doy, end_doy


def tile_to_harvest_season_heuristic_doy(point: Point) -> tuple[int, int]:
    lat = point.y
    abs_lat = abs(lat)
    if abs_lat > 45:
        start_doy, end_doy = (244, 304) if lat > 0 else (60, 151)  # Sep-Oct or Mar-May
    elif 20 < abs_lat <= 45:
        start_doy, end_doy = (213, 304) if lat > 0 else (32, 120)  # Aug-Oct or Feb-Apr
    elif 5 < abs_lat <= 20:
        start_doy, end_doy = (274, 365) if lat > 0 else (91, 181)  # Oct-Dec or Apr-Jun
    else:  # Equatorial
        start_doy, end_doy = (182, 243)  # Approx. Jul-Aug and Jan-Feb (simplified)
    return start_doy, end_doy
```

### Sentinel-2 Source

All Sentinel-2 scenes were sourced from `s3://sentinel-cogs/sentinel-s2-l2a-cogs`.

### Sentinel-2 SCL Flags

Pixels with the following
[SCL](https://documentation.dataspace.copernicus.eu/Data/SentinelMissions/Sentinel-2.html#algorithm)
values are masked out before taking the median:

- 0: No Data
- 1: Saturated Defective
- 3: Cloud Shadow
- 7: Cloud Low Probability / Unclassified
- 8: Cloud Medium Probability
- 9: Cloud High Probability
- 10: Thin Cirrus

## License

CC-BY-4.0

## Contact

`isaac.corley@taylorgeospatial.org`

## Cite

If you use this dataset in your research please cite the following papers:

```bibtex
@inproceedings{kerner2025fields,
  title={Fields of the world: A machine learning benchmark dataset for global agricultural field boundary segmentation},
  author={Kerner, Hannah and Chaudhari, Snehal and Ghosh, Aninda and Robinson, Caleb and Ahmad, Adeel and Choi, Eddie and Jacobs, Nathan and Holmes, Chris and Mohr, Matthias and Dodhia, Rahul and others},
  booktitle={Proceedings of the AAAI Conference on Artificial Intelligence},
  volume={39},
  number={27},
  pages={28151--28159},
  year={2025}
}
```

```bibtex
@article{muhawenayo2026prue,
  title={PRUE: A Practical Recipe for Field Boundary Segmentation at Scale},
  author={Muhawenayo, Gedeon and Robinson, Caleb and Khanal, Subash and Fang, Zhanpei and Corley, Isaac and Wollam, Alexander and Gao, Tianyi and Strnad, Leonard and Avery, Ryan and Estes, Lyndon and others},
  journal={arXiv preprint arXiv:2603.27101},
  year={2026}
}
```

```bibtex
@article{corley2026fields,
  title={Fields of The World: A Field Guide for Extracting Agricultural Field Boundaries},
  author={Corley, Isaac and Kerner, Hannah and Robinson, Caleb and Marcus, Jennifer},
  journal={arXiv preprint arXiv:2602.08131},
  year={2026}
}
```
