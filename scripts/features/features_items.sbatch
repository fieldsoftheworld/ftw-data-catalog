#!/bin/bash
# Generate the per-tile features items + items.parquet (S3-only) on TGI rails **via Slurm**.
#
# IMPORTANT: run on a compute node, not the rails login node (which reaps heavy jobs).
# Submit one job per year (they run in parallel on separate nodes):
#
#     rsync -av scripts/features/ rails:ftw-feat/
#     ssh rails 'cd ~/ftw-feat && sbatch --export=ALL,YEAR=2024 features_items.sbatch'
#     ssh rails 'cd ~/ftw-feat && sbatch --export=ALL,YEAR=2025 features_items.sbatch'
#
# Outputs go to s3://…/features/<year>/items/ + items.parquet and are NOT committed.
# Compute nodes have outbound S3 access (verified).
# Docs: https://docs.ncsa.illinois.edu/systems/tgirails/en/latest/running_jobs.html
#SBATCH --job-name=ftw-feat
#SBATCH --partition=cpu
#SBATCH --account=bgtj-tgirails
#SBATCH --time=12:00:00
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48g
#SBATCH --output=ftw-feat-%j.out
set -euo pipefail
export PATH=/u/cholmes/micromamba/envs/ftw/bin:$PATH
export AWS_DEFAULT_REGION=us-west-2
YEAR="${YEAR:?set YEAR=2024 or 2025 via sbatch --export=ALL,YEAR=...}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python "$SCRIPT_DIR/build_features_items.py" items "$YEAR" --workdir "/tmp/ftw-feat-${YEAR}-${SLURM_JOB_ID:-$$}"
