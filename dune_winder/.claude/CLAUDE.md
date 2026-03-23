# CLAUDE.md

## Commit policy

When making code changes:

- Group edits into small, logically coherent commits.
- Do not mix refactors, bug fixes, and formatting in the same commit.
- After each logical unit is complete and validated, stage only the relevant files.
- Create a git commit with a concise conventional-commit style message.
- If the requested task spans multiple concerns, split it into multiple commits and explain the proposed commit boundaries before committing.
- Prefer multiple atomic commits over one large commit.
- Each commit must correspond to one described change.
- Separate behavior changes, refactors, dependency updates, and tests.
- Before each commit, show the files included and a one-line rationale.
- Use Conventional Commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`
- Never commit unrelated formatting changes with functional edits.

## Python tooling (uv)

This project uses [uv](https://docs.astral.sh/uv/) for dependency and environment management.

- Install dependencies: `uv sync`
- Run the app: `uv run python -m dune_winder` or `uv run dune-winder`
- Run tests: `uv run python -m unittest discover -s tests`
- Lint/format: `uv run ruff check .` / `uv run ruff format .`
- Add a dependency: `uv add <package>` (updates both `pyproject.toml` and `uv.lock`)
- Do NOT use `pip install`, `python -m venv`, or bare `python` invocations — always prefix with `uv run`.

## Grafana / InfluxDB monitoring

The winder pushes PLC tag data to InfluxDB at ~10 Hz and Grafana visualises it in real time. Both run as Docker containers — no other install needed.

- Start: `docker compose up -d` (from repo root)
- Grafana: `http://localhost:3000` — login `admin` / `dune_winder`
- InfluxDB: `http://localhost:8086` — org `dune`, bucket `winder`
- Config lives in `docker-compose.yml` and `grafana/` / `influxdb/` provisioning dirs at the repo root.

## RLL codegen (Python → Rockwell Ladder Logic)

There are two transpiler paths for generating `.rll` (pasteable ladder text) from Python motion code.

### Python transpiler

- Source: `src/dune_winder/transpiler/`
- CLI: `uv run python -m dune_winder.transpiler <file.py> [function_name ...]`
- Output is pasteable ladder text; check it in under `plc/<program>/<subroutine>/pasteable.rll`.

### Haskell transpiler (`plc-transpiler-hs`)

- Source: `haskell/`
- Build: `cabal build` (requires GHC / Cabal — separate from uv)
- CLI: `cabal run plc-transpiler-hs -- <file.py> [function_name ...]`
- Covers the canonical motion-queue subroutines (`CapSegSpeed`, `ArcSweepRad`, etc.).

### RLL rung transform (`plc-rung-transform-hs`)

- Converts Studio 5000 copy-paste `.rllscrap` → pasteable `.rll` format.
- CLI: `cabal run plc-rung-transform-hs -- < input.rllscrap > output.rll`
- Python equivalent entrypoint: `uv run plc-rung-transform`

### PLC artifact layout

```text
plc/<program>/programTags.json
plc/<program>/main/studio_copy.rllscrap   ← copied from Studio 5000
plc/<program>/main/pasteable.rll          ← transformed / transpiled output
plc/<program>/<subroutine>/pasteable.rll
```

When regenerating a subroutine, update only the relevant `pasteable.rll`; never hand-edit `studio_copy.rllscrap` (it is the source of truth from Studio 5000).
