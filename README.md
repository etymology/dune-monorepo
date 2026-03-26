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

Useful root-level commands:

```bash
uv run python -m unittest discover -s dune_winder/tests
uv run pytest dune_tension/tests
uv run ruff check dune_winder dune_tension
```

## VS Code

Open `/home/dune/dune-monorepo` as the workspace folder. The root `.vscode/`
configuration is set up to use the monorepo `.venv` and launch both apps from
the root workflow.

## Package Notes

- `dune_winder` keeps its configuration, PLC assets, cache, and web files under
  `dune_winder/`.
- `dune_tension` keeps its measurement database, summaries, plots, streaming
  runs, and audio fixtures under `dune_tension/`.

Package-specific operational details remain in:

- [dune_winder/README.md](dune_winder/README.md)
- [dune_tension/README.md](dune_tension/README.md)
