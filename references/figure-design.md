# Figure design: what a re-render may change

Load this for capability 2 (regenerate a figure). It owns the design standard
a re-render is held to and, more importantly, the line between improving a
figure and changing what it claims. `references/analysis-integrity.md` owns
the protocol; this file owns the judgment inside step 2 of it.

## Why figures get their own standard

Figures are primary text, not decoration. A reader who skims only the figures
and their captions should be able to describe the paper's main result. That
is the test a figure passes or fails, and it is why a re-render is worth
doing at all: a figure that forces the reader into the body prose to learn
what it shows is under-doing its job.

The test applies to the caption as much as the plot. If the figure and its
caption together do not carry the claim, the fix is usually to promote a
claim the body prose already makes into the caption, not to add anything to
the plot. Caption text is the author's prose: propose it, never edit it in
place, and never write a caption that asserts something the plotted values do
not show.

## The invariant

**A regenerated figure plots the same values as the original.** Everything
below is downstream of that sentence.

May change (presentation):

- color, palette, and the encoding channel a variable uses
- ordering of categories, facets, or series
- scale labeling, tick density, units displayed, number formatting
- gridlines, reference lines the original already implied, legend placement
- direct labeling in place of a legend
- figure dimensions, aspect ratio, font sizes, resolution, output format
- caption wording, proposed as text for the author to accept

May not change (substance). Each of these is a new analysis, and it routes to
capability 3 under capability 3's rules:

- the data file, snapshot, or query the figure reads
- the sample: filters, exclusions, winsorizing, trimming, imputation
- transformations: logs, standardization, per-capita or index rebasing
- estimates: any recomputed coefficient, interval, smoother, or fit
- **added smoothing, trend lines, or interpolation the original did not apply**
- **an axis range, clipping, or log scale that removes points from view or
  changes which differences read as large**
- an added or dropped series, or a re-binned histogram

The two bolded items are where an honest re-render most often goes wrong:
both feel like presentation and both change what the reader concludes. A
truncated axis is a substantive claim about which differences matter. If a
change in this list genuinely improves the figure, do not make it: name it in
`Author decisions` as a proposed new analysis and let the author ask for it.

## Improving presentation

Work in this order; stop when the figure passes the skim test.

1. **Make the comparison the figure exists to support the easiest one to
   see.** Position along a common scale beats length, which beats area,
   angle, or color intensity. If the claim is about differences between
   groups, put the groups on a shared axis rather than in separate panels.
2. **Order by the data, not the alphabet.** Sort categories by the value
   being shown unless the categories carry their own order (time, dose,
   Likert).
3. **Label directly.** A series labeled at its end beats a legend the reader
   must map back onto the plot.
4. **Cut what does not carry information.** Heavy gridlines, boxes, redundant
   legends, decorative color, and 3D effects on 2D data all cost the reader
   attention and return nothing.
5. **Show the uncertainty the pipeline already computed.** If the analysis
   produced intervals or standard errors and the original figure omits them,
   plotting them is presentation, not new analysis. Computing them when the
   pipeline never did is capability 3.
6. **Keep it legible where it will be read.** Check font sizes at the
   column width of the target venue, and check that the figure survives
   grayscale printing and the common color-vision deficiencies: never let
   color be the only channel distinguishing two series.

If the environment provides a visualization standard of its own (a house
style, a lab template, or a data-visualization skill), load it and follow it
for palette and mark choices. It governs style; this file governs substance,
and the invariant above outranks any style rule.

## Confirm the re-render before proposing it

A re-render asserts nothing new, which is a promise you have to check rather
than assume:

- Same data version as the original run, recorded the same way.
- Same summary statistic behind every mark. Compare the numbers the new
  script plots against the numbers the original script plots, from the
  script's own output, not by eye against the image.
- Same number of observations in each group, series, or bin.
- If any of these differ, say so plainly. A re-render that changes a value is
  either a bug in the new script or a finding about the original one, and
  both belong in the report rather than in a quietly adopted figure.

State in the report what you changed (color, ordering, labeling, scale
formatting) and confirm what you did not (the values). Present the original
and the re-render together, with the exact script and command that produced
the new one, and let the author choose.
