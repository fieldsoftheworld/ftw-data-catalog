#!/usr/bin/env python3
"""Backfill ``file:size`` and multihash ``file:checksum`` on every asset.

Portolan 0.1 (PORTO-CORE-028/029) requires every asset to carry ``file:size``
(byte count) and ``file:checksum`` encoded as a multihash: ``1220`` (sha2-256,
32 bytes) followed by the 64-char sha256 hex digest.

Assets fall into two groups:

* **Local** — files that live in this repo (style JSON, README.md, llms.txt,
  the confidence thumbnail). Hashed straight off disk. Fast, no network.
* **Remote** — the data on Source Cooperative (GeoParquet, PMTiles, COGs,
  stac-geoparquet mirrors, remote thumbnails). Their bytes are not in the repo,
  so ``file:size`` / ``file:checksum`` require reading them. Prefer running this
  pass in us-west-2 / on Rails against the S3 source (``--via s3``) so the
  reads stay in-region.

Typical use:

    # fast, in-repo assets only (safe to run anywhere)
    python3 scripts/migrate/backfill_file_meta.py --local-only

    # remote pass, in-region, reading the S3 source bucket
    python3 scripts/migrate/backfill_file_meta.py \
        --via s3 \
        --s3-prefix s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data/

    # remote pass over public https (works anywhere, egresses bytes)
    python3 scripts/migrate/backfill_file_meta.py

The run is resumable: assets that already carry both fields are skipped unless
``--force`` is given. The two zarr collections are skipped (being regenerated).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PUBLIC_BASE = "https://data.source.coop/ftw/global-data/"
EXCLUDED = ("features/zarr", "predictions/zarr")
CHUNK = 1 << 20  # 1 MiB

STATS: dict[str, int] = {}
_LOCK = threading.Lock()


def bump(key: str, n: int = 1) -> None:
    with _LOCK:
        STATS[key] = STATS.get(key, 0) + n


def multihash(hexdigest: str) -> str:
    """sha2-256 multihash: 0x12 (code) 0x20 (length 32) + digest, as hex."""
    return "1220" + hexdigest


# --------------------------------------------------------------------------- #
# byte sources
# --------------------------------------------------------------------------- #
def hash_stream(reader) -> tuple[int, str]:
    h = hashlib.sha256()
    size = 0
    while True:
        chunk = reader.read(CHUNK)
        if not chunk:
            break
        size += len(chunk)
        h.update(chunk)
    return size, multihash(h.hexdigest())


def hash_local(path: Path) -> tuple[int, str]:
    with open(path, "rb") as fh:
        return hash_stream(fh)


def _encode_url(url: str) -> str:
    """Percent-encode a URL path/query so non-ASCII hrefs (e.g. Türkiye) are
    valid in the HTTP request line."""
    from urllib.parse import quote, urlsplit, urlunsplit
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, quote(p.path), quote(p.query, safe="=&"), p.fragment))


def hash_https(url: str) -> tuple[int, str]:
    req = urllib.request.Request(_encode_url(url), headers={"User-Agent": "ftw-catalog-backfill"})
    with urllib.request.urlopen(req) as resp:  # noqa: S310 - trusted catalog hosts
        return hash_stream(resp)


def hash_s3(uri: str):
    import boto3  # imported lazily so --local-only needs no deps

    assert uri.startswith("s3://")
    bucket, _, key = uri[len("s3://"):].partition("/")
    body = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"]
    return hash_stream(body)


# --------------------------------------------------------------------------- #
# asset href resolution
# --------------------------------------------------------------------------- #
def is_excluded(rel_path: str) -> bool:
    rel = rel_path.replace("\\", "/")
    return any(rel == d or rel.startswith(d + "/") for d in EXCLUDED)


def iter_stac_files(catalog: Path):
    for path in sorted(catalog.rglob("*.json")):
        rel = path.relative_to(catalog).as_posix()
        if rel.startswith(".portolan/") or "/.portolan/" in f"/{rel}":
            continue
        if is_excluded(rel):
            continue
        try:
            obj = json.loads(path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(obj, dict) or obj.get("type") not in ("Collection", "Feature"):
            continue
        yield path, obj


def remote_rel(catalog: Path, path: Path, href: str) -> str:
    """POSIX path of a relative asset href, relative to the catalog root."""
    return (path.parent.relative_to(catalog) / href).as_posix()


def resolve(catalog: Path, path: Path, href: str, args) -> tuple[str, str] | None:
    """Return (kind, locator) where kind is 'local' | 'https' | 's3'."""
    if "://" in href:
        if href.startswith("s3://"):
            return ("s3", href)
        # absolute https
        if args.via == "s3" and href.startswith(PUBLIC_BASE):
            return ("s3", args.s3_prefix.rstrip("/") + "/" + href[len(PUBLIC_BASE):])
        return ("https", href)
    # relative href
    local = (path.parent / href).resolve()
    if local.exists() and local.is_file():
        return ("local", str(local))
    rel = remote_rel(catalog, path, href)
    if args.via == "s3":
        return ("s3", args.s3_prefix.rstrip("/") + "/" + rel)
    return ("https", args.base_url.rstrip("/") + "/" + rel)


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def process_file(catalog: Path, path: Path, obj: dict, args) -> bool:
    changed = False
    for key, asset in (obj.get("assets") or {}).items():
        if not isinstance(asset, dict) or not asset.get("href"):
            continue
        if not args.force and asset.get("file:size") and asset.get("file:checksum"):
            bump("skipped_present")
            continue
        if any(s in asset["href"] for s in args.skip_href):
            bump("skipped_deferred")
            continue
        target = resolve(catalog, path, asset["href"], args)
        if target is None:
            continue
        kind, locator = target
        if kind != "local" and args.local_only:
            bump("skipped_remote")
            continue
        try:
            if kind == "local":
                size, checksum = hash_local(Path(locator))
            elif kind == "https":
                size, checksum = hash_https(locator)
            else:
                size, checksum = hash_s3(locator)
        except Exception as exc:  # noqa: BLE001 - report and continue
            bump("errors")
            print(f"  ! {path.relative_to(catalog)} [{key}] {kind} {locator}: {exc}", file=sys.stderr)
            continue
        asset["file:size"] = size
        asset["file:checksum"] = checksum
        bump(f"hashed_{kind}")
        changed = True
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", default="catalog", help="path to the catalog root")
    ap.add_argument("--local-only", action="store_true", help="hash only files present in the repo")
    ap.add_argument("--via", choices=["https", "s3"], default="https", help="remote byte source")
    ap.add_argument("--base-url", default=PUBLIC_BASE, help="public https base for relative hrefs")
    ap.add_argument("--s3-prefix", default="", help="s3:// prefix mapping the public base (for --via s3)")
    ap.add_argument("--force", action="store_true", help="recompute even when both fields are present")
    ap.add_argument("--workers", type=int, default=1, help="parallel file workers (I/O bound; try 16 for remote)")
    ap.add_argument("--skip-href", action="append", default=[],
                    help="skip assets whose href contains this substring (repeatable; e.g. huge/regenerating files)")
    args = ap.parse_args()

    if args.via == "s3" and not args.s3_prefix:
        ap.error("--via s3 requires --s3-prefix")

    catalog = Path(args.catalog).resolve()
    if not (catalog / "catalog.json").exists():
        raise SystemExit(f"no catalog.json under {catalog}")

    def handle(item):
        path, obj = item
        if process_file(catalog, path, obj, args):
            path.write_text(json.dumps(obj, indent=2, ensure_ascii=True) + "\n")
            bump("files_written")

    files = list(iter_stac_files(catalog))
    if args.workers > 1:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            list(pool.map(handle, files))
    else:
        for item in files:
            handle(item)

    width = max((len(k) for k in STATS), default=0)
    mode = "local-only" if args.local_only else f"local+{args.via}"
    print(f"file:size / file:checksum backfill ({mode}):")
    for key in sorted(STATS):
        print(f"  {key.ljust(width)}  {STATS[key]}")
    if not STATS:
        print("  no assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
