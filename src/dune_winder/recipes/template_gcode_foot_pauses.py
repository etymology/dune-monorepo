from __future__ import annotations

import re

from dune_winder.gcode.renderer import normalize_line_text
from dune_winder.machine.geometry.uv_layout import get_uv_layout
from dune_winder.machine.geometry.uv_wrap_geometry import Point2D
from dune_winder.machine.geometry.uv_wrap_geometry import tangent_sides


# Capture the anchor/target pins only; trailing keyword args (offset=(...),
# inTwoMoves=True, hover=...) describe how the move runs, not where the wire
# lands, so the match deliberately stops after the target pin.
_ANCHOR_TO_TARGET_RE = re.compile(
    r"~anchorToTarget\((?P<anchor>[PAB]\d+),(?P<target>[PAB]\d+)"
)
_SIDE_EPSILON = 1e-9
_FOOT_FACE = "foot"


def _normalize_pin_name(pin_name: str) -> str:
    value = str(pin_name).strip().upper()
    if value.startswith("P"):
        value = value[1:]
    return value


def _split_trailing_comments(line):
    body = str(line).rstrip()
    comments = []
    while True:
        match = re.search(r"\s+(\([^()]*\))\s*$", body)
        if match is None:
            break
        comments.insert(0, match.group(1))
        body = body[: match.start()].rstrip()
    return body, comments


def _append_command_before_trailing_comments(line, command):
    body, comments = _split_trailing_comments(line)
    if body.endswith(" " + command) or body == command:
        return str(line)
    if comments:
        return normalize_line_text(" ".join([body, command] + comments))
    return normalize_line_text(body + " " + command)


def _pin_point(layout, pin_name: str) -> Point2D:
    normalized_pin = _normalize_pin_name(pin_name)
    pin_locations = layout.nominal_positions()
    point = pin_locations.get(normalized_pin)
    if point is None:
        raise ValueError(f"Unknown pin {pin_name!r} for layer {layout.layer}.")
    return Point2D(float(point.x), float(point.y))


def _is_on_wrap_side(point: Point2D, center: Point2D, axis: str, side: str) -> bool:
    delta = (point.x - center.x) if axis == "x" else (point.y - center.y)
    if side == "plus":
        return delta > _SIDE_EPSILON
    return delta < -_SIDE_EPSILON


def _adjacent_pins_on_wrap_y_side(layout, target_pin: str) -> list[str]:
    """Same-family neighbours (n-1 / n+1) on the target's wrap side in Y.

    After the head wraps the target pin, the wire is laid off the pin on the
    side picked out by the pin's tangent orientation.  The neighbouring pin
    sitting on that side in the Y direction is the pin the wire is carried
    toward; that is the second pin of the "between two pins" the wire ends up
    spanning.
    """
    family = target_pin[:1]
    number = int(target_pin[1:])
    target_point = _pin_point(layout, target_pin)
    y_side = tangent_sides(layout.layer, target_pin)[1]
    adjacents = []
    for adjacent_number in (number - 1, number + 1):
        if adjacent_number < 1 or adjacent_number > layout.pin_max:
            continue
        adjacent_pin = f"{family}{adjacent_number}"
        if _is_on_wrap_side(
            _pin_point(layout, adjacent_pin), target_point, "y", y_side
        ):
            adjacents.append(adjacent_pin)
    return adjacents


def should_add_anchor_to_target_foot_pause(
    layer: str, anchor_pin: str, target_pin: str
) -> bool:
    """Whether an ~anchorToTarget should carry a foot board-gap pause.

    The decision is made entirely from the target pin.  Wrapping it lays the
    wire toward the neighbour on the pin's tangent Y side.  When the target is
    a board endpoint and that neighbour belongs to a different board -- with
    either side of the gap on the foot face -- the wire is placed across a
    foot board gap and the operator needs a pause.  The anchor pin does not
    affect where the wire lands and is ignored.
    """
    _ = anchor_pin
    layout = get_uv_layout(layer)
    target = _normalize_pin_name(target_pin)

    target_physical = int(layout.physical_pin_number(target))
    if target_physical not in set(layout.endpoint_pins):
        return False

    pin_to_board = layout.pin_to_board
    target_board = pin_to_board.get(target_physical)
    if target_board is None:
        return False

    for adjacent in _adjacent_pins_on_wrap_y_side(layout, target):
        adjacent_board = pin_to_board.get(int(layout.physical_pin_number(adjacent)))
        if adjacent_board is None:
            continue
        if adjacent_board.board_index == target_board.board_index:
            continue
        if _FOOT_FACE in (target_board.face, adjacent_board.face):
            return True
    return False


def apply_anchor_to_target_foot_pauses(lines, *, layer: str):
    layout = get_uv_layout(layer)
    updated_lines = []
    for line in lines:
        match = _ANCHOR_TO_TARGET_RE.search(str(line))
        if match is None:
            updated_lines.append(line)
            continue

        anchor_pin = _normalize_pin_name(match.group("anchor"))
        target_pin = _normalize_pin_name(match.group("target"))
        if should_add_anchor_to_target_foot_pause(
            layout.layer,
            anchor_pin,
            target_pin,
        ):
            updated_lines.append(
                _append_command_before_trailing_comments(line, "G111 (board gap)")
            )
            continue

        updated_lines.append(line)
    return updated_lines
