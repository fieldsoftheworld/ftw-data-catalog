"""Tests for scripts/build_vector_items.py — STAC generation for the field-
boundary prediction-vectors collection (per-parquet items, split-country
sub-catalogs, glob data asset, confidence provenance docs).

Pure-function tests, no network. SKIPs if pycountry isn't installed.
Run: python3 tests/test_build_vector_items.py
"""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def test_bbox_to_polygon():
    import build_vector_items as b
    poly = b.bbox_to_polygon([1.0, 42.0, 1.5, 42.5])
    assert poly["type"] == "Polygon"
    ring = poly["coordinates"][0]
    assert ring[0] == ring[-1]            # closed
    assert [1.0, 42.0] in ring and [1.5, 42.5] in ring


def test_title_for_single_file_country():
    import build_vector_items as b
    # Andorra is a single-file country (stem == country name in data)
    assert b.title_for("Andorra", "AD") == "Andorra"
    assert b.title_for("France", "FR") == "France"


def test_title_for_split_subdivision():
    import build_vector_items as b
    # stem uses underscore; ISO 3166-2 uses hyphen -> "New South Wales"
    t = b.title_for("AU_NSW", "AU")
    assert "New South Wales" in t and "Australia" in t


def test_build_item_structure_and_relative_hrefs():
    import build_vector_items as b
    item = b.build_item(stem="Andorra", country_code="AD",
                        bbox=[1.0, 42.0, 1.5, 42.5], feature_count=85)
    assert item["type"] == "Feature"
    assert item["id"] == "Andorra"
    assert item["properties"]["title"] == "Andorra"
    assert item["properties"]["geoparquet:feature_count"] == 85
    # data + pmtiles assets are colocated (relative) with the item JSON
    assert item["assets"]["data"]["href"] == "./Andorra.parquet"
    assert item["assets"]["pmtiles"]["href"] == "./Andorra.pmtiles"
    assert "visual" in item["assets"]["pmtiles"]["roles"]
    # confidence provenance is documented somewhere on the item
    blob = (item["properties"].get("description", "") + str(item["properties"]))
    assert "confidence" in blob.lower()


def test_build_collection_has_glob_and_two_pmtiles_and_styles():
    import build_vector_items as b
    col = b.build_collection(item_links=[("Andorra", "AD")], child_links=["AU"])
    assert col["type"] == "Collection"
    # must carry links incl. an item link and a child link (stac-check needs links)
    assert col["links"], "collection missing links"
    rels = [l["rel"] for l in col["links"]]
    assert "item" in rels and "child" in rels and "self" in rels
    # partition extension present
    assert any("partition" in e for e in col["stac_extensions"])
    # glob data asset over results-by-admin-conf
    glob = col["assets"]["data"]["href"]
    assert "results-by-admin-conf" in glob and glob.endswith("*.parquet")
    # two visual pmtiles, default flagged on the 2025 one
    assert "pmtiles_2025" in col["assets"] and "pmtiles_2024_confidence" in col["assets"]
    # two style assets with role style
    styles = [k for k, v in col["assets"].items() if "style" in v.get("roles", [])]
    assert len(styles) >= 2
    # confidence method + GitHub script link documented
    assert "add_confidence.py" in col["description"]
    assert "github.com/fieldsoftheworld/ftw-portolan" in col["description"]


def main() -> int:
    try:
        import pycountry  # noqa: F401
    except ImportError as e:
        print(f"SKIP: missing dep ({e.name}); build_vector_items tests skipped.")
        return 0
    tests = [test_bbox_to_polygon, test_title_for_single_file_country,
             test_title_for_split_subdivision,
             test_build_item_structure_and_relative_hrefs,
             test_build_collection_has_glob_and_two_pmtiles_and_styles]
    failures = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failures.append(t.__name__); print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    if failures:
        print(f"\n{len(failures)}/{len(tests)} failed"); return 1
    print(f"\nOK: {len(tests)} tests pass"); return 0


if __name__ == "__main__":
    sys.exit(main())
