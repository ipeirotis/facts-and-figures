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
AGENTS.md                           guidance for agents editing this repository
```

## Related

- [`blue-pencil`](https://github.com/ipeirotis/blue-pencil) — the editorial skill this protocol was extracted from. Use it for prose; use this for numbers.
- [`cloud-bootstrap`](https://github.com/ipeirotis/cloud-bootstrap) — owns cloud credential setup. This skill detects and uses credentials it has already placed in a repository, and never creates or modifies them.

## License

MIT
