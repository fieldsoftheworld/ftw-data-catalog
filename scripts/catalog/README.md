# `catalog/` — B: STAC generation & publishing

Generates the STAC metadata, READMEs, thumbnails, and styles under `catalog/`, and
publishes that tree 1:1 to Source Cooperative. (The data files themselves — parquet,
PMTiles, COGs — are produced by the other stages and live only on S3; `publish.py`
never touches them.)

| Script | Does | Run |
|---|---|---|
| `build_vector_items.py` | Generate the `vectors` collection: one STAC item per parquet (id = filename stem), split-country sub-catalogs, glob `data` asset, two collection PMTiles, `table:columns` (fiboa/vecorel wording + `describedby` links), per-country year-toggle MapLibre styles, and an `llms.txt` per country. | `python3 scripts/catalog/build_vector_items.py [--keys file]` |
| `build_items.py` | Generate the 5 STAC items for the `confidence` raster collection (reads COG headers). | `python3 scripts/catalog/build_items.py` |
| `make_llms.py` | Generate `llms.txt` for the confidence collection + items. | `python3 scripts/catalog/make_llms.py` |
| `make_thumbnails.py` | Render `thumbnail.png` for the confidence collection/items from COG overviews. | `python3 scripts/catalog/make_thumbnails.py` |
| `publish.py` | **Canonical publisher.** Walk `catalog/` and upload 1:1 to Source Cooperative (per-file content-types; skips `.portolan/config.yaml`/`state.json`). Config in `catalog.publish.yaml`. | `python3 scripts/catalog/publish.py` (dry run) · `--confirm` |
| `restructure_s3.sh`, `publish_metadata.sh` | Legacy one-offs (server-side moves; older targeted publisher) — superseded by `publish.py`. | — |

Validate before publishing: `python3 tests/test_links.py && python3 tests/test_stac_valid.py`
(see the repo root `CLAUDE.md`).
