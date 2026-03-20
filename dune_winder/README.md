# DUNE Winder (UChicago)

Python 3 control software and web UI for the UChicago APA winder.

## What This Repository Contains

- Runtime control process, state machine logic, and hardware I/O integration.
- Desktop/mobile web UI served from `web/`.
- Programmatic G-code generation for U/V/X/G templates.
- Queued-motion planning, preview, and PLC queue execution utilities.
- Rockwell PLC ladder text and exported tag metadata under `plc/`.
- Python-to-Rockwell Ladder Logic transpilation helpers for selected motion code.
- Unit tests for recipe generation, process behavior, and core utilities.

## Requirements

- Python 3.12+
- Network access to the production PLC and camera for live hardware operation

## Setup

### Windows (PowerShell)

```powershell
git clone <repo-url>
cd dune_winder
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

### Linux/macOS (bash/zsh)

```bash
git clone <repo-url>
cd dune_winder
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Optional spreadsheet tooling:

```bash
python -m pip install -e ".[spreadsheets]"
```

The base install already includes the runtime PLC and serial dependencies used by
the main application.

## Run The Application

### Windows (PowerShell)

From the project root:

```powershell
python -m dune_winder
```

The installed entrypoint also works:

```powershell
dune-winder
```

Example with runtime flags:

```powershell
python -m dune_winder START=TRUE LOG=TRUE LOG_IO=FALSE PLC_MODE=SIM
```

### Linux/macOS (bash/zsh)

From the project root:

```bash
python -m dune_winder
```

The installed entrypoint also works:

```bash
dune-winder
```

### Runtime flags

The main process supports command-line flags in `KEY=VALUE` form:

- `START=TRUE|FALSE`: auto-start the current APA after launch.
- `LOG=TRUE|FALSE`: echo runtime log messages to stdout.
- `LOG_IO=TRUE|FALSE`: log low-level I/O activity (very verbose).
- `PLC_MODE=REAL|SIM`: override PLC backend mode for this launch.

Example:

```bash
python -m dune_winder START=TRUE LOG=TRUE LOG_IO=FALSE PLC_MODE=SIM
```

Runtime default PLC mode is configured in `configuration.toml` with:

```toml
plcMode = "REAL" # or "SIM"
```

## Development

### Run tests

Windows (PowerShell):

```powershell
python -m unittest discover -s tests
```

Linux/macOS (bash/zsh):

```bash
python -m unittest discover -s tests
```

### Format and lint

Windows (PowerShell):

```powershell
python -m ruff format .
python -m ruff check .
```

Linux/macOS (bash/zsh):

```bash
python -m ruff format .
python -m ruff check .
```

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

For architecture follow-up and remaining high-priority refactors, see:

- [`docs/ArchitecturePriorityBacklog.md`](docs/ArchitecturePriorityBacklog.md)
- [`docs/PlcWinderCommunication.md`](docs/PlcWinderCommunication.md)
- [`docs/PlcWinderArchitectureProposals.md`](docs/PlcWinderArchitectureProposals.md)
- [`docs/WaypointPathPlanning.md`](docs/WaypointPathPlanning.md)

## Template G-Code Generation

### V-layer CLI generator

Write a recipe file with the standard header/hash:

```bash
python -m dune_winder.recipes.v_template_gcode gc_files/V-layer.gc --recipe
```

Apply special input overrides:

```bash
python -m dune_winder.recipes.v_template_gcode gc_files/V-layer.gc --recipe --special transferPause=true --special head_a_offset=7
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

Primary references:

- [`docs/WaypointPathPlanning.md`](docs/WaypointPathPlanning.md)
- [`docs/CircleLineQueue.md`](docs/CircleLineQueue.md)

CLI/GUI test tooling lives in:

- `src/motionQueueTest.py`
- `src/motionQueueTest_gui.py`

Example waypoint-planning invocation:

```bash
python src/motionQueueTest.py --pattern waypoint_path --waypoints "1000,200;2000,900;3500,1400;5000,500" --waypoint-order shortest --visualize-only
```

The web/API layer also exposes queued-motion preview commands:

- `process.get_queued_motion_preview`
- `process.continue_queued_motion_preview`
- `process.cancel_queued_motion_preview`

## PLC/Winder Communication

The PLC link in this repository has two main paths:

- Direct motion/state control: Python writes intent tags such as
  `MOVE_TYPE`, `X_POSITION`, `Y_POSITION`, `Z_POSITION`, and speed/accel tags.
  The PLC state routines in `plc/` validate interlocks, issue the Rockwell
  motion instructions, and report completion through `STATE`, `ERROR_CODE`, and
  axis status tags.
- Queued motion: Python serializes `MotionSeg` UDT payloads into `IncomingSeg`
  and drives the queue handshake tags (`IncomingSegReqID`, `IncomingSegAck`,
  `StartQueuedPath`, `AbortQueue`, `QueueCount`, `CurIssued`, `NextIssued`,
  and related fault tags). The checked-in standalone ladder counterpart is
  `plc/motionQueue/main/pasteable.rll`.

The runtime uses `pycomm3` in `REAL` mode and an in-memory `SimulatedPLC` in
`SIM` mode. Most reads come from the shared `PLC.Tag` polling cache in the
control loop; a few safety-sensitive checks use immediate reads instead.

Primary references:

- [`docs/PlcWinderCommunication.md`](docs/PlcWinderCommunication.md)
- [`docs/PlcWinderArchitectureProposals.md`](docs/PlcWinderArchitectureProposals.md)
- [`docs/PlcLadderWorkflow.md`](docs/PlcLadderWorkflow.md)

## Python To Ladder Logic Transpiler

The repository includes a small Python-to-Rockwell Ladder Logic transpiler for
selected motion-planning functions under `src/dune_winder/transpiler/`.

Studio 5000 copy/paste uses two different text formats in this workflow:
copied routine text is stored as `.rllscrap`, while pasteable ladder logic is
stored as `.rll`. Checked-in PLC artifacts live under `plc/` at the repo root.
The tree mixes exported metadata and manually maintained routine text:

- `plc/controller_level_tags.json`
- `plc/<program>/programTags.json`
- `plc/<program>/main/studio_copy.rllscrap`
- `plc/<program>/main/pasteable.rll`
- `plc/<program>/<subroutine>/studio_copy.rllscrap`
- `plc/<program>/<subroutine>/pasteable.rll`

Routine folders use these canonical files when available:

- `studio_copy.rllscrap`
- `pasteable.rll`

Some PLC programs also include supporting exported metadata in `programTags.json`
and the repository root includes controller-wide metadata in
`plc/controller_level_tags.json`. See
[`docs/PlcLadderWorkflow.md`](docs/PlcLadderWorkflow.md)
for the Studio 5000 workflow and storage conventions.

To scaffold a separate live-PLC metadata tree, use:

```bash
python3 src/export_plc_metadata.py 192.168.1.10
```

That command connects with `pycomm3`, writes controller/program tag metadata to
`plc/`, and creates empty `studio_copy.rllscrap` placeholders for each
discovered program entry point and subroutine. Users still need to copy actual
rung text from Studio 5000 into those `.rllscrap` files manually.

CLI usage:

```bash
python -m dune_winder.transpiler src/dune_winder/queued_motion/segment_patterns.py cap_segments_speed_by_axis_velocity
```

Python API usage:

```python
from dune_winder.transpiler import transpile

