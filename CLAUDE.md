# ftw-portolan — developer guide

Git-backed Portolan/STAC catalog for the **Fields of the World (FTW) Global** datasets.
This repo is the **source of truth for catalog metadata only**. The data (billions of
polygons, COGs, Zarr — hundreds of GB) lives on Source Cooperative and is **never** stored
or uploaded by this repo.

## Clean publish-directory model
`catalog/` **is** the published catalog — synced 1:1 to Source Cooperative. Everything in
`catalog/` is published; everything outside it never is.

- Write target (uploads): `s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data/`
- Public href base (all STAC hrefs): `https://data.source.coop/ftw/global-data/`
- Source Cooperative serves the public `ftw/global-data` path from the `tge-labs/...` prefix.

## Layout
- `catalog/` — the published catalog (STAC JSON, README.md, llms.txt, thumbnails, `.portolan/metadata.yaml`). Synced 1:1 to S3.
- `staging/` — collections being prepared; git-tracked but NOT published.
- `scripts/`, `tests/`, `docs/`, `CLAUDE.md`, root `README.md`, `catalog.publish.yaml` — tooling/docs, never published.
- Gitignored (never in repo): data files (`*.tif`, `*.parquet`, `*.zarr`), `.env`, caches.

## READMEs
- Root `README.md` — GitHub front door (not published).
- `catalog/README.md` — the README rendered on Source Cooperative (published).
- `catalog/README_next.md` — published preview of the proposed next catalog README (for sharing/feedback); promote by copying it over `catalog/README.md`.

## Publish workflow
Edit metadata under `catalog/` -> commit -> publish:
```
python3 scripts/publish.py            # dry run (lists the catalog/ tree -> S3)
python3 scripts/publish.py --confirm  # upload (needs AWS creds)
```
`publish.py` uploads every file in `catalog/` 1:1, skipping only Portolan-internal
`.portolan/config.yaml` and `.portolan/state.json`. Config (write_prefix, public_base, region, publish_dir) lives in `catalog.publish.yaml`.

## Add / promote a collection
1. Build it under `staging/<group>/<name>/` (collection.json + `.portolan/metadata.yaml`); hrefs use the public base.
2. When ready: `git mv staging/<group>/<name> catalog/<group>/<name>`.
3. Add a `child` link to `catalog/catalog.json`.
4. `python3 tests/test_links.py && python3 scripts/publish.py` to verify.

## Tests (dependency-free; run with python3)
`tests/test_links.py`, `tests/test_git_ext.py`, `tests/test_publish.py`, `tests/test_scaffolds.py`.

## Git extension (portolan-cli#485)
`catalog/catalog.json` hand-carries `git:repository`, `git:ref`, `git:provider` plus `vcs`/`issues`
links, pending CLI support.
