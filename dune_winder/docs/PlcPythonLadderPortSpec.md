# Python PLC Ladder Port Specification

## Purpose

This document captures the current plan for a Python port of the checked-in
Rockwell ladder logic in `plc/`.

The intended audience is:

- someone continuing the implementation
- someone reviewing or revising the spec before implementation
- someone trying to understand how the new ladder/runtime/transpiler work is
  supposed to fit with the existing repository

This is a forward-looking design document. It describes the target structure
and the first implementation milestone, not the current implementation status.

## Goals

- Import normalized `pasteable.rll` ladder text into editable Python.
- Represent PLC instructions as Python functions with side effects, using the
  Rockwell mnemonic names such as `TON`, `RES`, `MCLM`, `MCCM`, `MAM`, and
  `MSO`.
- Execute imported or hand-written ladder routines scan-by-scan in Python.
- Simulate motion side effects and instruction status bits closely enough to
  make the Python behavior match the ladder behavior for the targeted routines.
- Emit normalized `pasteable.rll` text from the Python or AST representation in
  the same style as the existing transpiler and `.rllscrap` converter.
- Keep imported Python readable enough that it can become an editable source of
  truth rather than a throwaway intermediate.

## Non-Goals for the First Milestone

- Replacing the existing `studio_copy.rllscrap -> pasteable.rll` transform.
- Replacing the current math/helper transpiler under
  `src/dune_winder/transpiler/`.
- Full Rockwell instruction coverage beyond the instructions exercised by the
  direct-motion and queued-motion routines already checked into this repo.
- Perfect controller-cycle fidelity for every undocumented edge case in the
  Rockwell manuals.

## Repository Facts This Spec Builds On

- `plc/` is the checked-in PLC artifact tree.
- `pasteable.rll` is the canonical normalized ladder text form used in this
  repo.
- `studio_copy.rllscrap` is a raw Studio 5000 copy/paste format that is already
  normalized by `src/dune_winder/plc_rung_transform.py`.
- The current Python-to-ladder transpiler already emits normalized `pasteable`
  style ladder text for math-heavy helper routines such as `CapSegSpeed`.
- The queue integration target is the standalone `plc/motionQueue/main`
  routine, not the older `plc/enqueueRoutineStateful` artifact.
- Exported PLC metadata already exists in `plc/controller_level_tags.json` and
  `plc/*/programTags.json`, including the UDT layouts for structures such as
  `TIMER`, `CONTROL`, `MOTION_INSTRUCTION`, `COORDINATE_SYSTEM`, and
  `MotionSeg`.

## Source References

The following checked-in artifacts are the reference inputs for this work:

- `plc/instruction_set.md`
- `docs/PlcLadderWorkflow.md`
- `docs/PlcWinderCommunication.md`
- `src/dune_winder/transpiler/`
- `src/dune_winder/plc_rung_transform.py`
- `docs/rockwell/1756-rm003_-en-p.pdf`
- `docs/rockwell/motion-rm002_-en-p.pdf`
- `docs/rockwell/motion-um002_-en-p.pdf`

The manuals are the source of truth for operand meaning and enum values. The
checked-in `.rll` files are the source of truth for the operand ordering and
output formatting that this repository already uses.

## Design Summary

The new implementation should introduce a ladder-specific subsystem under a new
package, tentatively:

```text
src/dune_winder/plc_ladder/
```

That package should own four things:

1. runtime types for PLC data structures and tags
2. side-effectful instruction functions like `TON(...)` and `MCLM(...)`
3. an internal AST for routines, rungs, branches, and instructions
4. import/export tooling between normalized `.rll`, AST, and Python source

The same ladder model should power:

- execution in a simulator
- `.rll -> Python` import
- Python -> `.rll` export

The goal is to avoid having one execution model for simulation and a separate
textual model for transpilation.

## Canonical Formats

### Canonical textual ladder format

The canonical text format is normalized `pasteable.rll`.

Implications:

- The importer should parse `pasteable.rll`, not raw `.rllscrap`.
- The `.rllscrap` converter remains the front door for copied Studio 5000 text.
- Emitted ladder text should match the existing normalized style:
  - one rung per line
  - space-separated instructions
  - `BST ... NXB ... BND` for branches
  - formula formatting compatible with the existing converter and transpiler
  - quoted multi-word tokens such as `"Units per sec2"`

### Canonical Python format

Imported Python should be a readable ladder-like source form, not a high-level
wrapper API.

