# PLC Ladder Simulator Assumptions

This document describes the current assumptions and approximations made by the
ladder-backed PLC simulator in `PLC_MODE=SIM` with `PLC_SIM_ENGINE=LADDER`.

It is intentionally a description of the code as it exists today, not a target
specification.

## Scope

The ladder-backed simulator currently models the direct-motion and queued-motion
slice of the PLC logic. It is designed to execute the checked-in
`plc/**/pasteable.rll` routines that are currently loaded by the simulator, not
the full PLC project.

## Loaded Ladder Routines

The simulator currently executes these routines each scan, in this order:

1. `MainProgram/main`
2. `Initialize/main`
3. `Ready_State_1/main`
4. `MoveXY_State_2_3/main`
5. `MoveZ_State_4_5/main`
6. `xz_move/xz_move`
7. `Error_State_10/main`
8. `motionQueue/main`

It also loads `MoveXY_State_2_3/xy_speed_regulator` as a callable subroutine.

These routines are not part of the active ladder execution path today:

- `Safety`
- `Camera`
- `PID_Tension_Servo`
- `Latch_UnLatch_State_6_7_8`
- `UnServo_9`
- `EOT_Trip_11`

## Tag And Metadata Assumptions

- The simulator seeds its tag inventory from `plc/controller_level_tags.json`
  plus all `plc/*/programTags.json`.
- `TagStore(..., use_exported_values=True)` is used, so exported tag values from
  the metadata snapshots are treated as the simulator's starting values unless
  they are explicitly overridden during bootstrap.
- Symbol lookup is effectively:
  `current program tag -> uniquely matching program tag -> controller tag -> builtin value -> 0`.
- If a path is not found in tag metadata, the runtime falls back to
  `builtin_values`; if it still does not exist, reads return `0`.
- Program tags shadow controller tags when names collide.
- `DWORD` values that are exported as single-element arrays are treated as
  packed bitfields, so tags such as `MACHINE_SW_STAT[17]`, `SetBit[0]`, and
  `oneshotsb[1]` are handled as bit access on an integer, not as Python list
  access.

## Scan Model Assumptions

- The runtime uses a fixed scan time of `100 ms`.
- One runtime advance happens per scan, before ladder routines execute.
- `PLC.Tag.pollAll()` wraps reads in explicit `begin_scan_cycle()` /
  `end_scan_cycle()` hooks so one poll cycle advances one simulator scan.
- If a direct tag read happens outside a poll cycle, that read advances one
  scan on demand.
- `MainProgram` executes before the other routines each scan so that derived
  inputs and controller-level state are refreshed before program logic runs.
- `Initialize/main` is skipped unless the simulator is actually entering the
  PLC init state. This prevents the initialization routine from re-clearing
  state on every scan.

## Ladder Execution Assumptions

- Rungs execute from the parsed AST, not from generated Python.
- The parser/emitter/codegen share the same normalized ladder model.
- The runtime currently supports the instruction set needed by the implemented
  slice, including:
  `XIC`, `XIO`, `OTE`, `OTL`, `OTU`, `MOV`, `ADD`, `CPT`, `CMP`, `EQU`, `NEQ`,
  `GEQ`, `GRT`, `LEQ`, `LES`, `LIM`, `TON`, `RES`, `ONS`, `OSR`, `COP`, `FLL`,
  `FFL`, `FFU`, `JSR`, `JMP`, `LBL`, `NOP`, `MSO`, `MSF`, `MAFR`, `MAS`, `MCS`,
  `MAM`, `MCLM`, `MCCM`, and `MCCD`.
- `BST/NXB/BND` branching is represented in the AST and executed from that
  structure rather than as literal opcodes at runtime.
- `CMP` and `CPT` expressions are evaluated by translating Rockwell-style
  formulas into restricted Python expressions and calling `eval()` with a small
  allowed function set (`ABS`, `ATN`, `COS`, `SIN`, `SQR`, `MOD`).
- Unknown or unsupported opcodes still raise an error instead of being silently
  ignored.

## Motion Model Assumptions

