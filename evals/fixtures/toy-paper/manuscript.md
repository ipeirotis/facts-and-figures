# Experience and Response Quality in Microtask Work

*Working paper, second revision. This is a synthetic manuscript: it is the
facts-and-figures eval fixture, and every data row behind it is fabricated.*

## Abstract

We study whether prior platform experience predicts response quality in a
pool of 40 microtask workers. Experienced workers outscore inexperienced
workers by 6.23 points on average, a difference a permutation test finds
highly significant (p < 0.001).

## Data

We recruited 40 workers, 20 with prior platform experience and 20 without.
Each worker completed a standardized batch of labeling tasks scored 0–100
against a gold set. The mean quality score across all workers was 71.48.
Our quality-control rule flagged 13% of workers for manual review.

## Results

The 20 workers with prior platform experience achieved a mean quality score
of 74.64, against 68.32 for the 20 workers without: experienced workers
outscore inexperienced ones by 6.23 points. A two-sided permutation test on
the difference in group means (10,000 permutations, fixed seed) rejects the
null of no difference (p < 0.001).

In the wave-2 follow-up conducted three months later, 64% of the original
workers returned to the platform.

## Data and code

`analysis/run_analysis.py` reproduces every number above from
`data/workers.csv`; run `python3 analysis/run_analysis.py` from the
repository root. The wave-2 follow-up file (`data/wave2_followup.csv`) is
not distributed with this repository under the terms of our data agreement.
