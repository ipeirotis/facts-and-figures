# Compute environment: where the analysis runs

Load this before any run that will not obviously finish locally, and before
any run that would read the author's data from, or write it to, a service
outside the repository. The integrity norms in
`references/analysis-integrity.md` do not change with the machine; what
changes is how much provenance a result has to carry to remain reproducible,
and how many ways a run can silently stop being the run you described.

## Local first, and measure before you move

Default to running the author's pipeline locally, read-only, on the machine
you already have. Remote compute buys wall-clock time and costs
reproducibility, money, and a data-movement decision that is the author's to
make, so it needs a reason that survives being written down.

Before proposing anything larger, measure:

- the size of the actual inputs the pipeline reads (not the repository)
- the local CPU count and available memory
- an observed runtime, from a timed run on a subset or a short profiling run

"This looks big" is not a measurement. A pipeline nobody has timed is a
pipeline that usually finishes. Report the measurement when you propose the
move; if it turns out the pipeline runs locally in ten minutes, run it
locally and say nothing further about the cloud.

Cheap local moves come before remote ones, and none of them change a result:
run the pipeline's own parallelism flags, restrict a verification run to the
targets in scope when the pipeline supports it, and cache nothing the
pipeline does not already cache. Never substitute a sample for the full data
to make a verification finish faster: a number computed on a subsample does
not verify a number computed on the whole, and reporting it as if it did
breaks the master rule.

## Detecting credentials the repository already has

This skill never creates cloud credentials, never creates service accounts,
and never modifies IAM. It only detects and uses access the author has
already established, and hands anything else to the `cloud-bootstrap` skill,
which owns that lifecycle.

Look in the manuscript repository for:

- `.cloud-config.json` at the repository root
- `.cloud-credentials.<email>.enc`, or
  `.cloud-credentials.<provider>.<email>.enc` in multi-provider setups
- an encryption passphrase in the environment: `GCP_CREDENTIALS_KEY`,
  `AWS_CREDENTIALS_KEY`, `AZURE_CREDENTIALS_KEY`, or the
  `CLOUD_CREDENTIALS_KEY` fallback

Read the four states correctly, because three of them are not "the cloud is
available":

| What you find | What it means |
|---|---|
| Config, a credentials file for this user, and the matching passphrase | Access is available. Delegate activation to `cloud-bootstrap`, then proceed under the gates below. |
| Config and credentials, no passphrase in the environment | Not available in this session. Say so, name the variable, and run locally or stop. Never ask the author to paste a passphrase into the conversation. |
| A passphrase in the environment, no config in the repository | Not available for **this** repository. A key set in the session says nothing about whether this project has cloud resources. Do not infer a project, bucket, or dataset. |
| Neither | Local only. |

Authentication failures (401, 403, expired token, "could not refresh access
token") are `cloud-bootstrap`'s territory. Hand them over rather than
improvising a fix, and never work around a permission error by broadening
access.

## The gates before a remote run

All four must hold. They are cheap to check and each one has a failure mode
that ends with the author's data somewhere they did not put it.

1. **The author agreed.** Remote execution spends the author's money and, for
   anything that leaves the machine, moves the author's data. Propose it with
   the measurement, the destination, and the expected cost, and wait. This is
   not covered by a general instruction to verify the numbers.
2. **The destination is one the project already uses.** Run in the project
   the repository is configured for, against the buckets and datasets the
   pipeline already reads. Never upload the author's data to a service the
   repository does not already use, never create a new bucket or dataset to
   hold it, and treat unpublished data and any data with human subjects as
   moving only where the author has explicitly said it may.
3. **The cost is bounded and known before the run.** Estimate first, with a
   dry run where the service offers one (a BigQuery dry run reports bytes
   scanned without executing). Ask before a run whose cost you cannot bound,
   and never leave a provisioned machine running after the analysis finishes.
4. **The result will still be reproducible.** If the run cannot carry the
   provenance below, it does not qualify as verification, whatever it
   produces.

## Provenance for a remote run

Everything the local protocol logs (the exact command, the data version, the
output location) plus:

- **The environment.** Interpreter and package versions, the container image
  digest when one is used, and the machine type. Record these for local runs
  too: a number reproduces only in an environment the author can rebuild, and
  a lockfile, `pip freeze`, `renv.lock`, or `sessionInfo()` captured at run
  time is the cheapest provenance in this file.
- **The job identity.** Region or zone, project or account, and the job,
  query, or run ID the service assigns. This is what lets the author or a
  reviewer find the run later.
- **A pinned data snapshot.** A warehouse table is not a file: it can change
  under a query, so "the table" is not a data version. Pin the read (a
  BigQuery time-travel decorator or table snapshot, an object version or
  generation on cloud storage, a partition key with a fixed as-of date) and
  record the pin. Without one, report the result as unverifiable rather than
  as verified, and say why.
- **Seeds and ordering.** Record every RNG seed. Where the work is sharded or
  parallel, floating-point results can shift with reduction order, so use the
  pipeline's deterministic reduction whenever it offers one. When it does not,
  say so in the report, name what makes the run order-dependent, and classify
  any value that moves between runs as unverifiable rather than as a match or
  a mismatch: a number that changes when nothing else did has not been
  verified by either run.

## Same rules, more compute

Two failure modes are specific to having a big machine, and both are the
no-forking-paths rule wearing a different hat:

- **Capacity is not permission.** Compute that makes a hundred specifications
  cheap does not make running them acceptable. The pinned specification is
  still the analysis; a grid is reported whole only when the author named the
  grid.
- **A disagreeing rerun is a finding.** When the remote run and the local run
  disagree, that is a result about the pipeline's reproducibility and it goes
  in the report. Do not pick the run that matches the manuscript, and do not
  quietly rerun until one does.

Finally, the write rule follows the analysis to the cloud: remote jobs author
new outputs in the proposal location (or a clearly labeled new remote prefix
or dataset the author names), and never overwrite a table, object, or
artifact the author's pipeline treats as its own.
