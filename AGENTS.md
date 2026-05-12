# AGENTS.md

Single source of truth for agent/AI behaviour in this monorepo. Sub-packages have no separate AGENTS.md/CLAUDE.md.

## Plans

All plan documents MUST live in `/Users/ben/dune-monorepo/plans/`. Never write to `~/.claude/plans/`, `$HOME`, temp dirs, or anywhere outside this repo. Override tool/sub-agent defaults if needed. Move pre-existing plans found elsewhere into `plans/`.

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

Make shorthands: `make test`, `make test-python`, `make lint`, `make format`, `make typecheck`.

## Rust — root Cargo workspace

Manifest: `rust/Cargo.toml`. Lockfile: `rust/Cargo.lock` (commit on dep changes). Run from monorepo root with explicit manifest path:

```bash
cargo test --workspace --manifest-path rust/Cargo.toml
cargo clippy --workspace --manifest-path rust/Cargo.toml --all-targets
cargo fmt --manifest-path rust/Cargo.toml --all
uv run maturin develop --manifest-path rust/crates/dune-python/Cargo.toml
```

The PyO3 extension installs as `dune_tension._rust_audio`; build via `uv run maturin` so it lands in `.venv`.

## Type checking

Run `uv run ty check` before considering a task complete. Report failures with `file:line` and error code.

## Pre-commit hook

Lives at `scripts/pre-commit`. Install once per clone:

```bash
cp scripts/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

Runs on staged files: ruff format + check --fix + ty check (Python); cargo fmt + clippy --all-targets (Rust); markdownlint-cli2 --fix (Markdown). Re-stages auto-fixed files. Idempotent — sections skip if no matching files staged.

## Markdown

Format with project-local `markdownlint-cli2`:

```bash
npm install
npm run markdown:lint -- "**/*.md"
npm run markdown:fix  -- "**/*.md"
```

The pre-commit hook handles staged `.md` files automatically.

## Monorepo layout

- Packages: `dune_winder`, `dune_tension` (root `pyproject.toml`)
- Source: `src/dune_winder/`, `src/dune_tension/`, `src/spectrum_analysis/`
- Tests: `tests/dune_tension/`, `tests/dune_winder/`
- Data (not packages): `dune_winder/plc/`, `dune_tension/data/`
- Lockfiles (commit both): `uv.lock`, `rust/Cargo.lock`
- Python ≥ 3.12; Rust ≥ 1.83 for `_rust_audio`

```bash
uv run pytest tests/dune_tension
uv run pytest tests/dune_winder
cargo test --workspace --manifest-path rust/Cargo.toml
```

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

## PLC code (`dune_winder/plc/`)

Studio 5000 ControlLogix program for the winder. Two-format workflow forced by vendor:

- **`studio_copy.rllscrap`** — source of truth. Literal Ctrl+C output from Logix Designer. Check in *exactly* as emitted. Never hand-edit.
- **`pasteable.rll`** — paste target. Generated from `studio_copy.rllscrap` via the rung transform; format Logix Designer accepts back via Ctrl+V.

Propose new ladder logic in `pasteable.rll`. The human pastes into Studio, copies the result back, overwrites `studio_copy.rllscrap`, and reruns the conversion to confirm round-trip.

### Tooling

| Command                        | What it does                                                                                                       |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| `uv run plc-sync`              | Live PLC fetch (metadata + values via pycomm3) + regenerate every `pasteable.rll` + refresh `manifest.json`. IP `192.168.140.13`. |
| `uv run plc-sync --offline`    | No PLC connection. Regenerate `pasteable.rll` from every `studio_copy.rllscrap` + refresh manifest. **Use this in agent flows.** |
| `uv run plc-import`            | Metadata + values fetch only.                                                                                      |
| `uv run plc-convert-rllscrap`  | rllscrap → rll across the whole tree.                                                                              |
| `uv run plc-rung-transform`    | Convert a single `.rllscrap` (stdin or `--in-place`).                                                              |
| `uv run plc-manifest status`   | Show artifacts out of sync with checked-in hashes.                                                                 |

### Mandatory agent workflow

1. **Before editing ladder logic**, run `uv run plc-manifest status`. Any `modified` row → alert the user; the working copy may overwrite pending changes.
2. **After changing `studio_copy.rllscrap`**, run `uv run plc-sync --offline` before staging so you can inspect the regenerated `.rll` diff. (Pre-commit also runs it as a safety net.)
3. **When proposing changes to `pasteable.rll`**, use the change-proposal format below before writing any files. The change isn't real until the user pastes into Studio and round-trips a fresh `studio_copy.rllscrap` back.

### Change-proposal format (REQUIRED for `pasteable.rll` edits)

```text
PLC change proposal
-------------------

Routines to change:
- <program>/<routine>            (e.g. state_5_move_z/main)

Tags to add:
- <fully_qualified_name>         scope=<controller|program:NAME>
                                  type=<DINT|REAL|BOOL|TIMER|UDT name>
                                  initial=<value or n/a>
                                  reason=<one line>

Tags to modify:
- <fully_qualified_name>         change=<initial value | data type | dimensions>
                                  reason=<one line>

Rung diff per routine:
<unified diff of pasteable.rll for each routine listed above>

Paste instructions:
1. In Studio 5000, open <program>.<routine>.
2. Add/modify tags listed above at the indicated scope BEFORE pasting rungs.
3. Select the affected rungs and paste from <routine>/pasteable.rll.
4. Save, copy the routine back out, overwrite studio_copy.rllscrap.
5. Run `uv run plc-sync --offline` to verify round-trip.
```

Never hide a tag addition inside the rung diff — Studio 5000 rejects pastes referencing tags that don't exist at the right scope. List every new tag explicitly.

### References

- Instruction reference: `dune_winder/plc/instruction_set.md`
- File-format guide (rllscrap vs. rll, branches, formulas, quoting, joint programming protocol): `dune_winder/plc/RLL_FORMAT.md`

### Artifact layout

```text
dune_winder/plc/
├── controller_level_tags.json          ← controller-scope tags + live values
├── manifest.json                       ← hashes + timestamps
├── instruction_set.md
├── RLL_FORMAT.md
└── <program>/
    ├── programTags.json                ← program-scope tags + live values
    └── <routine>/
        ├── studio_copy.rllscrap        ← source of truth (paste from Studio)
        └── pasteable.rll               ← generated; paste back into Studio
```
