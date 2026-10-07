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

RECORD_REQUIRED = {"location", "reported", "classification"}


def norm_path(k):
    """One spelling for a provenance path: slashes forward, no ./ prefix."""
    return re.sub(r"^\./", "", str(k).replace("\\", "/"))


def names_input(key, want):
    """True when a provenance key names the workspace-relative input: an
    exact match, or an ABSOLUTE path ending in it. A relative
    unrelated/data/workers.csv names a different input and must not
    suffix-match."""
    nk = norm_path(key).lower()
    want = want.lower()
    return nk == want or (nk.startswith("/") and nk.endswith("/" + want))


# an absence token inside a negation is a presence claim wearing the
# vocabulary: "not missing; present and verified" carries the token
# while denying the absence the check exists to require. Only the bare
# adjectives appear here — "not found", "not distributed", "did not
# run" and "could not" are themselves absence idioms and must survive
NEG_ABSENCE_RE = re.compile(
    r"\b(?:not|no longer|no|never|isn.?t|wasn.?t|aren.?t|weren.?t)\s+"
    r"(?:missing|unavailable|unreachable|absent|removed)\b")

# a reason crediting the gate or pipeline with success — or asserting
# that its blocking source was present, available, or verified —
# contradicts the unverifiable classification it sits on, whatever
# vocabulary it also carries. Adjacency keeps negations safe: "the gate
# never passed" and "is not present" do not match
GATE_SUCCESS_RE = re.compile(
    r"\b(?:gate|pipeline|run|computation|check)s?\s+(?:succeeded|passed)\b"
    r"|\bvalue\s+is\s+valid\b"
    r"|\b(?:is|are|was|were|remains?)\s+(?:present|available|verified|intact)\b")
TOP_REQUIRED = ("schema", "skill_version", "manuscript_files", "pipeline_command",
                "environment", "data_versions", "values")


def anchor_rx(a):
    """A numeric anchor must not match inside a larger number: "40" is not
    a claim found in "140" or "40.5". Digit guards apply only where the
    anchor itself starts or ends with a digit."""
    pat = re.escape(a.lower())
    if a[:1].isdigit():
        pat = r"(?<![\d.,])" + pat
    if a[-1:].isdigit():
        pat = pat + r"(?!\.?\d)"
    return re.compile(pat)


def pair_records(values, anchors):
    """Records covering a target, paired on the `reported` field only. The
    schema requires `reported` to carry the manuscript value verbatim, so a
    record only locatable through its note or location is non-compliant —
    and an earlier free-text fallback let a record pair on a note mention
    while asserting a different value in `reported`. Pairing uses the
    VALUE-bearing anchors where the target has them: a bare prose anchor
    like "flagged" locates discussion lines for the prose grader, but a
    reported field matching only it does not carry the manuscript value."""
    value_anchors = [a for a in anchors if any(c.isdigit() for c in a)] or anchors
    rxs = [anchor_rx(a) for a in value_anchors]
    return [r for r in values
            if any(rx.search(str(r.get("reported", "")).lower()) for rx in rxs)]


def close(c, t):
    """Equality up to float summation noise (~1e-13) and JSON round-trip,
    SCALED: a fixed absolute epsilon would let a small value hide a
    materially different one — a permutation p-value 0.9% off sat within
    1e-6 of the documented 9.999e-05."""
    return abs(c - t) <= 1e-9 + 1e-9 * abs(t)


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
        return isinstance(c, (int, float)) and any(close(c, t) for t in true_candidates)

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
                            if isinstance(c, (int, float)) and close(c, e)), None)
                if hit is None:
                    return False
                remaining.pop(hit)
            return True
        allowed = true_candidates + list(target.get("bundle_allowed", []))
        def is_allowed(c):
            return isinstance(c, (int, float)) and any(close(c, a) for a in allowed)
        return bool(computed) and any(is_true(c) for c in computed) and all(is_allowed(c) for c in computed)
    return is_true(computed)


