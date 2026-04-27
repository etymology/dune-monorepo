# AGENTS.md

This file is the single source of truth for all agent and AI-assistant
behaviour in this monorepo. Sub-package directories do not carry their own
AGENTS.md or CLAUDE.md; all policy lives here.

---

## Python tooling — always use `uv`

This project uses [uv](https://docs.astral.sh/uv/) for dependency and
environment management.

**Never** invoke `python`, `python3`, `pip`, or `python -m venv` directly.
Always prefix with `uv run` or use `uv` itself:

```bash
uv sync                          # Install / sync dependencies
uv run python <script.py>        # Run an arbitrary Python file
uv run python -m <module>        # Run a module
uv run pytest                    # Run tests (do NOT call pytest directly)
uv run ruff check src tests      # Lint
uv run ruff format src tests     # Format
uv run ty check                  # Static type check all files
uv run dune-winder               # APA winder control software
uv run dune-tension-gui          # Wire tension GUI
```

Or use the make shorthands:

```bash
make test      # uv run pytest
make lint      # uv run ruff check src tests
make format    # uv run ruff format src tests
```

---

## Static type checking

Run ty on all files before considering a task complete:

```bash
uv run ty check
```

When ty reports failures, include the `file:line` location and error code in
your notes or review comments so the complaint is annotated where it occurs.

---

## Pre-commit hook (ruff + ty + markdownlint-cli2)

A pre-commit script lives at `scripts/pre-commit`. It runs automatically on
staged files before every commit. **Install it once in a fresh clone:**

```bash
cp scripts/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

What it does:

- **Python (`.py`)** — `uv run ruff format` then
  `uv run ruff check --fix`, re-stages modified files, then
  `uv run ty check`.
- **Markdown (`.md`)** — `markdownlint-cli2 --fix`, re-stages modified files.

The hook is idempotent — each section skips silently if no matching files are staged.

## Markdown files

Always format `.md` files with `markdownlint-cli2` (installed globally via
`npm install markdownlint-cli2 --global`):

```bash
markdownlint-cli2 "**/*.md"          # lint entire repo
markdownlint-cli2 --fix "**/*.md"    # auto-fix where possible
```

The pre-commit hook runs this automatically on staged `.md` files, so manual
runs are only needed for bulk reformatting.

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
- Prefer multiple atomic commits over one large commit; each commit corresponds
  to one described change.
- Separate behaviour changes, refactors, dependency updates, and tests.
- Before each commit, show the files included and a one-line rationale.
- If the requested task spans multiple concerns, propose the commit boundaries
  before committing.
- Never commit unrelated formatting changes with functional edits.
- **Once a task is complete, group all related changes into a final commit**
  using the format below.

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

---

## PLC code (`dune_winder/plc/`)

The `dune_winder/plc/` tree contains the program for the Studio 5000
ControlLogix PLC that drives the winder. Vendor restrictions force a
two-format workflow:

- **`studio_copy.rllscrap`** is the **source of truth**. It is the literal
  text Logix Designer copies to the clipboard when the user selects a
  routine and presses Ctrl+C. We check it in *exactly* as Studio emitted
  it. Never hand-edit this file.
- **`pasteable.rll`** is the **paste target**. It is the same routine in
  the slightly different format Logix Designer accepts back through
  Ctrl+V (paste) when the user clicks into a rung region. We *generate*
  this file from `studio_copy.rllscrap` with the rung transform.

When **proposing changes to PLC behaviour**, work in `pasteable.rll` —
that is the format you can express new ladder logic in directly. The
human collaborator then pastes the diff into Studio 5000, copies the
resulting routine back out, overwrites `studio_copy.rllscrap`, and lets
the conversion script regenerate `pasteable.rll` to confirm round-trip
equivalence.

### Tooling

| Command                        | What it does                                                                                                                                         |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `uv run plc-sync`              | Live PLC fetch (metadata + values via pycomm3) **and** regenerate every `pasteable.rll`, refresh `manifest.json`. Default IP `192.168.140.13`.       |
| `uv run plc-sync --offline`    | No PLC connection. Only regenerate `pasteable.rll` from every `studio_copy.rllscrap` and refresh `manifest.json`. **Use this in agent flows.**       |
| `uv run plc-import`            | Just the metadata + values fetch (no rllscrap conversion).                                                                                           |
| `uv run plc-convert-rllscrap`  | Just the rllscrap → rll conversion across the whole `plc/` tree.                                                                                     |
| `uv run plc-rung-transform`    | Convert a single `.rllscrap` file (stdin or `--in-place`).                                                                                           |
| `uv run plc-manifest status`   | Show which routines / tag JSON files are out of sync with their checked-in hashes.                                                                   |

### Mandatory agent workflow

1. **Before editing PLC ladder logic**, run `uv run plc-manifest status`.
   If any row is `modified`, alert the user before doing anything else —
   the working copy diverges from the last sync and you may overwrite
   pending changes.
2. **When you change `studio_copy.rllscrap`** (because the user pasted a
   new copy from Studio), you MUST run `uv run plc-sync --offline`
   before staging. The pre-commit hook also runs it as a safety net,
   but doing it yourself lets you inspect the regenerated `.rll` diff.
3. **When you propose changes to `pasteable.rll`** (because we are
   designing new ladder logic on the agent side), you MUST present the
   change using the change-proposal format below before writing any
   files. The user will paste the proposed snippet into Studio 5000
   manually; only after they paste the result back as a new
   `studio_copy.rllscrap` is the change real.

### Change-proposal format (REQUIRED for `pasteable.rll` edits)

When proposing PLC changes, your message MUST contain a section with
this exact shape so the human can execute the Studio 5000 paste
deterministically:

```text
PLC change proposal
-------------------

Routines to change:
- <program>/<routine>            (e.g. state_5_move_z/main)
- <program>/<routine>            (e.g. queued_motion/main)

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
3. Select the affected rungs and paste the new content from <routine>/pasteable.rll.
4. Save, then copy the routine back out and overwrite studio_copy.rllscrap.
5. Run `uv run plc-sync --offline` to verify round-trip.
```

Never hide a tag addition inside the rung diff — Studio 5000 will reject
the paste if a referenced tag does not exist at the right scope. List
every new tag explicitly with its scope.

### RLL syntax reference

- **Instruction reference**: `dune_winder/plc/instruction_set.md`
- **File-format guide** (rllscrap vs. rll, branches, formulas, quoting,
  joint programming protocol): `dune_winder/plc/RLL_FORMAT.md`

### `plc/` artifact layout

```text
dune_winder/plc/
├── controller_level_tags.json          ← controller-scope tag metadata + live values
├── manifest.json                       ← hashes + timestamps for every artifact
├── instruction_set.md                  ← instruction reference
├── RLL_FORMAT.md                       ← file-format guide
└── <program>/
    ├── programTags.json                ← program-scope tags + live values
    └── <routine>/
        ├── studio_copy.rllscrap        ← source of truth (manual paste from Studio)
        └── pasteable.rll               ← generated; what we paste back into Studio
```
