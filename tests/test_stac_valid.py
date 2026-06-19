"""STAC metadata validation via the Portolan CLI.

Runs `portolan check --metadata` against catalog/ when the Portolan CLI is
installed, and SKIPs (exit 0) when it isn't — so the local suite stays
zero-setup while CI, which installs the CLI, enforces validation.
Run: python3 tests/test_stac_valid.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / "catalog"


def main() -> int:
    if shutil.which("portolan") is None:
        print("SKIP: portolan CLI not installed; STAC validation skipped "
              "(CI installs it and enforces this).")
        return 0
    proc = subprocess.run(
        ["portolan", "check", "--metadata"],
        cwd=CATALOG, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        print("FAIL: portolan check --metadata reported errors")
        return 1
    print("OK: portolan check --metadata passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
