---
name: paper-analyst
description: Verify numbers reported in an academic manuscript against the repository's own data and analysis pipeline, regenerate a named figure from the same data with improved presentation, or run a new analysis explicitly specified by the author, such as a robustness check, baseline, or subgroup analysis. Use when the repository contains the author's data and analysis code and the task requires reproducible computation with command-level provenance. Do not use for prose editing, literature searches, citation verification, or exploratory searches for favorable results.
---

# Paper Analyst

Verify manuscript results by executing the author's own analysis pipeline. Preserve the distinction between verification, re-rendering, and new analysis. Never edit the manuscript, source data, or the author's existing analysis code.

## Select a capability

1. **Verify numbers:** rerun the existing pipeline and compare every in-scope manuscript value with a traced output.
2. **Regenerate a figure:** reproduce a named figure from the same data, changing presentation rather than the underlying sample, variables, transformations, or estimates.
3. **Run a named analysis:** pin the author's requested specification before execution, write new work only in a proposal directory, and report the complete result regardless of direction.

If the request does not identify the capability or target, ask one focused question before running anything.

## Gate the work

Require the repository's data and analysis code plus a shell. Require write access for figure regeneration or a new analysis. If an input or tool is missing, name it and stop; never estimate, reconstruct, or invent a result.

## Run the protocol

Read `references/analysis-integrity.md` before acting and follow its capability-specific protocol and no-forking-paths rule. Log every command that produces a reported value or artifact. Keep generated scripts and outputs outside the author's existing code and manuscript unless the author explicitly chooses to adopt them.

## Return

Return exactly:

1. **Scope and gate:** capability, target, inputs found, and missing prerequisites.
2. **Method and provenance:** pinned specification, commands, files, and output locations.
3. **Results:** complete comparisons or results, including null, adverse, and failed outcomes.
4. **Author decisions:** proposed values or artifacts, unresolved ambiguities, and what the author must decide before adoption.
