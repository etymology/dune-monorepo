from __future__ import annotations

import math
import pytest

from dune_winder.gcode.handler_base import GCodeHandlerBase
from dune_winder.gcode.runtime import execute_text_line
from dune_winder.machine.calibration.layer import LayerCalibration
from dune_winder.machine.calibration.machine import MachineCalibration
from dune_winder.machine.head_compensation import WirePathModel
from dune_winder.paths import REPO_ROOT
from dune_winder.uv_head_target import (
  Point2D,
  UvHeadTargetError,
  UvHeadTargetRequest,
  UvTangentViewRequest,
  _arm_correction_head_shift_signs,
  _arm_correction_tangent_y_side,
  _compute_arm_corrected_outbound,
  _distance_point_to_line,
  _roller_index_for_head_shift_signs,
  _roller_offset_for_index,
  _b_side_equivalent_pin,
  _is_on_wrap_side,
  _matches_tangent_sides,
  _default_layer_calibration_path,
  _infer_pair_pin_from_wrap_side,
  _lookup_recipe_site,
  _clip_infinite_line_to_bounds,
  _line_equation_from_tangent_points,
  _select_tangent_solution,
  _tangent_candidates_for_pin_pair,
  RectBounds,
  compute_uv_head_target,
  compute_uv_tangent_view,
  tangent_sides,
)


_LINE_RE = re.compile(r"G109\s+(P[AB]\d+)\s+P([A-Z]{2})\s+G103\s+(P[AB]\d+)\s+(P[AB]\d+)\s+PXY")


def _load_machine_calibration() -> MachineCalibration:
  calibration = MachineCalibration(str(REPO_ROOT / "dune_winder" / "config"), "machineCalibration.json")
  calibration.load()
  return calibration


def _load_layer_calibration(layer: str) -> LayerCalibration:
  path = _default_layer_calibration_path(layer)
  calibration = LayerCalibration(layer)
  calibration.load(str(path.parent), path.name, exceptionForMismatch=False)
  return calibration


def _make_handler(layer: str) -> GCodeHandlerBase:
  machine_calibration = _load_machine_calibration()
  layer_calibration = _load_layer_calibration(layer)
  handler = GCodeHandlerBase(machine_calibration, WirePathModel(machine_calibration))
  handler.useLayerCalibration(layer_calibration)
  handler._x = 0.0
  handler._y = 0.0
  handler._z = 0.0
  return handler


def test_compute_uv_head_target_matches_runtime_for_known_v_case():
  request = UvHeadTargetRequest(
    layer="V",
    anchor_pin="B400",
    wrapped_pin="B1999",
    head_z_mode="front",
  )
  result = compute_uv_head_target(request)
  handler = _make_handler("V")
  head_position = 1

  execute_text_line(f"G106 P{head_position}", handler._callbacks.get)
  execute_text_line("G109 PB400 PRT", handler._callbacks.get)
  execute_text_line("G103 PB1999 PB1998 PXY", handler._callbacks.get)
  midpoint_x = handler._x
  midpoint_y = handler._y
  execute_text_line("G102", handler._callbacks.get)
  transfer_x = handler._x
  transfer_y = handler._y
  effective_anchor = handler._headCompensation.compensatedAnchorPoint()
  execute_text_line("G108", handler._callbacks.get)
  head_z = handler._getHeadPosition(head_position)
  actual = handler._headCompensation.getActualLocation(
    handler._headCompensation.anchorPoint().copy(x=handler._x, y=handler._y, z=head_z)
  )

  assert result.orientation_token == "RT"
  assert result.inferred_pair_pin == "B1998"
  assert math.isclose(result.midpoint_point.x, midpoint_x)
  assert math.isclose(result.midpoint_point.y, midpoint_y)
  assert math.isclose(result.transfer_point.x, transfer_x)
  assert math.isclose(result.transfer_point.y, transfer_y)
  assert math.isclose(result.effective_anchor_point.x, effective_anchor.x)
  assert math.isclose(result.effective_anchor_point.y, effective_anchor.y)
  assert math.isclose(result.final_head_point.x, handler._x)
  assert math.isclose(result.final_head_point.y, handler._y)
  assert math.isclose(result.final_wire_point.x, actual.x)
  assert math.isclose(result.final_wire_point.y, actual.y)


