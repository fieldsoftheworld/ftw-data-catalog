# Field boundary tiles 2025 (test)

**Test catalog** — candidate renderings of the 2025
[Fields of the World](https://fieldsofthe.world) PRUE field-boundary predictions
(1.58B polygons), evaluating a replacement for the current global PMTiles. Built with
[geoparquet-io](https://github.com/geoparquet-io/geoparquet-io) (A5 aggregation) and
[tylertoo](https://github.com/geoparquet-io/tylertoo) (tiling). One collection per
approach, so each can be previewed on its own:

| collection | what it shows |
|---|---|
| [`cells-r5`](./cells-r5/collection.json) | A5 resolution-5 cell aggregates (~33,200 km² cells), single verbatim layer z0–8 |
| [`cells-r7`](./cells-r7/collection.json) | A5 resolution-7 cell aggregates (~2,075 km² cells), single verbatim layer z0–8 |
| [`cells-r8`](./cells-r8/collection.json) | A5 resolution-8 cell aggregates (~519 km² cells), single verbatim layer z0–8 |
| [`fields-thinned`](./fields-thinned/collection.json) | Every field polygon, z0–13, tylertoo's generalization ladder (density thinning + simplification + tile-size cap) from z0 |

Each cells collection carries its PMTiles archive, the same aggregate as
GeoParquet (queryable directly with DuckDB or GeoPandas; adds the `a5_cell`
id), and four styles: field **count** (log ramp, the default), **coverage**,
**average field size**, and model **confidence** (gray = outside the
modeled-confidence coverage). The cells layer has per-cell `count`, `area_ha`
(total field area, hectares), `avg_confidence` (1dp; null in countries without
modeled confidence) and `pct_covered` (percent of the cell covered by fields —
A5 cells are equal-area; boundary fields count fully in their home cell, so
isolated values can exceed 100). Cell rollups are exact sums over every field —
nothing is dropped at low zooms, it is summarized.

The thinned collection carries the full-polygon archive with plain
**boundaries** (default), per-field **confidence**, and per-field **size**
styles. Field properties on its `fields` layer: `area` (m²), `confidence`
(0–100, sparse), `country`, `state`.

The raw field polygons live in the
[vectors collection](../vectors/collection.json).

## What lands next

The production per-year **handover archives** — a5 r7 cell aggregates at z0–8
switching to the actual field polygons at z9–13, one archive per year (2024 &
2025), built from deduplicated staging with the 350 km² artifact cutoff — will
be added as their own collection alongside these.

## Provenance notes

- Input: the 2025 subset of the `results-by-admin-conf` prediction partitions
  (year derived in UTC from `determination:datetime`).
- The cell aggregates exclude "fields" larger than 350 km²: the largest
  high-confidence real complex in the data is a 331 km² Russian grain block,
  while everything above 350 km² (498 features, 776k km² of mapped area) has
  the low-confidence Sahara-artifact signature.
- Known caveat: fields straddling admin subdivision boundaries are duplicated
  upstream (issue #9) and still double-counted in these test products; the
  production build stages deduplicated inputs.

## License

CC-BY-4.0, as the parent catalog.
