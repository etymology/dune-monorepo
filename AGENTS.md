# AGENTS.md

## Developer Commands

Always use `uv run` — never invoke `python` or `python3` directly. The environment is managed by uv.

```bash
uv sync          # Install all dependencies (creates root .venv)
make test       # Run all tests (pytest)
make lint       # ruff check src tests
make format     # ruff format src tests
```

## Running Applications

```bash
uv run dune-winder       # APA winder control software
uv run dune-tension-gui # Wire tension GUI
```

## Test by Package

```bash
uv run pytest tests/dune_tension    # Tension package only
uv run pytest tests/dune_winder    # Winder package only
```

## Monorepo Structure

- Root `pyproject.toml` manages both packages: `dune_winder`, `dune_tension`
- Source under `src/`: `dune_winder/`, `dune_tension/`, `spectrum_analysis/`
- Tests under `tests/`: `dune_tension/`, `dune_winder/`
- Data artifacts stay in package subdirs (not Python packages): `dune_winder/plc/`, `dune_tension/data/`

## Dependencies

- Uses `uv` (not pip/poetry/pdm)
- Python >=3.12 (managed by uv)
- Lock file: `uv.lock` (canonical, commit this)
- Works on Windows and Unix/macOS

## Conventions

- Ruff lint ignores: F401, F811, F841, E741
- CI runs both unittest (dune_winder) and pytest (dune_tension)
- See subpackage READMEs for package-specific run flags and environment variables.