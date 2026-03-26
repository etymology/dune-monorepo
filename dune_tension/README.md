# dune-tension

Wire-tension measurement tooling for DUNE APA work, including:
- A Tk GUI for guided measurements (`dune_tension`)
- Spectrum/pitch analysis CLIs (`spectrum_analysis`)
- PLC/servo/valve control integration
- Logging, summaries, plots, and M2M upload utilities

The supported setup and development workflow starts at the monorepo root.
See [../README.md](../README.md) for the canonical `uv sync`, run, test, and
debug commands. This README keeps package-specific operational detail only.

## Repository Layout
- `src/dune_tension/`: installable GUI/runtime package
- `src/dune_tension/ukapa7_comparison/`: UKAPA7-specific comparison and report-generation helpers
- `src/dune_tension/hardware/`: hardware-facing helpers such as the valve trigger
- `src/spectrum_analysis/`: installable spectrum/pitch analysis package
- `tools/`: ad hoc developer utilities not shipped as packages
- `experiments/`: exploratory scripts and datasets kept out of the install path

## Requirements
- Python `>=3.12`
- macOS/Linux with audio input support
- Optional hardware:
  - PLC reachable either directly via `pycomm3` or through `src/dune_tension/tension_server.py`
  - Pololu Micro Maestro servo controller
  - Supported valve trigger device

Project dependencies are declared in [pyproject.toml](pyproject.toml).

## Entry Points
After the root `uv sync`, the following console commands are available:

- `dune-tension-gui`
- `dune-tension-periodic-plots`
- `dune-spectrum-compare`
- `dune-spectrum-scroller`

## Quick Start

### 1. Choose a PLC transport mode

**Desktop mode (default, recommended):** dune_tension sends PLC commands
through the dune_winder HTTP API running on the PLC-connected desktop PC.
This is the default — no extra server process is needed beyond dune_winder
itself:

```bash
# On the desktop PC, dune_winder must be running (port 8080).
# From any machine that can reach the desktop:
dune-tension-gui
```

If the desktop PC is at a non-default address (e.g. over a mobile hotspot):
```bash
DESKTOP_SERVER_URL=http://192.168.137.1:8080 dune-tension-gui
```

**Direct mode:** For a machine with direct PLC access and no dune_winder
running:
```bash
PLC_IO_MODE=direct PLC_IP_ADDRESS=192.168.140.13 dune-tension-gui
```

**Server mode (legacy):** Uses a standalone Flask bridge
(`tension_server.py`). Desktop mode is preferred over this approach:
```bash
# On the PLC-connected machine:
PLC_IP_ADDRESS=192.168.140.13 SERVER_PORT=5000 python3 -m dune_tension.tension_server
# On the GUI machine:
PLC_IO_MODE=server TENSION_SERVER_URL=http://192.168.137.1:5000 dune-tension-gui
```

### 2. Launch the GUI
```bash
dune-tension-gui
```

The GUI lets you configure APA/layer/side, collect measurements, clear/re-measure ranges, and refresh summary outputs.

### 3. Generate summary outputs periodically (optional)
```bash
dune-tension-periodic-plots USAPA5 X --interval 900
```

## Hardware and Network Notes
- In `PLC_IO_MODE=server`, ensure the PLC server host is reachable from the GUI machine.
- In `PLC_IO_MODE=direct`, ensure the GUI machine can reach the PLC at `PLC_IP_ADDRESS`.
- Configure audio input device (historically "USB PnP" style device names).
- Servo controller reference: <https://www.pololu.com/product/1350/resources>

## PLC Environment Variables
Set these before launching the GUI or server as needed:

- `PLC_IO_MODE=desktop|direct|server` : transport mode (default: `desktop`)
- `DESKTOP_SERVER_URL=http://host:8080` : dune_winder API URL for desktop mode
- `TENSION_SERVER_URL=http://host:5000` : URL for legacy HTTP server mode
- `PLC_IP_ADDRESS=192.168.140.13` : PLC address for direct mode or the server process
- `PLC_COMM_RETRIES=2` : retry count for direct `pycomm3` communication
- `SERVER_PORT=5000` : Flask tension server port (legacy server mode)

## Spoof / Dry-Run Modes
Set environment variables before launching the GUI:

- `SPOOF_AUDIO=1` : use spoofed audio capture
- `SPOOF_PLC=1` : bypass real PLC movement
- `SPOOF_SERVO=1` : use dummy servo controller
- `SPOOF_VALVE=1` : disable real valve control

Example:
```bash
SPOOF_AUDIO=1 SPOOF_PLC=1 SPOOF_SERVO=1 SPOOF_VALVE=1 dune-tension-gui
```

## Data and Output Paths
Default runtime paths include:
- Measurement DB: `dune_tension/data/tension_data/tension_data.db`
- Summaries: `dune_tension/data/tension_summaries/`
- Plots: `dune_tension/data/tension_plots/`
- Missing/bad wires: `dune_tension/data/badwires/`

## Spectrum / Pitch Tools

### Compare pitch workflows
```bash
dune-spectrum-compare --config src/spectrum_analysis/pitch_compare_config.json
```

### Scrolling spectrogram viewer
```bash
dune-spectrum-scroller --demo
```

## M2M Upload Utilities
M2M helpers live in `src/dune_tension/m2m/`.

Example uploader script:
- [src/dune_tension/uploadTensions.py](src/dune_tension/uploadTensions.py)

## Development
Use the root README for setup, syncing, testing, linting, and editor workflow.
Package-local compile checks can still be run with:

```bash
python3 -m compileall src
```

## Troubleshooting
- If audio/GUI imports fail, verify system audio libs and `sounddevice` install.
- If PLC movement fails in server mode, confirm `TENSION_SERVER_URL` and that the tension server is running.
- If PLC movement fails in direct mode, confirm `PLC_IO_MODE=direct`, `PLC_IP_ADDRESS`, and that `pycomm3` is installed.
- If `uv` is not found after install, add `~/.local/bin` to your shell `PATH`.
