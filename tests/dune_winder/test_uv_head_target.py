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
  UvHeadTargetError,
  UvHeadTargetRequest,
  _infer_pair_pin_from_wrap_side,
  _lookup_recipe_site,
  compute_uv_head_target,
  wrap_side,
)


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


def test_wrap_side_matches_requested_formula_examples():
  assert wrap_side("U", "B", "top") == "-x"
  assert wrap_side("U", "A", "top") == "+x"
  assert wrap_side("V", "B", "top") == "+x"
  assert wrap_side("U", "A", "foot") == "+y"
  assert wrap_side("V", "B", "foot") == "+y"


def test_lookup_recipe_site_resolves_anchor_and_wrapped_pin():
  calibration = _load_layer_calibration("U")
  site = _lookup_recipe_site("U", calibration, "B1201", "B2001")

  assert site.orientation_token == "BR"
  assert site.side == "B"
  assert site.position == "top"
  assert site.site_label == "Top B corner - foot end"


def test_infer_pair_pin_from_wrap_side_matches_known_u_case():
  calibration = _load_layer_calibration("U")
  inferred = _infer_pair_pin_from_wrap_side(calibration, "B2001", "-x")
  assert inferred == "B2002"


def test_infer_pair_pin_from_wrap_side_matches_known_v_case():
  calibration = _load_layer_calibration("V")
  inferred = _infer_pair_pin_from_wrap_side(calibration, "B1999", "+x")
  assert inferred == "B1998"


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
