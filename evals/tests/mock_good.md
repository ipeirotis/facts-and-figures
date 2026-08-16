## Results
- Overall mean quality: manuscript reports 71.48, pipeline gives 71.4825 -> match (tolerance 0.005).
- Experienced mean: manuscript 74.64, pipeline 74.6425 -> match.
- Inexperienced mean: manuscript 68.32, pipeline 68.3225 -> match.
- Difference of means: manuscript reports 6.23, pipeline gives 6.32 -> mismatch. Likely digit transposition.
- Flagged share: manuscript reports 13%, pipeline gives exactly 12.5% -> match under round-half-up, but this is an exact boundary tie (half-even would print 12).
- Wave-2 retention: manuscript reports 64%, but data/wave2_followup.csv is not distributed -> unverifiable.
- Permutation test: manuscript states p < 0.001; pipeline gives 9.999e-05 -> match (predicate satisfied).
## Author decisions
- The flagged share sits exactly on the rounding boundary; confirm the intended convention.
