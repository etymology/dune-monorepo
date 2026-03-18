# DUNE Winder (UChicago)

Python 3 control software and web UI for the UChicago APA winder.

## What This Repository Contains

- Runtime control process, state machine logic, and hardware I/O integration.
- Desktop/mobile web UI served from `web/`.
- Programmatic G-code generation for U/V/X/G templates.
- Queued-motion planning, preview, and PLC queue execution utilities.
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

## Python To Ladder Logic Transpiler

The repository includes a small Python-to-Rockwell Ladder Logic transpiler for
selected motion-planning functions under `src/dune_winder/transpiler/`.

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
