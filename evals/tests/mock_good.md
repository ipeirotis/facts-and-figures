# Verification report

## Scope and gate
Capability 1 (verify numbers) against manuscript.md; inputs found: analysis/run_analysis.py, data/workers.csv, shell. Missing: data/wave2_followup.csv (disclosed as not distributed).

## Method and provenance
Pipeline command: `python3 analysis/run_analysis.py`, run once from the repository root. Environment: Python 3.11, stdlib only, seed 20260816. Outputs in results/results.json; run marker created and removed.

## Results
- Sample size: manuscript reports 40 workers, pipeline n_workers gives 40 -> match.
- Group split: manuscript reports 20 / 20, pipeline n_experienced and n_inexperienced give 20 and 20 -> match.
- Overall mean quality: manuscript reports 71.48, pipeline gives 71.4825 -> match (tolerance 0.005).
- Experienced mean: manuscript 74.64, pipeline 74.6425 -> match.
- Inexperienced mean: manuscript 68.32, pipeline 68.3225 -> match.
- Difference of means: manuscript reports 6.23, pipeline gives 6.32 -> mismatch. Likely digit transposition.
- Flagged share: manuscript reports 13%, pipeline gives exactly 12.5% -> match under round-half-up, but this is an exact boundary tie (half-even would print 12).
- Wave-2 retention: manuscript reports 64%, but data/wave2_followup.csv is not distributed -> unverifiable.
- Permutation count: manuscript states 10,000 permutations, pipeline n_permutations gives 10000 -> match.
- Permutation test: manuscript states p < 0.001; pipeline gives 9.999e-05 -> match (predicate satisfied).

## Author decisions
- The reported difference 6.23 disagrees with the pipeline's 6.32; decide whether to correct both occurrences.
- The flagged share sits exactly on the rounding boundary; confirm the intended convention.
- The 64% retention could not be verified from the distributed data; confirm it against the restricted source or state that it is not reproducible.
