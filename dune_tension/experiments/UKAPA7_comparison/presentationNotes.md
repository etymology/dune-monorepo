# NOTES for @ukapa7_shipment_storage_presentation.md

## What happened?

Tensions were lower by about half a newton
Everything looks okay, all tensions within final spec, no sign of damage.

---

## Measurement basis

- 2 years, 3 months, difference
  - Probably laser+ziptie+labview
- Chicago source data from March 11 2026
  - Chicago winder using laser+compressed air+python
- Residuals are defined as `Chicago - UK`; negative values mean Chicago measured lower tension.

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

![g both sides](/Users/ben/dune-monorepo/dune_tension/experiments/UKAPA7_comparison/ukapa7_landscape_G.png)

- Side A: mean change `-0.38 N`, mode `-0.45 N`, `84%` of wires lower in Chicago.
- Side B: mean change `-0.20 N`, mode `-0.43 N`, `71%` of wires lower in Chicago.
- Residual (change) widths are about `0.4 N` on both sides.

---
Orange lines are the UK, blue lines are chicago. Left is the A side, right is the B side
The lines are moving average of 3.
The wire numberings go from bottom to top on the A side and top to bottom on the B side.

---

![G change in tension](/Users/ben/dune-monorepo/dune_tension/experiments/UKAPA7_comparison/ukapa7_change_in_tension_G.png)

The sign is change in tension over time.
Blue is the A side, Green is the B side.

---

## U Layer

- Side A subset: mean residual `-0.54 N`, mode `-0.49 N`, `85%` of aligned
  wires lower in Chicago.
- Side B subset: mean residual `-0.87 N`, mode `-0.52 N`, `99%` of aligned
  wires lower in Chicago.
- Residual widths are about `0.5 N` on both sides.

2.3/5.75*8*0.218 = .7mm over the length of a long wire for a -0.5 change in tension assuming youngs mod E = 130Gpa

---

![U both sides](/Users/ben/dune-monorepo/dune_tension/experiments/UKAPA7_comparison/ukapa7_landscape_U.png)

Orange lines are the UK, blue lines are chicago. Left is the A side, right is the B side
The lines are moving average of 3.

The ordering of the segments goes from the top left corner short wires to bottom right corner short wires on the A side
From the bottom left corner to the top right corner on the B side.
Wire 751 is the one that goes down to the corner of the apa on the B side
---

![U change in tension](/Users/ben/dune-monorepo/dune_tension/experiments/UKAPA7_comparison/ukapa7_change_in_tension_U.png)

The sign is change in tension over time.
Blue is the A side, Green is the B side
a handful of wires "seemed" to have a huge drop in tension but are more likely erroneously high as measured initially: they seem the be like other wires nearby.

0.87*2.3/5.75*8 = 2.784mm for full length wire
---

## Interpretation

- The robust observation is downward shift: Chicago values are lower on average, with a clear peak at `-0.5 N`
- The current Chicago values remain in specification: G ranges from `4.44` to
  `7.00 N`; U ranges from `4.03` to `6.41 N`.
- The data do not show an out-of-spec tension signature after storage and shipment.

---

## Recommendation

- Tension measurement has long tails, which can erroneously appear as huge shifts in tension.
- As a result, changes alone cannot be the acceptance criterion.
- Establish an acceptance range of tensions after relaxation

---

![all g wires](/Users/ben/dune-monorepo/dune_tension/data/tension_plots/tension_profile_cloud_G_dunedb_noscale_avgwire_cov0p5_bins40_win5_daresbury.pngg)

---

![all u wires](/Users/ben/dune-monorepo/dune_tension/data/tension_plots/tension_profile_cloud_U_dunedb_noscale_avgwire_cov0p5_bins40_win5_daresbury.png)
