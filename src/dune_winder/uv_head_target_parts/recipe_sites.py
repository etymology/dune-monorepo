from __future__ import annotations

from functools import lru_cache
import math
from pathlib import Path

from dune_winder.machine.calibration.layer import LayerCalibration
from dune_winder.recipes.u_template_gcode import (
    iter_u_wrap_primary_sites,
    render_u_template_lines,
)
from dune_winder.recipes.v_template_gcode import (
    iter_v_wrap_primary_sites,
    render_v_template_lines,
)

from .calibration import _load_layer_calibration, _location_to_point2, _wire_space_pin
from .constants import _AXIS_EPSILON, _RECIPE_SITE_RE
from .geometry2d import _is_on_wrap_side
from .models import Point2D, RecipeSite, UvHeadTargetError, WrappedPinResolution
from .pin_layout import (
    _derive_wrap_context,
    _face_for_pin,
    _format_tangent_sides,
    _normalize_layer,
    _normalize_pin_name,
    _pin_number,
    tangent_sides,
)


def _parse_site_label(site_label: str) -> tuple[str, str]:
    label = str(site_label).strip().lower()
    if " a " in f" {label} ":
        side = "A"
    elif " b " in f" {label} ":
        side = "B"
    else:
        raise UvHeadTargetError(f"Could not determine site side from {site_label!r}.")

    for position in ("top", "bottom", "head", "foot"):
        if position in label:
            return (side, position)
    raise UvHeadTargetError(f"Could not determine site position from {site_label!r}.")


def _strip_p_prefix(pin_name: str) -> str:
    value = str(pin_name).strip().upper()
    if value.startswith("P"):
        return value[1:]
    return value


def _render_lines_for_layer(layer: str) -> list[str]:
    if layer == "U":
        return render_u_template_lines(strip_g113_params=True)
    return render_v_template_lines(strip_g113_params=True)


def iter_uv_wrap_primary_sites(
    layer: str,
    *,
    named_inputs=None,
    special_inputs=None,
    cell_overrides=None,
):
    normalized_layer = _normalize_layer(layer)
    if normalized_layer == "U":
        return iter_u_wrap_primary_sites(
            named_inputs=named_inputs,
            special_inputs=special_inputs,
            cell_overrides=cell_overrides,
        )
    return iter_v_wrap_primary_sites(
        named_inputs=named_inputs,
        special_inputs=special_inputs,
        cell_overrides=cell_overrides,
    )


@lru_cache(maxsize=2)
def _recipe_sites_by_anchor(layer: str) -> dict[str, list[RecipeSite]]:
    result: dict[str, list[RecipeSite]] = {}
    for line in _render_lines_for_layer(layer):
        match = _RECIPE_SITE_RE.search(line)
        if match is None:
            continue
        anchor_pin, orientation_token, pair_pin_a, pair_pin_b, site_label = (
            match.groups()
        )
        anchor_pin = _strip_p_prefix(anchor_pin)
        pair_pin_a = _strip_p_prefix(pair_pin_a)
        pair_pin_b = _strip_p_prefix(pair_pin_b)
        side, position = _parse_site_label(site_label)
        candidate = RecipeSite(
            anchor_pin=anchor_pin,
            orientation_token=orientation_token,
            recipe_pair_pin_a=pair_pin_a,
            recipe_pair_pin_b=pair_pin_b,
            site_label=site_label,
            side=side,
            position=position,
        )
        result.setdefault(anchor_pin, []).append(candidate)
    return result


def _lookup_recipe_site(layer: str, *args) -> RecipeSite:
    if len(args) == 2:
        anchor_pin, wrapped_pin = args
    elif len(args) == 3:
        _layer_calibration, anchor_pin, wrapped_pin = args
    else:
        raise TypeError("_lookup_recipe_site expects layer plus anchor/wrapped pins.")
    normalized_layer = _normalize_layer(layer)
    normalized_anchor_pin = _strip_p_prefix(
        _normalize_pin_name(anchor_pin, "Anchor pin")
    )
    normalized_wrapped_pin = _strip_p_prefix(
        _normalize_pin_name(wrapped_pin, "Wrapped pin")
    )

    candidates = _recipe_sites_by_anchor(normalized_layer).get(
        normalized_anchor_pin, []
    )
    if not candidates:
        raise UvHeadTargetError(
            f"No recipe site found for anchor pin {normalized_anchor_pin} in layer {normalized_layer}."
        )

    for candidate in candidates:
        if normalized_wrapped_pin in {
            candidate.recipe_pair_pin_a,
            candidate.recipe_pair_pin_b,
        }:
            return candidate

    raise UvHeadTargetError(
        f"No recipe site found for anchor pin {normalized_anchor_pin} and wrapped pin {normalized_wrapped_pin} in layer {normalized_layer}."
    )


