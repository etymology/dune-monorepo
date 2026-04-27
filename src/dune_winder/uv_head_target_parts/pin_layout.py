from __future__ import annotations

from pathlib import Path

from dune_winder.machine.geometry.uv_layout import get_uv_layout

from .constants import (
    _DEFAULT_LAYER_CALIBRATION_DIRECTORIES,
    _PIN_NAME_RE,
)
from .models import Point2D, UvHeadTargetError


def _normalize_layer(layer: str) -> str:
    value = str(layer).strip().upper()
    if value not in {"U", "V"}:
        raise UvHeadTargetError("Layer must be 'U' or 'V'.")
    return value


def _normalize_head_z_mode(mode: str) -> str:
    value = str(mode).strip().lower()
    if value not in {"front", "back"}:
        raise UvHeadTargetError("Head Z mode must be 'front' or 'back'.")
    return value


def _normalize_pin_name(pin_name: str, label: str) -> str:
    value = str(pin_name).strip().upper()
    if not _PIN_NAME_RE.match(value):
        raise UvHeadTargetError(f"{label} must be a pin name like B1201 or A799.")
    if value.startswith("F"):
        value = "A" + value[1:]
    return value


def _default_layer_calibration_path(layer: str) -> Path:
    file_name = f"{layer}_Calibration.json"
    for directory in _DEFAULT_LAYER_CALIBRATION_DIRECTORIES:
        candidate = directory / file_name
        if candidate.exists():
            return candidate
    return _DEFAULT_LAYER_CALIBRATION_DIRECTORIES[0] / file_name


def _pin_number(pin_name: str) -> int:
    return int(str(pin_name)[1:])


def _derive_wrap_context(layer: str, wrapped_pin: str) -> tuple[str, str]:
    layout = get_uv_layout(layer)
    side = _pin_family_side(wrapped_pin)
    try:
        face = layout.face_for_pin(wrapped_pin)
    except ValueError as exc:
        raise UvHeadTargetError(
            f"Could not determine board metadata for wrapped pin {wrapped_pin} on layer {layer}."
        ) from exc
    return (side, face)


def _wrap_context_for_pin(
    layer: str, pin_name: str
) -> tuple[str, str, tuple[str, str]]:
    side, face = _derive_wrap_context(layer, pin_name)
    return (side, face, tangent_sides(layer, pin_name))


def _pin_family_side(pin_name: str) -> str:
    normalized_pin = _normalize_pin_name(pin_name, "Pin")
    return "B" if normalized_pin.startswith("B") else "A"


def _face_for_pin(layer: str, pin_name: str) -> str:
    try:
        return get_uv_layout(layer).face_for_pin(pin_name)
    except ValueError as exc:
        raise UvHeadTargetError(
            f"Could not determine board metadata for pin {pin_name} on layer {layer}."
        ) from exc


def _b_side_equivalent_pin(layer: str, pin_name: str) -> str:
    normalized_layer = _normalize_layer(layer)
    normalized_pin = _normalize_pin_name(pin_name, "Pin")
    return get_uv_layout(normalized_layer).translate_pin(
        normalized_pin,
        target_family="B",
    )


def _b_side_face_for_pin(layer: str, pin_name: str) -> str:
    return _face_for_pin(layer, _b_side_equivalent_pin(layer, pin_name))


def tangent_sides(layer: str, pin_name: str) -> tuple[str, str]:
    normalized_layer = _normalize_layer(layer)
    normalized_pin = _normalize_pin_name(pin_name, "Pin")
    try:
        return get_uv_layout(normalized_layer).tangent_sides(normalized_pin)
    except ValueError as exc:
        raise UvHeadTargetError(str(exc)) from exc


def _format_tangent_sides(tangent_sides_value: tuple[str, str] | None) -> str:
    if tangent_sides_value is None:
        return "n/a"
    x_side, y_side = tangent_sides_value
    return f"x={x_side}, y={y_side}"
