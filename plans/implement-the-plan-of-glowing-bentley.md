# UV Layer Rewrite — Implementation Plan

## Context

The current UV diagonal-layer workflow bakes the **camera wire offset** into calibration JSON files at calibration time. In practice this offset is **not constant**: it varies with winder pose (e.g. how far the Z arm is extended). The wire under tension pulls the winding head and rollers laterally, and the resulting frame distortions depend on pose. Today, the operator works around this by hand-editing offsets for each of the 12 placement points on the gcode-generation page.

We want to:

1. Store calibration files as **raw camera-space coordinates** (no offset baked in).
2. Have `anchorToTarget` compute the camera wire offset **per pose** at solve time.
3. Replace the 12-point manual gcode-offset entry with a one-click pose-capture UI on `APA.html`.
4. Promote per-line gcode offsets from 2D `(x, y)` to 3D `(x, y, z)`, propagated per gcode label.
5. Fit camera wire offsets and roller offsets from the captured points using a new machine-calibration solver.
6. Solve B pins as a **continuous (not necessarily planar) loop**, with A pins displaced by the board width (130 mm U / 120 mm V).
7. Centralize geometry into a new `dune_geometry` module, consumed by both `dune_winder` and `dune_tension`.
8. Adopt new pin naming `{layer}{side}{number}` (e.g. `UA1`, `VB23`) backed by a `Pin` type.

## How this fits the long-term Rust port

`plans/portconsideration.md` calls for the live system to migrate to a typed Rust core with shared crates and Python kept only as a temporary bridge. Today's actual state of that port:

- The Rust workspace lives at `rust/Cargo.toml` (not root). Existing crates: `dune_plc_bus` (Phase A/B PLC migration, with PyO3), `dune_tension_core` (measurement orchestrator with PyO3, already contains a geometry submodule at `rust/crates/dune_tension_core/src/geometry.rs` covering bounds, zone lookup, position refinement), `dune-audio` (cpal + FFT + ONNX), `dune-python` (PyO3 wrapper).
- Winder geometry (pin coordinates, wire-tangent math, anchor-to-target) is **still pure Python** at `src/dune_winder/geometry/primitives/`.
- Authoritative behavioural specs already exist in Allium: `specs/layer-geometry.allium`, `specs/uv-wrap-geometry.allium`.
- No `tests/golden/` directory yet, no `dune-api-types` crate, no TS bindings.

**Decision:** create `dune_geometry` as a **new Rust crate at `rust/crates/dune_geometry/` with PyO3 bindings**, following the same pattern as `dune_plc_bus` and `dune_tension_core`. The crate is the single source of pin geometry, wire-path math, calibration schemas, and the continuous-loop solver, callable from Rust services and from Python via PyO3 today. This is the option the port plan prescribes ("parallel first, share artifacts and calibration data, prove behavior with golden tests, then transfer live responsibility one narrow boundary at a time").

Workflow: **Allium spec → propagate tests → implement crate → adopt from Python via PyO3 → adopt from Rust services directly**. This matches the existing memory note that "Allium specs are the source of truth".

## Outcomes (what changes for the operator)

- `Calibrate.html` records B-side pin XY by camera, derives A-side from nominal geometry + board width, and writes the new raw-coordinate calibration schema.
- `APA.html` shows a "Calibration capture" panel next to the executing-gcode panel. After running a gcode line, the operator manually jogs the winder to the correct position and clicks **"Use current position"**. The system records `(label, gcode_line, calculated_xyz, recorded_xyz)` and immediately rewrites the loaded gcode so all lines sharing that label receive an `offset(x, y, z)` that moves the winder from calculated → recorded.
- Machine-calibration page lists all captured points, runs the new solver, and writes per-pose camera wire offsets, two basic offsets (stage / fixed), and roller offsets to the machine-calibration file. After solve, gcode offsets are regenerated from the new model.
- Gcode-generation page no longer requires hand-edited per-placement offsets.

## Architectural decisions

