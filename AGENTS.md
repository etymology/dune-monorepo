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

## Pre-commit hook (ruff + markdownlint-cli2)

A pre-commit script lives at `scripts/pre-commit`. It runs automatically on staged files before every commit. **Install it once in a fresh clone:**

```bash
cp scripts/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

What it does:

- **Python (`.py`)** — `uv run ruff format` then `uv run ruff check --fix`, re-stages modified files.
- **Markdown (`.md`)** — `markdownlint-cli2 --fix`, re-stages modified files.

The hook is idempotent — each section skips silently if no matching files are staged.

## Markdown files

Always format `.md` files with `markdownlint-cli2` (installed globally via `npm install markdownlint-cli2 --global`):

```bash
markdownlint-cli2 "**/*.md"          # lint entire repo
markdownlint-cli2 --fix "**/*.md"    # auto-fix where possible
```

The pre-commit hook runs this automatically on staged `.md` files, so manual runs are only needed for bulk reformatting.

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
- **Once a task is complete, group all related changes into a final commit** using the format below.

### Conventional Commits

Format: `<type>(<scope>): <subject>` — scope is optional.

```text
feat: add hat wobble
^--^  ^------------^
|     |
|     +-> Summary in present tense.
|
+-------> Type: chore, docs, feat, fix, refactor, style, or test.
```

| Type         | Use for                                                      |
| ------------ | ------------------------------------------------------------ |
| `feat`       | New feature for the user (not a build-script feature)        |
| `fix`        | Bug fix for the user (not a build-script fix)                |
| `docs`       | Documentation changes only                                   |
| `style`      | Formatting, missing semicolons, etc. — no production change  |
| `refactor`   | Refactoring production code (e.g. renaming a variable)       |
| `test`       | Adding or refactoring tests — no production code change      |
| `chore`      | Tooling, deps, CI — no production code change                |

Examples:

```text
feat(tension): add real-time tension feedback loop
fix: correct off-by-one in winder segment counter
refactor(transpiler): rename internal helper to snake_case
chore: update uv.lock after dependency bump
```
