"""Dependency-free test of publisher file selection. Run: python3 tests/test_publish.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from publish import collect_uploads  # noqa: E402

def build_tree(tmp: Path):
    (tmp / "catalog.json").write_text("{}")
    (tmp / "llms.txt").write_text("x")
    (tmp / "README.md").write_text("x")
    (tmp / ".portolan").mkdir()
    (tmp / ".portolan/metadata.yaml").write_text("x")
    (tmp / ".portolan/config.yaml").write_text("x")  # must NOT publish
    (tmp / "scripts").mkdir()
    (tmp / "scripts/foo.py").write_text("x")          # must NOT publish
    c = tmp / "predictions/confidence"
    (c / "confidence").mkdir(parents=True)
    (c / "collection.json").write_text("{}")
    (c / "README.md").write_text("x")
    (c / "thumbnail.png").write_text("x")
    (c / "confidence/confidence.json").write_text("{}")
    v = tmp / "predictions/vectors"                    # scaffold, NOT enabled
    v.mkdir(parents=True)
    (v / "collection.json").write_text("{}")

def main():
    import tempfile
    manifest = {
        "write_prefix": "s3://bucket/ftw-global-data",
        "public_base": "https://data.source.coop/ftw/global-data",
        "region": "us-west-2",
        "root_files": ["catalog.json", "llms.txt", "README.md", ".portolan/metadata.yaml"],
        "publish_globs": ["**/*.json", "**/README.md", "**/llms.txt",
                          "**/thumbnail.png", "**/.portolan/metadata.yaml"],
        "collections": ["predictions/confidence"],
    }
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        build_tree(tmp)
        uploads = collect_uploads(manifest, tmp)
        rels = {u.local.relative_to(tmp).as_posix() for u in uploads}

    expected = {
        "catalog.json", "llms.txt", "README.md", ".portolan/metadata.yaml",
        "predictions/confidence/collection.json",
        "predictions/confidence/README.md",
        "predictions/confidence/thumbnail.png",
        "predictions/confidence/confidence/confidence.json",
    }
    forbidden = {
        ".portolan/config.yaml", "scripts/foo.py",
        "predictions/vectors/collection.json",  # not enabled
    }
    assert expected <= rels, f"missing: {expected - rels}"
    assert not (forbidden & rels), f"leaked: {forbidden & rels}"

    by_rel = {u.local.relative_to(tmp).as_posix(): u for u in uploads}
    assert by_rel["catalog.json"].s3_uri == "s3://bucket/ftw-global-data/catalog.json"
    assert by_rel["catalog.json"].content_type == "application/json"
    assert by_rel["predictions/confidence/confidence/confidence.json"].content_type == "application/geo+json"
    assert by_rel["predictions/confidence/thumbnail.png"].content_type == "image/png"
    assert by_rel["predictions/confidence/README.md"].content_type.startswith("text/markdown")
    print("OK: publisher selects metadata, excludes scripts/config/scaffolds")

if __name__ == "__main__":
    main()
