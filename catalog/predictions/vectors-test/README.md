# Field boundary tiles 2025 (test)

**Test collection** — candidate renderings of the 2025
[Fields of the World](https://fieldsofthe.world) PRUE field-boundary predictions
(1.58B polygons), evaluating a replacement for the current global PMTiles. Built with
[geoparquet-io](https://github.com/geoparquet-io/geoparquet-io) (A5 aggregation) and
[tylertoo](https://github.com/geoparquet-io/tylertoo) (tiling). Everything here is
for side-by-side evaluation before the production per-year archives are built.

## The archives

| file | what it shows |
|---|---|
| `fields-2025-thinned.pmtiles` | Every field polygon, z0–13, tylertoo's generalization ladder (density thinning + simplification + 500 KB cap) from z0 |
| `cells-2025-r5.pmtiles` | A5 resolution-5 cell aggregates (~33,200 km² cells), single verbatim layer z0–8 |
| `cells-2025-r7.pmtiles` | A5 resolution-7 cell aggregates (~2,075 km² cells), single verbatim layer z0–8 |
| `cells-2025-r8.pmtiles` | A5 resolution-8 cell aggregates (~519 km² cells), single verbatim layer z0–8 |

Each cells archive has one `cells` layer with per-cell `count`, `area_ha`
(total field area, hectares), `avg_confidence` (1dp; null in countries without
modeled confidence) and `pct_covered` (percent of the cell covered by fields —
A5 cells are equal-area; boundary fields count fully in their home cell, so
isolated values can exceed 100). Cell rollups are exact sums over every field —
nothing is dropped at low zooms, it is summarized.

## Styles

Per cells resolution (r5/r7/r8): field **count** (log ramp, r7 is the default
style), **coverage** (share of each cell covered by fields), **average field
size**, and model **confidence** (gray = outside the modeled-confidence
coverage). Thinned archive: plain **boundaries**, per-field **confidence**, and
per-field **size**.

Field properties on the `fields` layer: `area` (m²), `confidence` (0–100,
sparse), `country`, `state`.

## Data assets

The A5 cell aggregates are also published as GeoParquet — `cells_r5.parquet`,
`cells_r7.parquet`, `cells_r8.parquet` (same columns plus the `a5_cell` id) —
queryable directly with DuckDB or GeoPandas. The raw field polygons live in the
[vectors collection](../vectors/collection.json). If this approach works well,
this becomes the main tiles product.

## Provenance notes

- Input: the 2025 subset of the `results-by-admin-conf` prediction partitions
  (year derived in UTC from `determination:datetime`).
- The cell aggregates exclude "fields" larger than 350 km²: the largest
  high-confidence real complex in the data is a 331 km² Russian grain block,
  while everything above 350 km² (498 features, 776k km² of mapped area) has
  the low-confidence Sahara-artifact signature.
- Known caveat: fields straddling admin subdivision boundaries are duplicated
  upstream (issue #9) and still double-counted in these test aggregates; the
  production build stages deduplicated inputs.

## License

CC-BY-4.0, as the parent catalog.
