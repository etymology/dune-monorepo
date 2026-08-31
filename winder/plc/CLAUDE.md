# PLC code (`winder/plc/`)

Studio 5000 ControlLogix program for the winder. The `.ACD` project file is the source of truth; everything under `winder/plc/` is **generated** from it by `uv run plc-acd-export`. Never hand-edit generated files.

Agents program the PLC through the `.rung` cycle (see `plans/llm-friendly-ladder-language-to-l5x.md`):

1. Human saves the ACD in Studio 5000 and runs `uv run plc-acd-export` — regenerates the tree, including a readable `<routine>.rung` per routine.
2. Agent reads and edits the `.rung` source (language reference: `winder/plc/RUNG_FORMAT.md`). New tags are declared with `local <type> <name>` lines — the compiler enforces that every referenced tag is `uses` (existing) or `local` (new).
3. `uv run rung-compile <file.rung>` validates the source, prints an equivalence report against the current export, and writes `<routine>_import.L5X` (donor context shell + synthesized tags + new rungs).
4. Human imports it in Studio (right-click routine → Import Routine…), reviews the Import Configuration dialog (new tags appear there for creation), saves the ACD.
5. Re-run `uv run plc-acd-export`; an **empty `git diff` on the `.rung` file confirms the change landed**.

The old `pasteable.rll` copy/paste loop is retired: pasting cannot create tags and is not a Studio-recognized modification path. `pasteable.rll`, `manifest.json`, and `studio_copy.rllscrap` are no longer generated or checked in — the `<routine>_Routine_RLL.L5X` is the single source of truth for rung text, and the ladder simulator derives its paste-dialect text from that L5X in memory.

## Tooling

| Command                          | What it does                                                                                      |
| -------------------------------- | -------------------------------------------------------------------------------------------------- |
| `uv run plc-acd-export`          | Regenerate all of `winder/plc/` from the ACD + live tag values (`--offline` to skip the PLC read). |
| `uv run rung-compile <f.rung>`   | Check + compile an edited `.rung` → routine import L5X + equivalence report. `--check-only` to validate. |
| `uv run rung-render <prog>/<rt>` | Re-render one `.rung` from its exported L5X (`--all` for the tree). Mostly for development; the export runs it automatically. |
| `uv run plc-import`              | Live tag metadata + values fetch only (pycomm3, IP `192.168.140.13`).                              |

## Agent rules

1. **Edit `.rung` files only.** `*_Routine_RLL.L5X` and the tag JSONs are export artifacts; `ACD/donors/*.L5X` are Studio's own routine exports (context shells for the compiler) — never modify any of them.
2. **Declare every new tag** with `local <type> <name>` (types: `bool int dint real motion timer counter`; timers take `preset <N>ms`). `rung-compile` errors on unresolved tags instead of letting the Studio import fail.
3. **Run `uv run rung-compile --check-only`** on the edited source before handing the L5X to the human; include the equivalence report in your summary so the rung-level change is reviewable.
4. **Never compile a routine whose `.rung` carries `# PENDING EDIT in Studio` markers** — the human finalizes or discards pending Studio edits first (the compiler refuses anyway).
5. The change isn't real until the human imports the L5X, saves the ACD, re-exports, and the `.rung` diff comes back empty.

## References

- `.rung` language reference: `winder/plc/RUNG_FORMAT.md`
- Instruction reference: `winder/plc/instruction_set.md`
- Legacy text-format guide (paren-dialect rung syntax, as stored in the L5X CDATA): `winder/plc/RLL_FORMAT.md`

## Artifact layout

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