def _infer_pair_pin_from_wrap_side(
    layer_calibration: LayerCalibration,
    wrapped_pin: str,
    tangent_sides_value: tuple[str, str],
) -> str:
    wrapped_pin_name = (
        wrapped_pin[1:] if str(wrapped_pin).upper().startswith("P") else wrapped_pin
    )
    wrapped_location = _wire_space_pin(layer_calibration, wrapped_pin_name)
    wrapped_face = _face_for_pin(layer_calibration.getLayerNames(), wrapped_pin_name)
    same_face_pins = [
        pin_name
        for pin_name in layer_calibration.getPinNames()
        if (
            pin_name.startswith(wrapped_pin_name[0])
            and pin_name != wrapped_pin_name
            and _face_for_pin(layer_calibration.getLayerNames(), pin_name)
            == wrapped_face
        )
    ]
    if not same_face_pins:
        raise UvHeadTargetError(f"No same-face candidate pins found for {wrapped_pin}.")

    best_pin = None
    best_score = None
    x_sign = 1.0 if tangent_sides_value[0] == "plus" else -1.0

    def candidate_specs():
        for pin_name in same_face_pins:
            location = _wire_space_pin(layer_calibration, pin_name)
            delta_x = float(location.x - wrapped_location.x)
            delta_y = float(location.y - wrapped_location.y)
            signed_x = x_sign * delta_x
            if signed_x <= _AXIS_EPSILON:
                continue
            yield (pin_name, signed_x, abs(delta_y))

    candidates = list(candidate_specs())
    if candidates:
        local_pitch_x = min(spec[1] for spec in candidates)
    else:
        local_pitch_x = 0.0
    local_min_signed_x = local_pitch_x * 4.0
    local_max_signed_x = local_pitch_x * 12.0
    preferred_candidates = [
        spec
        for spec in candidates
        if local_min_signed_x - 1e-6 <= spec[1] <= local_max_signed_x + 1e-6
    ]

    for pin_name, signed_x, abs_delta_y in preferred_candidates or candidates:
        score = (abs_delta_y, signed_x)
        if best_score is None or score < best_score:
            best_score = score
            best_pin = pin_name

    if best_pin is None:
        raise UvHeadTargetError(
            "Could not infer the second G103 pin from wrapped pin "
            f"{wrapped_pin} and tangent sides {_format_tangent_sides(tangent_sides_value)}."
        )

    if str(wrapped_pin).upper().startswith("P"):
        return f"P{best_pin}"
    return best_pin


def _infer_local_pair_pin_from_wrap_side(
    layer_calibration: LayerCalibration,
    wrapped_pin: str,
    tangent_sides_value: tuple[str, str],
) -> str:
    wrapped_pin_label = str(wrapped_pin).strip().upper()
    wrapped_pin_name = (
        wrapped_pin[1:] if str(wrapped_pin).upper().startswith("P") else wrapped_pin
    )
    wrapped_location = _wire_space_pin(layer_calibration, wrapped_pin_name)
    family_pins = [
        pin_name
        for pin_name in layer_calibration.getPinNames()
        if pin_name.startswith(wrapped_pin_name[0]) and pin_name != wrapped_pin_name
    ]
    if not family_pins:
        raise UvHeadTargetError(
            f"No same-family candidate pins found for {wrapped_pin}."
        )

    def best_match(candidate_pins: list[str]) -> str | None:
        best_pin = None
        best_score = None
        wrapped_point = Point2D(float(wrapped_location.x), float(wrapped_location.y))
        for pin_name in candidate_pins:
            location = _wire_space_pin(layer_calibration, pin_name)
            delta_x = float(location.x - wrapped_location.x)
            delta_y = float(location.y - wrapped_location.y)
            candidate_point = Point2D(float(location.x), float(location.y))
            x_match = _is_on_wrap_side(
                candidate_point,
                wrapped_point,
                "x",
                tangent_sides_value[0],
            )
            y_match = _is_on_wrap_side(
                candidate_point,
                wrapped_point,
                "y",
                tangent_sides_value[1],
            )
            if not (x_match or y_match):
                continue
            match_count = int(x_match) + int(y_match)
            orthogonal_error = min(
                abs(delta_y) if x_match else math.inf,
                abs(delta_x) if y_match else math.inf,
            )
            distance = math.hypot(delta_x, delta_y)
            pin_number_gap = abs(_pin_number(pin_name) - _pin_number(wrapped_pin_name))
            score = (
                pin_number_gap,
                orthogonal_error,
                distance,
                -match_count,
            )
            if best_score is None or score < best_score:
                best_score = score
                best_pin = pin_name
        return best_pin

    wrapped_face = _face_for_pin(layer_calibration.getLayerNames(), wrapped_pin_name)
    same_face_pins = [
        pin_name
        for pin_name in family_pins
        if _face_for_pin(layer_calibration.getLayerNames(), pin_name) == wrapped_face
    ]
    best_pin = best_match(same_face_pins) or best_match(family_pins)
    if best_pin is None:
        raise UvHeadTargetError(
            "Could not infer a nearby G103 pair pin from wrapped pin "
            f"{wrapped_pin} and tangent sides {_format_tangent_sides(tangent_sides_value)}."
        )
    if wrapped_pin_label.startswith("P"):
        return f"P{best_pin}"
    if wrapped_pin_label.startswith("F"):
        return f"F{best_pin[1:]}"
    return best_pin


