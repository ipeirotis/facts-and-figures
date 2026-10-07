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

from grade_json_report import NEG_ABSENCE_RE, anchor_rx, names_file

EVALS = Path(__file__).resolve().parent
WINDOW = 3  # lines of context on each side of an anchor line (gate mode)

CLS_RE = {
    "match": re.compile(r"\bmatch(es|ed)?\b", re.I),
    "mismatch": re.compile(r"\bmis-?match(es|ed)?\b|\bdoes not match\b|\bdiscrepan", re.I),
    "unverifiable": re.compile(r"\bunverifiable\b|\b(cannot|could not|can['’]t) be verified\b|\bnot verifiable\b", re.I),
}
BOUNDARY_RE = re.compile(r"\bboundary\b|\btie\b|half[- ]even|\bendpoint\b", re.I)
# a negated boundary phrase ("is not a rounding boundary or tie") denies
# the disclosure its words would otherwise satisfy; stripped before the
# scan, with the or/nor continuation absorbed so "or tie" cannot survive
# the stripped negation
NEG_BOUNDARY_RE = re.compile(
    r"\b(?:not|no|never|isn[’']?t|wasn[’']?t)\s+(?:a\s+|an\s+|the\s+)?(?:\w+\s+){0,2}?"
    r"(?:boundary|tie|endpoint)\b"
    r"(?:\s*(?:,|or|nor)\s*(?:a\s+|an\s+|the\s+)?(?:\w+\s+){0,2}?(?:boundary|tie|endpoint)\b)*",
    re.I)
# a negated verdict ("unverifiable, not a match or mismatch" — phrasing a
# live run produced) is gate-compliant prose, not an asserted
# classification; strip it before classifying so the one remaining
# verdict scan does not false-fail reports that follow the gate contract
NEG_VERDICT_RE = re.compile(
    r"\b(?:not|neither|no|never)\b(?:\s+\w+){0,3}?\s+(?:a\s+|an\s+)?(?:mis)?match(?:es|ed)?"
    r"(?:\s+(?:or|nor)\s+(?:a\s+|an\s+)?(?:mis)?match(?:es|ed)?)?", re.I)
SECTIONS = ("scope and gate", "method and provenance", "results", "author decisions")


def heading_rx(name):
    """A contract heading is the section name and nothing else — a heading
    reading "Results omitted" credits no section. Markdown closers and a
    trailing colon are the only extras allowed."""
    return re.compile(r"(?mi)^\s*(?:#{1,6}|\*\*|\d+\.)\s*(?:\d+\.\s*)?(?:\*\*)?\s*"
                      + re.escape(name) + r"\s*(?:\*\*)?\s*:?\s*$")


def grade_sections(report):
    """The skill's return contract names four sections, which must appear as
    actual headings (markdown #, bold, or numbered), not merely be mentioned
    in a sentence — a report saying the sections were omitted must fail."""
    ok = True
    for s in SECTIONS:
        if heading_rx(s).search(report):
            print(f"PASS  section present: {s}")
        else:
            print(f"FAIL  section heading missing: {s}")
            ok = False
    return ok


def anchor_lines(lines, anchors):
    """Lines mentioning any anchor, with the JSON grader's digit guards:
    a line asserting 140 does not cover a target whose anchor is 40."""
    rxs = [anchor_rx(a) for a in anchors]
    return [i for i, ln in enumerate(lines) if any(rx.search(ln.lower()) for rx in rxs)]


def section_span(report, name):
    """The text under a contract heading, up to the next contract heading.
    Returns None when the heading is missing (grade_sections reports that
    on its own) — distinct from an empty string for a present-but-empty
    section, which must NOT fall back to searching the whole report."""
    m = heading_rx(name).search(report)
    if not m:
        return None
    ends = []
    for s in SECTIONS:
        if s == name:
            continue
        m2 = heading_rx(s).search(report, m.end())
        if m2:
            ends.append(m2.start())
    return report[m.end():min(ends)] if ends else report[m.end():]


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
    stripped = [NEG_VERDICT_RE.sub(" ", ln) for ln in lines]
    line_level = set().union(*(classify_text(stripped[i]) for i in hits)) if hits else set()
    if line_level:
        return line_level
    windowed = set()
    for i in hits:
        windowed |= classify_text("\n".join(stripped[max(0, i - WINDOW):i + WINDOW + 1]))
    return windowed


def grade_targets(report, expected):
    lines = report.splitlines()
    ok = grade_sections(report)
    # the decisions span starts at the section HEADING, not the last
    # textual occurrence of the phrase — prose like "these conclude the
    # Author decisions" after the items must not empty the span and fail
    # a valid report
    decisions_text = section_span(report, "author decisions")
    dlines = (decisions_text or "").splitlines()
    # the contract puts the value-by-value comparisons under Results, so
    # coverage is judged there — a report shuffling them into another
    # section while leaving Results empty has not met the contract. Only
    # a MISSING heading (which grade_sections already fails) falls back
    # to the whole report; a present-but-empty section stays empty
    results_text = section_span(report, "results")
    span = lines if results_text is None else results_text.splitlines()
    for t in expected["targets"]:
        if anchor_lines(span, t["anchors"]):
            print(f"PASS  {t['id']}: covered in the Results section")
        else:
            print(f"FAIL  {t['id']}: no Results line mentions any anchor {t['anchors']}")
            ok = False
        if t["expected"] in ("mismatch", "unverifiable"):
            # a planted mismatch and an unverifiable value are the
            # author's calls to make — correct or disclose — so each must
            # surface in Author decisions, not only in Results; the live
            # runs all did this unprompted
            if anchor_lines(dlines, t["anchors"]):
                print(f"PASS  {t['id']}: raised in Author decisions")
            else:
                print(f"FAIL  {t['id']}: {t['expected']} value absent from Author decisions")
                ok = False
        if t.get("boundary"):
            # the protocol requires the tie named in Author decisions, not
            # merely mentioned in Results, so the author chooses the
            # rounding convention — and the disclosure must sit with THIS
            # value: a boundary word about some other target is not the
            # required tie disclosure
            anchored = any(
                BOUNDARY_RE.search(
                    NEG_BOUNDARY_RE.sub(" ", "\n".join(dlines[max(0, i - 1):i + 2])))
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
    # the absence language must sit WITH the removed input: a report
    # saying the required file is available while some other file is
    # missing must not pass on two independent substring hits
    lower_lines = [ln.lower() for ln in report.splitlines()]
    terms = [p.lower() for p in gc["report_must_contain_any"]]
    for name in gc["report_must_name"]:
        # bounded, like every source comparison in the JSON grader: a
        # report naming only notworkers.csv has not named the removed
        # input — and with the gate companion optional, this prose path
        # can be the only one grading the claim
        idxs = [i for i, ln in enumerate(lower_lines) if names_file(name, ln)]
        if not idxs:
            print(f"FAIL  gate: report never names {name}")
            ok = False
            continue
        print(f"PASS  gate: report names {name}")
        # negated absence phrases are stripped before the term scan, so
        # "not missing; present and verified" cannot state the absence
        # on the strength of the token it negates
        if any(any(t in NEG_ABSENCE_RE.sub(" ", "\n".join(lower_lines[max(0, i - 2):i + 3]))
                   for t in terms)
               for i in idxs):
            print(f"PASS  gate: absence stated with {name}")
        else:
            print(f"FAIL  gate: none of {gc['report_must_contain_any']} appear near {name}")
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
