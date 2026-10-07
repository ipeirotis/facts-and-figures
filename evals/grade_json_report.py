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
    """Records covering a target, paired on the `reported` field only. The
    schema requires `reported` to carry the manuscript value verbatim, so a
    record only locatable through its note or location is non-compliant —
    and an earlier free-text fallback let a record pair on a note mention
    while asserting a different value in `reported`."""
    lowered = [a.lower() for a in anchors]
    return [r for r in values
            if any(a in str(r.get("reported", "")).lower() for a in lowered)]


def computed_matches(computed, target):
    """The record's computed value must equal the documented true value; a
    percent target may be recorded in either unit (0.125 or 12.5). A record
    whose reported claim bundles several quantities (the two group sizes, a
    count and its seed) may carry them as a list — but then every element
    must be a documented value (the true value or one the answer key's
    bundle_allowed names), and at least one must be the true value, so a
    bundle cannot smuggle an unverified number past grading."""
    true_candidates = [target["true_value"]]
    if target.get("result_scale"):
        true_candidates.append(target["true_value"] / target["result_scale"])

    def is_true(c):
        return isinstance(c, (int, float)) and any(abs(c - t) < EPS for t in true_candidates)

    if isinstance(computed, (list, tuple)):
        expect = target.get("bundle_expect")
        if expect is not None:
            # a target whose claim bundles a fixed set of quantities (the
            # two group counts) must carry exactly that multiset — [20]
            # verifies only one group of the 20 / 20 claim
            if len(computed) != len(expect):
                return False
            remaining = list(expect)
            for c in computed:
                hit = next((i for i, e in enumerate(remaining)
                            if isinstance(c, (int, float)) and abs(c - e) < EPS), None)
                if hit is None:
                    return False
                remaining.pop(hit)
            return True
        allowed = true_candidates + list(target.get("bundle_allowed", []))
        def is_allowed(c):
            return isinstance(c, (int, float)) and any(abs(c - a) < EPS for a in allowed)
        return bool(computed) and any(is_true(c) for c in computed) and all(is_allowed(c) for c in computed)
    return is_true(computed)


def out_of_scope_ids(values, expected):
    """Records covering a manuscript number the answer key deliberately
    leaves out (the 0-100 scale, the three-month interval) are not strays:
    an agent more thorough than the key must not fail for it."""
    extra = [a.lower() for a in expected.get("out_of_scope_anchors", [])]
    return {id(r) for r in values
            if any(a in str(r.get("reported", "")).lower() for a in extra)}


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
    bad = [i for i, r in enumerate(values)
           if any(not str(r.get(k) or "").strip() for k in RECORD_REQUIRED)]
    g.check(not bad, "required record fields present and non-empty",
            f"records with missing or empty fields: {bad}" if bad else f"{len(values)} records")
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
        # a boundary target's tie holds for every record asserting the
        # comparison, so one record claiming otherwise is an unverified
        # assertion, not a tolerable sibling
        if t["boundary"]:
            g.check(all(r.get("boundary") is True for r in recs),
                    f"{t['id']}: boundary flag is True on every record")
        else:
            g.check(not any(r.get("boundary") is True for r in recs),
                    f"{t['id']}: boundary flag is False")

        if t["expected"] == "unverifiable":
            g.check(all("computed" in r and r["computed"] is None for r in recs),
                    f"{t['id']}: computed explicitly null")
            g.check(all(r.get("reason") for r in recs), f"{t['id']}: reason on every record")
            must = t.get("reason_must_contain", "")
            g.check(all(must.lower() in str(r.get("reason", "")).lower() for r in recs),
                    f"{t['id']}: reason names the missing source",
                    f"reasons: {[r.get('reason') for r in recs]}" if must else "")
        else:
            # every covering record must be coherent on its own — a correct
            # sibling must not excuse an unverified or unexplained record
            g.check(all(computed_matches(r.get("computed"), t) for r in recs),
                    f"{t['id']}: correct computed value on every record",
                    f"documented {t['true_value']!r}, report has {[r.get('computed') for r in recs]}")
            # the command cannot be verified verbatim (supplementary logged
            # commands are legitimate), but it must at least invoke the
            # fixture's runtime: a fabricated "echo 0" is not provenance
            token = expected.get("producing_command_must_contain", "")
            g.check(all(token in str(r.get("producing_command", "")).lower() for r in recs),
                    f"{t['id']}: plausible producing command on every record",
                    f"commands: {[r.get('producing_command') for r in recs]}" if token else "")
            g.check(all(r.get("tolerance") for r in recs),
                    f"{t['id']}: tolerance/predicate stated on every record")

    skip = out_of_scope_ids(values, expected)
    stray = [r.get("reported") for r in values if id(r) not in paired and id(r) not in skip]
    g.check(not stray, "every record covers an in-scope manuscript value",
            f"stray records: {stray}" if stray else "")
    return g.ok


def grade_gate(report, expected):
    g = Grader()
    values = grade_top_level(g, report)
    paired = set()
    for t in expected["targets"]:
        recs = pair_records(values, t["anchors"])
        paired.update(id(r) for r in recs)
        g.check(bool(recs), f"gate: {t['id']} covered by a record")
    skip = out_of_scope_ids(values, expected)
    stray = [r.get("reported") for r in values if id(r) not in paired and id(r) not in skip]
    g.check(not stray, "gate: every record covers an in-scope manuscript value",
            f"stray records: {stray}" if stray else "")
    g.check(all(r.get("classification") == "unverifiable" for r in values),
            "every record is unverifiable after the failed gate",
            str(sorted({str(r.get('classification')) for r in values})))
    g.check(all("computed" in r and r["computed"] is None for r in values),
            "computed explicitly null on every record")
    g.check(not any(r.get("boundary") is True for r in values),
            "no boundary tie asserted after the failed gate")
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
