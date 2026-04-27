from __future__ import annotations

import re

from dune_winder.gcode.renderer import normalize_line_text
from dune_winder.machine.geometry.uv_layout import get_uv_layout
from dune_winder.machine.geometry.uv_wrap_geometry import Point2D, b_to_a_pin
from dune_winder.machine.geometry.uv_wrap_geometry import tangent_sides


_ANCHOR_TO_TARGET_RE = re.compile(
    r"~anchorToTarget\((?P<anchor>[PAB]\d+),(?P<target>[PAB]\d+)"
    r"(?:,(?:offset=\([^)]+\)|hover=(?:True|False|1|0|yes|no|on|off))){0,2}\)"
)
_SIDE_EPSILON = 1e-9


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


def _physical_endpoint_number(layout, pin_name: str) -> int:
    normalized_pin = _normalize_pin_name(pin_name)
    translated_pin = b_to_a_pin(layout.layer, normalized_pin)
    return int(layout.physical_pin_number(translated_pin))


def _is_on_wrap_side(point: Point2D, center: Point2D, axis: str, side: str) -> bool:
    delta = (point.x - center.x) if axis == "x" else (point.y - center.y)
    if side == "plus":
        return delta > _SIDE_EPSILON
    return delta < -_SIDE_EPSILON


def _is_anchor_adjacent_to_target(layout, anchor_pin: str, target_pin: str) -> bool:
    target_point = _pin_point(layout, target_pin)
    anchor_point = _pin_point(layout, anchor_pin)
    target_sides = tangent_sides(layout.layer, _normalize_pin_name(target_pin))
    return _is_on_wrap_side(
        anchor_point, target_point, "x", target_sides[0]
    ) or _is_on_wrap_side(anchor_point, target_point, "y", target_sides[1])


def should_add_anchor_to_target_foot_pause(
    layer: str, anchor_pin: str, target_pin: str
) -> bool:
    layout = get_uv_layout(layer)
    anchor_normalized = _normalize_pin_name(anchor_pin)
    target_normalized = _normalize_pin_name(target_pin)

    if anchor_normalized == target_normalized:
        return False
    if not _is_anchor_adjacent_to_target(layout, anchor_normalized, target_normalized):
        return False

    endpoint_pins = set(layout.endpoint_pins)
    anchor_endpoint = _physical_endpoint_number(layout, anchor_normalized)
    target_endpoint = _physical_endpoint_number(layout, target_normalized)
    return anchor_endpoint in endpoint_pins and target_endpoint in endpoint_pins


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
            updated_lines.append(_append_command_before_trailing_comments(line, "G111"))
            continue

        updated_lines.append(line)
    return updated_lines
