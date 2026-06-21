#!/bin/bash
# Run the confidence + per-country PMTiles processing on TGI rails **via Slurm**.
#
# IMPORTANT: do NOT run this on the rails *login* node — heavy tippecanoe/duckdb work
# gets silently reaped there by the login-node watchdog (jobs just die mid-run). Submit
# to a compute node instead:
#
#     rsync -av scripts/confidence/ rails:ftw-conf/      # deploy scripts + this sbatch
#     ssh rails 'cd ~/ftw-conf && sbatch run_rails.sbatch'
#     ssh rails 'squeue -u $USER'                        # watch the queue
#
# Idempotent (skip-existing), so the same job does the full run AND, re-run later,
# sweeps any stragglers. Compute nodes on rails DO have outbound S3 access (verified).
# Docs: https://docs.ncsa.illinois.edu/systems/tgirails/en/latest/running_jobs.html
#SBATCH --job-name=ftw-vectors
#SBATCH --partition=cpu
#SBATCH --account=bgtj-tgirails
#SBATCH --time=24:00:00
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --output=ftw-vectors-%j.out
set -euo pipefail
export PATH=/u/cholmes/micromamba/envs/ftw/bin:$PATH       # toolchain on shared /u
export AWS_DEFAULT_REGION=us-west-2
export WORK="/tmp/ftw-vectors-${SLURM_JOB_ID:-$$}"          # node-local scratch (fast tippecanoe temp)
mkdir -p "$WORK"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# -j 4 is safe on a dedicated (--exclusive) node; the login-node OOMs were from sharing.
"$SCRIPT_DIR/run_rails.sh" --all -j 4
