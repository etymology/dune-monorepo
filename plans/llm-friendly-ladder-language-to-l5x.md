# LLM-friendly ladder language ↔ L5X

Status: proposed (rev 2 — reoriented around `plc-acd-export` and L5X routine import)
Author: Ben (with Claude)
Scope: `winder/plc/`, new package under `src/dune_winder/`

## Goal

Let a text-based coding agent program the ControlLogix PLC through this cycle:

1. Human saves the `.ACD` in Studio 5000.
2. `uv run plc-acd-export` regenerates `winder/plc/` from the ACD — including
   a **rendered `.rung` file per routine**, the LLM-readable form.
3. The LLM reads and edits `.rung` sources.
4. `uv run rung-compile` turns an edited `.rung` into a **routine L5X**
   (rungs + synthesized tag definitions injected into a fresh context shell).
5. Human imports the routine L5X via the Studio 5000 GUI, reviews the import
   dialog, and saves the ACD.
6. Step 2 runs again; the re-rendered `.rung` diffed against the edited one
   confirms the change landed.

The ACD is the source of truth at every point. The `.rung` form is a
generated, checked-in projection of it — regenerated on every export so PLC
changes are reviewable in the readable form and drift is impossible to hide.

This **replaces** the imperative transpiler
(`src/dune_winder/transpiler/` + `src/dune_winder/plc_ladder/`), which
attempted to write `.rll`-type files from "python-ish" code, and it
**retires** the `pasteable.rll` copy/paste loop as a modification path.
Importing routine L5X is a Studio-recognized way to modify a project and
carries tag definitions; pasting rung text is not, and cannot create tags.
The transpiler's imperative shape was also the wrong fit: it hides rungs,
and the rung structure is exactly what we want the LLM to reason about.

The language must **mirror the structure and execution semantics of ladder
logic** (rungs, scan order, edge behavior, latches, branches) while removing
the constructs that make raw ladder error-prone for an LLM to write — and,
just as importantly, every readable construct must be **recoverable from
existing ladder** by the renderer, because rendered code is what the LLM
sees first.

---

## 1. Background: the export pipeline and the L5X routine form

`plc-acd-export` (`src/dune_winder/acd_export_l5x.py`) already regenerates
the whole `winder/plc/` tree from the ACD: per-routine
`<routine>_Routine_RLL.L5X` (byte-identical to Studio's own "Export Routine"
output), `studio_copy.rllscrap`, tag JSONs with live values, `pasteable.rll`,
and `acd_index.json` provenance. This plan adds one output to that list —
the rendered `.rung` — and one new tool that goes the other way.

Each routine L5X is three layers stacked in one XML document:

1. **Context shell.** `<RSLogix5000Content … ContainsContext="true">` wrapping
   `Use="Context"` declarations of every tag the routine references: controller
   tags (`STATE`, `MOVE_TYPE`, `NEXTSTATE`, …), full `AXIS_CIP_DRIVE` parameter
   blocks for `X_axis`/`Y_axis`/`Z_axis` (hundreds of vendor attributes each),
   UDTs (e.g. `MOTION_INSTRUCTION`), modules, and program-scoped local tags.
   This is **machine state, not logic** — none of it is authored by hand, and
   the export pipeline reproduces it fresh from the ACD on every run.

2. **Target routine.** Exactly one element marked `Use="Target"`:
   `<Routine Name="main" Type="RLL">`.

3. **The ladder.** Inside `<RLLContent>`, one element per rung:
   ```xml
   <Rung Number="0" Type="N">
     <Text><![CDATA[XIC(INIT_DONE)CMP(STATE=9)OTE(state_unservo_active);]]></Text>
   </Rung>
   ```
   The CDATA text is the `.rllscrap` paren dialect, one rung per element.

### Key consequence

