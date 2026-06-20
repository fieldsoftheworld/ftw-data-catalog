#!/usr/bin/env bash
# Drive confidence + PMTiles processing across the results-by-admin partitions,
# on the NCSA rails cluster. Builds a manifest from S3, optionally filters to a
# country subset, runs N partitions in parallel. process_partition.sh is
# idempotent, so re-running resumes where it left off.
#
# ── One-time setup on rails ──────────────────────────────────────────────────
#   1. From your laptop, authenticate once (Kerberos + Duo); the ControlPersist
#      socket then keeps the connection warm so later ssh calls are passwordless:
#          ssh rails
#   2. Copy these scripts over (or git clone the repo) and install deps:
#          rsync -av scripts/confidence/ rails:~/ftw-conf/
#          ssh rails 'pip install --user pyarrow rasterio shapely numpy affine'
#      (gpio + tippecanoe + aws are expected to already be on PATH on rails.)
#   3. Configure AWS write creds for the Source Cooperative bucket on rails
#      (e.g. ~/.aws/credentials profile, or AWS_ACCESS_KEY_ID/SECRET env).
#
# ── Run (on rails) ───────────────────────────────────────────────────────────
#   ./run_rails.sh --list              # preview the full 574-file manifest
#   ./run_rails.sh AD FR               # pilot: just these country codes
#   ./run_rails.sh --all -j 6          # everything, 6 workers
#   nohup ./run_rails.sh --all -j 6 >run.log 2>&1 &   # long unattended run
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data/predictions/vectors/alpha"
SRC_PREFIX="${SRC_PREFIX:-$BASE/results-by-admin}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-west-2}"

JOBS=4; ALL=0; LIST=0; FILTERS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -j) JOBS="$2"; shift 2;;
    --all) ALL=1; shift;;
    --list) LIST=1; shift;;
    -h|--help) sed -n '2,30p' "$0"; exit 0;;
    *) FILTERS+=("$1"); shift;;
  esac
done

# Manifest: every parquet key relative to results-by-admin/ (public read).
mapfile -t KEYS < <(
  aws s3 ls --no-sign-request --recursive "$SRC_PREFIX/" \
    | awk '{print $NF}' | grep '\.parquet$' \
    | sed "s#.*/results-by-admin/##"
)
[[ ${#KEYS[@]} -gt 0 ]] || { echo "ERROR: empty manifest from $SRC_PREFIX" >&2; exit 1; }

sel=()
if [[ $ALL -eq 1 || ${#FILTERS[@]} -eq 0 ]]; then
  sel=("${KEYS[@]}")
else
  for k in "${KEYS[@]}"; do
    for f in "${FILTERS[@]}"; do
      if [[ "$k" == "admin:country_code=$f/"* ]]; then sel+=("$k"); break; fi
    done
  done
fi

if [[ $LIST -eq 1 ]]; then
  printf '%s\n' "${sel[@]}"
  echo "(${#sel[@]} of ${#KEYS[@]} partitions)"
  exit 0
fi
[[ ${#sel[@]} -gt 0 ]] || { echo "ERROR: no partitions matched filters: ${FILTERS[*]}" >&2; exit 1; }

echo "Processing ${#sel[@]} partitions with $JOBS worker(s)"
printf '%s\0' "${sel[@]}" \
  | xargs -0 -P "$JOBS" -I{} bash "$SCRIPT_DIR/process_partition.sh" "{}"
echo "All requested partitions processed."
