#!/usr/bin/env python3
"""Grade a machine-readable verification report against expected.json.

Exact where prose grading cannot be: top-level provenance must be present
and non-empty, every record covering a target must itself be coherent
(expected classification, correct computed value, producing command, and
the tolerance or predicate fixed before comparison), and every record must
cover an in-scope manuscript value — an invented record is a planted
assertion, not noise. Pairing records with targets uses the target's
anchors against the record's `reported` field first, free text as a
fallback.

Usage:
  python3 evals/grade_json_report.py REPORT.json [EXPECTED.json]
  python3 evals/grade_json_report.py --gate REPORT.json [EXPECTED.json]

--gate grades a companion written by a run that stopped at the gate: every
record must be unverifiable with a reason, no computed values, and the
missing input must be named. Exit code 0 iff every check passes.
"""

import json
import sys
from pathlib import Path

EVALS = Path(__file__).resolve().parent
SCHEMA = "facts-and-figures.verification/1"
EPS = 1e-6

RECORD_REQUIRED = {"location", "reported", "classification"}
TOP_REQUIRED = ("schema", "skill_version", "manuscript_files", "pipeline_command",
                "environment", "data_versions", "values")


def pair_records(values, anchors):
    """Records covering a target. The `reported` field is authoritative —
    pairing on location/note text lets one record's cross-value arithmetic
    (a mismatch note quoting the group means) contaminate another target —
    so free text is a fallback only when no `reported` field matches."""
    lowered = [a.lower() for a in anchors]
    by_reported = [r for r in values
                   if any(a in str(r.get("reported", "")).lower() for a in lowered)]
    if by_reported:
        return by_reported
    return [r for r in values
            if any(a in f"{r.get('location', '')} {r.get('note', '')}".lower() for a in lowered)]


def computed_matches(computed, target):
    """The record's computed value must equal the documented true value; a
    percent target may be recorded in either unit (0.125 or 12.5), and a
    record whose reported claim bundles several quantities (a count and its
    seed, the two group sizes) may carry them as a list — any element equal
    to the documented value counts."""
    if isinstance(computed, (list, tuple)):
        return any(computed_matches(c, target) for c in computed)
    if not isinstance(computed, (int, float)):
        return False
    candidates = [target["true_value"]]
    if target.get("result_scale"):
        candidates.append(target["true_value"] / target["result_scale"])
    return any(abs(computed - c) < EPS for c in candidates)


class Grader:
    def __init__(self):
        self.ok = True

    def check(self, cond, label, detail=""):
        print(f"{'PASS' if cond else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
        self.ok = self.ok and bool(cond)


def grade_top_level(g, report):
    for key in TOP_REQUIRED:
        v = report.get(key)
        good = v == SCHEMA if key == "schema" else bool(v)
        g.check(good, f"top-level {key} present and non-empty",
                "" if good else repr(v)[:60])
    values = report.get("values") or []
    bad = [i for i, r in enumerate(values) if RECORD_REQUIRED - r.keys()]
    g.check(not bad, "required record fields present",
            f"records missing fields: {bad}" if bad else f"{len(values)} records")
    return values


def grade_targets(report, expected):
    g = Grader()
    values = grade_top_level(g, report)

    paired = set()
    for t in expected["targets"]:
        recs = pair_records(values, t["anchors"])
        paired.update(id(r) for r in recs)
        if not recs:
            g.check(False, f"{t['id']}: a record covers it", f"no record mentions {t['anchors']}")
            continue
        cls = {r.get("classification") for r in recs}
        g.check(cls == {t["expected"]}, f"{t['id']}: classified {t['expected']}",
                f"report says {sorted(map(str, cls))}")
        boundary = any(r.get("boundary") is True for r in recs)
        g.check(boundary == t["boundary"], f"{t['id']}: boundary flag is {t['boundary']}")

        if t["expected"] == "unverifiable":
            g.check(all(r.get("computed") is None for r in recs),
                    f"{t['id']}: no computed value asserted")
            g.check(all(r.get("reason") for r in recs), f"{t['id']}: reason on every record")
        else:
            # every covering record must be coherent on its own — a correct
            # sibling must not excuse an unverified or unexplained record
            g.check(all(computed_matches(r.get("computed"), t) for r in recs),
                    f"{t['id']}: correct computed value on every record",
                    f"documented {t['true_value']!r}, report has {[r.get('computed') for r in recs]}")
            g.check(all(r.get("producing_command") for r in recs),
                    f"{t['id']}: producing command on every record")
            g.check(all(r.get("tolerance") for r in recs),
                    f"{t['id']}: tolerance/predicate stated on every record")

    stray = [r.get("reported") for r in values if id(r) not in paired]
    g.check(not stray, "every record covers an in-scope manuscript value",
            f"stray records: {stray}" if stray else "")
    return g.ok


def grade_gate(report, expected):
    g = Grader()
    values = grade_top_level(g, report)
    g.check(all(r.get("classification") == "unverifiable" for r in values),
            "every record is unverifiable after the failed gate",
            str(sorted({str(r.get('classification')) for r in values})))
    g.check(all(r.get("computed") is None for r in values), "no computed values asserted")
    g.check(all(r.get("reason") for r in values), "reason on every record")
    text = json.dumps(report).lower()
    for name in expected["gate_case"]["report_must_name"]:
        g.check(name.lower() in text, f"the missing input {name} is named")
    return g.ok


def main():
    args = sys.argv[1:]
    gate = "--gate" in args
    args = [a for a in args if a != "--gate"]
    if not args:
        sys.exit(__doc__)
    report = json.loads(Path(args[0]).read_text())
    expected = json.loads(Path(args[1] if len(args) > 1 else EVALS / "expected.json").read_text())

    ok = grade_gate(report, expected) if gate else grade_targets(report, expected)
    print()
    print("json report GRADED PASS" if ok else "json report GRADED FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
