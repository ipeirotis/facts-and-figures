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

## Open

- [ ] **3. Eval suite.** A fixture paper repository with a known-good
  pipeline, one deliberately wrong manuscript number, one rounding case on
  the tie boundary, and one value whose data source is unreachable —
  exercising match, mismatch, the tie convention, unverifiable, and the
  gate. `AGENTS.md` already requires every rule to be checkable by reading
  the output; the evals turn that requirement into a harness, and settle
  empirically whether the subagent form follows the protocol better than the
  inline form. *Done when:* the fixture and expected classifications live
  under `evals/` and a documented command runs the comparison.

- [ ] **4. Plugin packaging.** Bundle skill + agent + hook as a Claude Code
  plugin so the three install as one versioned unit and the hook registers
  without hand-editing `settings.json`. Keep the plain-skill install path
  working for non-Claude hosts (`agents/openai.yaml` stays).
  *Done when:* the plugin manifest exists, installing it activates all three
  pieces, and `README.md` documents both install paths.

- [ ] **5. Headless / CI mode.** Emit a machine-readable report (one record
  per value: target, status, producing command) alongside the prose
  contract, then run verification on manuscript pushes via the Claude Agent
  SDK. Depends on 3 (evals gate the report format) and is where the agent
  form pays off most. *Done when:* a CI workflow verifies the fixture repo
  from task 3 end to end.
