# Recipe Template Language

This project now uses a shared mini-language for U/V wrap generation in:

- `src/dune_winder/library/RecipeTemplateLanguage.py`

## Goals

- Keep layer recipes declarative and readable.
- Reuse one execution path for U and V templates.
- Preserve existing G-Code output while reducing duplicated control flow.

## Statements

Each script line is one of:

- `emit <text>`
- `emit_head_restart <text>`
- `transition <name>`
- `if <expr>: emit <text>`
- `if <expr>: emit_head_restart <text>`
- `if <expr>: transition <name>`

Blank lines and lines starting with `#` are ignored.

## Interpolation

`emit` text supports `${expr}` interpolation.

Expressions are evaluated against the current environment dictionary and a
restricted set of helpers (`abs`, `int`, `float`, `min`, `max`, `round`).

If an interpolated expression returns `None`, it is removed from the rendered
line. Final whitespace is normalized to single spaces.

Example:

```text
emit G109 PB${1200 + wrap} PXY ${offset('PX', offsets[0])} G102
if near_comb(799 + wrap): emit G103 PF${799 + wrap} PF${798 + wrap} PX G105 ${coord('PX', Y_PULL_IN * COMB_PULL_FACTOR)}
```

## Transitions

`transition <name>` dispatches to a Python callback supplied by the caller.

U/V currently register:

- `transfer_b_to_a`
- `transfer_a_to_b`

These map to `append_pause_to_motion_transition(...)` and
`append_motion_to_pause_transition(...)` in
`TemplateGCodeTransitions.py`.

## Current Usage

The language is used for wrap rendering in:

- `src/dune_winder/library/UTemplateGCode.py` (`U_WRAP_SCRIPT`)
- `src/dune_winder/library/VTemplateGCode.py`
  (`V_WRAP_BASE_SCRIPT`, `V_WRAP_NORMAL_TAIL_SCRIPT`, `V_WRAP_FINAL_TAIL_SCRIPT`)
- `src/dune_winder/library/XGTemplateGCode.py`
  (`XG_PREAMBLE_SCRIPT`, `XG_WRAP_SCRIPT`, `XG_POSTAMBLE_SCRIPT`)

Preamble/header and recipe I/O APIs are unchanged.
