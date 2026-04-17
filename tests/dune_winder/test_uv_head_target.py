from __future__ import annotations

import math
import re

import pytest

from dune_winder.gcode.handler_base import GCodeHandlerBase
from dune_winder.gcode.runtime import execute_text_line
from dune_winder.machine.calibration.layer import LayerCalibration
from dune_winder.machine.calibration.machine import MachineCalibration
from dune_winder.machine.head_compensation import WirePathModel
from dune_winder.paths import REPO_ROOT
from dune_winder.recipes.u_template_gcode import render_u_template_lines
from dune_winder.recipes.v_template_gcode import render_v_template_lines
from dune_winder.uv_head_target import (
  UvHeadTargetError,
  UvHeadTargetRequest,
  _infer_pair_pin_from_wrap_side,
  _lookup_recipe_site,
  compute_uv_head_target,
  wrap_side,
)


_LINE_RE = re.compile(r"G109\s+(P[BF]\d+)\s+P([A-Z]{2})\s+G103\s+(P[BF]\d+)\s+(P[BF]\d+)\s+PXY")


def _load_machine_calibration() -> MachineCalibration:
  calibration = MachineCalibration(str(REPO_ROOT / "dune_winder" / "config"), "machineCalibration.json")
  calibration.load()
  return calibration


def _load_layer_calibration(layer: str) -> LayerCalibration:
  calibration = LayerCalibration(layer)
  calibration.load(str(REPO_ROOT / "config" / "APA"), f"{layer}_Calibration.json", exceptionForMismatch=False)
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


def _first_valid_request(layer: str) -> tuple[UvHeadTargetRequest, str, str]:
  lines = render_u_template_lines(strip_g113_params=True) if layer == "U" else render_v_template_lines(strip_g113_params=True)
  for line in lines:
    match = _LINE_RE.search(line)
    if match is None:
      continue
    anchor_pin, orientation, wrapped_pin, target_pin = match.groups()
    for head_z_mode in ("front", "back"):
      request = UvHeadTargetRequest(
        layer=layer,
        anchor_pin=anchor_pin[1:],
        wrapped_pin=wrapped_pin[1:],
        head_z_mode=head_z_mode,
      )
      try:
        result = compute_uv_head_target(request)
      except Exception:
        continue
      return (request, orientation, target_pin[1:])
  raise AssertionError(f"No valid {layer} request found in rendered recipe.")


def test_compute_uv_head_target_matches_runtime_for_first_valid_u_case():
  request, orientation, pair_pin = _first_valid_request("U")
  result = compute_uv_head_target(request)
  handler = _make_handler("U")
  head_position = 1 if request.head_z_mode == "front" else 2

  execute_text_line(f"G106 P{head_position}", handler._callbacks.get)
  execute_text_line(f"G109 P{request.anchor_pin} P{orientation}", handler._callbacks.get)
  execute_text_line(f"G103 P{request.wrapped_pin} P{pair_pin} PXY", handler._callbacks.get)
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

  assert result.orientation_token == orientation
  assert result.inferred_pair_pin == pair_pin
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


def test_compute_uv_head_target_matches_runtime_for_first_valid_v_case():
  request, orientation, pair_pin = _first_valid_request("V")
  result = compute_uv_head_target(request)
  handler = _make_handler("V")
  head_position = 1 if request.head_z_mode == "front" else 2
  execute_text_line(f"G106 P{head_position}", handler._callbacks.get)
  execute_text_line(f"G109 P{request.anchor_pin} P{orientation}", handler._callbacks.get)
  execute_text_line(f"G103 P{request.wrapped_pin} P{pair_pin} PXY", handler._callbacks.get)
  execute_text_line("G102", handler._callbacks.get)
  execute_text_line("G108", handler._callbacks.get)

  assert result.orientation_token == orientation
  assert result.inferred_pair_pin == pair_pin
  assert result.request.layer == "V"
  assert result.validation_error is None
  assert math.isclose(result.final_head_point.x, handler._x)
  assert math.isclose(result.final_head_point.y, handler._y)


def test_wrap_side_matches_requested_formula_examples():
  assert wrap_side("U", "B", "top") == "-x"
  assert wrap_side("U", "A", "top") == "+x"
  assert wrap_side("V", "B", "top") == "+x"
  assert wrap_side("U", "A", "foot") == "+y"
  assert wrap_side("V", "B", "foot") == "-y"


def test_lookup_recipe_site_resolves_anchor_and_wrapped_pin():
  site = _lookup_recipe_site("U", "PB1201", "PB2001")

  assert site.orientation_token == "BR"
  assert site.side == "B"
  assert site.position == "top"
  assert site.site_label == "Top B corner - foot end"


def test_infer_pair_pin_from_wrap_side_matches_known_u_case():
  calibration = _load_layer_calibration("U")
  inferred = _infer_pair_pin_from_wrap_side(calibration, "PB2001", "-x")
  assert inferred == "PB2002"


def test_infer_pair_pin_from_wrap_side_matches_known_v_case():
  calibration = _load_layer_calibration("V")
  inferred = _infer_pair_pin_from_wrap_side(calibration, "PB1998", "+x")
  assert inferred == "PB1999"


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
