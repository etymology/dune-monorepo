---
marp: true
paginate: true
theme: default
class: invert
---

# UKAPA7 After Storage and Shipment

---

## What happened?

- The comparable Chicago tension measurements are lower than the UK measurements
  in every layer-side group.
- The shift is not a single constant offset: G is lower by about `0.2-0.4 N`,
  while the currently measured U subset is lower by about `0.5-0.9 N`.
- All current Chicago G and U summary values are within the `4.0-8.5 N`
  tension specification.
- These data answer the tension question, but they do not by themselves identify
  a unique cause for the lower values.

---

## Measurement basis

- UK source data are the APA-UK007 action JSON records: U uploaded
  `2023-11-21`, G uploaded `2023-12-10`.
- Chicago source data are the current `tension_summary_UKAPA7_G.csv` and
  `tension_summary_UKAPA7_U.csv` files.
- The Chicago summary CSVs do not encode a measurement timestamp, so the deck
  does not rely on one.
- Residuals are defined as `Chicago - UK`; negative values mean Chicago measured
  lower tension.

---

## Coverage and limits

- **G layer:** full A-side comparison with `481` wires; corrected B-side
  comparison with `480` wires after reversing and shifting the B index.
- **U layer:** partial Chicago coverage only, with `385` aligned wires on side A
  and `641` on side B.
- U layer wires were accessed through a "slit" cut in the G wires near the
  middle of the APA.
- The G and U comparisons were therefore not made under identical access and
  frame conditions.

---

## G Layer

- Side A: mean residual `-0.38 N`, median `-0.43 N`, `84%` of wires lower in Chicago.
- Side B: mean residual `-0.20 N`, median `-0.30 N`, `71%` of wires lower in Chicago.
- Residual widths are about `0.4 N` on both sides.
- Some individual wires measured higher in Chicago, so the change is not uniform
  wire by wire.

---

![g both sides](/Users/ben/dune-monorepo/dune_tension/experiments/UKAPA7_comparison/ukapa7_landscape_G.png)

---

![G change in tension](/Users/ben/dune-monorepo/dune_tension/experiments/UKAPA7_comparison/ukapa7_change_in_tension_G.png)

---

## U Layer

- Side A subset: mean residual `-0.54 N`, median `-0.51 N`, `85%` of aligned
  wires lower in Chicago.
- Side B subset: mean residual `-0.87 N`, median `-0.76 N`, `99%` of aligned
  wires lower in Chicago.
- Residual widths are about `0.5 N` on both sides.
- The U-layer result is a partial-subset comparison, not a full-layer
  comparison.

---

![U both sides](/Users/ben/dune-monorepo/dune_tension/experiments/UKAPA7_comparison/ukapa7_landscape_U.png)

---

![U change in tension](/Users/ben/dune-monorepo/dune_tension/experiments/UKAPA7_comparison/ukapa7_change_in_tension_U.png)

---

## What the data do and do not show

- The robust observation is downward shift: Chicago values are lower on average
  for G A, G B, U A, and U B.
- The current Chicago values remain in specification: G ranges from `4.44` to
  `7.00 N`; U ranges from `4.03` to `6.41 N`.
- The data do not show an out-of-spec tension signature after storage and shipment.
- The data alone do not separate wire relaxation, measurement differences,
  access changes, frame state, or handling effects.

---

## Bottom line

- APA-UK007 tensions were lower when measured in Chicago than in the UK source
  records.
- The lower shift is modest for G and larger in the measured U subset.
- No measured Chicago G or U tension in these summary files falls outside the
  `4.0-8.5 N` specification.
- Any recommendation beyond tension acceptance needs external acceptance
  criteria or inspection evidence not contained in these files.

---

![all g wires](/Users/ben/dune-monorepo/dune_tension/data/tension_plots/tension_profile_cloud_G_mode_allsamples_cov0p5_it3_bins40.png)

---
![all u wires](/Users/ben/dune-monorepo/dune_tension/data/tension_plots/tension_profile_cloud_U_noscale_allsamples_cov0p5_it3_bins40.png)
