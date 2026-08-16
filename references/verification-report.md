# The machine-readable verification report

Verification (capability 1) writes a JSON companion to its prose report
whenever the session can write: `verification-report.json` in the proposal
directory (`facts-and-figures-out/` unless the author named another). The
prose report remains the deliverable for the author; the JSON companion
exists so software — CI, the eval grader, a dashboard — can consume the
same conclusions without parsing prose. The two must agree: the JSON file
is substance, and every value in it falls under the master rule exactly as
if it were written in the prose report.

It stays in the proposal directory like all generated work. It is not
teardown: the run marker is removed when the run ends, the report is kept.
A read-only session writes no report and says so in Method and provenance.

## Shape

```json
{
  "schema": "facts-and-figures.verification/1",
  "skill_version": "0.5.0",
  "manuscript_files": ["manuscript.md"],
  "pipeline_command": "python3 analysis/run_analysis.py",
  "environment": "Python 3.11.15, stdlib only; seed 20260816",
  "data_versions": {
    "data/workers.csv": "sha256:..."
  },
  "values": [
    {
      "location": "manuscript.md, Data",
      "reported": "71.48",
      "classification": "match",
      "computed": 71.4825,
      "tolerance": "half-open [71.475, 71.485), k=2",
      "boundary": false,
      "producing_command": "python3 analysis/run_analysis.py",
      "note": ""
    }
  ]
}
```

## Field rules

Top level, all required: `schema` (exactly `facts-and-figures.verification/1`),
`skill_version`, `manuscript_files`, `pipeline_command`, `environment`,
`data_versions`, `values`.

Each record in `values` carries one manuscript value:

- `location` (required): where the value appears, precise enough for the
  author to find it.
- `reported` (required): the value as the manuscript states it, verbatim —
  `"71.48"`, `"13%"`, `"p < 0.001"`.
- `classification` (required): exactly one of `match`, `mismatch`,
  `unverifiable` — the same classes, under the same tolerance and predicate
  rules, as `references/analysis-integrity.md` defines. No other value is
  valid.
- `computed` (required for match and mismatch, `null` for unverifiable):
  the pipeline output at full precision, never rounded to make the point.
- `tolerance` (required for match and mismatch of point values): the
  accepted interval or predicate, fixed before comparison, stated so a
  reader can recheck the classification from `reported` and `computed`
  alone. For a predicate value, state the predicate (`"p < 0.001"`).
- `boundary` (optional, defaults to false when absent): must be present and
  `true` for an exact endpoint tie, which the prose report simultaneously
  names in Author decisions; any other value or absence means no tie.
- `producing_command` (required for match and mismatch): the exact command,
  secrets redacted, whose logged run produced `computed`.
- `reason` (required for unverifiable): why — the named unreachable input,
  the unclear producing command, or the failed run.
- `note` (optional): anything the author needs that fits no other field.

Every classification in the file must appear in the prose report and vice
versa; a value present in one and absent from the other is a defect in the
run. Secrets are redacted here under the same rule as every logged command.
