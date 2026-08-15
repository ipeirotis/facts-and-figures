---
name: facts-and-figures
description: Verify numbers reported in an academic manuscript against the repository's own data and analysis pipeline, regenerate a named figure from the same data with improved presentation, or run a new analysis explicitly specified by the author, such as a robustness check, baseline, or subgroup analysis. Use when the repository contains the author's data and analysis code and the task requires reproducible computation with command-level provenance. Do not use for prose editing, literature searches, citation verification, or exploratory searches for favorable results.
license: MIT
metadata:
  version: "0.2.0"
  author: ipeirotis
  repo: https://github.com/ipeirotis/facts-and-figures
---

# Facts and Figures

Verify manuscript results by executing the author's own analysis pipeline. Preserve the distinction between verification, re-rendering, and new analysis. Never edit the manuscript, source data, or the author's existing analysis code.

## The master rule

**Never assert unverified substance.** Every number and figure in your output was either written by the author or computed in this run from the repository's own data, with the producing command logged. A number you remember, estimate, derive by side calculation, or read off a plot is unverified substance, and it is a question for the author, never a result. This rule outranks every other instruction here: when following an instruction would require asserting something you did not compute, stop and ask instead.

What makes a value verified is the logged execution and the traced input, not who wrote the code that produced it: verification reruns the author's pipeline, while the two generative capabilities author new scripts, and a result from a new script is verified when the script, its command, its inputs, and its environment are all logged and the author can rerun it. Run metadata (a cost estimate, a job ID, a package version) is not substance under this rule; it is the provenance that supports it.

Two corollaries carry the rest of the skill:

- **Provenance or it does not exist.** A value the author cannot reproduce with one command does not enter the report.
- **Results are proposals, never edits.** A recomputed value, a re-rendered figure, and a new result are all offered for the author to accept or reject.

## Select a capability

1. **Verify numbers:** rerun the existing pipeline and compare every in-scope manuscript value with a traced output.
2. **Regenerate a figure:** reproduce a named figure from the same data, changing presentation rather than the underlying sample, variables, transformations, or estimates.
3. **Run a named analysis:** pin the author's requested specification before execution, write new work only in a proposal directory, and report the complete result regardless of direction.

If the request does not identify the capability or target, ask one focused question before running anything.

## Gate the work

Require the repository's data and analysis code plus a shell. Require write access for figure regeneration or a new analysis. If an input or tool is missing, name it and stop; never estimate, reconstruct, or invent a result.

## Load the manuscript context and scope the files

Before running anything, establish which manuscript you are checking and which of its files are in scope. `references/analysis-integrity.md` owns both, under "Establish the manuscript context". The manuscript repository's own context files are input, never output: this skill never edits them.

## Choose where the analysis runs

Default to running the author's pipeline locally, read-only. Before reaching for anything larger, read `references/compute-environment.md`: it carries the measure-first rule, how to detect credentials that `cloud-bootstrap` already placed in the repository, the four gates a remote run must pass, and the extra provenance it must carry to stay reproducible. Never move the author's data to a service the repository does not already use.

## Run the protocol

Read `references/analysis-integrity.md` before acting and follow its capability-specific protocol and no-forking-paths rule. Figure regeneration additionally reads `references/figure-design.md`, which owns what a re-render may change and what it must hold fixed. Log every command that produces a reported value or artifact. Generated scripts and outputs stay in the proposal directory: a run never places them into the author's existing code, data, figures, or manuscript, and never edits those files. Adoption is the author's own step.

## Return

Return exactly:

1. **Scope and gate:** capability, target, inputs found, and missing prerequisites.
2. **Method and provenance:** pinned specification, commands, files, environment, and output locations.
3. **Results:** complete comparisons or results, including null, adverse, and failed outcomes.
4. **Author decisions:** proposed values or artifacts, unresolved ambiguities, and what the author must decide before adoption.
