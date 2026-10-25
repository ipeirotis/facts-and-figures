# Synthetic table and figure paper

All observations are fictional. The manuscript includes Table 1 and Figure 1.
The submitted graph is `figures/quality.svg`. The canonical pipeline reads
`data/scores.csv` and computes group means without filtering or transformation.

From this paper's directory, use a new output directory:

```bash
python3 analysis/run_analysis.py --output-dir facts-and-figures-out/recomputed
```

It writes `results.json`, `table.csv`, and `quality.svg` there. It does not
overwrite the submitted manuscript, data, or figure. No seed or third-party
package is needed. SVG axes are linear: score 0 at y=240, score 100 at y=40;
the bars start from zero. The same existing pipeline creates the table and
graph from the computed means.
