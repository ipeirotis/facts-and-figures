#!/usr/bin/env python3
"""Self-test for the graders. No LLM: runs each grader against the mock
reports in tests/ and asserts the expected verdict, so a grader regression
is caught deterministically instead of surfacing as a confusing agent-eval
failure.

Usage: python3 evals/test_graders.py
Exit code 0 iff every grader verdict is as expected.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

EVALS = Path(__file__).resolve().parent
TESTS = EVALS / "tests"
VERSION = (EVALS.parent / "VERSION").read_text().strip()

# (grader script, extra args, mock file, expected exit code)
CASES = [
    ("grade_report.py", [], "mock_good.md", 0),
    ("grade_report.py", [], "mock_bad.md", 1),
    ("grade_report.py", ["--gate"], "mock_gate.md", 0),
    ("grade_json_report.py", [], "mock_good.json", 0),
    ("grade_json_report.py", [], "mock_bad.json", 1),
    ("grade_json_report.py", ["--gate"], "mock_gate.json", 0),
    ("grade_report.py", ["--gate"], "mock_gate_bad.md", 1),
    ("grade_json_report.py", ["--gate"], "mock_gate_bad.json", 1),
]


def _numeric_reported(d):
    """The Codex round-15 PoC: a JSON 10000 whose digits still pair with
    the 10,000 anchor."""
    for r in d["values"]:
        if r.get("reported") == "10,000":
            r["reported"] = 10000


def _collapsed_gate(d):
    """One record whose reported string concatenates every anchor must not
    satisfy ten per-value coverage checks: the schema requires one record
    per manuscript value."""
    merged = dict(d["values"][0])
    merged["reported"] = "; ".join(str(r.get("reported", "")) for r in d["values"])
    d["values"] = [merged]


def _merged_plus_duplicates(d):
    """A merged record covering every anchor, padded with duplicates of a
    single target to inflate the record count, must still fail: each
    target needs a distinct record of its own."""
    merged = dict(d["values"][0])
    merged["reported"] = "; ".join(str(r.get("reported", "")) for r in d["values"])
    first = dict(d["values"][0])
    d["values"] = [merged] + [dict(first) for _ in range(len(d["values"]) - 1)]


def _scalar_bundle(d):
    """A scalar 20 for the 20-and-20 group split verifies only one group."""
    for r in d["values"]:
        if r.get("computed") == [20, 20]:
            r["computed"] = 20


def _ten_concatenated(d):
    """Ten copies of a record whose reported string concatenates every
    anchor form a perfect matching, but no copy is a record of any single
    manuscript value."""
    merged = dict(d["values"][0])
    merged["reported"] = "; ".join(str(r.get("reported", "")) for r in d["values"])
    d["values"] = [dict(merged) for _ in range(len(d["values"]))]


def _fabricated_exempt(d):
    """A record exempt from answer-key equality (an out-of-scope anchor)
    still owes the schema its classification enum."""
    d["values"].append({"location": "manuscript.md, Data", "reported": "0-100 scale",
                        "classification": "fabricated", "computed": 999})


def _renamed_data_key(d):
    """A legitimate alternative spelling of the hashed input's path must
    still pass: the schema requires the actual path, not one dictionary
    key."""
    d["data_versions"] = {"./data/workers.csv": v
                          for v in [d["data_versions"]["data/workers.csv"]]}


# single-field edits of a passing mock and the grader verdict each must
# produce: (label, extra args, base mock, mutation, expected exit code)
MUTATIONS = [
    ("numeric reported", [], "mock_good.json", _numeric_reported, 1),
    ("wrong skill_version", [], "mock_good.json",
     lambda d: d.update(skill_version="not-the-installed-skill"), 1),
    ("fabricated digest for removed input", ["--gate"], "mock_gate.json",
     lambda d: d["data_versions"].update({"data/workers.csv": "sha256:" + "0" * 64}), 1),
    ("presence claimed for removed input", ["--gate"], "mock_gate.json",
     lambda d: d["data_versions"].update({"data/workers.csv": "present and verified"}), 1),
    ("./-prefixed data_versions key", [], "mock_good.json", _renamed_data_key, 0),
    ("all anchors collapsed into one record", ["--gate"], "mock_gate.json",
     _collapsed_gate, 1),
    ("merged record padded with duplicates", ["--gate"], "mock_gate.json",
     _merged_plus_duplicates, 1),
    ("scalar computed for the bundled group split", [], "mock_good.json",
     _scalar_bundle, 1),
    ("ten concatenated records forming a fake matching", ["--gate"], "mock_gate.json",
     _ten_concatenated, 1),
    ("fabricated classification on an exempt record", [], "mock_good.json",
     _fabricated_exempt, 1),
    ("environment reduced to a placeholder", [], "mock_good.json",
     lambda d: d.update(environment="unknown"), 1),
    ("locations reduced to the bare word manuscript", [], "mock_good.json",
     lambda d: [r.update(location="manuscript") for r in d["values"]], 1),
    ("exempt match record without provenance fields", [], "mock_good.json",
     lambda d: d["values"].append({"location": "manuscript.md, Data",
                                   "reported": "0-100", "classification": "match",
                                   "computed": 999}), 1),
    ("absence entry keyed to a different file", ["--gate"], "mock_gate.json",
     lambda d: d.update(data_versions={"data/notworkers.csv":
                                       d["data_versions"]["data/workers.csv"]}), 1),
    ("seed exiled from provenance to a note", [], "mock_good.json",
     lambda d: (d.update(environment="Python 3.11.15, stdlib only"),
                d["values"][0].update(note="the run used seed 20260816")), 1),
    ("locations reduced to the word metadata", [], "mock_good.json",
     lambda d: [r.update(location="metadata") for r in d["values"]], 1),
    ("gate reasons claiming the pipeline succeeded", ["--gate"], "mock_gate.json",
     lambda d: [r.update(reason="the pipeline succeeded and this value is valid")
                for r in d["values"]], 1),
    ("sample size reported as 140", [], "mock_good.json",
     lambda d: [r.update(reported="140") for r in d["values"]
                if r.get("reported") == "40"], 1),
    ("locations reduced to the word database", [], "mock_good.json",
     lambda d: [r.update(location="database") for r in d["values"]], 1),
    ("digest keyed to a relative unrelated path", [], "mock_good.json",
     lambda d: d.update(data_versions={"unrelated/data/workers.csv":
                                       d["data_versions"]["data/workers.csv"]}), 1),
    ("flagged-share reported without the value", [], "mock_good.json",
     lambda d: [r.update(reported="flagged") for r in d["values"]
                if "13" in str(r.get("reported", ""))], 1),
    ("absolute manuscript_files path", [], "mock_good.json",
     lambda d: d.update(manuscript_files=["/tmp/fnf-eval.x/verify/manuscript.md"]), 0),
    ("exempt unverifiable without explicit null computed", [], "mock_good.json",
     lambda d: d["values"].append({"location": "manuscript.md, Data",
                                   "reported": "0-100 scale",
                                   "classification": "unverifiable",
                                   "reason": "the scale is not a pipeline output"}), 1),
    # a negated absence token is a presence claim wearing the vocabulary
    ("negated absence recorded for removed input", ["--gate"], "mock_gate.json",
     lambda d: d["data_versions"].update(
         {"data/workers.csv": "not missing; present and verified"}), 1),
    ("gate reason denying the absence by name", ["--gate"], "mock_gate.json",
     lambda d: [r.update(reason="data/workers.csv is not missing; the value stands")
                for r in d["values"]], 1),
    # ...but "not found" is itself an absence idiom and must keep passing
    ("gate reasons using the not-found idiom", ["--gate"], "mock_gate.json",
     lambda d: [r.update(reason="input data/workers.csv was not found; "
                                "the pipeline could not run")
                for r in d["values"]], 0),
    # the true digest mentioned beside a different current one is not a
    # record of the true digest
    ("expected digest quoted beside a planted current one", [], "mock_good.json",
     lambda d: d["data_versions"].update(
         {"data/workers.csv": "old copy was "
          + d["data_versions"]["data/workers.csv"]
          + "; current file is sha256:" + "0" * 64}), 1),
    ("digest entry with a plain annotation", [], "mock_good.json",
     lambda d: d["data_versions"].update(
         {"data/workers.csv": d["data_versions"]["data/workers.csv"]
          + " (10,000 rows)"}), 0),
    # the bare word "gate" must not whitelist a reason crediting the
    # gate with success
    ("gate reasons crediting a passed gate", ["--gate"], "mock_gate.json",
     lambda d: [r.update(reason="gate passed; the pipeline succeeded "
                                "and this value is valid")
                for r in d["values"]], 1),
    # ...while naming the FAILED gate remains sufficient vocabulary
    ("gate reasons naming the failed gate", ["--gate"], "mock_gate.json",
     lambda d: [r.update(reason="verification stopped at the failed gate")
                for r in d["values"]], 0),
    # a p-value 0.9% off sat inside the old absolute epsilon
    ("permutation p-value off by one percent", [], "mock_good.json",
     lambda d: [r.update(computed=0.00010089990009990002) for r in d["values"]
                if r.get("reported") == "p < 0.001"], 1),
    # a missing-source reason denying the absence names the file while
    # contradicting the unverifiable classification it sits on
    ("missing-source reason claiming presence", [], "mock_good.json",
     lambda d: [r.update(reason="data/wave2_followup.csv is present and "
                                "verified; it is not missing")
                for r in d["values"]
                if r.get("classification") == "unverifiable"], 1),
    # a reported field reversing the manuscript predicate pairs on the
    # bare threshold while asserting the opposite claim
    ("reported predicate reversed", [], "mock_good.json",
     lambda d: [r.update(reported="p > 0.001") for r in d["values"]
                if r.get("reported") == "p < 0.001"], 1),
    # an equality is not the manuscript claim either: the keyed operator
    # and threshold must be stated
    ("reported predicate reduced to equality", [], "mock_good.json",
     lambda d: [r.update(reported="p = 0.001") for r in d["values"]
                if r.get("reported") == "p < 0.001"], 1),
    # a negated seed mention names the digits while denying them
    ("seed denied in the environment field", [], "mock_good.json",
     lambda d: d.update(environment="Python 3.11.15, stdlib only; "
                                    "seed was not 20260816; actual seed 7"), 1),
    # an affirmative availability claim needs no negation to contradict
    # the unverifiable classification it sits on
    ("missing-source reason asserting availability", [], "mock_good.json",
     lambda d: [r.update(reason="data/wave2_followup.csv is present and verified")
                for r in d["values"]
                if r.get("classification") == "unverifiable"], 1),
    # ...while historical context beside a current absence statement
    # stays truthful
    ("missing-source reason with historical context", [], "mock_good.json",
     lambda d: [r.update(reason="data/wave2_followup.csv is missing from this "
                                "checkout; it was present in the archived v1 snapshot")
                for r in d["values"]
                if r.get("classification") == "unverifiable"], 0),
    # a negated wrapper around the manuscript value denies the claim it
    # pairs on
    ("reported value negated", [], "mock_good.json",
     lambda d: [r.update(reported="not 71.48") for r in d["values"]
                if r.get("reported") == "71.48"], 1),
    # ...and predicate syntax must not break the negation span
    ("reported predicate negated", [], "mock_good.json",
     lambda d: [r.update(reported="not p < 0.001") for r in d["values"]
                if r.get("reported") == "p < 0.001"], 1),
    # the gate companion requires the manuscript value verbatim too
    ("gate reported value negated", ["--gate"], "mock_gate.json",
     lambda d: [r.update(reported="not 71.48") for r in d["values"]
                if r.get("reported") == "71.48"], 1),
    # a graded echo of the keyed bundle is not RNG provenance
    ("seed only in a computed bundle", [], "mock_good.json",
     lambda d: (d.update(environment="Python 3.11.15, stdlib only"),
                [r.update(computed=[10000, 20260816]) for r in d["values"]
                 if r.get("reported") == "10,000"]), 1),
    # the missing-source stem inside another filename names a different
    # file
    ("missing-source reason naming a lookalike file", [], "mock_good.json",
     lambda d: [r.update(reason="data/not_wave2_followup.csv is missing "
                                "from the distribution")
                for r in d["values"]
                if r.get("classification") == "unverifiable"], 1),
    # a negated digest denies the provenance it spells out
    ("input digest negated", [], "mock_good.json",
     lambda d: d["data_versions"].update(
         {"data/workers.csv": "not " + d["data_versions"]["data/workers.csv"]}), 1),
    # a gate reason citing an unkeyed file fabricates blockage the gate
    # did not route through it
    ("gate reasons citing an unrelated file", ["--gate"], "mock_gate.json",
     lambda d: [r.update(reason="README.md is missing from the repository")
                for r in d["values"]], 1),
    # ...and a lookalike of the removed input is such a file: the
    # basename match is bounded
    ("gate reasons citing a lookalike of the removed input", ["--gate"],
     "mock_gate.json",
     lambda d: [r.update(reason="data/notworkers.csv is missing")
                for r in d["values"]], 1),
    # an exact integer count owes no relative slack
    ("permutation count off by a millionth", [], "mock_good.json",
     lambda d: [r.update(computed=10000.000009) for r in d["values"]
                if r.get("reported") == "10,000"], 1),
    # ...and a float target owes only genuine summation noise
    ("overall mean off beyond float noise", [], "mock_good.json",
     lambda d: [r.update(computed=71.48250005) for r in d["values"]
                if r.get("computed") == 71.4825], 1),
    # ...while citing the pipeline script it tried to run stays
    # legitimate
    ("gate reasons citing the pipeline script", ["--gate"], "mock_gate.json",
     lambda d: [r.update(reason="python3 analysis/run_analysis.py exited 1; "
                                "the pipeline did not run")
                for r in d["values"]], 0),
    # a presence claim about the blocking input is a contradiction even
    # when an unrelated file is said to be missing beside it
    ("gate reasons claiming the removed input present, blaming another file",
     ["--gate"], "mock_gate.json",
     lambda d: [r.update(reason="data/workers.csv is present and verified; "
                                "README.md is missing")
                for r in d["values"]], 1),
    # seed digits inside a larger number record no seed
    ("seed digits embedded in a build number", [], "mock_good.json",
     lambda d: d.update(environment="Python 3.11.15, stdlib only; "
                                    "build 1202608167"), 1),
    # the manuscript's actual Data wording is verbatim-compliant and
    # must pair with the group-split target
    ("group-split reported with the manuscript wording", [], "mock_good.json",
     lambda d: [r.update(reported="20 with prior platform experience and 20 without")
                for r in d["values"]
                if r.get("reported") == "20 / 20"], 0),
    # a gate reason citing only the optional wave-2 source manufactures
    # failure provenance for the nine targets the gate did not block
    # through it
    ("gate reasons citing only the wave-2 source", ["--gate"], "mock_gate.json",
     lambda d: [r.update(reason="data/wave2_followup.csv is not distributed; "
                                "nothing was computed")
                for r in d["values"]], 1),
    # ...while a generic absence reason naming no specific source stays
    # sufficient
    ("gate reasons naming no specific source", ["--gate"], "mock_gate.json",
     lambda d: [r.update(reason="the required input is missing and the "
                                "pipeline did not run")
                for r in d["values"]], 0),
    # naming the source is not explaining the blockage: the bare stem
    # says nothing about why the value is unverifiable
    ("missing-source reason reduced to the bare stem", [], "mock_good.json",
     lambda d: [r.update(reason="wave2_followup")
                for r in d["values"]
                if r.get("classification") == "unverifiable"], 1),
    # ...while failure vocabulary explains the blockage as well as the
    # absence idioms do
    ("missing-source reason stating a load failure", [], "mock_good.json",
     lambda d: [r.update(reason="pipeline failed to load data/wave2_followup.csv")
                for r in d["values"]
                if r.get("classification") == "unverifiable"], 0),
    # a producing command wearing the runtime token while touching no
    # known pipeline artifact is fabricated provenance
    ("producing commands reduced to echo python", [], "mock_good.json",
     lambda d: [r.update(producing_command="echo python") for r in d["values"]
                if r.get("producing_command")], 1),
    # ...while a supplementary command computing straight from the
    # dataset is legitimate provenance, as a live run produced
    ("supplementary command naming the dataset", [], "mock_good.json",
     lambda d: [r.update(producing_command="python3 -I -c \"csv count of rows "
                                           "in data/workers.csv\"")
                for r in d["values"]
                if r.get("reported") == "20 / 20"], 0),
    # a Data-only value located in Results sends the author to the wrong
    # section — the location must name a section carrying the value
    ("every location relocated to Results", [], "mock_good.json",
     lambda d: [r.update(location="manuscript.md, Results")
                for r in d["values"]], 1),
    # ...while a genuine second occurrence outside the keyed location
    # stays legitimate, as a live run located the group split in Results
    ("group split located at its Results occurrence", [], "mock_good.json",
     lambda d: [r.update(location="manuscript.md, Results") for r in d["values"]
                if r.get("reported") == "20 / 20"], 0),
    # a digest asserted for the source the record itself classifies as
    # unavailable is an uncomputed hash — the gate path has rejected
    # this for its removed input all along
    ("digest asserted for the unavailable wave-2 source", [], "mock_good.json",
     lambda d: d["data_versions"].update(
         {"data/wave2_followup.csv": "sha256:" + "ab" * 32}), 1),
    # ...while an entry recording the absence is legitimate provenance
    ("wave-2 absence recorded in data_versions", [], "mock_good.json",
     lambda d: d["data_versions"].update(
         {"data/wave2_followup.csv": "not distributed - nothing to hash"}), 0),
    # the gate path's attribution must be bounded like the normal path:
    # a lookalike filename must not exempt itself as the wave-2 record's
    # own legitimate source
    ("gate wave-2 reason citing a lookalike of its own source", ["--gate"],
     "mock_gate.json",
     lambda d: [r.update(reason="data/not_wave2_followup.csv is missing")
                for r in d["values"] if r.get("reported") == "64%"], 1),
    # ...while the wave-2 record citing its real keyed source stays
    # legitimate on the gate path
    ("gate wave-2 reason citing its real source", ["--gate"], "mock_gate.json",
     lambda d: [r.update(reason="data/wave2_followup.csv is not distributed; "
                                "nothing was computed")
                for r in d["values"] if r.get("reported") == "64%"], 0),
    # a trailing continuation is a different file too: the stem must be
    # bounded on BOTH sides, not only against prefix lookalikes
    ("missing-source reason citing a suffix lookalike", [], "mock_good.json",
     lambda d: [r.update(reason="data/wave2_followup-old.csv is not distributed")
                for r in d["values"]
                if r.get("classification") == "unverifiable"], 1),
    ("gate wave-2 reason citing a suffix lookalike", ["--gate"], "mock_gate.json",
     lambda d: [r.update(reason="data/wave2_followup-old.csv is missing")
                for r in d["values"] if r.get("reported") == "64%"], 1),
    # ...while a sentence-final period after the real filename is prose,
    # not a filename continuation
    ("missing-source reason ending at the filename", [], "mock_good.json",
     lambda d: [r.update(reason="the pipeline could not read "
                                "data/wave2_followup.csv.")
                for r in d["values"]
                if r.get("classification") == "unverifiable"], 0),
    # a section token inside a filename is a file, not a section: a
    # location of nonexistent documents certifies no traceability
    ("locations replaced by section-named files", [], "mock_good.json",
     lambda d: [r.update(location="results.md") for r in d["values"]], 1),
    # the same stem under a different extension is a file the fixture
    # does not contain — the keyed basename must match exactly
    ("missing-source reason citing a different extension", [], "mock_good.json",
     lambda d: [r.update(reason="data/wave2_followup.txt is missing "
                                "from the distribution")
                for r in d["values"]
                if r.get("classification") == "unverifiable"], 1),
    ("gate wave-2 reason citing a different extension", ["--gate"],
     "mock_gate.json",
     lambda d: [r.update(reason="data/wave2_followup.txt is missing")
                for r in d["values"] if r.get("reported") == "64%"], 1),
    # a basename that is merely a substring of a known artifact is a
    # distinct, nonexistent file — the context allowlist compares exact
    # basenames, so analysis.py cannot ride in on run_analysis.py
    ("gate reasons citing a tail of the pipeline script", ["--gate"],
     "mock_gate.json",
     lambda d: [r.update(reason="analysis.py is missing")
                for r in d["values"]], 1),
    # the file scan is extension-agnostic: blaming appendix.tex
    # fabricates blockage as surely as blaming README.md
    ("gate reasons citing an unkeyed tex file", ["--gate"], "mock_gate.json",
     lambda d: [r.update(reason="appendix.tex is missing")
                for r in d["values"]], 1),
    # ...while prose idioms with dots are not filenames
    ("gate reasons with a prose idiom", ["--gate"], "mock_gate.json",
     lambda d: [r.update(reason="the required input is missing (e.g. the "
                                "dataset the pipeline reads) and the "
                                "pipeline did not run")
                for r in d["values"]], 0),
    # an exact copy of a record double-counts a checked value
    ("duplicate record appended", [], "mock_good.json",
     lambda d: d["values"].append(d["values"][0]), 1),
    # ...while a second record for a second occurrence, differing in
    # location, is how the live runs legitimately report repeats
    ("second occurrence recorded separately", [], "mock_good.json",
     lambda d: d["values"].append(
         {**[v for v in d["values"] if v.get("reported") == "6.23"][0],
          "location": "manuscript.md, Abstract"}), 0),
    # the file scan has no meaningful extension-length ceiling
    ("gate reasons citing a long-extension file", ["--gate"], "mock_gate.json",
     lambda d: [r.update(reason="appendix.markdown is missing")
                for r in d["values"]], 1),
    # a disclaimed section is not traceability
    ("locations disclaiming their section", [], "mock_good.json",
     lambda d: [r.update(location="manuscript.md, not Results")
                for r in d["values"]], 1),
    # ...while a truthful section beside a disclaimed one still locates
    ("location naming Data while disclaiming Results", [], "mock_good.json",
     lambda d: [r.update(location="manuscript.md, Data, not Results")
                for r in d["values"] if r.get("reported") == "71.48"], 0),
    # the seed digits without a seed label are an identifier, not RNG
    # provenance
    ("seed digits labeled as a build number", [], "mock_good.json",
     lambda d: d.update(environment="Python 3.11.15, stdlib only; "
                                    "build 20260816"), 1),
    # provenance for an input the pipeline never reads is fabricated
    ("data_versions entry for a fabricated input", [], "mock_good.json",
     lambda d: d["data_versions"].update(
         {"data/fabricated.csv": "sha256:" + "00" * 32}), 1),
    # ...while hashing the pipeline script itself is legitimate
    # provenance a live run recorded
    ("data_versions entry for the pipeline script", [], "mock_good.json",
     lambda d: d["data_versions"].update(
         {"analysis/run_analysis.py": "sha256:" + "ab" * 32}), 0),
    # the unavailable source is exempt by its keyed PATH, not its
    # basename: unrelated/wave2_followup.csv names a path the pipeline
    # never reads
    ("data_versions entry for a relocated wave-2 path", [], "mock_good.json",
     lambda d: d["data_versions"].update(
         {"unrelated/wave2_followup.csv": "absent - not distributed"}), 1),
    # a file a location names must be a scoped manuscript file
    ("locations citing an unscoped file", [], "mock_good.json",
     lambda d: [r.update(location=str(r["location"]).replace(
         "manuscript.md", "fabricated.tex")) for r in d["values"]], 1),
    # ...while locating by section alone is the live runs' own shape
    ("locations by bare section", [], "mock_good.json",
     lambda d: [r.update(location=str(r["location"]).replace(
         "manuscript.md, ", "")) for r in d["values"]], 0),
    # a manuscript basename inside an unscoped container is a different
    # document — the full path must match the scoped entry
    ("locations citing the manuscript under /tmp", [], "mock_good.json",
     lambda d: [r.update(location=str(r["location"]).replace(
         "manuscript.md", "/tmp/fabricated/manuscript.md"))
                for r in d["values"]], 1),
    # a command that merely prints the script name runs nothing
    ("pipeline_command wrapped in echo", [], "mock_good.json",
     lambda d: d.update(pipeline_command="echo analysis/run_analysis.py"), 1),
    # a version the keyed python3 pipeline could not run under cannot
    # describe the run
    ("environment claiming an impossible interpreter", [], "mock_good.json",
     lambda d: d.update(environment="Python 0.0, stdlib only; "
                                    "seed 20260816"), 1),
    # a one-letter extension is still a filename when the stem is real,
    # and a dotfile is a filename with no stem at all
    ("gate reasons citing a single-letter-extension file", ["--gate"],
     "mock_gate.json",
     lambda d: [r.update(reason="helper.R is missing")
                for r in d["values"]], 1),
    ("gate reasons citing a dotfile", ["--gate"], "mock_gate.json",
     lambda d: [r.update(reason=".env is missing")
                for r in d["values"]], 1),
]


def _replacing(original, replacement):
    return lambda t: t.replace(original, replacement)


def _absence_words_removed(text):
    """A gate report that names the input but never states it is absent
    must fail — 'gate' was once an accepted term and is auto-satisfied by
    the mandatory Scope and gate heading."""
    for a, b in (("not found", "located"), ("Not found", "Located"),
                 ("missing", "pending"), ("Missing", "Pending"),
                 ("unreachable", "reachable"), ("absent", "present")):
        text = text.replace(a, b)
    return text


def _absence_decoupled(text):
    """Absence language for a different file must not satisfy the check
    for the removed input. Padding keeps the decoy outside the grader's
    co-occurrence window around the last workers.csv mention."""
    return (_absence_words_removed(text)
            + "\n\nAdditional notes follow.\n\n\n"
            + "Note: wave2_followup.csv is missing from the distribution.\n")


# text-level edits of a passing prose mock and the grader verdict each
# must produce: (label, mock file, extra args, text transform, want)
MD_MUTATIONS = [
    ("misdirected boundary", "mock_good.md", [], _replacing(
     "The flagged share sits exactly on the rounding boundary; confirm the intended convention.",
     "There are no boundary concerns for the overall mean 71.48."), 1),
    ("mismatch dropped from Author decisions", "mock_good.md", [], _replacing(
     "The reported difference 6.23 disagrees with the pipeline's 6.32; decide whether to correct both occurrences.",
     "Decide whether any corrections are needed."), 1),
    ("unverifiable dropped from Author decisions", "mock_good.md", [], _replacing(
     "The 64% retention could not be verified from the distributed data; confirm it against the restricted source or state that it is not reproducible.",
     "One value remains for you to confirm against the restricted source."), 1),
    ("absence terms removed from the gate report", "mock_gate.md", ["--gate"],
     _absence_words_removed, 1),
    ("absence language only for a different file", "mock_gate.md", ["--gate"],
     _absence_decoupled, 1),
    # gate-compliant negated verdicts are prose the live runs produced,
    # not asserted classifications — they must NOT fail the report
    ("negated verdict sentence appended", "mock_gate.md", ["--gate"],
     lambda t: t + "\nThe reported 40 workers value is unverifiable, "
                   "not a match or mismatch after the failed gate.\n", 0),
    # moving a comparison out of Results leaves the contract unmet even
    # though the anchor still appears elsewhere in the report
    ("mismatch comparison moved out of Results", "mock_good.md", [],
     lambda t: t.replace(
         "- Difference of means: manuscript reports 6.23, pipeline gives 6.32 -> mismatch. Likely digit transposition.",
         "- One comparison is recorded in the appendix instead.")
     + "\nAppendix: the difference of means, manuscript 6.23 versus pipeline 6.32, "
       "is a mismatch (likely digit transposition).\n", 1),
    # a present-but-empty Results section must not fall back to searching
    # the whole report for coverage
    ("Results heading emptied and moved to the end", "mock_good.md", [],
     lambda t: t.replace("## Results\n", "## Comparisons\n") + "\n## Results\n", 1),
    # harmless prose repeating the section name after the items must not
    # shift the decisions span and fail a valid report
    ("closing sentence repeating Author decisions", "mock_good.md", [],
     lambda t: t + "\nThese conclude the Author decisions.\n", 0),
    # "40 workers" inside "140 workers" is not coverage of the 40-worker
    # claim: the prose anchors carry the JSON grader's digit guards
    ("sample-size comparison drifted to 140", "mock_good.md", [], _replacing(
     "- Sample size: manuscript reports 40 workers, pipeline n_workers gives 40 -> match.",
     "- Sample size: manuscript reports 140 workers, pipeline gives 140 -> match."), 1),
    # a negated absence claim must not satisfy the gate's absence terms
    # on the strength of the token it negates
    ("negated absence claim in gate prose", "mock_gate.md", ["--gate"],
     lambda t: t.replace(
         "required input data/workers.csv is missing from the repository",
         "input data/workers.csv is not missing; it is present and verified")
     .replace("required input not found: data/workers.csv",
              "input check: data/workers.csv is not missing"), 1),
    # prose DENYING the tie must not satisfy the boundary disclosure on
    # the strength of the words it negates
    ("negated boundary disclosure", "mock_good.md", [], _replacing(
     "The flagged share sits exactly on the rounding boundary; confirm the intended convention.",
     "The flagged share is not a rounding boundary or tie; no decision is needed."), 1),
    # a heading reading "Results omitted" credits no section
    ("section headings suffixed with omitted", "mock_gate.md", ["--gate"],
     lambda t: t.replace("## Scope and gate", "## Scope and gate omitted")
                .replace("## Method and provenance", "## Method and provenance omitted")
                .replace("## Results", "## Results omitted")
                .replace("## Author decisions", "## Author decisions omitted"), 1),
    # a prose report naming only a lookalike has not named the removed
    # input — bounded matching applies to the prose path too, which can
    # be the only grading path when the optional gate companion is absent
    ("removed input replaced by a lookalike", "mock_gate.md", ["--gate"],
     _replacing("workers.csv", "notworkers.csv"), 1),
    # the failed-gate contract puts the missing prerequisite in front of
    # the author: naming it elsewhere while Author decisions sits empty
    # does not surface the decision
    ("gate action removed from Author decisions", "mock_gate.md", ["--gate"],
     _replacing("Restore data/workers.csv or point the pipeline at the "
                "intended dataset.",
                "Decide how to proceed."), 1),
]


def md_mutation_cases():
    failures = 0
    for label, mock, extra, transform, want in MD_MUTATIONS:
        text = (TESTS / mock).read_text()
        mutated = transform(text)
        assert mutated != text, f"{mock} text changed; update MD_MUTATIONS ({label})"
        f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
        f.write(mutated)
        f.close()
        proc = run_grader("grade_report.py", extra, Path(f.name))
        Path(f.name).unlink()
        ok = proc.returncode == want
        print(f"{'PASS' if ok else 'FAIL'}  grade_report.py {' '.join(extra)} {mock} with {label}: "
              f"exit {proc.returncode}, want {want}")
        if not ok:
            print(proc.stdout)
            failures += 1
    return failures


def prepared(mock, mutate=None):
    """A temp copy of a JSON mock with skill_version pinned to the current
    VERSION — the static mocks test report semantics, not release
    arithmetic, so a version bump must not break them — plus an optional
    corruption for the adversarial cases."""
    data = json.loads((TESTS / mock).read_text())
    data["skill_version"] = VERSION
    if mutate:
        mutate(data)
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(data, f)
    f.close()
    return Path(f.name)


def run_grader(script, extra, path):
    return subprocess.run(
        [sys.executable, str(EVALS / script), *extra, str(path)],
        capture_output=True, text=True,
    )


def main():
    failures = 0
    for script, extra, mock, want in CASES:
        if mock.endswith(".json"):
            path = prepared(mock)
            proc = run_grader(script, extra, path)
            path.unlink()
        else:
            proc = run_grader(script, extra, TESTS / mock)
        ok = proc.returncode == want
        print(f"{'PASS' if ok else 'FAIL'}  {script} {' '.join(extra)} {mock}: exit {proc.returncode}, want {want}")
        if not ok:
            print(proc.stdout)
            failures += 1
    for label, extra, mock, mutate, want in MUTATIONS:
        path = prepared(mock, mutate)
        proc = run_grader("grade_json_report.py", extra, path)
        path.unlink()
        ok = proc.returncode == want
        print(f"{'PASS' if ok else 'FAIL'}  grade_json_report.py {' '.join(extra)} {mock} with {label}: "
              f"exit {proc.returncode}, want {want}")
        if not ok:
            print(proc.stdout)
            failures += 1
    failures += md_mutation_cases()
    print()
    if failures:
        print(f"{failures} grader self-test(s) FAILED")
        sys.exit(1)
    print("all grader self-tests passed")


if __name__ == "__main__":
    main()
