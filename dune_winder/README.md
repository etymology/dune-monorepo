# DUNE Winder (UChicago)

Python 3 control software and web UI for the UChicago APA winder.

## What This Repository Contains

- Runtime control process, state machine logic, and hardware I/O integration.
- Desktop/mobile web UI served from `web/`.
- Programmatic G-code generation for V/X/G templates.
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

## Run The Application

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

Example:

```bash
python -m dune_winder START=TRUE LOG=TRUE LOG_IO=FALSE
```

## Development

### Run tests

```bash
python -m unittest discover -s tests
```

### Format and lint

```bash
python -m ruff format .
python -m ruff check .
```

## Remote Command API v2

The web server now exposes typed JSON command endpoints in addition to the
legacy expression-based XML interface:

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

For architecture follow-up and remaining high-priority refactors, see:

- [`docs/ArchitecturePriorityBacklog.md`](docs/ArchitecturePriorityBacklog.md)

## Template G-Code Generation

### V-layer CLI generator

Write a recipe file with the standard header/hash:

```bash
python -m dune_winder.library.VTemplateGCode gc_files/V-layer.gc --recipe
```

Apply special input overrides:

```bash
python -m dune_winder.library.VTemplateGCode gc_files/V-layer.gc --recipe --special transferPause=true --special head_a_offset=7
```

### X/G-layer generator (Python API)

```python
from dune_winder.library.XGTemplateGCode import write_xg_template_file

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

## Key Paths

- Configuration: `configuration.xml`
- Machine calibration: `config/`
- Generated recipes: `gc_files/`
- Runtime logs/cache: `cache/`
- Web UI assets: `web/`

## Contact

[oye@uchicago.edu](mailto:oye@uchicago.edu)
