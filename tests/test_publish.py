"""Dependency-free test of publisher file selection. Run: python3 tests/test_publish.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from publish import collect_uploads  # noqa: E402


def build_tree(tmp: Path):
    # Repo-root files that must NOT publish (outside catalog/)
    (tmp / "README.md").write_text("github")
    (tmp / "README_next.md").write_text("draft")
    (tmp / "scripts").mkdir()
    (tmp / "scripts/foo.py").write_text("x")
    (tmp / "staging/predictions/vectors").mkdir(parents=True)
    (tmp / "staging/predictions/vectors/collection.json").write_text("{}")
    # The published catalog tree
    cat = tmp / "catalog"
    (cat / ".portolan").mkdir(parents=True)
    (cat / "catalog.json").write_text("{}")
    (cat / "llms.txt").write_text("x")
    (cat / "README.md").write_text("x")
    (cat / "versions.json").write_text("{}")
    (cat / ".portolan/metadata.yaml").write_text("x")
    (cat / ".portolan/config.yaml").write_text("x")   # internal, must NOT publish
    (cat / ".portolan/state.json").write_text("{}")    # internal, must NOT publish
    c = cat / "predictions/confidence"
    (c / "confidence").mkdir(parents=True)
    (c / "collection.json").write_text("{}")
    (c / "README.md").write_text("x")
    (c / "thumbnail.png").write_text("x")
    (c / "confidence/confidence.json").write_text("{}")


def main():
    import tempfile
    manifest = {
        "write_prefix": "s3://bucket/ftw-global-data",
        "public_base": "https://data.source.coop/ftw/global-data",
        "region": "us-west-2",
        "publish_dir": "catalog",
    }
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        build_tree(tmp)
        uploads = collect_uploads(manifest, tmp)
        rels = {u.local.relative_to(tmp / "catalog").as_posix() for u in uploads}

    expected = {
        "catalog.json", "llms.txt", "README.md", "versions.json",
        ".portolan/metadata.yaml",
        "predictions/confidence/collection.json",
        "predictions/confidence/README.md",
        "predictions/confidence/thumbnail.png",
        "predictions/confidence/confidence/confidence.json",
    }
    forbidden = {".portolan/config.yaml", ".portolan/state.json"}
    assert expected == rels, f"missing: {expected - rels}; leaked: {rels - expected}"
    assert not (forbidden & rels), f"leaked internal: {forbidden & rels}"

    by_rel = {u.local.relative_to(tmp / "catalog").as_posix(): u for u in uploads}
    assert by_rel["catalog.json"].s3_uri == "s3://bucket/ftw-global-data/catalog.json"
    assert by_rel["catalog.json"].content_type == "application/json"
    assert by_rel["predictions/confidence/confidence/confidence.json"].content_type == "application/geo+json"
    assert by_rel["predictions/confidence/thumbnail.png"].content_type == "image/png"
    assert by_rel["predictions/confidence/README.md"].content_type.startswith("text/markdown")
    assert by_rel["versions.json"].content_type == "application/json"
    assert by_rel[".portolan/metadata.yaml"].content_type.startswith("text/yaml")
    print("OK: publisher walks catalog/ 1:1, excludes root/staging/scripts and .portolan internals")


if __name__ == "__main__":
    main()
