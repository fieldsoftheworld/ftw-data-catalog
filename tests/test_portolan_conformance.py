"""Portolan 0.1 conformance gate via rashid.

Runs ``rashid check catalog --no-data --json`` and fails on any error EXCEPT a
short, documented allow-list:

  * ``PTL-LNK-006`` in two narrow places, both "link does not resolve to any file":

    - the per-year features collections' ``child`` links into the **MGRS browse
      grid** (``./<zone>/catalog.json``). The grid — ~700 catalogs and ~22.7k items
      per year — is generated straight to S3 by scripts/features/build_features_items.py
      and never committed, so the targets are absent from a git checkout while every
      one of them resolves in the published catalog. Portolan requires structural links
      to be relative (PTL-LNK-004), so an absolute href is not the way out; the spec is
      being evolved to cover a catalog whose generated parts live only at the publish
      base (rashid would need to resolve them against it, cf. ``--live-base-url``).
    - the large-country subdivision items — rashid rejects an item whose ``collection``
      link is not its direct parent, though a catalog between a collection and its items
      is what this catalog does. Tracked in https://github.com/portolan-sdi/rashid/issues/61.
      Dormant as of rashid 0.1.3 (fires zero findings); kept scoped in case it returns.
  * ``PTL-COL-005`` on the per-year features collections — "registers item mirror
    'geoparquet-items' but publishes no items". Same S3-only situation as the
    PTL-LNK-006 case above and exempted for the same reason: the ~22.7k item JSONs
    per year are generated straight to S3 and never committed, so a git checkout
    sees a collection with no items beside its STAC-GeoParquet mirror. Against the
    published catalog the items are there and normative. Scoped to those two files
    so a collection that genuinely ships only a mirror still fails.
  * Anything under the two zarr collections (``features/zarr``,
    ``predictions/zarr``) — they are being regenerated and are out of scope.
  * ``file:size`` / ``file:checksum`` (PTL-AST-003/004) on **remote** assets
    whose bytes are not in the repo — these are filled by the in-region
    ``backfill_file_meta.py`` remote pass. A missing checksum on a *local*
    (in-repo) asset is still a hard failure.

SKIPs (exit 0) when ``rashid`` isn't installed, so the local suite stays
zero-setup; CI installs rashid and enforces this. ``--no-data`` keeps the run
offline. Run: python3 tests/test_portolan_conformance.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / "catalog"
DEFERRED_DIRS = ("features/zarr", "predictions/zarr")
FILE_FIELD_RULES = {"PTL-AST-003", "PTL-AST-004"}

# PTL-LNK-006 is accepted only on these two shapes — never blanket, or a genuinely
# broken structural link elsewhere would sail through. See the module docstring.
GRID_PARENT_RE = re.compile(r"^features/(2024|2025)/collection\.json$")
# PTL-COL-005 rides on the same S3-only-items fact, on the same two files.
MIRROR_WITHOUT_ITEMS_RE = GRID_PARENT_RE
GRID_CHILD_RE = re.compile(r"^\./[0-6][0-9]/catalog\.json$")
SUBDIVISION_RE = re.compile(r"^predictions/vectors/.*/results-by-admin")


def _accepted_lnk_006(finding: dict) -> bool:
    """True for the two documented unresolvable-link cases, false for everything else."""
    if finding.get("rule_id") != "PTL-LNK-006":
        return False
    path = finding.get("path", "").replace("\\", "/")
    if GRID_PARENT_RE.match(path) and GRID_CHILD_RE.match(str(finding.get("actual", ""))):
        return True
    return bool(SUBDIVISION_RE.match(path))


def _accepted_col_005(finding: dict) -> bool:
    """True for the per-year features collections whose items are S3-only."""
    if finding.get("rule_id") != "PTL-COL-005":
        return False
    return bool(MIRROR_WITHOUT_ITEMS_RE.match(finding.get("path", "").replace("\\", "/")))


def _under_deferred(path: str) -> bool:
    p = path.replace("\\", "/")
    return any(p == d or p.startswith(d + "/") for d in DEFERRED_DIRS)


def _asset_is_remote(finding: dict) -> bool:
    """True when the finding's asset is not a file present in the repo."""
    pointer = finding.get("json_pointer", "")
    parts = pointer.strip("/").split("/")
    if len(parts) < 2 or parts[0] != "assets":
        return True  # can't tie it to a local file; treat as remote/pending
    key = parts[1]
    obj_path = CATALOG / finding["path"]
    try:
        asset = json.loads(obj_path.read_text())["assets"][key]
    except (OSError, KeyError, json.JSONDecodeError):
        return True
    href = str(asset.get("href", ""))
    if "://" in href:
        return True  # absolute (remote) href
    return not (obj_path.parent / href).is_file()  # relative -> local file?


def main() -> int:
    rashid = shutil.which("rashid")
    if rashid is None:
        print("SKIP: rashid not installed; Portolan conformance not checked "
              "(CI installs it and enforces this).")
        return 0

    proc = subprocess.run(
        [rashid, "check", str(CATALOG), "--no-data", "--json"],
        capture_output=True, text=True,
    )
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print("FAIL: could not parse rashid JSON output:\n" + (proc.stderr or proc.stdout))
        return 1

    real, accepted = [], 0
    for f in report.get("findings", []):
        if f.get("severity") != "error":
            continue
        rid, path = f.get("rule_id"), f.get("path", "")
        if _under_deferred(path) or _accepted_lnk_006(f) or _accepted_col_005(f):
            accepted += 1
            continue
        if rid in FILE_FIELD_RULES and _asset_is_remote(f):
            accepted += 1
            continue
        real.append(f"{rid}  {path}  {f.get('message', '')}")

    if real:
        for line in real[:50]:
            print(f"FAIL {line}")
        if len(real) > 50:
            print(f"... and {len(real) - 50} more")
        print(f"\n{len(real)} unexpected conformance error(s) "
              f"({accepted} accepted/deferred)")
        return 1
    print(f"OK: Portolan 0.1 conformant ({accepted} accepted/deferred findings "
          "allow-listed: S3-only features grid, rashid#61, zarr regen, "
          "remote checksums pending)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
