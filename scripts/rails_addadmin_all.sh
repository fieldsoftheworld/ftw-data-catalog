#!/usr/bin/env bash
# Step A: add Vecorel admin divisions to every results-fiboa part, keeping outputs on local /u
# (no S3 upload). Resumable: skips parts whose admin output already exists. 8-way parallel.
#
# Usage:
#   bash rails_addadmin_all.sh            # driver
#   bash rails_addadmin_all.sh one NNNNN  # internal single part
set -uo pipefail

WORK="$HOME/ftw-crs-fix"
SCRATCH="$WORK/scratch"
ADMIN="$WORK/admin"          # persistent admin-augmented outputs (kept for later experimentation)
VENV="$WORK/venv"
SELF="$WORK/rails_addadmin_all.sh"
MANIFEST="$WORK/admin_manifest.csv"
export TMPDIR="$WORK/tmp"
REGION="us-west-2"
BUCKET="us-west-2.opendata.source.coop"
PREFIX="tge-labs/ftw-global-data/predictions/vectors/alpha"
SRC="s3://$BUCKET/$PREFIX/results-fiboa"
NPARTS=1000
PARALLEL=20
WRITE_MEM="3GB"
LWORK="/tmp/ftw_addadmin"   # local tmpfs staging (avoid NFS I/O contention on /u)

ensure_env() {
  mkdir -p "$SCRATCH" "$TMPDIR" "$ADMIN"
  if ! command -v gpio >/dev/null 2>&1; then
    module load python/3.11.14
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
  fi
}

if [ "${1:-}" = "one" ]; then
  PART="$2"
  FILE="ftw_global_${PART}.parquet"
  # Stage all hot I/O on local tmpfs; TMPDIR here is also where DuckDB temp + gpio's vecorel
  # os.replace land (same device as OUTL, so the replace is atomic, not cross-device).
  export TMPDIR="$LWORK"
  IN="$LWORK/in_${PART}.parquet"
  OUTL="$LWORK/out_${PART}.parquet"
  FINAL="$ADMIN/$FILE"
  ensure_env

  if ! aws s3 cp "$SRC/$FILE" "$IN" --no-sign-request --region "$REGION" --only-show-errors; then
    echo "${PART},DOWNLOAD_FAIL,,,," >> "$MANIFEST"; rm -f "$IN"; exit 1
  fi

  if ! gpio add admin-divisions "$IN" "$OUTL" --vecorel --overwrite --write-memory "$WRITE_MEM" >/dev/null 2>&1; then
    echo "${PART},ADD_FAIL,,,," >> "$MANIFEST"; rm -f "$IN" "$OUTL"; exit 1
  fi

  read -r STATUS INROWS OUTROWS COLL ADMINCOLS < <(python - "$IN" "$OUTL" <<'PY'
import sys, json
import pyarrow.parquet as pq
inp, outp = sys.argv[1], sys.argv[2]
pin, pout = pq.ParquetFile(inp), pq.ParquetFile(outp)
md = pout.schema_arrow.metadata or {}
names = pout.schema_arrow.names
has_admin = ('admin:country_code' in names) and ('admin:subdivision_code' in names)
coll = (b'collection' in md)
ir, orr = pin.metadata.num_rows, pout.metadata.num_rows
# out rows should be >= in rows (tiny straddle increase), and not absurdly larger (<1.5x guards fan-out regression)
ok = has_admin and coll and (orr >= ir) and (orr <= ir * 1.5)
print(("OK" if ok else "VERIFY_FAIL"), ir, orr, coll, has_admin)
PY
)
  if [ "$STATUS" != "OK" ]; then
    echo "${PART},${STATUS:-VERIFY_FAIL},${INROWS:-},${OUTROWS:-},${COLL:-},${ADMINCOLS:-}" >> "$MANIFEST"
    rm -f "$IN" "$OUTL"; exit 1
  fi

  # The only NFS write in the hot path: move the finished output to /u (cross-device copy+unlink).
  if ! mv -f "$OUTL" "$FINAL"; then
    echo "${PART},MOVE_FAIL,${INROWS},${OUTROWS},${COLL},${ADMINCOLS}" >> "$MANIFEST"; rm -f "$IN" "$OUTL"; exit 1
  fi
  echo "${PART},OK,${INROWS},${OUTROWS},${COLL},${ADMINCOLS}" >> "$MANIFEST"
  rm -f "$IN"
  exit 0
fi

# ---- driver ----
ensure_env
echo "gpio: $(cd "$WORK/geoparquet-io" && git log --oneline -1)"
echo "admin cache files:"; ls -1 ~/.geoparquet-io/cache/admin/ 2>/dev/null | grep -i land || echo "  (no land cache yet — first worker will build it)"
[ -f "$MANIFEST" ] || echo "part,status,in_rows,out_rows,collection,admin_cols" > "$MANIFEST"
echo "host=$(hostname) nproc=$(nproc) ram=$(free -g | awk '/Mem/{print $2}')GB parallel=$PARALLEL TMPDIR=$TMPDIR ADMIN=$ADMIN"

# resume from existing admin outputs on disk
TODO="$WORK/admin_todo.txt"; : > "$TODO"
for i in $(seq 0 $((NPARTS-1))); do
  part=$(printf '%05d' "$i")
  [ -f "$ADMIN/ftw_global_${part}.parquet" ] || echo "$part" >> "$TODO"
done
echo "already done: $((NPARTS - $(wc -l < "$TODO"))) / to process: $(wc -l < "$TODO")"

echo "=== launching $PARALLEL-way parallel add admin-divisions ==="
xargs -P "$PARALLEL" -n1 -I{} bash "$SELF" one {} < "$TODO"

OK=$(grep -c ',OK,' "$MANIFEST" || true)
FAIL=$(grep -cvE ',OK,|^part,' "$MANIFEST" || true)
echo "=== run complete: OK=$OK FAIL=$FAIL ==="
echo "admin files on disk: $(ls -1 "$ADMIN"/ftw_global_*.parquet 2>/dev/null | wc -l)"
echo "admin dir size: $(du -sh "$ADMIN" 2>/dev/null | cut -f1)"
echo "ADD_ADMIN_ALL_DONE"
