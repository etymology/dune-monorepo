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
from dune_winder import uv_head_target as uv_head_target_module
from dune_winder.uv_head_target import (
  UvHeadTargetError,
  UvHeadTargetRequest,
  _infer_orientation_token,
  compute_uv_head_target,
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


def _first_valid_request(layer: str) -> tuple[UvHeadTargetRequest, str]:
  lines = render_u_template_lines(strip_g113_params=True) if layer == "U" else render_v_template_lines(strip_g113_params=True)
  for line in lines:
    match = _LINE_RE.search(line)
    if match is None:
      continue
    anchor_pin, _orientation, near_pin, target_pin = match.groups()
    for head_z_mode in ("front", "back"):
      request = UvHeadTargetRequest(
        layer=layer,
        anchor_pin=anchor_pin[1:],
        near_pin=near_pin[1:],
        target_pair_pin_b=target_pin[1:],
        head_z_mode=head_z_mode,
      )
      try:
        result = compute_uv_head_target(request)
      except Exception:
        continue
      return (request, result.orientation_token)
  raise AssertionError(f"No valid {layer} request found in rendered recipe.")


def test_compute_uv_head_target_matches_runtime_for_first_valid_u_case():
  request, orientation = _first_valid_request("U")
  result = compute_uv_head_target(request)
  handler = _make_handler("U")
  head_position = 1 if request.head_z_mode == "front" else 2

  execute_text_line(f"G106 P{head_position}", handler._callbacks.get)
  execute_text_line(f"G109 P{request.anchor_pin} P{orientation}", handler._callbacks.get)
  execute_text_line(f"G103 P{request.near_pin} P{request.target_pair_pin_b} PXY", handler._callbacks.get)
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
  request, orientation = _first_valid_request("V")
  result = compute_uv_head_target(request)
  handler = _make_handler("V")
  head_position = 1 if request.head_z_mode == "front" else 2
  execute_text_line(f"G106 P{head_position}", handler._callbacks.get)
  execute_text_line(f"G109 P{request.anchor_pin} P{orientation}", handler._callbacks.get)
  execute_text_line(f"G103 P{request.near_pin} P{request.target_pair_pin_b} PXY", handler._callbacks.get)
  execute_text_line("G102", handler._callbacks.get)
  execute_text_line("G108", handler._callbacks.get)

  assert result.orientation_token == orientation
  assert result.request.layer == "V"
  assert result.validation_error is None
  assert math.isclose(result.final_head_point.x, handler._x)
  assert math.isclose(result.final_head_point.y, handler._y)


def test_infer_orientation_rejects_ambiguous_choice(monkeypatch):
  machine_calibration = _load_machine_calibration()
  anchor = _load_layer_calibration("U").getPinLocation("F400")
  provisional_target = anchor.copy(x=anchor.x + 25.0, y=anchor.y + 25.0)
  near_point = anchor.copy(x=anchor.x + 15.0, y=anchor.y + 5.0)
  monkeypatch.setattr(uv_head_target_module, "_score_orientation", lambda *_args, **_kwargs: 0.5)

  with pytest.raises(UvHeadTargetError, match="unique G109 orientation"):
    _infer_orientation_token(machine_calibration, anchor, provisional_target, near_point)


def test_infer_orientation_rejects_missing_tangent():
  machine_calibration = _load_machine_calibration()
  anchor = _load_layer_calibration("U").getPinLocation("F400")
  provisional_target = anchor.copy(x=anchor.x + 0.1, y=anchor.y + 0.1)
  near_point = anchor.copy(x=anchor.x + 5.0, y=anchor.y)

  with pytest.raises(UvHeadTargetError, match="valid G109 orientation"):
    _infer_orientation_token(machine_calibration, anchor, provisional_target, near_point)


def test_compute_uv_head_target_rejects_bad_pin_format():
  with pytest.raises(UvHeadTargetError, match="Anchor pin must be a pin name"):
    compute_uv_head_target(
      UvHeadTargetRequest(
        layer="U",
        anchor_pin="1201",
        near_pin="B2002",
        target_pair_pin_b="B2003",
        head_z_mode="front",
      )
    )


def test_compute_uv_head_target_rejects_unknown_pin():
  with pytest.raises(UvHeadTargetError, match="not present"):
    compute_uv_head_target(
      UvHeadTargetRequest(
        layer="U",
        anchor_pin="B99999",
        near_pin="B2002",
        target_pair_pin_b="B2003",
        head_z_mode="front",
      )
    )
