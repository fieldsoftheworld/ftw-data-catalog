#!/usr/bin/env bash
# Publish the STAC catalog metadata (JSON + README + llms.txt + thumbnails) to S3,
# colocated with the data. Does NOT touch the COGs (those are relocated by restructure_s3.sh).
#
#   ./publish_metadata.sh           # DRY RUN (aws s3 cp --dryrun)
#   CONFIRM=1 ./publish_metadata.sh # execute uploads
#
# Uses default AWS credentials. Never uploads .env, .git, *.tif, or portolan internal state.
set -euo pipefail

REMOTE="s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data"
REGION="us-west-2"
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

DRY="--dryrun"; [[ "${CONFIRM:-0}" == "1" ]] && DRY=""

cp_one() { # local-rel  content-type
  local rel="$1" ctype="$2"
  aws s3 cp $DRY "$rel" "$REMOTE/$rel" --region "$REGION" --content-type "$ctype"
}

# NOTE: the root catalog.json and root llms.txt are intentionally held back (not published yet).
# This publishes only the confidence collection and its contents.

# Collection-level
cp_one "predictions/confidence/collection.json" "application/json"
cp_one "predictions/confidence/README.md" "text/markdown; charset=utf-8"
cp_one "predictions/confidence/llms.txt" "text/markdown; charset=utf-8"
cp_one "predictions/confidence/thumbnail.png" "image/png"
cp_one "predictions/confidence/.portolan/metadata.yaml" "text/yaml; charset=utf-8"

# Items (item JSON + per-item llms.txt + per-item thumbnail where present)
for item in confidence field-density entropy crop-consensus precision-recall; do
  cp_one "predictions/confidence/$item/$item.json" "application/geo+json"
  cp_one "predictions/confidence/$item/llms.txt" "text/markdown; charset=utf-8"
  if [[ -f "predictions/confidence/$item/thumbnail.png" ]]; then
    cp_one "predictions/confidence/$item/thumbnail.png" "image/png"
  fi
done

if [[ -n "$DRY" ]]; then echo ""; echo "DRY RUN — re-run with CONFIRM=1 to upload."; fi
