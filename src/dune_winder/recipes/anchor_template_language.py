###############################################################################
# Name: AnchorTemplateLanguage.py
# Uses: Template dialect for the anchorToTarget ("wrapping") U/V G-Code.
# Date: 2026-08-06
###############################################################################
#
# The default U/V variants are already written in the mini-language from
# `recipe_template_language.py`; the wrapping variants were hand-rolled Python
# instead.  This module closes that gap without touching the shared runtime:
# the statement grammar stays `emit` / `if <cond>: emit`, and everything
# anchor-specific arrives through the `environment` dict as `${...}` helpers.
#
# A layer supplies an `AnchorLayerAdapter` (its line builder, pin arithmetic and
# offset conventions) plus `AnchorScriptSections` (preamble / wrap / wrap tail /
# final wrap tail / postscript).  `render_anchor_layer_lines` walks the wraps and
# applies the per-wrap `(w,l)` annotation; the post-processing passes stay with
# the per-layer callers because U and V order them differently.
#
# Emitted text is consumed by four separate parsers -- the runtime macro
# interpreter (`gcode/handler_base.py`), `uv_head_target_parts/constants.py`,
# `offset_axis_policy.py` and `template_gcode_foot_pauses.py`.  They agree on a
# strict shape: no whitespace inside a macro call, and `offset=` immediately
# after the two pins.  `anchor()` is the only sanctioned way to build the call
# so that shape cannot drift.

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from dune_winder.machine.geometry.uv_wrap_geometry import b_to_a_pin
from dune_winder.recipes.recipe_template_language import (
    RecipeTemplateLanguageError,
    TemplateInstruction,
    compile_template_script,
    execute_template_script,
)
from dune_winder.recipes.template_gcode_common import comb_pull

OFFSET_MODE_NATURAL = "natural"
OFFSET_MODE_XY = "xy"


@dataclass(frozen=True, eq=False)
class AnchorLayerAdapter:
    """The layer-specific half of an anchor template: one constant per layer."""

    layer: str
    line_builder: Callable[..., str]
    coord: Callable[[str, float], str]
    wrap_pin: Callable[[int], int]
    near_comb: Callable[[int], bool]
    annotate_wrap_lines: Callable[[int, list], list]
    offset_mode: str = OFFSET_MODE_XY
    offset_ids: Sequence[str] = ()
    offset_natural_axis: Mapping[str, str] = field(default_factory=dict)
    named_values: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, eq=False)
class AnchorScriptSections:
    """Compiled sections of one layer's anchor template.

    `wrap_tail` and `final_wrap_tail` are separate because the shared statement
    grammar has no `else` and no blocks -- a wrap whose ending differs on the
    last iteration cannot be expressed as a conditional inside `wrap`.
    A `None` section is skipped, never substituted for another.
    """

    preamble: tuple[TemplateInstruction, ...] = ()
    wrap: tuple[TemplateInstruction, ...] = ()
    wrap_tail: tuple[TemplateInstruction, ...] | None = None
    final_wrap_tail: tuple[TemplateInstruction, ...] | None = None
    postscript: tuple[TemplateInstruction, ...] = ()


def compile_anchor_script_sections(
    *,
    preamble=(),
    wrap=(),
    wrap_tail=None,
    final_wrap_tail=None,
    postscript=(),
):
    def compile_section(section):
        if section is None:
            return None
        return compile_template_script(section)

    return AnchorScriptSections(
        preamble=compile_template_script(preamble),
        wrap=compile_template_script(wrap),
        wrap_tail=compile_section(wrap_tail),
        final_wrap_tail=compile_section(final_wrap_tail),
        postscript=compile_template_script(postscript),
    )


def _offset_component(entry, axis):
    if isinstance(entry, dict):
        return float(entry.get(axis, 0.0))
    return float(entry)


