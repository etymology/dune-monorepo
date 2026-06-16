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

## Type checking

Run `uv run ty check` before considering a task complete. Report failures with `file:line` and error code.

## Pre-commit hook

Lives at `scripts/pre-commit`. Install once per clone:

```bash
cp scripts/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

Runs on staged files: ruff format + check --fix + ty check (Python); markdownlint-cli2 --fix (Markdown). Re-stages auto-fixed files. Idempotent — sections skip if no matching files staged.

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
- Data (not packages): `winder/plc/`, `tension/data/`
- Lockfile (commit): `uv.lock`
- Python ≥ 3.12

```bash
uv run pytest tests/dune_tension
uv run pytest tests/dune_winder
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

## PLC code (`winder/plc/`)

Studio 5000 ControlLogix program for the winder. The `.ACD` project file is the source of truth; everything under `winder/plc/` is **generated** from it by `uv run plc-acd-export`. Never hand-edit generated files.

Agents program the PLC through the `.rung` cycle (see `plans/llm-friendly-ladder-language-to-l5x.md`):

1. Human saves the ACD in Studio 5000 and runs `uv run plc-acd-export` — regenerates the tree, including a readable `<routine>.rung` per routine.
2. Agent reads and edits the `.rung` source (language reference: `winder/plc/RUNG_FORMAT.md`). New tags are declared with `local <type> <name>` lines — the compiler enforces that every referenced tag is `uses` (existing) or `local` (new).
3. `uv run rung-compile <file.rung>` validates the source, prints an equivalence report against the current export, and writes `<routine>_import.L5X` (donor context shell + synthesized tags + new rungs).
4. Human imports it in Studio (right-click routine → Import Routine…), reviews the Import Configuration dialog (new tags appear there for creation), saves the ACD.
5. Re-run `uv run plc-acd-export`; an **empty `git diff` on the `.rung` file confirms the change landed**.

The old `pasteable.rll` copy/paste loop is retired: pasting cannot create tags and is not a Studio-recognized modification path. `pasteable.rll`, `manifest.json`, and `studio_copy.rllscrap` are no longer generated or checked in — the `<routine>_Routine_RLL.L5X` is the single source of truth for rung text, and the ladder simulator derives its paste-dialect text from that L5X in memory.

### Tooling

| Command                          | What it does                                                                                      |
| -------------------------------- | -------------------------------------------------------------------------------------------------- |
| `uv run plc-acd-export`          | Regenerate all of `winder/plc/` from the ACD + live tag values (`--offline` to skip the PLC read). |
| `uv run rung-compile <f.rung>`   | Check + compile an edited `.rung` → routine import L5X + equivalence report. `--check-only` to validate. |
| `uv run rung-render <prog>/<rt>` | Re-render one `.rung` from its exported L5X (`--all` for the tree). Mostly for development; the export runs it automatically. |
| `uv run plc-import`              | Live tag metadata + values fetch only (pycomm3, IP `192.168.140.13`).                              |

### Agent rules

1. **Edit `.rung` files only.** `*_Routine_RLL.L5X` and the tag JSONs are export artifacts; `ACD/donors/*.L5X` are Studio's own routine exports (context shells for the compiler) — never modify any of them.
2. **Declare every new tag** with `local <type> <name>` (types: `bool int dint real motion timer counter`; timers take `preset <N>ms`). `rung-compile` errors on unresolved tags instead of letting the Studio import fail.
3. **Run `uv run rung-compile --check-only`** on the edited source before handing the L5X to the human; include the equivalence report in your summary so the rung-level change is reviewable.
4. **Never compile a routine whose `.rung` carries `# PENDING EDIT in Studio` markers** — the human finalizes or discards pending Studio edits first (the compiler refuses anyway).
5. The change isn't real until the human imports the L5X, saves the ACD, re-exports, and the `.rung` diff comes back empty.

### References

- `.rung` language reference: `winder/plc/RUNG_FORMAT.md`
- Instruction reference: `winder/plc/instruction_set.md`
- Legacy text-format guide (paren-dialect rung syntax, as stored in the L5X CDATA): `winder/plc/RLL_FORMAT.md`

### Artifact layout

```text
winder/plc/
├── ACD/
│   ├── DUNEW2PLC1_py3.ACD              ← SOURCE OF TRUTH (Studio 5000)
│   └── donors/<program>/<routine>_Routine_RLL.L5X   ← Studio routine exports (context shells)
├── acd_index.json                      ← provenance of the last export (ACD sha256, file hashes)
├── controller_level_tags.json          ← controller-scope tags + live values
├── instruction_set.md
├── RUNG_FORMAT.md / RLL_FORMAT.md
└── <program>/
    ├── programTags.json                ← program-scope tags + live values
    ├── <routine>_Routine_RLL.L5X       ← per-routine export snapshot; SOURCE OF TRUTH for rung text
    └── <routine-dir>/
        ├── <routine>.rung              ← readable projection; WHAT AGENTS EDIT
        └── <routine>_import.L5X        ← rung-compile output (not checked in)
```
