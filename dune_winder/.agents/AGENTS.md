# AGENTS.md

When making code changes:
- Group edits into small, logically coherent commits.
- Do not mix refactors, bug fixes, and formatting in the same commit.
- After each logical unit is complete and validated, stage only the relevant files.
- Create a git commit with a concise conventional-commit style message.
- If the requested task spans multiple concerns, split it into multiple commits and explain the proposed commit boundaries before committing.

# Development commands

Use `uv run` to execute tools managed by the project (pytest, ruff, etc.):

- **Run tests**: `uv run pytest` (do NOT use `pytest` directly as it's not on PATH)
- **Lint**: `uv run ruff check src tests`
- **Format**: `uv run ruff format src tests`

Or use make targets: `make test`, `make lint`, `make format`.

# Commit policy
- Prefer multiple atomic commits over one large commit.
- Each commit must correspond to one described change.
- Separate behavior changes, refactors, dependency updates, and tests.
- Before each commit, show the files included and a one-line rationale.
- Use Conventional Commits:
  - feat:
  - fix:
  - refactor:
  - test:
  - docs:
- Never commit unrelated formatting changes with functional edits.