The *logic* the LLM needs to produce is **only the rung CDATA plus any new
tag declarations**. The large context layer is harvested verbatim from the
freshly exported L5X for the same routine (the **donor**); genuinely new tags
are synthesized from their `.rung` declarations. The compiler never invents
axis tuning, UDTs, or module config.

### The forms and their roles

| File                   | Produced by                  | Role                                            |
| ---------------------- | ---------------------------- | ----------------------------------------------- |
| `.ACD`                 | Studio 5000 (save)           | **Source of truth**                             |
| `*_Routine_RLL.L5X`    | `plc-acd-export` / `rung-compile` | Export snapshot / **the import unit**      |
| `<routine>.rung`       | `plc-acd-export` (render)    | LLM-readable projection; what LLMs edit         |
| `studio_copy.rllscrap` | `plc-acd-export`             | Internal rung-text form; equivalence-check IR   |
| `pasteable.rll`        | `plc-acd-export`             | Legacy; kept for reference, no longer a modification path |

Direction of authority: ACD → everything else. An edited `.rung` becomes
authoritative only for the duration of one compile-import cycle, after which
the re-export reasserts the ACD's version (which should now match).

---

## 2. What makes raw ladder LLM-hostile

Grounded in the real routines under `winder/plc/`:

1. **Bracket branches** `[a, [b,c], d]` — OR-of-legs, AND-in-series, NOT only on
   individual contacts. Deep nesting is unreadable and the model loses bracket
   depth. (See `state_3_move_xy/main` entry rung, §4.2.)
2. **Positional motion args** — `MAM(Z_axis,ctl,0,0,1000,Units per sec,10000,Units per sec2,…)`
   is ~20 positional fields with magic enum strings (`Units per sec2`,
   `S-Curve`, `Active Motion`, `Programmed`). No model reliably recalls order.
3. **One-shot storage arrays** — `OSR(unservo_ons_storage[3], entered_state_9_osr)`
   forces manual allocation of a unique storage-bit index per edge.
4. **Timer presets live in metadata**, not the text. The preset belongs in the
   source next to the timer.
5. **Implicit dataflow** — a rung is "condition ⇒ action," but that intent is
   buried in contact-series syntax.
6. **Tag scope is invisible** — nothing in the rung text says whether a tag
   exists, or at which scope. The old paste loop failed silently on unknown
   tags; tag creation was a separate manual step.

The language must neutralize all six. Items 2–4 must be neutralized **in both
directions**: the renderer recovers the readable form from existing ladder,
not just the compiler lowering it.

---

## 3. The language: `.rung`

Governing principle: **stay 1:1 with rungs.** Top-to-bottom source order = scan
order. Each statement is a guarded action ≈ one rung (or a small, well-defined
group of rungs for the sugar forms). The author writes normal boolean
expressions and named-argument instructions; the compiler owns the bracket
algebra and storage allocation.

Second principle: **every surface form is round-trippable.** A construct earns
its place only if (a) the compiler can lower it deterministically and (b) the
renderer can recognize its lowered shape in existing ladder and render it
back. Sugar the renderer cannot recognize would never appear in the code LLMs
actually read, so it would be dead weight.

### 3.1 File header and tag declarations

```
routine <program>/<routine>

uses <name>, <name>, ...        # references to tags that already exist
                                # (controller- or program-scoped; resolved against the JSON exports)

local <type> <name> [attrs]     # NEW program-scoped tag this routine introduces
```

The renderer generates `uses` and `local` blocks automatically from the rungs
plus the tag JSONs; the LLM only writes new `local` lines when introducing
tags.

Types (mapping to L5X `DataType`):

| `.rung` type | L5X DataType         | Notes                                            |
| ------------ | -------------------- | ------------------------------------------------ |
| `bool`       | `BOOL`               |                                                  |
| `int`        | `INT`                |                                                  |
| `dint`       | `DINT`               |                                                  |
| `real`       | `REAL`               |                                                  |
| `motion`     | `MOTION_INSTRUCTION` | control tag for MSO/MSF/MAM/MAFR/MCLM/…          |
| `timer`      | `TIMER`              | declared with a `preset` attribute (see §3.5)    |
| `counter`    | `COUNTER`            | declared with a `preset` attribute               |
| `oneshot`    | `BOOL`               | sugar marker; see `on rising` / `on entry`       |

