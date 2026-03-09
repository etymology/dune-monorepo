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

Status: Partially implemented (2026-03-05) with centralized typed UI command
service (`web/Scripts/UiServices.js`) and refactors for `APA`, `Jog`, and
`Calibrate` page modules to remove direct global command catalog dependency and
inline global page singletons.

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

## P4: `GeometrySelection` abusing `__new__` as a disguised factory function

Status: Implemented (2026-03-09). Deleted `GeometrySelection` class; replaced with `create_layer_geometry(layer_name: str) -> LayerGeometry` factory function in `machine/geometry_selection.py`. All call sites updated. Invalid layer names now raise `ValueError` with a descriptive message listing valid names. Common layer attributes declared on `LayerGeometry` base class for correct static typing.


### Impact
- Type checkers and IDEs report the return type as `GeometrySelection`, but no `GeometrySelection` instance is ever created, misleading any static analysis.
- The pattern violates Python's contract for `__new__` and surprises readers who expect class instantiation to produce the declared type.

### Concrete Symptoms
- `machine/geometry_selection.py` declares `class GeometrySelection(LayerGeometry)` whose `__new__` returns an instance of a completely different class (`X_LayerGeometry`, `V_LayerGeometry`, etc.).
- The docstring itself acknowledges the deception: *"The new operator will actually not create an instance of this class."*
- The lookup table is rebuilt on every call and the inheritance relationship with `LayerGeometry` is never used.
- An invalid layer name raises a bare `KeyError` with no helpful message.

### Proposed Target Architecture
- Replace the class with a plain factory function: `def create_layer_geometry(layer_name: str) -> LayerGeometry`.
- Add explicit `ValueError` with the list of valid layer names when the key is missing.
- Remove the now-unused `GeometrySelection(LayerGeometry)` inheritance.

### Migration Strategy
1. Introduce `create_layer_geometry()` function alongside the existing class.
2. Update all call sites to use the function.
3. Delete `GeometrySelection`.

### Acceptance Criteria
- No use of `__new__` to return a foreign type.
- `mypy`/`pyright` correctly infers the return type as `LayerGeometry`.
- Invalid layer names produce a `ValueError` with a descriptive message.

## P5: `StateMachine` is a polling-only abstraction with no event dispatch, forcing the orchestrator to become a shared flag mailbox

Status: Implemented (2026-03-09). `library/state_machine.py` now exposes `dispatch(event)` and `library/state_machine_state.py` now exposes `handle(event)`. Control intents are represented as typed dataclass events in `core/control_events.py` and are dispatched from `core/process.py` instead of writing shared control flags. `ControlStateMachine.States` now uses `enum.Enum`; the prior `isInMotion()` tautology is fixed. Mode-private request data moved into mode classes (`StopMode`, `WindMode`, `ManualMode`, `CalibrationMode`), removing the root-level flag mailbox.

### Root Cause
`library/state_machine.py` defines `StateMachine` with only two entry points: `update()` (called each cycle) and `changeState()` (for transitions). There is no `dispatch(event)` mechanism — no way for external code to deliver intent to whichever state is currently active. Because states hold a back-reference to their parent (`self.stateMachine` in `StateMachineState.__init__`), the orchestrator is the only shared object both external callers and states can see. It inevitably becomes a mailbox: callers write flags, states read them in `update()`.

### Impact
- The flag bag on `ControlStateMachine` is not an accidental design choice — it is a structural consequence of the polling-only abstraction. Fixing the flags without changing the abstraction will just produce a tidier flag bag.
- Adding or changing a mode requires modifying the top-level orchestrator to add new flag fields, coupling mode-specific concerns to the root class.
- Flag lifecycle (when to set, when to clear) is managed by convention rather than structure, making stale-flag bugs silent and hard to reproduce.

### Concrete Symptoms
- `core/control_state_machine.py` carries 12+ mutable flag fields (`startRequest`, `stopRequest`, `manualRequest`, `isJogging`, `seekX`, `seekY`, `seekZ`, `calibrationRequest`, etc.) that are the only communication path between the API layer and the active mode.
- The `States` inner class uses singleton tuples `(0,)` / `(1,)` as identity tokens, but one entry (`TENTION`) uses a plain `int` — the pattern is self-inconsistent and unenforceable.
- `isInMotion()` has a logic bug: `HARDWARE != state or STOP != state` is a tautology (always `True`); the intended check is `and`.

### Proposed Target Architecture
Add event dispatch to the state machine abstraction:
- `StateMachine.dispatch(event)` delivers an event to the current state's `handle(event)` method; unhandled events are silently dropped or logged.
- `StateMachineState` gains `handle(event) -> bool` alongside `update()`; states opt in to the events they care about.
- External callers (the API layer) dispatch typed event objects (`StartWindEvent`, `SeekEvent(x, y, z, velocity)`) rather than writing flags.
- `ControlStateMachine` becomes a thin coordinator: it owns transitions and IO wiring, but no mode-private state.
- Replace the `States` inner class with a proper `enum.Enum`.

