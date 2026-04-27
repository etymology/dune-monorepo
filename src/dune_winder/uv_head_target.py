from __future__ import annotations

from .uv_head_target_parts.anchor_to_target import (
    _actual_wire_point_from_machine_target,
    _cached_compute_uv_anchor_to_target_view,
    _translated_point2,
    compute_uv_anchor_to_target_view,
    parse_anchor_to_target_command,
    translated_anchor_to_target_projection,
)
from .uv_head_target_parts.calibration import (
    _all_wire_space_pins,
    _cached_all_wire_space_pins,
    _load_layer_calibration,
    _load_machine_calibration,
    _location_to_point2,
    _location_to_point3,
    _wire_space_pin,
)
from .uv_head_target_parts.geometry2d import (
    _arm_correction_head_shift_signs,
    _arm_correction_tangent_y_side,
    _build_arm_geometry,
    _choose_outbound_intercept,
    _clip_infinite_line_to_bounds,
    _compute_arm_corrected_outbound,
    _distance_point_to_line,
    _dot_2d,
    _is_on_wrap_side,
    _length_2d,
    _line_deviation_at_point,
    _line_equation_from_tangent_points,
    _line_match,
    _matches_tangent_sides,
    _point_on_line,
    _roller_index_for_head_shift_signs,
    _roller_offset_for_index,
    _select_tangent_solution,
    _sign_with_epsilon,
    _subtract_2d,
    _tangent_candidates_for_pin_pair,
    matches_tangent_sides,
)
from .uv_head_target_parts.head_target import compute_uv_head_target
from .uv_head_target_parts.models import (
    AnchorToTargetCommand,
    AnchorToTargetViewResult,
    LineEquation,
    Point2D,
    Point3D,
    RecipeSite,
    RectBounds,
    UvHeadTargetError,
    UvHeadTargetRequest,
    UvHeadTargetResult,
    UvTangentViewRequest,
    UvTangentViewResult,
    WrappedPinResolution,
)
from .uv_head_target_parts.pin_layout import (
    _b_side_equivalent_pin,
    _b_side_face_for_pin,
    _default_layer_calibration_path,
    _derive_wrap_context,
    _face_for_pin,
    _format_tangent_sides,
    _normalize_head_z_mode,
    _normalize_layer,
    _normalize_pin_name,
    _pin_family_side,
    _pin_number,
    _wrap_context_for_pin,
    tangent_sides,
)
from .uv_head_target_parts.pin_pair_tangent import (
    PinPairTangentGeometry,
    _cached_compute_pin_pair_tangent_geometry,
    compute_pin_pair_tangent_geometry,
)
from .uv_head_target_parts.recipe_sites import (
    _infer_local_pair_pin_from_wrap_side,
    _infer_pair_pin_from_wrap_side,
    _lookup_recipe_site,
    _parse_site_label,
    _recipe_sites_by_anchor,
    _render_lines_for_layer,
    _strip_p_prefix,
    iter_uv_wrap_primary_sites,
    resolve_wrapped_pin_from_g103_pair,
)
from .uv_head_target_parts.runtime import (
    _execute_line,
    _initial_handler,
    _probe_runtime_orientation,
    _runtime_projection_points,
)
from .uv_head_target_parts.tangent_view import compute_uv_tangent_view


def clear_uv_head_target_caches(
    *, layer_calibration: bool = True, machine_calibration: bool = False
) -> None:
    if layer_calibration:
        _load_layer_calibration.cache_clear()
        _cached_all_wire_space_pins.cache_clear()
    if machine_calibration:
        _load_machine_calibration.cache_clear()
        _cached_compute_uv_anchor_to_target_view.cache_clear()
        _cached_compute_pin_pair_tangent_geometry.cache_clear()


__all__ = [
    "LineEquation",
    "PinPairTangentGeometry",
    "Point2D",
    "Point3D",
    "RecipeSite",
    "RectBounds",
    "AnchorToTargetCommand",
    "AnchorToTargetViewResult",
    "UvHeadTargetError",
    "UvHeadTargetRequest",
    "UvHeadTargetResult",
    "UvTangentViewRequest",
    "UvTangentViewResult",
    "WrappedPinResolution",
    "clear_uv_head_target_caches",
    "compute_pin_pair_tangent_geometry",
    "compute_uv_anchor_to_target_view",
    "compute_uv_head_target",
    "compute_uv_tangent_view",
    "iter_uv_wrap_primary_sites",
    "_lookup_recipe_site",
    "matches_tangent_sides",
    "parse_anchor_to_target_command",
    "resolve_wrapped_pin_from_g103_pair",
    "tangent_sides",
]
