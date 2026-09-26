#!/bin/bash
# Per-year a5 cell aggregation for the low-zoom exploration layer.
#
# Produces cells_a5r${R}_${YEAR}.parquet with, per a5 cell:
#   count          number of fields
#   sum_area       total field area (m2)
#   avg_confidence mean prediction confidence (null where source has none)
#   pct_covered    100 * sum_area / spheroid cell area (can slightly exceed
#                  100: a boundary field's full area counts in its home cell)
#
#   YEAR=2025 R=7 sbatch --export=ALL aggregate_cells.sbatch
#   (IN=... to override the input; defaults to global${YEAR}_gp2.parquet)
#SBATCH --job-name=ftw-agg-cells
#SBATCH --partition=cpu
#SBATCH --account=bgtj-tgirails
#SBATCH --time=24:00:00
#SBATCH --nodes=1
#SBATCH --cpus-per-task=48
#SBATCH --mem=192G
#SBATCH --output=%x-%j.out
set -euo pipefail
: "${YEAR:?set YEAR via --export=ALL,YEAR=..}"
R="${R:-7}"
cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")}"
IN="${IN:-$PWD/global${YEAR}_gp2.parquet}"
export PATH="$HOME/ftw-us-tiles/venv/bin:/u/cholmes/micromamba/envs/ftw/bin:$PATH"
export TMPDIR="$PWD/tmp-cells-${YEAR}"   # /u spill — /tmp is tmpfs
mkdir -p "$TMPDIR"
trap 'rm -rf "$TMPDIR"' EXIT

RAW="cells_a5r${R}_${YEAR}_raw.parquet"
PLAIN="cells_a5r${R}_${YEAR}_plain.parquet"
OUT="cells_a5r${R}_${YEAR}.parquet"

echo "== a5 aggregate r${R} from ${IN}"
[ -f "$RAW" ] || gpio process aggregate a5 "$IN" "$RAW" \
  --resolution "$R" --metric "sum:area,avg:confidence" \
  --out-geometry polygon --geoparquet-version 2.0

echo "== add pct_covered"
# DuckDB output loses the 'geo' metadata key on rails; gpio convert restores it.
python3 add_coverage.py "$RAW" "$PLAIN"
gpio convert geoparquet "$PLAIN" "$OUT" --geoparquet-version 2.0
rm -f "$PLAIN"

python3 - "$OUT" <<'EOF'
import sys, duckdb
c = duckdb.connect(); c.execute("INSTALL spatial; LOAD spatial")
print(c.execute(f"DESCRIBE SELECT * FROM '{sys.argv[1]}'").df().to_string(), flush=True)
print(c.execute(f"""SELECT count(*) cells, sum(count) fields, round(sum(sum_area)/1e12,2) mkm2,
    round(avg(pct_covered),2) mean_pct, round(max(pct_covered),1) max_pct
    FROM '{sys.argv[1]}'""").df().to_string(), flush=True)
EOF
echo "CELLS-DONE"
