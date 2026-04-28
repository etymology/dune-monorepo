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

### `tension-physics.allium`

Wire resonance physics, frequency-tension-length equations, KDE-based frequency
estimation, and pass/fail thresholds.

### `tension-measurement.allium`

Wire-tension measurement behaviour for DUNE APA detectors. Includes setup,
wire targeting, focus-aware pose planning, legacy pulse measurements, streaming
sweep/rescue measurements, result acceptance, raw samples, summaries, clearing,
and upload/review boundaries.

### `streaming-evidence.allium`

Streaming measurement evidence. Models how audio frames become voiced windows,
pitch observations, wire candidates, rescue queue items, and accepted tension
results.

### `layer-geometry.allium`

APA wire geometry for U, V, X, and G layers. U/V geometry is fully specified;
X/G geometry is intentionally marked as placeholder work pending detailed
mechanical design.

### `uv-wrap-geometry.allium`

Geometric planning for UV-layer winding-head pin wraps. Covers tangent point
computation, same-side versus cross-side transitions, transfer requirements,
head-position selection, and resolved `WrapTransitionPlan` output.

### `motion-safety.allium`

Queued-motion safety validation. Covers machine envelope limits, forbidden
regions, collision-state sampling, arc discretisation, and validation results
before segments are handed to the PLC queue.

### `gcode-opcodes.allium`

The winder-specific G-code opcode model used by recipe templates to drive
machine motion, head positioning, wire management, and wrap sequencing.

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
- Use `streaming-evidence.allium` for streaming measurement provenance.
- Reference `winder-states.allium` for safety interlocks and state transitions.
- Use `layer-geometry.allium` and `uv-wrap-geometry.allium` for wire geometry.
- Use `motion-safety.allium` for queued-motion safety validation.
- Use `gcode-opcodes.allium` for recipe execution semantics.

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
