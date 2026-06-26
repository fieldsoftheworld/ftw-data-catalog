<div style="display:flex; gap:16px; align-items:center;">
  <a href="https://fieldsofthe.world/">
    <img src="https://data.source.coop/ftw/global-data/docs/ftw_hero.svg" alt="Fields of the World" width="100%" />
  </a>
</div>

# Fields of the World — Global

The first global, wall-to-wall agricultural field-boundary dataset at 10 m resolution:
**~1.6 billion field polygons per year** — **1.63 billion for 2024** and **1.58 billion for 2025**
(~3.2 billion polygon records across both years) — spanning **195 countries and territories**,
produced by applying the [PRUE field-boundary segmentation model](https://huggingface.co/wherobots/prue-pt2)
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
| [Field Boundary Predictions (GeoParquet)](https://data.source.coop/ftw/global-data/predictions/vectors/collection.json) | GeoParquet + PMTiles | ~3.2 B field-boundary polygons (2024 & 2025) in the fiboa/vecorel schema, each with a per-polygon `confidence` score (0–100). One partition per country (195 countries, 574 files; large countries split by admin subdivision), plus global & per-country PMTiles and MapLibre styles for web maps. ([llms.txt](https://data.source.coop/ftw/global-data/predictions/vectors/llms.txt)) |
| [Prediction Confidence & Quality (500 m)](https://data.source.coop/ftw/global-data/predictions/confidence/collection.json) | COG | Global 500 m rasters showing where the 10 m predictions can be trusted — confidence, entropy, field/boundary density, cropland consensus, precision/recall. ([llms.txt](https://data.source.coop/ftw/global-data/predictions/confidence/llms.txt)) |
| [Sentinel-2 Planting & Harvest Composites](https://data.source.coop/ftw/global-data/features/catalog.json) | COG + Zarr | The model-input Sentinel-2 median composites (10 m), per year: ~22.7 k tiles/year, each with a planting and a harvest COG, plus a global EPSG:4326 Zarr mosaic and a STAC-GeoParquet item index. |
| [Field Prediction Probabilities (Zarr)](https://data.source.coop/ftw/global-data/predictions/zarr/collection.json) | Zarr | The raw PRUE softmax probabilities (non-field / field / field-boundary) the vectors are thresholded from. |

## Key facts

- **1.63 billion** field polygons for **2024** and **1.58 billion** for **2025** (~3.2 B across both
  years), over **195 countries** and **574 admin partitions**, at 10 m resolution. Each year is an
  independent global prediction, so the per-year count (~1.6 B) — not the both-years sum — is the
  number of distinct fields in a year.
- Every vector polygon carries a **`confidence` score (0–100)**, sampled at the polygon's
  representative point from the 500 m PRUE confidence layer and rescaled (`raw / 0.578178 × 100`,
  the same scaling the [FTW inference app](https://github.com/fieldsoftheworld/ftw-inference-app) uses).
- Model: **PRUE** (U-Net / EfficientNet-B7), trained on the CC-BY subset of the
  [Fields of The World benchmark](https://source.coop/kerner-lab/fields-of-the-world) (24 countries).
- A field here is a *remote-sensing field unit* (a connected component of predicted field-interior
  pixels), **not** a cadastral/legal parcel. This is not a land-tenure product.
- Outputs are fiboa/vecorel-compliant GeoParquet (vectors) and Cloud-Optimized GeoTIFFs / Zarr (rasters).
- Validation (paper): mean pixel-level recall 0.85 over 24 countries (14 > 0.90); confidence-model
  leave-one-country-out mean AUC 0.842.

## Data products

All files are anonymous-read on Source Cooperative and work directly over HTTP — no account or API key.

### Field boundary predictions (GeoParquet + PMTiles)

The PRUE model runs over the Sentinel-2 feature composites to produce per-pixel field probabilities;
vectors are derived by thresholding and polygonizing into **fiboa/vecorel GeoParquet v1.1.0**, then
partitioned **one file per country** (195 countries / 574 files, ~210 GB; the nine largest countries —
e.g. the US, India, China, Brazil — are split by admin subdivision) and enriched with a per-polygon
**`confidence`** column (0–100). Each polygon also carries `metrics:area`, `metrics:perimeter`, and a
`determination:datetime` (2024 or 2025). Query a country partition directly with DuckDB — only the
needed bytes are fetched:

```python
import duckdb

con = duckdb.connect()
con.execute("INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs;")
base = "s3://us-west-2.opendata.source.coop/ftw/global-data/predictions/vectors/alpha/results-by-admin-conf"
con.execute(f"""
SELECT id, EXTRACT(year FROM "determination:datetime") AS year,
       confidence, "metrics:area" AS area_m2, geometry
FROM read_parquet('{base}/admin:country_code=FR/France.parquet')
WHERE confidence >= 80          -- high-confidence fields only
""").df()
```

For web maps, the collection also exposes global PMTiles (a 2024 and a 2025 layer) and per-country
PMTiles, with MapLibre styles for plain green boundaries and for shading each field by its confidence.

### Prediction confidence & quality (500 m)

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

Planting- and harvest-season median composites over ~5–10 quality-masked Sentinel-2 scenes (the
model's inputs), as per-tile COGs (~22.7 k tiles/year) and a single global EPSG:4326 Zarr V3 mosaic
at `8.983119e-5°` (~10 m at the equator):

```python
import rasterix
import xarray as xr

features = xr.open_zarr(
    "s3://us-west-2.opendata.source.coop/ftw/global-data/features/zarr/alpha/global.zarr"
).pipe(rasterix.assign_index)
```

### Prediction probabilities (Zarr)

The raw PRUE softmax bands `[non_field_background, field, field_boundaries]` on the same grid as the
features (so they stack), from which the vectors are thresholded at `0.5` and polygonized.

## Caveats

- The field-density `_filtered` variant's exact threshold/method is pending author confirmation.
- The confidence layer is conservative outside the FTW training distribution (e.g. smallholder
  systems): real fields there may receive low confidence. Prefer the unfiltered density + continuous
  confidence over a hard threshold in such regions.
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
