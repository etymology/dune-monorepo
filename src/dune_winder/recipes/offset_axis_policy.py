###############################################################################
# Name: offset_axis_policy.py
# Uses: Restrict ~anchorToTarget / corner offsets to the natural axis of the
#       pin's placement and quantise them to 0.1 mm.
# Date: 2026-05-20
###############################################################################
"""Natural-axis policy for wrap offsets.

A wrap offset only makes physical sense along the axis the pin's face runs in:
the head and foot faces run along Y, the top and bottom faces run along X.  A
component on the *other* axis would push the wire off the face, so it is forced
to zero.  Surviving components are quantised to the nearest 0.1 mm, with values
under 0.1 mm treated as zero; an offset whose components are both zero is
dropped entirely rather than rendered as ``offset=(0,0)``.

The same rules drive three things so they can never drift apart:
  * the editable corner offsets on the GCode Generation page (per offset id),
  * the per-line overrides captured by jog calibration / the machine-geometry
    solver (per target pin),
  * a final pass over generated G-code, which re-derives the axis from each
    ``~anchorToTarget`` target pin and is also used to migrate existing files.
"""

from __future__ import annotations

import re

from dune_winder.machine.geometry.uv_layout import get_uv_layout
from dune_winder.recipes.line_offset_overrides import format_number


# Which machine axis an offset is allowed to move the pin along, by face.
NATURAL_AXIS_BY_FACE = {
    "top": "x",
    "bottom": "x",
    "foot": "y",
    "head": "y",
}

# Offsets are quantised to this grid; anything smaller in magnitude is zero.
OFFSET_GRID_MM = 0.1
_EPSILON = 1e-9

_PIN_NUMBER_RE = re.compile(r"-?\d+")
# Matches the offset rendered immediately after the two pins of an
# ~anchorToTarget call.  The offset components are plain decimals (no nested
# parens), so a flat capture is safe and leaves any trailing keyword args
# (inTwoMoves=..., hover=...) untouched.
_ANCHOR_OFFSET_RE = re.compile(
    r"(~anchorToTarget\([ABP]\d+,(?P<target>[ABP]\d+)),"
    r"offset=\((?P<x>-?\d*\.?\d+),(?P<y>-?\d*\.?\d+)\)"
)


def round_to_tenth(value) -> float:
    """Quantise to the nearest 0.1 mm; treat magnitudes under 0.1 mm as zero."""
    number = float(value)
    if abs(number) < OFFSET_GRID_MM:
        return 0.0
    rounded = round(number, 1)
    return 0.0 if rounded == 0.0 else rounded


def enforce_offset_axes(x, y, natural_axis):
    """Return ``(x, y)`` with the off-axis component zeroed and the on-axis
    component quantised.  An unknown ``natural_axis`` leaves both at zero."""
    on_x = round_to_tenth(x) if natural_axis == "x" else 0.0
    on_y = round_to_tenth(y) if natural_axis == "y" else 0.0
    return (on_x, on_y)


def enforce_offset_dict(value, natural_axis) -> dict:
    """Coerce a scalar or ``{x, y}`` offset to a quantised natural-axis dict.

    Scalars are taken to lie on the natural axis (legacy behaviour).
    """
    if isinstance(value, dict):
        raw_x = float(value.get("x", 0.0))
        raw_y = float(value.get("y", 0.0))
    else:
        scalar = float(value)
        raw_x = scalar if natural_axis == "x" else 0.0
        raw_y = scalar if natural_axis == "y" else 0.0
    on_x, on_y = enforce_offset_axes(raw_x, raw_y, natural_axis)
    return {"x": on_x, "y": on_y}


def natural_axis_for_pin(layer, pin):
    """Natural offset axis (``"x"`` or ``"y"``) for the pin's face, or ``None``.

    Accepts a pin token (``"A799"``, ``"B400"``, ``"P12"``) or a bare number;
    the family letter does not change the face the pin sits on.
    """
    match = _PIN_NUMBER_RE.search(str(pin))
    if match is None:
        return None
    try:
        layout = get_uv_layout(layer)
        face = layout.face_for_pin(layout.physical_pin_number(int(match.group(0))))
    except Exception:
        return None
    return NATURAL_AXIS_BY_FACE.get(face)


def enforce_offset_natural_axis(lines, *, layer):
    """Normalise every ``~anchorToTarget`` offset in ``lines`` for ``layer``.

    Each offset is forced onto its target pin's natural axis, quantised to
    0.1 mm, and dropped entirely when both components vanish.  Lines without a
    recognisable target pin are left untouched.  Operates purely on text, so
    the same call serves both the generator and one-shot migration of existing
    recipe files.
    """

    def replace(match):
        natural_axis = natural_axis_for_pin(layer, match.group("target"))
        if natural_axis is None:
            return match.group(0)
        on_x, on_y = enforce_offset_axes(
            float(match.group("x")), float(match.group("y")), natural_axis
        )
        if abs(on_x) < _EPSILON and abs(on_y) < _EPSILON:
            return match.group(1)
        return (
            match.group(1)
            + ",offset=("
            + format_number(on_x)
            + ","
            + format_number(on_y)
            + ")"
        )

    return [_ANCHOR_OFFSET_RE.sub(replace, str(line)) for line in lines]


__all__ = [
    "NATURAL_AXIS_BY_FACE",
    "OFFSET_GRID_MM",
    "round_to_tenth",
    "enforce_offset_axes",
    "enforce_offset_dict",
    "natural_axis_for_pin",
    "enforce_offset_natural_axis",
]