### Migration Strategy
1. Add `dispatch` / `handle` to `StateMachine` and `StateMachineState` without removing `update()`.
2. Define typed event dataclasses for each group of flags (`WindEvent`, `SeekEvent`, `ManualEvent`, `CalibrationEvent`).
3. Implement `handle(event)` on each mode, consuming the relevant event; have the orchestrator dispatch instead of setting flags.
4. Remove flag fields from `ControlStateMachine` one group at a time as modes adopt `handle`.
5. Convert `States` to `enum.Enum` and fix the `isInMotion` bug.

### Acceptance Criteria
- `StateMachine` has a `dispatch(event)` method; `StateMachineState` has `handle(event)`.
- `ControlStateMachine` owns no mode-specific mutable state; all inter-layer communication goes through dispatched events.
- All state identifiers are members of an `enum.Enum`; `isInMotion()` returns the correct value.

## P6: Remove unused `RemoteSession` authentication layer

Status: Implemented (2026-03-09). Deleted `library/remote_session.py` and `library/remote_command.py`; removed `isAuthenticated` surface from `web_server_interface.py`, `api/registry.py`, `main.py`, and related tests.

`RemoteSession` implements a custom session/password authentication system that is not actively used. It carries meaningful maintenance risk (global mutable class state, a hardcoded password in source, unguarded semaphore pairs) for no active benefit. The correct resolution is deletion, not improvement.

### Impact
- Dead code with security-relevant patterns (`PASSWORD = "PSL#Winder"` in source, unguarded semaphore acquire/release) invites accidental reactivation or cargo-culting into new code.
- Any future web server work will be confused by the presence of an authentication layer that appears functional but is not in use.

### Concrete Symptoms
- `library/remote_session.py` is a complete session management and password-hashing system with no active callers.
- `library/remote_command.py` references `RemoteSession` for authentication checks that are never exercised.

### Migration Strategy
1. Confirm no live call path reaches `RemoteSession.sessionSetup()` or `RemoteSession.isAuthenticated()`.
2. Delete `library/remote_session.py` and `library/remote_command.py` (or the authentication surface within it).
3. If authentication is needed in the future, implement it using a standard library (e.g., session middleware in whatever web framework is in use) rather than a bespoke implementation.

### Acceptance Criteria
- `library/remote_session.py` is deleted.
- No hardcoded password strings remain in the codebase.
- Any web command handler that previously checked `isAuthenticated` either uses a real auth mechanism or removes the check entirely.

## P7: XML used for two distinct persistence concerns that need different solutions

Status: Implemented (2026-03-09). `Configuration` / `configuration.xml` replaced by `AppConfig` (`library/app_config.py`) backed by `configuration.toml` — all fields are typed dataclass attributes; `tomllib` (stdlib 3.11+) loads the file; a simple inline writer saves it atomically. `Serializable` / `HashedSerializable` replaced by JSON load/save in each consumer: `MachineCalibration` (`machine_calibration.py`), `LayerCalibration` (`layer_calibration.py`), and `APA_Base` (`apa_base.py`) each have `_to_dict`/`_from_dict` and atomic JSON writes. Hash integrity is preserved in `LayerCalibration` via MD5 over the JSON payload. All three classes include an XML fallback that reads the legacy file and immediately re-saves as JSON on first run. `library/configuration.py`, `library/serializable.py`, and `library/hashed_serializable.py` are deleted; `serializable_location.py` retains only the `Location` subclass.



The codebase has two separate XML-based persistence mechanisms with different requirements that are currently conflated under a single "use XML" approach:

- **`Configuration` / `configuration.xml`** — ~15 operator-tunable settings (PLC address, camera URL, velocity limits, ports). Set once or rarely; should be human-editable with explanatory comments.
- **`Serializable` / `machineCalibration.xml`, `config/APA/*.xml`** — structured machine state populated during calibration runs and loaded at startup. Written programmatically; human-readability is secondary.

### Impact
- `Configuration` callers must cast every value manually (`int(config.get("maxVelocity"))`); a typo in a key name silently returns `None`, deferring the failure to the cast site at runtime.
- The complete set of valid configuration keys is only discoverable by reading `Settings.defaultConfig()` — there is no schema.
- `Serializable` uses `__dict__` introspection on classes with all-`None` fields, so the field schema is implicit and adding or removing a field silently diverges from persisted files until the missing-key error surfaces at load time.

### Concrete Symptoms
- `library/configuration.py` `get()` always returns `str | None`; callers do `int(config.get("maxVelocity"))` throughout.
- `Configuration.set()` writes to disk on every call — every single assignment triggers an XML serialization round-trip.
- `Serializable` encodes Python type names as XML tag names (e.g., `<float name="parkX">`) — a hand-rolled type system that `json` provides for free.

### Proposed Target Architecture

**Operator configuration → TOML + `@dataclass AppConfig`**
- `tomllib` is stdlib from Python 3.11+; no new dependency for reading.
- TOML supports `int`, `float`, `bool`, and `str` natively — the casting footgun disappears at the file level.
- Comments can annotate each field inline, which is valuable for operators editing PLC addresses and velocity limits.
- The `@dataclass` definition is the schema; missing or wrong-typed fields raise a descriptive error at startup.
- Writing: the config rarely changes at runtime; for the uncommon case, `tomli-w` is a ~10 KB optional dependency.