The key rule is:

- side-effectful instructions should appear as Python functions with Rockwell
  mnemonics, for example `TON(...)`, `RES(...)`, `MCLM(...)`, `MCCM(...)`

Logical and mathematical pieces can still be represented by helper expressions
or condition functions, but the instruction layer must preserve the mnemonic
names and side effects.

## Python Execution Model

### Routine model

A ladder routine should compile into a Python function that executes in rung
order against a mutable scan context.

That function should:

- read and write tags through a shared tag store
- evaluate branch groups in ladder order
- invoke instruction functions only when rung-condition-in is true
- preserve ladder semantics for one-shots, timer status bits, motion status
  bits, and reset behavior

### Suggested shape

The exact syntax can evolve, but the generated and hand-authored code should be
close to this style:

```python
def move_xy_main(ctx: ScanContext) -> None:
  if cmp_eq(ctx.STATE, 3) and xic(ctx.trigger_xy_move):
    MCLM(
      ctx.X_Y,
      ctx.main_xy_move,
      0,
      ctx.X_POSITION,
      ctx.XY_SPEED_REQ,
      SpeedUnits.UNITS_PER_SEC,
      ctx.XY_ACCELERATION,
      AccelUnits.UNITS_PER_SEC2,
      ctx.XY_DECELERATION,
      DecelUnits.UNITS_PER_SEC2,
      MotionProfile.S_CURVE,
      500,
      500,
      JerkUnits.UNITS_PER_SEC3,
      0,
      MergeMode.DISABLED,
      MergeSpeed.PROGRAMMED,
      50,
      0,
      LockDirection.NONE,
      0,
      0,
      ctx,
    )
```

The last `ctx` argument is not mandatory, but the implementation will need some
way for instruction functions to access shared runtime services. That can be an
explicit argument or an object captured by the PLC types.

## Runtime Types

The runtime needs Python representations for the PLC structures that appear as
instruction operands or whose members are read elsewhere in ladder.

### Minimum first-milestone structures

| Structure | Required Members |
| --- | --- |
| `Timer` | `PRE`, `ACC`, `EN`, `TT`, `DN` |
| `Counter` | `PRE`, `ACC`, `CU`, `DN`, related enable/status bits used by current ladder |
| `Control` | `LEN`, `POS`, `EN`, `EU`, `DN`, `EM`, `ER`, `UL`, `IN`, `FD` |
| `MotionInstruction` | `EN`, `DN`, `ER`, `PC`, `IP`, `ERR`, `EXERR`, `STATUS`, `STATE`, `SEGMENT` |
| `CoordinateSystem` | `MovePendingStatus`, `MovePendingQueueFullStatus`, `PhysicalAxisFault`, and status members used by targeted routines |
| `MotionSeg` | `Valid`, `SegType`, `XY`, `Speed`, `Accel`, `Decel`, `JerkAccel`, `JerkDecel`, `TermType`, `Seq`, `CircleType`, `ViaCenter`, `Direction` |

These structures should be initialized from the checked-in metadata where
possible so that field names and defaults match the exported PLC contract.

### Scalar and array operands

Instruction operands in Python should accept the same kinds of values seen in
normalized ladder:

- immediate numeric values
- enum values for known mode/unit operands
- tag-backed scalar objects
- PLC structure objects
- PLC arrays or array slices where the ladder uses array operands

The implementation should not require callers to manually unpack members that
already exist on the PLC objects.

## Instruction Layer

### First-milestone instruction categories

The first milestone should fully implement the instructions that are actually
used by the checked-in direct-motion and queue routines.

#### Full runtime + import/export support

- `TON`
- `RES`
- `CTU`
- `COP`
- `FLL`
- `FFL`
- `FFU`
- `MOV`
- `ONS`
- `OSR`
- `OSF`
- `OTE`
- `OTL`
- `OTU`
- `JSR`
- `JMP`
- `LBL`
- `MAM`
- `MAS`
- `MAFR`
- `MSO`
- `MSF`
- `MCS`
- `MCLM`
- `MCCM`
- `MCCD`

#### Signature-only placeholders allowed in the first milestone

These can exist as typed stubs if they are not yet needed by the targeted
acceptance routines:

- `PID`
- `SFX`
- `SLS`
- `AFI`
- other non-logical/non-math instructions listed in `plc/instruction_set.md`
  that are not yet exercised

### Instruction signatures

The guiding rule for signatures is:

