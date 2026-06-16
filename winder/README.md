# DUNE Winder (UChicago)

Python 3 control software and web UI for the UChicago APA winder.

The supported setup and development workflow starts at the monorepo root.
See [../README.md](../README.md) for the canonical `uv sync`, run, test, and
debug commands. This README keeps package-specific operational detail only.

## What This Repository Contains

- Runtime control process, state machine logic, and hardware I/O integration.
- Desktop/mobile web UI served from `web/`.
- Programmatic G-code generation for U/V/X/G templates.
- Queued-motion planning, preview, and PLC queue execution utilities.
- Rockwell PLC ladder text and exported tag metadata under `plc/`.
- Python-to-Rockwell Ladder Logic transpilation helpers for selected motion code.
- Unit tests for recipe generation, process behavior, and core utilities.

## Requirements

- Follow the root workflow in [../README.md](../README.md) for setup and sync
- Network access to the production PLC and camera for live hardware operation

## Run The Application

From the monorepo root:

```bash
uv run python -m dune_winder
```

The installed entrypoint also works:

```bash
uv run dune-winder
```

### Runtime flags

The main process supports command-line flags in `KEY=VALUE` form:

- `START=TRUE|FALSE`: auto-start the current APA after launch.
- `LOG=TRUE|FALSE`: echo runtime log messages to stdout.
- `LOG_IO=TRUE|FALSE`: log low-level I/O activity (very verbose).
- `PLC_MODE=REAL|SIM`: override PLC backend mode for this launch.

Example:

```bash
uv run python -m dune_winder START=TRUE LOG=TRUE LOG_IO=FALSE PLC_MODE=SIM
```

Runtime default PLC mode is configured in `configuration.toml` with:

```toml
plcMode = "REAL" # or "SIM"
```

## Development
Use the root README for setup, syncing, testing, linting, and editor workflow.

## Remote Command API v2

The web server exposes typed JSON command endpoints:

- `POST /api/v2/command`
- `POST /api/v2/batch`

Each command uses an explicit `{"name": "...", "args": {...}}` contract and
returns a structured response envelope:

```json
{
  "ok": true,
  "data": {},
  "error": null
}
```

Legacy expression/XML remote command shims have been removed.

## Template G-Code Generation

### V-layer CLI generator

Write a recipe file with the standard header/hash:

```bash
uv run python -m dune_winder.recipes.v_template_gcode gc_files/V-layer.gc --recipe
```

Apply special input overrides:

```bash
uv run uv run python -m dune_winder.recipes.v_template_gcode gc_files/V-layer.gc --recipe --special transferPause=true --special head_a_offset=7
```

### UV tangency analysis utility

Replay a rendered U/V wrap site and inspect commanded vs actual wire geometry:

```bash
uv run python -m dune_winder.analysis.uv_tangency_analysis --layer U --wrap 71 --site top_a_head_end
```

Compare the same site across both UV layers:

```bash
uv run python -m dune_winder.analysis.uv_tangency_analysis --layer U --wrap 71 --site top_a_head_end --compare-layer V
```

### X/G-layer generator (Python API)

```python
from dune_winder.recipes.xg_template_gcode import write_xg_template_file

special_inputs = {
  "references": {
    "head": {"wireY": 200.0},
    "foot": {"wireY": 400.0},
  },
  "offsets": {
    "headA": 1.5,
    "headB": 2.5,
    "footA": -0.5,
    "footB": -1.5,
  },
  "transferPause": False,
}

write_xg_template_file("X", "gc_files/X-layer.gc", specialInputs=special_inputs)
write_xg_template_file("G", "gc_files/G-layer.gc", specialInputs=special_inputs)
```

### Template generator state in the app/API

The built-in U/V template generators now persist draft state and expose these
toggles through the typed command API:

- `transferPause`
- `includeLeadMode`
- `stripG113Params`

`stripG113Params` removes parameter payloads from generated `G113` lines when a
downstream consumer requires bare `G113` commands.

## Queued Motion And Waypoint Planning

Queued motion now supports live preview and smoother waypoint traversal through
fillet/biarc planning, with safety validation against machine bounds and keepout
regions.

CLI/GUI test tooling lives in:

- `src/motionQueueTest.py`
- `src/motionQueueTest_gui.py`

Example waypoint-planning invocation:

```bash
uv run python src/motionQueueTest.py --pattern waypoint_path --waypoints "1000,200;2000,900;3500,1400;5000,500" --waypoint-order shortest --visualize-only
```

The web/API layer also exposes queued-motion preview commands:

- `process.get_queued_motion_preview`
- `process.continue_queued_motion_preview`
- `process.cancel_queued_motion_preview`

## PLC/Winder Communication

