# TASKS.md — development roadmap

The working roadmap for this skill, in priority order. `AGENTS.md` governs how
each item is implemented; `CHANGELOG.md` records what shipped. An item is done
when its definition of done holds, not when code for it exists.

## v0.3.0

- [x] **1. Enforce the write boundary mechanically.** The skill's headline
  promise — never modify the author's manuscript, data, figures, or analysis
  code — was prose only. `hooks/write-boundary.sh` is a Claude Code
  `PreToolUse` guard that, while a run marker
  (`facts-and-figures-out/.active`) exists, denies `Write`/`Edit`/
  `MultiEdit`/`NotebookEdit` outside the proposal directory. It is armed by
  the run and inert otherwise, fails open when it cannot parse its input, and
  is a guardrail rather than a sandbox: writes made through shell commands
  are not covered, and the master rule remains the primary control.
  *Done when:* the hook ships with registration instructions in `README.md`,
  `SKILL.md` pins the marker's lifecycle (created when the gates pass,
  removal confirmed under teardown in Return), and the deny path and the
  inert path are both exercised against sample payloads.

- [x] **2. Ship a subagent wrapper for isolated runs.**
  `agents/claude-code/facts-and-figures.md` runs the protocol in its own
  context. Isolation is an integrity feature here, not hygiene: the subagent
  receives only the pinned request, never the surrounding conversation where
  the author may have said what they hope the numbers show — the
  contamination the no-forking-paths rule exists to prevent. It also keeps
  pipeline logs out of the main context and allows parallel fan-out (one run
  per figure or manuscript section). The wrapper points at `SKILL.md` and
  never restates the protocol; it adds only the agent-mode adaptations
  (a mid-run question becomes an early return).
  *Done when:* the agent file ships with install instructions, its tool list
  excludes web access, and its body survives the `AGENTS.md` invariant that
  wrappers point rather than restate.

## v0.4.0

- [x] **3. Eval suite.** `evals/` holds a synthetic fixture paper repository
  (`fixtures/toy-paper/`: manuscript, 40-row dataset, deterministic
  stdlib-only pipeline) whose numbers are planted to exercise every
  classification the protocol defines: three clean matches, a transposed
  mismatch, an exact lower-endpoint rounding tie (pipeline 12.5% against a
  reported 13%), an unverifiable value whose source file is not
  distributed, a `p < 0.001` bound checked as a predicate, and a gate case
  with the dataset removed. Two layers: `check_fixture.py` (deterministic,
  no LLM, CI-safe — asserts the pipeline reproduces the documented values
  and that each expected classification follows from the protocol's own
  tolerance rule) and `run_agent_eval.sh` (headless Claude Code against
  scratch workspaces, graded by `grade_report.py`; keyword grading until
  item 5's machine-readable report). `expected.json` is the answer key and
  never enters an eval workspace.

## v0.5.0

- [x] **4. Plugin packaging.** The repository root is the plugin root: a
  single-skill plugin keeps `SKILL.md` where it is, so no restructuring and
  no drift. `.claude-plugin/plugin.json` names the subagent wrapper
  explicitly, `hooks/hooks.json` registers the write-boundary guard via
  `${CLAUDE_PLUGIN_ROOT}`, and `.claude-plugin/marketplace.json` makes the
  repo its own marketplace (`/plugin marketplace add ipeirotis/facts-and-figures`,
  then `/plugin install facts-and-figures@facts-and-figures`). One install
  activates skill, agent, and hook; updates ship by bumping `plugin.json`'s
  version, which the release checklist and CI now enforce alongside
  `VERSION` and `SKILL.md`. The plain-skill install path is unchanged, and
  `claude plugin validate . --strict` passes.

- [x] **5. Headless / CI mode.** Verification now writes a machine-readable
  companion, `facts-and-figures-out/verification-report.json` — one record
  per manuscript value with classification, computed value, tolerance, and
  producing command; `references/verification-report.md` owns the schema
  and `SKILL.md`'s Return section mandates it whenever the session can
  write. `evals/grade_json_report.py` grades it exactly (classifications,
  boundary flags, computed values), alongside the keyword grader for the
  prose. CI: `ci.yml` runs the deterministic layer, grader self-tests
  (`evals/test_graders.py` over `evals/tests/`), version-consistency and
  dangling-reference checks, and plugin validation on every push;
  `agent-eval.yml` runs the full headless eval against the fixture on
  pushes to `main` (requires the `ANTHROPIC_API_KEY` secret, skips with a
  notice without it). `README.md` carries a template workflow for running
  verification on a real paper repository's pushes.
