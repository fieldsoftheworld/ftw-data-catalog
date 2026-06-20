#!/usr/bin/env bash
# Copy the 2024 confidence PMTiles from the Azure visualizer host into this
# catalog's S3 prefix, so the collection serves its own copy. Streams through
# memory (no local disk needed); best run on rails (fast network). ~264 GB.
#
# Needs AWS write creds for the Source Cooperative bucket. Idempotent-ish: pass
# --force to re-upload if the destination already exists.
set -euo pipefail

SRC="${SRC:-https://geospatialvisualizer.z13.web.core.windows.net/ftw_visualizer/data/2024_with_confidence.pmtiles}"
DST="${DST:-s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data/predictions/vectors/alpha/2024_with_confidence.pmtiles}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-west-2}"

if [[ "${1:-}" != "--force" ]] && aws s3 ls "$DST" >/dev/null 2>&1; then
  echo "SKIP: $DST already exists (pass --force to overwrite)"
  exit 0
fi

# --expected-size lets the CLI pick a multipart chunk size big enough for ~264 GB.
size="$(curl -sIL "$SRC" | awk 'tolower($1)=="content-length:"{n=$2} END{gsub(/\r/,"",n); print n}')"
echo "Streaming $SRC ($size bytes) -> $DST"
curl -sL "$SRC" \
  | aws s3 cp - "$DST" \
      --expected-size "$size" \
      --content-type application/vnd.pmtiles
echo "DONE $DST"
