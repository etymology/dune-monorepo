# dune_tension — Operator Manual

A step-by-step guide for taking APA wire-tension measurements with the laser
tensiometer. Written against the simplified measurement GUI
(`src/dune_tension/gui/simple_app.py`) with notes on where the full GUI is
needed.

---

## 0. Which GUI to launch

There are two GUIs that share the same measurement engine; the difference is how
many controls are exposed.

| GUI | Command | Notes |
| --- | --- | --- |
| **Simplified** | `dune-tension-gui-simple` | Recommended. Covers the full routine — including U/V **laser-offset capture** and **focus** — on one clean panel. |
| **Full** | `dune-tension-gui` | Same engine plus advanced extras: manual G-code moves, zone/clear-range/set-tension, outlier erase, background-noise calibration, etc. |

> The simplified GUI now includes the **Laser Offset** and **Focus** panels, so
> you can do a complete side (setup → calibrate → measure) without leaving it.
> The **Laser Offset** panel appears only for **U/V** layers in legacy mode; it
> stays hidden for X/G (which don't use it). Reach for the full GUI only when you
> need one of the advanced controls above.

**Easiest:** launch the simplified GUI from the **shortcut on the launcher** —
no terminal needed.

To launch from a terminal instead (project Python environment active):

```powershell
dune-tension-gui-simple   # simplified (recommended)
dune-tension-gui          # full
```

---

## 1. Physical setup of the tensiometer

Do these in order before powering through software.

1. **USB hub** — Plug the USB hub into the computer using the USB port **closer
   to the user**. The farther port is broken and will not enumerate the
   devices.
2. **Winder interface (on the desktop PC)** — Confirm the **dune_winder
   interface is running on the desktop PC**. The tensiometer drives the winder
   through it; nothing will move if it is not up.
3. **Network** — Confirm the measurement computer is **connected to the DUNE
   network**. The tensiometer talks to the desktop over the network: it
   **downloads the U/V calibration file** from the desktop and **issues all
   winder commands** (motion, seek-to-pin, position reads) over that connection.
   No network ⇒ no calibration and no motion. (Default desktop address
   `http://192.168.137.1:8080`; the tension server is at `:5000`.)
4. **Install the tensiometer** on the carriage.
5. **Spring contacts** — Make sure the spring contacts are seated and making
   contact. They power the laser, so **the laser turning on is your confirmation
   contact is good.** No laser ⇒ no contact.
6. **Opposite contacts** — Check that the contacts on the *opposite* side are
   **not shorted**.
7. **Tension servo J-box** — Confirm the **orange switch** in the tension-servo
   J-box is in the **ON** position. When it is on, the window shows **red**.
8. **Air** — Connect the air-pressure quick-connect to the **bottom** fitting.
   Set pressure **between 30 and 60 psi**.

---

## 2. Software setup / pre-flight

1. Launch the GUI (§0).
2. Click **Refresh Connections** (bottom of the left panel). It retries for up
   to ~30 s and logs each subsystem as `✓`/`✗` in the **Log** panel on the
   right. Do not start measuring until everything reads `✓`.
3. In the **APA** panel set:
   - **APA Location** — `US` or `UK`
   - **APA Number** — the 3-digit APA number (`001`…`152`)
   - **Layer** — `X`, `V`, `U`, or `G`
   - **Side** — `A` or `B`
   - **A taped / B taped** — tick if that side's wires are taped (affects U/V
     wire planning).
4. **Calibration files (U and V only):** confirm a **current calibration file
   exists for the current support configuration, covering all pins**, for the
   layer you are about to measure. The GUI reads
   `config/APA/<LAYER>_Calibration.json`; selecting a U/V layer triggers a
   calibration sync/health check and the **Laser Offset** panel's readout
   reports any sync error. If the file is missing or stale, regenerate/sync
   it before continuing — measurement of U/V wires will refuse to run without a
   valid calibration.

---

## 3. Per-side calibration

This is where U/V and X/G differ. Do this **once per side**.

### 3a. U and V layers — capture the laser→wire offset