The PLC link in this repository has two main paths:

- Direct motion/state control: Python writes intent tags such as
  `STATE_REQUEST`, `X_POSITION`, `Y_POSITION`, `Z_POSITION`, and speed/accel
  tags. `MOVE_TYPE` remains for reset / PLC-init compatibility only. The PLC
  state routines in `plc/` validate interlocks, issue the Rockwell motion
  instructions, and report completion through `STATE`, `ERROR_CODE`, and axis
  status tags.
- Queued motion: Python serializes `MotionSeg` UDT payloads into `IncomingSeg`
  and drives the queue handshake tags (`IncomingSegReqID`, `IncomingSegAck`,
  `StartQueuedPath`, `AbortQueue`, `QueueCount`, `CurIssued`, `NextIssued`,
  and related fault tags). The ladder counterpart lives in the queue program's
  `.rung` projection under `plc/` (see `AGENTS.md` for the PLC edit workflow).

The runtime uses `pycomm3` in `REAL` mode and an in-memory `SimulatedPLC` in
`SIM` mode. Most reads come from the shared `PLC.Tag` polling cache in the
control loop; a few safety-sensitive checks use immediate reads instead.

## Python To Ladder Logic Transpiler

The repository includes a small Python-to-Rockwell Ladder Logic transpiler for
selected motion-planning functions under `src/dune_winder/transpiler/`.

Checked-in PLC artifacts live under `winder/plc/` (the paths below are
relative to this `winder/` package) and are regenerated from the Studio 5000
ACD by `uv run plc-acd-export` (see `AGENTS.md`). The per-routine
`*_Routine_RLL.L5X` is the single source of
truth for rung text; the `.rung` file is the readable projection agents edit:

- `plc/controller_level_tags.json`
- `plc/<program>/programTags.json`
- `plc/<program>/<routine>_Routine_RLL.L5X`  ← source of truth for rung text
- `plc/<program>/<routine-dir>/<routine>.rung`  ← readable projection; WHAT YOU EDIT

See [`../AGENTS.md`](../AGENTS.md) (PLC section) and the format references
under `plc/` (`RUNG_FORMAT.md`, `instruction_set.md`, `RLL_FORMAT.md`) for the
full edit/compile/re-export cycle.

CLI usage:

```bash
uv run python -m dune_winder.transpiler src/dune_winder/queued_motion/segment_patterns.py cap_segments_speed_by_axis_velocity
```

Python API usage:

```python
from dune_winder.transpiler import transpile

source = open("src/dune_winder/queued_motion/segment_patterns.py", encoding="utf-8").read()
ld_text = transpile(source, function_names=["cap_segments_speed_by_axis_velocity"])
print(ld_text)
```

## Grafana Monitoring Dashboard

The winder pushes PLC tag values directly into InfluxDB after each poll cycle
(~10 Hz) and a pre-configured Grafana dashboard displays them in real time.

### Requirements

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (runs Grafana and InfluxDB as containers — nothing else to install)

### Monitored tags

| Metric | Tag | Range |
|---|---|---|
| Tension | `tension` | 0–10 N |
| XYZ velocity setpoint | `v_xyz` | 0–1100 mm/s |
| Tension motor CV | `tension_motor_cv` | 0–10 |
| X axis position / velocity | `X_axis.ActualPosition/Velocity` | −10–7200 mm |
| Y axis position / velocity | `Y_axis.ActualPosition/Velocity` | −10–2688 mm |
| Z axis position / velocity | `Z_axis.ActualPosition/Velocity` | −5–420 mm |

### Usage

**1.** Start the winder application:

```bash
dune-winder
```

**2.** Start Grafana and InfluxDB from the project root:

```bash
docker compose up -d
```

**3.** Open Grafana in your browser:

```
http://localhost:3000
```

Login: `admin` / `dune_winder`

The "Dune Winder PLC Monitor" dashboard loads as the home page and
auto-refreshes every second. The default time window is the last 5 minutes.

InfluxDB is also accessible directly at `http://localhost:8086`
(login: `admin` / `dune_winder`, org: `dune`, bucket: `winder`).

### Architecture

No extra PLC network traffic is added. `MetricsCollector` registers a callback
that runs immediately after each `PLC.Tag.pollAll()` call in the existing
control loop — it reads from the already-cached tag values and pushes a data
point to InfluxDB asynchronously (write queued to a background thread, so the
control loop is never blocked). Grafana queries InfluxDB directly using Flux.

## Key Paths

- Configuration: `configuration.toml`
- Machine calibration: `config/`
- Generated recipes: `gc_files/`
- Runtime logs/cache: `cache/`
- Web UI assets: `web/`

## Contact

[oye@uchicago.edu](mailto:oye@uchicago.edu)
