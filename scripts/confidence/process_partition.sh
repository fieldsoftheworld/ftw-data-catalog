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
in="$d/in.parquet"; conf="$d/conf.parquet"; out="$d/$stem.parquet"; pm="$d/$stem.pmtiles"

echo "[$REL] download"
aws s3 cp --no-sign-request "$SRC_PREFIX/$REL" "$in" --quiet

echo "[$REL] add confidence"
python3 "$SCRIPT_DIR/add_confidence.py" "$in" "$conf" --cog "$COG"

# Spatially sort the output. Neither the admin-partition step nor add_confidence.py
# orders rows -- add_confidence.py streams iter_batches() and preserves input order
# -- so the published files inherited whatever order results-by-admin/ had, which is
# close to none. Measured on Albania: results-by-admin reached 38% of the row-group
# skip rate its row-group count allows, results-by-admin-conf 64%, and a Hilbert sort
# 95%. A 10%-of-extent window query read 43% of the file before and 19% after, and the
# sorted file is 39% smaller because spatial locality compresses better.
echo "[$REL] spatial sort"
gpio sort hilbert "$conf" "$out"

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