Attributes: `preset 250ms` (timers/counters), array dims `bool[32]`, etc.

**Compiler-enforced rule (replaces the AGENTS.md human checklist):** every tag
named in the routine must be either `uses` (and present in the JSON exports) or
`local`. An unresolved tag is a compile error, not a Studio import surprise.

### 3.2 Guarded actions — the core form

```
<action>  when <bool-expr>          # single guarded action (one rung)

when <bool-expr>:                    # grouped: several actions share a condition
    <action>
    <action>

<bool-target> = <bool-expr>          # OTE: output follows the rung condition
```

- **`<bool-expr>`**: `and` / `or` / `not`, comparisons (`==`, `!=`, `>=`, `>`,
  `<=`, `<`), arithmetic (`+ - * /`, `abs`, `sqr`, `sin`, `cos`, `atn`, `mod`),
  member access (`main_xy_move.IP`, `x_axis_msf.DN`), array index
  (`storage[0]`). Normal precedence; parentheses allowed.
- **`<action>`**: an assignment (`NEXTSTATE = 1`) or a named instruction
  (`servo_off X_axis using x_axis_msf`).
- **`let <name> = <bool-expr>`**: a reusable named sub-condition (compile-time
  alias, *not* a tag) so shared guards stay DRY and the compiler can factor
  them into shared series/branch contacts.

### 3.3 Assignment lowering

| `.rung`                    | rllscrap                       |
| -------------------------- | ------------------------------ |
| `NEXTSTATE = 1`            | `CPT(NEXTSTATE,1)`             |
| `STATE_REQUEST = 0`        | `MOV(0,STATE_REQUEST)` *or* `CPT` |
| `dx = abs(start - X_POSITION)` | `CPT(dx,ABS(start-X_POSITION))` |
| `STATE3_IND = entry_ok and Z_RETRACTED` | series contacts + `OTE(STATE3_IND)` |

Rule: assignment of a constant or simple copy → `MOV`; assignment of an
expression → `CPT`; assignment of a boolean expression to a `bool` target →
contacts + `OTE`. The renderer maps both `MOV` and `CPT` back to `=`, so the
choice is invisible at the `.rung` level.

### 3.4 Boolean → ladder lowering (the core algorithm)

A `<bool-expr>` guard compiles to a contact network by:

1. **Negation normal form (NNF).** Push `not` down to literals using De Morgan.
   Contacts: `XIC` ↔ `XIO`; comparators have negation duals
   (`GRT`↔`LEQ`, `GEQ`↔`LES`, `EQU`↔`NEQ`). Arithmetic comparisons that don't
   map to a single contact go inside a `CMP(expr)` whose expression carries the
   negation directly. This guarantees NNF is always representable — ladder
   cannot negate a whole branch, only literals.
2. **Sum-of-products (SOP).** Distribute to `OR` of `AND`-terms. Each product
   term = a series of contacts; the `OR` = parallel branch legs
   (`BST … NXB … BND`).
3. **Factor shared prefixes.** Pull common leading contacts out of the branch to
   match hand-written ladder shape (this is what `let` bindings hint at). This
   step is an optimization; an unfactored SOP is already correct. The existing
   `plc_ladder/branch_simplifier.py` proves branch simplification is tractable
   in this repo and can be referenced (not imported) for heuristics.

The reverse direction is simpler: a contact network is already a boolean
expression; the renderer rebuilds `and`/`or`/`not` from series/branch/contact
structure directly.

Comparisons strategy: two-operand comparison of plain tags → dedicated contact
(`GEQ(a,b)`); anything with arithmetic → `CMP(expr)`. Both are valid ladder.

