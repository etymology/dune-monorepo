# anchorToTarget template DSL for the U/V wrapping variants

## Context

The default U/V G-Code variants are written in the mini-language from
`src/dune_winder/recipes/recipe_template_language.py` — flat scripts of
`emit ...` / `if <cond>: emit ...` statements with `${...}` interpolation
(`V_WRAP_BASE_SCRIPT`, `U_WRAP_SCRIPT`, and the XG preamble/wrap/postamble
trio). The `wrapping` variant, which emits `~anchorToTarget` / `~increment` /
`~goto` macros instead of raw G-Code, was never converted: it lived in two
~190-line hand-rolled builders (`_render_wrapping_wrap_lines` in each of
`u_template_gcode.py` and `v_template_gcode.py`) that assembled lines with
`lines.extend([...])` and nested closures.

That made the two layers hard to compare and hid several load-bearing
asymmetries in Python control flow. This change expresses both wrapping
variants as scripts in the same language, with the four capabilities the
builders were faking: per-wrap parameterisation, interpolated calculated
values, conditional lines, and preamble/postscript sections.

**The refactor is byte-identical.** No generated G-Code changes.

## What was added

`src/dune_winder/recipes/anchor_template_language.py` — reuses
`recipe_template_language.py` **unchanged**. Everything anchor-specific arrives
through the `environment` dict, so the shared statement grammar (and the four
generators that depend on it) is untouched.

- `AnchorLayerAdapter` — the layer-specific half, one module-level constant per
  layer: line builder, `coord`, `wrap_pin`, `near_comb`, `annotate_wrap_lines`,
  offset mode, and `named_values` spliced into the environment.
- `AnchorScriptSections` / `compile_anchor_script_sections` — `preamble`,
  `wrap`, `wrap_tail`, `final_wrap_tail`, `postscript`. A `None` section is
  skipped, never substituted for another.
- `render_anchor_layer_lines(sections, adapter, *, offsets, pull_ins, wrap_count)`
  — emits the preamble un-annotated, walks the wraps applying the layer's
  `(w,l)` annotation, then the postscript un-annotated.

Script-visible helpers: `wrap`, `n`, `b_pin`, `a_from_b`, `wrap_pin`,
`near_comb`, `anchor`, `increment`, `goto`, `offset_natural` (U) /
`offset_xy` (V), `X_PULL_IN`, `Y_PULL_IN`, `COMB_PULL`.

Two deliberate guards: the preamble/postscript environment omits `wrap`/`n`
entirely so a stray reference raises instead of rendering `""`, and an `emit`
that renders to nothing raises rather than appending a blank line. Both failure
modes would otherwise shift every `(w,l)` identifier and silently re-point
saved jog-calibration offsets.

## Why sections rather than a conditional

The shared grammar has no `else` and no blocks — `if <cond>:` takes exactly one
statement. V's wrap 400 ends differently from wraps 1–399, so that ending has
to be a separate section. U instead has a two-line postscript outside the wrap
numbering. The container serves both.

## Asymmetries preserved verbatim

These were invisible in the hand-rolled form and are now commented in the
scripts. Each is a real behavioural difference, not a tidy-up opportunity:

| Aspect | U | V |
| --- | --- | --- |
| Cross-side transfer flag | `hover=True` | `inTwoMoves=True` |
| Comb-pull signs | `-,-,+,+` | `+,+,-,-` |
| Comb-pull comment | `(comb pull)` | none (adding one changes 69 of 400 wraps) |
| Offset axis | pinned to the offset id's natural axis when emitted | both components emitted, clamped later by `enforce_offset_natural_axis` |
| `add_foot_pauses` | inert (the G103-based pass matches nothing here) | live, 24 lines |
| Tail | un-annotated postscript, not override-addressable | inside wrap 400, override-addressable |
| Post-processing order | foot pauses → overrides → axis | overrides → foot pauses → axis |

The comb-pull sign tracks which side of the board the head is on (whether the
`±X_PULL_IN` traverse has happened yet), not the direction of the preceding Y
move. It cannot be derived; it is literal data per site.

`near_comb` must receive the **wrapped** pin wherever the expression can go
negative. `n - 399` is negative for wraps 1–399; passing it raw never matches a
comb and deletes 18 wraps' clearance moves.

## Verification

A scratchpad harness rendered 321 input combinations per side — every offset
index scalar/dict/positive/negative, float-quantisation boundaries, all four
offset input routes, pull-in overrides, every flag, `line_offset_overrides`
including comb-pull neighbours and the un-annotated lines that alias onto the
`(w,l)` regex, and the error paths — plus the `default` and `xz` variants as a
canary for the shared runtime. Baseline captured at `e8243e1b` before any edit:
**321/321 byte-identical.**

`tests/dune_winder/test_anchor_template_language.py` is the durable half: 26
tests covering the DSL itself plus the wrapping invariants nothing previously
guarded — total line counts (7276 U / 7274 V), comb-pull counts and labelling,
U's `add_foot_pauses` no-op, offsets on all 12 indices per layer, U pull-in
overrides. Verified to fail under mutation.

## Follow-up: the U head-end off-by-one, now fixed

Converting the builder to a script made a latent bug legible. The old code used
`b_pin(1 - 399 + n)` where the two preceding statements use `n - 399`, and
`1 - 399 + n` is `n - 398` — so the "Bottom B corner - foot end" move anchored
one pin past where the wire had actually been left (B2003 vs B2002 on wrap 1).

Fixed 2026-08-06 by using `b_pin(n - 399)`. Scope of the change: **U only**,
400 lines (one per wrap), all of them the "Bottom B corner - foot end" anchor.
Line counts, comb pulls, `(w,l)` identifiers and V output are all unaffected,
so saved jog-calibration offsets keep pointing at the same corners.

The general invariant is now asserted rather than the specific pins: the wire
is one continuous strand, so every anchor must equal the previous move's
target — 4801 moves on U, 4799 on V, across wrap boundaries and into U's
postscript. `tests/dune_winder/test_anchor_template_language.py` checks it for
both layers, plus that no `${...}` brace survives into the output and that every
emitted call is accepted by the runtime's `_ANCHOR_TO_TARGET_RE.fullmatch`.

## Known issues, deliberately not fixed here

1. **`U_WRAP_WRAPPING_SCRIPT` (`u_template_gcode.py`) is dead code** — a
   `G115`/`G117`/`G118` script with no references. Left in place because a plan
   doc still cites it; delete separately.
2. **`line_offset_overrides` keys alias onto un-annotated lines.**
   `extract_line_key` reads the first `(\d+,\d+)` in a line, so a key of
   `(7174,0)` mutates U's `~goto(7174,0)` and `(70,0)` mutates its tail
   `~increment(70,0)`. Preserved; worth fixing separately.
