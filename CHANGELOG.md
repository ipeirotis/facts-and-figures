# Changelog

All notable changes to facts-and-figures (called paper-analyst before v0.2.0) are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/). Versions use [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-08-15

Makes the skill self-contained. Extracted from `blue-pencil`, it carried citations to reference files that did not come with it: figure regeneration pointed at `blue-pencil`'s `edit-checks.md` for its design guidance, and the protocol appealed to a master rule the standalone `SKILL.md` never stated. Both are now resolved inside this repository, and the skill gains the two things the extraction dropped that it actually needed: the manuscript-context step and an explicit account of where the analysis runs.

### Added

- `references/figure-design.md`, replacing the inherited dependency on `blue-pencil`'s `edit-checks.md`. It states the figures-as-primary-text standard, an explicit two-column split of what a re-render may change (color, ordering, labeling, scale formatting) against what it may not (data path, sample, transformations, estimates, added smoothing, truncated axes), an ordered presentation-improvement procedure, and the value-parity confirmation a re-render must pass before being proposed.
- `references/compute-environment.md`. Local-first execution with a measure-before-you-move rule; detection of credentials `cloud-bootstrap` has already placed in the repository (`.cloud-config.json`, `.cloud-credentials.<email>.enc`, `*_CREDENTIALS_KEY`) with a table distinguishing the four states, three of which are not "the cloud is available"; four gates before a remote run (author consent, a destination the project already uses, bounded cost, preserved reproducibility); and the extra provenance a remote run carries — environment and image digest, region and job ID, a pinned data snapshot, seeds and reduction order. Credential creation, rotation, and IAM stay with `cloud-bootstrap`.
- `SKILL.md` states the master rule (never assert unverified substance) and its two corollaries directly, so `references/analysis-integrity.md`'s appeal to it resolves.
- `SKILL.md` gains "Load the manuscript context" (the `<paper_context>` block in the manuscript repository's `AGENTS.md`, `CLAUDE.md`, or `paper-meta.md`, plus the include-graph rule for choosing the manuscript file set) and "Choose where the analysis runs".
- `AGENTS.md` for this repository, carrying the precedence rule that separates it from the manuscript repository's `AGENTS.md`: this file governs the skill's own directory, the manuscript's is read-only input, and installing the skill never writes one next to an author's paper. It also carries the repository layout, the editing invariants, and a shell one-liner that fails on a dangling `references/` citation.
- A rounding-tolerance rule in verification step 5: state the tolerance before comparing, set it from the manuscript's own reported precision, and never widen it to convert a mismatch into a match.
- Environment capture (interpreter and package versions, seeds) in verification step 4 and in the provenance norm, for local runs as well as remote ones.
- `VERSION`, `CHANGELOG.md`, and a `.gitignore` for the proposal directory.

### Changed

- Renamed the skill from `paper-analyst` to `facts-and-figures`: `SKILL.md` frontmatter, `README.md`, `agents/openai.yaml`, and the default proposal directory, now `facts-and-figures-out/`.
- `references/analysis-integrity.md` drops the "lane" framing inherited from `blue-pencil`, where it named one branch of a larger editorial skill, and refers to the skill directly.

## [0.1.0] - 2026-08-15

Initial release: the analyst protocol extracted from `blue-pencil` as a standalone skill, with the three capabilities (verify numbers, regenerate a figure, run a named analysis), the five verification steps, the no-forking-paths rule, and a four-section output contract.