def test_compute_uv_head_target_matches_runtime_for_second_known_v_case():
  request = UvHeadTargetRequest(
    layer="V",
    anchor_pin="F800",
    wrapped_pin="F1599",
    head_z_mode="front",
  )
  result = compute_uv_head_target(request)
  handler = _make_handler("V")
  execute_text_line("G106 P1", handler._callbacks.get)
  execute_text_line("G109 PF800 PRB", handler._callbacks.get)
  execute_text_line("G103 PF1599 PF1600 PXY", handler._callbacks.get)
  execute_text_line("G102", handler._callbacks.get)
  execute_text_line("G108", handler._callbacks.get)

  assert result.orientation_token == "RB"
  assert result.inferred_pair_pin == "F1600"
  assert result.request.layer == "V"
  assert result.validation_error is None
  assert math.isclose(result.final_head_point.x, handler._x)
  assert math.isclose(result.final_head_point.y, handler._y)


def test_tangent_sides_matches_requested_formula_examples():
  assert tangent_sides("U", "B1") == ("plus", "plus")
  assert tangent_sides("U", "A401") == ("plus", "minus")
  assert tangent_sides("V", "B1") == ("plus", "minus")
  assert tangent_sides("U", "A1201") == ("minus", "plus")
  assert tangent_sides("V", "B1600") == ("plus", "minus")


def test_b_side_equivalent_pin_uses_closed_form_correspondence():
  assert _b_side_equivalent_pin("U", "A400") == "B1"
  assert _b_side_equivalent_pin("U", "A399") == "B2"
  assert _b_side_equivalent_pin("U", "A2401") == "B401"
  assert _b_side_equivalent_pin("V", "A399") == "B1"
  assert _b_side_equivalent_pin("V", "A398") == "B2"
  assert _b_side_equivalent_pin("V", "A2399") == "B400"


def test_lookup_recipe_site_resolves_anchor_and_wrapped_pin():
  calibration = _load_layer_calibration("U")
  site = _lookup_recipe_site("U", calibration, "B1201", "B2001")

  assert site.orientation_token == "BR"
  assert site.side == "B"
  assert site.position == "top"
  assert site.site_label == "Top B corner - foot end"


def test_infer_pair_pin_from_wrap_side_matches_known_u_case():
  calibration = _load_layer_calibration("U")
  inferred = _infer_pair_pin_from_wrap_side(calibration, "PB2001", ("minus", "minus"))
  assert inferred == "PB2005"


def test_infer_pair_pin_from_wrap_side_matches_known_v_case():
  calibration = _load_layer_calibration("V")
  inferred = _infer_pair_pin_from_wrap_side(calibration, "PB1998", ("plus", "minus"))
  assert inferred == "PB1992"


def test_compute_uv_head_target_rejects_bad_pin_format():
  with pytest.raises(UvHeadTargetError, match="Anchor pin must be a pin name"):
    compute_uv_head_target(
      UvHeadTargetRequest(
        layer="U",
        anchor_pin="1201",
        wrapped_pin="B2002",
        head_z_mode="front",
      )
    )


def test_compute_uv_head_target_rejects_unknown_pin():
  with pytest.raises(UvHeadTargetError, match="not present"):
    compute_uv_head_target(
      UvHeadTargetRequest(
        layer="U",
        anchor_pin="B99999",
        wrapped_pin="B2002",
        head_z_mode="front",
      )
    )


def test_default_layer_calibration_path_prefers_dune_winder_copy_for_u():
  path = _default_layer_calibration_path("U")

  assert path == REPO_ROOT / "dune_winder" / "config" / "APA" / "U_Calibration.json"


