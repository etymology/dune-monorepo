from __future__ import annotations

from dataclasses import dataclass
import logging
import math
from typing import Any

from dune_tension.config import GEOMETRY_CONFIG
from dune_tension.geometry import length_lookup, zone_lookup
from dune_tension.layer_calibration import (
    get_laser_offset,
    load_layer_calibration_summary,
)
from dune_tension.tensiometer_functions import PlannedWirePose, WirePositionProvider
from dune_winder.core.manual_calibration import _build_layer_metadata

LOGGER = logging.getLogger(__name__)

_EPSILON = 1e-9

_WRAP_X_SIGNS = {
    "V": {
        "A": {"top": -1, "foot": -1, "head": 1, "bottom": 1},
        "B": {"top": 1, "foot": -1, "bottom": -1, "head": 1},
    },
    "U": {
        "A": {"foot": -1, "head": 1, "top": 1, "bottom": -1},
        "B": {"foot": -1, "head": 1, "top": -1, "bottom": 1},
    },
}


@dataclass(frozen=True)
class PlannedUVWire:
    wire_number: int
    pin_a: str
    pin_b: str
    tangent_a: tuple[float, float]
    tangent_b: tuple[float, float]
    interval_start: tuple[float, float]
    interval_end: tuple[float, float]
    midpoint: tuple[float, float]
    zone: int
    wire_length_m: float


def _normalize_layer(layer: str) -> str:
    value = str(layer).strip().upper()
    if value not in {"U", "V"}:
        raise ValueError(f"Unsupported U/V layer {layer!r}.")
    return value


def _normalize_side(side: str) -> str:
    value = str(side).strip().upper()
    if value not in {"A", "B"}:
        raise ValueError(f"Unsupported side {side!r}.")
    return value


def _wrap_inclusive(value: int, low: int, high: int) -> int:
    span = int(high) - int(low) + 1
    return int(low) + ((int(value) - int(low)) % span)


def _wire_pin_pair(layer: str, wire_number: int) -> tuple[str, str]:
    requested_layer = _normalize_layer(layer)
    number = int(wire_number)
    delta = 1151 - number
    if requested_layer == "V":
        return (
            f"B{_wrap_inclusive(1199 - delta, 1, 2399)}",
            f"B{_wrap_inclusive(1200 + delta, 1, 2399)}",
        )
    return (
        f"B{_wrap_inclusive(1600 - delta, 1, 2401)}",
        f"B{_wrap_inclusive(1601 + delta, 1, 2401)}",
    )


