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

**Measure after the plan is pinned, never before.** The protocol pins the
number inventory and the producing commands (capability 1) or the
specification (capability 3) before the first run, and measuring is a run.
A timed subset that shows you a coefficient before the plan is fixed is a
peek at the results, and a plan written after a peek is the garden of
forking paths however honestly it was chosen. So: pin first, then measure,
and keep the measurement blind — read resource metrics from it, never
values.

Before proposing anything larger, measure:

- the size of the actual inputs the pipeline reads (not the repository), from
  file sizes, row counts, or a dry run that reports bytes without executing
- the local CPU count and available memory
- an observed runtime. Prefer a path that cannot surface a result: the
  pipeline's own dry-run or plan mode, a load-and-parse step with the
  analysis stage stopped, or a timed run of a stage that produces no
  reported quantity. When only a subset run will do, run it after the plan
  is pinned, record the timing, and do not read its output for values; if a
  value does land in front of you, say so in `Method and provenance` rather
  than pretending it did not, since the plan's credibility depends on when
  it was fixed.

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
never modifies IAM, and never decrypts a credentials file itself. It only
detects and uses access the author has already established, and hands
anything else to the `cloud-bootstrap` skill, which owns that lifecycle.

That makes `cloud-bootstrap` an **optional runtime prerequisite**: optional
because everything this skill does locally works without it, and a
prerequisite because it is the only sanctioned path from an encrypted
credentials file to an activated session. If the repository is fully
configured but `cloud-bootstrap` is not installed, remote execution is
unavailable, not improvised: name the missing skill in `Author decisions`
with its install location, and run locally or stop. Decrypting the author's
credentials by hand to get around a missing dependency is never the
workaround.

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
| Config, but no credentials file for this user (a fresh clone, or a collaborator not yet provisioned) | Not available. This is `cloud-bootstrap`'s add-team-member case: name it in `Author decisions` and hand it over. Never attempt activation, and never read a credentials file belonging to another user. |
| A passphrase in the environment, no config in the repository | Not available for **this** repository. A key set in the session says nothing about whether this project has cloud resources. Do not infer a project, bucket, or dataset. |
| Neither | Local only. |

In a multi-provider setup, read each configured provider independently: one
provider being usable says nothing about the next. Anything that does not
match a row above is a partial configuration, and every partial configuration
resolves the same way — treat access as unavailable, say which piece is
missing, and run locally or stop. Never infer availability from the config
file alone: it records what the project was set up for, not what this session
can reach.

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
   scanned without executing). A cost you cannot bound is a stop, not a
   question: approval does not turn an unknown cost into a known one, so
   either obtain a bound — a dry-run estimate, a documented rate against a
   known input size, or an enforceable ceiling such as a maximum-bytes-billed
   setting or a budget cap — or do not run, and say which. Never leave a
   provisioned machine running after the analysis finishes, and report the
   teardown rather than asserting it: see "Teardown, confirmed" below.
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
- **Commands with the secrets taken out.** A logged command is only useful
  if the author can paste it back, and only safe if it carries no secret. A
  pipeline invoked with a connection string, a signed URL, an API key, or a
  token embeds that secret in the exact command this skill is otherwise
  required to record. Redact the value and keep the shape: write
  `--dsn "$WAREHOUSE_DSN"` or `<signed URL for gs://bucket/path, expires
  2026-01-01>` in place of the literal, and name the environment variable or
  secret reference the value came from, so the command remains reproducible
  by someone who holds the credential. The same applies to anything an
  environment-capture step emits — a `printenv` dump, a config listing, a
  connection URL in an error message — and to output pasted into the report.
  A secret that reaches the report has left the machine; treat a leaked one
  as needing rotation and say so in `Author decisions`.
- **Teardown, confirmed.** A run that provisions anything (a VM, a cluster,
  a notebook instance, a scheduled job) records the teardown command and the
  final observed state of every resource it created: stopped, deleted, or
  still running. "Never leave a machine running" is not checkable unless the
  report says what happened, and a cleanup that silently failed keeps
  charging the author while the report looks compliant. If teardown fails or
  cannot be confirmed, say so in `Author decisions` with the resource
  identifier, rather than closing the report as if it succeeded.
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

Finally, the write rule follows the analysis to the cloud: remote jobs write
their outputs to a clearly labeled proposal prefix inside a location the
project already uses, and never overwrite a table, object, or artifact the
author's pipeline treats as its own. Gate 2 holds for outputs as it does for
inputs, so if no existing location can hold them, that is a stop-and-ask, not
a reason to create a bucket or dataset: the author creates any new
destination, and names it, before a run writes there. Pull results back into
the local proposal directory whenever they are small enough for the author to
inspect without the cloud.