def test_default_layer_calibration_path_prefers_dune_winder_copy_for_v():
  path = _default_layer_calibration_path("V")

  assert path == REPO_ROOT / "dune_winder" / "config" / "APA" / "V_Calibration.json"


@pytest.mark.parametrize(
  ("layer", "pin_a", "pin_b"),
  (
    ("U", "B1201", "B2001"),
    ("U", "A1201", "A2001"),
    ("U", "B1201", "A1201"),
    ("V", "B2001", "A800"),
  ),
)
def test_compute_uv_tangent_view_accepts_any_calibrated_pin_pair(layer, pin_a, pin_b):
  result = compute_uv_tangent_view(UvTangentViewRequest(layer=layer, pin_a=pin_a, pin_b=pin_b))

  assert result.request == UvTangentViewRequest(layer=layer, pin_a=pin_a, pin_b=pin_b)
  assert result.pin_a_point.x != result.pin_b_point.x or result.pin_a_point.y != result.pin_b_point.y
  assert result.apa_bounds.left <= min(result.pin_a_point.x, result.pin_b_point.x)
  assert result.apa_bounds.right >= max(result.pin_a_point.x, result.pin_b_point.x)


@pytest.mark.parametrize(
  ("layer", "pin_a", "pin_b"),
  (
    ("U", "B1201", "B2001"),
    ("U", "A1201", "A2001"),
  ),
)
def test_compute_uv_tangent_view_returns_valid_tangent_geometry(layer, pin_a, pin_b):
  result = compute_uv_tangent_view(UvTangentViewRequest(layer=layer, pin_a=pin_a, pin_b=pin_b))

  radius_a = math.hypot(
    result.tangent_point_a.x - result.pin_a_point.x,
    result.tangent_point_a.y - result.pin_a_point.y,
  )
  radius_b = math.hypot(
    result.tangent_point_b.x - result.pin_b_point.x,
    result.tangent_point_b.y - result.pin_b_point.y,
  )
  tangent_direction = (
    result.tangent_point_b.x - result.tangent_point_a.x,
    result.tangent_point_b.y - result.tangent_point_a.y,
  )
  radial_a = (
    result.tangent_point_a.x - result.pin_a_point.x,
    result.tangent_point_a.y - result.pin_a_point.y,
  )
  radial_b = (
    result.tangent_point_b.x - result.pin_b_point.x,
    result.tangent_point_b.y - result.pin_b_point.y,
  )

  assert math.isclose(radius_a, result.pin_radius, rel_tol=1e-9, abs_tol=1e-6)
  assert math.isclose(radius_b, result.pin_radius, rel_tol=1e-9, abs_tol=1e-6)
  assert math.isclose(
    tangent_direction[0] * radial_a[0] + tangent_direction[1] * radial_a[1],
    0.0,
    abs_tol=1e-6,
  )
  assert math.isclose(
    tangent_direction[0] * radial_b[0] + tangent_direction[1] * radial_b[1],
    0.0,
    abs_tol=1e-6,
  )
  intercept = result.outbound_intercept
  bounds = result.transfer_bounds
  assert (
    math.isclose(intercept.x, bounds.left, abs_tol=1e-6)
    or math.isclose(intercept.x, bounds.right, abs_tol=1e-6)
    or math.isclose(intercept.y, bounds.bottom, abs_tol=1e-6)
    or math.isclose(intercept.y, bounds.top, abs_tol=1e-6)
  )


def test_compute_uv_tangent_view_uses_wrap_side_for_recipe_valid_pair():
  result = compute_uv_tangent_view(UvTangentViewRequest(layer="U", pin_a="B1201", pin_b="B2001"))

  assert result.anchor_side == "B"
  assert result.anchor_face == "foot"
  assert result.anchor_tangent_sides == ("minus", "minus")
  assert result.wrapped_side == "B"
  assert result.wrapped_face == "top"
  assert result.wrap_sides == ("minus", "minus")
  assert _matches_tangent_sides(
    result.tangent_point_a,
    Point2D(result.pin_a_point.x, result.pin_a_point.y),
    result.anchor_tangent_sides,
  )
  assert _matches_tangent_sides(
    result.tangent_point_b,
    Point2D(result.pin_b_point.x, result.pin_b_point.y),
    result.wrap_sides,
  )


