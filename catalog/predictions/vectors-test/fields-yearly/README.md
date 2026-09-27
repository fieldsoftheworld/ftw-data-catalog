# Fields 2024 & 2025 — cells-to-fields handover (test)

The candidate production product: **one PMTiles archive per year** with a zoom
handover. At z0–8 you see A5 resolution-7 cell aggregates (~2,075 km² equal-area
cells), every cell verbatim — nothing is dropped at low zooms, it is summarized.
From z9 the archive switches to the **actual field polygons** through z13
(canonical zoom, verbatim; z9–12 lightly thinned).

| file | layers |
|---|---|
| `fields-2024.pmtiles` (115.5 GB) | `cells` z0–8 → `fields` z9–13, 1.62B fields |
| `fields-2025.pmtiles` (114.1 GB) | `cells` z0–8 → `fields` z9–13, 1.58B fields |

Cell properties: `count`, `area_ha` (total field area, hectares),
`avg_confidence` (1dp; null in countries without modeled confidence),
`pct_covered` (percent of cell covered; boundary fields count fully in their
home cell, so isolated values can exceed 100). Field properties: `area` (m²),
`confidence` (0–100, sparse), `country`, `state`.

Unlike the earlier eval products in the sibling collections, these are built
from **deduplicated staging** (boundary-straddling fields collapsed, issue #9)
and the **350 km² artifact cutoff applies to both layers** — the largest
high-confidence real field complex in the data is 331 km²; everything above
350 km² has the low-confidence Sahara-artifact signature.

## Styles

Four per year, each pairing a cell metric with the matching per-field rendering
across the handover: **count** (log-stepped bins → plain boundaries; 2025 is
the default), **coverage** (stepped percent → plain boundaries), **average
field size** (stepped hectares → each field colored by its own size on the same
bins), and **confidence** (stepped 0–100, gray = no modeled confidence → each
field colored by its own confidence).

## Data assets

The per-year A5 r7 cell aggregates are also published as GeoParquet
(`cells_a5r7_2024.parquet`, `cells_a5r7_2025.parquet` — same columns plus the
`a5_cell` id), queryable directly with DuckDB or GeoPandas. The raw field
polygons live in the [vectors collection](../../vectors/collection.json).

## License

CC-BY-4.0, as the parent catalog.
