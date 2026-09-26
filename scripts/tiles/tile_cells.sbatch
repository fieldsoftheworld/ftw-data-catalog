#!/bin/bash
# Tile a per-year a5 cells file into the low-zoom exploration PMTiles:
# a single "cells" layer, every cell verbatim at every zoom (no thinning,
# no drops), z0-8. Prints a per-zoom tile-weight report afterwards so the
# <=600 KB @ z2+ budget can be checked.
#
#   YEAR=2025 R=7 sbatch --export=ALL tile_cells.sbatch
#   (IN=... to override; defaults to cells_a5r${R}_${YEAR}.parquet)
#SBATCH --job-name=ftw-tile-cells
#SBATCH --partition=cpu
#SBATCH --account=bgtj-tgirails
#SBATCH --time=12:00:00
#SBATCH --nodes=1
#SBATCH --cpus-per-task=48
#SBATCH --mem=192G
#SBATCH --output=%x-%j.out
set -euo pipefail
: "${YEAR:?set YEAR via --export=ALL,YEAR=..}"
R="${R:-7}"
cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")}"
IN="${IN:-$PWD/cells_a5r${R}_${YEAR}.parquet}"
OUT="${OUT:-fields-${YEAR}-a5r${R}.pmtiles}"
TT="${TT:-$HOME/tylertoo-src/target/release/tylertoo}"
export TMPDIR="$PWD/tmp-tile-cells-${YEAR}"   # /u spill — /tmp is tmpfs
mkdir -p "$TMPDIR"
trap 'rm -rf "$TMPDIR"' EXIT
export RUST_LOG=info

"$TT" tiles "$IN" "$OUT" \
  --min-zoom 0 --max-zoom 8 --layer-name cells --verbatim \
  --profile bounded -v -f

ls -la "$OUT"
sha256sum "$OUT"
echo "== per-zoom tile weights"
~/ftw-us-tiles/venv/bin/python3 tile_weights.py "$OUT"
echo "TILE-CELLS-DONE"