def test_compute_uv_tangent_view_derives_wrap_side_for_f_pin():
  result = compute_uv_tangent_view(UvTangentViewRequest(layer="U", pin_a="B2001", pin_b="A800"))

  assert result.anchor_side == "B"
  assert result.anchor_face == "top"
  assert result.anchor_tangent_sides == ("minus", "minus")
  assert result.wrapped_side == "A"
  assert result.wrapped_face == "top"
  assert result.wrap_sides == ("plus", "minus")
  assert _matches_tangent_sides(
    result.tangent_point_a,
    Point2D(result.pin_a_point.x, result.pin_a_point.y),
    result.anchor_tangent_sides,
  )
  assert _matches_tangent_sides(
    result.tangent_point_b,
    Point2D(result.pin_b_point.x, result.pin_b_point.y),
    result.wrap_sides,
  )


def test_tangent_candidate_selection_allows_different_anchor_and_target_sides():
  candidates = _tangent_candidates_for_pin_pair(
    Point2D(0.0, 0.0),
    Point2D(10.0, 0.0),
    1.0,
  )

  tangent_point_a, tangent_point_b, _, _ = _select_tangent_solution(
    candidates,
    RectBounds(left=-20.0, top=20.0, right=20.0, bottom=-20.0),
    anchor_pin_point=Point2D(0.0, 0.0),
    anchor_tangent_sides=("minus", "minus"),
    wrapped_pin_point=Point2D(10.0, 0.0),
    wrapped_tangent_sides=("plus", "plus"),
  )

  assert _matches_tangent_sides(
    tangent_point_a,
    Point2D(0.0, 0.0),
    ("minus", "minus"),
  )
  assert _matches_tangent_sides(
    tangent_point_b,
    Point2D(10.0, 0.0),
    ("plus", "plus"),
  )


def test_compute_uv_tangent_view_includes_runtime_comparison_for_recipe_pair():
  result = compute_uv_tangent_view(UvTangentViewRequest(layer="U", pin_a="B1201", pin_b="B2001"))

  assert result.runtime_orientation_token is not None
  assert result.runtime_tangent_point is not None
  assert result.runtime_target_point is not None
  assert result.runtime_line_equation is not None
  assert result.runtime_clipped_segment_start is not None
  assert result.runtime_clipped_segment_end is not None
  assert result.runtime_outbound_intercept is not None
  assert result.matches_runtime_line in {True, False}


def test_compute_uv_tangent_view_uses_machine_calibration_pin_radius():
  result = compute_uv_tangent_view(UvTangentViewRequest(layer="U", pin_a="B1201", pin_b="B2001"))
  machine_calibration = _load_machine_calibration()

  assert math.isclose(
    result.pin_radius,
    float(machine_calibration.pinDiameter) / 2.0,
    rel_tol=1e-9,
    abs_tol=1e-9,
  )


def test_compute_uv_tangent_view_probes_runtime_orientation_for_non_recipe_pair():
  result = compute_uv_tangent_view(UvTangentViewRequest(layer="U", pin_a="B1201", pin_b="A1201"))

  assert result.runtime_orientation_token is not None
  assert result.runtime_tangent_point is not None
  assert result.runtime_target_point is not None
  assert result.runtime_outbound_intercept is not None
  assert (
    math.isclose(result.runtime_outbound_intercept.x, result.transfer_bounds.left, abs_tol=1e-6)
    or math.isclose(result.runtime_outbound_intercept.x, result.transfer_bounds.right, abs_tol=1e-6)
    or math.isclose(result.runtime_outbound_intercept.y, result.transfer_bounds.bottom, abs_tol=1e-6)
    or math.isclose(result.runtime_outbound_intercept.y, result.transfer_bounds.top, abs_tol=1e-6)
  )


