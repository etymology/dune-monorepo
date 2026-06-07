# Tufte-Oriented Revision Proposal for APA-UK007 Shipment Presentation

This proposal covers
`ukapa7_shipment_storage_presentation.md`. It treats Edward Tufte's principles
as practical constraints for the deck: show comparisons directly, reduce
non-data ink, make uncertainty and coverage visible, and place words next to
the evidence they explain.

## Presentation Diagnosis

- The current deck states the conclusion before showing enough evidence for
  the audience to reconstruct it.
- Important caveats, especially U-layer partial coverage and different access
  geometry, appear as bullets rather than visible constraints on the figures.
- The landscape plots ask the audience to compare Chicago and UK traces, then
  separately compare residual plots. The central question is the residual, so
  it should become the primary graphic.
- Legends carry too much statistical text. That consumes attention and
  duplicates information that could be placed as direct labels or small margin
  summaries.
- The dark inverted slide theme adds visual weight around sparse scientific
  plots. A light background with quiet axes will usually improve legibility and
  reduce non-data ink.
- The extra plots at the end are not tied to a decision. They should either be
  integrated into the argument or moved to backup.
- The markdown uses absolute image paths. A Tufte-style handout or deck should
  be portable and reproducible from the experiment directory.

## Revised Storyline

1. **Title and finding.** One sentence: APA-UK007 measured lower in Chicago,
   with all current measured values still inside the 4.0-8.5 N specification.
2. **Measurement basis.** A compact table: layer, side, UK source, Chicago
   source, aligned wire count, comparability note.
3. **Primary evidence.** One small-multiple residual figure with G A, G B,
   U A, and U B on shared y scales. This should be the first data slide.
4. **Specification status.** One plot showing current Chicago tensions against
   the 4.0-8.5 N band, grouped by layer and side.
5. **Wire-position structure.** One plot showing residuals by wire number with
   light points and a thin smoothed line, used only to show whether there is a
   spatial pattern beyond the downward shift.
6. **Coverage and comparability.** A compact coverage plot or strip chart for
   G and U, making the U partial subset visible rather than describing it only
   in text.
7. **Interpretation.** A short evidence table: observation, what it supports,
   and what it cannot distinguish.
8. **Recommendation.** Acceptance should be based on relaxed absolute tension
   range plus inspection evidence, not on per-wire change alone.

## Proposed Plot Regeneration

### 1. Residual Small Multiples

Replace the separate `ukapa7_change_in_tension_G.png` and
`ukapa7_change_in_tension_U.png` slides with one four-panel figure:

- Panels: G side A, G side B, U side A, U side B.
- X axis: wire number.
- Y axis: `Chicago - UK` tension in N, shared across all panels.
- Reference lines: zero change and median residual for each panel.
- Encoding: very small gray points for wires, one thin colored median or rolling
  trend line, no grid except faint horizontal references.
- Direct labels: `n`, median, mean, and percent lower in Chicago in the panel
  margin.
- Use the same x limits for sides where meaningful; otherwise label the
  measured subset explicitly.

This follows Tufte's small-multiple principle: the same visual grammar repeated
across comparable groups lets the audience see the pattern rather than decode
the chart.

### 2. Current Tensions Versus Spec

Add a new figure focused on the acceptance question:

- One horizontal dot plot or interval strip per layer-side group.
- Plot every current Chicago wire tension as a light point or rug mark.
- Draw the 4.0-8.5 N specification band as two thin reference lines or a pale
  band.
- Annotate min, median, max only once per group.
- Avoid histograms here. The point is not the distribution shape; it is whether
  any measured values fall outside the acceptance band.

This separates "changed since the UK measurement" from "currently acceptable,"
which are different decisions.

### 3. Coverage Strip

Add a small coverage figure:

- Rows: G A, G B, U A, U B.
- X axis: wire number.
- Mark wires with aligned Chicago and UK data.
- Mark missing or unavailable regions as open space, not as zero values.
- Add the U-layer slit/access note as a direct label beside the affected rows.

This prevents the U-layer caveat from being buried in prose and makes the
partial-subset comparison visually honest.

### 4. Optional Raw-Tension Backup

Keep raw Chicago-vs-UK traces only as backup:

- Use one panel per layer-side group.
- Share y limits across panels.
- Use thin lines or faint points, direct labels, and no long legend.
- Do not place raw and residual summaries on separate required slides unless a
  specific question needs both.

Raw traces are useful for auditability, but they are secondary to the shipment
and storage question.

## Plot Style Rules

- Prefer a white or very light background.
- Use black or dark gray text and axes; use color only to distinguish a small
  number of data roles.
- Remove chart borders, heavy grids, and repeated legends.
- Put units in axis labels, not in every annotation.
- Use direct labels next to the data when possible.
- Use consistent axis ranges for comparisons that the audience is expected to
  make.
- Keep statistics close to the plot they summarize and show only statistics
  that drive the argument.
- Normalize or avoid histograms when sample sizes differ; counts are misleading
  between G full coverage and U partial coverage.
- Prefer medians and quantile intervals for long-tailed measurement behavior.
- Use figure captions as claims: each caption should say what the plot proves
  or limits.

## Slide-Level Edits

- Replace `class: invert` with a light theme in the Marp markdown.
- Replace absolute image links with relative paths such as
  `./ukapa7_residual_small_multiples.png`.
- Fold "G Layer statistics" and "U Layer" bullets into direct annotations on
  the regenerated residual figure.
- Move "Laser tension vs DWA" into backup unless it is essential for the live
  audience. If retained, present it as a measurement-comparability table.
- Replace the "Interpretation" bullet slide with a two-column evidence table:
  `Observed` and `Interpretation limit`.
- Replace the "Recommendation" slide with a decision slide showing:
  current spec status, why change-only criteria are unstable, and the proposed
  acceptance basis.
- Move profile-cloud plots to backup with captions explaining why they are
  background context, not direct evidence for APA-UK007 shipment effects.

## Suggested Deck Skeleton

```text
1. APA-UK007 After Storage and Shipment
2. Measurement Basis and Comparable Coverage
3. Change in Tension, Chicago - UK
4. Current Chicago Tensions Relative to Specification
5. Is the Shift Spatially Structured?
6. What the Data Show and Do Not Show
7. Recommendation
8. Backup: Raw Chicago and UK Tension Traces
9. Backup: G and U Population Profiles
```

## Implementation Notes

- The existing generator
  `src/dune_tension/ukapa7_comparison/generate_landscape_display_plots.py`
  already builds the aligned G and U comparison frames, including corrected B
  mappings. Extend it rather than adding a separate analysis path.
- Add new outputs in the experiment directory:
  - `ukapa7_residual_small_multiples.png`
  - `ukapa7_current_tension_vs_spec.png`
  - `ukapa7_coverage_strip.png`
- Keep the old PNGs until the revised deck is accepted; they are useful for
  comparison and backup.
- Regenerate from Quarto or the plotting module so the presentation remains
  reproducible from source data.

## Acceptance Check for the Revised Deck

- A reader should understand the main result from the first data figure without
  reading the bullets.
- Every numeric claim on a slide should be visible in the neighboring plot or
  table.
- The U-layer partial-coverage caveat should be visible on the same slide as
  the U-layer result.
- The recommendation should distinguish current acceptance from historical
  change.
- Backup slides should answer audit questions without competing with the main
  narrative.
