#!/usr/bin/env python3
"""Self-test for the graders. No LLM: runs each grader against the mock
reports in tests/ and asserts the expected verdict, so a grader regression
is caught deterministically instead of surfacing as a confusing agent-eval
failure.

Usage: python3 evals/test_graders.py
Exit code 0 iff every grader verdict is as expected.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

EVALS = Path(__file__).resolve().parent
TESTS = EVALS / "tests"

# (grader script, extra args, mock file, expected exit code)
CASES = [
    ("grade_report.py", [], "mock_good.md", 0),
    ("grade_report.py", [], "mock_bad.md", 1),
    ("grade_report.py", ["--gate"], "mock_gate.md", 0),
    ("grade_json_report.py", [], "mock_good.json", 0),
    ("grade_json_report.py", [], "mock_bad.json", 1),
    ("grade_json_report.py", ["--gate"], "mock_gate.json", 0),
    ("grade_report.py", ["--gate"], "mock_gate_bad.md", 1),
    ("grade_json_report.py", ["--gate"], "mock_gate_bad.json", 1),
]


def numeric_reported_case():
    """A record whose `reported` field is a JSON number instead of the
    manuscript's verbatim string must fail grading, even when its digits
    still pair with a target anchor (10,000 -> 10000)."""
    report = json.loads((TESTS / "mock_good.json").read_text())
    for r in report["values"]:
        if r.get("reported") == "10,000":
            r["reported"] = 10000
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(report, f)
        path = f.name
    try:
        proc = subprocess.run(
            [sys.executable, str(EVALS / "grade_json_report.py"), path],
            capture_output=True, text=True,
        )
    finally:
        Path(path).unlink()
    ok = proc.returncode == 1
    print(f"{'PASS' if ok else 'FAIL'}  grade_json_report.py mock_good with numeric reported: "
          f"exit {proc.returncode}, want 1")
    if not ok:
        print(proc.stdout)
    return ok


def main():
    failures = 0
    for script, extra, mock, want in CASES:
        proc = subprocess.run(
            [sys.executable, str(EVALS / script), *extra, str(TESTS / mock)],
            capture_output=True, text=True,
        )
        ok = proc.returncode == want
        print(f"{'PASS' if ok else 'FAIL'}  {script} {' '.join(extra)} {mock}: exit {proc.returncode}, want {want}")
        if not ok:
            print(proc.stdout)
            failures += 1
    if not numeric_reported_case():
        failures += 1
    print()
    if failures:
        print(f"{failures} grader self-test(s) FAILED")
        sys.exit(1)
    print("all grader self-tests passed")


if __name__ == "__main__":
    main()
