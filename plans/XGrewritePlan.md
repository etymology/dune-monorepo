# XG Layer Rewrite Plan

## Objective
Migrate X and G layer gcode generation and calibration to a solver-based approach using `anchorToTarget` macros, eliminating the simplified calibration panel. Update the APA plane Z-coordinate storage to be relative to the board center. Properly implement the specific X and G slot nomenclature (e.g., `XAH1`, `GBF23`) across the stack.

## Key Files & Context
- **Specs:** `specs/layer-geometry.allium`
- **Rust Core (`dune_geometry`):** `pins.rs`, `calibration.rs`, `spine.rs`, `wire.rs`, `python.rs`
- **Python Bindings & Logic:** G-code template generators (e.g. `xg_template_gcode.py`), calibration loaders.
- **UI:** The winder interface (to remove the old calibration panel and add the new 4-point workflow).

## Active Constraints & Nomenclature
- **Nomenclature:** X and G slots use a specific 4-part string format: `{Layer}{Side}{Edge}{Index}` (e.g. `XAH1`, `GBF23`). 
  - `Layer`: `X` or `G`
  - `Side`: `A` or `B`
  - `Edge`: `H` (Head) or `F` (Foot)
  - `Index`: 1..480 (X) or 1..481 (G)
- **Geometry:** X and G layers do not have top or bottom edges; wires run directly from head to foot. They use tooth slots (zero radius, no wrap orientation).
- **Z-Coordinates:** All Z coordinates must be stored relative to the center of the board. A and B faces are derived via `+/- boardWidth / 2` (X width = 110mm, G width = 140mm).
- **Wrapping Sequence:** For n in 1..maxwireno:
  - `AHn` -> `AFn` -> `BFn` -> `BHn` -> `AHn` (with specific head/foot increments).

## Implementation Steps

### Phase 1: Core Geometry, Types & Nomenclature (Rust & Specs)
- **Status:** Mostly complete, but needs nomenclature update.
- **Tasks:**
  - Update Allium spec to explicitly define the `XAH1` nomenclature and mappings.
  - Modify `Pin::from_str` and `Pin::fmt` in `rust/crates/dune_geometry/src/pins.rs` to correctly parse and format `XAH1`/`GBF23` format. It will map the Head (`H`) and Foot (`F`) string prefixes and 1..480 index back to the internal contiguous 1..960/962 pin number space.
  - Update Rust tests to enforce the nomenclature.

### Phase 2: Calibration Storage & Python Bindings
- **Tasks:**
  - Update the Python layer logic to load/store APA plane Z-coordinates relative to the board center.
  - Modify the schema validation if necessary to support this updated structural storage.

### Phase 3: Recipe Generation Rewrite
- **Tasks:**
  - Rewrite the Python generator for X and G gcode.
  - Utilize the new `solve_xg_slots` logic to retrieve absolute coordinates.
  - Generate sequences utilizing the `anchorToTarget` macros.
  - Implement the specific wrap logic:
    ```
    preamble: goto AH1
    for n in 1-maxwireno:
        increment(80,0)
        anchorToTarget(Layer+AH{n}, Layer+AF{n})
        anchorToTarget(Layer+AF{n}, Layer+BF{n})
        increment(-80,0)
        anchorToTarget(Layer+BF{n}, Layer+BH{n})
        anchorToTarget(Layer+BH{n}, Layer+AH{n})
    ```

### Phase 4: UI & Workflow Updates
- **Tasks:**
  - Strip out the simplified calibration panel from the user interface.
  - Implement the new 4-point workflow for X and G layer calibration (Head 1, Head Max, Foot 1, Foot Max on the B side).

### Phase 5: Testing & Validation
- **Tasks:**
  - Verify string round-tripping for X/G slot names.
  - Validate output G-code recipes against physical machine safety limits.
