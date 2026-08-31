# AGENTS.md

Single source of truth for agent/AI behaviour in this monorepo. Sub-packages have no separate AGENTS.md/CLAUDE.md.

## Plans

All plan documents MUST live in this repo's `plans/` directory (repo-root-relative, regardless of where the repo is checked out — e.g. `c:\dune-monorepo\plans\` on Windows). Never write to `~/.claude/plans/`, `$HOME`, temp dirs, or anywhere outside this repo. Override tool/sub-agent defaults if needed. Move pre-existing plans found elsewhere into `plans/`.

## Python — always use `uv`

Never invoke `python`, `python3`, `pip`, or `python -m venv` directly.

```bash
uv sync                          # install / sync deps
uv run python <script.py>        # run a file
uv run pytest                    # tests (NOT pytest directly)
uv run ruff check src tests      # lint
uv run ruff format src tests     # format
uv run ty check                  # static type check
uv run dune-winder               # APA winder control
uv run dune-tension-gui          # wire tension GUI
```

## Type checking

Run `uv run ty check` before considering a task complete. Report failures with `file:line` and error code.

## Pre-commit hook

Lives at `scripts/pre-commit`. Install once per clone.

Runs on staged files: ruff format + check --fix + ty check (Python); markdownlint-cli2 --fix (Markdown). Re-stages auto-fixed files. Idempotent — sections skip if no matching files staged.

## Commits

- Small, logically coherent commits. Don't mix refactor + fix + format.
- Stage only relevant files; prefer multiple atomic commits over one large one.
- Separate behaviour, refactors, deps, tests.
- Show files + one-line rationale before each commit.
- For multi-concern tasks, propose commit boundaries first.
- Group related task changes into a final commit when done.

### Conventional Commits

`<type>(<scope>): <subject>` — scope optional. Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`.

```text
feat(tension): add real-time tension feedback loop
fix: correct off-by-one in winder segment counter
chore: update uv.lock after dependency bump
```