def resolve_wrapped_pin_from_g103_pair(
    layer: str,
    g103_pin_a: str,
    g103_pin_b: str,
    *,
    layer_calibration_path: str | Path | None = None,
    preferred_wrapped_pin: str | None = None,
) -> WrappedPinResolution:
    normalized_layer = _normalize_layer(layer)
    candidate_a = _normalize_pin_name(g103_pin_a, "G103 pin A")
    candidate_b = _normalize_pin_name(g103_pin_b, "G103 pin B")
    preferred_candidate = None
    if preferred_wrapped_pin is not None:
        preferred_candidate = _normalize_pin_name(
            preferred_wrapped_pin, "Preferred wrapped pin"
        )
    if candidate_a == candidate_b:
        raise UvHeadTargetError("G103 pin pair must contain two different pins.")
    if candidate_a[:1] != candidate_b[:1]:
        raise UvHeadTargetError(
            f"G103 pin pair must be same-side; got {candidate_a} and {candidate_b}."
        )

    layer_calibration = _load_layer_calibration(
        normalized_layer,
        layer_calibration_path,
    )
    geometric_matches: list[WrappedPinResolution] = []
    inferred_matches: list[WrappedPinResolution] = []
    for wrapped_candidate, adjacent_candidate in (
        (candidate_a, candidate_b),
        (candidate_b, candidate_a),
    ):
        wrapped_side, wrapped_face = _derive_wrap_context(
            normalized_layer, wrapped_candidate
        )
        tangent_sides_value = tangent_sides(normalized_layer, wrapped_candidate)
        wrapped_point = _location_to_point2(
            _wire_space_pin(layer_calibration, wrapped_candidate)
        )
        adjacent_point = _location_to_point2(
            _wire_space_pin(layer_calibration, adjacent_candidate)
        )
        if _is_on_wrap_side(
            adjacent_point, wrapped_point, "x", tangent_sides_value[0]
        ) or _is_on_wrap_side(
            adjacent_point, wrapped_point, "y", tangent_sides_value[1]
        ):
            geometric_matches.append(
                WrappedPinResolution(
                    wrapped_pin=wrapped_candidate,
                    adjacent_pin=adjacent_candidate,
                    wrap_sides=tangent_sides_value,
                )
            )
        inferred_adjacent = _infer_pair_pin_from_wrap_side(
            layer_calibration,
            wrapped_candidate,
            tangent_sides_value,
        )
        if inferred_adjacent == adjacent_candidate:
            inferred_matches.append(
                WrappedPinResolution(
                    wrapped_pin=wrapped_candidate,
                    adjacent_pin=adjacent_candidate,
                    wrap_sides=tangent_sides_value,
                )
            )

    if len(geometric_matches) == 1:
        return geometric_matches[0]
    if len(geometric_matches) != 1 and len(inferred_matches) == 1:
        return inferred_matches[0]
    if preferred_candidate is not None:
        ordered_matches = geometric_matches or inferred_matches
        preferred_matches = [
            match
            for match in ordered_matches
            if match.wrapped_pin == preferred_candidate
        ]
        if len(preferred_matches) == 1:
            return preferred_matches[0]
    if not geometric_matches and not inferred_matches:
        raise UvHeadTargetError(
            "Could not resolve wrapped pin from G103 pair "
            f"{candidate_a}/{candidate_b} on layer {normalized_layer}."
        )
    raise UvHeadTargetError(
        "Ambiguous wrapped pin from G103 pair "
        f"{candidate_a}/{candidate_b} on layer {normalized_layer}."
    )
