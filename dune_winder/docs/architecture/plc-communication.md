# PLC/Winder Communication Architecture

## Scope

This document describes how the Python winder runtime in `src/` communicates
with the Rockwell PLC artifacts stored in `plc/`, and how that link is split
between:

- a general tag-based machine-state and direct-motion interface
- a queued-motion interface for streamed XY path segments
- a simulator path that implements the same tag contract in memory

The goal is to explain the current behavior of the repository as checked in,
not an idealized target design.

Related documents:

- [plc-ladder-workflow.md](plc-ladder-workflow.md) for the Studio 5000 storage/export workflow
- [../planning/plc-architecture-proposals.md](../planning/plc-architecture-proposals.md) for suggested follow-on changes

## End-to-End Runtime Path

### Startup and backend selection

1. `src/dune_winder/main.py` loads `configuration.toml` through `AppConfig`.
2. `ProductionIO` selects either:
   - `ControllogixPLC` for `PLC_MODE=REAL`
   - `SimulatedPLC` for `PLC_MODE=SIM`
3. `BaseIO` wires that backend into:
   - `PLC_Motor` objects for X, Y, and Z
   - `PLC_Logic` for motion/state-machine commands
   - `PLC_Input` wrappers for `MACHINE_SW_STAT[*]` and related tags
   - `Head` and `Camera` helpers that sit on top of PLC tags
4. `Process`, `GCodeHandler`, the web/API command registry, and the control
   state machine all work through that same `BaseIO` object.

### Poll loop and cache behavior

`ControlThread.body()` is the main runtime loop. Each cycle it:

1. calls `io.pollInputs()`
2. which calls `PLC_Logic.poll()`
3. which calls `PLC.Tag.pollAll(self._plc)`
4. which batches all polled tags into reads of at most 14 tag names at a time

That means most of the application reads cached `PLC.Tag` values rather than
performing an immediate PLC round-trip on every access.

Two important exceptions are implemented in `PLC_Logic`:

- `_readTagNow()` does a fresh read for tags where stale data is unsafe
- `_writeTagNow()` fails fast when a direct tag write is rejected

The checked-in code currently uses fresh reads in places such as:

- `getState()`
- `setXZ_Position()`, which fresh-reads `Y_XFER_OK` before issuing an X/Z move

## Transport and Tag Abstractions

### REAL backend

`ControllogixPLC` wraps `pycomm3.LogixDriver`, so the physical link is
Ethernet/CIP against a ControlLogix/CompactLogix-style tag namespace.

At the Python boundary the runtime uses the local `PLC` abstraction:

- `read(tag_or_tag_list)`
- `write((tag_name, value))`
- `PLC.Tag` objects for cached tag instances

### SIM backend

`SimulatedPLC` implements the same `PLC` interface in memory. It mirrors the
current tag contract closely enough for:

- direct motion (`MOVE_TYPE`, position targets, state transitions)
- queue handshake tags (`IncomingSeg*`, `StartQueuedPath`, `AbortQueue`, ...)
- derived machine switch bits (`MACHINE_SW_STAT[*]`)
- the `sim_plc.*` API commands used by tests and debugging

The simulator is intentionally behavioral, not a cycle-accurate model of the
PLC scan.

## Main Communication Layers

### 1. Direct machine-state and motion link

This is the oldest and broadest interface in the codebase. Python writes intent
into controller tags, and PLC ladder decides how to execute it.

#### Python-owned write tags

The main direct-motion contract is written by `PLC_Logic`, `PLC_Motor`, and
related helpers:

- `MOVE_TYPE`
- `X_POSITION`, `Y_POSITION`, `Z_POSITION`
- `XY_SPEED`, `XY_ACCELERATION`, `XY_DECELERATION`
- `Z_SPEED`, `Z_ACCELERATION`, `Z_DECELLERATION`
- `X_DIR`, `Y_DIR`, `Z_DIR`
- `xz_position_target`

#### PLC-owned read tags

The PLC reports machine state back through tags such as:

- `STATE`
- `ERROR_CODE`
- `HEAD_POS`
- `ACTUATOR_POS`
- `Y_XFER_OK`
- `X_axis.*`, `Y_axis.*`, `Z_axis.*`
- `MACHINE_SW_STAT[*]`
- `MORE_STATS_S[0]`
- `tension`, `v_xyz`, `tension_motor_cv`

#### Direct-motion handshake

The direct-motion flow is:

1. Python computes a target and writes the target/speed/accel tags.
2. Python writes `MOVE_TYPE`.
3. `plc/Ready_State_1/main/pasteable.rll` maps `MOVE_TYPE` to a `NEXTSTATE`.
4. `plc/MainProgram/main/pasteable.rll` copies `NEXTSTATE` into `STATE`.
5. The state-specific ladder routine executes the real motion instruction.
6. The PLC clears `MOVE_TYPE` and returns `NEXTSTATE` to `1` when done, or
   sets an error path through `STATE=10`.