def _base_environment(adapter, *, offsets, pull_ins):
    """Helpers that do not depend on the wrap number.

    Deliberately omits `wrap` and `n` so that a preamble or postscript
    statement referencing them fails loudly instead of rendering an empty
    string and silently shifting every downstream line number.
    """
    coord = adapter.coord
    layer = adapter.layer

    def wrap_pin(pin_number):
        return adapter.wrap_pin(pin_number)

    def b_pin(pin_number):
        return "B" + str(adapter.wrap_pin(pin_number))

    def a_from_b(pin_number):
        return b_to_a_pin(layer, b_pin(pin_number))

    def anchor(anchor_pin, target_pin, offset=None, hover=False, in_two_moves=False):
        # `offset` must stay immediately after the pins: offset_axis_policy's
        # regex anchors on that position and silently stops clamping the
        # off-axis component if anything is inserted before it.
        call = "~anchorToTarget(" + str(anchor_pin) + "," + str(target_pin)
        if offset is not None:
            offset_x = float(offset[0])
            offset_y = float(offset[1])
            if abs(offset_x) >= 1e-9 or abs(offset_y) >= 1e-9:
                call += (
                    ",offset=(" + coord("", offset_x) + "," + coord("", offset_y) + ")"
                )
        if hover:
            call += ",hover=True"
        if in_two_moves:
            call += ",inTwoMoves=True"
        return call + ")"

    def increment(delta_x, delta_y):
        return "~increment(" + coord("", delta_x) + "," + coord("", delta_y) + ")"

    def goto(x_position, y_position):
        return "~goto(" + coord("", x_position) + "," + coord("", y_position) + ")"

    def offset_xy(index):
        entry = offsets[index]
        if isinstance(entry, dict):
            return (float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
        return (float(entry), 0.0)

    def offset_natural(index):
        axis = adapter.offset_natural_axis.get(adapter.offset_ids[index], "x")
        value = _offset_component(offsets[index], axis)
        return (value, 0.0) if axis == "x" else (0.0, value)

    environment = {
        "offsets": offsets,
        "wrap_pin": wrap_pin,
        "b_pin": b_pin,
        "a_from_b": a_from_b,
        "near_comb": adapter.near_comb,
        "anchor": anchor,
        "increment": increment,
        "goto": goto,
        "coord": coord,
        "X_PULL_IN": pull_ins["X_PULL_IN"],
        "Y_PULL_IN": pull_ins["Y_PULL_IN"],
        "COMB_PULL": comb_pull(pull_ins["Y_PULL_IN"], pull_ins["HEAD_ARM_LENGTH"]),
    }
    if adapter.offset_mode == OFFSET_MODE_NATURAL:
        environment["offset_natural"] = offset_natural
    else:
        environment["offset_xy"] = offset_xy
    environment.update(adapter.named_values)
    return environment


def _emit_non_empty(output_lines, line, action):
    # An `emit` whose interpolations all render empty still appends a line.
    # That would shift every `(w,l)` identifier and every `N` number without
    # changing anything a reader would notice, so refuse it outright.
    if not str(line).strip():
        raise RecipeTemplateLanguageError(
            "Anchor template emitted an empty line (action " + repr(action) + ")."
        )
    output_lines.append(line)


def _execute_section(section, environment, adapter):
    lines = []
    if section:
        execute_template_script(
            section,
            environment=environment,
            output_lines=lines,
            line_builder=adapter.line_builder,
            transfers={},
            emit_callback=_emit_non_empty,
        )
    return lines


def render_anchor_layer_lines(
    sections,
    adapter,
    *,
    offsets,
    pull_ins,
    wrap_count,
):
    """Render one layer's wrapping G-Code, before any post-processing pass.

    The preamble and postscript are emitted without the `(w,l)` annotation, so
    only the per-wrap lines are addressable by `line_offset_overrides`.
    """
    base_environment = _base_environment(adapter, offsets=offsets, pull_ins=pull_ins)
    lines = _execute_section(sections.preamble, base_environment, adapter)

    for wrap_number in range(1, wrap_count + 1):
        environment = dict(base_environment)
        environment["wrap"] = wrap_number
        environment["n"] = wrap_number - 1

        wrap_lines = _execute_section(sections.wrap, environment, adapter)
        if wrap_number == wrap_count and sections.final_wrap_tail is not None:
            tail = sections.final_wrap_tail
        else:
            tail = sections.wrap_tail
        wrap_lines.extend(_execute_section(tail, environment, adapter))
        lines.extend(adapter.annotate_wrap_lines(wrap_number, wrap_lines))

    lines.extend(_execute_section(sections.postscript, base_environment, adapter))
    return lines
