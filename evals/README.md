# evals

The eval suite for facts-and-figures. Two layers: a deterministic fixture
check that runs anywhere without an LLM, and an agent-in-the-loop eval that
runs the skill against the fixture and grades its report.

## The fixture

`fixtures/toy-paper/` is a synthetic paper repository: a manuscript, a
40-row dataset, and a deterministic stdlib-only pipeline
(`python3 analysis/run_analysis.py`). Its numbers are planted to exercise
every classification the protocol defines:

| Target | Manuscript says | Pipeline gives | Expected |
|---|---|---|---|
| sample size | 40 workers | 40 | match |
| group split | 20 / 20 | 20 and 20 | match |
| overall mean | 71.48 | 71.4825 | match |
| experienced mean | 74.64 | 74.6425 | match |
| inexperienced mean | 68.32 | 68.3225 | match |
| difference of means | 6.23 | 6.32 | mismatch (planted transposition) |
| flagged share | 13% | exactly 12.5% | match **and** a named boundary case — the exact lower-endpoint tie, where half-up prints 13 and half-even prints 12 |
| permutation count | 10,000 | 10000 | match |
| wave-2 retention | 64% | source file not distributed | unverifiable |
| permutation test | p < 0.001 | 9.999e-05 | match, checked as a predicate |
| gate case | — | dataset removed | name the unreachable input; classify nothing as match or mismatch — a blanket unverifiable naming the missing input is the correct outcome |

The dataset was constructed in integer cents so the documented values are
exact, not approximate: group sums 1492.85 and 1366.45 give the means
above by construction, and 5 flagged workers out of 40 give exactly 12.5%.
`expected.json` is the answer key.

## Layer 1: deterministic fixture check

```bash
python3 evals/check_fixture.py
```

No LLM. Runs the pipeline in a scratch copy and asserts that every
documented true value is what the pipeline actually produces, that each
expected classification follows from the protocol's own tolerance rule
(half-open on magnitudes: `|m| - u/2 <= |v| < |m| + u/2` with matching
sign, the lower magnitude endpoint a disclosed boundary match, the upper
excluded), and that the gate case fails loudly. This is the CI-safe layer:
if it fails, the fixture has drifted and the agent eval is meaningless.

## Layer 2: agent-in-the-loop eval

```bash
evals/run_agent_eval.sh
```

Prepares two scratch workspaces (fixture intact; fixture with the dataset
removed), installs the skill and the write-boundary hook into each, runs
Claude Code headless when the `claude` CLI is available, and grades the
reports:

```bash
python3 evals/grade_report.py <workspace>/report.md          # verification case
python3 evals/grade_report.py --gate <workspace>/report.md   # gate case
```

The workspaces receive the fixture and the skill's runtime files only —
never this directory, which contains the answer key.

The verification case is graded twice, with a clear division of labor:
`grade_report.py` grades the prose structurally — the four sections of the
return contract, coverage of every target, the boundary-tie disclosure —
and `grade_json_report.py` grades the machine-readable companion the skill
writes to `facts-and-figures-out/verification-report.json` exactly:
classifications, boundary flags, computed values, and the conditional
fields (tolerance, producing command, reason) on the record that carries
each value. A missing JSON companion is itself a failure, since the
workspace is writable and `references/verification-report.md` mandates it
there. On a failed gate the companion is optional (the prose naming the
missing input is the deliverable), but when written it is graded under
`--gate`: every record unverifiable with a reason, nothing computed, the
missing input named.

## Table and figure verification starter

`fixtures/table-figure-paper/` contains a separate synthetic manuscript with
Table 1 and a submitted SVG bar chart, source data, and a stdlib-only
pipeline that writes correct table/figure outputs to an explicitly named
new directory. Group A's mean is 80.0 and is correct in both artifacts;
group B's mean is 60.0 but is deliberately reported/plotted as 65.0.
`table-figure-expected.json` holds the prompt and external answer key, with
separate expectations for cells, printed graph labels and bar geometry.

Run `python3 -B evals/test_table_figure_fixture.py -v` to verify the test
materials, pipeline execution, exact SVG encoding and input preservation.
This does not evaluate Claude. For an agent pilot, copy only this fixture
and the installed skill runtime to a fresh workspace, keep the answer key
outside it, and submit the key's prompt. Review the four-section report and
numeric JSON against the key, including all three shared requirements.
The existing `run_agent_eval.sh` and toy-paper graders still run their
original cases; they do not automatically run or grade this new fixture.
No end-to-end agent score is claimed until that pilot is actually run.

For a locally signed-in Claude Code, run this from a regular terminal
(macOS, Linux or WSL), not inside an existing Claude session:

```bash
python3 evals/run_table_figure_eval.py
```

It creates a fresh workspace outside the checkout, installs only runtime
skill files and the hook, and calls `claude -p` with a fresh conversation.
It uses the existing login rather than forwarding `ANTHROPIC_API_KEY`.
The run pre-approves Bash on this synthetic fixture; the write hook guards
file edits but is not an OS sandbox. Personal MCP servers are excluded and
only the built-in file/shell tools are enabled. Use `--model` to select a
model (default `sonnet`; the actual model is captured in the trace).

The runner saves the prompt, full stream trace, final Markdown report,
Claude's JSON result, usage/time/model metadata, input hashes, before/after
workspace snapshots and generated outputs. A ZIP is created in Downloads
and its full path printed, including on authentication/invocation failure.
`--output-dir` selects a new destination outside the checkout;
`--prepare-only` prepares files without calling Claude. Nothing is uploaded.
Review the ZIP before sharing. Semantic grading and complete provenance
review are pending; a completed run is not itself a passing eval.
The answer key is excluded from the workspace, but Bash is not isolated
from the rest of the machine; this is a local pilot, not a sandboxed benchmark.

Test runner plumbing without a model with
`python3 -B evals/test_table_figure_runner.py -v`; its fake CLI is explicitly
a stub and its outputs are not Claude evaluation results.

## CI

`.github/workflows/ci.yml` runs the deterministic layer plus the repo's
consistency checks on every push and pull request. `.github/workflows/agent-eval.yml`
runs the full agent eval on pushes to `main` that touch the skill's runtime
files (and on manual dispatch); it needs the `ANTHROPIC_API_KEY` secret and
skips with a notice when the secret is absent. The job is bound to the
`agent-eval` deployment environment: store the key as an environment secret
there, and if the repository has collaborators, use the environment's
protection rules (deployment branch policy or required reviewers) to keep a
manual dispatch from an unreviewed branch away from the key — a plain
repository secret would reach any branch anyone with write access dispatches.

## Honesty notes

- Prose verdicts are not graded, by design. Two live runs each broke
  keyword verdict-classification in a different way (verdict-grouped
  tables whose rows carry no verdict word; discussion lines like "not a
  mismatch" quoting other targets), so verdicts are graded exactly on the
  machine-readable companion, and the prose is held to structure,
  coverage, and the boundary disclosure. The schema requires the two
  reports to agree; a disagreement is a defect of the run that prose
  keyword-matching cannot reliably detect.
- A PASS on the planted defects is meaningful: a JSON report that calls
  the transposed 6.23 a match, resolves the 12.5% boundary tie silently,
  or produces a value for the undistributed wave-2 file cannot pass.
- The fixture is synthetic and says so in its own manuscript, AGENTS.md,
  and README. Do not reuse it as an example of real results.