7. Python considers the operation complete when `PLC_Logic.isReady()` becomes
   true again (`STATE == READY`).

#### MoveType/state mapping

| Python entry point | `MOVE_TYPE` | PLC state | Ladder artifact |
| --- | ---: | ---: | --- |
| `reset()` | `0` | return to ready/error clear path | `plc/Error_State_10/main/pasteable.rll` |
| `jogXY()` | `1` | `2` | `plc/MoveXY_State_2_3/main/pasteable.rll` |
| `setXY_Position()` | `2` | `3` | `plc/MoveXY_State_2_3/main/pasteable.rll` |
| `jogZ()` | `3` | `4` | `plc/MoveZ_State_4_5/main/pasteable.rll` |
| `setZ_Position()` | `4` | `5` | `plc/MoveZ_State_4_5/main/pasteable.rll` |
| `move_latch()` | `5` | `6` | `plc/Latch_UnLatch_State_6_7_8/main/pasteable.rll` |
| `latchHome()` | `6` | `7` | `plc/Latch_UnLatch_State_6_7_8/main/pasteable.rll` |
| `latchUnlock()` | `7` | `8` | `plc/Latch_UnLatch_State_6_7_8/main/pasteable.rll` |
| `servoDisable()` | `8` | `9` | `plc/UnServo_9/main/pasteable.rll` |
| `PLC_init()` | `9` | `0` then ready | `plc/Initialize/main/pasteable.rll` |
| `setXZ_Position()` | `10` | `12` | `plc/xz_move/main/pasteable.rll` |

### 2. Input and status projection

`plc/MainProgram/main/pasteable.rll` is the broad projection layer between raw
I/O and the tags consumed by Python. It:

- maps physical PLC input points into `MACHINE_SW_STAT[*]`
- computes aggregate bits such as `Z_RETRACTED` and `ALL_EOT_GOOD`
- computes position-derived collision windows
- derives `HEAD_POS` from latch and head state
- mirrors transfer interlocks such as `Y_XFER_OK`
- publishes live velocity terms like `v_xyz` and `v_xy`

That is why the Python side mostly consumes semantic tags and does not talk to
raw module-local I/O addresses directly.

### 3. Queued-motion streaming link

Queued motion is the newer path used for merged/previewed XY path execution,
especially around `G113`-style queueable moves.

#### Runtime owners

- `GCodeHandler` decides when a block of G-code lines can be converted into a
  queued block.
- `QueuedMotionSession` is the runtime state machine that streams segments.
- `QueuedMotionPLCInterface` owns the tag names and UDT serialization.
- `plc/motionQueue/main/pasteable.rll` is the checked-in standalone ladder
  program that consumes those tags.

#### Segment UDT contract

Python writes a `MotionSeg` UDT into `IncomingSeg` with these logical fields:

- `Valid`
- `SegType`
- `XY[2]`
- `Speed`
- `Accel`
- `Decel`
- `JerkAccel`
- `JerkDecel`
- `TermType`
- `Seq`
- `CircleType`
- `ViaCenter[2]`
- `Direction`

The checked-in UDT definition is exported in
`plc/motionQueue/programTags.json`.

#### Queue handshake tags

Python-to-PLC command tags:

- `IncomingSeg`
- `IncomingSegReqID`
- `AbortQueue`
- `StartQueuedPath`
- `QueueStopRequest`

PLC-to-Python status tags:

- `LastIncomingSegReqID`
- `IncomingSegAck`
- `MotionFault`
- `QueueFault`
- `CurIssued`
- `NextIssued`
- `ActiveSeq`
- `PendingSeq`
- `QueueCount`
- `UseAasCurrent`
- `X_Y.MovePendingStatus`
- `FaultCode`

#### Queue handshake sequence

`QueuedMotionSession` performs the following sequence:

1. pulse `AbortQueue` to force a clean queue reset
2. clear `QueueStopRequest`
3. synchronize the local request counter from `LastIncomingSegReqID`
4. for each segment:
   - write `IncomingSeg`
   - increment and write `IncomingSegReqID`
   - wait for `IncomingSegAck == segment.seq`
5. prefill up to the PLC queue depth (`32`)
6. pulse `StartQueuedPath`
7. wait for `CurIssued` to go true
8. keep streaming additional segments whenever `QueueCount` shows free room
9. finish when the PLC reports an idle queue and no issued moves remain

#### What the PLC queue routine does

`plc/motionQueue/main/pasteable.rll` performs the matching work:

- deduplicates writes via `IncomingSegReqID != LastIncomingSegReqID`
- validates line and arc segment fields
- `FFL`s valid segments into `SegQueue`
- copies `IncomingSeg.Seq` into `IncomingSegAck`
- on `StartQueuedPath`, pulls the first segment with `FFU`
- alternates between `MoveA` and `MoveB` so the next move can be prepared while
  the current one is in progress