source = open("src/dune_winder/queued_motion/segment_patterns.py", encoding="utf-8").read()
ld_text = transpile(source, function_names=["cap_segments_speed_by_axis_velocity"])
print(ld_text)
```

## Haskell Utilities

The repository also includes a separate Cabal package, `dune-winder-hs`, under
`haskell/`. These tools are not required to run the main Python application;
they exist to support PLC ladder-logic generation and Studio 5000 text
transforms.

Build from the repo root with:

```bash
cabal build
```

### Executables

#### `plc-transpiler-hs`

`plc-transpiler-hs` reads one or more Python source files, parses a restricted
subset of Python, and emits Rockwell ladder-like text for selected functions.
If you pass function names after the source files, only those functions are
emitted.

```bash
cabal run plc-transpiler-hs -- src/dune_winder/queued_motion/segment_patterns.py cap_segments_speed_by_axis_velocity
```

With no function filter, the transpiler emits the supported routines it finds in
its built-in order:

- `_max_abs_sin_over_sweep` -> `MaxAbsSinSweep`
- `_max_abs_cos_over_sweep` -> `MaxAbsCosSweep`
- `arc_sweep_rad` -> `ArcSweepRad`
- `circle_center_for_segment` -> `CircleCenterForSeg`
- `_segment_tangent_component_bounds` -> `SegTangentBounds`
- `cap_segments_speed_by_axis_velocity` -> `CapSegSpeed`

Internally, the transpiler pipeline is split into these modules:

- `haskell/src/DuneWinder/Transpiler/Syntax.hs`: parses a constrained Python
  subset into an AST. Supported constructs include module-level numeric
  constants, function definitions, assignments, `if`/`else`, `for` loops over
  `range(...)` and `enumerate(...)`, arithmetic, comparisons, tuples/lists, and
  a small set of calls.
- `haskell/src/DuneWinder/Transpiler/Lower.hs`: lowers the parsed AST into a
  PLC-oriented IR, allocates registers, maps supported builtins (`math.sin`,
  `math.cos`, `math.sqrt`, `math.atan2`, `min`, `max`, `math.ceil`, and
  similar), and turns known function calls into `JSR`-style routine calls.
- `haskell/src/DuneWinder/Transpiler/Emit.hs`: renders the IR into ladder text,
  including `MOV`, `CPT`, `XIC`/`XIO`, `JSR`, loop labels, and special-case
  emission for operations such as `ATAN2`, `MIN`, `MAX`, `CEIL`, and `TRUNC`.
- `haskell/src/DuneWinder/Transpiler/Builtins.hs`: defines the builtin function
  and segment-field mappings used during lowering.
- `haskell/src/DuneWinder/Transpiler/IR.hs`,
  `haskell/src/DuneWinder/Transpiler/Types.hs`, and
  `haskell/src/DuneWinder/Transpiler/RegisterAllocator.hs`: define the
  intermediate representation, PLC/register types, and sequential register
  allocation used by the generated routines.
- `haskell/app/TranspileMain.hs`: CLI wrapper that concatenates `.py` inputs,
  applies an optional function filter, and prints the generated text to stdout.

#### `plc-rung-transform-hs`

`plc-rung-transform-hs` is a stdin-to-stdout text transformer for Studio 5000
ladder snippets:

```bash
cabal run plc-rung-transform-hs -- < input.rllscrap > output.rll
```

Its implementation lives in `haskell/src/PlcRungTransform.hs`. That module
rewrites bracketed conditions into `BST`/`NXB`/`BND` form, preserves nested
`CPT(...)` expressions while splitting top-level arguments, quotes command
arguments that contain spaces, flattens delimiter layout, and normalizes the
result into paste-friendly ladder text.

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
