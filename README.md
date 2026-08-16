# facts-and-figures

A reproducibility-first agent skill for checking manuscript numbers against a repository's analysis pipeline, re-rendering figures from unchanged data, and running analyses explicitly specified by the author.

> Renamed from `paper-analyst` in v0.2.0. The skill's identifier is now `facts-and-figures`.

## Install

### As a Claude Code plugin (recommended)

The repository is its own plugin marketplace. One install activates all
three pieces — the skill, the isolated-run subagent, and the write-boundary
hook — and updates arrive when the plugin version changes:

```
/plugin marketplace add ipeirotis/facts-and-figures
/plugin install facts-and-figures@facts-and-figures
```

### As a plain skill (any host)

Copy or clone this repository into your agent's skills directory, for example:

```bash
git clone https://github.com/ipeirotis/facts-and-figures.git ~/.agents/skills/facts-and-figures
# or, for Claude Code:
git clone https://github.com/ipeirotis/facts-and-figures.git ~/.claude/skills/facts-and-figures
```

With this path the subagent and hook are separate opt-ins, documented below.

Then ask the agent to verify a manuscript number, regenerate a named figure, or run a precisely named analysis. The skill requires the author's analysis code plus reachable data and shell access; generative tasks also require write access.

[`cloud-bootstrap`](https://github.com/ipeirotis/cloud-bootstrap) is an optional runtime prerequisite. Everything local works without it; it is required only to activate encrypted cloud credentials, which this skill detects but never decrypts itself.

### Optional: run it as an isolated subagent (Claude Code)

```bash
cp agents/claude-code/facts-and-figures.md ~/.claude/agents/   # or <project>/.claude/agents/
```

Then delegate: *"Use the facts-and-figures agent to verify the numbers in Table 2."* The subagent runs the same protocol in its own context. That isolation is an integrity feature, not just hygiene: the run receives only the pinned request, never the surrounding conversation where the author may have said what they hope the numbers show — the contamination the no-forking-paths rule exists to prevent. It also keeps pipeline logs out of the main conversation and allows parallel runs, one per figure or section. The wrapper carries no protocol of its own; it locates the installed skill and follows `SKILL.md`.

### Optional: enforce the write boundary mechanically (Claude Code)

Register `hooks/write-boundary.sh` as a `PreToolUse` hook in the manuscript repository's `.claude/settings.json`, adjusting the path to where the skill is installed:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/skills/facts-and-figures/hooks/write-boundary.sh"
          }
        ]
      }
    ]
  }
}
```

While a run is active (the skill creates `facts-and-figures-out/.active` when its gates pass, and removes it at teardown), the hook denies file edits outside the proposal directory; without the marker it is inert, so ordinary editing sessions in the same repository are unaffected. If the author named a different proposal directory, set `FACTS_AND_FIGURES_OUT` to it. This is a guardrail, not a sandbox — writes made through shell commands are not intercepted, and the skill's master rule remains the primary control.

## What it does

| Capability | Produces | Requires |
|---|---|---|
| Verify reported numbers | a match / mismatch / unverifiable classification for every number in scope | data, analysis code, shell |
| Regenerate a figure | a re-rendered figure proposed beside the original | the above, plus write access |
| Run a named analysis | one pinned specification, run and reported in full | the above, plus write access |

## Safety model

The skill logs provenance for every result, never modifies existing code, data, figures, or manuscript files, and never searches specifications for a favorable result. Generated work stays in a proposal directory (`facts-and-figures-out/` by default) until the author adopts it.

## Layout

```
SKILL.md                            entry point: master rule, capabilities, gates, output
references/analysis-integrity.md    the protocol and integrity norms
references/figure-design.md         what a figure re-render may and may not change
references/compute-environment.md   local-first execution and cloud provenance
agents/claude-code/facts-and-figures.md   subagent wrapper for isolated runs
agents/openai.yaml                  display metadata for non-Claude agent hosts
hooks/write-boundary.sh             PreToolUse guard for the write boundary
hooks/hooks.json                    plugin hook registration for the guard
.claude-plugin/                     plugin and marketplace manifests
.github/workflows/                  CI: deterministic checks and the agent eval
evals/                              eval suite: fixture paper repo, answer key, graders
AGENTS.md                           guidance for agents editing this repository
TASKS.md                            development roadmap
```

## Machine-readable report and CI

Verification writes `facts-and-figures-out/verification-report.json`
alongside the prose report whenever the session can write — one record per
manuscript value with its classification, computed value, tolerance, and
producing command (`references/verification-report.md` owns the schema).
That is what makes verification scriptable: CI can parse conclusions
instead of prose.

To verify a paper repository on every push, install the skill in that
repository (`.claude/skills/facts-and-figures/`), add an `ANTHROPIC_API_KEY`
secret, and adapt:

```yaml
name: verify-manuscript
on:
  push:
    branches: [main]
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: {node-version: 22}
      - run: npm install -g @anthropic-ai/claude-code
      - name: run verification
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          claude -p "Using the facts-and-figures skill installed under .claude/skills/, verify every number reported in the manuscript against this repository's analysis pipeline. Produce the skill's full four-section report." \
            --permission-mode acceptEdits --allowedTools Bash | tee verification-report.md
      - name: fail on mismatches
        run: |
          python3 -c "
          import json, sys
          r = json.load(open('facts-and-figures-out/verification-report.json'))
          bad = [v for v in r['values'] if v['classification'] != 'match']
          for v in bad: print(v['classification'], v['reported'], '-', v['location'])
          sys.exit(1 if bad else 0)"
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: verification
          path: |
            verification-report.md
            facts-and-figures-out/verification-report.json
```

The gate on mismatches is the author's policy choice: some papers carry
legitimately unverifiable values (data agreements, restricted sources), so
you may prefer failing only on `mismatch` and reporting `unverifiable`
counts instead. This repository's own CI (`.github/workflows/`) runs the
deterministic eval layer on every push and the full agent eval against the
fixture paper on pushes to `main`.

## Evals

`evals/` tests the skill against a synthetic paper repository with planted
defects: a transposed number, an exact rounding-boundary tie, a value whose
data source is not distributed, and a gate case with the dataset removed.
Two commands:

```bash
python3 evals/check_fixture.py    # deterministic, no LLM: fixture self-check
evals/run_agent_eval.sh           # headless Claude Code against the fixture, graded
```

See `evals/README.md` for the target table and grading caveats.

## Related

- [`blue-pencil`](https://github.com/ipeirotis/blue-pencil) — the editorial skill this protocol was extracted from. Use it for prose; use this for numbers.
- [`cloud-bootstrap`](https://github.com/ipeirotis/cloud-bootstrap) — owns cloud credential setup. This skill detects and uses credentials it has already placed in a repository, and never creates or modifies them.

## License

MIT
