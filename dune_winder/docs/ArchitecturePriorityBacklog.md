# Architecture Priority Backlog

This document captures high-priority architectural follow-up work that was
intentionally left out of the phase-1 remote command API implementation.

## P1: Split G-code domain model across `library/`, `machine/`, and `recipes/`

Status: Implemented with legacy wrapper removal (2026-03-05). Canonical domain package:
`src/dune_winder/gcode/` (`model`, `parser`, `renderer`, `runtime`).
Details: [`docs/GCodeDomainArchitecture.md`](docs/GCodeDomainArchitecture.md)

### Impact
- Domain behavior is hard to reason about because parsing, generation, and execution logic are spread across multiple layers with overlapping names.
- Changes to G-code behavior require touching several modules, increasing regression risk.

### Concrete Symptoms
- Multiple similarly named abstractions (`G_Code`, `G_CodeFunction`, `G_Codes`, handler tables) exist in different packages with different semantics.
- Recipe generation and runtime interpretation use distinct models that are only coupled through text formatting.
- The command/function mapping lives in different places (`machine/G_Codes.py`, handler tables, recipe function classes), so source-of-truth is unclear.

### Proposed Target Architecture
- Introduce a single `gcode` domain package with explicit submodules:
  - `gcode.model` for tokens/instructions/program line objects
  - `gcode.parser` for text-to-model
  - `gcode.renderer` for model-to-text
  - `gcode.runtime` for machine execution adapters
- Define one canonical opcode/function catalog shared by both generation and execution.

### Migration Strategy
1. Create canonical opcode catalog and adapter layer without changing behavior.
2. Route recipe generators to build canonical instruction objects, then render.
3. Route runtime parser/handler to consume canonical instruction objects.
4. Remove legacy duplicate abstractions once parity tests pass.

### Acceptance Criteria
- One canonical opcode/function definition source.
- Recipe generation and runtime execution share the same instruction model.
- No duplicated G-code class hierarchies across `library/`, `machine/`, and `recipes/`.

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
