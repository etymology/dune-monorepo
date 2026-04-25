# dune-monorepo

Canonical monorepo workflow for:

- `dune_winder`: the UChicago APA winder control software and web UI
- `dune_tension`: the wire-tension GUI and spectrum-analysis tooling

The monorepo root is the supported developer entrypoint for setup, run, test, and debug.
The only supported lock state is the root [`uv.lock`](uv.lock).

## Requirements

- [uv](https://docs.astral.sh/uv/)
- Python `>=3.12` (managed automatically by `uv`)

## Quick Start

Install dependencies for both workspace packages plus shared developer tools:

```bash
uv sync
```

This creates the shared root `.venv` and installs both workspace members with
the repo-wide dev tooling.

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
make test                           # shorthand via Makefile
```

## VS Code

Open `/home/dune/dune-monorepo` as the workspace folder. The root `.vscode/`
configuration is set up to use the monorepo `.venv` and launch both apps from
the root workflow.

## Layout

All Python source lives under [`src/`](src/): `dune_winder`, `dune_tension`, `spectrum_analysis`.

Data artifacts stay in their own subdirectories and are **not** Python packages:

- `dune_winder/` — PLC ladder programs, machine config, web UI, Grafana/InfluxDB
- `dune_tension/` — measurement DB, tension summaries, plots, streaming runs, audio fixtures

Tests live under [`tests/`](tests/): `dune_tension/` and `dune_winder/`.

Docs live under [`docs/`](docs/): `dune_tension/` and `dune_winder/`.

Package-specific operational details:

- [dune_winder/README.md](dune_winder/README.md)
- [dune_tension/README.md](dune_tension/README.md)

---

## Grafana / InfluxDB monitoring (dune_winder)

The winder pushes PLC tag data to InfluxDB at ~10 Hz; Grafana visualises it in real time. Both run as Docker containers.

```bash
docker compose up -d          # start Grafana + InfluxDB
```

- Grafana: `http://localhost:3000` — login `admin` / `dune_winder`
- InfluxDB: `http://localhost:8086` — org `dune`, bucket `winder`
- Config: `docker-compose.yml` and `grafana/` / `influxdb/` provisioning dirs at repo root

---

## RLL codegen — Python → Rockwell Ladder Logic (dune_winder)

### Python transpiler

- Source: `src/dune_winder/transpiler/`
- CLI: `uv run python -m dune_winder.transpiler <file.py> [function_name ...]`
- Output: pasteable ladder text → check in under `plc/<program>/<subroutine>/pasteable.rll`

### RLL rung transform (`plc-rung-transform-hs`)

Converts Studio 5000 copy-paste `.rllscrap` → pasteable `.rll` format.

```bash
cabal run plc-rung-transform-hs -- < input.rllscrap > output.rll
uv run plc-rung-transform                                          # Python equivalent
```

### PLC artifact layout

```text
plc/<program>/programTags.json
plc/<program>/main/studio_copy.rllscrap   ← copied from Studio 5000 (source of truth)
plc/<program>/main/pasteable.rll          ← transformed / transpiled output
plc/<program>/<subroutine>/pasteable.rll
```

Never hand-edit `studio_copy.rllscrap`; it is the source of truth from Studio 5000.
