"""Tests for scripts/add_confidence.py — per-polygon confidence enrichment.

Confidence is centroid-sampled from the 500 m confidence COG and scaled to a
0-100 percentage using 0.578178 as 100% (matching the ftw-inference-app legend);
nodata (-1) becomes null. The new `confidence` column is appended without
disturbing the original GeoParquet schema or its `geo` metadata.

Deterministic + offline: uses a tiny synthetic COG and parquet (no network).
SKIPs when pyarrow/rasterio/shapely aren't installed, matching the repo's
zero-setup local convention. Run: python3 tests/test_add_confidence.py
"""
import math
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "confidence"
sys.path.insert(0, str(SCRIPTS))


def _build_synthetic_cog(path, array, transform):
    import rasterio
    from rasterio.crs import CRS
    with rasterio.open(
        path, "w", driver="GTiff", height=array.shape[0], width=array.shape[1],
        count=1, dtype="float32", nodata=-1.0, crs=CRS.from_epsg(4326),
        transform=transform,
    ) as dst:
        dst.write(array, 1)


def _build_synthetic_parquet(path):
    """A minimal GeoParquet-like table: WKB geometry + bbox struct + a string
    column + a `geo` schema-metadata key, so we can assert nothing is lost."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    from shapely import to_wkb
    from shapely.geometry import box

    # Four 0.4-wide squares, centers land in the four synthetic raster cells.
    centers = [(0.5, 1.5), (1.5, 1.5), (0.5, 0.5), (1.5, 0.5)]
    geoms = [box(cx - 0.2, cy - 0.2, cx + 0.2, cy + 0.2) for cx, cy in centers]
    wkb = [to_wkb(g) for g in geoms]
    bbox = [{"xmin": g.bounds[0], "ymin": g.bounds[1],
             "xmax": g.bounds[2], "ymax": g.bounds[3]} for g in geoms]
    table = pa.table({
        "id": pa.array(["a", "b", "c", "d"]),
        "geometry": pa.array(wkb, pa.binary()),
        "bbox": pa.array(bbox, pa.struct([
            ("xmin", pa.float64()), ("ymin", pa.float64()),
            ("xmax", pa.float64()), ("ymax", pa.float64())])),
    })
    geo = ('{"version":"1.1.0","primary_column":"geometry","columns":'
           '{"geometry":{"encoding":"WKB","bbox":[0.3,0.3,1.7,1.7]}}}')
    table = table.replace_schema_metadata({b"geo": geo.encode()})
    pq.write_table(table, path)


def test_raw_to_confidence():
    import add_confidence as ac
    assert ac.raw_to_confidence(0.0) == 0.0
    assert abs(ac.raw_to_confidence(0.578178) - 100.0) < 1e-6
    assert abs(ac.raw_to_confidence(0.289089) - 50.0) < 1e-3
    assert ac.raw_to_confidence(0.633) == 100.0          # clamp above max
    assert ac.raw_to_confidence(-1.0) is None            # nodata
    assert ac.raw_to_confidence(None) is None


def test_sample_points():
    import numpy as np
    from affine import Affine
    import add_confidence as ac
    array = np.array([[0.0, 0.289089], [0.578178, -1.0]], dtype="float32")
    transform = Affine(1.0, 0.0, 0.0, 0.0, -1.0, 2.0)  # 1x1 px, origin (0,2)
    xs = [0.5, 1.5, 0.5, 1.5, 5.0]
    ys = [1.5, 1.5, 0.5, 0.5, 5.0]
    got = ac.sample_points(xs, ys, array, transform, nodata=-1.0)
    assert abs(got[0] - 0.0) < 1e-3
    assert abs(got[1] - 50.0) < 1e-3
    assert abs(got[2] - 100.0) < 1e-3      # float32 of 0.578178 isn't exact
    assert got[3] is None        # nodata cell
    assert got[4] is None        # out of bounds


def test_enrich_roundtrip():
    import numpy as np
    import pyarrow.parquet as pq
    from affine import Affine
    import add_confidence as ac
    array = np.array([[0.0, 0.289089], [0.578178, -1.0]], dtype="float32")
    transform = Affine(1.0, 0.0, 0.0, 0.0, -1.0, 2.0)
    with tempfile.TemporaryDirectory() as d:
        cog = Path(d) / "conf.tif"
        src = Path(d) / "in.parquet"
        out = Path(d) / "out.parquet"
        _build_synthetic_cog(cog, array, transform)
        _build_synthetic_parquet(src)

        ac.enrich(str(src), str(cog), str(out))

        t = pq.read_table(out)
        # original columns + metadata preserved, one new column added
        assert t.column_names == ["id", "geometry", "bbox", "confidence"]
        assert t.schema.field("confidence").type.equals(__import__("pyarrow").float32())
        assert b'"primary_column":"geometry"' in t.schema.metadata.get(b"geo")
        conf = t.column("confidence").to_pylist()
        assert abs(conf[0] - 0.0) < 1e-3
        assert abs(conf[1] - 50.0) < 1e-3
        assert abs(conf[2] - 100.0) < 1e-3
        assert conf[3] is None       # polygon over nodata cell


def main() -> int:
    try:
        import pyarrow  # noqa: F401
        import rasterio  # noqa: F401
        import shapely  # noqa: F401
        import numpy  # noqa: F401
        import affine  # noqa: F401
    except ImportError as e:
        print(f"SKIP: missing dep ({e.name}); confidence-enrichment tests skipped.")
        return 0

    tests = [test_raw_to_confidence, test_sample_points, test_enrich_roundtrip]
    failures = []
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failures.append(f"{t.__name__}: {type(e).__name__}: {e}")
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    if failures:
        print(f"\n{len(failures)}/{len(tests)} tests failed")
        return 1
    print(f"\nOK: {len(tests)} tests pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
