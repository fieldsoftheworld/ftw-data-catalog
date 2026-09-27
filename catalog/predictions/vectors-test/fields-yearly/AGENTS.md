# AGENTS.md — Fields 2024 & 2025 — cells-to-fields handover (test)

Guidance for AI agents and automated clients working with this Portolan/STAC object.

- This directory is part of the **Fields of the World — Global** catalog (`https://data.source.coop/ftw/global-data/`) — the candidate production tiles product, still under the test catalog.
- Data files (PMTiles, GeoParquet) are hosted on Source Cooperative and referenced in place; this repo carries metadata only.
- Each PMTiles archive holds TWO layers: `cells` (A5 r7 aggregates, z0–8) and `fields` (actual polygons, z9–13). A style or renderer must read the right `source-layer` per zoom range.
- For analysis, prefer the `cells_*` GeoParquet assets (same aggregates plus the `a5_cell` id) over reading tiles; for per-field analysis use the raw polygons in `../../vectors/`.
- See `README.md` for the layer schemas and provenance (deduped staging, 350 km² cutoff), and the parent catalog's README for how this compares to the eval collections beside it.
- Resolve assets and structural links relative to this object; catalogs carry no `self` links.
