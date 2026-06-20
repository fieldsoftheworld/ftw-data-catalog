#!/usr/bin/env bash
# Parallel driver for rails_relayout.py — one country per worker, resumable (.done markers).
# Usage: bash rails_relayout_all.sh [PARALLEL] [CC ...]
set -uo pipefail
WORK="$HOME/ftw-crs-fix"
export TMPDIR="$WORK/tmp"; mkdir -p "$TMPDIR"
module load python/3.11.14
# shellcheck disable=SC1091
source "$WORK/venv/bin/activate"

PAR="${1:-8}"; shift || true
if [ "$#" -gt 0 ]; then
  printf '%s\n' "$@" > "$WORK/relayout_codes.txt"
else
  python -c "import json; [print(c) for c in sorted(json.load(open('$WORK/country_names.json')))]" > "$WORK/relayout_codes.txt"
fi
echo "relayout: $(wc -l < "$WORK/relayout_codes.txt") countries, parallel=$PAR"
xargs -P "$PAR" -n1 -I{} python "$WORK/rails_relayout.py" {} < "$WORK/relayout_codes.txt"
echo "done dirs: $(ls -d "$WORK"/results_by_admin/admin:* 2>/dev/null | wc -l)"
echo "RELAYOUT_ALL_DONE"