def test_compute_uv_tangent_view_preserves_explicit_adjacent_pin():
  request = UvTangentViewRequest(
    layer="U",
    pin_a="B401",
    pin_b="B400",
    g103_adjacent_pin="B399",
  )

  result = compute_uv_tangent_view(request)

  assert result.request == request
  assert result.runtime_target_point is not None
  assert result.runtime_target_point.x < 1000.0


def test_compute_uv_tangent_view_prefers_nearby_local_adjacent_pin_for_runtime_probe():
  result = compute_uv_tangent_view(UvTangentViewRequest(layer="V", pin_a="A1", pin_b="A2398"))

  assert result.runtime_target_point is not None
  assert result.runtime_target_point.x < 1000.0


def test_compute_uv_tangent_view_builds_alternating_projection_for_yz_face():
  result = compute_uv_tangent_view(UvTangentViewRequest(layer="U", pin_a="B1201", pin_b="A1201"))

  assert result.alternating_plane == "yz"
  assert result.alternating_face == "foot"
  assert result.alternating_anchor_center is not None
  assert result.alternating_wrapped_center is not None
  assert result.alternating_anchor_segment_start is not None
  assert result.alternating_anchor_segment_end is not None
  assert result.alternating_wrapped_segment_start is not None
  assert result.alternating_wrapped_segment_end is not None
  assert result.alternating_g109_projection is not None
  assert result.alternating_g103_projection is not None
  assert result.alternating_g108_projection is None
  assert math.isclose(result.alternating_wrap_line_start.x, result.z_retracted, abs_tol=1e-6)
  assert math.isclose(result.alternating_wrap_line_end.x, result.z_extended, abs_tol=1e-6)
  assert math.isclose(
    abs(result.alternating_anchor_segment_end.y - result.alternating_anchor_segment_start.y),
    result.pin_radius * 2.0,
    abs_tol=1e-6,
  )


def test_compute_uv_tangent_view_builds_alternating_projection_for_xz_face():
  result = compute_uv_tangent_view(UvTangentViewRequest(layer="U", pin_a="B2001", pin_b="A800"))

  assert result.alternating_plane == "xz"
  assert result.alternating_face == "top"
  assert result.alternating_g108_projection is None
  assert math.isclose(result.alternating_wrap_line_start.y, result.z_retracted, abs_tol=1e-6)
  assert math.isclose(result.alternating_wrap_line_end.y, result.z_extended, abs_tol=1e-6)
  assert math.isclose(
    abs(result.alternating_anchor_segment_end.x - result.alternating_anchor_segment_start.x),
    result.pin_radius * 2.0,
    abs_tol=1e-6,
  )


def test_compute_uv_tangent_view_rejects_mixed_pair_on_different_faces():
  with pytest.raises(UvHeadTargetError, match="same face after converting the A pin to the B side"):
    compute_uv_tangent_view(UvTangentViewRequest(layer="U", pin_a="B1201", pin_b="A2001"))


def test_compute_uv_tangent_view_returns_arm_geometry_from_machine_config():
  result = compute_uv_tangent_view(UvTangentViewRequest(layer="U", pin_a="B1201", pin_b="B2001"))
  machine_calibration = _load_machine_calibration()

  assert result.arm_head_center is not None
  assert result.arm_left_endpoint is not None
  assert result.arm_right_endpoint is not None
  assert len(result.roller_centers) == 4
  assert math.isclose(result.head_arm_length, float(machine_calibration.headArmLength), abs_tol=1e-9)
  assert math.isclose(result.head_roller_radius, float(machine_calibration.headRollerRadius), abs_tol=1e-9)
  assert math.isclose(result.head_roller_gap, float(machine_calibration.headRollerGap), abs_tol=1e-9)
  assert math.isclose(
    result.arm_head_center.x - result.arm_left_endpoint.x,
    result.head_arm_length,
    abs_tol=1e-9,
  )
  assert math.isclose(
    result.arm_right_endpoint.x - result.arm_head_center.x,
    result.head_arm_length,
    abs_tol=1e-9,
  )
  expected_y_offset = (result.head_roller_gap / 2.0) + result.head_roller_radius
  assert {
    round(abs(roller.y - result.arm_head_center.y), 6)
    for roller in result.roller_centers
  } == {round(expected_y_offset, 6)}


