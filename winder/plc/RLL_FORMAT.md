# RLL file format guide

This guide explains the two ladder-logic text formats checked in under
`dune_winder/plc/<program>/<routine>/` and how they relate. For the
*meaning* of individual instructions (`XIC`, `OTE`, `MAM`, …), see
[`instruction_set.md`](instruction_set.md). This document is purely about
**syntax, surface formatting, and the two-way conversion**.

## 1. Why two formats?

Studio 5000 Logix Designer (the Rockwell IDE that programs the
ControlLogix PLC) does not expose its routines as a checked-in textual
representation. The only two officially supported routes that survive a
clipboard round-trip are:

1. **Copy from Studio (Ctrl+C):** Studio emits a compact, single-line,
   parenthesised text we call **`.rllscrap`** ("scrap" = the OS
   clipboard scrap). This is what comes out.
2. **Paste into Studio (Ctrl+V):** Studio accepts a slightly different,
   token-separated, multi-line text we call **`.rll`**. This is what
   goes in.

The two formats describe the same ladder, but they are not the same
text. So we check in **both** files for every routine:

| File                     | Direction                       | Source of truth?         |
| ------------------------ | ------------------------------- | ------------------------ |
| `studio_copy.rllscrap`   | Studio → repo (Ctrl+C output)   | **Yes.** Authoritative.  |
| `pasteable.rll`          | Repo → Studio (Ctrl+V input)    | No. Regenerable.         |

`pasteable.rll` is fully derivable from `studio_copy.rllscrap` via
`uv run plc-sync --offline`. If they disagree, the `.rllscrap` wins —
delete the `.rll` and regenerate.

## 2. `.rllscrap` syntax (Studio's clipboard output)

```
INSTR(arg1,arg2)INSTR(arg)...;   INSTR(arg)...;   ...
```

- **Instructions** are uppercase mnemonics: `XIC`, `OTE`, `CMP`, `MOV`,
  `MAM`, `BST`, `NXB`, `BND`, etc.
- **Operands** are inside `(...)`, separated by `,`. No spaces.
- **Rungs** are separated by `;`. Studio inserts three spaces of
  padding (`;   `) between rungs but the parser tolerates any
  whitespace.
- The whole routine is on one line.

### Branches use `[ ... , ... ]`

A parallel branch (multiple input legs) is written with brackets and
commas:

```
[XIC(A),XIO(B),XIC(C)]OTE(OUT)
```

means: `OUT` is energised when (`A` is on) OR (`B` is off) OR (`C` is
on). Brackets nest:

```
[XIC(A)[XIC(B),XIC(C)],XIC(D)]OTE(OUT)
```

means: (`A` AND (`B` OR `C`)) OR `D` → `OUT`.

### Formula instructions use the formula language inside `()`

`CMP` and `CPT` carry a formula expression rather than a positional
operand list:

- `CMP(STATE=5)` — boolean comparison.
- `CMP(ABS(Z_axis.ActualPosition-Z_POSITION)<0.1)` — nested function
  calls inside the formula are fine; commas inside formula calls do
  not split the operand list.
- `CPT(ERROR_CODE,5004)` — first operand is the destination tag, second
  operand is the formula.
- `CPT(NEXTSTATE,STATE_REQUEST+1)` — formula can reference any tag.

### String operands

String literal operands like motion units (`Units per sec`) are bare
text inside the parentheses; the converter quotes them on the way to
`.rll`. Example: `MAM(Z_axis,...,Units per sec,...)`.

## 3. `.rll` syntax (the pasteable form)

```
INSTR arg1 arg2 INSTR arg ... INSTR arg
```

- **Tokens are space-separated** within a rung.
- **Each rung is on its own line**, terminated by a newline. The file
  ends with a blank line.
- **Branches** are written with explicit `BST` … `NXB` … `BND`
  keywords:
    - `BST` — begin branch
    - `NXB` — next leg (separator between parallel legs)
    - `BND` — branch end
- **Formula text is double-quoted.** `CMP "STATE=5"`,
  `CMP "ABS(Z_axis.ActualPosition-Z_POSITION)<0.1"`. The converter
  preserves the original characters inside the quotes — including the
  `(` and `,` that would otherwise be parsed as syntax.
- **String operands containing spaces are double-quoted.**
  `MAM Z_axis ... "Units per sec" ...`.

### Translation example

`.rllscrap` (one line; rungs separated by `;`):

```
[XIC(A),XIC(B)]OTE(OUT);   CMP(STATE=1)MOV(2,NEXTSTATE);
```

`.rll` (one rung per line, BST/NXB/BND, quoted formulas):

```
BST XIC A NXB XIC B BND OTE OUT
CMP "STATE=1" MOV 2 NEXTSTATE
```

