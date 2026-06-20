#!/usr/bin/env bash
# Process ONE FTW per-admin field-boundary parquet:
#   download -> add confidence column -> build PMTiles -> upload both to S3.
#
# Reads (public, no creds):  SRC_PREFIX/<key> parquet, and the confidence COG.
# Writes (needs creds):      DST_PREFIX/<key> parquet + a sibling .pmtiles.
# Idempotent: skips when both outputs already exist.
#
# Usage:
#   ./process_partition.sh "admin:country_code=AD/Andorra.parquet"
#
# Env overrides: SRC_PREFIX, DST_PREFIX, COG, WORK (scratch dir).
# Requires on PATH: aws, python3 (pyarrow/rasterio/shapely/numpy/affine), gpio, tippecanoe.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REL="${1:?usage: process_partition.sh <key under results-by-admin>}"

BASE="s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data/predictions/vectors/alpha"
SRC_PREFIX="${SRC_PREFIX:-$BASE/results-by-admin}"
DST_PREFIX="${DST_PREFIX:-$BASE/results-by-admin-conf}"
COG="${COG:-https://data.source.coop/ftw/global-data/predictions/confidence/confidence/prue_v1_confidence_global.tif}"
WORK="${WORK:-${TMPDIR:-/tmp}/ftw-conf}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-west-2}"

stem="$(basename "$REL" .parquet)"
dstparq="$DST_PREFIX/$REL"
dstpm="$DST_PREFIX/$(dirname "$REL")/$stem.pmtiles"

if aws s3 ls "$dstparq" >/dev/null 2>&1 && aws s3 ls "$dstpm" >/dev/null 2>&1; then
  echo "SKIP $REL (outputs already exist)"
  exit 0
fi

d="$WORK/${stem}.$$"
logdir="$WORK/logs"
mkdir -p "$d" "$logdir"
log="$logdir/$stem.tippecanoe.log"
# tippecanoe spills large temp files: keep them on scratch disk, not RAM-backed /tmp.
export TMPDIR="$d"
trap 'rm -rf "$d"' EXIT
in="$d/in.parquet"; out="$d/$stem.parquet"; pm="$d/$stem.pmtiles"

echo "[$REL] download"
aws s3 cp --no-sign-request "$SRC_PREFIX/$REL" "$in" --quiet

echo "[$REL] add confidence"
python3 "$SCRIPT_DIR/add_confidence.py" "$in" "$out" --cog "$COG"

echo "[$REL] build pmtiles"
if ! python3 "$SCRIPT_DIR/make_pmtiles.py" "$out" "$pm" \
       --layer fields --cols confidence,metrics:area --tmpdir "$d" >"$log" 2>&1; then
  echo "FAILED pmtiles $REL — last lines of $log:" >&2
  tail -n 25 "$log" >&2
  exit 1
fi

echo "[$REL] upload"
aws s3 cp "$out" "$dstparq" --quiet
aws s3 cp "$pm" "$dstpm" --quiet
echo "DONE $REL"
