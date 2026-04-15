---
marp: true
paginate: true
theme: default
class: invert
---

# UKAPA7 After Storage and Shipment

- What happened to wire tensions after a of the APA and transatlantic shipment from the UK to Chicago?
- We compare UK factory measurements from December 10, 2023 against Chicago measurements from March 11, 2026.
- Headline result: Chicago tensions are on average lower (~0.5N) probably due to relaxation during storage.
- No tensions are out of spec [4-8.5], no evidence of shipping damage.

---

# What We're Comparing

- **G layer:** full comparison on both sides, `481` aligned wires on side A and `481` on side B.
- **U layer:** partial Chicago coverage only, with `385` aligned wires on side A and `641` on side B.
- U layer wires were accessed through a "slit" cut in the G wires near the middle of the APA.

---

# G Layer

- Most wires on both sides changed by `-0.45 N` (Chicago lower).
- On a wire-by-wire basis, differences range from `-1.63` to `+1.32` with `σ = 0.4`
- Actual increase in tension is less likely than compounded measurement uncertainties

---

![g both sides](/Users/ben/dune-monorepo/dune_tension/experiments/UKAPA7_comparison/ukapa7_landscape_G.png)

---

![G change in tension](/Users/ben/dune-monorepo/dune_tension/experiments/UKAPA7_comparison/ukapa7_change_in_tension_G.png)

---

# U Layer

- Most wires dropped about `-0.5N` 
- Differences from `-3.1` to `+0.68` `σ = 0.5`
- The negative outliers suggest measurement errors in the UK data
- Frame deformation after the G layer may have changed the shape of the U-layer tension distribution

 
---

![U both sides](/Users/ben/dune-monorepo/dune_tension/experiments/UKAPA7_comparison/ukapa7_landscape_U.png)

---

![U change in tension](/Users/ben/dune-monorepo/dune_tension/experiments/UKAPA7_comparison/ukapa7_change_in_tension_U.png)

---

# What This Says About Storage and Shipment

- ~0.5N decrease over 2.25y consistent with wire relaxation under stress
- Probably, +0.5N isn't real but the result of combined measurement uncertainty
- `-3N` is probably also not real, the result of mistaken measurements at Daresbury
- Changes in tension even large ones shouldn't disqualify acceptance if the final tension is acceptable.
 
---

![all g wires](/Users/ben/dune-monorepo/dune_tension/data/tension_plots/tension_profile_cloud_G_mode_allsamples_cov0p5_it3_bins40.png)

---
![all u wires](/Users/ben/dune-monorepo/dune_tension/data/tension_plots/tension_profile_cloud_U_noscale_allsamples_cov0p5_it3_bins40.png)