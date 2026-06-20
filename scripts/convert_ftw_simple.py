#!/usr/bin/env python3
"""
Convert FTW global predictions to GeoParquet 2.0.

Reads directly from S3 via gpio extract — no local download needed.
Filters to 'field' label only, drops label and bbox columns,
outputs GeoParquet 2.0 with zstd level 22. Runs multiple files in parallel.

Usage:
    python scripts/convert_ftw_simple.py                           # all 1000 files, 4 parallel
    python scripts/convert_ftw_simple.py --start 0 --end 20        # first 21 files
    python scripts/convert_ftw_simple.py --parallel 6              # 6 at a time
"""

import argparse
import os
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

S3_BASE = "s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data/predictions/vectors/alpha"
S3_RESULTS = f"{S3_BASE}/results"
S3_OUTPUT = f"{S3_BASE}/fiboa-results"
SPARK_UUID = "9aa5d1a5-7ded-4ad2-bb8f-dca43727645e"
GPIO = "/Users/cholmes/miniforge3/envs/g/bin/gpio"


def source_url(part_num):
    return f"{S3_RESULTS}/part-{part_num:05d}-{SPARK_UUID}-c000.snappy.parquet"


def output_filename(part_num):
    return f"ftw_global_{part_num:05d}.parquet"


def process_one(part_num, output_dir):
    out_path = os.path.join(output_dir, output_filename(part_num))
    t0 = time.time()
    result = subprocess.run(
        [
            GPIO,
            "--s3-endpoint", "s3.us-west-2.amazonaws.com",
            "--s3-region", "us-west-2",
            "extract", "geoparquet",
            source_url(part_num), out_path,
            "--where", "label = 'field'",
            "--exclude-cols", "label,bbox",
            "--geoparquet-version", "2.0",
            "--compression", "zstd",
            "--compression-level", "22",
            "--skip-count",
            "--overwrite",
        ],
        capture_output=True, text=True,
    )
    elapsed = time.time() - t0
    if result.returncode != 0:
        err = result.stderr.strip().split("\n")[-1]
        return part_num, False, 0, elapsed, err
    out_mb = os.path.getsize(out_path) / 1e6
    msg = result.stdout.strip()
    return part_num, True, out_mb, elapsed, msg


def main():
    parser = argparse.ArgumentParser(description="Convert FTW predictions to GeoParquet 2.0")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=999)
    parser.add_argument("--parallel", type=int, default=4, help="Number of parallel workers (default: 4)")
    parser.add_argument("--output-dir", type=str, default=os.path.expanduser("~/geodata/ftw/fiboa-results"))
    parser.add_argument("--skip-upload", action="store_true")
    args = parser.parse_args()

    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    pending = [
        pn for pn in range(args.start, args.end + 1)
        if not os.path.exists(os.path.join(output_dir, output_filename(pn)))
    ]

    if not pending:
        print("All files already processed.")
        return

    total = len(pending)
    print(f"{total} files to process with {args.parallel} parallel workers", flush=True)
    t_start = time.time()
    done = 0
    errors = 0

    with ProcessPoolExecutor(max_workers=args.parallel) as pool:
        futures = {pool.submit(process_one, pn, output_dir): pn for pn in pending}

        for future in as_completed(futures):
            pn, ok, out_mb, elapsed, msg = future.result()
            done += 1
            if ok:
                rate = done / (time.time() - t_start) * 3600
                eta_h = (total - done) / rate if rate > 0 else 0
                print(f"[{done}/{total}] Part {pn:05d}  {msg} ({out_mb:.0f} MB, {elapsed:.0f}s)  ETA: {eta_h:.1f}h", flush=True)
            else:
                errors += 1
                print(f"[{done}/{total}] Part {pn:05d}  ERROR: {msg}", flush=True)

            if not args.skip_upload and ok:
                s3_dest = f"{S3_OUTPUT}/{output_filename(pn)}"
                subprocess.run(["aws", "s3", "cp", os.path.join(output_dir, output_filename(pn)), s3_dest],
                               capture_output=True, text=True)

    elapsed_total = time.time() - t_start
    output_files = sorted(Path(output_dir).glob("ftw_global_*.parquet"))
    total_mb = sum(f.stat().st_size for f in output_files) / 1e6
    print(f"\nDone! {len(output_files)} files, {total_mb/1000:.1f} GB total, {elapsed_total/3600:.1f}h elapsed, {errors} errors", flush=True)


if __name__ == "__main__":
    main()