### Timer / counter expansion

In `.rllscrap`, timer and counter instructions appear as
`TON(my_timer,?,?)` because Studio emits placeholders for the preset
and accumulator. The converter looks the timer / counter up in
`programTags.json` and substitutes the real `PRE` and `ACC` values, so
`.rll` ends up with `TON my_timer 5000 5000` (preset, accum). This
substitution is one of the reasons we cannot hand-edit `.rll` and
expect a clean round-trip — the values come from the metadata files,
not the rllscrap.

## 4. Tag scope and where new tags must be declared

Every tag referenced from a routine has to exist at one of two scopes
**before** the routine is pasted into Studio. The scope determines
where it lives in the JSON metadata:

| Scope            | Declared in                                    | Example tags                              |
| ---------------- | ---------------------------------------------- | ----------------------------------------- |
| Controller       | `dune_winder/plc/controller_level_tags.json`   | `STATE`, `ERROR_CODE`, `Z_axis`, `MOVE_TYPE` |
| Program-scoped   | `dune_winder/plc/<program>/programTags.json`   | timers, one-shots, locals to one program  |

A tag referenced inside `state_5_move_z/main` that does not exist
at either scope will cause the Studio paste to fail. **When proposing
new ladder logic, you must enumerate every new tag with its scope.**
See `AGENTS.md` for the full change-proposal template.

## 5. The conversion pipeline

`uv run plc-sync --offline` walks the `plc/` tree and, for every
`studio_copy.rllscrap`, performs the following passes (implemented in
`src/dune_winder/plc_rung_transform.py` and
`src/dune_winder/convert_plc_rllscrap.py`):

1. **Bracket → BST/NXB/BND.** `[a,b,c]` → `BST a NXB b NXB c BND`,
   nested correctly.
2. **Formula protection.** `CMP(EXPR)` and `CPT(DEST,EXPR)` have their
   `EXPR` body shielded from the next pass so commas and parens inside
   formulas survive.
3. **Quote spaced operands.** Any operand containing a space picks up
   surrounding double quotes.
4. **Flatten delimiters.** Remaining `(`, `)`, `,` become spaces; `;`
   becomes a newline.
5. **Normalise whitespace.** Collapse runs of spaces, strip leading
   indentation per rung.
6. **Resolve TON/CTU presets** from `programTags.json` (see §3 above).
7. **Update `manifest.json`** with the new hash + timestamp for the
   touched `.rllscrap`.

There is no reverse pipeline. Going `.rll` → `.rllscrap` is the human's
job: paste the `.rll` into Studio, copy the routine back out, save the
result as `studio_copy.rllscrap`, run `plc-sync --offline`, and verify
the regenerated `.rll` matches what you pasted.

## 6. Joint programming protocol (humans + agents)

Because the source of truth lives behind a vendor IDE that the agent
cannot drive, joint PLC work uses a strict three-step loop:

1. **Agent proposes.** The agent edits `pasteable.rll` and produces a
   change-proposal block (see `AGENTS.md` → *Change-proposal format*)
   listing every affected routine, every new / modified tag with its
   scope, and the rung diff.
2. **Human pastes.** The human creates the listed tags in Studio 5000
   at the correct scope, opens the listed routines, and pastes the
   proposed rungs.
3. **Human round-trips.** The human selects the resulting routine,
   copies it, overwrites the corresponding `studio_copy.rllscrap`, and
   runs `uv run plc-sync --offline`. The diff against `pasteable.rll`
   confirms the paste was clean. Both files are committed together.

The agent is **never** allowed to skip step 1's enumeration of tags
and routines: a missing tag declaration silently breaks the paste at
step 2 and the human has no easy way to discover what was assumed.

## 7. Common pitfalls

- **Editing `pasteable.rll` without updating `studio_copy.rllscrap`.**
  The next `plc-sync --offline` will overwrite your edits with the
  regenerated content. Either go through the round-trip, or only ever
  treat `.rll` as a *proposal* document.
- **Forgetting to declare a new tag.** Studio rejects pastes that
  reference unknown tags. Always list new tags with their scope.
- **Using a controller-scope tag inside a program-scoped routine
  without prefixing it correctly.** Controller tags are global; program
  tags are local. Mixing them silently picks the wrong tag if the same
  name exists at both scopes — name collisions are a real footgun.
- **Hand-editing `manifest.json`.** It is regenerated by `plc-sync` and
  the rung transform; manual edits are clobbered.
- **Editing a `.rllscrap` that has Windows line endings.** The hash
  function normalises `\r\n` → `\n` before hashing, so line-ending
  churn is harmless, but most editors will still mark the whole file
  as changed. Configure your editor to preserve LF.
