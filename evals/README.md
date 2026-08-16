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
| overall mean | 71.48 | 71.4825 | match |
| experienced mean | 74.64 | 74.6425 | match |
| inexperienced mean | 68.32 | 68.3225 | match |
| difference of means | 6.23 | 6.32 | mismatch (planted transposition) |
| flagged share | 13% | exactly 12.5% | match **and** a named boundary case — the exact lower-endpoint tie, where half-up prints 13 and half-even prints 12 |
| wave-2 retention | 64% | source file not distributed | unverifiable |
| permutation test | p < 0.001 | 9.999e-05 | match, checked as a predicate |
| gate case | — | dataset removed | name the unreachable input and stop; classify nothing |

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
expected classification follows from the protocol's own half-open
tolerance rule (`m - u/2 <= v < m + u/2`, lower endpoint a disclosed
boundary match, upper endpoint excluded), and that the gate case fails
loudly. This is the CI-safe layer: if it fails, the fixture has drifted
and the agent eval is meaningless.

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

## Honesty notes

- Grading is keyword-based and coarse: it anchors on the manuscript's
  value strings and checks the classification word nearby. Prose that
  legitimately references another target's verdict on the same line
  ("not as a match or mismatch", cross-value arithmetic) surfaces as WARN,
  not FAIL. A FAIL deserves a human read of the report before it is
  believed. Exact grading arrives with the machine-readable report
  (TASKS.md item 5).
- A PASS on the planted defects is meaningful despite that coarseness: a
  report that calls the transposed 6.23 a match, resolves the 12.5%
  boundary tie silently, or produces a value for the undistributed wave-2
  file cannot pass.
- The fixture is synthetic and says so in its own manuscript, AGENTS.md,
  and README. Do not reuse it as an example of real results.
