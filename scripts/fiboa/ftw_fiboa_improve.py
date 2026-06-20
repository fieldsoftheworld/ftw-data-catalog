#!/usr/bin/env python3
"""
Run gpio fiboa improve on all FTW files.

Adds fiboa schemas, geometry metrics, determination columns.
Processes in parallel, deletes input after successful output.

Usage:
    python scripts/ftw_fiboa_improve.py                    # all files, 4 parallel
    python scripts/ftw_fiboa_improve.py --parallel 6       # 6 at a time
"""

import argparse
import glob
import os
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

GPIO = "/Users/cholmes/miniforge3/envs/g/bin/gpio"
INPUT_DIR = os.path.expanduser("~/geodata/ftw/fiboa-results")
OUTPUT_DIR = os.path.expanduser("~/geodata/ftw/fiboa-improved")


def process_one(input_path, output_path):
    t0 = time.time()
    result = subprocess.run(
        [
            GPIO, "fiboa", "improve",
            "-s", "-sz",
            input_path, output_path,
            "--determination-datetime", "time",
            "--determination-method", "auto-imagery",
            "--compression", "zstd",
            "--compression-level", "22",
            "--overwrite",
        ],
        capture_output=True, text=True,
    )
    elapsed = time.time() - t0
    if result.returncode != 0:
        err = result.stderr.strip().split("\n")[-1]
        return input_path, False, 0, elapsed, err
    out_mb = os.path.getsize(output_path) / 1e6
    return input_path, True, out_mb, elapsed, ""


def main():
    parser = argparse.ArgumentParser(description="Run fiboa improve on FTW files")
    parser.add_argument("--parallel", type=int, default=4)
    parser.add_argument("--input-dir", default=INPUT_DIR)
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    parser.add_argument("--keep-input", action="store_true")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    inputs = sorted(glob.glob(os.path.join(args.input_dir, "ftw_global_*.parquet")))
    pending = []
    for inp in inputs:
        name = os.path.basename(inp)
        out = os.path.join(args.output_dir, name)
        if os.path.exists(out):
            continue
        pending.append((inp, out))

    if not pending:
        print("All files already processed.")
        return

    total = len(pending)
    print(f"{total} files to process with {args.parallel} parallel workers", flush=True)
    t_start = time.time()
    done = 0
    errors = 0

    with ProcessPoolExecutor(max_workers=args.parallel) as pool:
        futures = {pool.submit(process_one, inp, out): (inp, out) for inp, out in pending}

        for future in as_completed(futures):
            inp, out = futures[future]
            inp_path, ok, out_mb, elapsed, err = future.result()
            done += 1
            name = os.path.basename(inp_path)

            if ok:
                rate = done / (time.time() - t_start) * 3600
                eta_h = (total - done) / rate if rate > 0 else 0
                print(f"[{done}/{total}] {name}  {out_mb:.0f} MB  {elapsed:.0f}s  ETA: {eta_h:.1f}h", flush=True)
                if not args.keep_input:
                    os.unlink(inp_path)
            else:
                errors += 1
                print(f"[{done}/{total}] {name}  ERROR: {err}", flush=True)
                if os.path.exists(out):
                    os.unlink(out)

    elapsed_total = time.time() - t_start
    output_files = sorted(Path(args.output_dir).glob("ftw_global_*.parquet"))
    total_gb = sum(f.stat().st_size for f in output_files) / 1e9
    print(f"\nDone! {len(output_files)} files, {total_gb:.1f} GB, {elapsed_total/3600:.1f}h, {errors} errors", flush=True)


if __name__ == "__main__":
    main()
