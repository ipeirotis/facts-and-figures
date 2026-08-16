# AGENTS.md — the facts-and-figures skill repository

This file governs work **on the skill**: editing, reviewing, or releasing the
files in this repository. It is not part of the skill's runtime instructions,
and it is not paper context.

## Precedence: this file versus the manuscript repository's AGENTS.md

Two files named `AGENTS.md` can be in play at once, and confusing them is the
failure this section exists to prevent.

| File | Belongs to | Role |
|---|---|---|
| **This file** | the `facts-and-figures` repository | instructions for agents editing the skill |
| The manuscript repository's `AGENTS.md` | the author's paper | input to the skill: the `<paper_context>` block (venue, audience, thesis, revision stage) |

The rules:

1. **Nearest owner wins.** This file applies only to work inside this
   repository. When the skill is installed under a manuscript repository
   (vendored, submoduled, or symlinked into `.claude/skills/`), this file
   still describes only the skill's own directory and never governs the
   manuscript around it.
2. **The manuscript's `AGENTS.md` is read-only input.** The skill reads its
   `<paper_context>` block and never edits, extends, or reformats it. A
   change the author needs to make there is an item in `Author decisions`.
3. **Never install this file into a paper repository.** Installing the skill
   must not create or overwrite an `AGENTS.md` next to the author's
   manuscript. If a paper repository needs one, the author writes it.
4. **If you are in a paper repository and see only one `AGENTS.md`, it is the
   author's.** Read it for context; do not treat it as guidance about how to
   edit the skill.

## What this repository is

A single-purpose skill that verifies manuscript numbers against the
repository's own analysis pipeline, regenerates named figures from the same
data, and runs analyses the author names. It executes the author's code and
authors new files only in a proposal directory; it never edits a manuscript,
a dataset, or the author's analysis code.

```
SKILL.md                            entry point, always loaded: master rule,
                                    capability selection, gates, output contract
references/analysis-integrity.md    the protocol: three capabilities, five
                                    verification steps, integrity norms
references/figure-design.md         capability 2: what a re-render may change
references/compute-environment.md   local-first execution, cloud-bootstrap
                                    detection, provenance for remote runs
agents/openai.yaml                  display metadata for non-Claude agent hosts
```

## Invariants when editing

- **`SKILL.md` stays thin.** It is loaded on every invocation. Detail belongs
  in `references/`; `SKILL.md` says which reference owns what and when to
  read it.
- **No dangling references.** Every `references/*.md` path named in any file
  must exist in this repository. This skill was extracted from a larger one
  and inherited citations to files that did not come with it; do not
  reintroduce that. Check before committing:
  ```bash
  grep -rhoE 'references/[a-z0-9-]+\.md' -- SKILL.md README.md AGENTS.md references/ \
    | sort -u | while read -r p; do [ -f "$p" ] || echo "MISSING: $p"; done
  ```
  `CHANGELOG.md` is excluded on purpose: its history names files that once
  lived elsewhere. Name those without the `references/` prefix.
- **The name is consistent everywhere.** `facts-and-figures` in `SKILL.md`
  frontmatter, `README.md`, `agents/openai.yaml`, and the
  `facts-and-figures-out/` proposal directory. The skill was called
  `paper-analyst` before v0.2.0; no live reference to the old name should
  remain.
- **The master rule outranks new material.** Never assert unverified
  substance. Any addition that would have the skill report a number it did
  not compute, widen a rounding tolerance after seeing a gap, choose a
  specification after seeing results, or edit the author's files is a
  regression however useful it looks.
- **Additions state a rule, not a preference.** Each one should be checkable
  by reading the output: a reader can tell whether it was followed.

## Releasing

Update `VERSION`, the `metadata.version` field in `SKILL.md`, and
`CHANGELOG.md` together. Versions follow semantic versioning: a changed
output contract, a renamed reference file, or a new hard gate is a major or
minor bump, not a patch.