The offset relates the camera/laser position to the calibrated pin geometry. It
is stored in `config/APA/TensionLaserOffsets.json`, separately for side A and
side B. **U/V measurement will not run until an offset exists for the active
side** (you'll see `No saved laser offset exists for side …`).

The **Laser Offset** panel is in the **Measurement** section and appears
automatically once you select a **U or V** layer (it stays hidden for X/G):

1. Select the correct **Layer** (U or V) and **Side**.
2. In **Laser Offset → Bottom Pin**, choose the **first or last pin of the
   bottom side** (the dropdown offers "Bottom first" / "Bottom last").
3. Drive the laser to that pin (jog, or **Seek Camera To Pin**) until the laser
   is on the pin.
4. Click **Capture Laser Offset**. The readout updates to
   `Side X: x=… mm, y=… mm, pin=…, layer=…`.
5. (Optional check) **Move Laser To Pin** should now drive back onto the pin
   using the saved offset.

Once the offset is captured for the side, you can **Measure All** / **Measure
Wires** for that side (§5).

### 3b. X and G layers — calibrate against a known wire

X/G have no laser-offset step; instead you anchor the coordinate system to one
wire of known number:

1. Move the winder to **X = 6300** and to the **Y of the lowest-numbered wire**
   (or any wire whose number you know for certain).
2. Enter that **wire number** in the **Wire(s)** field.
3. Click **Measure Calibrate**. (Measure Calibrate requires a *single* wire
   number — it will reject lists/ranges and tell you to use Measure Wires.) For
   X/G this measures the wire **at the current XY position** and uses it as the
   reference for locating every other wire.
4. After a good calibration measurement you can **Measure All** / **Measure
   Wires** (§5).

---

## 4. Before every measurement: capos and focus

### Capos

Install the capos before measuring:

- **Plastic touches plastic, foam touches wire.**
- Mount them on the **opposite side of the comb from where you are measuring.**
- **Do not over-tighten** — apply no excess pressure, but they **must at least
  be touching the comb.**

### Focus

The **Focus** panel is at the bottom of the **Measurement** section (slider +
**Manual Focus** checkbox).

- For a single fiddly wire, tick **Manual Focus** and drag the **focus slider**
  (4000–8000) to drive the servo until the wire is sharp.
- Once you have a good focus position, **untick Manual Focus** to let the system
  **autofocus** during measurement for the rest.
- The X-position is automatically compensated as focus changes (so the laser
  stays on the wire) unless X-compensation is disabled.

> The laser "mic" only powers on **while a measurement is actively running** (to
> save power). If the winder is idle you will not hear it — that is normal. When
> a wire is being measured you should be able to **hear the wire** as it is
> excited.

---

## 5. Measuring

All of these are in the **Measurement** panel and work in both GUIs.

| Button | What it does |
| --- | --- |
| **Measure Calibrate** | Measure a **single** wire (number from **Wire(s)**). U/V plan the position from calibration; X/G measure at the current XY (this is the §3b calibration step). |
| **Measure Wires** | Measure a **comma-separated list / ranges** from **Wire(s)**, e.g. `5, 10, 20-30`. Honors **Skip measured**. |
| **Measure All** | Measure every **missing** wire on the current layer/side automatically. |
| **Refine** | Re-measure the **outliers** (residual + bulk-distribution) on the current side — use this to clean up wires that look wrong on the plot. |
| **Measure Condition** | Measure wires matching the **Condition** expression (see below). |
| **Interrupt** | Stop the running measurement. ETA shows `Interrupted`. |

Supporting fields:

- **Wire(s)** — single number (Measure Calibrate) or list/ranges (Measure
  Wires). Lists accept `a-b` ranges and reversed ranges (`30-20`).
- **Skip measured** (default on) — already-measured wires are skipped by Measure
  Wires / Measure All.
- **Condition (AND/OR)** — expression over `t` (tension), `n` (wire number), and
  `z` (zone, U/V only). Examples: `t < 4.0 OR t > 7.0`, `n < 1000 AND t < 5`,
  `z = 3`. Used by **Measure Condition**.
- **Legacy Tension** — an optional per-measurement tension filter passed to the
  measurement engine.
- **ETA** — estimated time remaining for the current run.

**Typical flow once a side is set up:**

1. Set APA / Layer / Side, confirm connections `✓`.
2. Install capos, focus on a representative wire.
3. **Measure All** (or **Measure Wires** for a subset).
4. Watch the **Live Plots**; when it finishes, **Refine** any outliers, or use
   **Measure Condition** to chase specific bad tensions.

---

## 6. Reading results

- **Live Plots** (center): top = tension summary across the side, bottom =
  the live audio waveform of the wire being measured. Click **Refresh Plots** to
  force a re-read of the saved tension logs.
- **Log** (right): connection status, per-wire results, warnings, and any
  calibration/offset errors.

---

## 7. Uploading tensions

When a side/layer is complete, upload with the **upload-tensions** tool.

> **Status: work in progress.** The uploader lives at
> `src/dune_tension/uploadTensions.py` (and the M2M template
> `src/dune_tension/m2m/template_upload_tensions.py`). It reads the per-APA
> tension summary CSV and pushes side-A/side-B tensions to the database via the
> M2M API. Use the upload-tensions GUI/script as it stands; expect rough edges
> until it is finalized.

---

## 8. Quick troubleshooting

| Symptom | Likely cause / fix |
| --- | --- |
| Devices not detected | USB hub in the **wrong (far) port** — move it to the near port; then **Refresh Connections**. |
| Nothing moves | dune_winder interface not running on the desktop; not on the **DUNE network**; tension-servo orange switch not **ON** (window not red). |
| Can't reach winder / commands time out | Measurement computer not on the **DUNE network** (winder commands go over the network to the desktop, default `192.168.137.1`). |
| U/V calibration won't download / sync error | Network down or desktop interface not running — the calibration file is fetched from the desktop over the network (§2.4). |
| Laser off | Spring contacts not making contact (laser is powered by them); reseat. Check opposite contacts aren't shorted. |
| `No saved laser offset exists for side …` (U/V) | Capture the laser offset for that side via the **Laser Offset** panel (§3a). |
| Laser Offset panel not showing | It only appears for **U/V** layers — check the **Layer** dropdown. |
| U/V refuses to run / calibration sync error | Missing/stale `config/APA/<LAYER>_Calibration.json` for the current support config — regenerate/sync it (§2.4). |
| Can't hear the wire | Normal when idle — the mic only powers on during an active measurement. |
| No air / weak strum | Quick-connect on the **bottom**; pressure **30–60 psi**. |
| Capos | Plastic-to-plastic, foam-to-wire, opposite side of the comb from where you measure; touching but not over-pressed. |
