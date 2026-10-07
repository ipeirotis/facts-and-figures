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
VERSION = (EVALS.parent / "VERSION").read_text().strip()

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


def _numeric_reported(d):
    """The Codex round-15 PoC: a JSON 10000 whose digits still pair with
    the 10,000 anchor."""
    for r in d["values"]:
        if r.get("reported") == "10,000":
            r["reported"] = 10000


def _collapsed_gate(d):
    """One record whose reported string concatenates every anchor must not
    satisfy ten per-value coverage checks: the schema requires one record
    per manuscript value."""
    merged = dict(d["values"][0])
    merged["reported"] = "; ".join(str(r.get("reported", "")) for r in d["values"])
    d["values"] = [merged]


def _renamed_data_key(d):
    """A legitimate alternative spelling of the hashed input's path must
    still pass: the schema requires the actual path, not one dictionary
    key."""
    d["data_versions"] = {"./data/workers.csv": v
                          for v in [d["data_versions"]["data/workers.csv"]]}


# single-field edits of a passing mock and the grader verdict each must
# produce: (label, extra args, base mock, mutation, expected exit code)
MUTATIONS = [
    ("numeric reported", [], "mock_good.json", _numeric_reported, 1),
    ("wrong skill_version", [], "mock_good.json",
     lambda d: d.update(skill_version="not-the-installed-skill"), 1),
    ("fabricated digest for removed input", ["--gate"], "mock_gate.json",
     lambda d: d["data_versions"].update({"data/workers.csv": "sha256:" + "0" * 64}), 1),
    ("presence claimed for removed input", ["--gate"], "mock_gate.json",
     lambda d: d["data_versions"].update({"data/workers.csv": "present and verified"}), 1),
    ("./-prefixed data_versions key", [], "mock_good.json", _renamed_data_key, 0),
    ("all anchors collapsed into one record", ["--gate"], "mock_gate.json",
     _collapsed_gate, 1),
]


def md_boundary_case():
    """A boundary word about a different value in Author decisions must not
    satisfy the tie disclosure for the flagged share."""
    text = (TESTS / "mock_good.md").read_text()
    original = ("The flagged share sits exactly on the rounding boundary; "
                "confirm the intended convention.")
    mutated = text.replace(
        original, "There are no boundary concerns for the overall mean 71.48.")
    assert mutated != text, "mock_good.md boundary line changed; update this test"
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
    f.write(mutated)
    f.close()
    proc = run_grader("grade_report.py", [], Path(f.name))
    Path(f.name).unlink()
    ok = proc.returncode == 1
    print(f"{'PASS' if ok else 'FAIL'}  grade_report.py mock_good.md with misdirected boundary: "
          f"exit {proc.returncode}, want 1")
    if not ok:
        print(proc.stdout)
    return ok


def prepared(mock, mutate=None):
    """A temp copy of a JSON mock with skill_version pinned to the current
    VERSION — the static mocks test report semantics, not release
    arithmetic, so a version bump must not break them — plus an optional
    corruption for the adversarial cases."""
    data = json.loads((TESTS / mock).read_text())
    data["skill_version"] = VERSION
    if mutate:
        mutate(data)
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(data, f)
    f.close()
    return Path(f.name)


def run_grader(script, extra, path):
    return subprocess.run(
        [sys.executable, str(EVALS / script), *extra, str(path)],
        capture_output=True, text=True,
    )


def main():
    failures = 0
    for script, extra, mock, want in CASES:
        if mock.endswith(".json"):
            path = prepared(mock)
            proc = run_grader(script, extra, path)
            path.unlink()
        else:
            proc = run_grader(script, extra, TESTS / mock)
        ok = proc.returncode == want
        print(f"{'PASS' if ok else 'FAIL'}  {script} {' '.join(extra)} {mock}: exit {proc.returncode}, want {want}")
        if not ok:
            print(proc.stdout)
            failures += 1
    for label, extra, mock, mutate, want in MUTATIONS:
        path = prepared(mock, mutate)
        proc = run_grader("grade_json_report.py", extra, path)
        path.unlink()
        ok = proc.returncode == want
        print(f"{'PASS' if ok else 'FAIL'}  grade_json_report.py {' '.join(extra)} {mock} with {label}: "
              f"exit {proc.returncode}, want {want}")
        if not ok:
            print(proc.stdout)
            failures += 1
    if not md_boundary_case():
        failures += 1
    print()
    if failures:
        print(f"{failures} grader self-test(s) FAILED")
        sys.exit(1)
    print("all grader self-tests passed")


if __name__ == "__main__":
    main()
