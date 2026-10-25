## 1. Scope and gate

- **Capability:** verify numbers, tables and graphs.
- **Target:** Table 1 and Figure 1 in `manuscript.md`. Figure 1 is the submitted file `figures/quality.svg`.
- **Inputs found:**
  - `analysis/run_analysis.py`, which the README names as the canonical pipeline.
  - `data/scores.csv`, with 4 rows.
  - The submitted SVG.
  - Python 3.9.6.
  - There is no `<paper_context>` file (no `AGENTS.md`, `CLAUDE.md` or `paper-meta.md`), so I worked from the files you named.
- **Missing prerequisites:** none.
- **Marker:** I created `facts-and-figures-out/.active` exclusively and removed it at the end.

## 2. Method and provenance

- **Plan, fixed before running:**
  - Compare each Table 1 cell and each printed label to the pipeline mean at one decimal. The accepted interval is half-open, [m−0.05, m+0.05).
  - Check the bar geometry separately, using the README's axis transform (y=240 is 0, y=40 is 100, so score = height/2).
- **Commands, both run from the repository root:**
  - `python3 -I analysis/run_analysis.py --output-dir facts-and-figures-out/recomputed`
  - `python3 -I facts-and-figures-out/extract_svg.py figures/quality.svg`
- **What the extraction script does:** it parses the `rect` and `data-value-for` attributes in the SVG and converts height to score. I wrote it as a new file in the proposal directory. It has no side calculations.
- **Environment:** Python 3.9.6, standard library only, no seed.
- **Inputs and hashes (sha256):**
  - `data/scores.csv`: `a61e82df…eb8dd`
  - `figures/quality.svg`: `4fca7a38…13bc`
  - `manuscript.md`: `6e1cf155…db55`
  - `analysis/run_analysis.py`: `34e52c25…2729`
  - The directory is not a git repository, so these hashes identify the data version.
- **Preservation:** all pipeline writes went to `facts-and-figures-out/recomputed/`. I did not edit the manuscript, data, code or submitted figure.
- **Outputs:**
  - `facts-and-figures-out/recomputed/` (`results.json`, `table.csv`, `quality.svg`)
  - `facts-and-figures-out/extract_svg.py`
  - `facts-and-figures-out/verification-report.json`
- **Teardown:** nothing was provisioned. The marker is gone. I kept `facts-and-figures-out/` because it holds the report.

## 3. Results

**Pipeline output** (`results.json`): A = 80.0 and B = 60.0. The raw scores are A: 75, 85 and B: 55, 65.

**Table 1**

| Cell | Reported | Computed | Verdict |
|---|---|---|---|
| Row A, Mean | 80.0 | 80.0 | match |
| Row B, Mean | 65.0 | 60.0 | **mismatch** |

- **Labels and units:**
  - The Group and Mean headers match the pipeline's `group` and `mean` fields.
  - The caption's "0–100 scale" matches the 0–100 axis the pipeline uses.
  - The data file records no units beyond the score itself.
  - The row labels are in the right order. The wrong number sits under the correct label, B.

**Figure 1: numeric labels and bar heights, checked separately**

| Mark | Reported | Computed | Verdict |
|---|---|---|---|
| A, printed label | 80.0 | 80.0 | match |
| B, printed label | 65.0 | 60.0 | **mismatch** |
| A, bar | height 160, which is 80.0 | 80.0 | match |
| B, bar | height 130 (y=110), which is 65.0 | 60.0 | **mismatch** |

- **Bar B:** the geometry is wrong, not only the label. The pipeline's own figure draws B at y=120 with height 120.
- **Diff against the freshly generated SVG:** the only differences are those two B lines, the `rect` and the label text. Bar A is identical.
- **Group labels:** the A and B labels under the bars match the `data-group` attributes and the pipeline's groups.
- **Axes:**
  - The y-axis runs linearly from 0 to 100, with bars starting at zero.
  - The ticks sit at the documented positions. Tick 100 is at y=45 as a text baseline, 5 px below y=40, which is the same offset the pipeline uses.
  - The x-axis is titled "Group".
- **Chart title and y-axis unit:** the chart title is "Mean quality score". There is no y-axis title, so the unit and scale appear only in the chart title and the caption. This is a presentation note, not a numeric finding.
- **Caption:** "Bars show group means on the same 0–100 quality scale as Table 1." The scale statement is consistent. The caption's implied agreement with Table 1 holds numerically only for A. For B, the table and figure agree with each other (both 65.0) but not with the data.

## 4. Author decisions

1. **Table 1, B Mean (65.0 vs 60.0):** the data gives 60.0. Is `data/scores.csv` the intended snapshot? If it is, 65.0 should become 60.0. If not, which data produced 65.0? One possibility is that the manuscript was written from different or earlier data, for example without the score of 55.
2. **Figure 1, B printed label and bar:** the label and the bar both need correcting to 60.0 and height 120. The submitted file is stale. You could replace it with the pipeline's `facts-and-figures-out/recomputed/quality.svg` as a proposal. I have not changed any of your files.
3. **Optional presentation:** should the y-axis carry its own title, such as "Mean quality score (0–100)"? If you want a redesign, that would be a separate figure-regeneration request.
4. **Consistency check:** once B is corrected, check the whole paper for other mentions of 65 or the A–B gap. Correcting B changes the gap from 15 to 20.

The companion `facts-and-figures-out/verification-report.json` has six value records that agree with the verdicts above: 2 matches and 2 mismatches for the table and printed labels, and 1 match and 1 mismatch for the bars. Its `computed` fields hold the full-precision pipeline values.