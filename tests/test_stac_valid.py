"""Complete STAC validation via stac-check (per file).

Lints every STAC object under catalog/ (catalog.json, all collection.json, all
item JSONs) with stac-check's Linter in per-file mode (recursive=False).

Per-file is deliberate: stac-validator's recursive link-resolver has a bug
("list index out of range") that fires on a directory-less path + relative
links — purely an artifact of recursive invocation, not a catalog defect (this
catalog validates 7/7). Per-file sidesteps it entirely.

Each object is checked for STAC JSON-schema validity (hard failure; a Linter
that raises on a malformed field is also a failure) and for best-practice notes
(printed as non-fatal warnings). SKIPs (exit 0) when stac-check isn't installed,
so the local suite stays zero-setup; CI installs it and enforces this. Needs
network to fetch the schemas. Run: python3 tests/test_stac_valid.py
"""
import sys
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / "catalog"


def stac_files():
    """catalog.json + every collection.json + every item JSON (item subdirs)."""
    seen, out = set(), []
    candidates = [CATALOG / "catalog.json", *CATALOG.glob("**/collection.json"),
                  *CATALOG.glob("**/*/*.json")]
    for p in candidates:
        if ".portolan" in p.parts or "styles" in p.parts or p.name.endswith(".style.json"):
            continue  # MapLibre styles (styles/*.json and *.style.json) are not STAC
        if p.is_file() and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def main() -> int:
    try:
        from stac_check.lint import Linter
    except ImportError:
        print("SKIP: stac-check not installed; STAC validation skipped "
              "(CI installs it and enforces this).")
        return 0

    files = stac_files()
    failures, warnings = [], []
    for f in files:
        rel = f.relative_to(CATALOG).as_posix()
        try:
            linter = Linter(str(f), recursive=False)
        except Exception as e:  # stac-check can raise on malformed fields
            failures.append(f"{rel}: could not lint ({type(e).__name__}: {e})")
            continue
        if not linter.valid_stac:
            failures.append(f"{rel}: {linter.error_msg}")
            continue
        for note in (linter.best_practices_msg or [])[1:]:
            if note.strip():
                warnings.append(f"{rel}: {note.strip()}")

    for w in warnings:
        print(f"WARN {w}")
    if failures:
        if warnings:
            print()
        print("\n".join(f"FAIL {x}" for x in failures))
        print(f"\n{len(failures)}/{len(files)} STAC objects invalid")
        return 1
    extra = f" ({len(warnings)} best-practice warning(s))" if warnings else ""
    print(f"OK: {len(files)} STAC objects pass schema validation{extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
