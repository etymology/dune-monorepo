# UV Layer Rewrite — Status & Plan

## Background (the desired workflow)

The desired UV workflow is similar to today's but differs in how the
machine calibration is solved, what calibration artifacts are stored,
and how they are used.

Today the UV calibration routines save JSON files with winder
("camera") coordinates that have had the **camera wire offset** baked
in. The `~anchorToTarget` macro consumes those adjusted positions to
solve for the winder pose that stretches a wire from anchor pin to
target pin, tangent to both pins on the correct sides, accounting for
the displacement between the camera position and the actual wire
position. That displacement is the camera wire offset plus the **arm
correction**.

The camera wire offset is *not* in fact constant — it varies with the
winder pose (e.g. how far the Z arm is extended). So baking it into
the calibration file is wrong. Instead, `anchorToTarget` should consume
**raw camera-space** pin coordinates and compute the camera wire
offset per-pose at solve time.

In a UV recipe there are 12 pin placements. Today the operator must
edit per-placement offsets on the gcode-generation page. The new
workflow records calibration points on `APA.html` after each gcode
line by jogging to the correct position and clicking "use current
position." Offsets are 3D `(x, y, z)` (currently 2D) and propagate to
every gcode line sharing a label. Once enough points are captured, the
machine-calibration solver fits per-pose camera wire offsets, two base
offsets (stage / fixed), and roller offsets, then regenerates the
gcode offsets from the new model.

The Z plane fit is replaced by a **continuous closed-loop spine**: the
spine is the closed perimeter loop at the APA Z midplane on which all
boards are physically centred. Pin coordinates derive from the spine
by displacing ± half the layer's board width along Z (board widths:
U 130 mm, V 120 mm, X 110 mm, G 140 mm). **Convention: A face is −Z,
B face is +Z** (committed `4a7e7615`).

Pins are renamed `{layer}{side}{number}` (e.g. `UA1`, `VB23`),
backed by a `Pin` type with derived `face`, `tangent_normal_sign`, and
`is_endpoint` properties (face/endpoint tables in the original spec
section preserved at the bottom of this file).

Geometry is centralized into a new `dune_geometry` Rust crate with
PyO3 bindings, consumed by both `dune_winder` and `dune_tension` from
Python today and directly from Rust services as the port progresses.

---

## Status — done

### Phase A0 — Allium specs (source of truth) ✅

- `specs/layer-geometry.allium` — `Pin` entity, layer/side/number/face,
  tangent normal signs, endpoint tables, board widths.
- `specs/uv-wrap-geometry.allium` — per-pose camera wire offset model,
  anchor-to-target obligations on raw camera-space inputs.
- `specs/uv-machine-calibration.allium` — capture-point shape, label
  propagation, 3D offsets, solver inputs/outputs.
- `specs/spine-calibration.allium` — `SpinePoint` / `SpineLoop` /
  `SpineCalibrationFile`, `DerivePinPositionFromSpine` (A=−Z, B=+Z),
  `SolveSpineLoopFromCalibrationTouches` with the three-prior fit
  obligation.

### Phase A — `dune_geometry` Rust crate skeleton + `Pin` type ✅

Crate at `rust/crates/dune_geometry/` registered in `rust/Cargo.toml`.
Modules: `pins.rs`, `wire.rs`, `calibration.rs`, `spine.rs`,
`tension.rs`, `python.rs`. PyO3 abi3-py312 bindings via maturin produce
a Python `dune_geometry` module. 57 Rust unit tests + Python
PyO3-surface tests in `tests/dune_geometry/` (e.g.
`test_pin_surface.py`, `test_calibration_surface.py`,
`test_anchor_to_target_math_smoke.py`).

### Phase B — rename pins to `{layer}{side}{number}` ✅

`Pin` instances or string form propagated through `dune_winder`,
`dune_tension`, and `dune_tension_core`. Calibration readers/writers,
gcode generation, logs, and UI labels updated.
`scripts/migrate_pin_names.py` exists for legacy persisted JSON.

### Phase C — `PinCalibration` schema (no offset baked in) ✅

`PinCalibrationFile` with append-only `PinCalibrationSnapshot` list
defined in `dune_geometry::calibration`. Pins serialise as object form
`{"layer", "side", "number"}`. PyO3-surfaced.
`scripts/convert_legacy_pin_calibration.py` migrates existing per-side
files into the new snapshot file.

### Phase D — `anchorToTarget` consumes raw coords + per-pose offset ✅

