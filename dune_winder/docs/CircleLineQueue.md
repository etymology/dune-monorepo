# Circle + Line Motion Queue (MCLM/MCCM)

This document records the new mixed-segment queue implementation that supports:

- Linear segments issued with `MCLM`
- Circular/tangential arc segments issued with `MCCM`
- Queue blending across line-line, line-arc, and arc-arc transitions

Primary implementation files:

- `src/enqueueRoutine.txt`
- `src/dune_winder/queued_motion/queue_client.py`
- `src/dune_winder/queued_motion/segment_types.py`
- `src/dune_winder/queued_motion/segment_patterns.py`
- `src/dune_winder/queued_motion/safety.py`
- `src/motionQueueTest.py`

## PLC Queue Routine Summary

The PLC routine now validates and queues both segment types:

- `SegType = 1` for line (`MCLM`)
- `SegType = 2` for circle (`MCCM`)

Validation is split into line and arc rungs, then OR-combined with branch syntax:

- `BST XIC SegValidLine NXB XIC SegValidArc BND OTE SegValid`

The queue state machine uses dual command buffers (`MoveA`/`MoveB`) for blending:

- Current segment loads into active buffer.
- Next segment preloads into alternate buffer while current is in progress.
- On pending completion, buffers rotate and continue.

Instruction argument arrays are indexed explicitly for Studio 5000 text form:

- `Cmd*_XY[0]`
- `Cmd*_ViaCenter[0]`

## MotionSeg UDT Contract (Required Fields)

The incoming segment payload (`IncomingSeg`) must provide all fields below.

| Field | Type | Notes |
|---|---|---|
| `Valid` | `BOOL` | Must be `1` to enqueue |
| `SegType` | `DINT` | `1=line`, `2=circle` |
| `XY` | `REAL[2]` | Target endpoint `[X,Y]` |
| `CircleType` | `DINT` | Used for circles (`0..3`) |
| `ViaCenter` | `REAL[2]` | Via/center args for `MCCM` |
| `Direction` | `DINT` | 2D arc direction (`0..3`) |
| `Speed` | `REAL` | Must be `>0` |
| `Accel` | `REAL` | Must be `>0` |
| `Decel` | `REAL` | Must be `>0` |
| `JerkAccel` | `REAL` | Jerk value (`% of Time` in routine) |
| `JerkDecel` | `REAL` | Jerk value (`% of Time` in routine) |
| `TermType` | `DINT` | `0..6` |
| `Seq` | `DINT` | Segment sequence number |

Python-side UDT packing is in `MotionQueueClient._segment_to_udt(...)`.

## Required PLC Tags

External handshake/control tags used by Python:

- `IncomingSeg` (MotionSeg UDT instance)
- `IncomingSegReqID`
- `LastIncomingSegReqID`
- `IncomingSegAck`
- `StartQueuedPath`
- `AbortQueue`

Status/diagnostic tags read by Python:

- `MotionFault`
- `QueueFault`
- `MoveA.ER`
- `MoveB.ER`
- `CurIssued`
- `NextIssued`
- `ActiveSeq`
- `PendingSeq`
- `QueueCount`
- `UseAasCurrent`
- `X_Y.MovePendingStatus`
- `FaultCode`

Queue/internal tags used by the routine:

- `SegQueue[0..31]` (MotionSeg array, depth 32)
- `QueueCtl` (FFL/FFU control)
- `CurSeg`, `NextSeg`
- `CmdA_*`, `CmdB_*` command fields (`XY[2]`, `ViaCenter[2]`, dynamics, type, term)

## MCLM/MCCM Invocation Format

The routine uses the corrected text instruction format for both command channels.

Examples:

```text
MCLM X_Y MoveA 0 CmdA_XY[0] CmdA_Speed "Units per sec" CmdA_Accel "Units per sec2" CmdA_Decel "Units per sec2" S-Curve CmdA_JerkAccel CmdA_JerkDecel "% of Time" CmdA_TermType Disabled Programmed CmdTolerance 0 None 0 0
MCCM X_Y MoveA 0 CmdA_XY[0] CmdA_CircleType CmdA_ViaCenter[0] CmdA_Direction CmdA_Speed "Units per sec" CmdA_Accel "Units per sec2" CmdA_Decel "Units per sec2" S-Curve CmdA_JerkAccel CmdA_JerkDecel "% of Time" CmdA_TermType Disabled Programmed CmdTolerance 0 None 0 0
```

Equivalent `CmdB_*` calls are used for the alternate in-flight segment.

## Python Queueing Architecture

`motionQueueTest.py` is now a thin orchestration script over reusable modules:

- `segment_types.py`: segment dataclass and geometry primitives
- `segment_patterns.py`: path generation + term assignment + speed planning
- `safety.py`: machine bounds and keepout validation
- `queue_client.py`: PLC UDT writes, request/ack handshake, queue streaming

Pipeline per run:

1. Build segment list from selected pattern.
2. Optionally tune for constant-velocity operation.
3. Cap each segment speed by axis component limits.
4. Assign merge term types from tangency.
5. Validate full path against machine safety limits.
6. Stream to PLC FIFO and execute queued path.

## Term-Type Propagation

`apply_merge_term_types(...)` sets term type per merge:

- Tangential merge: default `term_type 4`
- Non-tangential merge: default `term_type 0`
- Optional final segment override

Tangency is decided from segment end/start tangents with tolerance
(`DEFAULT_TANGENCY_ANGLE_TOLERANCE_DEG`, currently `2.0` degrees).

## Dynamics and Speed Limits

Default segment dynamics (`MotionSegment`):

- `speed = 1000`
- `accel = 2000 mm/s^2`
- `decel = 2000 mm/s^2`
- `jerk_accel = 100`
- `jerk_decel = 100`

Routine jerk units are configured as `"% of Time"`.

Component-wise velocity capping is applied in
`cap_segments_speed_by_axis_velocity(...)`:

- `V_X_MAX = 825`
- `V_Y_MAX = 600`
- Final segment speed is `min(requested_speed, cap_from_x, cap_from_y)`

If `--start-x/--start-y` are not provided, the first segment start direction is
unknown and is conservatively capped to `min(V_X_MAX, V_Y_MAX)`.

## Safety Constraints and Calibration

Safety limits are loaded from machine calibration (`config/machineCalibration.json`):

- `limitLeft`, `limitRight`, `limitBottom`, `limitTop`
- `transferLeft`
- `headwardPivotX`, `headwardPivotY`
- `headwardPivotXTolerance`, `headwardPivotYTolerance`

Validation rejects paths that:

- Exit machine XY bounds
- Enter transfer keepout region
- Enter/intersect winding-head pivot keepout region

## Pattern Coverage

The queue supports mixed line/circle generation from reusable patterns, including:

- `lissajous` (tangent arc tessellation)
- `tangent_mix`
- `fibonacci_arcs` (bounded, cw/ccw)
- `apsidal_orbit` (elliptical precessing)
- `archimedean_spiral`
- `waypoint_path` (line + tangent arcs, min arc radius, optional shortest order)

## Troubleshooting (No Motion / Unexpected Stops)

If segments enqueue but motion does not start:

1. Confirm `QueueCount >= 2` before `StartQueuedPath`.
2. Confirm `IncomingSegAck` advances to each `Seq`.
3. Check `MotionFault`, `QueueFault`, `FaultCode`, `MoveA.ER`, `MoveB.ER`.
4. Verify `SegType`, `CircleType`, `Direction`, and `TermType` are in valid ranges.
5. Verify first move is valid from current position (`--start-x/--start-y` helps).

If motion stops between segments despite many `term_type=4` values:

1. Geometry may be non-tangential at the merge.
2. Segment may be extremely short/degenerate.
3. Queue prefetching may fail if queue runs too shallow or faults occur mid-stream.