- preserve Rockwell mnemonic names
- preserve repo-style operand ordering
- use runtime objects for structure operands
- use enums for known unit/mode operands when that improves readability

Examples:

```python
def TON(timer: Timer, ctx: ScanContext | None = None) -> None: ...

def RES(structure: Timer | Counter | Control, ctx: ScanContext | None = None) -> None: ...

def MSO(axis: AxisRef, motion_control: MotionInstruction, ctx: ScanContext) -> None: ...

def MCLM(
  coordinate_system: CoordinateSystem,
  motion_control: MotionInstruction,
  move_type,
  position,
  speed,
  speed_units,
  accel_rate,
  accel_units,
  decel_rate,
  decel_units,
  profile,
  accel_jerk,
  decel_jerk,
  jerk_units,
  termination_type,
  merge,
  merge_speed,
  command_tolerance,
  lock_position,
  lock_direction,
  event_distance,
  calculated_data,
  ctx: ScanContext,
) -> None: ...
```

For `TON`, `RES`, and similar structure-driven instructions, the ladder pseudo
operands do not need to be separate Python arguments. The structure object
should carry the relevant state internally.

## Motion Semantics

Motion instructions are not just syntax nodes. They must mutate runtime state.

### Required side effects

- `MSO`:
  - request servo-on
  - mark the motion control object as active/completed according to the chosen
    simulator model
  - update drive-enable related status visible to later rungs
- `MSF`:
  - request servo-off
  - clear relevant active-motion state
- `MAFR`:
  - clear motion fault state on the targeted axis or motion object
- `MAM`:
  - start axis motion
  - update the motion instruction object's `IP`, `PC`, `DN`, and `ER` bits
  - update axis position and velocity in the simulator
- `MCLM` and `MCCM`:
  - start coordinated motion against a coordinate system object
  - drive pending-queue bits when a second move is queued
  - update the targeted motion instruction object's `IP`, `PC`, `DN`, and `ER`
  - update axis positions and any coordinated-motion status fields used by the
    current ladder
- `MCCD`:
  - update the active or pending coordinated dynamics attached to the runtime
    coordinate system
- `MCS` and `MAS`:
  - stop active motion
  - update completion/error bits and motion status so later rungs see the same
    state transitions as the ladder expects

### First-milestone fidelity target

The target is scan-exact behavior for the routines under test, not merely
eventual-state equivalence.

In practice that means:

- one-shots only pulse for one scan
- timers increment by scan time and set `TT`/`DN` correctly
- `RES` clears the same members the ladder relies on
- motion control objects expose the transient `IP` and `PC` states that later
  rungs read
- `MovePendingStatus` is maintained well enough for the queue routine to work

## Queue Semantics

The standalone `plc/motionQueue/main` routine is part of the first acceptance
slice.

Required behaviors:

- `FFL` pushes `IncomingSeg` into `SegQueue` while updating the `CONTROL`
  structure.
- `FFU` pops into `CurSeg` and `NextSeg` while updating the `CONTROL`
  structure.
- queue validation bits and fault latches behave scan-by-scan.
- `StartQueuedPath` begins current-segment issue.
- `MovePendingStatus` and `MovePendingQueueFullStatus` support alternating
  `MoveA`/`MoveB`.
- `AbortQueue` and `QueueStopRequest` clear runtime state the same way the
  ladder cleanup rungs expect.

## Import/Export Pipeline

### Existing converter stays in place

The current path remains:

```text
studio_copy.rllscrap -> plc_rung_transform.py -> pasteable.rll
```

This work starts from normalized `pasteable.rll`.

### New pipeline

The new ladder pipeline should be:

```text
pasteable.rll -> parser -> AST -> Python codegen
Python source -> AST or direct structured representation -> emitter -> pasteable.rll
```

### Output style requirements

The `.rll` emitter must match the conventions already established by:

- `src/dune_winder/transpiler/ir_to_ld.py`
- `src/dune_winder/plc_rung_transform.py`

The goal is that emitted text is compatible with the existing tests and human
review style in the repo. Whitespace does not have to be byte-for-byte
identical, but the normalized structure must match.

## Relationship to the Existing Transpiler

The existing transpiler under `src/dune_winder/transpiler/` already handles a
restricted Python subset for math-heavy motion helpers like `CapSegSpeed`.

That path should remain active.

### First-milestone integration rule

