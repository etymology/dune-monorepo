# Waypoint Path Planning

This document describes the waypoint path planning workflow implemented for
`motionQueueTest.py`, including the new GUI planner and live position overlay.

## Scope

The waypoint workflow now supports:

- Interactive waypoint selection on an XY canvas (`motionQueueTest_gui.py`).
- CLI waypoint input (`--waypoints` / `--waypoints-file`).
- Automatic line/arc segment generation for smooth paths.
- Safety validation against machine bounds and keepout regions.
- Optional execution on PLC queue logic.
- Live machine position overlay from:
  - `X_axis.ActualPosition`
  - `Y_axis.ActualPosition`

## Key Files

- `src/motionQueueTest.py`
  - Existing test runner with `waypoint_path` support.
  - New `--gui` flag launches the planner GUI.
- `src/motionQueueTest_gui.py`
  - Interactive waypoint planning/execution UI.
  - Polls live X/Y actual position tags and draws them on the canvas.
- `src/dune_winder/queued_motion/segment_patterns.py`
  - `waypoint_path_segments(...)`
  - waypoint ordering and tangent biarc tessellation.
- `src/dune_winder/queued_motion/safety.py`
  - motion-space safety and keepout validation.
- `src/dune_winder/queued_motion/queue_client.py`
  - queue streaming and execution against PLC.

## Planning Pipeline

Both CLI and GUI use the same underlying planning pipeline:

1. Collect waypoint list.
2. Build `waypoint_path` segments with `build_segments(...)`.
3. Optionally tune for constant-velocity mode.
4. Cap speed by X/Y axis component limits.
5. Apply merge termination types (tangential vs non-tangential).
6. Validate complete motion path inside configured safety limits.

This keeps GUI behavior consistent with the established queue test flow.

## Waypoint Path Generation Details

Waypoint segment generation (`waypoint_path_segments`) does the following:

- Removes consecutive duplicate points.
- Supports ordering modes:
  - `input`: preserves click/input order.
  - `shortest`: nearest-neighbor + 2-opt open path optimization.
- Estimates tangents at each waypoint.
- Uses tangent biarc tessellation to generate line/arc segments.
- Enforces minimum arc radius:
  - arcs tighter than threshold are rewritten to lines.
- Optional stop/start fallback (`waypoint_allow_stops`):
  - planner first attempts smooth biarc path through waypoints.
  - if smooth segments violate machine XY bounds, offending spans fallback to
    linear moves between waypoints.
  - merge assignment then uses stop transitions (`term_type=1`) at
    non-tangential joins in this mode.
- Applies a planner timeout for `shortest` ordering:
  - default `3.0 s` (`DEFAULT_WAYPOINT_PLANNER_TIMEOUT_S`).
  - if exceeded, planning raises `TimeoutError` with guidance to reduce waypoint
    count or use `waypoint_order_mode='input'`.

## GUI Planner

Launch options:

```bash
python src/motionQueueTest.py --gui
```

or directly:

```bash
python src/motionQueueTest_gui.py
```

### Main interactions

- Left click: add waypoint.
- Right click: undo last waypoint.
- `Replan`: rebuild segment list using current settings.
- `Execute Path`: enqueue and run plan on PLC (with confirmation dialog).

### Controls exposed

- PLC path.
- Optional start X/Y.
- Waypoint order mode (`input` or `shortest`).
- Term type.
- Min arc radius.
- Allow stop/start fallback.
- Speed.
- Min segment length.
- Constant-velocity tuning toggle.

The following are now fixed to machine-intrinsic values in the GUI:

- `Vx max` / `Vy max` (internal axis speed caps).
- Queue depth (`PLC_QUEUE_DEPTH`).

## Live Position Overlay

The GUI runs a background polling loop using `pycomm3.LogixDriver`:

- Reads `X_axis.ActualPosition`.
- Reads `Y_axis.ActualPosition`.
- Updates every `0.20 s` (`POSITION_POLL_S`).
- Retries on comm error every `1.00 s` (`POSITION_ERROR_RETRY_S`).

Display behavior:

- Current XY is shown in the control panel text.
- Current XY is superimposed on the selection canvas as a cyan crosshair and dot.
- Overlay is drawn only when the position is within machine plot bounds.
- On connection/tag errors, overlay is hidden and a status message is shown.

## CLI Usage (Waypoint Path)

Example with inline waypoints:

```bash
python src/motionQueueTest.py \
  --pattern waypoint_path \
  --waypoints "1000,200;2000,900;3500,1400;5000,500" \
  --waypoint-order shortest \
  --waypoint-min-arc-radius 80 \
  --waypoint-allow-stops \
  --visualize-svg waypoints.svg \
  --visualize-only
```

Example with waypoint file:

```bash
python src/motionQueueTest.py \
  --pattern waypoint_path \
  --waypoints-file path_points.json \
  --start-x 900 --start-y 250
```

## Safety and Execution Notes

- At least two distinct waypoints are required.
- Safety checks enforce:
  - machine XY limits from calibration,
  - transfer-region restrictions,
  - winding-head pivot keepout protection.
- Queue execution uses the same `run_queue_case(...)` stream/prefill logic as
  other motion test patterns.
- Execute only when the machine state is confirmed safe for motion.
