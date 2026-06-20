#!/usr/bin/env bash
# Bootstrap geoparquet-io (PR 471, --assume-crs84) + awscli on the NCSA rails box.
# Idempotent: safe to re-run. Logs to $WORK/install.log.
set -euo pipefail

WORK="$HOME/ftw-crs-fix"
VENV="$WORK/venv"
REPO="$WORK/geoparquet-io"
PR_REF="pull/471/head"
PR_BRANCH="pr-471"

mkdir -p "$WORK"
echo "=== load python module ==="
module load python/3.11.14
python3 --version

echo "=== venv ==="
if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --quiet --upgrade pip setuptools wheel

echo "=== clone / update geoparquet-io @ PR 471 ==="
if [ ! -d "$REPO/.git" ]; then
  git clone --quiet https://github.com/geoparquet/geoparquet-io.git "$REPO"
fi
cd "$REPO"
git fetch --quiet origin "$PR_REF"
git checkout --quiet -B "$PR_BRANCH" FETCH_HEAD
echo "HEAD: $(git log --oneline -1)"

echo "=== install geoparquet-io (editable) + awscli ==="
python -m pip install --quiet -e "$REPO"
python -m pip install --quiet awscli

echo "=== verify gpio + --assume-crs84 flag ==="
gpio --version
if gpio convert reproject --help 2>&1 | grep -q -- '--assume-crs84'; then
  echo "FLAG_OK: --assume-crs84 present"
else
  echo "FLAG_MISSING: --assume-crs84 NOT found" >&2
  exit 3
fi

echo "=== aws cli ==="
aws --version

echo "INSTALL_DONE"
