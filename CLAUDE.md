# ftw-portolan — developer guide

Git-backed Portolan/STAC catalog for the **Fields of the World (FTW) Global** datasets.
This repo is the **source of truth for metadata only**. The data (billions of polygons,
COGs, Zarr — hundreds of GB) lives on Source Cooperative and is **never** stored or
uploaded by this repo.

## Path mapping (Source Cooperative)
- Write target (uploads): `s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data/`
- Public href base (all STAC hrefs): `https://data.source.coop/ftw/global-data/`
- Source Cooperative serves the public `ftw/global-data` path from the `tge-labs/...` prefix.

## Three file categories
1. Tracked + published: STAC JSON, README.md, llms.txt, thumbnail.png, `.portolan/metadata.yaml`.
2. Tracked, NOT published: `scripts/`, `docs/`, `CLAUDE.md`, `catalog.publish.yaml`, `.portolan/config.yaml`.
3. Gitignored (never in repo): data files (`*.tif`, `*.parquet`, `*.zarr`), `.env`, caches.

## Publish workflow
Edit metadata -> commit -> publish:
```
python3 scripts/publish.py            # dry run
python3 scripts/publish.py --confirm  # upload (needs AWS creds)
```
Only collections listed under `collections:` in `catalog.publish.yaml` are published.

## Add a collection
1. Create `<group>/<name>/collection.json` (+ `.portolan/metadata.yaml`); hrefs use the public base.
2. Add a `child` link in `catalog.json`.
3. When ready to go live, add its path to `collections:` in `catalog.publish.yaml`.
4. `python3 tests/test_links.py && python3 scripts/publish.py` to verify.

## Tests (dependency-free; run with python3)
`tests/test_links.py`, `tests/test_git_ext.py`, `tests/test_publish.py`, `tests/test_scaffolds.py`.

## Git extension (portolan-cli#485)
`catalog.json` hand-carries `git:repository`, `git:ref`, `git:provider` plus `vcs`/`issues`
links, pending CLI support.