### 3.5 Sugar (only where it removes a documented footgun)

**Edge detection (footgun #3).** Auto-allocates the OSR storage bit and edge
output; the author never manages array indices:

```
on rising <bool-expr>:        # OSR on false→true transition
    <action>
    ...
on entry of <bool>:           # alias: rising edge of a state-active bit
on falling <bool-expr>:       # OSF
```

Lowers to: one rung computing `OSR(storage[k], edge_bit)` (compiler picks `k`
and names `edge_bit`), then each `<action>` gated by `edge_bit`. **Reverse
rule:** the renderer recognizes the idiom — a rung whose only output is
`OSR(storage, edge)` followed by rungs gated on `edge` — and renders it as
`on rising`. Edge bits referenced outside the idiom shape stay explicit.

**Motion, named-argument (footguns #2, #4).** Each motion instruction has a
fixed key schema with defaults for trailing/optional fields:

```
move_axis Z_axis using z_axis_pre_xy_retract:
    type     = absolute          # → positional move-type 0
    position = 0
    speed    = 1000  units/s     # → "Units per sec"
    accel    = 10000 units/s2    # → "Units per sec2"
    decel    = 10000 units/s2
    profile  = s-curve           # → "S-Curve"
    jerk     = 10000             # accel & decel jerk

servo_on   X_axis using x_axis_mso     # → MSO(X_axis,x_axis_mso)
servo_off  X_axis using x_axis_msf     # → MSF(X_axis,x_axis_msf)
fault_reset X_axis using x_axis_mafr   # → MAFR(X_axis,x_axis_mafr)

coordinated_move X_Y using main_xy_move:   # → MCLM(...)
    type   = absolute
    target = X_POSITION
    speed  = XY_SPEED_REQ units/s
    accel  = XY_ACCELERATION units/s2
    decel  = XY_DECELERATION units/s2
    profile = s-curve
    termination = programmed
```

Unit suffixes (`units/s`, `units/s2`, `units/s3`) map to the magic strings;
enum keywords (`absolute`, `s-curve`, `trapezoidal`, `programmed`, `disabled`,
`active-motion`, `coordinated-move`) map to their vendor strings. The schema is
defined once in the compiler, sourced from `winder/plc/instruction_set.md` plus
the observed vendor arg order. **Reverse rule:** trivial — the arg order is
fixed, so positional → named is a table lookup. This is the highest-value
de-sugaring and lands early (§7 M4).

**Timers with presets in source (footgun #4):**

```
local timer tension_stable_timer preset 250ms

start_timer tension_stable_timer  when check_tension_stable    # → TON(t, 250, 0)
```

The preset is emitted into the rung **and** into the tag's `PRE` in the L5X
`<Data>`. **Reverse rule:** the renderer reads `PRE` from the tag JSON and
lifts it into the `local timer … preset` declaration.

**Subroutine calls:** `call xy_speed_regulator` → `JSR(xy_speed_regulator,0)`.
The compiler checks the target routine exists (see `plc_ladder/jsr_registry.py`
for the existing notion of a JSR registry).

### 3.6 Escape hatch — the renderer's no-fail guarantee

Any rung that the surface syntax can't express is writable verbatim:

```
raw `XIC(weird_tag)SOMENEWINSTR(a,b,c);`
```

The text is passed through to a `<Rung>` unchanged (after the normal tag-scope
check is skipped with a warning).

In reverse this is an **invariant, not a convenience**: the renderer must
render *every* rung of *every* routine — anything it cannot express in surface
syntax comes out as `raw`. Rendering never fails, so the full ACD always has a
`.rung` projection, even before every instruction has sugar. A `raw`-density
metric per routine tracks how much of the tree is idiomatic yet.

### 3.7 Comments

L5X rungs carry `<Comment>` elements and Studio preserves them through import,
so the **forward** path works today: `# comment` lines attached to a statement
compile into rung comments.

The **reverse** path is currently blocked: `plc-acd-export` does not extract
rung comments (the `Comments.Dat` linkage in the ACD is not reverse
engineered). Until that gap closes, LLM-authored comments would be silently
dropped on the next re-export — breaking idempotence and discarding exactly
the readability this plan exists to create. Interim rule: **the renderer
carries comments forward from the previous checked-in `.rung`** by rung
identity (same routine, semantically-equal rung text), and flags comments it
could not re-attach. Closing the `Comments.Dat` gap properly is tracked as
follow-on work in `plc-acd-export`, not in this package.

---

## 4. Worked translations (acceptance fixtures)

These are the golden round-trip tests: the compiler must reproduce the existing
rllscrap (semantically; rung packing may differ) from these sources, **and the
renderer must produce source of this shape from the existing rllscrap**.

### 4.1 `state_9_unservo/main` (full routine)

```
routine state_9_unservo/main
uses INIT_DONE, STATE, STATE_REQUEST, NEXTSTATE, MOVE_TYPE, X_axis, Y_axis, Z_axis

local bool    state_unservo_active
local motion  x_axis_msf, y_axis_msf, z_axis_msf
local motion  x_axis_mafr, y_axis_mafr, z_axis_mafr

state_unservo_active = INIT_DONE and STATE == 9

on entry of state_unservo_active:
    servo_off X_axis using x_axis_msf
    servo_off Y_axis using y_axis_msf
    servo_off Z_axis using z_axis_msf

on rising x_axis_msf.DN:  fault_reset X_axis using x_axis_mafr
on rising y_axis_msf.DN:  fault_reset Y_axis using y_axis_mafr
on rising z_axis_msf.DN:  fault_reset Z_axis using z_axis_mafr

when state_unservo_active and x_axis_mafr.DN and y_axis_mafr.DN and z_axis_mafr.DN:
    MOVE_TYPE = 0
    STATE_REQUEST = 0
    NEXTSTATE = 1
```

Target (existing) rungs:
```
XIC(INIT_DONE)CMP(STATE=9)OTE(state_unservo_active);
XIC(state_unservo_active)OSR(unservo_ons_storage[0],entered_state_9_osr);
XIC(state_unservo_active)XIC(entered_state_9_osr)MSF(X_axis,x_axis_msf);
... (Y, Z) ...
XIC(x_axis_msf.DN)OSR(unservo_ons_storage[1],x_axis_msf_dn_osr);
XIC(x_axis_msf_dn_osr)MAFR(X_axis,x_axis_mafr);
... (Y, Z) ...
XIC(state_unservo_active)XIC(x_axis_mafr.DN)XIC(y_axis_mafr.DN)XIC(z_axis_mafr.DN)CPT(MOVE_TYPE,0)MOV(0,STATE_REQUEST)CPT(NEXTSTATE,1);
```

### 4.2 `state_3_move_xy/main` entry rung (hard branch case)

Raw:
```
XIO(main_xy_move.IP)CMP(STATE=3)[XIC(tension_stable_timer.DN),XIO(check_tension_stable),XIO(TENSION_CONTROL_OK)]
[[XIO(Z_RETRACTED),GEQ(Z_axis.ActualPosition,MAX_TOLERABLE_Z)]CPT(ERROR_CODE,3001)CPT(NEXTSTATE,10)
,XIC(Z_RETRACTED)[XIC(APA_IS_VERTICAL),XIO(APA_IS_VERTICAL)CPT(ERROR_CODE,3005)CPT(NEXTSTATE,10)]OTE(STATE3_IND)];
```

New:
```
let entry_ok = not main_xy_move.IP and STATE == 3
               and (tension_stable_timer.DN or not check_tension_stable or not TENSION_CONTROL_OK)

when entry_ok and (not Z_RETRACTED or Z_axis.ActualPosition >= MAX_TOLERABLE_Z):
    ERROR_CODE = 3001
    NEXTSTATE  = 10

when entry_ok and Z_RETRACTED and not APA_IS_VERTICAL:
    ERROR_CODE = 3005
    NEXTSTATE  = 10

STATE3_IND = entry_ok and Z_RETRACTED
```

This fixture demonstrates the flattening recovers intent that bracket nesting
obscured. Note the compiler may emit this as 3 rungs rather than 1; equivalence
is checked semantically (see §6), not by byte-identity.

---

## 5. Pipeline and package layout

Two directions, sharing one IR:

```
render (the front door, runs inside plc-acd-export):
    rllscrap ──parse──► rung IR ──recognize sugar──► .rung text

compile (runs when an LLM has edited a .rung):
    .rung ──parse──► AST ──check──► lower ──► rung IR ──► emit L5X
                                                    └───► emit rllscrap (internal/CI)
```

New package (independent of `plc_ladder/` and `transpiler/`, both of which are
retired by this work):

```
src/dune_winder/rung_lang/
    __init__.py
    __main__.py          # CLI: rung-compile <file.rung> [--emit l5x|rllscrap]
    ast.py               # RoutineDecl, TagDecl, GuardedAction, Assignment, Instr, Expr nodes
    parser.py            # .rung text → AST (hand-written recursive descent)
    schema.py            # instruction key-schemas (motion arg order, enum/unit string maps)
    check.py             # tag scope resolution, motion-key validation, JSR target existence
    lower.py             # AST → rung IR: NNF → SOP → factor; sugar expansion; storage alloc
    rung_ir.py           # contact-network IR (Rung/Branch/InstructionCall) + evaluator
    render.py            # rung IR → .rung text; sugar recognition; comment carry-forward
    emit_rllscrap.py     # rung IR → paren dialect (internal format for equivalence checks)
    emit_l5x.py          # rung IR + tag context → full <RSLogix5000Content> document
    context.py           # donor-L5X harvesting; synthesize <Tag> for new locals
    equiv.py             # semantic equivalence checker over the rung IR
tests/dune_winder/
    test_rung_parser.py
    test_rung_lower.py           # boolean→branch algebra unit tests
    test_rung_render.py          # sugar recognition; raw fallback; determinism
    test_rung_roundtrip.py       # every routine: rllscrap → .rung → rllscrap (semantic eq)
                                 # and .rung → rllscrap → .rung (fixed point)
    fixtures/rung/*.rung         # the §4 fixtures + one per existing routine
```

CLI entry points (alongside the existing `uv run plc-*` console scripts):

- `uv run rung-compile <file.rung>` → routine L5X next to the source
  (`--emit rllscrap` for the internal form; `--check-only` to validate).
- `uv run rung-render <routine>` → `.rung` from the routine's rllscrap
  (also invoked by `plc-acd-export` for every routine; the standalone CLI
  exists for development and spot-rendering).

`plc-acd-export` gains output #7: `<program>/<routine-dir>/<routine>.rung`,
checked in next to `studio_copy.rllscrap`.

### Tag context resolution (`context.py`, `emit_l5x.py`)

For an importable L5X the compiler produces the context shell:

1. Start from the **donor L5X** for the same routine —
   `<program>/<routine>_Routine_RLL.L5X` as written by the latest
   `plc-acd-export` run (always fresh from the ACD, never hand-maintained).
   Copy its `Use="Context"` blocks verbatim — axes, UDTs, modules, existing
   program/controller tags.
2. For each `local` tag not already present, synthesize a `<Tag>` with the right
   `DataType`/`Dimensions` and zeroed `<Data Format="L5K">` + `<Data
   Format="Decorated">` (pattern copied from existing `MOTION_INSTRUCTION` /
   `BOOL` tag blocks in the exports). This is what makes new tags arrive with
   the import — the capability the paste loop never had.
3. Replace the `Use="Target"` routine's `<RLLContent>` with the emitted rungs.

Never synthesize `AxisParameters`, UDT field layouts, or module config — always
reuse.

### Determinism

Rendered `.rung` text must be a pure function of the rung IR plus tag JSONs:
stable statement order (scan order), stable name choices, stable formatting.
Likewise compiled output must be a pure function of the source. Without this,
every export cycle produces diff churn and the git history of `.rung` files
becomes useless.

---

## 6. Verification strategy

PLC code is safety-critical; the trust model must be earned incrementally.
Three independent gates stand between an LLM edit and the controller:

- the **semantic equivalence checker** (automated, this package),
- **Studio's own L5X import validation** (rejects unresolved tags, malformed
  rungs, bad data types — a vendor-maintained schema check we get for free),
- the **human** driving the import dialog and reviewing what Studio reports.

### 6.1 Semantic equivalence checker

Evaluate a routine's contact network against random tag valuations and compare
outputs between two rung-IR forms. Two routines are equivalent if every output
instruction fires under the same valuations. This tolerates rung-packing and
branch-factoring differences while catching logic errors. Used by CI and by
`rung-compile`, which prints an equivalence report against the routine's
current rllscrap whenever it compiles an edit.

### 6.2 Round-trip CI, both directions

For all ~22 existing routines:

1. **Render soundness:** `rllscrap → .rung → rllscrap`, asserted equivalent
   by §6.1. The renderer may not change meaning, ever.
2. **Fixed point:** `.rung → rllscrap → .rung` reproduces the input text
   byte-for-byte for renderer-produced sources. This is what keeps the
   edit-import-re-export cycle diff-clean: after a successful import, the next
   `plc-acd-export` must regenerate the same `.rung` the LLM wrote (modulo
   constructs the LLM wrote that the renderer normalizes — those normalize
   once and are then stable).

### 6.3 The ACD round-trip is the end-to-end proof

The retired `plc-sync --offline` paste-confirmation loop is replaced by:

1. LLM edits `<routine>.rung`; `rung-compile` produces the routine L5X and an
   equivalence report describing exactly which rungs changed.
2. Human imports the L5X in Studio (Import Routine → review the Import
   Configuration dialog, where new tags appear for creation), saves the ACD.
3. `uv run plc-acd-export` regenerates the tree. `git diff` on the `.rung`
   file is the confirmation: empty diff against the edited source = the change
   landed exactly. `acd_index.json` ties the result to specific ACD bytes.

### 6.4 Pending-edit rungs

The ACD can contain pending-edit rungs (`Type="e"`); `plc-acd-export` emits
them in display order. The renderer must mark these
(`# PENDING EDIT in Studio` annotation) and `rung-compile` must **refuse to
compile a routine whose source contains pending-edit markers** — importing
over a routine with uncommitted Studio edits is a corruption vector. The human
finalizes or discards the pending edits in Studio first.

### 6.5 Comment safety

Per §3.7: until `Comments.Dat` extraction lands, the renderer's comment
carry-forward must report (not silently drop) any comment it failed to
re-attach, so review catches it in the export diff.

---

## 7. Milestones

**M0 — Import linchpin spike (do first, it's the premise).**
Hand-modify one exported routine L5X: change one rung, add one synthesized
`<Tag>` to the context. Import via the Studio GUI; confirm the Import
Configuration dialog offers to create the new tag and the rung change lands.
Save, re-export with `plc-acd-export`, confirm the round-trip. No code —
this validates the entire approach before any is written. Document the exact
import-dialog steps in `winder/plc/RLL_FORMAT.md` or a sibling doc.

**M1 — Rung IR + parser + boolean lowering + equivalence checker.**
`rung_ir.py` (with evaluator), `ast.py`, `parser.py`, `lower.py` (NNF→SOP,
unfactored branches ok), `emit_rllscrap.py`, `equiv.py`. The checker comes
*first*, with the IR, because every later milestone is gated on it. Unit
tests for boolean→branch algebra. Fixture: `state_9_unservo` with `raw` for
the motion/OSR rungs.

**M2 — Renderer over the full tree + round-trip CI.**
`render.py` with the `raw` fallback invariant, determinism, pending-edit
markers, comment carry-forward. `test_rung_roundtrip.py` over all existing
routines, both directions (§6.2). Wire into `plc-acd-export` as output #7 and
commit the rendered tree. At this point LLMs can *read* every routine; the
`raw`-density metric says how idiomatically.

**M3 — L5X emit + context resolution: first end-to-end edit.**
`context.py`, `emit_l5x.py`, donor harvesting, new-tag synthesis,
`rung-compile` CLI. Deliverable: one real (small) routine edit authored in
`.rung`, compiled, imported through the Studio GUI, re-exported, empty diff.
This is the goal pipeline working end to end; everything after is readability.

**M4 — Motion named-argument schemas, both directions.**
`schema.py` + `check.py` validation forward; positional→named rendering in
reverse (mechanical — fixed arg order). Biggest single `raw`-density drop:
the motion state routines (`state_3_move_xy`, `state_5_move_z`,
`state_12_move_xz`) become readable.

**M5 — Edge, assignment-style, and timer sugar.**
`on rising`/`on entry`/`on falling` with storage allocation forward and idiom
recognition in reverse; `start_timer` with preset lifted from tag JSON.
Renderer recognition is the hard half; edge bits used outside the idiom shape
stay explicit, and that's fine.

**M6 — Branch factoring + prefix sharing (cosmetic).**
Make compiled rungs resemble hand-written ladder (shared prefixes, packed
outputs) so the Studio-side view stays familiar. Gated on the equivalence
checker staying green; pure polish.

After M3 the pipeline is live and each later milestone only improves the
fraction of the tree that renders idiomatically.

---

## 8. Open questions / decisions to confirm

- **Naming for renderer-introduced constructs** — when compiling LLM-authored
  sugar, auto-generate OSR storage indices and edge-bit names
  deterministically (e.g. derived from the guard expression hash or statement
  position) rather than reproducing historical names; the equivalence checker,
  not byte-diffing, is the correctness bar. Confirm the deterministic scheme.
- **Where `.rung` lives** — proposed: `<program>/<routine-dir>/<routine>.rung`
  next to `studio_copy.rllscrap`. Alternative: a parallel `winder/plc_src/`
  tree. Lean: next to the rllscrap, one directory per routine as today.
- **Pasteable.rll retirement timing** — keep generating it for reference until
  M3 proves the import path, then decide whether `plc-acd-export` drops it.
- **Parser tech** — hand-written recursive descent (no dep, full control) vs.
  `lark` grammar. Lean: hand-written to avoid a new runtime dep in the winder
  package.
- **How much of `plc_ladder` to reference** — the new stack is standalone, but
  `render.py` needs an rllscrap→IR parser, and `plc_ladder/parser.py` already
  parses the paren dialect. Lean: port (copy + trim) the parsing logic into
  `rung_lang` rather than importing across packages, so retiring
  `plc_ladder`/`transpiler` later deletes cleanly.
- **`Comments.Dat` extraction** — schedule as `plc-acd-export` follow-on work;
  decide whether carry-forward (§3.7) is acceptable in the interim or whether
  comment support waits.

---

## 9. Out of scope

- Synthesizing axis tuning, UDT layouts, or module configuration — always
  reused from the donor export.
- Automating the Studio import itself — the human drives the GUI import and
  remains the final gate. (LogixServices COM automation was investigated and
  fails; the Logix Designer SDK is not installed. If that changes, automation
  is a separate plan.)
- Closing the `Comments.Dat` reverse-engineering gap — tracked as
  `plc-acd-export` work, not this package (interim carry-forward per §3.7).
- Reverse compilation of arbitrary hand-written ladder into *maximally*
  idiomatic `.rung` — the renderer is best-effort plus `raw`; `raw`-density
  improves milestone by milestone but never needs to hit zero.
