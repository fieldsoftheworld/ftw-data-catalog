# AGENTS.md — Fields 2025 — A5 r7 cell aggregates (test)

Guidance for AI agents and automated clients working with this Portolan/STAC object.

- This directory is part of the **Fields of the World — Global** catalog (`https://data.source.coop/ftw/global-data/`) — a TEST collection for evaluating tiling approaches.
- Data files (PMTiles, GeoParquet) are hosted on Source Cooperative and referenced in place; this repo carries metadata only.
- For analysis, prefer the `parquet` asset (same aggregate as the tiles, plus the `a5_cell` id) over reading tiles.
- See `README.md` for the layer schema, and the parent catalog's README for how the collections compare.
- Resolve assets and structural links relative to this object; catalogs carry no `self` links.
