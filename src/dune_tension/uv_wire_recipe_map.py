from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
import re

from dune_tension.layer_calibration import load_normalized_layer_calibration
from dune_tension.uv_wire_planner import wire_pin_pair
from dune_winder.machine.geometry.uv_layout import get_uv_layout
from dune_winder.recipes.u_template_gcode import (
    WRAP_COUNT as U_WRAP_COUNT,
    render_u_template_lines,
)
from dune_winder.recipes.v_template_gcode import (
    WRAP_COUNT as V_WRAP_COUNT,
    render_v_template_lines,
)

VALID_WIRE_MIN = 8
VALID_WIRE_MAX = 1146
CANONICAL_SEGMENT_LINES = (2, 6, 10, 14, 18, 22)

_WRAP_MARKER_RE = re.compile(r"\((\d+),(\d+)\)")
_TRAILING_COMMENT_RE = re.compile(r"\(([^()]*)\)\s*$")

_WRAP_COUNT_BY_LAYER = {
    "U": int(U_WRAP_COUNT),
    "V": int(V_WRAP_COUNT),
}

_WRAP_RENDERER_BY_LAYER = {
    "U": render_u_template_lines,
    "V": render_v_template_lines,
}

_SEGMENT_FORMULAS = {
    "V": (
        (1, 351),
        (-1, 1952),
        (1, 1151),
        (-1, 1152),
        (1, 1951),
        (-1, 352),
    ),
    "U": (
        (1, 751),
        (1, 1551),
        (1, -49),
        (-1, -49),
        (1, 1552),
        (-1, 752),
    ),
}


@dataclass(frozen=True)
class WireWrapRef:
    wrap_number: int
    segment_index: int
    segment_line: int
    segment_comment: str
    start_pin: str
    end_pin: str


@dataclass(frozen=True)
class UvWireRecipeMaps:
    layer: str
    wrap_to_wire_numbers: dict[int, list[int]]
    wire_to_wrap: dict[int, WireWrapRef]
    wire_to_applied_length_mm: dict[int, float]
    wire_to_endpoint_sides: dict[int, tuple[str, str]]


def _normalize_layer(layer: str) -> str:
    value = str(layer).strip().upper()
    if value not in {"U", "V"}:
        raise ValueError(f"Unsupported U/V layer {layer!r}.")
    return value


def _wire_number_for_segment(layer: str, segment_index: int, wrap_number: int) -> int:
    multiplier, offset = _SEGMENT_FORMULAS[layer][segment_index - 1]
    return (multiplier * int(wrap_number)) + offset


@lru_cache(maxsize=2)
def _canonical_segment_comments(layer: str) -> dict[int, str]:
    requested_layer = _normalize_layer(layer)
    comments: dict[int, str] = {}
    for line in _WRAP_RENDERER_BY_LAYER[requested_layer]():
        wrap_match = _WRAP_MARKER_RE.search(line)
        if wrap_match is None:
            continue
        wrap_number = int(wrap_match.group(1))
        segment_line = int(wrap_match.group(2))
        if wrap_number != 1 or segment_line not in CANONICAL_SEGMENT_LINES:
            continue
        comment_match = _TRAILING_COMMENT_RE.search(line)
        if comment_match is None:
            raise ValueError(
                f"Unable to extract canonical segment comment for layer {requested_layer} line {segment_line}."
            )
        comments[segment_line] = comment_match.group(1)
    missing = [line for line in CANONICAL_SEGMENT_LINES if line not in comments]
    if missing:
        raise ValueError(
            f"Missing canonical segment comments for layer {requested_layer}: {missing!r}."
        )
    return comments


@lru_cache(maxsize=2)
def _layer_metadata(layer: str) -> dict[str, object]:
    return get_uv_layout(_normalize_layer(layer)).legacy_metadata()


@lru_cache(maxsize=2)
def _layer_calibration(layer: str) -> dict[str, object]:
    return load_normalized_layer_calibration(_normalize_layer(layer))


def _pin_location_xyz(
    calibration: dict[str, object], pin_name: str
) -> tuple[float, float, float]:
    try:
        location = calibration["locations"][pin_name]
    except KeyError as exc:
        raise ValueError(
            f"Pin {pin_name} is not present in the calibration payload."
        ) from exc
    return (
        float(location["x"]),
        float(location["y"]),
        float(location.get("z", 0.0)),
    )


def build_wrap_to_wire_numbers(layer: str) -> dict[int, list[int]]:
    requested_layer = _normalize_layer(layer)
    wrap_count = _WRAP_COUNT_BY_LAYER[requested_layer]
    return {
        wrap_number: [
            _wire_number_for_segment(requested_layer, segment_index, wrap_number)
            for segment_index in range(1, len(CANONICAL_SEGMENT_LINES) + 1)
        ]
        for wrap_number in range(1, wrap_count + 1)
    }


def build_uv_wire_recipe_maps(layer: str) -> UvWireRecipeMaps:
    requested_layer = _normalize_layer(layer)
    comments = _canonical_segment_comments(requested_layer)
    layout = get_uv_layout(requested_layer)
    calibration = _layer_calibration(requested_layer)
    wrap_to_wire_numbers = build_wrap_to_wire_numbers(requested_layer)

    wire_to_wrap: dict[int, WireWrapRef] = {}
    wire_to_applied_length_mm: dict[int, float] = {}
    wire_to_endpoint_sides: dict[int, tuple[str, str]] = {}

    for wrap_number, wire_numbers in wrap_to_wire_numbers.items():
        for segment_index, wire_number in enumerate(wire_numbers, start=1):
            if wire_number < VALID_WIRE_MIN or wire_number > VALID_WIRE_MAX:
                continue
            if wire_number in wire_to_wrap:
                raise ValueError(
                    f"Wire {wire_number} is mapped multiple times for layer {requested_layer}."
                )

            segment_line = CANONICAL_SEGMENT_LINES[segment_index - 1]
            start_pin, end_pin = wire_pin_pair(requested_layer, wire_number)
            start_side = layout.face_for_pin(start_pin)
            end_side = layout.face_for_pin(end_pin)
            start_xyz = _pin_location_xyz(calibration, start_pin)
            end_xyz = _pin_location_xyz(calibration, end_pin)

            wire_to_wrap[wire_number] = WireWrapRef(
                wrap_number=int(wrap_number),
                segment_index=int(segment_index),
                segment_line=int(segment_line),
                segment_comment=comments[segment_line],
                start_pin=start_pin,
                end_pin=end_pin,
            )
            wire_to_applied_length_mm[wire_number] = float(
                math.dist(start_xyz, end_xyz)
            )
            wire_to_endpoint_sides[wire_number] = (start_side, end_side)

    missing_wires = [
        wire_number
        for wire_number in range(VALID_WIRE_MIN, VALID_WIRE_MAX + 1)
        if wire_number not in wire_to_wrap
    ]
    if missing_wires:
        raise ValueError(
            f"Missing wire mappings for layer {requested_layer}: {missing_wires[:10]!r}."
        )

    return UvWireRecipeMaps(
        layer=requested_layer,
        wrap_to_wire_numbers=wrap_to_wire_numbers,
        wire_to_wrap=wire_to_wrap,
        wire_to_applied_length_mm=wire_to_applied_length_mm,
        wire_to_endpoint_sides=wire_to_endpoint_sides,
    )


__all__ = [
    "CANONICAL_SEGMENT_LINES",
    "VALID_WIRE_MAX",
    "VALID_WIRE_MIN",
    "UvWireRecipeMaps",
    "WireWrapRef",
    "build_uv_wire_recipe_maps",
    "build_wrap_to_wire_numbers",
]
