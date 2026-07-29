#!/usr/bin/env python3
"""Migrate the FTW catalog metadata to the Portolan 0.1 spec.

Idempotent sweep over ``catalog/`` applying the structural/metadata fixes the
0.1 spec (and the rashid 0.1.x conformance checker) require. This does NOT touch
asset ``file:size`` / ``file:checksum`` — that byte-level backfill lives in
``backfill_file_meta.py``.

What it does (see docs/plan for the rule -> fix mapping):
  * strip forbidden ``rel:"self"`` links from every object
  * declare the Portolan v0.1.0 schema URI on every catalog + collection
  * declare the file extension on every asset-bearing object; web-map-links
    wherever a ``rel:"pmtiles"`` link is added; fix the partition extension URI
  * add ``updated`` to catalogs + collections
  * create ``AGENTS.md`` (all 17 catalog/collection dirs) and ``README.md``
    (the 9 large-country sub-catalog dirs) and wire ``rel:"agents"`` /
    ``rel:"describedby"`` links
  * title every ``child`` / ``item`` link (from the target object's title)
  * add a ``host`` provider (Source Cooperative), listed last, where missing
  * set style asset media types to application/vnd.mapbox.style+json
  * vectors collection: fix partition ext URI, add ``partition:glob``, drop the
    un-checksummable glob ``data`` asset, register PMTiles via ``rel:"pmtiles"``
  * vector items: register their PMTiles via ``rel:"pmtiles"``
  * features 2024/2025: give the stac-geoparquet mirror the ``collection-mirror`` role

The two zarr collections (``predictions/zarr``, ``features/zarr``) are being
regenerated and are skipped entirely.

Usage:
    python3 scripts/migrate/upgrade_to_0_1.py [--catalog catalog] [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path

PORTOLAN_URI = "https://schemas.portolan-sdi.org/portolan/v0.1.0/schema.json"
FILE_EXT = "https://stac-extensions.github.io/file/v2.1.0/schema.json"
WML_EXT = "https://stac-extensions.github.io/web-map-links/v1.3.0/schema.json"
PARTITION_OLD = "https://portolan-sdi.github.io/stac-partition-extension/v1.0.0/schema.json"
PARTITION_NEW = "https://schemas.portolan-sdi.org/incubating/partition/v1.0.0/schema.json"

MAPBOX_STYLE_TYPE = "application/vnd.mapbox.style+json"
PARTITION_GLOB = (
    "https://data.source.coop/ftw/global-data/predictions/vectors/"
    "alpha/results-by-admin-conf/admin:country_code=*/*.parquet"
)
# The dataset is self-published by Taylor Geospatial and served on Source
# Cooperative. Per the operator's choice we model Source Cooperative as the
# `host` (the org serving this copy) and Taylor as producer/licensor/processor;
# host != producer makes each collection a "mirror" in the spec's taxonomy, so
# mirror provenance rules (rel:via, updated) apply.
SOURCE_COOP = {
    "name": "Source Cooperative",
    "roles": ["host"],
    "url": "https://source.coop/ftw/global-data",
}
HOST_NAME = "source cooperative"
PRODUCER_NAME = "taylor geospatial institute"
PRODUCER_ROLES = ["producer", "licensor", "processor"]
# The "original source" via target for a mirror that has no external upstream.
VIA_FALLBACK = {
    "rel": "via",
    "href": "https://data.source.coop/ftw/global-data/",
    "type": "text/html",
    "title": "Fields of the World — Global data product",
}

# Directories whose STAC objects are excluded from this migration (regenerating).
EXCLUDED = ("features/zarr", "predictions/zarr")

# One timestamp per run for any `updated` we add.
UPDATED = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

STATS: dict[str, int] = {}


def bump(key: str, n: int = 1) -> None:
    STATS[key] = STATS.get(key, 0) + n


# --------------------------------------------------------------------------- #
# tree walking
# --------------------------------------------------------------------------- #
def is_excluded(rel_path: str) -> bool:
    rel = rel_path.replace(os.sep, "/")
    return any(rel == d or rel.startswith(d + "/") for d in EXCLUDED)


def iter_stac_files(catalog: Path):
    """Yield (path, obj) for every STAC Catalog/Collection/Feature under catalog/."""
    for path in sorted(catalog.rglob("*.json")):
        rel = path.relative_to(catalog).as_posix()
        if "/.portolan/" in f"/{rel}" or rel.startswith(".portolan/"):
            continue
        if is_excluded(rel):
            continue
        try:
            obj = json.loads(path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(obj, dict) or obj.get("type") not in ("Catalog", "Collection", "Feature"):
            continue
        yield path, obj


def load_title(catalog: Path, src: Path, href: str) -> str | None:
    """Resolve a relative link href against src and return the target's title."""
    if "://" in href:
        return None
    target = (src.parent / href).resolve()
    try:
        obj = json.loads(target.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if obj.get("type") == "Feature":
        return (obj.get("properties") or {}).get("title") or obj.get("id")
    return obj.get("title") or obj.get("id")


# --------------------------------------------------------------------------- #
# generic edits
# --------------------------------------------------------------------------- #
def remove_self_links(obj: dict) -> bool:
    links = obj.get("links")
    if not isinstance(links, list):
        return False
    kept = [ln for ln in links if not (isinstance(ln, dict) and ln.get("rel") == "self")]
    if len(kept) != len(links):
        obj["links"] = kept
        bump("self_links_removed", len(links) - len(kept))
        return True
    return False


def ensure_extension(obj: dict, uri: str, front: bool = False) -> bool:
    exts = obj.setdefault("stac_extensions", [])
    if uri in exts:
        return False
    if front:
        exts.insert(0, uri)
    else:
        exts.append(uri)
    bump("extensions_added")
    return True


def has_link(obj: dict, rel: str, href: str) -> bool:
    return any(
        isinstance(ln, dict) and ln.get("rel") == rel and ln.get("href") == href
        for ln in obj.get("links", [])
    )


def add_link(obj: dict, link: dict) -> None:
    obj.setdefault("links", []).append(link)


def ensure_updated(obj: dict) -> bool:
    if "updated" not in obj:
        obj["updated"] = UPDATED
        bump("updated_added")
        return True
    return False


def fix_style_types(obj: dict) -> bool:
    changed = False
    for asset in (obj.get("assets") or {}).values():
        if not isinstance(asset, dict):
            continue
        if "style" in (asset.get("roles") or []) and asset.get("type") != MAPBOX_STYLE_TYPE:
            asset["type"] = MAPBOX_STYLE_TYPE
            bump("style_types_fixed")
            changed = True
    return changed


def has_asset_named_href(obj: dict) -> bool:
    return isinstance(obj.get("assets"), dict) and len(obj["assets"]) > 0


# --------------------------------------------------------------------------- #
# AGENTS.md / README.md
# --------------------------------------------------------------------------- #
def agents_body(obj: dict) -> str:
    title = obj.get("title") or obj.get("id") or "This object"
    return (
        f"# AGENTS.md — {title}\n\n"
        "Guidance for AI agents and automated clients working with this "
        "Portolan/STAC object.\n\n"
        "- This directory is part of the **Fields of the World — Global** catalog "
        "(`https://data.source.coop/ftw/global-data/`).\n"
        "- Data files (GeoParquet, COG, Zarr, PMTiles) are hosted on Source "
        "Cooperative and referenced in place; this repo carries metadata only.\n"
        "- Prefer the machine-readable `llms.txt` in this directory for query "
        "snippets and access patterns, and `README.md` for human documentation.\n"
        "- Resolve assets and structural links relative to this object; catalogs "
        "carry no `self` links.\n"
    )


def readme_body(obj: dict) -> str:
    title = obj.get("title") or obj.get("id") or "Fields of the World — Global"
    desc = obj.get("description") or ""
    return (
        f"# {title}\n\n"
        f"{desc}\n\n"
        "## License\n\n"
        "Released under **CC-BY-4.0**.\n\n"
        "## Provenance\n\n"
        "Part of [Fields of the World](https://fieldsofthe.world); field-boundary "
        "predictions from the PRUE model over global Sentinel-2 composites. "
        "Produced by the Taylor Geospatial Institute and collaborators, hosted on "
        "[Source Cooperative](https://source.coop/ftw/global-data).\n"
    )


def ensure_doc_files(path: Path, obj: dict, dry: bool) -> None:
    """Create AGENTS.md (always) and README.md (if missing) in obj's directory."""
    d = path.parent
    agents = d / "AGENTS.md"
    if not agents.exists():
        if not dry:
            agents.write_text(agents_body(obj))
        bump("agents_md_created")
    readme = d / "README.md"
    if not readme.exists():
        if not dry:
            readme.write_text(readme_body(obj))
        bump("readme_md_created")


def ensure_doc_links(obj: dict) -> None:
    """Add rel:agents -> ./AGENTS.md and a markdown rel:describedby -> ./README.md."""
    if not has_link(obj, "agents", "./AGENTS.md"):
        add_link(obj, {
            "rel": "agents", "href": "./AGENTS.md",
            "type": "text/markdown", "title": "Guidance for AI agents",
        })
        bump("agents_links_added")
    has_md_readme = any(
        isinstance(ln, dict) and ln.get("rel") == "describedby"
        and ln.get("type") == "text/markdown" and str(ln.get("href", "")).endswith("README.md")
        for ln in obj.get("links", [])
    )
    if not has_md_readme:
        add_link(obj, {
            "rel": "describedby", "href": "./README.md",
            "type": "text/markdown", "title": "Human-readable documentation",
        })
        bump("describedby_links_added")


# --------------------------------------------------------------------------- #
# link titles
# --------------------------------------------------------------------------- #
def title_child_item_links(catalog: Path, path: Path, obj: dict) -> None:
    for ln in obj.get("links", []):
        if not isinstance(ln, dict) or ln.get("rel") not in ("child", "item"):
            continue
        if ln.get("title"):
            continue
        title = load_title(catalog, path, ln.get("href", ""))
        if title:
            ln["title"] = title
            bump("link_titles_added")


# --------------------------------------------------------------------------- #
# providers
# --------------------------------------------------------------------------- #
def _name(p: dict) -> str:
    return str(p.get("name", "")).strip().casefold()


def set_providers(obj: dict) -> None:
    """Source Cooperative is the sole `host` (listed last); Taylor is
    producer/licensor/processor. Other producers are left untouched."""
    providers = obj.get("providers")
    if not isinstance(providers, list):
        return
    changed = False
    for p in providers:
        if isinstance(p, dict) and PRODUCER_NAME in _name(p) and p.get("roles") != PRODUCER_ROLES:
            p["roles"] = list(PRODUCER_ROLES)
            changed = True
    source = next((p for p in providers if isinstance(p, dict) and _name(p) == HOST_NAME), None)
    if source is None:
        source = dict(SOURCE_COOP)
        providers.append(source)
        changed = True
    else:
        if source.get("roles") != ["host"]:
            source["roles"] = ["host"]
            changed = True
        source.setdefault("url", SOURCE_COOP["url"])
    # host provider MUST be the last element
    if providers[-1] is not source:
        providers.remove(source)
        providers.append(source)
        changed = True
    if changed:
        bump("providers_normalized")


def fix_mirror_via(obj: dict) -> None:
    """Mirror provenance: every rel:'via' must be text/html; demote non-HTML
    via links to rel:'related', and guarantee at least one via link."""
    links = obj.get("links", [])
    for ln in links:
        if isinstance(ln, dict) and ln.get("rel") == "via" and ln.get("type") != "text/html":
            ln["rel"] = "related"
            bump("via_links_demoted")
    if not any(isinstance(ln, dict) and ln.get("rel") == "via" for ln in links):
        links.append(dict(VIA_FALLBACK))
        bump("via_links_added")


def fix_describedby(obj: dict) -> None:
    """rel:'describedby' is reserved for the README; demote external/non-markdown
    describedby links (e.g. spec references) to rel:'related'."""
    for ln in obj.get("links", []):
        if not isinstance(ln, dict) or ln.get("rel") != "describedby":
            continue
        href = str(ln.get("href", ""))
        if "://" in href or ln.get("type") != "text/markdown":
            ln["rel"] = "related"
            bump("describedby_links_demoted")


# --------------------------------------------------------------------------- #
# PMTiles registration
# --------------------------------------------------------------------------- #
def pmtiles_layers(asset_key: str, href: str) -> list[str]:
    if href.endswith("2025.pmtiles") or "fields-2025" in href:
        return ["fields"]
    if "2024_with_confidence" in href or "2024" in asset_key:
        return ["2024"]
    # per-item pmtiles carry both year layers
    return ["2024", "2025"]


def register_pmtiles(obj: dict) -> bool:
    """Add a rel:pmtiles link for each visual PMTiles asset; declare web-map-links."""
    added = False
    for key, asset in (obj.get("assets") or {}).items():
        if not isinstance(asset, dict) or asset.get("type") != "application/vnd.pmtiles":
            continue
        href = asset.get("href", "")
        if has_link(obj, "pmtiles", href):
            continue
        add_link(obj, {
            "rel": "pmtiles", "href": href, "type": "application/vnd.pmtiles",
            "title": asset.get("title", "Web map tiles"),
            "pmtiles:layers": pmtiles_layers(key, href),
        })
        bump("pmtiles_links_added")
        added = True
    if added:
        ensure_extension(obj, WML_EXT)
    return added


# --------------------------------------------------------------------------- #
# per-object driver
# --------------------------------------------------------------------------- #
def process(catalog: Path, path: Path, obj: dict, dry: bool) -> None:
    kind = obj["type"]
    remove_self_links(obj)

    if kind in ("Catalog", "Collection"):
        ensure_extension(obj, PORTOLAN_URI, front=True)
        ensure_updated(obj)
        ensure_doc_files(path, obj, dry)
        fix_describedby(obj)
        ensure_doc_links(obj)
        title_child_item_links(catalog, path, obj)

    if has_asset_named_href(obj):
        ensure_extension(obj, FILE_EXT)
        fix_style_types(obj)

    if kind == "Collection":
        set_providers(obj)
        fix_mirror_via(obj)

    # partition extension URI fix (vectors collection)
    exts = obj.get("stac_extensions", [])
    if PARTITION_OLD in exts:
        exts[exts.index(PARTITION_OLD)] = PARTITION_NEW
        bump("partition_ext_fixed")

    # vectors collection specifics
    if kind == "Collection" and obj.get("id") == "vectors":
        if "partition:glob" not in obj:
            obj["partition:glob"] = PARTITION_GLOB
            bump("partition_glob_added")
        assets = obj.get("assets", {})
        data = assets.get("data")
        if isinstance(data, dict) and "*" in str(data.get("href", "")):
            del assets["data"]
            bump("glob_data_assets_removed")
        register_pmtiles(obj)

    # features 2024/2025 stac-geoparquet mirror role
    if kind == "Collection" and obj.get("id", "").startswith("s2-planting-harvest-composites-20"):
        gp = (obj.get("assets") or {}).get("geoparquet-items")
        if isinstance(gp, dict) and "collection-mirror" not in (gp.get("roles") or []):
            gp["roles"] = ["collection-mirror"]
            gp["type"] = "application/vnd.apache.parquet"
            bump("mirror_roles_fixed")

    # Item-level PMTiles links are not required by the profile (only the
    # collection registers PMTiles) and would point at data files that are not
    # in the repo, so they don't resolve locally. Keep items lean.
    if kind == "Feature":
        links = obj.get("links", [])
        pruned = [ln for ln in links if not (isinstance(ln, dict) and ln.get("rel") == "pmtiles")]
        if len(pruned) != len(links):
            obj["links"] = pruned
            bump("item_pmtiles_links_removed", len(links) - len(pruned))
        exts = obj.get("stac_extensions", [])
        if WML_EXT in exts:
            exts.remove(WML_EXT)
            bump("item_wml_ext_removed")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog", default="catalog", help="path to the catalog root")
    ap.add_argument("--dry-run", action="store_true", help="report changes without writing")
    args = ap.parse_args()

    catalog = Path(args.catalog).resolve()
    if not (catalog / "catalog.json").exists():
        raise SystemExit(f"no catalog.json under {catalog}")

    for path, obj in iter_stac_files(catalog):
        before = json.dumps(obj, sort_keys=True)
        process(catalog, path, obj, args.dry_run)
        after = json.dumps(obj, sort_keys=True)
        if before != after:
            bump("files_modified")
            if not args.dry_run:
                path.write_text(json.dumps(obj, indent=2, ensure_ascii=True) + "\n")

    width = max((len(k) for k in STATS), default=0)
    print("Portolan 0.1 upgrade" + (" (dry run)" if args.dry_run else "") + ":")
    for key in sorted(STATS):
        print(f"  {key.ljust(width)}  {STATS[key]}")
    if not STATS:
        print("  no changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
