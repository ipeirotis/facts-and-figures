#!/usr/bin/env python3
"""Grade a machine-readable verification report against expected.json.

Exact where the keyword grader is fuzzy: classifications, boundary flags,
and computed values are compared precisely. Pairing a report record with an
expected target still uses the target's anchor strings against the record's
`reported`/`location`/`note` fields, since the agent chooses its own
wording there.

Usage: python3 evals/grade_json_report.py VERIFICATION_REPORT.json [EXPECTED.json]
Exit code 0 iff every check passes.
"""

import json
import sys
from pathlib import Path

EVALS = Path(__file__).resolve().parent
SCHEMA = "facts-and-figures.verification/1"
EPS = 1e-6

RECORD_REQUIRED = {"location", "reported", "classification", "boundary"}
TOP_REQUIRED = {"schema", "skill_version", "manuscript_files", "pipeline_command",
                "environment", "data_versions", "values"}


def record_text(r):
    return " ".join(str(r.get(k, "")) for k in ("reported", "location", "note")).lower()


def computed_matches(computed, target):
    """The record's computed value must equal the documented true value; a
    percent target may be recorded in either unit (0.125 or 12.5)."""
    if not isinstance(computed, (int, float)):
        return False
    candidates = [target["true_value"]]
    if target.get("result_scale"):
        candidates.append(target["true_value"] / target["result_scale"])
    return any(abs(computed - c) < EPS for c in candidates)


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    report = json.loads(Path(args[0]).read_text())
    expected = json.loads(Path(args[1] if len(args) > 1 else EVALS / "expected.json").read_text())

    ok = True

    def check(cond, label, detail=""):
        nonlocal ok
        print(f"{'PASS' if cond else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
        ok = ok and bool(cond)

    check(report.get("schema") == SCHEMA, "schema identifier", str(report.get("schema")))
    missing_top = TOP_REQUIRED - report.keys()
    check(not missing_top, "required top-level fields present", f"missing: {sorted(missing_top)}" if missing_top else "")

    values = report.get("values", [])
    bad = [i for i, r in enumerate(values) if RECORD_REQUIRED - r.keys()]
    check(not bad, "required record fields present", f"records missing fields: {bad}" if bad else f"{len(values)} records")

    for t in expected["targets"]:
        recs = [r for r in values if any(a.lower() in record_text(r) for a in t["anchors"])]
        if not recs:
            check(False, f"{t['id']}: a record covers it", f"no record mentions {t['anchors']}")
            continue
        cls = {r.get("classification") for r in recs}
        check(cls == {t["expected"]}, f"{t['id']}: classified {t['expected']}", f"report says {sorted(cls)}")
        boundary = any(r.get("boundary") is True for r in recs)
        check(boundary == t["boundary"], f"{t['id']}: boundary flag is {t['boundary']}")

        if t["expected"] == "unverifiable":
            check(all(r.get("computed") is None for r in recs), f"{t['id']}: no computed value asserted")
            check(any(r.get("reason") for r in recs), f"{t['id']}: reason given")
        else:
            check(any(computed_matches(r.get("computed"), t) for r in recs),
                  f"{t['id']}: computed equals documented true value",
                  f"documented {t['true_value']!r}, report has {[r.get('computed') for r in recs]}")
            check(any(r.get("producing_command") for r in recs), f"{t['id']}: producing command logged")

    print()
    print("json report GRADED PASS" if ok else "json report GRADED FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
