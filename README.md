# paper-analyst

A reproducibility-first agent skill for checking manuscript numbers against a repository's analysis pipeline, re-rendering figures from unchanged data, and running analyses explicitly specified by the author.

## Install

Copy or clone this repository into your agent's skills directory, for example:

```bash
git clone https://github.com/ipeirotis/paper-analyst.git ~/.agents/skills/paper-analyst
```

Then ask the agent to verify a manuscript number, regenerate a named figure, or run a precisely named analysis. The skill requires the author's data and code plus shell access; generative tasks also require write access.

## Safety model

The skill logs provenance for every result, never modifies existing code, data, figures, or manuscript files, and never searches specifications for a favorable result. Generated work stays in a proposal directory until the author adopts it.
