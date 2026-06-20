# `fiboa/` — A1: raw `results/` → fiboa-refined GeoParquet

Turns the raw Wherobots output (`…/predictions/vectors/alpha/results/`, snappy parquet
with both fields and non-fields) into fiboa-compliant GeoParquet
(`…/results-fiboa/`): fields only, with fiboa schemas, geometry metrics, and
determination columns. This is the preferred "simple" CLI pipeline (streams via the
`gpio` CLI; an older all-in-one DuckDB variant, `convert_ftw_global.py`, lives in
`~/repos/ftw-scripts`).

| Script | Does | Run |
|---|---|---|
| `convert_ftw_simple.py` | `gpio extract geoparquet` straight from the S3 `results/` parts, filter to `label = 'field'`, drop `label`/`bbox`, write GeoParquet 2.0 (zstd-22). Parallel; uploads each result. | `python3 scripts/fiboa/convert_ftw_simple.py [--start N --end M --parallel P] [--skip-upload]` |
| `ftw_fiboa_improve.py` | `gpio fiboa improve` on stage-1 output: adds fiboa schemas, geometry metrics (`metrics:area`/`metrics:perimeter`), and `determination:*` columns. Deletes each input after success. | `python3 scripts/fiboa/ftw_fiboa_improve.py [--parallel P] [--keep-input]` |
| `ftw_upload_and_clean.sh` | `aws s3 cp` the improved files to `…/results-fiboa/`, `rm` on success. | `bash scripts/fiboa/ftw_upload_and_clean.sh` |

Process a single part end-to-end before launching a 1000-file run; both stages skip
parts whose output already exists, so reruns are cheap and resumable. Next stage:
[`../admin/`](../admin/).
