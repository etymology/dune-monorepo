# dune-monorepo

Canonical monorepo workflow for:

- `dune_winder`: the UChicago APA winder control software and web UI
- `dune_tension`: the wire-tension GUI and spectrum-analysis tooling

The monorepo root is the supported developer entrypoint for setup, run, test, and debug.
The supported lock state is the root [`uv.lock`](uv.lock) plus
[`rust/Cargo.lock`](rust/Cargo.lock) for the Rust workspace.

## Requirements

- [uv](https://docs.astral.sh/uv/)
- Python `>=3.12` (managed automatically by `uv`)
- Rust toolchain `>=1.83` with `cargo`, `rustfmt`, and `clippy`
- Node.js `>=18` and npm for Markdown tooling

## Quick Start

Install Python dependencies for both workspace packages, local PyO3 extension
modules, and shared developer tools:

```bash
uv sync
npm install
```

This creates the shared root `.venv`, installs both Python workspace members
with repo-wide dev tooling, builds the local Rust-backed Python modules declared
in `tool.uv.sources`, and installs the Node-based Markdown tools.

Use an explicit maturin rebuild when iterating on the audio extension or feature
flags:

```bash
uv run maturin develop --manifest-path rust/crates/dune-python/Cargo.toml
```

Run the main applications from the monorepo root:

```bash
uv run dune-winder
uv run dune-tension-gui
```

Run all Python tests from root:

```bash
uv run pytest
```

Run the full mixed-language suite with the Makefile shorthand:

```bash
make test
```

Other useful commands:

```bash
uv run pytest tests/dune_tension    # tension tests only
uv run pytest tests/dune_winder     # winder tests only
uv run pytest tests/dune_geometry   # Python surface tests for dune_geometry
uv run pytest tests/dune_plc_bus    # Python surface tests for dune_plc_bus
uv run ruff check src tests         # lint
uv run ruff format src tests        # format
uv run ty check                     # Python static type check
uv run maturin develop --manifest-path rust/crates/dune-python/Cargo.toml
cargo test --workspace --manifest-path rust/Cargo.toml
cargo clippy --workspace --manifest-path rust/Cargo.toml --all-targets
cargo fmt --manifest-path rust/Cargo.toml --all
npm run markdown:lint -- README.md AGENTS.md dune_tension/README.md rust/README.md
make test                           # shorthand via Makefile
```

## VS Code

Open `/home/dune/dune-monorepo` as the workspace folder. The root `.vscode/`
configuration is set up to use the monorepo `.venv` and launch both apps from
the root workflow.

## Layout

All Python source lives under [`src/`](src/): `dune_winder`, `dune_tension`, `spectrum_analysis`.

Rust source lives under [`rust/`](rust/). The root [`rust/Cargo.lock`](rust/Cargo.lock)
is the canonical Rust lockfile. Several Rust crates are also installed into the
Python environment through local `uv` path dependencies:

- `dune-rust-audio` provides `dune_tension._rust_audio`
- `dune-tension-core` provides `dune_tension_core`
- `dune-geometry` provides `dune_geometry`
- `dune-plc-bus` provides `dune_plc_bus`

Use Cargo for Rust-only tests and linting; use `uv run pytest` for Python tests
that import those extension modules.

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
