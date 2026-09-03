#!/usr/bin/env python3
"""Recover Overture *dependency* territories from the `ZZ` (Unknown) partition.

Why this exists
---------------
The original admin run (`rails_addadmin_all.sh`, step A) attributed countries with
`gpio add admin-divisions --vecorel`, which joins against Overture divisions. gpio
built its country-level cache with `subtype = 'country'` — matching only the 219
sovereign states. Overture files the 53 *dependent* territories (French Guiana,
Puerto Rico, Réunion, Guadeloupe, Mayotte, New Caledonia, Greenland, Hong Kong,
Macao, Guam, the Channel Islands, …) under `subtype = 'dependency'`, so every field
in them matched no polygon at all and was coalesced to `admin:country_code = 'ZZ'`.

Fixed upstream in geoparquet-io#820 (issue #819): the country level now draws on
`subtype IN ('country', 'dependency')`. This script applies that fix to the already
published data without re-running the whole ~3.2 B-polygon pipeline.

What it does
------------
Only the *country* level changes, and only for features inside a dependency, so this
is a narrow patch rather than a re-run. **The two steps that decide anything are gpio
commands — the same ones the original run used**; DuckDB only prepares and tidies
around them.

1. **Split** off the *candidates* (DuckDB) — rows of the published `ZZ` partition
   whose bbox overlaps at least one of the 50 dependency bboxes, i.e. the only rows
   that could possibly be recovered: ~5.9 M of 46.4 M. Purely an optimisation; running
   gpio over all 46.4 M would give the same answer roughly eight times more slowly.
   The other rows are not written anywhere, and step 4 carries them through from the
   source untouched.
2. **Re-attribute** with `gpio add admin-divisions --vecorel` (as step A of
   `rails_addadmin_all.sh` did). The published `admin:*` columns are moved out of the
   way first: gpio selects `a.*` beside its computed columns, so leaving them in
   yields duplicate names that DuckDB silently suffixes (`admin:country_code_1`) and
   the stale `'ZZ'` wins — the run looks like a no-op.
3. **Normalise** (DuckDB) — collapse region-join duplicates and restore the published
   schema. The country join is 1:1 (Overture's country and dependency polygons do not
   overlap — verified in #820), but the *region* join is not: a feature between two
   adjacent regions matches both. Pre-existing gpio behaviour, unrelated to the fix.
4. **Partition** with `gpio partition string --column admin:country_code --hive` (as
   step B did), rename each output to the catalog's `<Country_Name>.parquet`
   convention (steps C/D), and concatenate gpio's `ZZ` partition with the rows that
   were never candidates to form the new `Unknown.parquet`. Row conservation is
   asserted.

A **future from-scratch run needs none of this** — with the #820 fix in gpio, the
original `rails_addadmin_all.sh` → `rails_partition_batched.sh` → `rails_relayout.py`
chain produces the dependency partitions on its own. This script exists only to patch
data that is already published.

Recovered rows keep their published `admin:subdivision_code`: it travels through the
pipeline as ORIG_SUB rather than being taken from the re-join, so a newer Overture
release cannot quietly perturb subdivision codes. For the dependencies themselves the
value is `'ZZ'`, which is correct rather than a gap — Overture has region rows for
them (French Guiana has Cayenne, Saint-Georges and Saint-Laurent-du-Maroni) but their
`region` field is NULL, so there is no ISO 3166-2 code to record.

Usage
-----
    python3 recover_dependencies.py --zz Unknown.parquet --out out/ [--gpio "uv run --directory ~/repos/geoparquet-io gpio"]
    python3 recover_dependencies.py --zz Unknown.parquet --out out/ --stage split   # one stage at a time

Each stage is resumable: a stage whose outputs already exist is skipped unless
`--force` is given.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

# The Overture release the recovery is pinned to. Recorded in the manifest so a
# later re-run can tell whether boundaries moved underneath it.
OVERTURE_RELEASE_DEFAULT = "2026-07-22.0"

# Short, common names where the ISO official name is long or awkward. Mirrors the
# OVERRIDES table in rails_country_names.py so the new partitions are named
# consistently with the 194 that already exist.
NAME_OVERRIDES = {
    "VG": "British Virgin Islands",
    "VI": "US Virgin Islands",
    "FK": "Falkland Islands",
    "BQ": "Bonaire Sint Eustatius and Saba",
    "SH": "Saint Helena",
    "UM": "US Minor Outlying Islands",
    "CP": "Clipperton Island",  # not an ISO 3166-1 code; pycountry cannot resolve it
    "ZZ": "Unknown",
}

DUCKDB_MEM = os.environ.get("DUCKDB_MEM", "12GB")
DUCKDB_THREADS = os.environ.get("DUCKDB_THREADS", "8")

ADMIN_CC = "admin:country_code"
ADMIN_SUB = "admin:subdivision_code"
ADMIN_COLS = (ADMIN_CC, ADMIN_SUB)
# The candidates file carries the published subdivision code under a name gpio will
# not collide with, so recovered rows can keep it. Everything the emit stage needs
# then lives in the attributed file itself — there is deliberately no positional key
# joining back to the source, because `row_number() OVER ()` is not guaranteed to
# assign the same numbers in two different queries over the same parquet.
ORIG_SUB = "__orig_subdivision"
# Used only to collapse region-join duplicates *within* the attributed file, where it
# is valid by construction (gpio carries it through via `a.*`).
ROW_ID = "__row_id"


def connect():
    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute(f"SET memory_limit='{DUCKDB_MEM}'")
    con.execute(f"SET threads={DUCKDB_THREADS}")
    con.execute("SET TimeZone='UTC'")
    return con


def fname(name: str) -> str:
    """Sanitised filename stem — the same rule rails_country_names.py used."""
    return "".join(c if (c.isalnum() or c in " -") else "" for c in name).strip().replace(" ", "_")


def country_name(cc: str) -> str:
    """ISO short name for a code, the way the published partitions are named.

    Fails rather than falling back to the bare code: a silent fallback publishes
    `GF.parquet` next to 194 partitions named `France.parquet`, `Suriname.parquet`
    and so on, and the mismatch is easy to miss in a long run log. Codes pycountry
    genuinely cannot resolve (CP / Clipperton is not ISO 3166-1) belong in
    NAME_OVERRIDES.
    """
    if cc in NAME_OVERRIDES:
        return NAME_OVERRIDES[cc]
    try:
        import pycountry
    except ImportError:
        raise SystemExit(
            "pycountry is required to name the partitions the way the catalog does.\n"
            "  pip install pycountry   — or run with:\n"
            '  uv run --with pycountry python3 scripts/admin/recover_dependencies.py ...'
        ) from None
    obj = pycountry.countries.get(alpha_2=cc)
    if not obj:
        raise SystemExit(
            f"no ISO 3166-1 name for {cc!r}; add it to NAME_OVERRIDES in this script"
        )
    return getattr(obj, "common_name", None) or obj.name


def dependency_bboxes(con, release: str, cache: Path) -> list[dict]:
    """Bounding boxes of the land dependency polygons, from the gpio admin cache.

    Reads gpio's own dependency-aware country cache when it is present (so the
    bboxes match exactly what the re-attribution will join against) and falls back
    to reading Overture directly.
    """
    if cache.exists() and cache.stat().st_size > 0:
        src = f"read_parquet('{cache}')"
        where = "subtype = 'dependency'"
    else:
        base = (
            "https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/release/"
            f"{release}/theme=divisions/type=division_area/"
        )
        listing = subprocess.run(
            ["aws", "s3", "ls", "--no-sign-request",
             f"s3://overturemaps-us-west-2/release/{release}/theme=divisions/type=division_area/"],
            capture_output=True, text=True, check=True,
        )
        files = [f"'{base}{line.split()[-1]}'" for line in listing.stdout.splitlines() if line.strip()]
        con.execute("LOAD httpfs;")
        src = f"read_parquet([{', '.join(files)}])"
        where = ("subtype = 'dependency' AND is_land IS NOT FALSE "
                 "AND country NOT LIKE 'X%' AND country != 'AQ'")

    rows = con.execute(f"""
        SELECT country,
               ST_XMin(geometry), ST_YMin(geometry),
               ST_XMax(geometry), ST_YMax(geometry)
        FROM {src} WHERE {where} ORDER BY country
    """).fetchall()
    return [{"cc": r[0], "xmin": r[1], "ymin": r[2], "xmax": r[3], "ymax": r[4]} for r in rows]


def _overlap_sql(deps: list[dict]) -> str:
    """Predicate: this feature's bbox overlaps at least one dependency's bbox."""
    return " OR ".join(
        f"(bbox.xmin <= {d['xmax']!r} AND bbox.xmax >= {d['xmin']!r} AND "
        f"bbox.ymin <= {d['ymax']!r} AND bbox.ymax >= {d['ymin']!r})"
        for d in deps
    )


def stage_split(con, zz: Path, out: Path, deps: list[dict], force: bool) -> Path:
    """Extract the gpio-ready candidate rows from ZZ.

    Only the candidates are materialised; the rest of ZZ is re-read from the source
    in `emit`. The candidates keep every published column: the two `admin:*` ones are
    renamed out of the way (`admin:country_code` is dropped — inside ZZ it is
    uniformly 'ZZ' — and `admin:subdivision_code` is preserved as ORIG_SUB) so that
    gpio can add its own without colliding, and so recovered rows can still be
    written with their published subdivision code.
    """
    cand = out / "candidates.parquet"
    if cand.exists() and not force:
        print(f"  split: reusing {cand.name}")
        return cand

    overlap = _overlap_sql(deps)
    cols = [r[0] for r in con.execute(
        f"DESCRIBE SELECT * FROM read_parquet('{zz}')").fetchall()]
    passthrough = ", ".join(
        f'"{ADMIN_SUB}" AS {ORIG_SUB}' if c == ADMIN_SUB else f'"{c}"'
        for c in cols if c != ADMIN_CC
    )

    print(f"  split: scanning {zz.name} against {len(deps)} dependency bboxes")
    con.execute(f"""
        COPY (
          SELECT row_number() OVER () AS {ROW_ID}, {passthrough}
          FROM read_parquet('{zz}') WHERE {overlap}
        ) TO '{cand}' (FORMAT parquet, COMPRESSION zstd)
    """)
    n_c = con.execute(f"SELECT count(*) FROM read_parquet('{cand}')").fetchone()[0]
    n_all = con.execute(f"SELECT count(*) FROM read_parquet('{zz}')").fetchone()[0]
    print(f"  split: {n_c:,} candidates of {n_all:,} rows ({n_all - n_c:,} carried through)")
    return cand


def gpio_provenance(gpio: str) -> dict:
    """Identify the gpio actually being invoked.

    `gpio --version` alone is not enough to tell a build that carries the #819 fix
    from one that does not: both report 1.4.0 until the fix is released. So this also
    records the git commit when gpio is being run out of a checkout, and probes the
    dependency-aware config directly — a run against an unfixed gpio would silently
    recover nothing, and this makes it fail loudly instead.
    """
    prov: dict = {"invocation": gpio}
    try:
        prov["version"] = subprocess.run(
            shlex.split(gpio) + ["--version"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise SystemExit(f"cannot run gpio ({gpio!r}): {e}") from None

    parts = shlex.split(gpio)
    if "--directory" in parts:
        repo = parts[parts.index("--directory") + 1]
        for key, args in (("commit", ["rev-parse", "HEAD"]),
                          ("branch", ["rev-parse", "--abbrev-ref", "HEAD"])):
            r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
            if r.returncode == 0:
                prov[key] = r.stdout.strip()
        dirty = subprocess.run(["git", "-C", repo, "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True)
        prov["dirty"] = bool(dirty.stdout.strip())

    # Probe the config of the *same* interpreter gpio runs under. For a checkout
    # invocation ("uv run --directory REPO gpio") swap the trailing "gpio" for
    # "python"; for a plain installed "gpio" there is no matching interpreter to
    # borrow, so fall back to importing in this process.
    parts_probe = shlex.split(gpio)
    code = ("from geoparquet_io.core.admin_datasets import _OVERTURE_LEVEL_CACHE_CONFIG as C; "
            "print(','.join(C['country'].get('subtypes', ['country'])))")
    subtypes = ""
    if len(parts_probe) > 1 and parts_probe[-1].endswith("gpio"):
        probe = subprocess.run(parts_probe[:-1] + ["python", "-c", code],
                               capture_output=True, text=True)
        if probe.returncode == 0:
            subtypes = probe.stdout.strip()
    else:
        try:
            from geoparquet_io.core.admin_datasets import _OVERTURE_LEVEL_CACHE_CONFIG as C
            subtypes = ",".join(C["country"].get("subtypes", ["country"]))
        except ImportError:
            pass

    prov["country_subtypes"] = subtypes or "unknown"
    if subtypes and "dependency" not in subtypes:
        raise SystemExit(
            f"this gpio does not carry the #819 fix (country subtypes: {subtypes!r}).\n"
            "Point --gpio at a build that does, e.g.\n"
            '  --gpio "uv run --directory ~/repos/geoparquet-io gpio"'
        )
    return prov


def stage_attribute(cand: Path, out: Path, gpio: str, write_memory: str, force: bool) -> Path:
    """Re-run the fixed `gpio add admin-divisions --vecorel` over the candidates."""
    attributed = out / "candidates_admin.parquet"
    if attributed.exists() and not force:
        print(f"  attribute: reusing {attributed.name}")
        return attributed
    cmd = shlex.split(gpio) + [
        "add", "admin-divisions", str(cand), str(attributed),
        "--vecorel", "--overwrite", "--write-memory", write_memory,
    ]
    print(f"  attribute: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    return attributed


def stage_emit(con, attributed: Path, zz: Path, out: Path, deps: list[dict],
               release: str, gpio: str, write_memory: str, prov: dict) -> dict:
    """Partition the attributed candidates by country and rewrite Unknown.

    Mirrors the original run's steps B-D: `gpio partition string --column
    admin:country_code` does the split (as `rails_partition_batched.sh` did), then the
    per-country file is renamed to the catalog's `<Country_Name>.parquet` convention
    (as `rails_relayout.py` / `rails_hive_reorg.py` did).

    DuckDB is used only either side of that: to normalise the attributed file back to
    the published schema, and to concatenate gpio's ZZ partition with the rows that
    were never candidates. There is deliberately no positional key back to the source
    — `row_number() OVER ()` is not guaranteed to number two queries alike — so a
    recovered row is written entirely from the attributed file, which carries every
    published column.
    """
    parts = out / "partitions"
    parts.mkdir(parents=True, exist_ok=True)
    overlap = _overlap_sql(deps)
    src_cols = [r[0] for r in con.execute(
        f"DESCRIBE SELECT * FROM read_parquet('{zz}')").fetchall()]

    # 1. Normalise: collapse region-join duplicates and restore the published schema
    #    (new country code, ORIGINAL subdivision code, drop the scratch columns).
    #    The country join is 1:1, so rows sharing a __row_id agree on the country.
    clean = out / "attributed_clean.parquet"
    projected = ", ".join(
        f'"{ADMIN_CC}"' if c == ADMIN_CC
        else (f'{ORIG_SUB} AS "{ADMIN_SUB}"' if c == ADMIN_SUB else f'"{c}"')
        for c in src_cols
    )
    con.execute(f"""
        COPY (
          SELECT {projected} FROM read_parquet('{attributed}')
          QUALIFY row_number() OVER (PARTITION BY {ROW_ID}) = 1
        ) TO '{clean}' (FORMAT parquet, COMPRESSION zstd)
    """)
    n_raw = con.execute(f"SELECT count(*) FROM read_parquet('{attributed}')").fetchone()[0]
    n_clean = con.execute(f"SELECT count(*) FROM read_parquet('{clean}')").fetchone()[0]
    print(f"  emit: {n_clean:,} candidates ({n_raw - n_clean:,} region-join duplicates collapsed)")

    # 2. Partition by country with gpio — the same command the original run used.
    staged = out / "by_country"
    if staged.exists():
        shutil.rmtree(staged)
    cmd = shlex.split(gpio) + [
        "partition", "string", str(clean), str(staged),
        "--column", ADMIN_CC, "--hive", "--force", "--skip-analysis",
        "--write-memory", write_memory,
    ]
    print(f"  emit: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    # 3. Rename each partition to the catalog's <Country_Name>.parquet convention.
    #
    #    ONLY the dependency codes are emitted. The re-join also matches a handful of
    #    rows to ordinary sovereign countries (CA, BR, ES, US, JP, MX, … — 771 rows
    #    across 31 codes on the 2026-07-22.0 run): candidates sit inside a dependency's
    #    *bbox* but on a neighbour's land, and Overture's borders have moved a little
    #    since the original run, so they now match where they previously did not. That
    #    is boundary drift, not the bug being fixed here — and emitting them would
    #    produce e.g. a 167-row `Canada.parquet` that the upload step would write
    #    straight over the published multi-million-row one. They stay in ZZ, exactly as
    #    published, and are reported for follow-up.
    dep_codes = {d["cc"] for d in deps}
    manifest = {"overture_release": release, "gpio": prov,
                "dependencies_considered": len(deps),
                "recovered_rows": 0, "partitions": {}, "drift_held_back": {}}
    zz_pieces, drift_pieces = [], []
    for d in sorted(staged.glob(f"{ADMIN_CC}=*")):
        cc = d.name.split("=", 1)[1]
        pieces = sorted(d.glob("*.parquet"))
        if not pieces:
            continue
        if cc == "ZZ":
            zz_pieces = pieces
            continue
        if cc not in dep_codes:
            n = con.execute(
                f"SELECT count(*) FROM read_parquet([{', '.join(repr(str(p)) for p in pieces)}])"
            ).fetchone()[0]
            manifest["drift_held_back"][cc] = n
            drift_pieces.extend(pieces)
            continue
        stem = fname(country_name(cc))
        dest_dir = parts / f"{ADMIN_CC}={cc}"
        dest_dir.mkdir(parents=True, exist_ok=True)
        target = dest_dir / f"{stem}.parquet"
        if len(pieces) == 1:
            shutil.move(str(pieces[0]), target)
        else:  # gpio may emit several files for one value; merge them
            srcs = ", ".join(f"'{p}'" for p in pieces)
            con.execute(f"""COPY (SELECT * FROM read_parquet([{srcs}]))
                            TO '{target}' (FORMAT parquet, COMPRESSION zstd, COMPRESSION_LEVEL 9)""")
        n = con.execute(f"SELECT count(*) FROM read_parquet('{target}')").fetchone()[0]
        manifest["partitions"][cc] = {"stem": stem, "rows": n, "bytes": target.stat().st_size}
        manifest["recovered_rows"] += n
        print(f"    {cc} {stem:<44} {n:>9,} rows  {target.stat().st_size/1e6:>8.1f} MB")

    # 4. New Unknown: rows that were never candidates (straight from the published
    #    parquet, so unchanged), plus gpio's ZZ partition, plus the drift rows held
    #    back in step 3 — which must land somewhere or row conservation fails. They
    #    keep 'ZZ' so the published Unknown stays a superset of what it was minus
    #    exactly the dependency recoveries.
    unknown_dir = parts / f"{ADMIN_CC}=ZZ"
    unknown_dir.mkdir(parents=True, exist_ok=True)
    unknown = unknown_dir / "Unknown.parquet"
    quoted = ", ".join(f'"{c}"' for c in src_cols)
    forced_zz = ", ".join(
        f"'ZZ' AS \"{c}\"" if c == ADMIN_CC else f'"{c}"' for c in src_cols
    )
    unions = []
    if zz_pieces:
        srcs = ", ".join(f"'{p}'" for p in zz_pieces)
        unions.append(f"UNION ALL SELECT {quoted} FROM read_parquet([{srcs}])")
    if drift_pieces:
        srcs = ", ".join(f"'{p}'" for p in drift_pieces)
        unions.append(f"UNION ALL SELECT {forced_zz} FROM read_parquet([{srcs}])")
        held = sum(manifest["drift_held_back"].values())
        print(f"  emit: {held:,} row(s) across {len(manifest['drift_held_back'])} "
              f"non-dependency code(s) held back as boundary drift, kept in ZZ: "
              f"{', '.join(sorted(manifest['drift_held_back']))}")
    con.execute(f"""
        COPY (
          SELECT {quoted} FROM read_parquet('{zz}') WHERE NOT ({overlap})
          {' '.join(unions)}
        ) TO '{unknown}' (FORMAT parquet, COMPRESSION zstd, COMPRESSION_LEVEL 9)
    """)
    n_zz = con.execute(f"SELECT count(*) FROM read_parquet('{unknown}')").fetchone()[0]
    manifest["unknown_rows"] = n_zz
    print(f"    ZZ {'Unknown':<44} {n_zz:>9,} rows  {unknown.stat().st_size/1e6:>8.1f} MB")

    total_in = con.execute(f"SELECT count(*) FROM read_parquet('{zz}')").fetchone()[0]
    manifest["source_rows"] = total_in
    rec = manifest["recovered_rows"]
    if rec + n_zz != total_in:
        raise SystemExit(f"row conservation FAILED: {rec:,} + {n_zz:,} != {total_in:,}")
    print(f"  emit: row conservation OK ({rec:,} + {n_zz:,} = {total_in:,})")

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zz", required=True, type=Path, help="published Unknown.parquet")
    ap.add_argument("--out", required=True, type=Path, help="working/output directory")
    ap.add_argument("--gpio", default="gpio",
                    help="gpio invocation; use e.g. 'uv run --directory ~/repos/geoparquet-io gpio' "
                         "to run a checkout that carries the #820 fix")
    ap.add_argument("--release", default=OVERTURE_RELEASE_DEFAULT)
    ap.add_argument("--write-memory", default="4GB")
    ap.add_argument("--stage", choices=("split", "attribute", "emit", "all"), default="all")
    ap.add_argument("--force", action="store_true", help="redo stages whose outputs exist")
    a = ap.parse_args()

    a.out.mkdir(parents=True, exist_ok=True)
    con = connect()

    prov = gpio_provenance(a.gpio)
    print(f"gpio: {prov.get('version')} "
          f"[{prov.get('branch', 'installed')}@{prov.get('commit', '-')[:8]}"
          f"{' DIRTY' if prov.get('dirty') else ''}] "
          f"country subtypes: {prov['country_subtypes']}")

    cache = (Path.home() / ".geoparquet-io" / "cache" / "admin"
             / f"overture-{a.release}-country-dependency-land.parquet")
    deps = dependency_bboxes(con, a.release, cache)
    print(f"dependencies: {len(deps)} ({'gpio cache' if cache.exists() else 'Overture direct'})")
    if not deps:
        print("no dependency polygons found — is the gpio fix (#820) in place?", file=sys.stderr)
        return 1

    cand = stage_split(con, a.zz, a.out, deps, a.force)
    if a.stage == "split":
        return 0

    attributed = stage_attribute(cand, a.out, a.gpio, a.write_memory, a.force)
    if a.stage == "attribute":
        return 0

    stage_emit(con, attributed, a.zz, a.out, deps, a.release, a.gpio, a.write_memory, prov)
    print(f"\nwrote {a.out / 'partitions'} and {a.out / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
