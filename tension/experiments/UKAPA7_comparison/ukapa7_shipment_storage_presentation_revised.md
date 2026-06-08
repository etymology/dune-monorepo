---
marp: true
paginate: true
theme: default
style: |
  section {
    background: #fbfbf8;
    color: #202020;
    font-family: "Avenir Next", "Helvetica Neue", Arial, sans-serif;
    letter-spacing: 0;
    padding: 44px 58px;
  }
  h1 {
    font-size: 48px;
    font-weight: 650;
  }
  h2 {
    font-size: 34px;
    font-weight: 650;
    margin-bottom: 22px;
  }
  p, li, td, th {
    font-size: 24px;
    line-height: 1.25;
  }
  ul {
    margin-top: 0;
  }
  table {
    border-collapse: collapse;
    width: 100%;
  }
  th {
    border-bottom: 2px solid #444;
    text-align: left;
    padding: 8px 10px;
  }
  td {
    border-bottom: 1px solid #d6d6d0;
    padding: 8px 10px;
    vertical-align: top;
  }
  code {
    color: #202020;
    background: #ecece6;
    padding: 0 0.15em;
  }
  .lede {
    font-size: 34px;
    line-height: 1.2;
    max-width: 980px;
  }
  .note {
    font-size: 20px;
    color: #4e565d;
  }
  .small li, .small td, .small th, .small p {
    font-size: 19px;
  }
  .figure-note {
    font-size: 18px;
    color: #4e565d;
    margin-top: 4px;
  }
  .cols {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 34px;
    align-items: start;
  }
  .wide-img img {
    display: block;
    margin: 0 auto;
    max-width: 100%;
    max-height: 530px;
  }
  .two-img {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 22px;
    align-items: center;
  }
  .two-img img {
    width: 100%;
  }
---

<!-- markdownlint-disable MD013 MD033 -->

# APA-UK007 After Storage and Shipment

<p class="lede">Chicago measurements are lower than the UK source records, but
the current measured G and U tensions remain inside the 4.0-8.5 N specification.</p>

<p class="note">Comparison of UK action JSON records with current Chicago
tension summary files.</p>

---

## Bottom Line

- APA-UK007 was stored for about `2.25` years and then shipped across the
  Atlantic.
- The comparable Chicago tensions are lower in every layer-side group.
- The typical shift is modest: about `-0.2` to `-0.4 N` for G and about
  `-0.5` to `-0.9 N` for the measured U subset.
- No current Chicago summary value in these G and U files is outside the
  `4.0-8.5 N` specification.

---

## Measurement Basis

<div class="small">

| Layer | UK source | Chicago source | Comparison note |
| --- | --- | --- | --- |
| G | APA-UK007 G action JSON, uploaded `2023-12-10` | `tension_summary_UKAPA7_G.csv` | Full A coverage; B uses corrected reverse/shift alignment |
| U | APA-UK007 U action JSON, uploaded `2023-11-21` | `tension_summary_UKAPA7_U.csv` | Partial Chicago coverage through access slit |

</div>

- Residuals are `Chicago - UK`; negative values mean Chicago measured lower.
- The UK measurements were probably laser + ziptie + LabVIEW.
- The Chicago measurements used the winder, laser, compressed air, and Python
  processing.

---

## Comparable Coverage

<div class="wide-img">

![Comparable wire coverage](ukapa7_revised_coverage_strip.png)

</div>

<p class="figure-note">The G comparison is effectively full coverage. The U
comparison is a measured subset, so its result should be read as a subset
comparison rather than a full-layer statement.</p>

---

## Measurement Comparability

- G-layer access and pose are the closest comparison between the UK and Chicago
  measurements.
- U-layer wires were accessed through a slit cut in the G wires.
- The U-layer pose is closer to the ASF DWA access geometry, but with winder
  support.
- Measurements on the finished APA could not use capos.

---

## Change in Tension

<div class="wide-img">

![Change in tension by layer and side](ukapa7_revised_residual_small_multiples.png)

</div>

<p class="figure-note">Each panel uses the same vertical scale. Points are
individual wires; the colored line is a local median trend.</p>

---

## G Layer Result

<div class="cols">

<div>

- Side A: mean residual `-0.38 N`, median `-0.43 N`.
- Side A: `84%` of aligned wires are lower in Chicago.
- Side B: mean residual `-0.20 N`, median `-0.30 N`.
- Side B: `71%` of aligned wires are lower in Chicago.

</div>

<div>

- Residual widths are about `0.4 N` on both sides.
- Some wires measured higher in Chicago, so the change is not a uniform
  wire-by-wire offset.
- The corrected B-side comparison uses `480` aligned wires.

</div>

</div>

---

## U Layer Result

<div class="cols">

<div>

- Side A subset: mean residual `-0.54 N`, median `-0.51 N`.
- Side A subset: `85%` of aligned wires are lower in Chicago.
- Side B subset: mean residual `-0.87 N`, median `-0.76 N`.
- Side B subset: `99%` of aligned wires are lower in Chicago.

</div>

<div>

- Residual widths are about `0.5 N` on both sides.
- U side A has `385` aligned wires; U side B has `641`.
- This is a partial-subset comparison and not a full U-layer survey.

</div>

</div>

---

## Current Tensions Relative to Specification

<div class="wide-img">

![Current Chicago tensions relative to specification](ukapa7_revised_current_tension_vs_spec.png)

</div>

<p class="figure-note">All plotted Chicago summary values are within the
4.0-8.5 N specification band.</p>

---

## What the Data Show

<div class="small">

| Observation | Interpretation |
| --- | --- |
| Chicago tensions are lower on average in G A, G B, U A, and U B. | The robust comparison result is a downward shift after storage and shipment. |
| Current measured values remain in specification. | The data do not show an out-of-spec tension signature. |
| Residuals have visible spread and long tails. | Per-wire change alone is not a stable acceptance criterion. |
| U coverage and access differ from G. | U results should be interpreted with the partial-coverage and access limits attached. |

</div>

---

## What the Data Do Not Separate

- The comparison does not uniquely identify the cause of the lower values.
- Plausible contributors include wire relaxation under tension, measurement
  method differences, access geometry, frame state, and handling effects.
- The data alone do not distinguish storage effects from shipment effects.
- The tension data do not replace visual or mechanical inspection for shipping
  damage.

---

## Recommendation

- Use relaxed absolute tension acceptance ranges, not change from the UK record
  alone.
- Treat long-tailed per-wire changes as diagnostic evidence, not pass/fail
  criteria.
- Keep the `4.0-8.5 N` current-tension range as the primary tension acceptance
  check unless a project-level relaxed range supersedes it.
- Based on the current interpretation, an additional decrease below `0.5 N`
  over the next four years would be expected.

---

## Backup: G Raw Tensions

<div class="wide-img">

![G layer raw tension landscape](ukapa7_landscape_G.png)

</div>

---

## Backup: U Raw Tensions

<div class="wide-img">

![U layer raw tension landscape](ukapa7_landscape_U.png)

</div>

---

## Backup: Population Profiles

<div class="two-img">

![G wire tension profile](../../data/tension_plots/tension_profile_cloud_G_dunedb_noscale_avgwire_cov0p5_bins40_win5_daresbury.png)

![U wire tension profile](../../data/tension_plots/tension_profile_cloud_U_dunedb_noscale_avgwire_cov0p5_bins40_win5_daresbury.png)

</div>

---

## Discussion

- Are the current G and U measured values acceptable under the project tension
  criteria?
- What external inspection evidence should be paired with this tension
  comparison?
- Should future acceptance use a relaxed absolute range rather than historical
  per-wire change?
