# dune-monorepo

Canonical monorepo workflow for:

- `dune_winder`: the UChicago APA winder control software and web UI
- `dune_tension`: the wire-tension GUI and spectrum-analysis tooling

The monorepo root is the supported developer entrypoint for setup, run, test, and debug.
The only supported lock state is the root [`uv.lock`](uv.lock).

## Requirements

- [uv](https://docs.astral.sh/uv/)
- Python `>=3.12` (managed automatically by `uv`)
- Node.js `>=18` and npm for Markdown tooling

## Quick Start

Install Python dependencies for both workspace packages plus shared developer tools:

```bash
uv sync
npm install
```

This creates the shared root `.venv`, installs both Python workspace members
with the repo-wide dev tooling, and installs the Node-based Markdown tools.

Run the main applications from the monorepo root:

```bash
uv run dune-winder
uv run dune-tension-gui
```

Run all tests (both packages) from root:

```bash
uv run pytest
```

Other useful commands:

```bash
uv run pytest tests/dune_tension    # tension tests only
uv run pytest tests/dune_winder     # winder tests only
uv run ruff check src tests         # lint
uv run ruff format src tests        # format
uv run ty check                     # Python static type check
npm run markdown:lint -- README.md AGENTS.md tension/README.md
make test                           # shorthand via Makefile
```

## VS Code

Open `/home/dune/dune-monorepo` as the workspace folder. The root `.vscode/`
configuration is set up to use the monorepo `.venv` and launch both apps from
the root workflow.

## Layout

All Python source lives under [`src/`](src/): `dune_winder`, `dune_tension`, `spectrum_analysis`.

Data artifacts stay in their own subdirectories and are **not** Python packages:

- `winder/` — PLC ladder programs, machine config, web UI, Grafana/InfluxDB
- `tension/` — measurement DB, tension summaries, plots, streaming runs, audio fixtures

Tests live under [`tests/`](tests/): `dune_tension/` and `dune_winder/`.

Docs live under [`docs/`](docs/): `dune_tension/` and `dune_winder/`.

Package-specific operational details:

- [winder/README.md](winder/README.md)
- [tension/README.md](tension/README.md)

---

## Grafana / InfluxDB monitoring (dune_winder)

The winder pushes PLC tag data to InfluxDB at ~10 Hz; Grafana visualises it in real time. Both run as Docker containers.

```bash
docker compose -f winder/docker-compose.yml up -d   # start Grafana + InfluxDB
```

- Grafana: `http://localhost:3000` — login `admin` / `dune_winder`
- InfluxDB: `http://localhost:8086` — org `dune`, bucket `winder`
- Config: `winder/docker-compose.yml`; Grafana/InfluxDB provisioning under `config/`

---

## RLL codegen — Python → Rockwell Ladder Logic (dune_winder)

### Python transpiler

- Source: `src/dune_winder/transpiler/`
- CLI: `uv run python -m dune_winder.transpiler <file.py> [function_name ...]`
- Output: pasteable ladder text → check in under `plc/<program>/<subroutine>/pasteable.rll`

### RLL rung transform (`plc-rung-transform`)

Converts Studio 5000 copy-paste `.rllscrap` → pasteable `.rll` format.

```bash
uv run plc-rung-transform input.rllscrap -o output.rll
```

### PLC artifact layout

The whole `plc/` tree is regenerated from the Studio 5000 ACD by
`uv run plc-acd-export` (see `AGENTS.md`). The per-routine L5X is the single
source of truth for rung text; the `.rung` file is the readable projection
agents edit.

```text
plc/ACD/DUNEW2PLC1_py3.ACD                 ← SOURCE OF TRUTH (Studio 5000)
plc/<program>/programTags.json
plc/<program>/<routine>_Routine_RLL.L5X    ← source of truth for rung text
plc/<program>/<routine-dir>/<routine>.rung ← readable projection; WHAT YOU EDIT
```

Never hand-edit the L5X or tag JSONs; they are export artifacts. Edit `.rung`
files and round-trip with `uv run rung-compile`.
