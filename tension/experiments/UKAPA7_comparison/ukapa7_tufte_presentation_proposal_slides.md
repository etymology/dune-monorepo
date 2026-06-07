---
marp: true
paginate: true
theme: default
style: |
  section {
    background: #fdfcf8;
    color: #202426;
    font-family: "Avenir Next", "Helvetica Neue", Arial, sans-serif;
    font-size: 30px;
    letter-spacing: 0;
    padding: 66px 78px;
  }
  h1 {
    color: #111;
    font-size: 54px;
    font-weight: 600;
    letter-spacing: 0;
  }
  h2 {
    color: #111;
    font-size: 42px;
    font-weight: 600;
    letter-spacing: 0;
  }
  h3 {
    color: #111;
    font-size: 32px;
    font-weight: 600;
    letter-spacing: 0;
  }
  p, li {
    line-height: 1.35;
  }
  strong {
    color: #111;
  }
  code {
    background: #efeee8;
    color: #202426;
    padding: 0.05em 0.18em;
  }
  table {
    font-size: 24px;
    width: 100%;
  }
  th {
    color: #111;
    border-bottom: 1px solid #555;
  }
  td {
    border-bottom: 1px solid #d5d2c8;
  }
  section.lead {
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
  section.lead h1 {
    font-size: 62px;
    max-width: 900px;
  }
  section.lead p {
    color: #4a4f51;
    font-size: 31px;
    max-width: 900px;
  }
  .quiet {
    color: #555b5e;
  }
---

<!-- _class: lead -->

# Tufte-Oriented Revision Proposal

APA-UK007 After Storage and Shipment

---

## Aim

Make the deck behave like evidence, not narration around evidence.

The revised presentation should let the audience see three things quickly:

- Chicago measured lower than the UK records.
- Current measured tensions remain inside the `4.0-8.5 N` specification.
- U-layer conclusions are constrained by partial coverage and different access.

---

## Tufte Principles Applied

### Reduce

- Remove heavy theme treatment.
- Remove repeated legends.
- Keep only statistics used by the argument.
- Move background plots to backup.

### Reveal

- Put comparable panels on shared scales.
- Label data directly.
- Show coverage limits visually.
- Tie each figure to one claim.

---

## Current Deck Diagnosis

- The conclusion appears before enough visible evidence.
- Caveats are stated as bullets, not encoded in the figures.
- The audience must compare raw traces, then residual plots, then statistics.
- Long legends carry too much quantitative content.
- The dark inverted theme adds weight around sparse scientific plots.
- Absolute image paths make the deck less portable.

---

## Revised Storyline

1. Finding and decision context.
2. Measurement basis and comparable coverage.
3. Primary residual evidence.
4. Current Chicago tensions relative to specification.
5. Wire-position structure.
6. What the data show and do not show.
7. Recommendation.
8. Backup for audit questions.

---

## First Data Slide

### Residual small multiples

Replace separate G and U change slides with one four-panel figure:

| Panel | Data shown |
| --- | --- |
| G A | `Chicago - UK` by wire |
| G B | corrected B mapping residuals |
| U A | aligned partial subset |
| U B | aligned partial subset |

Use shared y scales, faint points, a thin trend line, zero reference, and direct
labels for `n`, median, mean, and percent lower in Chicago.

---

## Why This Figure Leads

The central question is not the raw tension trace.

The central question is:

> What changed between the UK record and the Chicago measurement?

Small multiples make the repeated pattern visible: four comparable layer-side
groups all shift downward, while the magnitude and coverage differ.

---

## Acceptance Figure

### Current tensions versus specification

Add one figure focused on the acceptance question:

- One horizontal strip per layer-side group.
- Every current Chicago wire tension shown as a light point or rug mark.
- The `4.0-8.5 N` spec shown as a pale band or two thin reference lines.
- Min, median, and max labeled once per group.

This separates historical change from current acceptability.

---

## Coverage Figure

### Make partial data visible

Add a compact coverage strip:

| Row | Mark |
| --- | --- |
| G A | aligned UK and Chicago wires |
| G B | corrected aligned wires |
| U A | measured aligned subset |
| U B | measured aligned subset |

Missing or unavailable regions should remain empty. The U-layer slit/access
note belongs beside the affected rows, not on a separate caveat slide.

---

## Raw Traces Move to Backup

Raw Chicago-versus-UK traces remain useful for auditability.

They should not carry the main argument unless the audience is inspecting a
specific mapping or wire-region question.

Backup trace plots should use:

- one panel per layer-side group,
- shared y limits,
- thin marks,
- direct labels,
- no long statistical legends.

---

## Plot Style Rules

- Use a white or very light background.
- Use color only for data roles.
- Remove chart borders and heavy grids.
- Put units in axis labels.
- Use direct labels instead of legends where practical.
- Use consistent axis ranges for intended comparisons.
- Prefer medians and quantile intervals for long-tailed measurements.
- Avoid count histograms when sample sizes differ.

---

## Slide-Level Edits

- Replace `class: invert` with a light Marp theme.
- Replace absolute image links with relative paths.
- Fold G and U statistics into direct figure annotations.
- Move "Laser tension vs DWA" to backup unless needed live.
- Replace interpretation bullets with an evidence table.
- Make the recommendation distinguish change from acceptance.
- Move population profile-cloud plots to backup.

---

## Proposed Deck Skeleton

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

---

## Regenerated Assets

Add new outputs in `dune_tension/experiments/UKAPA7_comparison`:

- `ukapa7_residual_small_multiples.png`
- `ukapa7_current_tension_vs_spec.png`
- `ukapa7_coverage_strip.png`

Extend
`src/dune_tension/ukapa7_comparison/generate_landscape_display_plots.py` so the
deck remains reproducible from the source data.

---

## Acceptance Check

The revised deck is ready when:

- the main result is visible from the first data figure,
- every numeric claim is next to the plot or table that supports it,
- the U-layer coverage limit appears with the U-layer result,
- current acceptance and historical change are visually separate,
- backup slides answer audit questions without competing with the main story.

---

<!-- _class: lead -->

## Recommendation

Adopt the residual small-multiple figure as the core graphic, add a separate
current-tension spec figure, and make measurement coverage explicit.

Then let the slides say less because the figures say more.
