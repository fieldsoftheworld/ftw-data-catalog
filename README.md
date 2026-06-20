# ftw-portolan

Git-backed [Portolan](https://portolan-sdi.org)/STAC catalog for the **Fields of the World (FTW) Global** datasets — global agricultural field boundaries and prediction-quality layers at 10 m resolution.

**This repository is the source of truth for catalog _metadata_ only.** The data itself — billions of field polygons, COGs, and Zarr stacks (hundreds of GB) — lives on [Source Cooperative](https://source.coop/ftw/global-data) and is never stored in or uploaded by this repo.

- 🌍 **Live catalog & data:** <https://data.source.coop/ftw/global-data/>
- 🧭 **Browse the STAC catalog:** [Portolan browser](https://browser.portolan-sdi.org/#/external/data.source.coop/ftw/global-data/catalog.json)
- 🤖 **For AI agents:** [`llms.txt`](https://data.source.coop/ftw/global-data/llms.txt)
- 📄 **Paper:** Robinson et al. 2026, [arXiv:2605.11055](https://arxiv.org/abs/2605.11055)

## How this repo works

The [`catalog/`](./catalog/) directory **is** the published catalog: it is synced 1:1 to
`s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data/`, which Source Cooperative
serves at `https://data.source.coop/ftw/global-data/`. What you see in `catalog/` is exactly
what is live. Everything outside `catalog/` is never published.

```
catalog/        the published STAC/Portolan catalog (1:1 with Source Cooperative)
  README.md       the README rendered on Source Cooperative
  README_next.md  published preview of the proposed next catalog README
staging/        collections being prepared, not yet published
scripts/        publishing + build tooling
tests/          dependency-free catalog validation
docs/           design specs and plans
CLAUDE.md       developer / agent guide
```

## Editing & publishing

1. Edit metadata under `catalog/` (STAC JSON, `README.md`, `llms.txt`, `.portolan/metadata.yaml`).
2. Validate: `python3 tests/test_links.py && python3 tests/test_publish.py`
3. Commit.
4. Publish: `python3 scripts/catalog/publish.py` (dry run), then `python3 scripts/catalog/publish.py --confirm` (needs AWS credentials).

See [CLAUDE.md](./CLAUDE.md) for the full developer guide. Corrections and additions welcome via pull request.

## License

Catalog metadata and data are published under CC-BY-4.0 by Taylor Geospatial and collaborators.
