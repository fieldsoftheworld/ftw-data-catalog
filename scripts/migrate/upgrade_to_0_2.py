#!/usr/bin/env python3
"""Migrate the FTW catalog metadata from Portolan 0.1 to 0.2, and declare it official.

Runs *after* ``upgrade_to_0_1.py`` — that script is the historical 0.1 sweep and
still applies the structural fixes (self links, link titles, style media types,
extensions). This one applies the 0.2 deltas on top, so the order is:

    python3 scripts/migrate/upgrade_to_0_1.py
    python3 scripts/migrate/upgrade_to_0_2.py
    python3 scripts/migrate/backfill_file_meta.py --local-only

Idempotent: running it twice changes nothing the second time.

What it does
------------

**Declares the 0.2.0 profile.** Swaps the schema URI in ``stac_extensions`` on
every catalog and collection. 0.2.0 is the current release (2026-08-28); it is
breaking for *validators*, not for catalogs — every 0.1.2-conformant catalog
still conforms. rashid 0.1.8 is the first release carrying the new rules.

**Makes the catalog official rather than a mirror.** This is the substantive
change. Portolan derives the distinction from providers alone
(``specs/portolan/core.md``, Source Provenance):

    A catalog is official when its producer and host are the same organization;
    it is a mirror when they differ.

FTW listed Source Cooperative as ``host``, which made all six provider-bearing
objects derive as mirrors. That was a modelling error — the spec is explicit
that the host is the organization operating the catalog, *not* the storage
vendor:

    The host is the organization responsible for operating and maintaining this
    copy of the catalog and its data, not the underlying cloud vendor whose
    storage it happens to sit on; a catalog on S3 maintained by a city GIS
    office lists the office as host, not AWS.

Source Cooperative is the AWS of that sentence. Taylor Geospatial operates and
maintains this catalog and already holds producer/licensor/processor, so it
takes ``host`` too and is listed last, and Source Cooperative leaves the
provider list. Producer == host, so the catalog is official.

The tell that the mirror modelling was always artificial: the ``via`` link on
``predictions/confidence`` pointed at *itself*
(``https://data.source.coop/ftw/global-data/``). A mirror's ``via`` names an
upstream source elsewhere; there is no upstream, because this is it.

**Rehomes the provenance links.** An official catalog "carries no ``via`` or
``canonical`` link to an upstream source, because it is the source." The
self-pointing ``via`` is dropped outright. The others name genuine provenance
that is worth keeping but is not a mirror source — the FTW benchmark that
trained the model, and the published model weights — so they become ``related``
rather than being thrown away.

**Marks a default style** (``PORTO-CORE-070``, a MUST since 0.1.1): where a
collection registers more than one style asset, exactly one must carry both
``style`` and ``default`` in its ``roles``. The vectors collection registers
four and marked none, which rashid 0.1.8 reports as ``PTL-VIZ-006``. The word
"default" was only ever in the asset *title*.

Usage
-----
    python3 upgrade_to_0_2.py [--catalog catalog] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

PORTOLAN_0_1 = "https://schemas.portolan-sdi.org/portolan/v0.1.0/schema.json"
PORTOLAN_0_2 = "https://schemas.portolan-sdi.org/portolan/v0.2.0/schema.json"

# The organization that operates and maintains this catalog. Named as the
# organization styles itself, not by its longer legal form.
HOST_NAME = "Taylor Geospatial"
HOST_ALIASES = ("Taylor Geospatial Institute", "Taylor Geospatial")
HOST_URL = "https://taylorgeospatial.org/"

# Dropped from `providers`: it is where the bytes sit, not who maintains the
# catalog. Keeping it as `host` is what made every collection derive as a mirror.
STORAGE_VENDOR = "Source Cooperative"

# A `via` pointing at our own publish base is self-referential and simply goes.
SELF_VIA_PREFIXES = (
    "https://data.source.coop/ftw/global-data",
    "https://source.coop/ftw/global-data",
)


def load(p: Path):
    with p.open() as f:
        return json.load(f)


def save(p: Path, obj) -> None:
    with p.open("w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


# Any released Portolan profile URI, whatever the version.
PORTOLAN_PROFILE_RE = re.compile(
    r"^https://schemas\.portolan-sdi\.org/portolan/v[0-9.]+/schema\.json$")


def bump_schema(obj, stats: Counter) -> bool:
    """Leave exactly one Portolan profile URI, at 0.2.0.

    Collapses rather than substitutes, because `upgrade_to_0_1.py` re-adds the
    v0.1.0 URI when run against an already-migrated catalog. A naive
    find-and-replace then produced *two* identical v0.2.0 entries, which
    `stac_extensions` forbids (unique items) — PTL-CNF-001 and PTL-STR-001.
    Rebuilding the list keeps this idempotent whatever order the two migrations
    run in.
    """
    exts = obj.get("stac_extensions")
    if not isinstance(exts, list):
        return False
    others = [e for e in exts if not PORTOLAN_PROFILE_RE.match(str(e))]
    had = [e for e in exts if PORTOLAN_PROFILE_RE.match(str(e))]
    if not had:
        return False
    rebuilt = [PORTOLAN_0_2, *others]
    if rebuilt == exts:
        return False
    obj["stac_extensions"] = rebuilt
    stats["schema_bumped"] += 1
    if len(had) > 1:
        stats["duplicate_profiles_collapsed"] += 1
    return True


def make_official(obj, stats: Counter) -> bool:
    """Host becomes the maintaining organization; the storage vendor drops out."""
    providers = obj.get("providers")
    if not isinstance(providers, list) or not providers:
        return False

    changed = False
    kept = []
    for p in providers:
        if p.get("name") == STORAGE_VENDOR:
            changed = True  # dropped
            continue
        if p.get("name") in HOST_ALIASES and p.get("name") != HOST_NAME:
            p["name"] = HOST_NAME
            changed = True
        kept.append(p)

    host = next((p for p in kept if p.get("name") == HOST_NAME), None)
    if host is None:
        # Nothing to promote: leave the object alone rather than inventing a host.
        if changed:
            obj["providers"] = kept
            stats["storage_vendor_dropped"] += 1
        return changed

    roles = host.setdefault("roles", [])
    if "host" not in roles:
        roles.append("host")
        changed = True
    if not host.get("url"):
        host["url"] = HOST_URL
        changed = True

    # PORTO-CORE-036: exactly one host provider, listed last.
    if kept[-1] is not host:
        kept.remove(host)
        kept.append(host)
        changed = True

    if changed:
        obj["providers"] = kept
        stats["made_official"] += 1
    return changed


def rehome_via(obj, stats: Counter) -> bool:
    """An official catalog carries no `via`/`canonical` to an upstream source."""
    links = obj.get("links")
    if not isinstance(links, list):
        return False
    changed = False
    out = []
    for l in links:
        if l.get("rel") not in ("via", "canonical"):
            out.append(l)
            continue
        href = l.get("href", "")
        if href.startswith(SELF_VIA_PREFIXES):
            stats["self_via_dropped"] += 1
            changed = True
            continue  # points at ourselves; just goes
        # Genuine provenance (benchmark, model weights) — keep it, but not as a
        # mirror-source relation.
        l["rel"] = "related"
        stats["via_to_related"] += 1
        changed = True
        out.append(l)
    if changed:
        obj["links"] = out
    return changed


def mark_default_style(obj, stats: Counter) -> bool:
    """PORTO-CORE-070: >1 style asset => exactly one also carries `default`."""
    assets = obj.get("assets")
    if not isinstance(assets, dict):
        return False
    styles = [(k, v) for k, v in assets.items()
              if isinstance(v, dict) and "style" in (v.get("roles") or [])]
    if len(styles) < 2:
        return False
    if any("default" in (v.get("roles") or []) for _, v in styles):
        return False
    # Prefer an asset whose title or key already says "default"; else the first.
    def prefers(kv):
        k, v = kv
        return "default" in f"{k} {v.get('title', '')}".lower()
    key, asset = next((kv for kv in styles if prefers(kv)), styles[0])
    asset["roles"] = [*asset.get("roles", []), "default"]
    stats["default_style_marked"] += 1
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", default="catalog", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not a.catalog.is_dir():
        print(f"no such directory: {a.catalog}", file=sys.stderr)
        return 1

    stats = Counter()
    targets = sorted(
        [*a.catalog.rglob("collection.json"), *a.catalog.rglob("catalog.json")]
    )
    for p in targets:
        obj = load(p)
        touched = False
        for fn in (bump_schema, make_official, rehome_via, mark_default_style):
            touched |= bool(fn(obj, stats))
        if touched:
            stats["files_modified"] += 1
            if not a.dry_run:
                save(p, obj)

    label = "would change" if a.dry_run else "changed"
    print(f"Portolan 0.1 -> 0.2 migration ({label}):")
    for k in sorted(stats):
        print(f"  {k:<26} {stats[k]}")
    if not stats:
        print("  nothing to do (already at 0.2)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