- Keep the current helper transpiler authoritative for math/helper routines.
- Let the new ladder runtime and import/export layer focus on the non-logical
  and motion-instruction side.
- Support `JSR` in the new ladder runtime so a routine can call either:
  - another imported ladder/Python routine, or
  - a registered Python callable that already exists in the helper path

This avoids blocking the queue milestone on rewriting the current helper
transpiler.

## Suggested Package Layout

The exact filenames can change, but this layout is the intended shape:

```text
src/dune_winder/plc_ladder/
  __init__.py
  ast.py
  types.py
  enums.py
  tags.py
  instructions.py
  runtime.py
  parser.py
  emitter.py
  codegen.py
  jsr_registry.py
  programs/
```

### Module responsibilities

- `types.py`
  - PLC structure dataclasses and runtime object models
- `enums.py`
  - mode/unit/profile enums derived from the Rockwell manuals
- `tags.py`
  - tag store, member resolution, array access, scalar wrappers
- `instructions.py`
  - side-effectful instruction functions with mnemonic names
- `runtime.py`
  - scan context, rung execution, branch evaluation, per-scan stepping
- `parser.py`
  - normalized `.rll` to AST
- `emitter.py`
  - AST to normalized `.rll`
- `codegen.py`
  - AST to editable Python source
- `jsr_registry.py`
  - mapping between `JSR` target names and Python callables or imported routines

## First Acceptance Slice

The first end-to-end target should include:

- direct-motion ready/main/error flow
- `MoveXY_State_2_3`
- `MoveZ_State_4_5`
- `xz_move`
- standalone `motionQueue/main`

The rationale is:

- these routines exercise timers, one-shots, motion status bits, queue control,
  coordinated motion, and reset/abort logic
- they are already the routines most relevant to simulator parity and
  future Python-authored PLC logic

## Test Plan

### Unit tests

- instruction-level behavior for each first-milestone instruction
- timer/counter/control state transitions
- motion instruction bit transitions
- enum and operand serialization rules

### Golden tests

- `.rllscrap -> .rll` compatibility with the existing converter
- `.rll -> AST` parsing for representative current routines
- AST or Python -> `.rll` emission in normalized repo style

### Round-trip tests

- `.rll -> Python`
- Python -> `.rll`
- `.rll -> Python -> .rll`

### Behavioral tests

- queue handshake and alternating `MoveA`/`MoveB`
- direct XY and Z move issue/completion/error cases
- XZ transfer gating
- abort/reset cleanup
- one-shot and timer gating inside latching or queue logic where applicable

### Parity tests

Where the current `SimulatedPLC` already models overlapping behavior, compare
the new ladder-backed path against it to catch regressions or spec drift.

## Phased Implementation Plan

### Phase 1: object model and instruction skeletons

- add runtime structures and tag access model
- add mnemonic instruction function signatures
- fully implement `TON`, `RES`, `MOV`, one-shots, and `CONTROL`-based queue ops

### Phase 2: parser/emitter/codegen

- add normalized `.rll` parser
- add AST and `.rll` emitter
- add Python code generation for editable ladder-like source

### Phase 3: motion semantics

- implement `MSO`, `MSF`, `MAFR`, `MAM`, `MAS`, `MCS`, `MCLM`, `MCCM`, `MCCD`
- connect motion objects to simulator axis state and coordinate-system state

### Phase 4: routine coverage and acceptance

- import and run the targeted direct-motion routines
- import and run the standalone queue routine
- wire `JSR` integration for helper routines such as `CapSegSpeed`
- land round-trip and behavioral tests

## Open Revision Points

These are acceptable places to revise the spec later without changing the core
goal.

- Whether generated Python should be AST-builder style or direct imperative
  rung code, as long as mnemonic instruction calls and side effects are
  preserved.
- Whether instruction functions receive an explicit `ScanContext` argument or
  capture it through bound PLC objects.
- Whether the new ladder runtime extends the current `SimulatedPLC` directly or
  lands as a parallel ladder-backed simulator first.
- Whether some signature-only instructions should be promoted into full support
  earlier if additional ladder routines need them.

## Decision Log

The current decisions captured by this spec are:

- normalized `pasteable.rll` is the canonical text form
- Python instruction calls should use Rockwell mnemonic names
- instructions such as `MCLM` must have real side effects in simulation
- output formatting should follow the current transpiler and `.rllscrap`
  converter conventions
- the first milestone is queue-inclusive, not direct-motion-only
- the existing helper transpiler remains part of the architecture

