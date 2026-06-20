#!/usr/bin/env python3
"""Generate the STAC for the FTW field-boundary prediction-vectors collection.

One item per parquet partition (id = parquet filename stem), colocated with its
data on S3 via relative hrefs; countries split into multiple parquets get a
country sub-catalog. Collection carries a Portolan glob `data` asset over
results-by-admin-conf, two collection PMTiles (2025 default + 2024 confidence),
and the two MapLibre styles. The per-polygon `confidence` derivation is
documented on the collection (with links to the generating scripts on GitHub).

Pure builders (bbox_to_polygon / title_for / build_item / build_collection) are
unit-tested. The CLI reads each parquet's bbox + row count and writes the tree
under staging/predictions/vectors/.

Usage:
    python3 build_vector_items.py --keys /tmp/keys.txt        # offline-ish
    python3 build_vector_items.py                              # list S3 itself
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PUBLIC_BASE = "https://data.source.coop/ftw/global-data"
COLLECTION_HREF = f"{PUBLIC_BASE}/predictions/vectors"
DATA_REL = "alpha/results-by-admin-conf"          # relative to the collection dir
SRC_S3 = ("s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data/"
          "predictions/vectors/alpha/results-by-admin")
GITHUB = "https://github.com/fieldsoftheworld/ftw-portolan"
PMTILES_2025 = f"{PUBLIC_BASE}/../global-field-boundaries/pmtiles/ftw-global-fields-2025.pmtiles"
PMTILES_2025 = "https://data.source.coop/ftw/global-field-boundaries/pmtiles/ftw-global-fields-2025.pmtiles"
PMTILES_2024 = f"{PUBLIC_BASE}/predictions/vectors/alpha/2024_with_confidence.pmtiles"

TABLE_EXT = "https://stac-extensions.github.io/table/v1.2.0/schema.json"
PARTITION_EXT = "https://portolan-sdi.github.io/stac-partition-extension/v1.0.0/schema.json"

# Field definitions — wording taken verbatim from the fiboa core spec and the
# vecorel extensions, linked via `describedby` collection links below.
FIBOA_CORE = "https://github.com/fiboa/specification/blob/main/core/README.md"
VECOREL_METRICS = "https://github.com/vecorel/geometry-metrics-extension"
VECOREL_ADMIN = "https://github.com/vecorel/administrative-division-extension"
TABLE_COLUMNS = [
    {"name": "id", "type": "string",
     "description": "An identifier for the field. Must be unique per collection."},
    {"name": "geometry", "type": "binary",
     "description": "A geometry that reflects the footprint of the field, usually a "
                    "Polygon. Default CRS is WGS84."},
    {"name": "bbox", "type": "struct",
     "description": "The bounding box of the field."},
    {"name": "metrics:area", "type": "float",
     "description": "Area of the field, in square meters (m²). Must be > 0."},
    {"name": "metrics:perimeter", "type": "float",
     "description": "Perimeter of the field, in meters (m). Must be > 0."},
    {"name": "determination:datetime", "type": "timestamp",
     "description": "The last timestamp at which the field did exist and was observed, "
                    "in the UTC timezone."},
    {"name": "determination:method", "type": "string",
     "description": "The boundary creation method (one of: manual, surveyed, driven, "
                    "auto-operation, auto-imagery, unknown)."},
    {"name": "admin:country_code", "type": "string",
     "description": "ISO 3166-1 alpha-2 country code (aka admin0). Two-letter country "
                    "code for the country that contains the field."},
    {"name": "admin:subdivision_code", "type": "string",
     "description": "ISO 3166-2 code for identifying the principal subdivision (e.g. "
                    "province or state, aka admin1) of a country that contains the "
                    "field. Only the subdivision part of the code is stored."},
    {"name": "confidence", "type": "float",
     "description": "Derived (not part of the upstream model output). Modeled PRUE "
                    "confidence on a 0–100 scale: sampled at the field's point-on-"
                    "surface from the 500 m confidence COG (predictions/confidence) and "
                    "rescaled raw/0.578178×100, clamped to 100; null where the COG has "
                    "no data. Recommended reliability filter: confidence >= 69 (raw 0.4)."},
]
PROJ_EXT = "https://stac-extensions.github.io/projection/v2.0.0/schema.json"
VECTOR_EXT = "https://stac-extensions.github.io/vector/v0.1.0/schema.json"
WEBMAP_EXT = "https://stac-extensions.github.io/web-map-links/v1.3.0/schema.json"

CONFIDENCE_DOC = (
    "Each polygon carries a `confidence` value (0–100): the modeled PRUE "
    "confidence sampled at the field's point-on-surface from the 500 m confidence "
    "COG (the `predictions/confidence` collection), rescaled `raw / 0.578178 * "
    "100` and clamped to 100 (cells with no data become null). 0.578178 is treated "
    "as 100%, matching the FTW inference app; this centroid sample is the closest "
    "single value to the app's `confidence_mean`. Recommended default reliability "
    "filter: confidence >= 69 (raw 0.4). Confidence reflects cell-level model "
    "reliability, not individual-polygon geometric accuracy. Generated by "
    f"`add_confidence.py` (+ `process_partition.sh`, `run_rails.sh`, "
    f"`make_pmtiles.py`): {GITHUB}/blob/main/scripts/add_confidence.py"
)


# ── pure builders ────────────────────────────────────────────────────────────

def bbox_to_polygon(bbox):
    minx, miny, maxx, maxy = bbox
    return {"type": "Polygon", "coordinates": [[
        [minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]]}


def _country_name(cc):
    import pycountry
    c = pycountry.countries.get(alpha_2=cc)
    return c.name if c else cc


def title_for(stem, country_code):
    """Single-file partitions are named for the country; split partitions use an
    ISO-3166-2 subdivision code (underscore) -> "<Country> — <Subdivision>"."""
    import pycountry
    if "_" in stem:
        sub = pycountry.subdivisions.get(code=stem.replace("_", "-"))
        if sub:
            return f"{_country_name(country_code)} — {sub.name}"
        return stem
    return _country_name(country_code)


# Confidence ramp (0-100 scale, as stored in the per-country PMTiles `confidence`).
_RAMP = [0, "#d7191c", 70, "#fec379", 80, "#f3fabb", 90, "#cfecb0", 100, "#33a02c"]
_FILTER = ["all", ["has", "confidence"], [">=", ["get", "confidence"], 69]]


def item_style(stem, years=("2024", "2025"), default_year="2025"):
    """A MapLibre style for one item's PMTiles: a layer per year, with only the
    default year visible (toggle the other on in the viewer). Colored by the
    0-100 confidence (red->green), filtered to the recommended >= 69, with a
    legend layer."""
    src = {"data": {"type": "vector", "url": f"pmtiles://./{stem}.pmtiles"}}
    color = ["interpolate", ["linear"], ["get", "confidence"], *_RAMP]
    layers = [{
        "id": "confidence-legend", "type": "fill", "source": "data",
        "source-layer": default_year,
        "paint": {"fill-color": ["step", ["get", "confidence"], *_RAMP], "fill-opacity": 0},
    }]
    for y in years:
        vis = "visible" if y == default_year else "none"
        layers.append({
            "id": f"fields-{y}-fill", "type": "fill", "source": "data",
            "source-layer": y, "layout": {"visibility": vis}, "filter": _FILTER,
            "paint": {"fill-color": color, "fill-opacity": 0.5}})
        layers.append({
            "id": f"fields-{y}-outline", "type": "line", "source": "data",
            "source-layer": y, "layout": {"visibility": vis}, "filter": _FILTER,
            "paint": {"line-color": color, "line-width": 1}})
    return {
        "version": 8,
        "name": f"{stem} field boundaries by confidence (year layers)",
        "metadata": {
            "portolan:legend": {"title": "Confidence (0–100)", "unit": "%", "type": "ramp"},
            "description": (f"Per-year field boundaries for {stem}; one year layer "
                            f"visible at a time (default {default_year}). Colored by "
                            "confidence (0–100, red→green), filtered to confidence >= 69.")},
        "sources": src,
        "layers": layers,
    }


def build_item(stem, country_code, bbox, feature_count, is_split=False):
    coll_up = "../../../"          # item dir -> collection dir
    root_up = "../../../../../"    # item dir -> catalog root
    parent = "./catalog.json" if is_split else f"{coll_up}collection.json"
    self_href = (f"{COLLECTION_HREF}/{DATA_REL}/admin:country_code={country_code}/"
                 f"{stem}.json")
    return {
        "type": "Feature",
        "stac_version": "1.1.0",
        "stac_extensions": [PROJ_EXT, VECTOR_EXT],
        "id": stem,
        "geometry": bbox_to_polygon(bbox),
        "bbox": bbox,
        "properties": {
            "title": title_for(stem, country_code),
            "description": (
                f"FTW PRUE field-boundary predictions for "
                f"{title_for(stem, country_code)}. {CONFIDENCE_DOC}"),
            "datetime": None,
            "start_datetime": "2024-01-01T00:00:00Z",
            "end_datetime": "2025-12-31T23:59:59Z",
            "admin:country_code": country_code,
            "proj:code": "EPSG:4326",
            "geoparquet:geometry_type": "Polygon",
            "geoparquet:feature_count": feature_count,
        },
        "collection": "vectors",
        "assets": {
            "data": {
                "href": f"./{stem}.parquet",
                "type": "application/vnd.apache.parquet",
                "title": f"{title_for(stem, country_code)} field boundaries (GeoParquet)",
                "roles": ["data"],
            },
            "pmtiles": {
                "href": f"./{stem}.pmtiles",
                "type": "application/vnd.pmtiles",
                "title": f"{title_for(stem, country_code)} field boundaries (PMTiles, 2024/2025 layers)",
                "roles": ["visual"],
            },
            "style": {
                "href": f"./{stem}.style.json",
                "type": "application/json",
                "title": "MapLibre style — confidence, one year layer at a time",
                "roles": ["style"],
            },
        },
        "links": [
            {"rel": "root", "href": f"{root_up}catalog.json", "type": "application/json"},
            {"rel": "collection", "href": f"{coll_up}collection.json", "type": "application/json"},
            {"rel": "parent", "href": parent, "type": "application/json"},
            {"rel": "self", "href": self_href, "type": "application/geo+json"},
            {"rel": "llms", "href": "./llms.txt", "type": "text/markdown",
             "title": "Agent/LLM usage guide"},
        ],
    }


def build_collection(item_links, child_links):
    """item_links: [(stem, country_code)] single-file items; child_links:
    [country_code] split-country sub-catalogs."""
    links = [
        {"rel": "root", "href": "../../catalog.json", "type": "application/json",
         "title": "Fields of the World — Global"},
        {"rel": "parent", "href": "../../catalog.json", "type": "application/json"},
        {"rel": "self", "href": f"{COLLECTION_HREF}/collection.json", "type": "application/json"},
        {"rel": "license", "href": "https://creativecommons.org/licenses/by/4.0/",
         "type": "text/html"},
        {"rel": "llms", "href": "./llms.txt", "type": "text/markdown",
         "title": "Agent/LLM usage guide"},
        # field definitions follow these specs (verbatim in table:columns)
        {"rel": "describedby", "href": FIBOA_CORE, "type": "text/html",
         "title": "fiboa core specification (id, geometry, bbox, determination:*)"},
        {"rel": "describedby", "href": VECOREL_METRICS, "type": "text/html",
         "title": "vecorel geometry-metrics extension (metrics:area, metrics:perimeter)"},
        {"rel": "describedby", "href": VECOREL_ADMIN, "type": "text/html",
         "title": "vecorel administrative-division extension (admin:*)"},
        # web-map-links extension: PMTiles exposed as links (default = 2025)
        {"rel": "pmtiles", "href": PMTILES_2025, "type": "application/vnd.pmtiles",
         "title": "Field boundaries 2025 (default)"},
        {"rel": "pmtiles", "href": PMTILES_2024, "type": "application/vnd.pmtiles",
         "title": "Field boundaries 2024 with confidence"},
    ]
    for stem, cc in item_links:
        links.append({"rel": "item",
                      "href": f"./{DATA_REL}/admin:country_code={cc}/{stem}.json",
                      "type": "application/geo+json"})
    for cc in child_links:
        links.append({"rel": "child",
                      "href": f"./{DATA_REL}/admin:country_code={cc}/catalog.json",
                      "type": "application/json", "title": _country_name(cc)})

    return {
        "type": "Collection",
        "stac_version": "1.1.0",
        "stac_extensions": [PROJ_EXT, VECTOR_EXT, WEBMAP_EXT, TABLE_EXT, PARTITION_EXT],
        "id": "vectors",
        "title": "FTW Global — Field Boundary Predictions (alpha)",
        "description": (
            "Global agricultural field-boundary polygons predicted by the PRUE "
            "model, as cloud-native GeoParquet partitioned by country (admin), with "
            "per-country PMTiles for web visualization. " + CONFIDENCE_DOC),
        "license": "CC-BY-4.0",
        "keywords": ["agriculture", "field boundaries", "Fields of the World",
                     "FTW", "global", "PRUE", "confidence"],
        "providers": [
            {"name": "Taylor Geospatial Institute", "roles": ["producer", "licensor"],
             "url": "https://taylorgeospatial.org/"},
            {"name": "Microsoft AI for Good Research Lab",
             "roles": ["producer", "processor"],
             "url": "https://www.microsoft.com/en-us/research/group/ai-for-good-research-lab/"},
        ],
        "extent": {
            "spatial": {"bbox": [[-180.0, -60.0, 180.0, 84.0]]},
            "temporal": {"interval": [["2024-01-01T00:00:00Z", "2025-12-31T23:59:59Z"]]},
        },
        "summaries": {"proj:code": ["EPSG:4326"], "vector:geometry_types": ["Polygon"]},
        "table:columns": TABLE_COLUMNS,
        "partition:scheme": "hive",
        "partition:keys": [{"name": "admin:country_code", "type": "string"}],
        "links": links,
        "assets": {
            "data": {
                "href": f"./{DATA_REL}/admin:country_code=*/*.parquet",
                "type": "application/vnd.apache.parquet",
                "title": "Field-boundary polygons, partitioned by country (GeoParquet glob)",
                "description": "Portolan glob over all admin (country) partitions.",
                "roles": ["data"],
            },
            "pmtiles_2025": {
                "href": PMTILES_2025,
                "type": "application/vnd.pmtiles",
                "title": "Field boundaries 2025 (PMTiles, default web view)",
                "roles": ["visual"],
            },
            "pmtiles_2024_confidence": {
                "href": PMTILES_2024,
                "type": "application/vnd.pmtiles",
                "title": "Field boundaries 2024 with confidence (PMTiles)",
                "roles": ["visual"],
            },
            "styles/default": {
                "href": "./styles/default.json", "type": "application/json",
                "title": "Confidence (2025) — default", "roles": ["style"]},
            "styles/confidence-2024": {
                "href": "./styles/confidence-2024.json", "type": "application/json",
                "title": "Confidence (2024)", "roles": ["style"]},
            "documentation": {
                "href": "./llms.txt", "type": "text/markdown",
                "title": "Agent/LLM usage guide", "roles": ["documentation"]},
            "README": {"href": "./README.md", "type": "text/markdown",
                       "title": "Human-readable README", "roles": ["metadata"]},
        },
    }


def build_country_catalog(country_code, child_stems):
    return {
        "type": "Catalog",
        "stac_version": "1.1.0",
        "id": f"vectors-{country_code}",
        "title": f"{_country_name(country_code)} — field boundary predictions",
        "description": (f"Field-boundary predictions for {_country_name(country_code)}, "
                        f"split into {len(child_stems)} admin-subdivision partitions. "
                        + CONFIDENCE_DOC),
        "links": [
            {"rel": "root", "href": "../../../../../catalog.json", "type": "application/json"},
            {"rel": "parent", "href": "../../../collection.json", "type": "application/json"},
            {"rel": "self",
             "href": f"{COLLECTION_HREF}/{DATA_REL}/admin:country_code={country_code}/catalog.json",
             "type": "application/json"},
            {"rel": "llms", "href": "./llms.txt", "type": "text/markdown"},
            *[{"rel": "item", "href": f"./{stem}.json", "type": "application/geo+json"}
              for stem in child_stems],
        ],
    }


# ── CLI: read parquet metadata + write the tree ──────────────────────────────

def _read_keys(keys_path):
    if keys_path:
        return [l.strip() for l in Path(keys_path).read_text().splitlines() if l.strip()]
    out = subprocess.run(
        ["aws", "s3", "ls", "--no-sign-request", "--recursive", "--region",
         "us-west-2", SRC_S3 + "/"], check=True, capture_output=True, text=True).stdout
    keys = []
    for line in out.splitlines():
        p = line.split()[-1]
        if p.endswith(".parquet"):
            keys.append(p.split("/results-by-admin/", 1)[1])
    return keys


_S3FS = None


def _parquet_meta(cc, fname):
    """(bbox, feature_count) from the original parquet footer (anonymous S3)."""
    global _S3FS
    import pyarrow.parquet as pq
    import pyarrow.fs as pafs
    if _S3FS is None:
        _S3FS = pafs.S3FileSystem(anonymous=True, region="us-west-2")
    path = ("us-west-2.opendata.source.coop/tge-labs/ftw-global-data/predictions/"
            f"vectors/alpha/results-by-admin/admin:country_code={cc}/{fname}")
    with _S3FS.open_input_file(path) as f:
        pf = pq.ParquetFile(f)
        geo = json.loads(pf.metadata.metadata[b"geo"])
        gcol = geo["columns"][geo["primary_column"]]
        return gcol["bbox"], pf.metadata.num_rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keys", help="file with parquet keys (else list S3)")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1]
                                         / "staging/predictions/vectors"))
    args = ap.parse_args(argv)

    keys = _read_keys(args.keys)
    # group by country code
    from collections import defaultdict
    by_cc = defaultdict(list)
    for k in keys:
        cc = k.split("admin:country_code=", 1)[1].split("/", 1)[0]
        fname = k.rsplit("/", 1)[-1]
        by_cc[cc].append(fname)

    out = Path(args.out)
    item_links, child_links = [], []
    n_items = 0
    for cc, fnames in sorted(by_cc.items()):
        is_split = len(fnames) > 1
        cdir = out / DATA_REL / f"admin:country_code={cc}"
        cdir.mkdir(parents=True, exist_ok=True)
        stems = []
        for fname in sorted(fnames):
            stem = fname[:-len(".parquet")]
            stems.append(stem)
            bbox, count = _parquet_meta(cc, fname)
            item = build_item(stem, cc, bbox, count, is_split=is_split)
            (cdir / f"{stem}.json").write_text(json.dumps(item, indent=2))
            (cdir / f"{stem}.style.json").write_text(json.dumps(item_style(stem), indent=2))
            n_items += 1
            if not is_split:
                item_links.append((stem, cc))
        # one llms.txt per country dir
        (cdir / "llms.txt").write_text(_country_llms(cc, stems))
        if is_split:
            cat = build_country_catalog(cc, stems)
            (cdir / "catalog.json").write_text(json.dumps(cat, indent=2))
            child_links.append(cc)
        print(f"{cc}: {len(fnames)} item(s){' [split]' if is_split else ''}")

    col = build_collection(item_links, child_links)
    out.mkdir(parents=True, exist_ok=True)
    (out / "collection.json").write_text(json.dumps(col, indent=2))
    (out / "llms.txt").write_text(_collection_llms(len(by_cc), n_items))
    print(f"\nOK: collection + {n_items} items across {len(by_cc)} countries "
          f"({len(child_links)} split) -> {out}")
    return 0


def _country_llms(cc, stems):
    name = _country_name(cc)
    lines = [f"# FTW field-boundary predictions — {name}", "",
             f"Country code: {cc}. Partitions: {len(stems)}.", "",
             CONFIDENCE_DOC, "",
             "## Files", *[f"- `{s}.parquet` (GeoParquet) + `{s}.pmtiles` (vector tiles)"
                          for s in stems]]
    return "\n".join(lines) + "\n"


def _collection_llms(n_countries, n_items):
    return "\n".join([
        "# FTW Global — Field Boundary Predictions (alpha)", "",
        f"{n_items} country/subdivision partitions across {n_countries} countries.",
        "GeoParquet partitioned by country; query the whole set with the glob "
        f"`{DATA_REL}/admin:country_code=*/*.parquet`.", "",
        "## Fields",
        "Field definitions use the wording of the fiboa core spec and vecorel "
        f"extensions ([fiboa core]({FIBOA_CORE}), [geometry-metrics]({VECOREL_METRICS}), "
        f"[administrative-division]({VECOREL_ADMIN})):",
        *[f"- `{c['name']}` ({c['type']}): {c['description']}" for c in TABLE_COLUMNS], "",
        "## Confidence", CONFIDENCE_DOC, "",
        "## Visualization",
        "Two collection PMTiles: 2025 (default) and 2024-with-confidence; per-country "
        "PMTiles per partition. Styles in `styles/` color by confidence (red→green, "
        "0–100) with the recommended >=69 filter.", "",
    ]) + "\n"


if __name__ == "__main__":
    sys.exit(main())