- Axis and coordinated motion are modeled scan-by-scan, not as instant moves.
- Motion duration is derived from `distance / speed` and the fixed scan period.
- Motion uses simplified constant-velocity interpolation to the target.
- Acceleration values are stored onto simulated axis structures, but the motion
  profile itself is not a full jerk-limited or S-curve implementation.
- `MAM` drives one axis to its target and updates control bits such as `IP`,
  `PC`, and `DN` in the simplified runtime model.
- `MCLM` and `MCCM` support one active coordinated move and one pending move per
  coordinate system, which is enough for the currently modeled queue logic.
- `MovePendingStatus` and `MovePendingQueueFullStatus` are compatibility-level
  queue indicators maintained by the runtime, not full controller queue models.
- `MCCM` currently preserves the circle direction operand, but the actual path
  is still simulated as endpoint-oriented coordinated motion rather than full
  arc geometry.

## Queue And JSR Assumptions

- `motionQueue/main` is executed from ladder each scan.
- Imported ladder subroutines are preferred when they are loaded.
- `CapSegSpeed` is currently a Python fallback JSR, not a ladder-executed
  routine. It calls the existing queue speed-capping helper in Python.
- Queue activity forces a compatibility state of `STATE=13` when
  `CurIssued`, `NextIssued`, or `X_Y.MovePendingStatus` is active.
- When queue activity clears, the compatibility state layer returns the machine
  to `STATE=1`.

## PLC / IO Assumptions

- The simulator synthesizes PLC input points from axis positions, `HEAD_POS`,
  `ACTUATOR_POS`, and configured machine limits inherited from the base
  simulator.
- Retracted, extended, transfer-window, park, frame-location, and stage/fixed
  present/latched inputs are all derived values, not independent simulated
  devices.
- End-of-travel inputs are currently permissive by default:
  `PLUS_X_EOT`, `MINUS_X_EOT`, `PLUS_Y_EOT`, `MINUS_Y_EOT`, and `Z_EOT` default
  to healthy values unless explicitly overridden.
- Several safety-adjacent digital inputs are also hard-coded permissive for the
  implemented slice, for example the `DUNEW2PLC2` points used by `MainProgram`.
- `APA_IS_VERTICAL` is currently hard-coded true through the synthesized input
  map unless overridden.
- `set_tag(..., override=True)` takes precedence over derived machine bits and
  derived local I/O until the override is cleared.

## Latch Assumptions

- The real `Latch_UnLatch_State_6_7_8/main` routine is not executed as part of
  the active ladder scan set.
- Latching is currently handled by a simulator-side compatibility model.
- The compatibility model assumes every commanded latch transition succeeds.
- `MOVE_LATCH`, `MOVE_HOME_LATCH`, and `MOVE_LATCH_UNLOCK` move through their
  PLC states (`6`, `7`, `8`) and then request `NEXTSTATE=1` without modeling the
  timers, pulse trains, timeout counters, or fault branches from the real ladder
  routine.
- `MOVE_LATCH` captures `PREV_ACT_POS` and cycles `ACTUATOR_POS` through the
  existing three-position application contract: `0 -> 1 -> 2 -> 0`.
- When latch motion reaches `ACTUATOR_POS == 2`, the head toggles between stage
  side and fixed side if it is currently on one of those sides.
- `MOVE_HOME_LATCH` sets `ACTUATOR_POS=0` and marks the latch as homed.
- `MOVE_LATCH_UNLOCK` sets `ACTUATOR_POS=2` and clears the homed flag.
- The four-position interpretation visible inside the real latch routine is not
  currently exposed as a first-class application-facing simulator state.

## Known Simplifications And Gaps

- The simulator is parity-oriented for the currently loaded routines, not a
  full Rockwell controller emulator.
- The runtime is intentionally permissive about unresolved non-metadata values
  and treats many of them as builtins or zero.
- Camera, safety, servo state machine coverage, and full latch/eot behavior are
  still incomplete.
- Generated Python exists for inspection and tests, but it is not yet the
  source-of-truth path for authoring PLC logic in the simulator.