**Calibration state → JSON + typed `@dataclass` per model**
- Replaces the hand-rolled XML type system with standard `json.load()` / `json.dump()`.
- Each calibration class becomes a typed `@dataclass`; `dataclasses.asdict()` serializes it without reflection magic.
- The atomic-write pattern in `Serializable.save()` (tempfile + `os.replace()`) is correct and should be kept verbatim.
- Files remain text-readable in a debugger.

### Migration Strategy
1. Define `@dataclass AppConfig` mirroring all keys in `Settings.defaultConfig()`; write a TOML loader that validates types and fails fast.
2. Replace all `configuration.get("key")` call sites with typed attribute access; ship `configuration.toml` as a committed template with defaults.
3. Convert each `Serializable` subclass to a `@dataclass` with explicit field types; write a `from_dict` / `to_dict` pair and a JSON load/save wrapper that preserves the atomic-write logic.
4. Delete `library/configuration.py` and `library/serializable.py` once all consumers are migrated.

### Acceptance Criteria
- Operator settings live in `configuration.toml`; all fields are typed attributes on `AppConfig`.
- Calibration state is persisted as JSON; each model class is a typed dataclass with a `from_dict` loader.
- A missing or malformed field in either file raises a descriptive error at startup, not a `TypeError` mid-run.
- Disk writes for calibration state are explicit and atomic; operator config is loaded read-only at startup.

## P8: `GCodeCallbacks` delivers one callback per parameter word, forcing handlers to re-assemble instructions from fragments

Status: Implemented (2026-03-09). `gcode/runtime.py` now dispatches exactly one `on_instruction(line: ProgramLine)` callback per parsed line. `machine/g_code_handler_base.py` now consumes complete instructions via `handle_instruction`, removing per-letter callback registration (`X/Y/Z/F/G/N`) and related dirty-flag fields from the base class. `core/g_code_handler.py` now executes queued instruction actions (`xy`, `z`, `head`, `latch`) plus deferred stop requests, preserving move sequencing without per-word callback fanout.

### Root Cause
`gcode/runtime.py` `execute_program_line` iterates over every `CommandWord` in a `ProgramLine` and fires a separate callback per letter. A single instruction like `G1 X10 Y20 F500` arrives as four independent calls: `G(1)`, `X(10.0)`, `Y(20.0)`, `F(500.0)`. The runtime has no concept of instruction boundary — it treats a program line as an unordered bag of words rather than a structured command.

### Impact
- Handlers have no choice but to accumulate partial state across callbacks and use dirty flags to detect when a complete instruction has been assembled.
- There is no structural guarantee that flags are cleared exactly once per cycle; reset timing is managed manually in `poll()`.
- The logical unit of work (one G-code instruction) never exists as an object anywhere in the system, making it untestable in isolation.

### Concrete Symptoms
- `machine/g_code_handler_base.py` defines `_setX`, `_setY`, `_setZ`, `_setVelocity`, `_setLine`, etc. — one per parameter letter — each mutating a separate field and setting a separate dirty flag (`_xyChange`, `_zChange`, `_headPositionChange`).
- For `G1 X10 Y20 F500`, the handler receives four calls with no indication they belong together; it infers the instruction is complete only when `poll()` runs next.
- The dirty flags must be manually reset in `poll()` after consumption; if any code path through `poll()` misses a reset, the flag remains set and the next cycle sees stale state.

### Proposed Target Architecture
Change `execute_program_line` to deliver a complete `ProgramLine` to a single `on_instruction(line: ProgramLine)` callback rather than fanning out per word. The handler then receives the whole instruction atomically and can extract X, Y, Z, F, etc. from it directly — no accumulation, no dirty flags.

- `GCodeCallbacks` is replaced by a single `on_instruction` protocol; the per-letter dispatch table is removed from the public interface.
- `G_CodeHandlerBase` replaces its setter callbacks and dirty-flag fields with a single `handle_instruction(line: ProgramLine)` method that reads all parameters at once and acts atomically.

### Migration Strategy
1. Add an `on_instruction` callback path to `execute_program_line` alongside the existing per-word dispatch (feature-flag the new path).
2. Rewrite `G_CodeHandlerBase.handle_instruction` to consume a `ProgramLine` directly; extract X/Y/Z/F/etc. in one place.
3. Remove per-letter setter callbacks and dirty flags once `handle_instruction` is the sole entry point.
4. Remove the old per-word dispatch from `GCodeCallbacks` once no callers remain.

### Acceptance Criteria
- `execute_program_line` delivers one call per instruction, not one call per parameter word.
- `G_CodeHandlerBase` has no per-letter setter callbacks and no dirty flags.
- A complete instruction (X, Y, Z, F) can be tested by constructing a `ProgramLine` and calling `handle_instruction` directly, without a full handler instantiation.