def _vector_sub(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return (float(a[0] - b[0]), float(a[1] - b[1]))


def _vector_add(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return (float(a[0] + b[0]), float(a[1] + b[1]))


def _vector_scale(a: tuple[float, float], factor: float) -> tuple[float, float]:
    return (float(a[0] * factor), float(a[1] * factor))


def _vector_dot(a: tuple[float, float], b: tuple[float, float]) -> float:
    return float(a[0] * b[0] + a[1] * b[1])


def _vector_length(a: tuple[float, float]) -> float:
    return float(math.hypot(a[0], a[1]))


def _sign(value: float) -> int:
    if value > _EPSILON:
        return 1
    if value < -_EPSILON:
        return -1
    return 0


def _clip_line_to_rectangle(
    point_a: tuple[float, float],
    point_b: tuple[float, float],
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    x0, y0 = float(point_a[0]), float(point_a[1])
    x1, y1 = float(point_b[0]), float(point_b[1])
    dx = x1 - x0
    dy = y1 - y0
    if abs(dx) <= _EPSILON and abs(dy) <= _EPSILON:
        return None

    t0 = float("-inf")
    t1 = float("inf")

    def _update(p: float, q: float) -> bool:
        nonlocal t0, t1
        if abs(p) <= _EPSILON:
            return q >= 0.0
        r = q / p
        if p < 0.0:
            if r > t1:
                return False
            if r > t0:
                t0 = r
            return True
        if r < t0:
            return False
        if r < t1:
            t1 = r
        return True

    if not _update(-dx, x0 - GEOMETRY_CONFIG.measurable_x_min):
        return None
    if not _update(dx, GEOMETRY_CONFIG.measurable_x_max - x0):
        return None
    if not _update(-dy, y0 - GEOMETRY_CONFIG.measurable_y_min):
        return None
    if not _update(dy, GEOMETRY_CONFIG.measurable_y_max - y0):
        return None
    if t1 < t0:
        return None
    return (
        (x0 + (dx * t0), y0 + (dy * t0)),
        (x0 + (dx * t1), y0 + (dy * t1)),
    )


def _split_segment_at_combs(
    start: tuple[float, float],
    end: tuple[float, float],
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    x0, y0 = float(start[0]), float(start[1])
    x1, y1 = float(end[0]), float(end[1])
    if abs(x1 - x0) <= _EPSILON:
        return [(start, end)]

    boundaries = [0.0, 1.0]
    lower_x = min(x0, x1)
    upper_x = max(x0, x1)
    for comb_x in GEOMETRY_CONFIG.comb_positions:
        if comb_x <= lower_x + _EPSILON or comb_x >= upper_x - _EPSILON:
            continue
        t_value = (float(comb_x) - x0) / (x1 - x0)
        if _EPSILON < t_value < 1.0 - _EPSILON:
            boundaries.append(float(t_value))
    boundaries = sorted(set(boundaries))

    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for left, right in zip(boundaries, boundaries[1:]):
        if right - left <= _EPSILON:
            continue
        seg0 = (x0 + ((x1 - x0) * left), y0 + ((y1 - y0) * left))
        seg1 = (x0 + ((x1 - x0) * right), y0 + ((y1 - y0) * right))
        segments.append((seg0, seg1))
    return segments


def _segment_length(segment: tuple[tuple[float, float], tuple[float, float]]) -> float:
    return _vector_length(_vector_sub(segment[1], segment[0]))


def _segment_midpoint(segment: tuple[tuple[float, float], tuple[float, float]]) -> tuple[float, float]:
    return (
        float((segment[0][0] + segment[1][0]) / 2.0),
        float((segment[0][1] + segment[1][1]) / 2.0),
    )


def _solve_tangent_candidates(
    *,
    center_a: tuple[float, float],
    center_b: tuple[float, float],
    tangent_x_sign_a: int,
    tangent_x_sign_b: int,
    radius_mm: float,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    delta = _vector_sub(center_b, center_a)
    distance = _vector_length(delta)
    if distance <= _EPSILON:
        raise ValueError("Cannot plan a tangent for coincident pin centers.")

    direction = _vector_scale(delta, 1.0 / distance)
    perpendicular = (-direction[1], direction[0])
    candidates: list[tuple[tuple[float, float], tuple[float, float]]] = []

    for normal_x_sign in (-1, 1):
        distance_sign_a = -int(tangent_x_sign_a) * int(normal_x_sign)
        distance_sign_b = -int(tangent_x_sign_b) * int(normal_x_sign)
        projection = float(radius_mm * (distance_sign_b - distance_sign_a))
        if abs(projection) > distance + _EPSILON:
            continue
        along = projection / distance
        across_sq = max(0.0, 1.0 - (along * along))
        across = math.sqrt(across_sq)
        base = _vector_scale(direction, along)
        for orientation in (-1.0, 1.0):
            normal = _vector_add(base, _vector_scale(perpendicular, across * orientation))
            if _sign(normal[0]) != normal_x_sign:
                continue
            tangent_a = _vector_sub(center_a, _vector_scale(normal, distance_sign_a * radius_mm))
            tangent_b = _vector_sub(center_b, _vector_scale(normal, distance_sign_b * radius_mm))
            if _sign(tangent_a[0] - center_a[0]) != int(tangent_x_sign_a):
                continue
            if _sign(tangent_b[0] - center_b[0]) != int(tangent_x_sign_b):
                continue
            candidates.append((tangent_a, tangent_b))
    return candidates


def plan_uv_wire(layer: str, side: str, wire_number: int, *, taped: bool = False) -> PlannedUVWire:
    requested_layer = _normalize_layer(layer)
    requested_side = _normalize_side(side)
    calibration = load_layer_calibration_summary(requested_layer)
    offset = get_laser_offset(requested_side)
    if offset is None:
        raise ValueError(f"No saved laser offset exists for side {requested_side}.")

    pin_a, pin_b = _wire_pin_pair(requested_layer, int(wire_number))
    locations = calibration["locations"]
    center_a = (float(locations[pin_a]["x"]), float(locations[pin_a]["y"]))
    center_b = (float(locations[pin_b]["x"]), float(locations[pin_b]["y"]))
    pin_radius_mm = float(calibration.get("pinDiameterMm", 0.0)) / 2.0
    metadata = _build_layer_metadata(requested_layer)
    pin_side_a = metadata["pinToBoard"][int(pin_a[1:])]["side"]
    pin_side_b = metadata["pinToBoard"][int(pin_b[1:])]["side"]
    tangent_sign_a = _WRAP_X_SIGNS[requested_layer][requested_side][pin_side_a]
    tangent_sign_b = _WRAP_X_SIGNS[requested_layer][requested_side][pin_side_b]

    best_segment: tuple[tuple[float, float], tuple[float, float]] | None = None
    best_tangent_a: tuple[float, float] | None = None
    best_tangent_b: tuple[float, float] | None = None
    best_length = -1.0
    best_midpoint_y = float("inf")
    for tangent_a, tangent_b in _solve_tangent_candidates(
        center_a=center_a,
        center_b=center_b,
        tangent_x_sign_a=tangent_sign_a,
        tangent_x_sign_b=tangent_sign_b,
        radius_mm=pin_radius_mm,
    ):
        clipped = _clip_line_to_rectangle(tangent_a, tangent_b)
        if clipped is None:
            continue
        length = _segment_length(clipped)
        midpoint = _segment_midpoint(clipped)
        if (
            length > best_length + _EPSILON
            or (
                math.isclose(length, best_length, rel_tol=0.0, abs_tol=_EPSILON)
                and midpoint[1] < best_midpoint_y
            )
        ):
            best_segment = clipped
            best_tangent_a = tangent_a
            best_tangent_b = tangent_b
            best_length = length
            best_midpoint_y = midpoint[1]

    if best_segment is None or best_tangent_a is None or best_tangent_b is None:
        raise ValueError(
            f"Unable to plan a measurable U/V segment for layer={requested_layer} side={requested_side} wire={wire_number}."
        )

    midpoint = _segment_midpoint(best_segment)
    laser_midpoint = (
        float(midpoint[0] - float(offset["x"])),
        float(midpoint[1] - float(offset["y"])),
    )
    zone = zone_lookup(laser_midpoint[0])
    wire_length_m = length_lookup(
        requested_layer,
        int(wire_number),
        zone,
        taped=bool(taped),
    )
    return PlannedUVWire(
        wire_number=int(wire_number),
        pin_a=pin_a,
        pin_b=pin_b,
        tangent_a=best_tangent_a,
        tangent_b=best_tangent_b,
        interval_start=(
            float(best_segment[0][0] - float(offset["x"])),
            float(best_segment[0][1] - float(offset["y"])),
        ),
        interval_end=(
            float(best_segment[1][0] - float(offset["x"])),
            float(best_segment[1][1] - float(offset["y"])),
        ),
        midpoint=laser_midpoint,
        zone=int(zone),
        wire_length_m=float(wire_length_m),
    )


class LegacyUVWirePositionProvider:
    """Use the U/V pin planner and fall back to the historical provider elsewhere."""

    def __init__(self, fallback_provider: WirePositionProvider | None = None) -> None:
        self._fallback_provider = fallback_provider or WirePositionProvider()

    def invalidate(self) -> None:
        self._fallback_provider.invalidate()

    def get_pose(self, config, wire_number: int, current_focus_position: int | None = None):
        if str(config.layer).upper() not in {"U", "V"}:
            return self._fallback_provider.get_pose(config, wire_number, current_focus_position)
        try:
            planned = plan_uv_wire(
                str(config.layer).upper(),
                str(config.side).upper(),
                int(wire_number),
                taped=False,
            )
        except Exception as exc:
            LOGGER.warning("U/V legacy planner failed for wire %s: %s", wire_number, exc)
            return None
        return PlannedWirePose(
            wire_number=int(wire_number),
            x=float(planned.midpoint[0]),
            y=float(planned.midpoint[1]),
            focus_position=None if current_focus_position is None else int(current_focus_position),
        )

    def get_xy(self, config, wire_number: int):
        pose = self.get_pose(config, wire_number)
        if pose is None:
            return None
        return (float(pose.x), float(pose.y))
