# Verification report

## Scope and gate
Verification of manuscript.md. Gate failed: required input data/workers.csv is missing from the repository. Stopping without asserting anything about the reported numbers.

## Method and provenance
Only a diagnostic run was made: `python3 analysis/run_analysis.py` exits 1 with "required input not found: data/workers.csv". No values were computed, so there is no execution provenance to report.

## Results
No value could be checked in either direction; nothing is classified as match or mismatch.

## Author decisions
Restore data/workers.csv or point the pipeline at the intended dataset.
