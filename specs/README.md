# DUNE Allium Specifications

This directory contains the authoritative Allium specifications for the DUNE
winder and tension-measurement systems. The specs describe observable domain
behaviour for the current Python implementation and future ports.

## Specifications

### `core.allium`

Shared foundational types and hardware-control contracts used across the DUNE
specs.

- **Layer enum**: `u | v | x | g`
- **Shared contracts**: MotionControl, FocusControl, ExcitationControl
- **Common value types**: PinSide, FrameEdge, PinRange, PinName, PinPair,
  WrapSide

### `operator-workflows.allium`

Operator-facing workflows across the winder and tension tools. Covers manual
motion, winding, calibration capture, tension measurement, and tension
observation review as user-visible interactions, while deferring low-level
geometry, safety, PLC, and analysis details to the domain specs below.

### `tension-physics.allium`

Wire resonance physics, frequency-tension-length equations, KDE-based frequency
estimation, and pass/fail thresholds.

### `tension-measurement.allium`

Wire-tension measurement behaviour for DUNE APA detectors. Includes setup,
wire targeting, focus-aware pose planning, legacy pulse measurements, streaming
sweep/rescue measurements, result acceptance, raw samples, summaries, clearing,
and upload/review boundaries.

### `layer-geometry.allium`

APA wire geometry for U, V, X, and G layers, plus the APA physical
envelope: frame dimensions, board cross-section, pin radius, the X/G
board slot grid (head/foot edges, A/B sides, X slots numbered 1-480,
G slots numbered 1-481), the four mid-APA combs, and
the X/G wrap visit order. U/V wire geometry is fully specified; X/G
wire-segment formulas remain placeholders pending detailed mechanical
design. Winding angles are derived from pin locations on the fly and
are intentionally not part of the spec.

### `winder-calibration.allium`

The `WinderCalibration` contract — the single, enumerated set of
calibration values a reimplementer must supply (APA envelope, board
cross-section, pin and tooth tables, workspace bounds, Y transfer
positions, headward-pivot keepout, frame-support keepout bands, arc
discretisation, max velocity).

### `uv-wrap-geometry.allium`

Geometric planning for UV-layer winding-head pin wraps. Covers tangent point
computation, same-side versus cross-side transitions, transfer requirements,
head-position selection, the per-pose `CameraWireOffset` model, and the
resolved `WrapTransitionPlan` and `AnchorToTargetSolution` outputs.

### `uv-machine-calibration.allium`

Capture, persistence, and solver behaviour for the UV diagonal-layer
machine calibration workflow. Covers the snapshot-based
`PinCalibrationFile`, the APA.html "Use current position" capture
(`MachineCalibrationCapturePoint`), label-driven 3D gcode offset
propagation, the machine-calibration solver that fits the
`MachineCalibrationModel` and roller offsets, and the continuous
B-pin loop solver that replaces the planar Z fit.

### `motion-safety.allium`

Queued-motion safety validation. Covers machine envelope limits, forbidden
regions, collision-state sampling, arc discretisation, and validation results
before segments are handed to the PLC queue.

### `winder-macros.allium`

The high-level winder macro model used by recipe templates to drive machine motion, head positioning, and wrap sequencing through composite state transitions (e.g. `anchorToTarget`).

### `winder-states.allium`

Runtime and PLC state behaviour for the winder. Includes runtime modes, PLC
states, head-transfer protocol, latch actuator state, Z-axis coordination,
safety interlocks, queued-motion diagnostics, and operator-facing diagnostics.

## Cross-Spec Sharing Pattern

Shared entities and contracts are managed through a small canonical core spec
plus local redeclarations where a spec needs to validate independently.

1. `core.allium` is the canonical source for shared definitions.
2. Dependent specs redeclare shared definitions locally when necessary.
3. Comments near redeclarations identify the source definition in `core.allium`.

This keeps individual specs self-contained while making cross-spec updates
explicit. When a shared definition changes, update `core.allium` first and then
propagate the same change to dependent specs.

## Structure And Scope

All specs are self-contained Allium v3 specifications. They describe observable
behaviour and domain contracts, not implementation layout.

Common exclusions:

- UI layout, directory structure, threading, and logging format
- PLC communication protocol framing and pycomm3 transport details
- Servo tuning and low-level machine wiring
- SQLite, CSV, PNG, WAV, and JSON storage schemas
- PESTO, CREPE, harmonic-comb, and audio-device internals

## Using These Specs

### For Rust Port

- Start with `tension-measurement.allium` for measurement contracts.
- Use `tension-physics.allium` for resonance equations and thresholds.
- Use `operator-workflows.allium` for user-facing workflow obligations and
  operator-visible progress/outcome states.
- Reference `winder-states.allium` for safety interlocks and state transitions.
- Use `layer-geometry.allium` and `uv-wrap-geometry.allium` for wire geometry and the APA physical envelope.
- Use `motion-safety.allium` for queued-motion safety validation and pose invariants.
- Use `winder-calibration.allium` for the calibration values that workspace and geometry rules consume.
- Use `winder-macros.allium` for recipe execution semantics.

### For Python Implementation

- Contracts define the obligations fulfilled by hardware and service boundaries.
- Rules define state changes, emitted triggers, and accepted outcomes.
- Config blocks define physical constants, thresholds, timeouts, and ranges.

### For Domain Review

- Surfaces show what operators or external systems can observe and do.
- Invariants capture safety-critical relationships that must always hold.
- Open questions identify requirements that still need a domain decision.

## Maintenance

### Editing Specs

1. Use the `tend` skill for focused spec edits.
2. After editing, run `allium check <spec>`.
3. Run `allium analyse <spec>` when a spec has rules and surfaces.
4. Update this README when scope, key entities, or file structure changes.

### Cross-Spec Changes

If a shared definition changes, update the canonical definition first:

1. Edit `core.allium`.
2. Propagate the same change to dependent specs.
3. Keep redeclaration comments accurate.
4. Run `allium check specs/*.allium`.

### Example: Adding A New Layer

If you add `w` to the Layer enum:

- Edit `core.allium`: `enum Layer { u | v | x | g | w }`
- Edit dependent specs that redeclare Layer.
- Run validation to confirm the spec set still checks.