Wire-path math ported into `dune_geometry::wire`:
`solve_anchor_to_target` takes raw XYZ + `MachineCalibrationModel` and
returns the solved pose. Tension-side geometry moved into
`dune_geometry::tension` and re-exported by `dune_tension_core`.
Python `anchorToTarget` is a thin PyO3 wrapper. Golden parity fixtures
under `tests/golden/geometry/{compute_arm_corrected_outbound,actual_wire_point,…}/`.

Sub-tasks fully done:

- Port `_select_tangent_solution` into `dune_geometry::wire` (`8238ab53`).
- Finish `anchorToTarget` math port — arm-correction + roller-tilt
  (`c02580a3`).
- Analytic `tangent_for_pin_pair` single-tangent solver (`cae1f680`).

### Phase G (partial) — spine solver math ✅

`dune_geometry::spine`:

- `SpinePoint`, `SpineLoop`, `SpineCalibrationFile`, `CalibrationTouch`.
- `derive_pin_position_from_spine` and inverse
  `observe_spine_point_from_touch` (A=−, B=+ since `4a7e7615`).
- `solve_spine_loop` / `solve_spine_loop_with_config` — ridge-regularised
  plane fit (`Z = a·X + b·Y + c`) with tilt prior, then closed-loop
  Gaussian-smoothed residuals to fill unobserved pin numbers
  (`6d4aebdc`).
- X and G layer support (`9e53c77d`).
- PyO3 surface for `SpinePoint` / `SpineLoop` / `SpineCalibrationFile`
  / `solve_spine_loop`.

### Phase D consumers — step 1 of `SpineCalibrationFile` adoption ✅

- `dune_geometry::wire::solve_anchor_to_target_from_spine` — parallel
  surface that resolves XYZ via `SpineCalibrationFile.raw_pin_position`,
  then delegates to the existing XYZ solver. New error
  `WireError::MissingSpinePoint { pin }`.
- PyO3 wrappers `PySpineCalibrationFile.raw_pin_position`,
  `PyAnchorToTargetSpineRequest`,
  `py_solve_anchor_to_target_from_spine`.
- 4 Rust tests covering parity, layer mismatch, and missing-pin paths.
- Landed inside `1f94a86c`.

### Sign convention fix ✅

Spine `A=−Z, B=+Z` is now consistent across the spec
(`spine-calibration.allium`), Rust (`Pin::spine_to_face_sign`,
`derive_pin_position_from_spine` doc + tests), and the PyO3 surface
test. Commit `4a7e7615`.

---

## Status — in progress

### Phase E — APA.html one-click pose capture + 3D gcode offsets

Not started in code. Spec exists. The capture UI, the
"execution-paused" gate (server-side and client-side), the `(label,
gcode_line, calculated_xyz, recorded_xyz, head_side)` POST endpoint,
the immediate gcode rewrite for every line sharing the label, and the
`offset(x, y)` → `offset(x, y, z)` parser/emitter extension all need
implementation.

### Phase G consumer flip — `_wire_space_pin` onto the spine surface (step 2 of #13)

**Blocked.** The constant-Z fallback (207 ± half_w) we discussed is
mathematically compatible end-to-end after the sign fix, but ~24
existing tests encode legacy per-pin Z values and break by 3-30 mm
when a flat-plane spine replaces the per-pin Z. Two viable cuts (see
**Open decisions** below). Not flipped in code.

### Phase H — end-to-end verification

Pending Phase E + the rest of #13.

---

## Status — pending

### Phase F — machine-calibration solver page

`dune_geometry::calibration::solve_machine_calibration` not yet
written. UI rewiring also pending. Inputs: `CalibrationPoint`s, current
`PinCalibrationFile`, roller positions. Outputs:
`per_pin_camera_wire_offset`, `base_camera_wire_offset_stage` /
`_fixed`, updated `roller_offsets`. After save, regenerate gcode
offsets from the new model. Golden fixtures under
`tests/golden/geometry/machine_calibration/`.

### Remaining steps of #13 — adopt `SpineCalibrationFile` across consumers

- **Step 2 (blocked):** flip Python `_wire_space_pin` onto
  `SpineCalibrationFile.raw_pin_position`.
- **Step 3:** `Calibrate.html` backend writes a real
  `SpineCalibrationFile`; new
  `scripts/convert_legacy_pin_calibration_to_spine.py` synthesises
  spine points from existing per-side files using:

  ```
  V: BtoA(n) = A( 1 + ((399 - n) mod 2399) )
  U: BtoA(n) = A( 1 + ((400 - n) mod 2401) )
  ```

  i.e. `BtoA(n)` returns the A-side pin number that physically maps to
  B-side number `n` on the same perimeter location. The spine point at
  that perimeter is the XY mean of those two legacy entries (Z is the
  midpoint, or the spine plane if we trust the new model more than the
  legacy Z).
