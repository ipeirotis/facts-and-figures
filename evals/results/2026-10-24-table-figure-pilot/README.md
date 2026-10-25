# Table and figure pilot: 2026-10-24

**Numerical checks: 6/6 correct. Overall: FAIL under the shared-requirement hard gate.**

This is the user's local Claude Code run, started at 2026-10-25 00:43:37 UTC
(October 24 in New York), using `claude-sonnet-5-5`, CLI 2.1.309 and skill
commit `5609c6465de6389044839f98da08b15fb6fe84ed`. It is not a GitHub Actions run.

Claude correctly checked both table cells, both printed graph labels, and
both SVG bar heights. Group A is correct at 80.0. Group B is reported and
plotted at 65.0, while the executed pipeline produces 60.0. The chart's
encoded geometry was inspected separately from its labels.

## Results and evidence

- [Grading and metrics](grading.json): manual review plus deterministic
  checks against the external key, data and uploaded integrity snapshots.
- [Claude's final report](report.md) and [numeric JSON](verification-report.json).
- [Public tool trace](claude-events.jsonl): calls and returned outputs, with
  local identity information and model thinking blocks removed.
- [Run metadata](run-metadata.json), [final CLI result](claude-result.json),
  [stderr](claude-stderr.txt), and [exact prompt](prompt.txt).
- [Inputs](inputs/), [generated outputs](outputs/), and [answer key](answer-key.json).
- [Before](workspace-before.txt) and [after](workspace-after.txt) snapshots.
- [Publication/redaction record](publication.json), including the checksum
  of the original ZIP supplied privately in the conversation.

## Shared checks

**I. Provenance: FAIL for the complete report.** All six scored values have
logged computation/extraction, source hashes and environment information.
However, the final report additionally states A–B gaps of 15 and 20 without
a logged command/output computing those new derived results. The skill's
master rule requires producing commands for reported numerical results.

**II. Preserve originals: PASS on the available evidence.** Before/after
snapshots agree and all uploaded input files match their recorded hashes.
These are end-state checks, not proof against transient changes.

**III. Output/cleanup: FAIL for marker lifecycle.** Retained generated files
are in the proposal directory and no marker remains at the end. But the
trace shows `rm facts-and-figures-out/.active` before a later Bash call writes
`verification-report.json`. The guard must remain armed for every write.
An end-state-only cleanup check would miss this failure.

The final report also claims a pre-execution plan without an externally
recorded complete inventory/tolerance before computation, and the B-bar
tolerance is anchored on computed 60 rather than submitted 65. These are
recorded in the grading notes; the numeric verdict itself is still correct.

## Usage

- Wall time: **49.428 seconds**; Claude-reported duration: 48.118 seconds.
- Input: 14 uncached + 27,842 cache-creation + 127,677 cache-read tokens.
- Output: **5,652 tokens**, including reported thinking-token usage.
- CLI list-price cost estimate: **$0.180684**. This is not a subscription
  billing amount. Cache reads include repeated input across turns.

## Limits and reproduction

One synthetic SVG case and one with-skill run cannot establish general graph
verification reliability. There is no no-skill baseline, repeated-run
estimate, or raster/PDF rendering evaluation here. The answer key was not
copied into the workspace; the local process was not an OS sandbox. The
trace shows no answer-key lookup. The broader local skills/plugins listed
by Claude's initialization are preserved in metadata for reproducibility.

To make a new run, check out the exact skill commit above and run
`python3 evals/run_table_figure_eval.py` with a locally signed-in Claude Code.
This runner collects evidence; the grade here was reviewed after upload,
not produced by the toy-paper automatic graders. Source files/results have
not been modified to fix any model mistakes. Personal paths and identifiers
were redacted before public posting; the original ZIP was not republished.
