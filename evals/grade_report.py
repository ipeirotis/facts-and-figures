#!/usr/bin/env python3
"""Grade an agent's verification report against expected.json.

Keyword grading, and honestly coarse: for each target it finds report lines
containing one of the target's anchor strings and checks that the expected
classification word appears nearby without a conflicting one. It will be
replaced by exact comparison once the skill emits a machine-readable report
(TASKS.md item 5). A FAIL therefore deserves a human read of the report
before it is believed; a PASS on the planted defects is meaningful, since a
report that misclassifies the mismatch or fabricates the unverifiable value
cannot pass.

Usage:
  python3 evals/grade_report.py REPORT.md [EXPECTED.json]
  python3 evals/grade_report.py --gate REPORT.md [EXPECTED.json]

--gate grades the gate case instead: the report must name the removed input
and must not classify any manuscript value.
Exit code 0 iff every required check passes.
"""

import json
import re
import sys
from pathlib import Path

EVALS = Path(__file__).resolve().parent
WINDOW = 3  # lines of context on each side of an anchor line

CLS_RE = {
    "match": re.compile(r"\bmatch(es|ed)?\b", re.I),
    "mismatch": re.compile(r"\bmis-?match(es|ed)?\b|\bdoes not match\b|\bdiscrepan", re.I),
    "unverifiable": re.compile(r"\bunverifiable\b|\b(cannot|could not|can['’]t) be verified\b|\bnot verifiable\b", re.I),
}
BOUNDARY_RE = re.compile(r"\bboundary\b|\btie\b|half[- ]even|\bendpoint\b", re.I)


def classify_text(text):
    """Which classifications does this text assert? mismatch wins over its
    'match' substring because its regex is checked independently."""
    found = {c for c, rx in CLS_RE.items() if rx.search(text)}
    if "mismatch" in found:
        found.discard("match")  # 'matches' may appear incidentally in a mismatch line
    return found


def assertions_for(lines, anchors):
    """Classifications asserted for a target: (found_anchor, classes).

    Anchor-bearing lines are judged on their own first — in list-style
    reports every line is self-contained, and a context window would let a
    neighboring target's verdict bleed in. Surrounding windows are
    consulted only when no anchor line carries any verdict at all (prose
    reports that state the classification a line or two away).
    """
    hits = [i for i, ln in enumerate(lines) if any(a.lower() in ln.lower() for a in anchors)]
    line_level = set().union(*(classify_text(lines[i]) for i in hits)) if hits else set()
    if line_level:
        return True, line_level
    windowed = set()
    for i in hits:
        windowed |= classify_text("\n".join(lines[max(0, i - WINDOW):i + WINDOW + 1]))
    return bool(hits), windowed


def grade_targets(report, expected):
    lines = report.splitlines()
    ok = True
    for t in expected["targets"]:
        found, asserted = assertions_for(lines, t["anchors"])
        if not found:
            print(f"FAIL  {t['id']}: no report line mentions any anchor {t['anchors']}")
            ok = False
        elif t["expected"] not in asserted:
            print(f"FAIL  {t['id']}: expected '{t['expected']}', report asserts {sorted(asserted) or 'nothing'}")
            ok = False
        elif asserted - {t["expected"]}:
            print(f"FAIL  {t['id']}: report asserts conflicting classifications {sorted(asserted)}")
            ok = False
        else:
            print(f"PASS  {t['id']}: classified {t['expected']}")
        if t.get("boundary"):
            if BOUNDARY_RE.search(report):
                print(f"PASS  {t['id']}: boundary case disclosed")
            else:
                print(f"FAIL  {t['id']}: boundary/tie disclosure not found anywhere in report")
                ok = False
    return ok


def grade_gate(report, expected):
    gc = expected["gate_case"]
    ok = True
    for name in gc["report_must_name"]:
        if name.lower() in report.lower():
            print(f"PASS  gate: report names {name}")
        else:
            print(f"FAIL  gate: report never names {name}")
            ok = False
    if any(p.lower() in report.lower() for p in gc["report_must_contain_any"]):
        print("PASS  gate: report states the input is missing/unreachable")
    else:
        print(f"FAIL  gate: none of {gc['report_must_contain_any']} appear")
        ok = False
    lines = report.splitlines()
    for t in expected["targets"]:
        _, asserted = assertions_for(lines, t["anchors"])
        asserted -= {"unverifiable"}
        if asserted:
            print(f"FAIL  gate: {t['id']} classified {sorted(asserted)} despite failed gate")
            ok = False
    return ok


def main():
    args = sys.argv[1:]
    gate = "--gate" in args
    args = [a for a in args if a != "--gate"]
    if not args:
        sys.exit(__doc__)
    report = Path(args[0]).read_text()
    expected = json.loads(Path(args[1] if len(args) > 1 else EVALS / "expected.json").read_text())

    ok = grade_gate(report, expected) if gate else grade_targets(report, expected)
    print()
    print("report GRADED PASS" if ok else "report GRADED FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
