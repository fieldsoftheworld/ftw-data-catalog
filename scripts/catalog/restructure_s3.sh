#!/usr/bin/env bash
# Restructure the 11 confidence COGs on S3 from the flat layout into the STAC item-directory
# layout (server-side moves; no download/upload). Idempotent: skips files already moved.
#
#   ./restructure_s3.sh          # DRY RUN: print the planned moves, touch nothing
#   CONFIRM=1 ./restructure_s3.sh # execute the server-side aws s3 mv operations
#
# Uses default AWS credentials (writes to the user's bucket). Reads are within the same bucket.
set -euo pipefail

BUCKET="s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data/predictions/confidence"
REGION="us-west-2"

# file -> item-dir
declare -a MAP=(
  "prue_v1_confidence_global.tif:confidence"
  "prue_v1_confidence_global_uint8_3857.tif:confidence"
  "prue_v1_field_area_500m.tif:field-density"
  "prue_v1_field_area_500m_conf0.4.tif:field-density"
  "prue_v1_field_area_500m_conf0.5.tif:field-density"
  "prue_v1_field_area_500m_filtered.tif:field-density"
  "prue_v1_field_area_500m_fieldsonly.tif:field-density"
  "prue_v1_field_area_500m_fieldsonly_uint8_3857.tif:field-density"
  "prue_v1_entropy_500m.tif:entropy"
  "prue_v1_crop_count_mean_500m.tif:crop-consensus"
  "prue_v1_precision_recall_500m.tif:precision-recall"
)

DRY=1; [[ "${CONFIRM:-0}" == "1" ]] && DRY=0

for entry in "${MAP[@]}"; do
  file="${entry%%:*}"; item="${entry##*:}"
  src="$BUCKET/$file"
  dst="$BUCKET/$item/$file"
  if [[ $DRY -eq 1 ]]; then
    echo "MOVE  $src"
    echo "  ->  $dst"
  else
    # skip if already at destination
    if aws s3 ls "$dst" --region "$REGION" >/dev/null 2>&1; then
      echo "skip (exists): $dst"
    else
      echo "moving: $file -> $item/"
      aws s3 mv "$src" "$dst" --region "$REGION"
    fi
  fi
done
if [[ $DRY -eq 1 ]]; then echo ""; echo "DRY RUN — re-run with CONFIRM=1 to execute."; fi
