#!/usr/bin/env python3
"""Metadata-only publisher for the FTW Portolan catalog.

Reads catalog.publish.yaml and uploads everything under the configured publish_dir
(the catalog/ tree) 1:1 to S3, skipping only .portolan/config.yaml and
.portolan/state.json. Never uploads data (*.tif/*.parquet/*.zarr), scripts/, or config.

Usage:
  python3 scripts/publish.py            # dry run (prints planned uploads)
  python3 scripts/publish.py --confirm  # execute aws s3 cp
"""
from __future__ import annotations
import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_CT_BY_NAME = {"catalog.json": "application/json", "collection.json": "application/json",
               "versions.json": "application/json"}
_CT_BY_SUFFIX = {
    ".json": "application/geo+json",  # items; catalog/collection overridden by name
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/markdown; charset=utf-8",  # llms.txt
    ".png": "image/png",
    ".yaml": "text/yaml; charset=utf-8",
    ".yml": "text/yaml; charset=utf-8",
}


@dataclass(frozen=True)
class Upload:
    local: Path
    s3_uri: str
    content_type: str


def _content_type(p: Path) -> str:
    if p.name in _CT_BY_NAME:
        return _CT_BY_NAME[p.name]
    return _CT_BY_SUFFIX.get(p.suffix, "application/octet-stream")


def collect_uploads(manifest: dict, root: Path) -> list[Upload]:
    write_prefix = manifest["write_prefix"].rstrip("/")
    pub_dir = root / manifest.get("publish_dir", "catalog")
    skip = {".portolan/config.yaml", ".portolan/state.json"}

    uploads = []
    if not pub_dir.is_dir():
        return uploads
    for p in sorted(pub_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(pub_dir).as_posix()
        if rel in skip:
            continue
        uploads.append(Upload(local=p, s3_uri=f"{write_prefix}/{rel}",
                              content_type=_content_type(p)))
    return uploads


def _load_manifest(root: Path) -> dict:
    import json
    text = (root / "catalog.publish.yaml").read_text()
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except ModuleNotFoundError:
        pass
    # Minimal YAML fallback (flat scalars + simple "- item" lists) so the
    # publisher has zero third-party dependencies.
    data: dict = {}
    key = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("- "):
            item = line.lstrip()[2:].strip().strip('"')
            data.setdefault(key, []).append(item)
        elif ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            key = k.strip()
            v = v.strip()
            data[key] = json.loads(v) if v.startswith("[") else (v.strip('"') if v else [])
    return data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--confirm", action="store_true", help="execute uploads (default: dry run)")
    args = ap.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    manifest = _load_manifest(root)
    region = manifest.get("region", "us-west-2")
    uploads = collect_uploads(manifest, root)

    if not uploads:
        print("No files to publish (check publish_dir in catalog.publish.yaml).")
        return 0

    for u in uploads:
        if args.confirm:
            print(f"upload: {u.local.relative_to(root)} -> {u.s3_uri}")
            subprocess.run(
                ["aws", "s3", "cp", str(u.local), u.s3_uri,
                 "--region", region, "--content-type", u.content_type],
                check=True,
            )
        else:
            print(f"DRYRUN {u.s3_uri}  ({u.content_type})")
    if not args.confirm:
        print(f"\n{len(uploads)} files. Re-run with --confirm to upload.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
