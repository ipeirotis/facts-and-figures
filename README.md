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

Then delegate: *"Use the facts-and-figures agent to verify the numbers in Table 2."* The subagent runs the same protocol in its own context. That isolation is an integrity feature, not just hygiene: the run receives only the pinned request, never the surrounding conversation where the author may have said what they hope the numbers show — the contamination the no-forking-paths rule exists to prevent. It also keeps pipeline logs out of the main conversation. Runs can go in parallel only across separate checkouts: within one checkout, the single run marker `facts-and-figures-out/.active` coordinates the write boundary, so concurrent runs would fight over it and over `verification-report.json`. The wrapper carries no protocol of its own; it locates the installed skill and follows `SKILL.md`.

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
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/skills/facts-and-figures/hooks/write-boundary.sh"
          }
        ]
      }
    ]
  }
}
```

While a run is active (the skill creates `facts-and-figures-out/.active` whenever the session can write and the run will author anything — a failed gate that still writes its optional companion included — and removes it at teardown), the hook denies file edits outside the proposal directory; without the marker it is inert, so ordinary editing sessions in the same repository are unaffected. If the author named a different proposal directory, the marker's single line carries its path and the hook guards that directory — the marker is the only channel for a custom directory, and its creation is refused when the named directory already exists and is not empty. This is a guardrail, not a sandbox — writes made through shell commands are not intercepted, and the skill's master rule remains the primary control.

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
# the job executes the repository's own manuscript and pipeline content
# with Bash pre-approved, so it runs with read-only repo access
permissions:
  contents: read
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          # checkout persists its token in .git/config by default; the
          # pre-approved Bash commands must not inherit a credential that
          # could push
          persist-credentials: false
      - uses: actions/setup-node@v4
        with: {node-version: 22}
      - run: npm install -g @anthropic-ai/claude-code
      - name: register the write-boundary hook
        # a plain-skill install leaves the hook a separate opt-in, so the
        # workflow registers it itself — without this the run has only
        # the skill's own discipline, not the mechanical guard. If your
        # repository already carries a .claude/settings.json, merge the
        # registration from the hook section above instead of this step
        run: |
          mkdir -p .claude
          if [ ! -f .claude/settings.json ]; then
            cat > .claude/settings.json <<'JSON'
          {
            "hooks": {
              "PreToolUse": [
                {
                  "matcher": "Write|Edit|MultiEdit|NotebookEdit",
                  "hooks": [
                    {
                      "type": "command",
                      "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/skills/facts-and-figures/hooks/write-boundary.sh"
                    }
                  ]
                }
              ]
            }
          }
          JSON
          fi
      - name: run verification
        shell: bash
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          # strip the key from the environment the pre-approved Bash
          # commands inherit; Claude Code keeps it for its own API calls.
          # This is hygiene against accidental reads, not isolation: a
          # hostile same-user process can still read a parent's
          # environment via /proc, so a pipeline you do not trust belongs
          # in a container or a separate user. Drop only if your pipeline
          # itself needs scrubbed credentials.
          CLAUDE_CODE_SUBPROCESS_ENV_SCRUB: "1"
        run: |
          # redundant with the declared shell's -eo pipefail, kept
          # explicit so a failing claude exit still fails the step when
          # this block is copied into a workflow that drops shell: bash
          set -o pipefail
          # the proposal root must be a real directory or absent: a
          # symlinked or non-directory root would route this cleanup —
          # and the gate's later read — into whatever it points at, so a
          # stale all-match companion behind a symlink could pass the
          # gate without this run writing anything. Fail the run instead
          # of skipping
          if [ -L facts-and-figures-out ] || { [ -e facts-and-figures-out ] && [ ! -d facts-and-figures-out ]; }; then
            echo "facts-and-figures-out exists and is not a real directory" >&2
            exit 1
          fi
          # a committed or leftover companion from an earlier run must
          # not satisfy the gate below if this run fails to write its own
          rm -f facts-and-figures-out/verification-report.json
          # the prose capture goes to RUNNER_TEMP, not the checkout root:
          # a shell redirect bypasses the write-boundary hook, and a paper
          # repository may own a file by this name
          claude -p "Using the facts-and-figures skill installed under .claude/skills/, verify every number reported in the manuscript against this repository's analysis pipeline. Produce the skill's full four-section report." \
            --permission-mode acceptEdits --allowedTools Bash | tee "$RUNNER_TEMP/verification-report.md"
      - name: fail on mismatches
        run: |
          python3 -c "
          import json, sys
          r = json.load(open('facts-and-figures-out/verification-report.json'))
          # shape before policy: a malformed companion must not pass the
          # gate on records that carry a classification and nothing else
          missing = [k for k in ('schema', 'manuscript_files', 'pipeline_command',
                                 'environment', 'data_versions') if not r.get(k)]
          vals = r.get('values') or []
          # an empty report verified nothing; completeness beyond that is
          # your spot check against the manuscript, since a real paper has
          # no answer key
          if missing or not vals:
              print('malformed report:', missing or 'no value records'); sys.exit(1)
          shapeless = [v for v in vals
                       if not (v.get('location') and v.get('reported')
                               and v.get('classification'))
                       or (v.get('classification') in ('match', 'mismatch')
                           and (v.get('computed') is None or not v.get('tolerance')
                                or not v.get('producing_command')))
                       or (v.get('classification') == 'unverifiable'
                           and not v.get('reason'))]
          if shapeless:
              print('records missing required fields:', shapeless[:2]); sys.exit(1)
          bad = [v for v in vals if v['classification'] != 'match']
          for v in bad: print(v['classification'], v['reported'], '-', v['location'])
          print(f'{len(vals)} values checked, {len(bad)} not a clean match')
          sys.exit(1 if bad else 0)"
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: verification
          path: |
            ${{ runner.temp }}/verification-report.md
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
