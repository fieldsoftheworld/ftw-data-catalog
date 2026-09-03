#!/usr/bin/env bash
# Publish the territories recovered by recover_dependencies.py.
#
# For each recovered partition (and the rewritten ZZ): build PMTiles from the
# GeoParquet, then upload both to the published `results-by-admin-conf/` prefix —
# the same shape every other country partition already has.
#
# Reads:   the local output tree from `recover_dependencies.py --out <dir>`.
# Writes:  s3://…/predictions/vectors/alpha/results-by-admin-conf/admin:country_code=<CC>/
#          (needs credentials). Data only — the STAC metadata beside it is generated
#          afterwards by scripts/catalog/build_vector_items.py and shipped via
#          scripts/catalog/publish.py.
#
# Idempotent: a partition whose parquet and pmtiles are already on S3 with the
# expected size is skipped. Use --force to redo one anyway.
#
# Usage:
#   ./publish_recovered.sh /tmp/ftwrec                 # dry run: print the plan
#   ./publish_recovered.sh /tmp/ftwrec --confirm       # build + upload
#   ./publish_recovered.sh /tmp/ftwrec --confirm --skip-zz
#
# --skip-zz omits the rewritten Unknown partition. Rebuilding its PMTiles means
# running tippecanoe over ~40 M polygons, which dominates the whole job; the
# recovered territories can go out first and ZZ can follow.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MAKE_PMTILES="$REPO_ROOT/scripts/confidence/make_pmtiles.py"

WORK_IN="${1:?usage: publish_recovered.sh <recover_dependencies output dir> [--confirm] [--skip-zz] [--force]}"
shift || true
CONFIRM=0; SKIP_ZZ=0; FORCE=0
for a in "$@"; do
  case "$a" in
    --confirm) CONFIRM=1 ;;
    --skip-zz) SKIP_ZZ=1 ;;
    --force)   FORCE=1 ;;
    *) echo "unknown flag: $a" >&2; exit 2 ;;
  esac
done

PARTS="$WORK_IN/partitions"
[ -d "$PARTS" ] || { echo "no partitions dir at $PARTS — run recover_dependencies.py first" >&2; exit 1; }

DST="s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data/predictions/vectors/alpha/results-by-admin-conf"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-west-2}"
export DUCKDB_MEM="${DUCKDB_MEM:-12GB}"
export DUCKDB_THREADS="${DUCKDB_THREADS:-8}"

total=0; planned=0
for dir in "$PARTS"/admin:country_code=*; do
  cc="${dir##*admin:country_code=}"
  [ "$cc" = "ZZ" ] && [ "$SKIP_ZZ" -eq 1 ] && { echo "SKIP ZZ (--skip-zz)"; continue; }
  for parq in "$dir"/*.parquet; do
    [ -e "$parq" ] || continue
    stem="$(basename "$parq" .parquet)"
    pm="$dir/$stem.pmtiles"
    size=$(stat -f%z "$parq" 2>/dev/null || stat -c%s "$parq")
    total=$((total + size)); planned=$((planned + 1))
    printf '%-4s %-46s %10.1f MB -> %s/\n' "$cc" "$stem.parquet" "$(echo "$size/1000000" | bc -l)" "admin:country_code=$cc"

    [ "$CONFIRM" -eq 1 ] || continue

    remote_parq="$DST/admin:country_code=$cc/$stem.parquet"
    remote_pm="$DST/admin:country_code=$cc/$stem.pmtiles"
    if [ "$FORCE" -eq 0 ] \
       && aws s3 ls "$remote_parq" >/dev/null 2>&1 \
       && [ "$(aws s3 ls "$remote_parq" | awk '{print $3}')" = "$size" ] \
       && aws s3 ls "$remote_pm" >/dev/null 2>&1; then
      echo "  skip (already on S3 at the same size)"
      continue
    fi

    if [ ! -s "$pm" ]; then
      echo "  tippecanoe -> $stem.pmtiles"
      if ! python3 "$MAKE_PMTILES" "$parq" "$pm" --tmpdir "$dir/.tmp"; then
        echo "  PMTILES FAILED for $cc/$stem" >&2; continue
      fi
    else
      echo "  pmtiles already built locally"
    fi

    echo "  upload parquet"
    aws s3 cp "$parq" "$remote_parq" --only-show-errors || { echo "  UPLOAD FAILED $cc parquet" >&2; continue; }
    echo "  upload pmtiles"
    aws s3 cp "$pm" "$remote_pm" --only-show-errors || { echo "  UPLOAD FAILED $cc pmtiles" >&2; continue; }
    echo "  done $cc/$stem"
  done
done

printf '\n%d partition(s), %.1f GB of parquet\n' "$planned" "$(echo "$total/1000000000" | bc -l)"
if [ "$CONFIRM" -eq 0 ]; then
  echo "dry run — re-run with --confirm to build PMTiles and upload"
fi
