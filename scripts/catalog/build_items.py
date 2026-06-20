#!/usr/bin/env python3
"""Generate the 5 STAC items for the FTW Global predictions/confidence collection.

Reads each Cloud-Optimized GeoTIFF's header (over the network, header-only) to extract
projection + band metadata, then writes self-contained STAC 1.1 items into portolan's
item-directory layout under predictions/confidence/.  Asset hrefs are RELATIVE
(./<file>.tif) so the tree is valid both locally and once the COGs are colocated at the
S3 prefix.  Rerunnable.

All descriptions are grounded in Robinson et al. 2026 (arXiv:2605.11055); nothing invented.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

import rasterio

os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")

ROOT = Path(__file__).resolve().parents[1]  # repo root (scripts/ -> ..)
COLL_REL = "predictions/confidence"
COLL_DIR = ROOT / COLL_REL
PUBLIC_BASE = "https://data.source.coop/ftw/global-data/predictions/confidence"

PROJ_EXT = "https://stac-extensions.github.io/projection/v2.0.0/schema.json"
RENDER_EXT = "https://stac-extensions.github.io/render/v1.0.0/schema.json"

# STAC render extension: named, pickable colormap/rescale styles per item, applied to a
# COG band directly by the deck.gl renderer (no tile server). colormap_name values map to
# built-in ramps in portolan-browser (rdylgn, ftw_density, magma, ylgn, viridis).
RENDERS = {
    "confidence": {
        "confidence": {
            "title": "Confidence (red → green)",
            "assets": ["data"], "bidx": [1],
            "rescale": [[0, 0.578178]], "colormap_name": "rdylgn", "nodata": -1,
        },
    },
    "field-density": {
        "field_density": {
            "title": "Field density (magenta → green)",
            "assets": ["fields_only"], "bidx": [1],
            "rescale": [[0, 1500]], "colormap_name": "ftw_density", "nodata": 0,
        },
        "boundary_density": {
            "title": "Boundary density",
            "assets": ["field_boundary"], "bidx": [2],
            "rescale": [[0, 800]], "colormap_name": "magma", "nodata": 0,
        },
    },
    "entropy": {
        "entropy_field": {
            "title": "Field entropy",
            "assets": ["data"], "bidx": [1],
            "rescale": [[0, 20]], "colormap_name": "magma",
        },
        "entropy_boundary": {
            "title": "Boundary entropy",
            "assets": ["data"], "bidx": [2],
            "rescale": [[0, 20]], "colormap_name": "magma",
        },
    },
    "crop-consensus": {
        "crop_consensus": {
            "title": "Cropland consensus (0–8)",
            "assets": ["data"], "bidx": [1],
            "rescale": [[0, 8]], "colormap_name": "ylgn", "nodata": 0,
        },
    },
    "precision-recall": {
        "precision_ge2": {
            "title": "Precision (≥ 2 datasets)",
            "assets": ["data"], "bidx": [1],
            "rescale": [[0, 1]], "colormap_name": "viridis",
        },
        "recall_ge2": {
            "title": "Recall (≥ 2 datasets)",
            "assets": ["data"], "bidx": [2],
            "rescale": [[0, 1]], "colormap_name": "viridis",
        },
    },
}

# Temporal: inferred from the paper (all quality-layer figures + the retention curve are 2025).
START_DT = "2024-01-01T00:00:00Z"  # growing seasons feeding the 2025 product begin late 2024
END_DT = "2025-12-31T23:59:59Z"
# Global footprint of the 500 m grid (EPSG:4326).
BBOX = [-180.0, -60.0, 180.0, 84.0]
GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[-180.0, -60.0], [180.0, -60.0], [180.0, 84.0], [-180.0, 84.0], [-180.0, -60.0]]],
}
TIF = "image/tiff; application=geotiff; profile=cloud-optimized"

# ---- Per-asset band documentation (grounded in the paper). ----------------------------
# Each asset: file, roles, title, description, and per-band [(name, description, unit)].
ITEMS = {
    "confidence": {
        "title": "Modeled confidence layer (500 m)",
        "description": (
            "Per-500 m-cell modeled confidence that the "
            "[PRUE](https://github.com/fieldsoftheworld/ftw-baselines/releases) "
            "field predictions are reliable, from a Random Forest trained on model-internal quality "
            "indicators (entropy and prediction density) over the 24 "
            "[Fields of The World](https://fieldsofthe.world)-labelled "
            "countries, using only model-derived features and a cropland-consensus filter for "
            "negatives (leave-one-country-out mean AUC 0.842). Higher values indicate predictions "
            "whose statistical signature matches areas with ground-truth fields. Recommended default "
            "filter conf >= 0.4; conservative conf >= 0.5. Cell-level reliability, not a measure of "
            "individual-polygon geometric accuracy. Temporal basis inferred as 2025 from the "
            "[paper](https://arxiv.org/abs/2605.11055); pending author confirmation."
        ),
        "assets": {
            "data": {
                "file": "prue_v1_confidence_global.tif",
                "roles": ["data"],
                "title": "Confidence score (EPSG:4326, float32)",
                "bands": [("confidence", "Modeled confidence score (0 to ~0.578)", None)],
            },
            "visual": {
                "file": "prue_v1_confidence_global_uint8_3857.tif",
                "roles": ["visual", "overview"],
                "title": "Confidence score, 8-bit web-mercator (display)",
                "bands": [("confidence_uint8", "Confidence rescaled to 8-bit for web display", None)],
            },
        },
    },
    "field-density": {
        "title": "Field & boundary prediction density (500 m)",
        "description": (
            "Count of 10 m model pixels classified as field interior and field boundary within "
            "each 500 m cell (theoretical max 2500 = 50x50 pixels). Provided unfiltered, "
            "confidence-filtered at the default (conf >= 0.4) and conservative (conf >= 0.5) "
            "thresholds, a default 'filtered' product, and a single-band fields-only variant; a "
            "web-mercator 8-bit rendering is included for display. Use as a per-cell field-area "
            "weight or filterable density surface. See [Robinson et al. 2026]"
            "(https://arxiv.org/abs/2605.11055). Temporal basis inferred as 2025; pending "
            "author confirmation."
        ),
        "assets": {
            "field_boundary": {
                "file": "prue_v1_field_area_500m.tif",
                "roles": ["data"],
                "title": "Field & boundary pixel count, unfiltered",
                "bands": [
                    ("field_pixel_count", "Count of field-interior 10 m pixels per 500 m cell", None),
                    ("boundary_pixel_count", "Count of field-boundary 10 m pixels per 500 m cell", None),
                ],
            },
            "field_boundary_conf0.4": {
                "file": "prue_v1_field_area_500m_conf0.4.tif",
                "roles": ["data"],
                "title": "Field & boundary pixel count, confidence >= 0.4 (default filter)",
                "bands": [
                    ("field_pixel_count_conf0.4", "Field-interior pixel count, cells with confidence >= 0.4", None),
                    ("boundary_pixel_count_conf0.4", "Field-boundary pixel count, cells with confidence >= 0.4", None),
                ],
            },
            "field_boundary_conf0.5": {
                "file": "prue_v1_field_area_500m_conf0.5.tif",
                "roles": ["data"],
                "title": "Field & boundary pixel count, confidence >= 0.5 (conservative)",
                "bands": [
                    ("field_pixel_count_conf0.5", "Field-interior pixel count, cells with confidence >= 0.5", None),
                    ("boundary_pixel_count_conf0.5", "Field-boundary pixel count, cells with confidence >= 0.5", None),
                ],
            },
            "field_boundary_filtered": {
                "file": "prue_v1_field_area_500m_filtered.tif",
                "roles": ["data"],
                "title": "Field & boundary pixel count, default filtered",
                "bands": [
                    ("field_pixel_count_filtered", "Field-interior pixel count, default confidence-filtered (exact threshold pending author confirmation)", None),
                    ("boundary_pixel_count_filtered", "Field-boundary pixel count, default confidence-filtered (exact threshold pending author confirmation)", None),
                ],
            },
            "fields_only": {
                "file": "prue_v1_field_area_500m_fieldsonly.tif",
                "roles": ["data"],
                "title": "Field pixel count only (single band)",
                "bands": [("field_pixel_count", "Count of field-interior 10 m pixels per 500 m cell", None)],
            },
            "visual": {
                "file": "prue_v1_field_area_500m_fieldsonly_uint8_3857.tif",
                "roles": ["visual", "overview"],
                "title": "Field density, 8-bit web-mercator (display)",
                "bands": [("field_density_uint8", "Field pixel count rescaled to 8-bit for web display", None)],
            },
        },
    },
    "entropy": {
        "title": "Model entropy (500 m)",
        "description": (
            "Mean Shannon entropy of the PRUE softmax outputs across the 10 m pixels in each "
            "500 m cell, computed separately for the field and field-boundary classes. A "
            "model-internal uncertainty indicator (higher = less certain) used as a feature of "
            "the confidence model. See the Methods (Quality indicator computation) of "
            "[Robinson et al. 2026](https://arxiv.org/abs/2605.11055). Temporal "
            "basis inferred as 2025; pending author confirmation."
        ),
        "assets": {
            "data": {
                "file": "prue_v1_entropy_500m.tif",
                "roles": ["data"],
                "title": "Model entropy (field & boundary)",
                "bands": [
                    ("mean_entropy_field", "Mean per-pixel Shannon entropy of the field class within the cell", None),
                    ("mean_entropy_boundary", "Mean per-pixel Shannon entropy of the field-boundary class within the cell", None),
                ],
            },
        },
    },
    "crop-consensus": {
        "title": "Cropland consensus count (500 m)",
        "description": (
            "Mean per-cell agreement of eight independent global cropland datasets (ASAP Crop "
            "Mask, GlobCover 2009, ESA CCI Land Cover 2020, Copernicus Global Land Cover 100 m, "
            "GLAD Cropland 2019, Esri 10 m LULC 2021, Digital Earth Africa 2019, ESA WorldCereal "
            "2021), each binarised to cropland/non-cropland, reprojected to the ESA WorldCover "
            "10 m grid and aggregated to 500 m. Range 0-8 (practical max 7 outside Africa, where "
            "Digital Earth Africa is unavailable). An external reference layer, year-independent; "
            "used to construct confidence-model negatives and the precision/recall layers. See "
            "[Robinson et al. 2026](https://arxiv.org/abs/2605.11055)."
        ),
        "assets": {
            "data": {
                "file": "prue_v1_crop_count_mean_500m.tif",
                "roles": ["data"],
                "title": "Cropland consensus count",
                "bands": [("crop_count_mean", "Mean number of agreeing cropland datasets (0-8)", None)],
            },
        },
    },
    "precision-recall": {
        "title": "Precision & recall vs cropland agreement (500 m)",
        "description": (
            "Per-cell precision and recall of the field predictions against the cropland-consensus "
            "agreement layer at two agreement thresholds. precision = |field & cropland| / |field|; "
            "recall = |field & cropland| / |cropland|, restricted to pixels within the cell. The "
            "'gt1' bands use cropland agreement of >= 2 datasets and 'gt2' use >= 3 datasets "
            "(the k in {2,3} of [Robinson et al. 2026](https://arxiv.org/abs/2605.11055)). "
            "Temporal basis inferred as 2025; pending author confirmation."
        ),
        "assets": {
            "data": {
                "file": "prue_v1_precision_recall_500m.tif",
                "roles": ["data"],
                "title": "Precision & recall vs cropland agreement",
                "bands": [
                    ("precision_gt1", "Precision vs cropland agreement >= 2 datasets", None),
                    ("recall_gt1", "Recall vs cropland agreement >= 2 datasets", None),
                    ("precision_gt2", "Precision vs cropland agreement >= 3 datasets", None),
                    ("recall_gt2", "Recall vs cropland agreement >= 3 datasets", None),
                ],
            },
        },
    },
}


def stats_for_band(ds, bidx: int) -> dict | None:
    """Prefer embedded STATISTICS_* tags; else compute from a decimated read (nodata-masked)."""
    tags = ds.tags(bidx)
    if "STATISTICS_MINIMUM" in tags:
        out = {
            "minimum": float(tags["STATISTICS_MINIMUM"]),
            "maximum": float(tags["STATISTICS_MAXIMUM"]),
            "mean": float(tags["STATISTICS_MEAN"]),
            "stddev": float(tags["STATISTICS_STDDEV"]),
        }
        if "STATISTICS_VALID_PERCENT" in tags:
            out["valid_percent"] = float(tags["STATISTICS_VALID_PERCENT"])
        return out
    # Decimated read (~1/64) masked by nodata.
    import numpy as np
    h = max(1, ds.height // 64)
    w = max(1, ds.width // 64)
    arr = ds.read(bidx, out_shape=(h, w), masked=True)
    if ds.nodata is not None:
        arr = np.ma.masked_equal(arr, ds.nodata)
    if arr.count() == 0:
        return None
    return {
        "minimum": float(arr.min()),
        "maximum": float(arr.max()),
        "mean": float(arr.mean()),
        "stddev": float(arr.std()),
    }


def _cog_url(item_id: str, fname: str) -> str:
    """Prefer the restructured item-dir path; fall back to the flat layout."""
    import urllib.request
    for cand in (f"{PUBLIC_BASE}/{item_id}/{fname}", f"{PUBLIC_BASE}/{fname}"):
        try:
            req = urllib.request.Request(cand, method="HEAD", headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=30):
                return cand
        except Exception:
            continue
    return f"{PUBLIC_BASE}/{item_id}/{fname}"


def build_item(item_id: str, spec: dict) -> dict:
    assets = {}
    epsgs = set()
    for key, aspec in spec["assets"].items():
        url = _cog_url(item_id, aspec["file"])  # item-dir (post-restructure) or flat fallback
        with rasterio.open(url) as ds:
            epsg = ds.crs.to_epsg()
            epsgs.add(epsg)
            transform = list(ds.transform)[:6] + [0.0, 0.0, 1.0]
            proj_bbox = [ds.bounds.left, ds.bounds.bottom, ds.bounds.right, ds.bounds.top]
            shape = [ds.height, ds.width]
            res = round((abs(ds.transform.a) + abs(ds.transform.e)) / 2, 6)
            bands = []
            for i, (name, desc, unit) in enumerate(aspec["bands"], start=1):
                b = {"name": name, "description": desc, "data_type": str(ds.dtypes[i - 1])}
                nd = ds.nodatavals[i - 1]
                if nd is not None:
                    b["nodata"] = nd
                if unit:
                    b["unit"] = unit
                st = stats_for_band(ds, i)
                if st:
                    b["statistics"] = st
                bands.append(b)
        assets[key] = {
            "href": f"./{aspec['file']}",
            "type": TIF,
            "title": aspec["title"],
            "roles": aspec["roles"] + ["cloud-optimized"],
            "proj:code": f"EPSG:{epsg}",
            "proj:shape": shape,
            "proj:transform": transform,
            "proj:bbox": proj_bbox,
            "bands": bands,
        }
        print(f"  asset {key}: EPSG:{epsg} {shape} {len(bands)} band(s)")

    assets["documentation"] = {
        "href": "./llms.txt",
        "type": "text/markdown",
        "title": "Agent/LLM usage guide",
        "roles": ["documentation"],
    }
    item = {
        "type": "Feature",
        "stac_version": "1.1.0",
        "stac_extensions": [PROJ_EXT, RENDER_EXT],
        "id": item_id,
        "geometry": GEOMETRY,
        "bbox": BBOX,
        "properties": {
            "title": spec["title"],
            "description": spec["description"],
            "datetime": None,
            "start_datetime": START_DT,
            "end_datetime": END_DT,
            "gsd": 500,
            "ftw:temporal_basis": "inferred 2025 from paper; pending author confirmation",
        },
        "collection": "confidence",
        "renders": RENDERS[item_id],
        "links": [
            {"rel": "root", "href": "../../../catalog.json", "type": "application/json"},
            {"rel": "collection", "href": "../collection.json", "type": "application/json"},
            {"rel": "parent", "href": "../collection.json", "type": "application/json"},
            {"rel": "self", "href": f"{PUBLIC_BASE}/{item_id}/{item_id}.json", "type": "application/geo+json"},
            {"rel": "llms", "href": "./llms.txt", "type": "text/markdown", "title": "Agent/LLM usage guide"},
        ],
        "assets": assets,
    }
    return item


def main() -> None:
    for item_id, spec in ITEMS.items():
        print(f"Building item: {item_id}")
        item = build_item(item_id, spec)
        out_dir = COLL_DIR / item_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{item_id}.json"
        out_path.write_text(json.dumps(item, indent=2) + "\n")
        print(f"  -> {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