- issues `MCLM` for lines and `MCCM` for arcs
- rotates `CurSeg`/`NextSeg` and `ActiveSeq`/`PendingSeq`
- latches `QueueFault`/`MotionFault` and handles abort/reset cleanup

#### Important implementation detail

Based on the checked-in Python code, the active queue integration target is the
standalone `plc/motionQueue/main/pasteable.rll` program, not the older
`plc/enqueueRoutineStateful` artifact. The Python runtime writes queue tags and
never drives `STATE=13`, which matches the standalone `motionQueue` routine and
does not match the state-gated variant.

That makes `plc/enqueueRoutineStateful` best interpreted as a related or older
alternate integration path unless the PLC project explicitly wires it in.

### 4. Experimental 3D arc queue path

There is also an experimental 3D arc path:

- Python client: `src/dune_winder/queued_motion/queue_client_3d_arc.py`
- ladder text: `plc/enqueueRoutine_3d_arc.txt`

This path defines its own `IncomingSeg3D*`, `StartQueuedPath3D`, and
`MotionFault3D` tag family and coordinates against the XY queue as an
interlock.

It is not wired into `PLC_Logic` or the normal `GCodeHandler` execution path,
so it should be treated as a development branch rather than the primary
runtime-to-PLC link.

## G-code Integration

Queued motion is not used for every move. The current `GCodeHandler` behavior
is:

- normal XY, Z, XZ, head, and latch actions still go through direct
  `PLC_Logic` commands
- queueable XY blocks are previewed, optionally merged, and then launched as a
  `QueuedMotionSession`
- preview approval/cancel is exposed through typed API commands:
  - `process.get_queued_motion_preview`
  - `process.continue_queued_motion_preview`
  - `process.cancel_queued_motion_preview`

This means the runtime currently supports two motion-command dialects at once:

- command-per-move through `MOVE_TYPE`
- stream-per-block through `IncomingSeg` and queue control tags

## Simulator and API Support

The simulator is part of the communication story because it exercises the same
contract the UI and control code use in production.

Relevant pieces:

- backend selection: `ProductionIO`
- simulator implementation: `SimulatedPLC`
- debug API:
  - `sim_plc.get_status`
  - `sim_plc.get_tag`
  - `sim_plc.set_tag`
  - `sim_plc.clear_override`
  - `sim_plc.inject_error`
  - `sim_plc.clear_error`
- cached tag inspection:
  - `low_level_io.get_tags`
  - `low_level_io.get_tag`

The simulator supports the queue handshake well enough for the current unit
tests, including `AbortQueue`, `StartQueuedPath`, queue counts, and segment
acknowledgment.

## PLC Artifact Map

The most relevant PLC files for understanding the current link are:

- `plc/MainProgram/main/pasteable.rll`
  - controller-wide projections into semantic machine-state tags
- `plc/Ready_State_1/main/pasteable.rll`
  - `MOVE_TYPE` to `NEXTSTATE` dispatch
- `plc/MoveXY_State_2_3/main/pasteable.rll`
  - XY jog/seek execution
- `plc/MoveZ_State_4_5/main/pasteable.rll`
  - Z jog/seek execution and latch-aware interlocks
- `plc/Latch_UnLatch_State_6_7_8/main/pasteable.rll`
  - head/latch actuator state machine
- `plc/xz_move/main/pasteable.rll`
  - combined X/Z transfer motion using `xz_position_target`
- `plc/Error_State_10/main/pasteable.rll`
  - stop/fault recovery path
- `plc/Initialize/main/pasteable.rll`
  - PLC init behavior
- `plc/motionQueue/main/pasteable.rll`
  - active queued-motion ladder program
- `plc/enqueueRoutineStateful`
  - state-gated queue variant
- `plc/enqueueRoutine_3d_arc.txt`
  - experimental 3D arc queue branch

## Metadata and Export Tooling

The repository also contains maintenance tooling for the PLC contract itself:

- `src/dune_winder/plc_metadata_export.py`
  - connects to a live PLC and scaffolds `plc/controller_level_tags.json` plus
    per-program `programTags.json`
- `src/dune_winder/plc_tag_values_export.py`
  - reads every tag listed in those JSON files and writes live values back into
    them

Those files are useful because they expose the current controller/program tag
surface and UDT definitions that the Python runtime depends on.

## Current Architectural Shape

Today the communication link is best thought of as:

- a tag-based boundary, not an RPC boundary
- PLC-owned safety and motion execution, with Python supplying intent
- a cached-poll model for normal telemetry
- fresh reads only in a few safety-sensitive places
- one shared queue contract for merged XY motion
- a simulator that mirrors the contract instead of mirroring the ladder scan

That design works, but it also means the contract is duplicated across:

- string tag names in Python
- simulator behavior in Python
- ladder text in `plc/`
- exported metadata in `plc/*.json`

The companion proposal document outlines the main improvements that would make
that contract easier to evolve safely.