- **`dune_geometry` is a Rust crate** at `rust/crates/dune_geometry/` with PyO3 bindings exposed as a Python module `dune_geometry`. No I/O, no winder hardware coupling. Imported by Rust services directly and by Python via PyO3.
- **Extract, don't duplicate.** The geometry already in `rust/crates/dune_tension_core/src/geometry.rs` (bounds, zones, position refinement) is moved into `dune_geometry`, and `dune_tension_core` re-imports from it. The winder-side geometry currently in `src/dune_winder/geometry/primitives/` is rewritten into Rust as part of this rollout.
- **Allium specs are updated first** (`specs/layer-geometry.allium`, `specs/uv-wrap-geometry.allium`, plus a new `specs/uv-machine-calibration.allium`). Tests are propagated from spec; Rust + PyO3 implementation is verified against them.
- **Calibration schemas live in `dune_geometry::calibration`** so producers (`Calibrate.html` backend) and consumers (`anchorToTarget`, machine-calibration solver, `dune_tension`) share a single typed definition. The Python side gets autogenerated Pydantic-compatible models via PyO3.
- **`Pin` type** is the canonical identity for a pin everywhere in the codebase. String form `f"{layer}{side}{number}"`. Defined in Rust, exposed to Python. **Stored in JSON as serialized objects with `{layer, side, number}` properties — not as opaque strings.** The string form is only for display/logs.
- **Pin calibrations are snapshot-based** (replacing today's `{layer}_Calibration.json` strings-of-pins format). One combined file per machine (`config/APA/pin_calibrations.json`) holds an append-only list of snapshots, each timestamped and possibly partial (a snapshot may carry only some pins). Effective pin coordinates resolve to the most recent snapshot containing that pin. Both U and V live in the same file because snapshots are independent of layer.
- **Per-pose camera wire offset** — solver-time function of pose, parameterised from the machine-calibration model (two base offsets + per-placement corrections).
- **Continuous B-loop** — the planar Z fit is replaced by a continuous closed loop of B-pin XYZ points fitted to the wire-touches-pin constraint and recorded winder positions. A points are derived as `B + board_width_normal`.
- **3D offsets in gcode** — extend the existing `offset(x, y)` mechanism to `offset(x, y, z)`. Old recipes get migrated by setting `z = 0`.
- **Golden parity tests** — a new `tests/golden/geometry/` directory with Python fixtures and Rust comparison harnesses gates each migration step.

## Phased implementation

### Phase A0 — Update Allium specs (source of truth)

Edit existing specs so the rest of the work has a target to point at.

- `specs/layer-geometry.allium` — add the new pin naming (`{layer}{side}{number}`), the `Pin` entity with `layer`, `side`, `number`, derived `face`, `tangent_normal_sign`, `is_endpoint`, `board_width_mm`. Encode the `_FACE_RANGES` and `_ENDPOINT_PINS` tables. Encode pin-count rules (U: 1–2401; V: 1–2399).
- `specs/uv-wrap-geometry.allium` — replace the constant-camera-wire-offset assumption with a per-pose offset model: `(base_stage, base_fixed, per_pin overrides) → effective_offset(pose)`. Encode the anchor-to-target solve obligations (raw camera-space inputs, pose-dependent offset, arm correction, tangent-side from `Pin.tangent_normal_sign`).
- New `specs/uv-machine-calibration.allium` — the calibration capture workflow on `APA.html`: capture point shape, label propagation rule (offset applies to every gcode line sharing the label), 3D offset (`x, y, z`), persistence model. The machine-calibration solver: inputs (`PinCalibration`, `CalibrationPoint`s, roller positions), outputs (`per_pin_camera_wire_offset`, `base_camera_wire_offset_stage/fixed`, `roller_offsets`), and the regenerate-gcode-offsets step. The continuous B-loop solver obligation.

Run `tend` / `weed` to confirm the specs validate and `propagate` to materialise tests as the next phase's harness.

### Phase A — `dune_geometry` Rust crate skeleton + `Pin` type

Create `rust/crates/dune_geometry/` and add it to `rust/Cargo.toml`'s workspace members.

Modules:

- `src/lib.rs` — re-exports.
- `src/pins.rs`:
  - `FACE_RANGES` and `ENDPOINT_PINS` consts mirroring the source plan.
  - `pub fn tangent_sides(layer: Layer, side: Side, n: u16) -> (i8, i8)` matching the Python reference.
  - `pub enum Layer { U, V }`, `pub enum Side { A, B }`, `pub enum Face { Head, Bottom, Foot, Top }`.
  - `pub struct Pin { layer: Layer, side: Side, number: u16 }` with constructor that validates ranges (U: 1–2401, V: 1–2399).
  - `Display` → `"UA1"` etc.; `FromStr` parser.
  - Methods: `face()`, `tangent_normal_sign() -> (i8, i8)`, `is_endpoint() -> bool`, `board_width_mm() -> f64` (130 U / 120 V).
- `src/python.rs` — PyO3 bindings exposing `Pin`, `Layer`, `Side`, `Face`, the constants, and `tangent_sides`.
- `pyproject.toml` + `maturin` build so `pip install -e rust/crates/dune_geometry` produces a Python module `dune_geometry`.

Tests (Rust, in `tests/`): enumerate every pin number per layer; assert face ranges, tangent signs, endpoint membership, and string round-trip.
Tests (Python, in `tests/dune_geometry/`): import the PyO3 module and re-check the spot examples from the source plan.
Golden parity (`tests/golden/geometry/pins/`): JSON fixtures of `(layer, side, number) → {face, tangent, is_endpoint}` for the entire pin range — both Rust and Python tests consume the same fixture file.

### Phase B — Adopt `Pin` everywhere; rename pins to `{layer}{side}{number}`

Sweep `src/dune_winder/`, `src/dune_tension/`, `rust/crates/dune_tension_core/`, and any persisted JSON for existing pin identifiers, and replace them with `Pin` instances or their string form.

- Update calibration file readers/writers to use the new naming.
- Update gcode generation (`src/dune_winder/.../gcode_generation/`) to label placements with `Pin`.
- Update logs / UI labels in `Calibrate.html`, `APA.html`, machine-calibration page.
- One-shot script `scripts/migrate_pin_names.py` rewrites any legacy persisted JSON in `data/`, `calibration/`, and similar locations to the new naming.

### Phase C — New `PinCalibration` schema (no offset baked in)

In `rust/crates/dune_geometry/src/calibration.rs`, define:

- `PinCalibrationSnapshot`:
  - `taken_at: DateTime<Utc>`
  - `calibration_camera_id: String`
  - `operator: Option<String>`
  - `notes: Option<String>`
  - `pins: BTreeMap<Pin, Vec3>` — raw camera-space `(x, y, z)`, the winder XYZ recorded with the calibration camera looking at the pin, **with no camera-wire-offset and no arm-correction added**. May be partial (a snapshot can contain only the pins re-calibrated in that session).
- `PinCalibrationFile`:
  - `machine_id: String`
  - `snapshots: Vec<PinCalibrationSnapshot>` — append-only, oldest → newest.
  - Method `effective_pin_coords()` walks snapshots newest-first and returns the latest known coordinate for each `Pin`. U and V coexist in one file.
  - JSON path: `config/APA/pin_calibrations.json` (replaces `config/APA/U_Calibration.json` and `V_Calibration.json`).
- Pins serialise as `{"layer": "U", "side": "A", "number": 234}` (object form), never as `"A234"`-style strings.
- `MachineCalibration`:
  - `base_camera_wire_offset_stage: Vec3`
  - `base_camera_wire_offset_fixed: Vec3`
  - `per_pin_camera_wire_offset: HashMap<Pin, Vec3>`
  - `roller_offsets: RollerOffsets`
  - `source_points: Vec<CalibrationPoint>`
- `CalibrationPoint`:
  - `gcode_label: String`
  - `gcode_line: String`
  - `calculated_xyz: Vec3`
  - `recorded_xyz: Vec3`
  - `head_side: HeadSide` (`Stage` | `Fixed`)
  - `pin: Option<Pin>`

`serde` for JSON. PyO3 bindings expose them as Python classes (Pydantic-friendly via `__init__` / `dict()` helpers, or use `pydantic-core` interop if it's already in the project; otherwise plain `@dataclass`-style mirrors generated by `pyo3`).

Provide a one-shot legacy converter (`scripts/convert_legacy_pin_calibration.py`) that:

1. Reads existing `config/APA/U_Calibration.json` and `V_Calibration.json` (string-keyed pin maps like `"A234"`).
2. Re-keys to `Pin` objects (`{layer, side, number}`).
3. Subtracts any baked-in camera-wire-offset / arm-correction so the values are raw camera-space.
4. Emits a single `config/APA/pin_calibrations.json` whose `snapshots` list begins with one entry timestamped at the legacy file's `mtime`, marked `notes: "Imported from legacy {layer}_Calibration.json"`.

`Calibrate.html` flow:

- Operator drives camera to each B pin, records winder XYZ.
- A pins generated by transformation from nominal geometry: B coordinates plus the board-width normal (130 mm U / 120 mm V).
- Backend appends a new `PinCalibrationSnapshot` (calling Rust via PyO3). The snapshot may be partial — only the pins touched in that session are recorded.

### Phase D — `anchorToTarget` consumes raw coords + per-pose offset

Move wire-path geometry into `rust/crates/dune_geometry/src/wire.rs` (pure functions). Move the existing tension geometry from `rust/crates/dune_tension_core/src/geometry.rs` into `dune_geometry::tension` and have `dune_tension_core` re-export from there.

`anchorToTarget` (currently Python at `src/dune_winder/.../anchorToTarget.py`):

1. Reads anchor and target raw camera-space coordinates from `PinCalibration`.
2. Looks up per-pose camera wire offset from `MachineCalibration` (per-placement value if present, otherwise the appropriate base value for stage/fixed).
3. Adds arm correction.
4. Solves the winder pose so the wire is tangent to both pins on the correct sides, using `Pin.tangent_normal_sign`.

The solve itself moves into `dune_geometry::wire::solve_anchor_to_target`. Python `anchorToTarget` becomes a thin wrapper that calls the Rust function via PyO3 and applies the result to the winder. Same function is callable directly from a future Rust winder service.

Golden parity (`tests/golden/geometry/anchor_to_target/`): JSON fixtures of `(anchor_pin, target_pin, calibration, machine_cal) → solved_pose`. Compare current Python output (frozen as of pre-change baseline) and new Rust output for cases where the offset model collapses to a constant; document expected drift for the per-pose model.

### Phase E — `APA.html` one-click pose capture + 3D gcode offsets

UI on `APA.html`, next to the executing-gcode panel:

- Panel "Calibration capture":
  - Read-only display of the most-recently-executed gcode line and its label.
  - Calculated target XYZ.
  - Button **"Use current position"** — **disabled unless gcode execution is paused**. Avoids racing the controller mid-move and prevents capturing a transient pose.
- Pressing the button:
  1. Reads live winder XYZ from the controller.
  2. POSTs to `POST /machine_calibration/points` with `{label, gcode_line, calculated_xyz, recorded_xyz, head_side}`. Persistence path is the same one the existing machine-calibration page already uses.
  3. Server appends the `CalibrationPoint` to the active machine-calibration JSON.
  4. Server **regenerates the loaded recipe gcode immediately**: identifies the last-executed gcode line, computes `offset(x, y, z) = recorded_xyz - calculated_xyz`, and applies that offset to every gcode line sharing the captured `label`. The regenerated recipe is written back to the recipe file on disk and reloaded into the active session, so a paused-then-resumed run picks up the new offsets.
  5. Toast confirmation.

Backend:

- Extend `offset(x, y)` parser/emitter to `offset(x, y, z)`. Old recipes get `z = 0` on read.
- New endpoint enforces "execution paused" server-side as well as in the UI: refuse the POST if the controller reports it is mid-execution.
- `CalibrationPoint`s constructed via the PyO3 binding from `dune_geometry`.

### Phase F — Machine-calibration solver page

On the existing machine-calibration page:

- Display all collected `CalibrationPoint`s.
- **"Solve"** button calls the solver in `dune_geometry::calibration::solve_machine_calibration`:
  - Inputs: `CalibrationPoint`s, current `PinCalibration`, roller positions, gcode line for each point.
  - Outputs:
    - `per_pin_camera_wire_offset` for every captured placement.
    - `base_camera_wire_offset_stage` and `_fixed` (defaults for un-captured poses, by partitioning points by which side of the head was extended).
    - Updated `roller_offsets`.
- Save into the `MachineCalibration` file.
- After save, regenerate gcode offsets from the new machine-calibration model (so the loaded recipe gcode reflects the fitted offsets).

Golden parity (`tests/golden/geometry/machine_calibration/`): synthetic `CalibrationPoint` sets with known ground-truth offsets; assert solver recovers them within tolerance.

### Phase G — Continuous-loop SPINE solver

Replace the current planar Z fit. **Revised model:** instead of solving
the B side as a continuous loop and deriving A by `B +
board_width_normal`, solve the **spine** — the closed continuous loop
running around the perimeter at the APA Z midplane on which every
layer's boards are physically centred. A and B side coords are then
both derived from the spine by displacing ± half the layer's board
width along Z. Per-layer board widths: X = 110 mm, V = 120 mm, U =
130 mm, G = 140 mm.

Why the spine, not B: the two pin-bearing faces are bolted to opposite
sides of the same physical board. Storing them independently doubles
the free parameters and lets calibration drift accumulate
asymmetrically. The spine carries the geometry the boards actually
share; A and B are geometric consequences, not calibration targets.

New `rust/crates/dune_geometry/src/spine.rs`:

- `SpinePoint { layer, number, xyz }` — spine XYZ in raw camera-space.
- `SpineLoop { layer, points }` — ordered closed loop, indexed by pin
  number 1..pin_count(layer).
- `SpineCalibrationFile { machine_id, loops }` — replaces the per-side
  `PinCalibrationFile` for any reader that needs raw pin coords. Per
  side is derived at lookup time.
- `derive_pin_position_from_spine(spine_xyz, layer, side)` — returns
  raw XYZ for a `(layer, side, number)` pin by adding ± half board
  width along Z.
- `solve_spine_loop(layer, touches)` — fits a closed continuous 3D
  loop from `CalibrationTouch { pin, winder_xyz }` records. Each touch
  contributes one observation of the spine point at `pin.number`
  (after subtracting the side-dependent half board width along Z).
  The fit propagates around the closed perimeter; missing pin numbers
  are interpolated.

Spec source of truth: new `specs/spine-calibration.allium` plus updated
`specs/layer-geometry.allium` (per-layer `*_board_width_z_mm` configs).

Tests:
- Rust unit tests for `derive_pin_position_from_spine` symmetry, board
  width per layer, sign convention.
- Synthetic non-planar spine loops with known ground truth, asserting
  the solver recovers them within tolerance.
- Golden fixtures in `tests/golden/geometry/spine_loop/` (synthetic
  inputs and expected fitted output, regenerable from the reference
  Python implementation if/when one exists).

Migration:
- `scripts/convert_legacy_pin_calibration_to_spine.py` reads any
  existing per-side `PinCalibrationFile`s and emits a
  `SpineCalibrationFile` whose spine for each pin number is the
  midpoint of the legacy A and B Z values (X/Y averaged when both
  sides are present, taken from the available side otherwise).

### Phase H — End-to-end verification

1. `cargo test -p dune_geometry` green.
2. `pytest tests/dune_geometry/` and `pytest tests/golden/geometry/` green.
3. Smoke test that `dune_tension_core` still builds and behaves identically after the geometry extraction.
4. In dev, run a full UV recipe:
   1. Generate a fresh `PinCalibration` via `Calibrate.html`.
   2. Run a UV recipe on `APA.html`; capture all 12 placements one-by-one.
   3. Run the machine-calibration solver.
   4. Re-run the recipe and confirm no manual gcode offsets are needed.
5. Confirm the legacy calibration converter handles existing files in `data/` / `calibration/`.

## File map

To be created:

- `rust/crates/dune_geometry/Cargo.toml`
- `rust/crates/dune_geometry/pyproject.toml` (maturin)
- `rust/crates/dune_geometry/src/lib.rs`
- `rust/crates/dune_geometry/src/pins.rs`
- `rust/crates/dune_geometry/src/wire.rs`
- `rust/crates/dune_geometry/src/calibration.rs`
- `rust/crates/dune_geometry/src/loop.rs`
- `rust/crates/dune_geometry/src/tension.rs` (extracted from `dune_tension_core/src/geometry.rs`)
- `rust/crates/dune_geometry/src/python.rs`
- `rust/crates/dune_geometry/tests/...`
- `tests/dune_geometry/test_pyo3_surface.py`
- `tests/golden/geometry/{pins,anchor_to_target,machine_calibration,loop}/...`
- `specs/uv-machine-calibration.allium`
- `scripts/migrate_pin_names.py`
- `scripts/convert_legacy_pin_calibration.py`

To be modified:

- `rust/Cargo.toml` (add `dune_geometry` to workspace members)
- `rust/crates/dune_tension_core/src/geometry.rs` (replace with re-exports from `dune_geometry::tension`)
- `rust/crates/dune_tension_core/Cargo.toml` (depend on `dune_geometry`)
- `specs/layer-geometry.allium`
- `specs/uv-wrap-geometry.allium`
- `src/dune_winder/.../anchorToTarget.py` (becomes a thin PyO3 wrapper)
- `src/dune_winder/.../Calibrate.html` and its FastAPI/handler module
- `src/dune_winder/.../APA.html` and its handler module
- `src/dune_winder/.../machine_calibration` page + handler module
- `src/dune_winder/.../gcode_generation/` (drop manual 12-offset UI; gcode parser/emitter to support `offset(x, y, z)`)
- `src/dune_winder/geometry/primitives/` (delete or thin to re-exports from PyO3 `dune_geometry`)
- `src/dune_tension/geometry.py` (re-export from PyO3 `dune_geometry`)

## Verification

- `cargo test -p dune_geometry`
- `pytest tests/dune_geometry/ tests/golden/geometry/`
- Manual end-to-end as in Phase H, item 4.
- Manual: capture a single point with a label and verify the offset propagates to all same-label gcode lines in the loaded recipe.
