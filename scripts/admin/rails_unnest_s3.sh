#!/usr/bin/env bash
# Flatten the giant subdivision files on S3:
#   admin:country_code=<CC>/admin:subdivision_code=<sub>/<CountryName>.parquet
#   -> admin:country_code=<CC>/<CC>_<sub>.parquet
# Server-side aws s3 mv (no re-upload). Parallel.
set -uo pipefail
source ~/ftw-crs-fix/venv/bin/activate
BUCKET="us-west-2.opendata.source.coop"
PFX="tge-labs/ftw-global-data/predictions/vectors/alpha/results-by-admin"

aws s3 ls "s3://$BUCKET/$PFX/" --recursive --region us-west-2 \
  | awk '{print $4}' | grep "admin:subdivision_code=" > ~/ftw-crs-fix/nested_keys.txt
echo "nested objects to flatten: $(wc -l < ~/ftw-crs-fix/nested_keys.txt)"

move_one() {
  key="$1"
  cc=$(printf '%s' "$key" | sed -n 's#.*admin:country_code=\([^/]*\)/.*#\1#p')
  sub=$(printf '%s' "$key" | sed -n 's#.*admin:subdivision_code=\([^/]*\)/.*#\1#p')
  dst="$PFX/admin:country_code=$cc/${cc}_${sub}.parquet"
  aws s3 mv "s3://$BUCKET/$key" "s3://$BUCKET/$dst" --region us-west-2 --only-show-errors
}
export -f move_one; export BUCKET PFX
xargs -P 16 -I{} bash -c 'move_one "$@"' _ {} < ~/ftw-crs-fix/nested_keys.txt
echo S3_UNNEST_DONE
