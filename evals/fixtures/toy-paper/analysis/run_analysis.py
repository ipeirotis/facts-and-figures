#!/usr/bin/env python3
"""Analysis pipeline for "Experience and Response Quality in Microtask Work".

Reads data/workers.csv, writes results/results.json, and prints every
computed quantity. Deterministic: the permutation test runs with a fixed
seed, and no step depends on wall-clock time or environment state.

The wave-2 follow-up file (data/wave2_followup.csv) is not distributed with
this repository (see manuscript.md, "Data and code"). When it is absent the
pipeline says so and skips retention; every other quantity still runs.
"""

import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "workers.csv"
WAVE2 = ROOT / "data" / "wave2_followup.csv"
OUT = ROOT / "results"

PERM_SEED = 20260816
N_PERM = 10_000


def main():
    if not DATA.exists():
        sys.exit(f"required input not found: {DATA}")

    rows = list(csv.DictReader(DATA.open()))
    scores = [float(r["quality_score"]) for r in rows]
    exp = [float(r["quality_score"]) for r in rows if r["experienced"] == "1"]
    inexp = [float(r["quality_score"]) for r in rows if r["experienced"] == "0"]

    results = {
        "n_workers": len(rows),
        "overall_mean_quality": sum(scores) / len(scores),
        "mean_quality_experienced": sum(exp) / len(exp),
        "mean_quality_inexperienced": sum(inexp) / len(inexp),
    }
    results["diff_experienced_minus_inexperienced"] = (
        results["mean_quality_experienced"] - results["mean_quality_inexperienced"]
    )
    results["flagged_share"] = sum(int(r["flagged"]) for r in rows) / len(rows)

    # Two-sided permutation test on the difference in group means. The pool
    # is shuffled cumulatively; with the fixed seed the sequence of
    # permutations, and therefore the p-value, is identical on every run.
    obs = results["diff_experienced_minus_inexperienced"]
    pool = list(scores)
    k = len(exp)
    rng = random.Random(PERM_SEED)
    n_ge = 0
    for _ in range(N_PERM):
        rng.shuffle(pool)
        d = sum(pool[:k]) / k - sum(pool[k:]) / (len(pool) - k)
        if abs(d) >= abs(obs):
            n_ge += 1
    results["perm_p_value"] = (1 + n_ge) / (1 + N_PERM)
    results["perm_seed"] = PERM_SEED
    results["n_permutations"] = N_PERM

    if WAVE2.exists():
        w2 = list(csv.DictReader(WAVE2.open()))
        results["retention_wave2"] = sum(1 for r in w2 if r["returned"] == "1") / len(rows)
    else:
        results["retention_wave2"] = None
        print(f"note: {WAVE2} not found; wave-2 retention not computed", file=sys.stderr)

    OUT.mkdir(exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    for key, val in results.items():
        print(f"{key}: {val}")


if __name__ == "__main__":
    main()
