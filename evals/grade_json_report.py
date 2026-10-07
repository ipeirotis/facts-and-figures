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

import hashlib
import json
import re
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

    expect = target.get("bundle_expect")
    if expect is not None and not isinstance(computed, (list, tuple)):
        # the claim bundles a fixed set of quantities, so a scalar
        # verifies only one of them — 20 is not the 20-and-20 split
        return False

    if isinstance(computed, (list, tuple)):
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


def grade_top_level(g, report, expected):
    for key in TOP_REQUIRED:
        v = report.get(key)
        good = v == SCHEMA if key == "schema" else bool(v)
        g.check(good, f"top-level {key} present and non-empty",
                "" if good else repr(v)[:60])
    # the eval installs this repository's skill, so the declared version
    # must be the installed one — arbitrary provenance would leave a
    # consumer unable to tell which protocol produced the report
    want_version = (EVALS.parent / "VERSION").read_text().strip()
    got_version = str(report.get("skill_version") or "").strip()
    g.check(got_version == want_version, "skill_version matches the installed skill",
            "" if got_version == want_version else f"report {got_version!r} vs VERSION {want_version!r}")
    want_files = expected.get("manuscript_files")
    if want_files:
        got = report.get("manuscript_files")
        g.check(sorted(map(str, got or [])) == sorted(want_files),
                "manuscript_files names the scoped manuscript",
                "" if sorted(map(str, got or [])) == sorted(want_files) else repr(got)[:60])
    # the top-level pipeline command names THE pipeline (unlike per-record
    # supplementary commands), so it must at least invoke the canonical
    # script; output-directory arguments remain legitimate
    script = str(expected.get("pipeline_command", "")).split()[-1] if expected.get("pipeline_command") else ""
    if script:
        got_cmd = str(report.get("pipeline_command", ""))
        g.check(script in got_cmd, "pipeline_command invokes the canonical pipeline script",
                "" if script in got_cmd else repr(got_cmd)[:60])
    values = report.get("values") or []
    bad = [i for i, r in enumerate(values)
           if any(not str(r.get(k) or "").strip() for k in RECORD_REQUIRED)]
    g.check(not bad, "required record fields present and non-empty",
            f"records with missing or empty fields: {bad}" if bad else f"{len(values)} records")
    # the schema requires `reported` to carry the manuscript text verbatim,
    # so it must be a string — a JSON number loses the formatting consumers
    # rely on for display and traceability
    non_str = [i for i, r in enumerate(values) if not isinstance(r.get("reported"), str)]
    g.check(not non_str, "reported is a verbatim string on every record",
            f"records with non-string reported: {non_str}" if non_str else "")
    # a location must at least name a place in the manuscript — a filler
    # string cannot support the promised value-by-value review
    place_tokens = ("manuscript", "abstract", "data", "results", "method",
                    "table", "figure", "scope", "author")
    bad_locs = [r.get("location") for r in values
                if not any(tok in str(r.get("location", "")).lower() for tok in place_tokens)]
    g.check(not bad_locs, "record locations identify a manuscript place",
            f"unusable locations: {bad_locs[:3]}" if bad_locs else "")
    return values


def grade_targets(report, expected):
    g = Grader()
    values = grade_top_level(g, report, expected)

    # the data provenance must identify the actual fixture input, not an
    # invented file or digest — the workspaces are byte copies, so the
    # repository fixture's hash is the ground truth. The schema requires
    # the actual input path but not one exact spelling, so the entry is
    # located by normalized path: "data/workers.csv", "./data/workers.csv"
    # and an absolute workspace path all name the same input
    fixture_data = EVALS / expected["fixture"] / "data" / "workers.csv"
    true_hash = hashlib.sha256(fixture_data.read_bytes()).hexdigest()
    want_key = "data/workers.csv"

    def norm(k):
        return re.sub(r"^\./", "", str(k).replace("\\", "/"))

    entries = [str(v) for k, v in (report.get("data_versions") or {}).items()
               if norm(k) == want_key or norm(k).endswith("/" + want_key)]
    ok = bool(entries) and all(true_hash in e for e in entries)
    g.check(ok, "data_versions carries the real workers.csv digest",
            "" if ok else f"entries: {[e[:50] for e in entries]!r}")

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


def distinct_matching(cover):
    """Size of a maximum bipartite matching of targets to records, each
    record representing at most one target. The schema requires one record
    per manuscript value, so every target must claim its own record — a
    merged record covering every anchor, even padded with duplicates of a
    single target, cannot represent them all."""
    match = {}

    def assign(i, seen):
        for rid in cover[i]:
            if rid in seen:
                continue
            seen.add(rid)
            if rid not in match or assign(match[rid], seen):
                match[rid] = i
                return True
        return False

    return sum(1 for i in range(len(cover)) if assign(i, set()))


def grade_gate(report, expected):
    g = Grader()
    values = grade_top_level(g, report, expected)
    paired = set()
    cover = []
    for t in expected["targets"]:
        recs = pair_records(values, t["anchors"])
        paired.update(id(r) for r in recs)
        cover.append([id(r) for r in recs])
        g.check(bool(recs), f"gate: {t['id']} covered by a record")
    # after a failed gate every record shares one classification and a
    # null computed value, so coverage alone cannot tell ten records from
    # one concatenation — each target must have a distinct record of its own
    matched = distinct_matching(cover)
    g.check(matched == len(expected["targets"]),
            "gate: each target has a distinct record",
            f"only {matched} of {len(expected['targets'])} targets have their own record")
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
    # provenance for the removed input must record its absence — the
    # schema requires it where there is nothing to hash. Asserting a
    # digest is a planted claim, and so is any entry that does not state
    # the absence ("present and verified" is not a recorded absence)
    dv = report.get("data_versions") or {}
    for name in expected["gate_case"]["remove"]:
        base = name.split("/")[-1].lower()
        entries = [str(v) for k, v in dv.items() if base in str(k).lower()]
        faked = [e for e in entries if re.search(r"[0-9a-f]{40,}", e.lower())]
        g.check(not faked, f"gate: no digest asserted for removed input {name}",
                f"entries: {faked}" if faked else "")
        absent_ok = bool(entries) and all(
            re.search(r"absent|missing|not found|unavailable|unreachable|removed|no such",
                      e.lower()) for e in entries)
        g.check(absent_ok, f"gate: data_versions records {name} as absent",
                f"entries: {entries}" if not absent_ok else "")
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