@pytest.mark.parametrize(
  ("anchor_point", "target_point", "tangent_y_side"),
  (
    (Point2D(0.0, 0.0), Point2D(-1.0, -1.0), 1),
    (Point2D(0.0, 0.0), Point2D(-1.0, 1.0), -1),
    (Point2D(0.0, 0.0), Point2D(1.0, -1.0), 1),
    (Point2D(0.0, 0.0), Point2D(1.0, 1.0), -1),
  ),
)
def test_arm_correction_tangent_side_follows_pin_y_ordering(
  anchor_point, target_point, tangent_y_side
):
  assert _arm_correction_tangent_y_side(
    anchor_pin_point=anchor_point,
    target_pin_point=target_point,
  ) == tangent_y_side


@pytest.mark.parametrize(
  ("anchor_point", "target_point", "head_shift_signs", "roller_index"),
  (
    (Point2D(0.0, 0.0), Point2D(-1.0, -1.0), (-1, -1), 0),
    (Point2D(0.0, 0.0), Point2D(-1.0, 1.0), (-1, 1), 1),
    (Point2D(0.0, 0.0), Point2D(1.0, -1.0), (1, -1), 2),
    (Point2D(0.0, 0.0), Point2D(1.0, 1.0), (1, 1), 3),
  ),
)
def test_arm_correction_head_shift_signs_follow_anchor_to_target_direction(
  anchor_point, target_point, head_shift_signs, roller_index
):
  assert _arm_correction_head_shift_signs(
    anchor_pin_point=anchor_point,
    target_pin_point=target_point,
  ) == head_shift_signs
  assert _roller_index_for_head_shift_signs(*head_shift_signs) == roller_index


@pytest.mark.parametrize(
  ("anchor_point", "target_point"),
  (
    (Point2D(0.0, 0.0), Point2D(1.0, 0.0)),
    (Point2D(0.0, 0.0), Point2D(0.0, 1.0)),
  ),
)
def test_arm_correction_pin_direction_is_unavailable_on_axes(anchor_point, target_point):
  assert (
    _arm_correction_head_shift_signs(
      anchor_pin_point=anchor_point,
      target_pin_point=target_point,
    )
    is None
  )


def test_compute_arm_corrected_outbound_returns_transfer_edge_point_for_selected_quarter_arc():
  head_arm_length = 6.0
  head_roller_radius = 1.0
  head_roller_gap = 1.0
  corrected_outbound, corrected_head_center, roller_index, quadrant = (
    _compute_arm_corrected_outbound(
      anchor_pin_point=Point2D(0.0, 0.0),
      target_pin_point=Point2D(10.0, 10.0),
      tangent_point_a=Point2D(0.0, 0.0),
      tangent_point_b=Point2D(10.0, 10.0),
      transfer_bounds=RectBounds(left=-20.0, top=20.0, right=20.0, bottom=-20.0),
      head_arm_length=head_arm_length,
      head_roller_radius=head_roller_radius,
      head_roller_gap=head_roller_gap,
    )
  )

  assert quadrant == "NE"
  assert roller_index == 3
  assert corrected_outbound == corrected_head_center
  assert (
    math.isclose(corrected_outbound.x, 20.0, abs_tol=1e-6)
    or math.isclose(corrected_outbound.y, 20.0, abs_tol=1e-6)
  )
  roller_offset = _roller_offset_for_index(
    roller_index,
    head_arm_length=head_arm_length,
    head_roller_radius=head_roller_radius,
    head_roller_gap=head_roller_gap,
  )
  roller_center = Point2D(
    corrected_head_center.x + roller_offset.x,
    corrected_head_center.y + roller_offset.y,
  )
  assert math.isclose(
    _distance_point_to_line(
      roller_center,
      line_point=Point2D(0.0, 0.0),
      line_direction=Point2D(10.0, 10.0),
    ),
    head_roller_radius,
    abs_tol=1e-6,
  )