- **Step 4:** flip the tension-side loader (`dune_tension`) onto
  `SpineCalibrationFile` once Step 3 produces real files.
- **Step 5:** delete the legacy per-side `PinCalibrationFile`.

### `dune_winder/geometry/primitives/`

Today still has Python wire-path / pin-coordinate code that
predates the Rust port. Should be deleted or thinned to re-exports
from PyO3 `dune_geometry` once `_wire_space_pin` is fully on the spine
surface.

---

## Architectural decisions in force

- `dune_geometry` is a Rust crate at `rust/crates/dune_geometry/` with
  PyO3 bindings. No I/O, no winder hardware coupling. Imported by Rust
  services directly and by Python via PyO3.
- Existing tension geometry (`rust/crates/dune_tension_core/src/geometry.rs`)
  has been moved into `dune_geometry::tension` and re-exported from
  `dune_tension_core`.
- Allium specs are updated **first**; tests propagate from spec; Rust
  + PyO3 implementation is verified against them.
- Calibration schemas live in `dune_geometry::calibration` so producers
  (`Calibrate.html` backend) and consumers (`anchorToTarget`,
  machine-calibration solver, `dune_tension`) share one typed
  definition. The Python side gets PyO3-bound classes.
- `Pin` is the canonical identity for a pin everywhere.
  Stored in JSON as `{layer, side, number}` objects, not opaque
  strings. The string form is for display/logs only.
- `SpineCalibrationFile` is the sole source of raw pin coordinates
  going forward. Per-side `PinCalibrationFile` is migrated by the
  legacy-converter script (Step 3 above) and then deleted (Step 5).
- 3D offsets in gcode: `offset(x, y)` extended to `offset(x, y, z)`;
  old recipes get `z = 0` on read.
- Golden parity tests gate each migration step (`tests/golden/geometry/`).

---

## Open decisions

### How to land Step 2 of #13 without breaking the 24 calibration tests

Two options:

1. **Update fixtures + expected values** to spine-fallback Z
   (207 ± half_w). ~6 test files affected (`test_uv_head_target.py`,
   `test_uv_head_target_gui.py`, `test_uv_tangency_analysis.py`,
   `test_wrap_runtime.py`, `test_v_template_gcode.py`,
   `test_manual_calibration.py`, `test_uv_layout.py`). One is a
   golden-string output (`test_v_template_gcode`). This locks in a
   stand-in we will throw away once real spine capture exists.
2. **Defer Step 2 until Step 3 lands** — once `Calibrate.html` writes a
   real `SpineCalibrationFile`, the spine fallback becomes spine-truth
   and tests can be updated against captured data rather than a
   flat-plane stand-in.

Recommendation: option 2.

### Where the spine plane Z constant should live for the fallback

Currently `_DEFAULT_SPINE_Z_MM = 207.0` (zExtended/2) was the
candidate value. Once Step 3 lands this constant disappears. If we
take option 1 above, it would live in
`dune_geometry::spine::DEFAULT_SPINE_Z_MM` to be testable from Rust
and reachable from Python.

---

## File map

Created (all live):

- `rust/crates/dune_geometry/Cargo.toml`
- `rust/crates/dune_geometry/pyproject.toml`
- `rust/crates/dune_geometry/src/{lib,pins,wire,calibration,spine,tension,python}.rs`
- `rust/crates/dune_geometry/tests/...`
- `tests/dune_geometry/test_*.py` (PyO3 surface)
- `tests/golden/geometry/{actual_wire_point,compute_arm_corrected_outbound,…}/`
- `specs/{layer-geometry,uv-wrap-geometry,uv-machine-calibration,spine-calibration}.allium`
- `scripts/migrate_pin_names.py`
- `scripts/convert_legacy_pin_calibration.py`

Modified:

- `rust/Cargo.toml` (added `dune_geometry` to workspace members)
- `rust/crates/dune_tension_core/{Cargo.toml,src/geometry.rs}` (re-exports
  from `dune_geometry::tension`)
- `src/dune_winder/.../anchorToTarget.py` (PyO3 wrapper)
- `src/dune_tension/geometry.py` (re-exports from PyO3 `dune_geometry`)

To create:

- `scripts/convert_legacy_pin_calibration_to_spine.py`
- `tests/golden/geometry/{machine_calibration,spine_loop}/...` (currently
  only synthetic in-Rust fixtures exist)

To modify (for remaining phases):

- `src/dune_winder/.../Calibrate.html` and its FastAPI/handler module
  (Step 3)
- `src/dune_winder/.../APA.html` and its handler module (Phase E)
- `src/dune_winder/.../machine_calibration` page + handler module
  (Phase F)
