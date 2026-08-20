# `features/` — Sentinel-2 planting/harvest composite collections

Builds the STAC for the FTW model-input **features**: the Sentinel-2 planting- and
harvest-season median composites (`features/cogs/alpha`, `features/zarr/alpha`). One
**collection per year** (`s2-planting-harvest-composites-2024` / `-2025`).

`build_features_items.py` has two modes:

| Command | Output | Committed? |
|---|---|---|
| `collections` | The 2 `catalog/features/<year>/collection.json` + `README.md` + `llms.txt`. Each collection carries the global **Zarr** mosaic as a `data` asset, a **STAC-GeoParquet** asset (`items.parquet`) as the item index, and a `child` link per UTM zone into the browse tree. | **Yes** (in the repo) |
| `items <year>` | The **MGRS browse tree**: per-tile STAC items (one per MGRS tile, with `planting` + `harvest` COG assets), the ~700 zone / grid-zone catalogs above them, and the `items.parquet` STAC-GeoParquet. Written under `features/<year>/…` **on S3**. | **No — S3-only, `.gitignore`d** |
| `places` | `mgrs_places.json` — the countries behind each grid node's title. Needs `duckdb`+`spatial` and network (Natural Earth 50m). | **Yes** (in `scripts/`, never published) |

## The MGRS browse tree

Items are browsable four levels down, and every level is derivable from the tile id
(`35UQA` = UTM zone **35**, latitude band **U**, 100 km square **QA**) — no spatial join,
no gaps, no tile in two places:

```
features/2024/collection.json         children = the 60 UTM zones
└── 35/catalog.json                   "UTM Zone 35 — Dem. Rep. Congo, Sudan, South Africa, Egypt (+27 more)"
    └── 35u/catalog.json              "Zone 35U — Ukraine, Belarus, Lithuania, Moldova (+3 more)"
        └── 35uqa_2024.json           item: planting + harvest COGs
```

641 grid-zone cells hold a median of 36 tiles (max 63), so no node is unbrowsably long.
The country names in the titles come from `mgrs_places.json`, precomputed by the `places`
subcommand so neither `collections` nor a rails run needs Natural Earth.

**Why the tree is S3-only.** There are ~22.7k tiles per year; committing ~45k item JSONs
plus ~1.4k catalogs to git is impractical, so — like the prediction `vectors` data — it
**lives only on Source Cooperative (S3)**, produced by this script and `.gitignore`d
locally. `scripts/catalog/publish.py` only publishes the repo's `catalog/` tree, so it
never touches these artifacts.

That split has one consequence worth knowing: the committed collections carry **relative**
`child` links (`./35/catalog.json`) into a tree that is not in the repo. Relative is a
Portolan MUST (PTL-LNK-004), and the links resolve in the published catalog — but in a git
checkout the targets are absent, so `tests/test_links.py` and
`tests/test_portolan_conformance.py` each carry a narrow, documented exemption for exactly
these links. Verify the real thing against the published catalog, not the checkout.

## Item shape (best-practice STAC for COGs)

Each item = one MGRS tile/year: lowercase id (`01fbe_2024`), the [grid extension](https://github.com/stac-extensions/grid)
`grid:code` (`MGRS-01FBE`), populated `datetime` + season range, item-level `proj:` (read
from the COG header), unified STAC 1.1 `bands` (eo) with `data_type`/`gsd` at the asset,
COG media type, a markdown description with links, and a `derived_from` link to the
official ESA **Copernicus Data Space Ecosystem** Sentinel-2 L2A collection (plus a `via`
to the AWS/Earth Search L2A COGs actually used).

## Run

```bash
# in the repo (writes the committed collections)
python3 scripts/features/build_features_items.py collections

# metadata-only change (new links, new layout, new titles)? Rebuild the tree from the
# PUBLISHED items.parquet instead of re-reading ~45k COG headers — minutes, runs anywhere:
python3 scripts/features/build_features_items.py items 2024 --from-parquet

# on rails: submit via Slurm (NOT the login node — it reaps heavy jobs). One job per year:
rsync -av scripts/features/ rails:ftw-feat/
ssh rails 'cd ~/ftw-feat && sbatch --export=ALL,YEAR=2024 features_items.sbatch'
ssh rails 'cd ~/ftw-feat && sbatch --export=ALL,YEAR=2025 features_items.sbatch'
# the sbatch runs: build_features_items.py items <YEAR>  (test first with --limit 5 --no-upload)
```

Use the full remote passes (no `--from-parquet`) only when the **tiles themselves** change;
they re-read every COG header and re-HEAD every asset (~8 h/year of pure network latency,
which is why they are parallelised and belong in-region).

See the root `scripts/README.md` "Running on TGI rails" for the full Slurm recipe
(account `bgtj-tgirails`, partition `cpu`, env on `/u`, compute-node S3 egress).

Needs `duckdb`, `rasterio`, `pyarrow`, `aws`, and (for a proper stac-geoparquet)
`stac-geoparquet`; falls back to a minimal index parquet if that isn't installed.
