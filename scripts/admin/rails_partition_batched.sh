#!/usr/bin/env bash
# Memory-safe (64 GB cgroup) size-adaptive partition via gpio (vec-valid output). RESUMABLE.
# Phase 1: partition admin files in small batches by country -> batch_parts/bNNN/{C}.parquet (+ .done)
# Phase 2: per country, merge its batch files into final form with ONE bounded gpio call:
#          small -> final/{C}.parquet ; big (> THRESH rows) -> final/{C}_{region}.parquet
# Small batches => few partition buffers per gpio call => stays under the 64 GB cap.
set -uo pipefail

WORK="$HOME/ftw-crs-fix"
ADMIN="$WORK/admin"
BP="$WORK/batch_parts"
LNK="$WORK/_links"
FINAL="$WORK/final_partitions"
export TMPDIR="$WORK/tmp"; mkdir -p "$TMPDIR" "$BP" "$FINAL"
WMEM="${WMEM:-4GB}"
BATCH="${BATCH:-20}"
THRESH_ROWS="${THRESH_ROWS:-29000000}"
LIMIT="${LIMIT:-0}"

module load python/3.11.14
# shellcheck disable=SC1091
source "$WORK/venv/bin/activate"
GP() { gpio partition string "$1" "$2" --column "$3" --write-memory "$WMEM" --force --skip-analysis "${@:4}" >/dev/null 2>&1; }

mapfile -t FILES < <(ls -1 "$ADMIN"/ftw_global_*.parquet | sort)
[ "$LIMIT" -gt 0 ] && FILES=("${FILES[@]:0:$LIMIT}")

# rebuild symlink batches (cheap)
rm -rf "$LNK"; mkdir -p "$LNK"
n=0; i=0; bdir=""
for f in "${FILES[@]}"; do
  if [ $((i % BATCH)) -eq 0 ]; then bdir="$LNK/b$(printf '%03d' "$n")"; mkdir -p "$bdir"; n=$((n+1)); fi
  ln -sf "$f" "$bdir/"; i=$((i+1))
done
echo "phase1: ${#FILES[@]} files, $n batches, batch=$BATCH wmem=$WMEM"

# ---- Phase 1 (resumable: skip batches with .done) ----
b=0
for bdir in "$LNK"/b*; do
  b=$((b+1)); bn=$(basename "$bdir")
  if [ -f "$BP/$bn/.done" ]; then echo "  $bn ($b/$n) already done"; continue; fi
  rm -rf "$BP/$bn"   # clear any partial
  if GP "$bdir/*.parquet" "$BP/$bn" "admin:country_code"; then
    touch "$BP/$bn/.done"; echo "  $bn ($b/$n) ok"
  else
    echo "  $bn ($b/$n) FAILED"
  fi
done

# ---- per-country totals ----
python - "$BP" > "$WORK/country_rows.txt" <<'PY'
import sys, glob, os, collections
import pyarrow.parquet as pq
bp=sys.argv[1]; tot=collections.Counter()
for f in glob.glob(os.path.join(bp,"b*","*.parquet")):
    tot[os.path.basename(f)[:-8]] += pq.ParquetFile(f).metadata.num_rows
for c,nn in sorted(tot.items()): print(c, nn)
PY
echo "phase2: $(wc -l < "$WORK/country_rows.txt") countries"

# ---- Phase 2 (resumable: skip countries already finalized) ----
mkdir -p "$LNK/c"
while read -r C ROWS; do
  if compgen -G "$FINAL/${C}.parquet" >/dev/null || compgen -G "$FINAL/${C}_*.parquet" >/dev/null; then
    echo "  $C already finalized"; continue
  fi
  cl="$LNK/c/$C"; rm -rf "$cl"; mkdir -p "$cl"
  for bf in "$BP"/b*/"$C.parquet"; do [ -e "$bf" ] && ln -sf "$bf" "$cl/$(basename "$(dirname "$bf")")_$C.parquet"; done
  if [ "$ROWS" -gt "$THRESH_ROWS" ]; then
    GP "$cl/*.parquet" "$FINAL" "admin:subdivision_code" --prefix "$C" && echo "  $C ($ROWS) split" || echo "  $C SPLIT FAILED"
  else
    GP "$cl/*.parquet" "$FINAL" "admin:country_code" && echo "  $C ($ROWS) whole" || echo "  $C MERGE FAILED"
  fi
done < "$WORK/country_rows.txt"

# ---- verify ----
python - "$ADMIN" "$FINAL" "$LIMIT" <<'PY'
import sys, glob, os, json
import pyarrow.parquet as pq
admin, final, limit = sys.argv[1], sys.argv[2], int(sys.argv[3])
af=sorted(glob.glob(os.path.join(admin,"ftw_global_*.parquet")));
if limit>0: af=af[:limit]
inr=sum(pq.ParquetFile(f).metadata.num_rows for f in af)
ff=sorted(glob.glob(os.path.join(final,"*.parquet"))); outr=0; bad=0
for f in ff:
    pf=pq.ParquetFile(f); md=pf.schema_arrow.metadata or {}
    ok=(b'collection' in md) and ('crs' not in json.loads(md[b'geo'])['columns']['geometry'])
    outr+=pf.metadata.num_rows
    if not ok: bad+=1
print(f"input_rows={inr} output_rows={outr} reconcile={inr==outr} partitions={len(ff)} schema_bad={bad}")
PY
echo "=== vec validate 2 ==="
for F in $(ls "$FINAL"/*.parquet 2>/dev/null | head -2); do printf '%s: ' "$(basename "$F")"; vec validate "$F" 2>&1 | grep -aoE 'VALID|INVALID' | head -1; done
echo "BATCHED_PARTITION_DONE"
