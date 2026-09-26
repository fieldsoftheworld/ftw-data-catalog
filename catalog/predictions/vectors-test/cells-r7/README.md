# Fields 2025 — A5 r7 cell aggregates (test)

Single `cells` layer, every A5 resolution-7 cell verbatim at z0–8 — nothing is
dropped at low zooms, it is summarized. Per-cell properties:

| property | meaning |
|---|---|
| `count` | number of 2025 predicted fields in the cell |
| `area_ha` | total field area, whole hectares |
| `avg_confidence` | mean model confidence, 1dp (null where the source has none) |
| `pct_covered` | 100 × field area / cell area; boundary fields count fully in their home cell, so isolated values can exceed 100 |

The same aggregate is published as GeoParquet (`parquet` asset; adds the
`a5_cell` id) — queryable directly with DuckDB or GeoPandas. Styles: field
**count** (log ramp, the default), **coverage**, **average field size**, and
model **confidence** (gray = outside the modeled-confidence coverage).

Input: the 2025 subset of the FTW PRUE predictions with >350 km² artifact
polygons excluded, pre-dedupe (boundary-straddling fields are still
double-counted — the production build stages deduplicated inputs). The raw
polygons live in the [vectors collection](../../vectors/collection.json).

CC-BY-4.0, as the parent catalog.
