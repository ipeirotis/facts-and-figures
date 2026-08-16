#!/usr/bin/env python3
"""Deterministic self-check for the toy-paper fixture. No LLM involved.

Guards the fixture against drift: runs the pipeline in a scratch copy and
asserts (a) every documented true value is what the pipeline actually
produces, (b) each expected classification follows from the protocol's own
tolerance rule applied to those values, and (c) the gate case fails loudly
when the dataset is removed.

The tolerance rule checked here is the one references/analysis-integrity.md
states: for a manuscript value m reported to k decimals, with u = 10^-k,
the accepted set is the half-open interval m - u/2 <= v < m + u/2; a value
landing exactly on the lower endpoint is a match that must additionally be
disclosed as a boundary case; the upper endpoint is excluded.

Usage: python3 evals/check_fixture.py
Exit code 0 iff every check passes.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EVALS = Path(__file__).resolve().parent
EPS = 1e-9

failures = []


def check(ok, label, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(label)


def classify(v, m, decimals):
    """Apply the protocol's half-open tolerance rule. Returns (cls, boundary)."""
    u = 10 ** -decimals
    lo, hi = m - u / 2, m + u / 2
    if abs(v - lo) < EPS:
        return "match", True
    if lo < v < hi - EPS:
        return "match", False
    return "mismatch", False


def run_pipeline(fixture_dir):
    return subprocess.run(
        [sys.executable, "analysis/run_analysis.py"],
        cwd=fixture_dir, capture_output=True, text=True,
    )


def main():
    expected = json.loads((EVALS / "expected.json").read_text())
    src = EVALS / expected["fixture"]

    with tempfile.TemporaryDirectory() as tmp:
        fixture = Path(tmp) / "paper"
        shutil.copytree(src, fixture)
        shutil.rmtree(fixture / "results", ignore_errors=True)

        proc = run_pipeline(fixture)
        check(proc.returncode == 0, "pipeline runs", proc.stderr.strip()[:120])
        if proc.returncode != 0:
            sys.exit(1)
        results = json.loads((fixture / expected["results_file"]).read_text())

        for t in expected["targets"]:
            tid = t["id"]
            v = results.get(t["result_key"])

            if t["kind"] == "missing-source":
                gone = not (fixture / "data" / "wave2_followup.csv").exists()
                check(gone and v is None, f"{tid}: source absent, pipeline reports no value")
                check(t["expected"] == "unverifiable", f"{tid}: expected classification is unverifiable")
                continue

            if t.get("result_scale"):
                v = v * t["result_scale"]
            check(abs(v - t["true_value"]) < EPS, f"{tid}: pipeline value equals documented true value",
                  f"pipeline {v!r} vs documented {t['true_value']!r}")

            if t["kind"] == "predicate":
                assert t["predicate"] == "less_than"
                cls = "match" if v < t["predicate_value"] else "mismatch"
                check(cls == t["expected"], f"{tid}: predicate yields expected classification",
                      f"{v!r} < {t['predicate_value']!r} -> {cls}")
            else:
                cls, boundary = classify(v, t["manuscript_value"], t["decimals"])
                check(cls == t["expected"], f"{tid}: tolerance rule yields expected classification",
                      f"v={v!r} m={t['manuscript_value']!r} k={t['decimals']} -> {cls}")
                check(boundary == t["boundary"], f"{tid}: boundary status as documented",
                      f"boundary={boundary}")

        # gate case: remove the dataset, the pipeline must fail loudly
        gated = Path(tmp) / "gated"
        shutil.copytree(src, gated)
        shutil.rmtree(gated / "results", ignore_errors=True)
        for rel in expected["gate_case"]["remove"]:
            (gated / rel).unlink()
        proc = run_pipeline(gated)
        check(proc.returncode != 0, "gate case: pipeline exits nonzero without its data")
        named = all(n in (proc.stderr + proc.stdout) for n in expected["gate_case"]["report_must_name"])
        check(named, "gate case: failure names the missing input", proc.stderr.strip()[:120])

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED")
        sys.exit(1)
    print("all fixture checks passed")


if __name__ == "__main__":
    main()