def test_compute_arm_corrected_outbound_rejects_indeterminate_quadrant():
  with pytest.raises(UvHeadTargetError, match="pin direction is indeterminate"):
    _compute_arm_corrected_outbound(
      anchor_pin_point=Point2D(0.0, 0.0),
      target_pin_point=Point2D(2.0, 0.0),
      tangent_point_a=Point2D(0.0, 0.0),
      tangent_point_b=Point2D(2.0, 0.0),
      transfer_bounds=RectBounds(left=-20.0, top=20.0, right=20.0, bottom=-20.0),
      head_arm_length=6.0,
      head_roller_radius=1.0,
      head_roller_gap=1.0,
    )


def test_compute_uv_tangent_view_includes_arm_corrected_overlay_for_same_side_pair():
  result = compute_uv_tangent_view(UvTangentViewRequest(layer="U", pin_a="B1201", pin_b="B2001"))

  assert result.outbound_intercept is not None
  assert result.arm_corrected_available is True
  assert result.arm_corrected_outbound_point is not None
  assert result.arm_corrected_head_center is not None
  assert result.arm_corrected_selected_roller_index is not None
  assert result.arm_corrected_quadrant in {"NW", "NE", "SW", "SE"}
  assert result.arm_corrected_error is None
  assert (
    math.isclose(result.arm_corrected_outbound_point.x, result.transfer_bounds.left, abs_tol=1e-6)
    or math.isclose(result.arm_corrected_outbound_point.x, result.transfer_bounds.right, abs_tol=1e-6)
    or math.isclose(result.arm_corrected_outbound_point.y, result.transfer_bounds.bottom, abs_tol=1e-6)
    or math.isclose(result.arm_corrected_outbound_point.y, result.transfer_bounds.top, abs_tol=1e-6)
  )


def test_compute_uv_tangent_view_marks_arm_correction_unavailable_when_quadrant_is_indeterminate():
  result = compute_uv_tangent_view(UvTangentViewRequest(layer="U", pin_a="B1201", pin_b="A1201"))

  assert result.arm_corrected_available is False
  assert result.arm_corrected_outbound_point is None
  assert result.arm_corrected_head_center is None
  assert result.arm_corrected_selected_roller_index is None
  assert result.arm_corrected_quadrant is None
  assert result.arm_corrected_error is None


def test_clip_infinite_line_to_bounds_handles_vertical_line():
  clipped = _clip_infinite_line_to_bounds(
    Point2D(5.0, 5.0),
    Point2D(0.0, 1.0),
    RectBounds(left=0.0, right=10.0, bottom=0.0, top=20.0),
  )

  assert clipped == (Point2D(5.0, 0.0), Point2D(5.0, 20.0))


def test_clip_infinite_line_to_bounds_handles_non_vertical_line():
  clipped = _clip_infinite_line_to_bounds(
    Point2D(5.0, 5.0),
    Point2D(1.0, 1.0),
    RectBounds(left=0.0, right=10.0, bottom=0.0, top=20.0),
  )

  assert clipped == (Point2D(0.0, 0.0), Point2D(10.0, 10.0))


def test_compute_uv_tangent_view_rejects_same_pin():
  with pytest.raises(UvHeadTargetError, match="must be different pins"):
    compute_uv_tangent_view(UvTangentViewRequest(layer="U", pin_a="B1201", pin_b="B1201"))


def test_line_equation_reports_vertical_line():
  line = _line_equation_from_tangent_points(Point2D(7.0, 1.0), Point2D(7.0, 9.0))

  assert line.is_vertical is True
  assert math.isinf(line.slope)
  assert math.isclose(line.intercept, 7.0)
