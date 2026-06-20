# FTW Global — Field Boundary Predictions (alpha)

Global agricultural **field-boundary polygons** predicted by the PRUE model
([ftw-baselines](https://github.com/fieldsoftheworld/ftw-baselines)), published as
cloud-native **GeoParquet partitioned by country** with per-country **PMTiles** for
web visualization. Part of [Fields of the World](https://fieldsofthe.world).

## What's here

- **GeoParquet, partitioned by country** under
  `alpha/results-by-admin-conf/admin:country_code=<CC>/`. Query the whole dataset
  with the Portolan glob asset:
  `alpha/results-by-admin-conf/admin:country_code=*/*.parquet`.
- **One STAC item per parquet partition** (id = the parquet filename). Large
  countries are split by admin subdivision and grouped under a per-country
  sub-catalog.
- **Per-country PMTiles** alongside each parquet (`<name>.pmtiles`).
- **Two collection-level PMTiles** for the global web view:
  - `ftw-global-fields-2025.pmtiles` — **default display** (2025).
  - `2024_with_confidence.pmtiles` — 2024.
- **MapLibre styles** in `styles/` that color fields by confidence (red→green,
  0–100) with the recommended `>= 69` reliability filter and a legend.

## The `confidence` column

Each polygon carries a **`confidence`** value on a **0–100** scale. It is derived,
not part of the raw model vector output:

- Sampled at each field's **point-on-surface** from the 500 m **PRUE confidence
  COG** (the [`predictions/confidence`](../confidence/) collection).
- Rescaled **`raw / 0.578178 * 100`** and clamped to 100 — i.e. `0.578178` is
  treated as 100%, matching the [FTW inference app](https://fieldsofthe.world/ftw-inference-app/)
  legend (raw `0.404`→70, `0.463`→80, `0.521`→90, `0.578`→100). Cells with no data
  become null.
- This centroid sample is the closest single value to the app's `confidence_mean`
  (for the common case of fields smaller than a 500 m cell they are identical).
- **Recommended default filter:** `confidence >= 69` (raw 0.4). Confidence reflects
  cell-level model reliability, **not** individual-polygon geometric accuracy.

It is computed by the scripts in this repo:
[`add_confidence.py`](https://github.com/fieldsoftheworld/ftw-portolan/blob/main/scripts/add_confidence.py),
[`process_partition.sh`](https://github.com/fieldsoftheworld/ftw-portolan/blob/main/scripts/process_partition.sh),
[`run_rails.sh`](https://github.com/fieldsoftheworld/ftw-portolan/blob/main/scripts/run_rails.sh),
[`make_pmtiles.py`](https://github.com/fieldsoftheworld/ftw-portolan/blob/main/scripts/make_pmtiles.py).

## Schema

Field definitions use the wording of the [fiboa core specification](https://github.com/fiboa/specification/blob/main/core/README.md)
and the vecorel [geometry-metrics](https://github.com/vecorel/geometry-metrics-extension)
and [administrative-division](https://github.com/vecorel/administrative-division-extension)
extensions (also machine-readable in the collection's `table:columns`):

| Field | Description |
|---|---|
| `id` | An identifier for the field. Must be unique per collection. |
| `geometry` | A geometry that reflects the footprint of the field, usually a Polygon. Default CRS is WGS84. |
| `bbox` | The bounding box of the field. |
| `metrics:area` | Area of the field, in square meters (m²). Must be > 0. |
| `metrics:perimeter` | Perimeter of the field, in meters (m). Must be > 0. |
| `determination:datetime` | The last timestamp at which the field did exist and was observed, in the UTC timezone. |
| `determination:method` | The boundary creation method (one of: manual, surveyed, driven, auto-operation, auto-imagery, unknown). |
| `admin:country_code` | ISO 3166-1 alpha-2 country code (aka admin0). Two-letter country code for the country that contains the field. |
| `admin:subdivision_code` | ISO 3166-2 code for the principal subdivision (e.g. province or state, aka admin1) of a country that contains the field. Only the subdivision part of the code is stored. |
| **`confidence`** | **Derived** (not in the upstream model output). Modeled PRUE confidence on a 0–100 scale — see above. |

The per-country PMTiles split fields into **two layers by prediction year — `2024` and
`2025`** — derived from `determination:datetime`.

## Using the data

```python
import duckdb
con = duckdb.connect(); con.execute("INSTALL spatial; LOAD spatial;")
base = "https://data.source.coop/ftw/global-data/predictions/vectors/alpha/results-by-admin-conf"
# one country
con.sql(f"SELECT count(*), avg(confidence) FROM read_parquet('{base}/admin:country_code=FR/France.parquet')").show()
# whole dataset via the glob, only confident fields
con.sql(f"SELECT count(*) FROM read_parquet('{base}/admin:country_code=*/*.parquet') WHERE confidence >= 69").show()
```

## License

CC-BY-4.0. Produced by the Taylor Geospatial Institute and the Microsoft AI for
Good Research Lab.
