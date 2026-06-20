<div style="display:flex; gap:16px; align-items:center;">
  <a href="https://fieldsofthe.world/">
    <img src="https://data.source.coop/ftw/global-data/docs/ftw_hero.svg" alt="Fields of the World" width="100%" />
  </a>
</div>

# Fields of the World — Global

The first global, wall-to-wall agricultural field-boundary dataset at 10 m resolution:
**3.17 billion field polygons across 241 countries and territories** for 2024–2025, produced by
applying the [PRUE field-boundary segmentation model](https://huggingface.co/wherobots/prue-pt2)
(a U-Net with an EfficientNet-B7 encoder, trained on the Fields of The World benchmark) to
cloud-free Sentinel-2 mosaics. Published openly under CC-BY-4.0 by Taylor Geospatial and
collaborators (Microsoft AI for Good, ASU, WashU in St. Louis, Oregon State, Clark).

Paper: Robinson et al. 2026, *The first global agricultural field boundary map at 10 m resolution*
([arXiv:2605.11055](https://arxiv.org/abs/2605.11055)).

## Explore this catalog

- **STAC catalog (root):** <https://data.source.coop/ftw/global-data/catalog.json>
- **Browse interactively:** [Portolan browser](https://browser.portolan-sdi.org/#/external/data.source.coop/ftw/global-data/catalog.json)
- **For AI agents:** [`llms.txt`](https://data.source.coop/ftw/global-data/llms.txt) — a machine-readable
  description of the whole dataset. Point [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
  or [Gemini CLI](https://github.com/google-gemini/gemini-cli) at it and ask it to query the data,
  build interactive maps, or generate charts. Each collection also has its own `llms.txt`.
- **Source repository:** <https://github.com/fieldsoftheworld/ftw-data-catalog>

Storage: the public URL base `https://data.source.coop/ftw/global-data/` is physically backed by
`s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data/` (anonymous read).

## Collections

| Collection | Format | Description |
|---|---|---|
| [Prediction Confidence & Quality (500 m)](https://data.source.coop/ftw/global-data/predictions/confidence/collection.json) | COG | Global 500 m rasters quantifying where the field predictions can be trusted ([llms.txt](https://data.source.coop/ftw/global-data/predictions/confidence/llms.txt)) |

*More products — vector field boundaries (fiboa GeoParquet + PMTiles), prediction & feature Zarr
stacks, and Sentinel-2 composites (COG) — are already on Source Cooperative and are being added to
the STAC catalog incrementally (see [Data products](#data-products) below).*

## Key facts

- 3.17 billion field polygons (1.62 B in 2024, 1.55 B in 2025); 241 countries/territories; 10 m resolution.
- Model: PRUE (U-Net / EfficientNet-B7), trained on the CC-BY subset of Fields of The World (24 countries).
- A field here is a *remote-sensing field unit* (a connected component of predicted field-interior
  pixels), **not** a cadastral/legal parcel. This is not a land-tenure product.
- Outputs are fiboa-compliant GeoParquet (vectors) and Cloud-Optimized GeoTIFFs (rasters).
- Validation: mean pixel-level recall 0.85 over 24 countries (14 > 0.90); confidence-model LOCO mean AUC 0.842.

## Data products

All files are anonymous-read on Source Cooperative and work directly over HTTP — no account or API key.

### Prediction confidence & quality (500 m) — in the STAC catalog

Global 500 m rasters quantifying where the 10 m field predictions can be trusted (confidence,
field/boundary density, entropy, cropland consensus, precision/recall). Read a window of the
confidence COG — only the needed bytes are fetched:

```python
import rasterio
from rasterio.windows import from_bounds

url = "https://data.source.coop/ftw/global-data/predictions/confidence/confidence/prue_v1_confidence_global.tif"
with rasterio.open(url) as ds:
    conf = ds.read(1, window=from_bounds(2.0, 47.5, 3.0, 48.5, ds.transform), masked=True)
```

Or load the whole collection lazily as an xarray stack:

```python
import pystac, odc.stac
col = pystac.Collection.from_file(
    "https://data.source.coop/ftw/global-data/predictions/confidence/collection.json")
ds = odc.stac.load(list(col.get_items()), chunks={})
```

### Features — Sentinel-2 composites (COG & Zarr)

Planting/harvest median composites over ~5–10 Sentinel-2 scenes, as COGs and a single EPSG:4326
Zarr V3 mosaic at `8.983119e-5°` (~10 m at the equator).

```python
import rasterix
import xarray as xr

features = xr.open_zarr(
    "s3://us-west-2.opendata.source.coop/ftw/global-data/features/zarr/alpha/global.zarr"
).pipe(rasterix.assign_index)
```

### Predictions — Zarr, GeoParquet, PMTiles

The PRUE model runs over the feature Zarr to produce a prediction Zarr with bands
`[non_field_background, field, field_boundaries]` (same grid, so they stack). Vectors are derived by
thresholding at `0.5` and polygonizing into fiboa GeoParquet v1.1.0 (~8.2 B rows, ~629 GB) and a
PMTiles archive for web maps. Query the vectors with DuckDB:

```python
import duckdb

con = duckdb.connect()
con.execute("INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs;")
con.execute("""
SELECT geometry, time, label, bbox
FROM read_parquet('s3://us-west-2.opendata.source.coop/ftw/global-data/predictions/vectors/alpha/results/*.parquet')
WHERE label = 'field'
  AND struct_extract(bbox, 'xmax') >= -93.71488
  AND struct_extract(bbox, 'xmin') <= -93.06492
  AND struct_extract(bbox, 'ymax') >=  41.78201
  AND struct_extract(bbox, 'ymin') <=  42.09459
""").df()
```

## Caveats

- Temporal year (2025) is inferred from the paper and pending author confirmation.
- The field-density `_filtered` variant's exact threshold/method is pending author confirmation.
- The confidence layer is conservative outside the FTW training distribution (e.g. smallholder
  systems): real fields there may receive low confidence. Prefer the unfiltered density + continuous
  confidence over the default 0.4 threshold in such regions.
- Polygons are remote-sensing field units, not legal parcels; one parcel may map to many polygons or none.

## License

CC-BY-4.0.

## Cite

Robinson, C., Muhawenayo, G., Khanal, S., Fang, Z., Corley, I., Tárano, A. M., Estes, L., Marcus, J.,
Jacobs, N., Kerner, H., Becker-Reshef, I., & Lavista Ferres, J. M. (2026). *The first global
agricultural field boundary map at 10 m resolution.* arXiv:2605.11055.

## Contact

`isaac.corley@taylorgeospatial.org`

---

*Published with [Portolan](https://portolan-sdi.org).*
