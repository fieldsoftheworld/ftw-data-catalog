# Field boundary tiles 2025 (test)

**Test collection** — two candidate single-archive renderings of the 2025
[Fields of the World](https://fieldsofthe.world) PRUE field-boundary predictions
(~600M polygons), evaluating a replacement for the current global PMTiles. Built with
[geoparquet-io](https://github.com/geoparquet-io/geoparquet-io) (A5 aggregation) and
[tylertoo](https://github.com/geoparquet-io/tylertoo) (tiling).

## The two archives

- **`fields-2025-aggregate.pmtiles`** — A5 grid-cell aggregates at low zooms
  (`cells` layer: resolution 5 at z0–5, resolution 8 from z6; per-cell `count`,
  `sum_area`, `avg_area`, `max_area`, `avg_confidence`), handing over to the
  **unthinned** field polygons (`fields` layer, 2 MB per-tile cap). Cell rollups are
  exact sums over every field — nothing is dropped at low zooms, it is summarized.
- **`fields-2025-thinned.pmtiles`** — the raw field polygons through tylertoo's
  standard generalization ladder from z0 (density thinning + simplification +
  500 KB tile cap), the conventional approach for comparison.

## Styles

Aggregate archive: field **count** (default), field **coverage** (share of each cell
covered by fields — A5 cells are equal-area, so `sum_area` divides by a per-resolution
constant), **average** and **largest** field size, and model **confidence** (gray =
outside the modeled-confidence coverage). Thinned archive: plain boundaries and
per-field confidence.

Field properties on `fields` layers: `area` (m²), `confidence` (0–100, sparse),
`country`, `state`.

## Data assets

The A5 cell aggregates behind the low zooms are published here as GeoParquet:
`cells_r8.parquet` (resolution 8, the z6+ cells) and `cells_r5.parquet` (resolution 5,
the z0–5 rollup) — queryable directly with DuckDB or GeoPandas. The raw field polygons
live in the [vectors collection](../vectors/collection.json). If this approach works
well, this becomes the main tiles product.

## License

CC-BY-4.0, as the parent catalog.