def out_of_scope_ids(values, expected):
    """Records covering a manuscript number the answer key deliberately
    leaves out (the 0-100 scale, the three-month interval) are not strays:
    an agent more thorough than the key must not fail for it."""
    rxs = [anchor_rx(a) for a in expected.get("out_of_scope_anchors", [])]
    return {id(r) for r in values
            if any(rx.search(str(r.get("reported", "")).lower()) for rx in rxs)}


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
        # the scoped set must match, but an absolute workspace path that
        # resolves to the keyed file identifies it precisely — normalize
        # like the data-provenance lookup instead of comparing literally
        got = [str(x) for x in (report.get("manuscript_files") or [])]
        ok_files = (len(got) == len(want_files)
                    and all(any(names_input(g, norm_path(w)) for g in got)
                            for w in want_files))
        g.check(ok_files, "manuscript_files names the scoped manuscript",
                "" if ok_files else repr(got)[:60])
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
    # schema shape holds for every record, in or out of the answer key's
    # scope: a record exempt from value equality (the 0-100 scale) is not
    # exempt from the classification enum or its conditional fields
    bad_cls = [str(r.get("classification")) for r in values
               if r.get("classification") not in ("match", "mismatch", "unverifiable")]
    g.check(not bad_cls, "classification within the schema enum on every record",
            f"outside the enum: {bad_cls[:3]}" if bad_cls else "")
    # an unverifiable record owes an EXPLICIT null computed — a missing
    # key breaks consumers relying on the schema's stable record shape
    bad_shape = [str(r.get("reported"))[:40] for r in values
                 if (r.get("classification") == "unverifiable"
                     and ("computed" not in r or r["computed"] is not None
                          or not r.get("reason")))
                 or (r.get("classification") in ("match", "mismatch")
                     and (r.get("computed") is None or not r.get("tolerance")
                          or not r.get("producing_command")))]
    g.check(not bad_shape, "conditional fields match each record's classification",
            f"malformed records: {bad_shape[:3]}" if bad_shape else "")
    # the environment field must name the actual, versioned runtime —
    # "unknown" or a bare "python" supports no reproduction
    env = str(report.get("environment", "")).lower()
    versioned = bool(re.search(r"python\s*[0-9]", env))
    g.check(versioned, "environment names a versioned interpreter",
            "" if versioned else repr(env)[:60])
    # a location must name a section-level place the author can look up —
    # the bare word "manuscript" locates nothing in a document that
    # repeats numbers across sections. The keyed section itself is not
    # required: a live run legitimately located a second occurrence of the
    # group split in Results where the key names Data
    place_tokens = ("abstract", "data", "results", "method", "table", "figure",
                    "introduction", "discussion", "appendix", "conclusion")
    # whole-token matching, bounded on both sides with plurals allowed:
    # "metadata" contains "data" and "database" starts with it, yet
    # neither locates a manuscript section
    bad_locs = [r.get("location") for r in values
                if not any(re.search(r"\b" + tok + r"(?:e?s)?\b",
                                     str(r.get("location", "")).lower())
                           for tok in place_tokens)]
    g.check(not bad_locs, "record locations identify a manuscript place",
            f"unusable locations: {bad_locs[:3]}" if bad_locs else "")
    return values


