# AGENTS.md

This file is the single source of truth for all agent and AI-assistant behaviour in this monorepo. Sub-package directories do not carry their own AGENTS.md or CLAUDE.md; all policy lives here.

---

## Python tooling — always use `uv`

This project uses [uv](https://docs.astral.sh/uv/) for dependency and environment management.

**Never** invoke `python`, `python3`, `pip`, or `python -m venv` directly. Always prefix with `uv run` or use `uv` itself:

```bash
uv sync                          # Install / sync all dependencies (creates root .venv)
uv run python <script.py>        # Run an arbitrary Python file
uv run python -m <module>        # Run a module
uv run pytest                    # Run tests (do NOT call pytest directly)
uv run ruff check src tests      # Lint
uv run ruff format src tests     # Format
uv run dune-winder               # APA winder control software
uv run dune-tension-gui          # Wire tension GUI
```

Or use the make shorthands:

```bash
make test     # uv run pytest
make lint     # uv run ruff check src tests
make format   # uv run ruff format src tests
```

---

## Pre-commit hook (ruff format + fix)

A pre-commit script lives at `scripts/pre-commit`. It runs `ruff format` and `ruff check --fix` on every staged Python file and re-stages the result. **Install it before your first commit in a fresh clone:**

```bash
cp scripts/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

The hook is idempotent — if no Python files are staged it exits immediately.

---

## Monorepo structure

- Root `pyproject.toml` manages both packages: `dune_winder`, `dune_tension`
- Source: `src/dune_winder/`, `src/dune_tension/`, `src/spectrum_analysis/`
- Tests: `tests/dune_tension/`, `tests/dune_winder/`
- Data artifacts (not Python packages): `dune_winder/plc/`, `dune_tension/data/`
- Lock file: `uv.lock` (canonical — always commit this)
- Python ≥ 3.12 (managed by uv); works on Windows and Unix/macOS

### Test by package

```bash
uv run pytest tests/dune_tension    # tension package only
uv run pytest tests/dune_winder     # winder package only
```

---

## Commit policy

- Group edits into small, logically coherent commits.
- Do not mix refactors, bug fixes, and formatting in the same commit.
- After each logical unit is complete and validated, stage only the relevant files.
- Prefer multiple atomic commits over one large commit; each commit corresponds to one described change.
- Separate behaviour changes, refactors, dependency updates, and tests.
- Before each commit, show the files included and a one-line rationale.
- If the requested task spans multiple concerns, propose the commit boundaries before committing.
- Never commit unrelated formatting changes with functional edits.

### Conventional Commits

Use these prefixes:

| Prefix     | Use for                                    |
| ---------- | ------------------------------------------ |
| `feat:` | New features |
| `fix:` | Bug fixes |
| `refactor:` | Code restructuring without behaviour change |
| `test:` | Test-only changes |
| `docs:` | Documentation only |
| `chore:` | Tooling, deps, CI |

---

## Ruff conventions

- Lint ignores in `pyproject.toml`: F401, F811, F841, E741
- CI runs both unittest (dune_winder) and pytest (dune_tension)

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

### Haskell transpiler (`plc-transpiler-hs`)

- Source: `haskell/`
- Build: `cabal build` (requires GHC / Cabal — separate from uv)
- CLI: `cabal run plc-transpiler-hs -- <file.py> [function_name ...]`
- Covers the canonical motion-queue subroutines (`CapSegSpeed`, `ArcSweepRad`, etc.)

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
