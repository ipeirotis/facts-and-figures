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


def _merged_plus_duplicates(d):
    """A merged record covering every anchor, padded with duplicates of a
    single target to inflate the record count, must still fail: each
    target needs a distinct record of its own."""
    merged = dict(d["values"][0])
    merged["reported"] = "; ".join(str(r.get("reported", "")) for r in d["values"])
    first = dict(d["values"][0])
    d["values"] = [merged] + [dict(first) for _ in range(len(d["values"]) - 1)]


def _scalar_bundle(d):
    """A scalar 20 for the 20-and-20 group split verifies only one group."""
    for r in d["values"]:
        if r.get("computed") == [20, 20]:
            r["computed"] = 20


def _ten_concatenated(d):
    """Ten copies of a record whose reported string concatenates every
    anchor form a perfect matching, but no copy is a record of any single
    manuscript value."""
    merged = dict(d["values"][0])
    merged["reported"] = "; ".join(str(r.get("reported", "")) for r in d["values"])
    d["values"] = [dict(merged) for _ in range(len(d["values"]))]


def _fabricated_exempt(d):
    """A record exempt from answer-key equality (an out-of-scope anchor)
    still owes the schema its classification enum."""
    d["values"].append({"location": "manuscript.md, Data", "reported": "0-100 scale",
                        "classification": "fabricated", "computed": 999})


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
    ("merged record padded with duplicates", ["--gate"], "mock_gate.json",
     _merged_plus_duplicates, 1),
    ("scalar computed for the bundled group split", [], "mock_good.json",
     _scalar_bundle, 1),
    ("ten concatenated records forming a fake matching", ["--gate"], "mock_gate.json",
     _ten_concatenated, 1),
    ("fabricated classification on an exempt record", [], "mock_good.json",
     _fabricated_exempt, 1),
    ("environment reduced to a placeholder", [], "mock_good.json",
     lambda d: d.update(environment="unknown"), 1),
    ("locations reduced to the bare word manuscript", [], "mock_good.json",
     lambda d: [r.update(location="manuscript") for r in d["values"]], 1),
    ("exempt match record without provenance fields", [], "mock_good.json",
     lambda d: d["values"].append({"location": "manuscript.md, Data",
                                   "reported": "0-100", "classification": "match",
                                   "computed": 999}), 1),
    ("absence entry keyed to a different file", ["--gate"], "mock_gate.json",
     lambda d: d.update(data_versions={"data/notworkers.csv":
                                       d["data_versions"]["data/workers.csv"]}), 1),
]


def _replacing(original, replacement):
    return lambda t: t.replace(original, replacement)


def _absence_words_removed(text):
    """A gate report that names the input but never states it is absent
    must fail — 'gate' was once an accepted term and is auto-satisfied by
    the mandatory Scope and gate heading."""
    for a, b in (("not found", "located"), ("Not found", "Located"),
                 ("missing", "pending"), ("Missing", "Pending"),
                 ("unreachable", "reachable"), ("absent", "present")):
        text = text.replace(a, b)
    return text


# text-level corruptions of a passing prose mock that grade_report.py must
# reject: (label, mock file, extra args, text transform)
MD_MUTATIONS = [
    ("misdirected boundary", "mock_good.md", [], _replacing(
     "The flagged share sits exactly on the rounding boundary; confirm the intended convention.",
     "There are no boundary concerns for the overall mean 71.48.")),
    ("mismatch dropped from Author decisions", "mock_good.md", [], _replacing(
     "The reported difference 6.23 disagrees with the pipeline's 6.32; decide whether to correct both occurrences.",
     "Decide whether any corrections are needed.")),
    ("unverifiable dropped from Author decisions", "mock_good.md", [], _replacing(
     "The 64% retention could not be verified from the distributed data; confirm it against the restricted source or state that it is not reproducible.",
     "One value remains for you to confirm against the restricted source.")),
    ("absence terms removed from the gate report", "mock_gate.md", ["--gate"],
     _absence_words_removed),
]


def md_mutation_cases():
    failures = 0
    for label, mock, extra, transform in MD_MUTATIONS:
        text = (TESTS / mock).read_text()
        mutated = transform(text)
        assert mutated != text, f"{mock} text changed; update MD_MUTATIONS ({label})"
        f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
        f.write(mutated)
        f.close()
        proc = run_grader("grade_report.py", extra, Path(f.name))
        Path(f.name).unlink()
        ok = proc.returncode == 1
        print(f"{'PASS' if ok else 'FAIL'}  grade_report.py {' '.join(extra)} {mock} with {label}: "
              f"exit {proc.returncode}, want 1")
        if not ok:
            print(proc.stdout)
            failures += 1
    return failures


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
    failures += md_mutation_cases()
    print()
    if failures:
        print(f"{failures} grader self-test(s) FAILED")
        sys.exit(1)
    print("all grader self-tests passed")


if __name__ == "__main__":
    main()