def check_reported_integrity(g, t, recs):
    """The reported field must reproduce the claim it pairs on — in the
    normal AND the gate path, since the schema requires the manuscript
    value verbatim in both. A negated wrapper denies the claim ("not
    71.48", "not p < 0.001" — the gap tolerates any tokens, so a
    predicate operator between the negator and the value does not break
    the span), and a predicate claim is irreducibly its keyed operator
    and threshold: "p > 0.001", "p = 0.001" and a bare "0.001" all pair
    on the number while reversing, altering, or dropping the assertion.
    Both requirements derive from the answer key's existing fields, not
    a verbatim reported key."""
    vals = [a for a in t["anchors"] if any(c.isdigit() for c in a)] or t["anchors"]
    neg_pats = [re.compile(r"\b(?:not|never|no|isn.?t|wasn.?t)\s+(?:\S+\s+){0,3}?"
                           + anchor_rx(a).pattern) for a in vals]
    negged = [r.get("reported") for r in recs
              if any(p.search(str(r.get("reported", "")).lower()) for p in neg_pats)]
    g.check(not negged,
            f"{t['id']}: reported does not negate the manuscript value",
            f"reported: {negged}" if negged else "")
    if t.get("kind") == "predicate" and t.get("predicate") in ("less_than",
                                                               "greater_than"):
        op = "<" if t["predicate"] == "less_than" else ">"
        want_ns = op + str(t.get("predicate_value", ""))
        bad_pred = [r.get("reported") for r in recs
                    if want_ns not in str(r.get("reported", "")).lower().replace(" ", "")]
        g.check(not bad_pred,
                f"{t['id']}: reported states the keyed predicate {want_ns}",
                f"reported: {bad_pred}" if bad_pred else "")


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
    entries = [str(v) for k, v in (report.get("data_versions") or {}).items()
               if names_input(k, want_key)]
    # the digest must be stated exactly, not merely mentioned: "old copy
    # was sha256:<expected>; current file is sha256:<zeros>" contains the
    # true hash while recording a different current input, so every long
    # hex run in the entry must BE the true hash
    def digests(e):
        return re.findall(r"[0-9a-f]{40,}", e.lower())
    ok = bool(entries) and all(
        digests(e) and set(digests(e)) == {true_hash} for e in entries)
    g.check(ok, "data_versions carries the real workers.csv digest",
            "" if ok else f"entries: {[e[:50] for e in entries]!r}")

    # the documented RNG seed must appear in a provenance field — the
    # protocol logs it so the permutation result can be reproduced, and a
    # mention buried in a note is a remark, not provenance
    seed = str(expected.get("pipeline_seed", ""))
    if seed:
        # computed values are deliberately NOT provenance: the keyed
        # bundle [10000, 20260816] is a graded echo of the answer key
        # (bundle_allowed names the seed), so counting it here was
        # circular — a report with the seed nowhere but in that bundle
        # recorded no RNG provenance at all
        prov = " ".join(
            [str(report.get("environment", "")), str(report.get("pipeline_command", ""))]
            + [str(r.get("producing_command", "")) for r in values])
        # a negated mention is not provenance: "seed was not 20260816;
        # actual seed 7" names the digits while denying them, so the
        # negated phrase is stripped before the scan
        neg_seed = re.compile(
            r"\b(?:not|never|wasn.?t|isn.?t)\s+(?:\w+\s+){0,2}?" + re.escape(seed),
            re.I)
        g.check(seed in neg_seed.sub(" ", prov),
                "the pipeline seed appears in the provenance fields")

    paired = set()
    for t in expected["targets"]:
        recs = pair_records(values, t["anchors"])
        paired.update(id(r) for r in recs)
        if not recs:
            g.check(False, f"{t['id']}: a record covers it", f"no record mentions {t['anchors']}")
            continue
        check_reported_integrity(g, t, recs)
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
            # the same rejection the gate grader applies: a reason that
            # DENIES the absence or credits the run with success
            # contradicts the unverifiable classification it sits on,
            # whichever file it also names
            denying = [str(r.get("reason"))[:60] for r in recs
                       if NEG_ABSENCE_RE.search(str(r.get("reason", "")).lower())
                       or GATE_SUCCESS_RE.search(str(r.get("reason", "")).lower())]
            g.check(not denying, f"{t['id']}: no reason denies the absence",
                    f"reasons: {denying}" if denying else "")
            must = t.get("reason_must_contain", "").lower()
            # bounded: the stem inside ANOTHER filename
            # (not_wave2_followup.csv) names a different file
            must_rx = (re.compile(r"(?<![\w.-])" + re.escape(must) + r"(?!\w)")
                       if must else None)
            g.check(all(must_rx.search(str(r.get("reason", "")).lower()) for r in recs)
                    if must_rx else True,
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
    hits = {}
    rec_targets = {}
    for t in expected["targets"]:
        recs = pair_records(values, t["anchors"])
        paired.update(id(r) for r in recs)
        cover.append([id(r) for r in recs])
        for r in recs:
            hits.setdefault(id(r), [str(r.get("reported"))[:40], 0])
            hits[id(r)][1] += 1
            rec_targets.setdefault(id(r), set()).add(t["id"])
        g.check(bool(recs), f"gate: {t['id']} covered by a record")
        # the gate companion requires the manuscript value verbatim too
        if recs:
            check_reported_integrity(g, t, recs)
    # one record per manuscript value cuts both ways: a record pairing to
    # several targets is a record of no single value, so ten copies of a
    # concatenated reported string must not pass as ten distinct records
    multi = [rep for rep, n in hits.values() if n > 1]
    g.check(not multi, "gate: each record covers exactly one target",
            f"records spanning several targets: {multi[:2]}" if multi else "")
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
    # each reason must actually explain an absence or the failed gate —
    # "the pipeline succeeded and this value is valid" contradicts the
    # unverifiable classification it sits on. A record may cite its own
    # missing source (the undistributed wave-2 file) rather than the
    # removed input, so absence vocabulary or the removed name both count
    # the bare word "gate" is auto-satisfied by compliant phrasing in
    # either direction — "gate passed; the value is valid" wore it — so
    # only the failure collocations count as gate vocabulary
    gate_words = ("failed gate", "gate failed", "gate failure", "missing",
                  "not found", "unavailable", "unreachable", "absent",
                  "removed", "not distributed", "did not run", "never ran",
                  "could not")
    removed = [norm_path(n).lower() for n in expected["gate_case"]["remove"]]
    # a reason that DENIES the absence or CREDITS the gate with success
    # fails outright, whatever else it names: "workers.csv is not
    # missing" and "gate passed for workers.csv" would otherwise pass on
    # the basename alone
    bad_reasons = [str(r.get("reason"))[:60] for r in values
                   if NEG_ABSENCE_RE.search(str(r.get("reason", "")).lower())
                   or GATE_SUCCESS_RE.search(str(r.get("reason", "")).lower())
                   or (not any(w in str(r.get("reason", "")).lower() for w in gate_words)
                       and not any(n.split("/")[-1] in str(r.get("reason", "")).lower()
                                   for n in removed))]
    g.check(not bad_reasons, "every reason explains an absence or the failed gate",
            f"reasons: {bad_reasons[:2]}" if bad_reasons else "")
    # a reason must explain THIS record's blockage: a record covering
    # the sample size while citing only the optional wave-2 file as its
    # missing source manufactures failure provenance the gate did not
    # route through that file. A target-specific source is permitted
    # only on records covering its own target; the removed input and
    # the failed gate remain valid for every record
    specific = {t["id"]: str(t.get("reason_must_contain", "")).lower()
                for t in expected["targets"] if t.get("reason_must_contain")}
    misattributed = []
    for r in values:
        reason = str(r.get("reason", "")).lower()
        if any(n.split("/")[-1] in reason for n in removed):
            continue
        if any(w in reason for w in ("failed gate", "gate failed", "gate failure")):
            continue
        cited = {tid for tid, src in specific.items() if src and src in reason}
        if cited and not (rec_targets.get(id(r), set()) & cited):
            misattributed.append(str(r.get("reason"))[:60])
    g.check(not misattributed,
            "gate: no reason cites only another target's missing source",
            f"reasons: {misattributed[:2]}" if misattributed else "")
    # provenance for the removed input must record its absence — the
    # schema requires it where there is nothing to hash. Asserting a
    # digest is a planted claim, and so is any entry that does not state
    # the absence ("present and verified" is not a recorded absence)
    dv = report.get("data_versions") or {}
    for name in expected["gate_case"]["remove"]:
        # locate the entry by normalized path, as the normal-case check
        # does — a basename substring would accept an absence recorded
        # for a different file (data/notworkers.csv)
        entries = [str(v) for k, v in dv.items() if names_input(k, norm_path(name))]
        faked = [e for e in entries if re.search(r"[0-9a-f]{40,}", e.lower())]
        g.check(not faked, f"gate: no digest asserted for removed input {name}",
                f"entries: {faked}" if faked else "")
        # negated tokens are stripped before the scan, so "not missing;
        # present and verified" cannot satisfy the absence requirement
        # on the strength of the token it negates
        absent_ok = bool(entries) and all(
            re.search(r"absent|missing|not found|unavailable|unreachable|removed|no such",
                      NEG_ABSENCE_RE.sub(" ", e.lower())) for e in entries)
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
