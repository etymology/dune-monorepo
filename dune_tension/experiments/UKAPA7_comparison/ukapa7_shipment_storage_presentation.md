---
marp: true
paginate: true
theme: default
class: invert
---

# APA-UK007 After Storage and Shipment

---

## What happened to APA-UK007

- `~2.25` years of storage and transatlantic shipment
- Chicago tensions on average lower by `-0.5N` with a spread in difference of `0.4N`
- All current Chicago G and U summary values are within the `4.0-8.5 N` spec.
- No obvious sign of shipping damage

---

## Measurement basis

- UK source data are the APA-UK007 action JSON records: U uploaded
  `2023-11-21`, G uploaded `2023-12-10`.
  - Probably laser+ziptie+labview
  - The U layer was measured without the G layer above it
- Chicago source data from March 11 2026
  - Chicago winder using laser+compressed air+python
- **G layer:** Full chicago coverage, with `481` wires on side A and `481` on side B.
- **U layer:** partial Chicago coverage only, with `385` aligned wires on side A
  and `641` on side B.

---

## Laser tension vs DWA

- U layer wires were accessed through a "slit" cut in the G wires.
- The pose for the G layer is comparable but not the U.
- The U layer pose is closer to that of the DWA measurement in ASF, but with winder support.
- Measurements on a the finished apa could not use "capos"

---

## G Layer statistics

- Side A: mean residual `-0.38 N`, mode `-0.45 N`, `84%` of wires lower in Chicago.
- Side B: mean residual `-0.20 N`, mode `-0.43 N`, `71%` of wires lower in Chicago.
- Residual widths are about `0.4 N` on both sides.

---

![g both sides](/Users/ben/dune-monorepo/dune_tension/experiments/UKAPA7_comparison/ukapa7_landscape_G.png)

---

![G change in tension](/Users/ben/dune-monorepo/dune_tension/experiments/UKAPA7_comparison/ukapa7_change_in_tension_G.png)

---

## U Layer

- Side A subset: mean residual `-0.54 N`, mode `-0.49 N`, `85%` of aligned
  wires lower in Chicago.
- Side B subset: mean residual `-0.87 N`, mode `-0.52 N`, `99%` of aligned
  wires lower in Chicago.
- Residual widths are about `0.5 N` on both sides.

---

![U both sides](/Users/ben/dune-monorepo/dune_tension/experiments/UKAPA7_comparison/ukapa7_landscape_U.png)

---

![U change in tension](/Users/ben/dune-monorepo/dune_tension/experiments/UKAPA7_comparison/ukapa7_change_in_tension_U.png)

---

## Interpretation

- The robust observation is downward shift: Chicago values are lower on average, with a clear peak at `-0.5 N`
- The spread of the changes is consistent with compounded measurement uncertainties
- The current Chicago values remain in specification: G ranges from `4.44` to
  `7.00 N`; U ranges from `4.03` to `6.41 N`.
- The data do not show an out-of-spec tension signature after storage and shipment.
- This is consistent with relaxation under tension and slight changes in frame shape
- I would expect `<0.5N` decrease in tension in the next four years

---

## Recommendation

- Tension measurements have long tails, which can erroneously appear as huge shifts in tension.
- As a result, changes alone cannot be the acceptance criterion.
- Establish an acceptance range of tensions after relaxation.

---

## Discussion

---

## Extra plots

---

![all g wires](/Users/ben/dune-monorepo/dune_tension/data/tension_plots/tension_profile_cloud_G_dunedb_noscale_avgwire_cov0p5_bins40_win5_daresbury.png)

---

![all u wires](/Users/ben/dune-monorepo/dune_tension/data/tension_plots/tension_profile_cloud_U_dunedb_noscale_avgwire_cov0p5_bins40_win5_daresbury.png)
