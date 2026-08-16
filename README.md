# facts-and-figures

A reproducibility-first agent skill for checking manuscript numbers against a repository's analysis pipeline, re-rendering figures from unchanged data, and running analyses explicitly specified by the author.

> Renamed from `paper-analyst` in v0.2.0. The skill's identifier is now `facts-and-figures`.

## Install

Copy or clone this repository into your agent's skills directory, for example:

```bash
git clone https://github.com/ipeirotis/facts-and-figures.git ~/.agents/skills/facts-and-figures
# or, for Claude Code:
git clone https://github.com/ipeirotis/facts-and-figures.git ~/.claude/skills/facts-and-figures
```

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
hooks/write-boundary.sh             optional PreToolUse guard for the write boundary
evals/                              eval suite: fixture paper repo, answer key, graders
AGENTS.md                           guidance for agents editing this repository
TASKS.md                            development roadmap
```

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
