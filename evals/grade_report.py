#!/usr/bin/env python3
"""Grade an agent's prose verification report against expected.json.

Structural grading only. Two live runs showed that classifying verdicts
out of free prose is unreliable against real report formats — one agent
grouped its results under verdict headings whose table rows carry no
verdict word, another discussed targets inside other targets' explanations
("not a mismatch", cross-value arithmetic) — so verdict-by-verdict grading
lives in grade_json_report.py, which reads the machine-readable companion
the skill mandates. Here the prose must carry the four sections of the
return contract, mention every target, and disclose the boundary tie.

Usage:
  python3 evals/grade_report.py REPORT.md [EXPECTED.json]
  python3 evals/grade_report.py --gate REPORT.md [EXPECTED.json]

--gate grades the gate case instead: the report must name the removed
input, state that it is missing, and classify no value as match or
mismatch. Exit code 0 iff every required check passes.
"""

import json
import re
import sys
from pathlib import Path

EVALS = Path(__file__).resolve().parent
WINDOW = 3  # lines of context on each side of an anchor line (gate mode)

CLS_RE = {
    "match": re.compile(r"\bmatch(es|ed)?\b", re.I),
    "mismatch": re.compile(r"\bmis-?match(es|ed)?\b|\bdoes not match\b|\bdiscrepan", re.I),
    "unverifiable": re.compile(r"\bunverifiable\b|\b(cannot|could not|can['’]t) be verified\b|\bnot verifiable\b", re.I),
}
BOUNDARY_RE = re.compile(r"\bboundary\b|\btie\b|half[- ]even|\bendpoint\b", re.I)
SECTIONS = ("scope and gate", "method and provenance", "results", "author decisions")


def grade_sections(report):
    """The skill's return contract names four sections, which must appear as
    actual headings (markdown #, bold, or numbered), not merely be mentioned
    in a sentence — a report saying the sections were omitted must fail."""
    ok = True
    for s in SECTIONS:
        rx = re.compile(r"(?mi)^\s*(?:#{1,6}|\*\*|\d+\.)\s*(?:\d+\.\s*)?(?:\*\*)?\s*"
                        + re.escape(s) + r"\b")
        if rx.search(report):
            print(f"PASS  section present: {s}")
        else:
            print(f"FAIL  section heading missing: {s}")
            ok = False
    return ok


def anchor_lines(lines, anchors):
    return [i for i, ln in enumerate(lines) if any(a.lower() in ln.lower() for a in anchors)]


def classify_text(text):
    """Which classifications does this text assert? mismatch wins over its
    'match' substring because its regex is checked independently."""
    found = {c for c, rx in CLS_RE.items() if rx.search(text)}
    if "mismatch" in found:
        found.discard("match")  # 'matches' may appear incidentally in a mismatch line
    return found


def assertions_for(lines, anchors):
    """Classifications asserted near a target's anchors (gate mode only,
    where any match/mismatch at all is the failure being looked for)."""
    hits = anchor_lines(lines, anchors)
    line_level = set().union(*(classify_text(lines[i]) for i in hits)) if hits else set()
    if line_level:
        return line_level
    windowed = set()
    for i in hits:
        windowed |= classify_text("\n".join(lines[max(0, i - WINDOW):i + WINDOW + 1]))
    return windowed


def grade_targets(report, expected):
    lines = report.splitlines()
    ok = grade_sections(report)
    for t in expected["targets"]:
        if anchor_lines(lines, t["anchors"]):
            print(f"PASS  {t['id']}: covered by the report")
        else:
            print(f"FAIL  {t['id']}: no report line mentions any anchor {t['anchors']}")
            ok = False
        if t.get("boundary"):
            # the protocol requires the tie named in Author decisions, not
            # merely mentioned in Results, so the author chooses the
            # rounding convention — and the disclosure must sit with THIS
            # value: a boundary word about some other target is not the
            # required tie disclosure
            idx = report.lower().rfind("author decisions")
            dlines = (report[idx:] if idx != -1 else "").splitlines()
            anchored = any(
                BOUNDARY_RE.search("\n".join(dlines[max(0, i - 1):i + 2]))
                for i in anchor_lines(dlines, t["anchors"]))
            if anchored:
                print(f"PASS  {t['id']}: boundary case raised with this value in Author decisions")
            else:
                print(f"FAIL  {t['id']}: boundary/tie not raised against this value in Author decisions")
                ok = False
    return ok


def grade_gate(report, expected):
    gc = expected["gate_case"]
    ok = grade_sections(report)
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
        asserted = assertions_for(lines, t["anchors"]) - {"unverifiable"}
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