- `src/dune_winder/.../gcode_generation/` (drop manual 12-offset UI;
  parser/emitter to support `offset(x, y, z)`)
- `src/dune_winder/uv_head_target_parts/calibration.py`
  (`_wire_space_pin` onto spine — Step 2 of #13)
- `src/dune_winder/geometry/primitives/` (delete or thin)

---

## Verification checklist

- `cargo test -p dune_geometry` — currently 57 tests passing.
- `pytest tests/dune_geometry/ tests/golden/geometry/` — passing.
- `pytest tests/dune_winder/ tests/dune_tension/` — passing on
  pre-Step-2 state.
- Manual end-to-end (Phase H, item 4 of original plan):
  1. Generate fresh `PinCalibration` via `Calibrate.html`.
  2. Run UV recipe on `APA.html`; capture all 12 placements.
  3. Run machine-calibration solver.
  4. Re-run recipe; confirm no manual gcode offsets needed.
- Manual: capture single point with a label and verify offset
  propagates to all same-label gcode lines.

---

## Original spec data (preserved for reference)

`_FACE_RANGES`:

```python
_FACE_RANGES = {
  "U": {
    "head":   (1, 400),
    "bottom": (401, 1200),
    "foot":   (1201, 1601),
    "top":    (1602, 2401),
  },
  "V": {
    "head":   (1, 399),
    "bottom": (400, 1199),
    "foot":   (1200, 1599),
    "top":    (1600, 2399),
  },
}
```

`tangent_sides`:

```python
def tangent_sides(layer: str, side: str, n: int) -> tuple[int, int]:
    x = 1 if (
        (layer == "U" and n <= 1200) or
        (layer == "V" and (n <= 399 or n >= 1600))
    ) else -1
    y = (1 if (layer, side) in {("U", "B"), ("V", "A")} else -1) * x
    return x, y
```

`_ENDPOINT_PINS`:

```python
_ENDPOINT_PINS = {
  "U": (
    1, 40, 41, 80, 81, 120, 121, 160, 161, 200, 201, 240, 241, 280, 281, 320,
    321, 360, 361, 400, 401, 424, 425, 449, 450, 473, 474, 510, 511, 547, 548,
    584, 585, 621, 622, 658, 659, 695, 696, 732, 733, 769, 770, 806,
    807, 843, 844, 880, 881, 917, 918, 954, 955, 991, 992, 1028, 1029, 1065,
    1066, 1102, 1103, 1139, 1140, 1176, 1177, 1200, 1201, 1240, 1241, 1280,
    1281, 1320, 1321, 1360, 1361, 1400, 1401, 1440, 1441, 1480, 1481, 1520,
    1521, 1560, 1561, 1601, 1602, 1625, 1626, 1662, 1663, 1699, 1700, 1736,
    1737, 1773, 1774, 1810, 1811, 1847, 1848, 1884, 1885, 1921, 1922, 1958,
    1959, 1995, 1996, 2032, 2033, 2069, 2070, 2106, 2107, 2143,
    2144, 2180, 2181, 2217, 2218, 2254, 2255, 2291, 2292, 2328, 2329, 2352,
    2353, 2377, 2378, 2401,
  ),
  "V": (
    1, 40, 41, 80, 81, 120, 121, 160, 161, 200, 201, 240, 241, 280, 281, 320,
    321, 360, 361, 399, 400, 423, 424, 448, 449, 472, 473, 509, 510, 546, 547,
    583, 584, 620, 621, 657, 658, 694, 695, 731, 732, 768, 769, 805,
    806, 842, 843, 879, 880, 916, 917, 953, 954, 990, 991, 1027, 1028, 1064,
    1065, 1101, 1102, 1138, 1139, 1175, 1176, 1199, 1200, 1239, 1240, 1279,
    1280, 1319, 1320, 1359, 1360, 1399, 1400, 1439, 1440, 1479, 1480, 1519,
    1520, 1559, 1560, 1599, 1600, 1623, 1624, 1660, 1661, 1697, 1698, 1734,
    1735, 1771, 1772, 1808, 1809, 1845, 1846, 1882, 1883, 1919, 1920, 1956,
    1957, 1993, 1994, 2030, 2031, 2067, 2068, 2104, 2105, 2141,
    2142, 2178, 2179, 2215, 2216, 2252, 2253, 2289, 2290, 2326, 2327, 2350,
    2351, 2375, 2376, 2399,
  ),
}
```

The `BtoA(n)` mapping the spine legacy converter will use:

```
V: BtoA(n) = A( 1 + ((399 - n) mod 2399) )
U: BtoA(n) = A( 1 + ((400 - n) mod 2401) )
```
