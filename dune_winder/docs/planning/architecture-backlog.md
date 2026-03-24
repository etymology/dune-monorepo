# Architecture Backlog

This document tracks architectural improvements that have not yet been
implemented.

## P2: `Process` as a high-coupling orchestration god-class

### Impact

- `Process` mixes orchestration, validation, safety constraints, hardware control, and UI-facing behavior, making it difficult to change safely.
- Unit testing is expensive because broad dependencies are required even for isolated behavior.

### Concrete Symptoms

- `Process` owns unrelated responsibilities (APA lifecycle, jog/seek, manual G-code validation, calibration flows, UI snapshots, editor launching).
- Safety/validation logic is embedded inline with command orchestration.
- UI transport concerns and machine-level operation concerns leak into the same class.

### Proposed Target Architecture

- Split `Process` into cohesive services:
  - `RecipeService`
  - `MotionService`
  - `CalibrationService`
  - `RuntimeStateService`
  - `SafetyValidationService`
- Keep `Process` as a thin facade coordinating service dependencies.

### Migration Strategy

1. Extract pure validation logic first (manual G-code line checks, limits).
2. Extract motion commands and state transitions into `MotionService`.
3. Extract recipe and calibration operations into dedicated services.
4. Keep facade method names stable while internal delegation is introduced.
5. Remove direct field coupling once service APIs are stable.

### Acceptance Criteria

- `Process` is primarily delegation/orchestration code.
- Safety and validation are independently testable without hardware object graphs.
- New behavior changes affect one focused service rather than the monolithic class.

## P3: Legacy page/module organization in `web/`

Status: Partially implemented (2026-03-05) with centralized typed UI command
service (`web/Scripts/UiServices.js`) and refactors for `APA`, `Jog`, and
`Calibrate` page modules.
Details: [webui-hardening.md](webui-hardening.md)

### Impact

- UI behavior is difficult to trace because modules rely on global mutable state and loosely structured callback chains.
- Feature work and bug fixes are slow due to hidden coupling and duplicate command string usage.

### Concrete Symptoms

- Page scripts maintain state and transport concerns together.
- Cross-module coordination relies on globals and implicit module load order.
- Command usage is scattered and previously string-concatenated, making refactors fragile.

### Proposed Target Architecture

- Introduce a thin UI data-access layer (typed client wrapper) used by all pages.
- Move page state into explicit state objects per page/module.
- Standardize module lifecycle hooks and avoid global singleton side effects.

### Migration Strategy

1. Complete migration from legacy `remoteAction` usage to typed command client.
2. Extract per-page API calls into dedicated page service modules.
3. Refactor high-churn pages (`APA`, `Jog`, `Calibrate`) to isolate state and rendering.
4. Add targeted smoke tests around key page workflows.

### Acceptance Criteria

- Page modules no longer build remote command strings inline.
- Cross-page behavior does not rely on undocumented global mutable state.
- Command usage is discoverable from centralized client/service modules.

## P0: Make the PLC Contract Explicit

See [plc-architecture-proposals.md](plc-architecture-proposals.md) for the full
proposals. Summary of unstarted items:

- **P0.1**: Generate a shared `plc_contract` package from exported PLC metadata — tag constants, UDT serializers, move/state enums, queue tag groups.
- **P0.2**: Add an explicit structure or manifest to `plc/` separating exported metadata from hand-maintained ladder artifacts and labeling which routines are active vs experimental.
- **P0.3**: Normalize uppercase package directories (`io/Devices`, `io/Maps`, `io/Primitives`) to lowercase to fix cross-platform import failures on case-sensitive filesystems.
- **P0.4**: Replace the global `PLC.Tag` singleton with a scoped per-backend tag registry.
- **P0.5**: Split telemetry reads from command writes (`read_cached`, `read_fresh`, `write_command`) to make freshness expectations explicit.
- **P0.6**: Consolidate queued-motion implementations — `QueuedMotionSession`, `QueuedMotionPLCInterface`, `queue_client.py`, `queue_client_3d_arc.py` — around one port abstraction.

## Additional Feature Backlog

These items originated in earlier notes and have not been captured elsewhere:

- **Wrap/wire tracking**: Track current wrap number and wire number along with tension during recipe execution.
- **Reversible G-code**: Make G-code reversible so the machine can unwind a winding as well as wind it.
- **Collision protection**: Sequence motion as ZX → ZY → full XYZ to protect against collisions during combined-axis moves.
- **Anchored wire pull refactor**: Redesign anchored wire pull calculation — decide whether the command should be stateful (remembering which pin the wire is currently wrapped around and taking only a target) or declarative (taking full state each time).
- **Queued Motion Preview / Machine Layout pane unification**: Both panes give live visualizations of robot position and planned/executed paths. Merging them into a single pane would eliminate duplication and give operators a unified view.
- **Tag read latency**: Batch tag reads where possible to reduce poll latency; relates to P0.4 tag registry work.
