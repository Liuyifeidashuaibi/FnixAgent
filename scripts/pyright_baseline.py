#!/usr/bin/env python3
"""Pyright baseline checker.

Runs pyright and compares the error count against a stored baseline.
- Exit 0 if error count <= baseline (no regression)
- Exit 1 if error count > baseline (regression detected)

Usage:
    python scripts/pyright_baseline.py          # Check against baseline
    python scripts/pyright_baseline.py --update  # Update baseline to current count
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASELINE_FILE = PROJECT_ROOT / ".pyright-baseline"


def run_pyright() -> dict:
    """Run pyright and return parsed JSON output."""
    result = subprocess.run(
        ["pyright", "src/fnixagent/", "--outputjson"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=300,
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        # If JSON parsing fails, try to parse from stderr or combined output
        print(f"ERROR: Failed to parse pyright output as JSON", file=sys.stderr)
        print(f"stdout (first 500 chars): {result.stdout[:500]}", file=sys.stderr)
        print(f"stderr (first 500 chars): {result.stderr[:500]}", file=sys.stderr)
        sys.exit(2)


def get_error_count(data: dict) -> int:
    """Extract error count from pyright JSON output."""
    summary = data.get("summary", {})
    # pyright uses errorCount (not numErrors)
    return summary.get("errorCount", summary.get("numErrors", 0))


def read_baseline() -> int:
    """Read the stored baseline error count."""
    if not BASELINE_FILE.exists():
        return 0
    try:
        return int(BASELINE_FILE.read_text().strip())
    except (ValueError, OSError):
        return 0


def write_baseline(count: int) -> None:
    """Write the baseline error count to file."""
    BASELINE_FILE.write_text(f"{count}\n")
    print(f"Baseline updated to {count} errors")


def main() -> int:
    parser = argparse.ArgumentParser(description="Pyright baseline checker")
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update baseline to current error count",
    )
    args = parser.parse_args()

    print("Running pyright...")
    data = run_pyright()
    current_errors = get_error_count(data)

    if args.update:
        write_baseline(current_errors)
        return 0

    baseline = read_baseline()
    print(f"Current errors: {current_errors}")
    print(f"Baseline:       {baseline}")
    print(f"Delta:          {current_errors - baseline:+d}")

    if current_errors > baseline:
        print(f"\nREGRESSION DETECTED: {current_errors - baseline} new error(s)!")
        print("Fix the new errors or run: python scripts/pyright_baseline.py --update")
        return 1
    else:
        improvement = baseline - current_errors
        if improvement > 0:
            print(f"\nIMPROVEMENT: {improvement} fewer errors than baseline!")
            print("Consider updating baseline: python scripts/pyright_baseline.py --update")
        else:
            print("\nNo regression. Error count matches baseline.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
