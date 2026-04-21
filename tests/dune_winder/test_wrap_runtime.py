from __future__ import annotations

import unittest

from dune_winder.gcode.handler import GCodeHandler
from dune_winder.library.Geometry.location import Location
from dune_winder.machine.calibration.layer import LayerCalibration
from dune_winder.machine.calibration.machine import MachineCalibration
from dune_winder.machine.geometry.uv_wrap_geometry import (
  Point2D,
  Point3D,
  RectBounds,
  alternating_side_hover_y_offset,
  plan_wrap_transition,
)
from dune_winder.machine.geometry.uv_tangency import (
  UvTangentViewRequest,
  compute_uv_tangent_view,
)
from dune_winder.machine.head_compensation import WirePathModel
from dune_winder.paths import REPO_ROOT


class _Axis:
  def __init__(self, position):
    self._position = float(position)

  def getPosition(self):
    return float(self._position)

  def setPosition(self, position):
    self._position = float(position)


class _Input:
  def __init__(self, value=False):
    self._value = bool(value)

  def get(self):
    return self._value


class _PLCLogic:
  def __init__(self, x_axis, y_axis, z_axis):
    self._x_axis = x_axis
    self._y_axis = y_axis
    self._z_axis = z_axis
    self.xy_moves = []
    self.z_moves = []
    self.xz_moves = []
    self.latch_moves = 0

  def isReady(self):
    return True

  def setXY_Position(self, x, y, velocity=None, acceleration=None, deceleration=None):
    self.xy_moves.append((float(x), float(y), velocity, acceleration, deceleration))
    self._x_axis.setPosition(x)
    self._y_axis.setPosition(y)

  def setZ_Position(self, z, velocity=None):
    self.z_moves.append((float(z), velocity))
    self._z_axis.setPosition(z)

  def setXZ_Position(self, x, z, velocity=None):
    self.xz_moves.append((float(x), float(z), velocity))
    self._x_axis.setPosition(x)
    self._z_axis.setPosition(z)

  def move_latch(self):
    self.latch_moves += 1


class _Head:
  def __init__(self):
    self.moves = []
    self.transfer_moves = []
    self.front_back = None
    self.position = 0

  def isReady(self):
    return True

  def hasError(self):
    return False

  def getLastError(self):
    return ""

  def consumeLastError(self):
    return ""

  def readCurrentPosition(self):
    return int(self.position)

  def setHeadPosition(self, position, velocity=None):
    self.moves.append((int(position), velocity))
    self.position = int(position)
    return None

  def setTransferPosition(self, position, velocity=None):
    self.transfer_moves.append((int(position), velocity))
    self.position = int(position)
    return None

  def stop(self):
    return None

  def getTargetAxisPosition(self):
    return 0.0

  def setFrontAndBack(self, front, back):
    self.front_back = (float(front), float(back))

  def clearQueuedTransfer(self):
    return None


class _IO:
  def __init__(self, x, y, z=0.0):
    self.xAxis = _Axis(x)
    self.yAxis = _Axis(y)
    self.zAxis = _Axis(z)
    self.plcLogic = _PLCLogic(self.xAxis, self.yAxis, self.zAxis)
    self.head = _Head()
    self.Y_Transfer_OK = _Input(True)
    self.FrameLockHeadTop = _Input(False)
    self.FrameLockHeadMid = _Input(False)
    self.FrameLockHeadBtm = _Input(False)
    self.FrameLockFootTop = _Input(False)
    self.FrameLockFootMid = _Input(False)
    self.FrameLockFootBtm = _Input(False)


def _load_machine_calibration() -> MachineCalibration:
  calibration = MachineCalibration(str(REPO_ROOT / "dune_winder" / "config"), "machineCalibration.json")
  calibration.load()
  return calibration


def _load_layer_calibration(layer: str) -> LayerCalibration:
  path = REPO_ROOT / "dune_winder" / "config" / "APA" / f"{str(layer).upper()}_Calibration.json"
  calibration = LayerCalibration(layer)
  calibration.load(str(path.parent), path.name, exceptionForMismatch=False)
  return calibration


def _wire_space_pin(layer_calibration: LayerCalibration, pin_name: str) -> Location:
  return layer_calibration.getPinLocation(pin_name).add(layer_calibration.offset)


def _point3(location: Location) -> Point3D:
  return Point3D(float(location.x), float(location.y), float(location.z))


class WrapRuntimeTests(unittest.TestCase):
  def _build_handler(self, start_x, start_y):
    machine_calibration = _load_machine_calibration()
    layer_calibration = _load_layer_calibration("U")
    io = _IO(start_x, start_y, z=0.0)
    handler = GCodeHandler(io, machine_calibration, WirePathModel(machine_calibration))
    handler.useLayerCalibration(layer_calibration)
    handler._x = float(start_x)
    handler._y = float(start_y)
    handler._z = 0.0
    return handler, io, machine_calibration, layer_calibration

  def _expected_explicit_wrap_plan(self, *, layer_calibration, machine_calibration, anchor_pin, target_pin, offset_x=0.0, offset_y=0.0, start_x=None, start_y=None):
    anchor_location = layer_calibration.getPinLocation(anchor_pin).add(layer_calibration.offset)
    target_location = layer_calibration.getPinLocation(target_pin).add(layer_calibration.offset)
    target_location = Location(
      float(target_location.x) + float(offset_x),
      float(target_location.y) + float(offset_y),
      float(target_location.z),
    )
    current_xy = None
    if start_x is not None and start_y is not None:
      current_xy = Point2D(float(start_x), float(start_y))
    return plan_wrap_transition(
      layer=layer_calibration.getLayerNames(),
      anchor_pin=anchor_pin,
      target_pin=target_pin,
      anchor_pin_point=Point3D(float(anchor_location.x), float(anchor_location.y), float(anchor_location.z)),
      target_pin_point=Point3D(float(target_location.x), float(target_location.y), float(target_location.z)),
      transfer_bounds=RectBounds(
        left=float(machine_calibration.transferLeft),
        top=float(machine_calibration.transferTop),
        right=float(machine_calibration.transferRight),
        bottom=float(machine_calibration.transferBottom),
      ),
      z_front=float(machine_calibration.zFront),
      z_back=float(machine_calibration.zBack),
      pin_radius=float(machine_calibration.pinDiameter) / 2.0,
      head_arm_length=float(machine_calibration.headArmLength),
      head_roller_radius=float(machine_calibration.headRollerRadius),
      head_roller_gap=float(machine_calibration.headRollerGap),
      current_xy=current_xy,
    )

  def _expected_explicit_wrap_final_xy(
    self,
    *,
    layer_calibration,
    machine_calibration,
    anchor_pin,
    target_pin,
    offset_x=0.0,
    offset_y=0.0,
    hover=False,
  ):
    anchor_location = layer_calibration.getPinLocation(anchor_pin).add(layer_calibration.offset)
    target_location = layer_calibration.getPinLocation(target_pin).add(layer_calibration.offset)
    target_location = Location(
      float(target_location.x) + float(offset_x),
      float(target_location.y) + float(offset_y),
      float(target_location.z),
    )
    tangent_view = compute_uv_tangent_view(
      UvTangentViewRequest(
        layer=layer_calibration.getLayerNames(),
        pin_a=anchor_pin,
        pin_b=target_pin,
      ),
      pin_b_point_override=Point3D(
        float(target_location.x),
        float(target_location.y),
        float(target_location.z),
      ),
      roller_arm_y_offsets=(
        machine_calibration.rollerArmCalibration.fitted_y_cals
        if machine_calibration.rollerArmCalibration is not None
        else None
      ),
    )
    if tangent_view.alternating_plane is None:
      self.assertIsNotNone(tangent_view.arm_corrected_outbound_point)
      final_xy = Point2D(
        float(tangent_view.arm_corrected_outbound_point.x),
        float(tangent_view.arm_corrected_outbound_point.y),
      )
      return final_xy, tangent_view

    target_family = str(target_pin).strip().upper()[:1]
    if tangent_view.alternating_plane == "xz":
      plane_point = (
        tangent_view.alternating_wrap_line_start
        if target_family == "A"
        else tangent_view.alternating_wrap_line_end
      )
      final_xy = Point2D(
        float(plane_point.x),
        float((tangent_view.pin_a_point.y + tangent_view.pin_b_point.y) / 2.0),
      )
    else:
      plane_point = (
        tangent_view.alternating_wrap_line_start
        if target_family == "A"
        else tangent_view.alternating_wrap_line_end
      )
      final_xy = Point2D(
        float((tangent_view.pin_a_point.x + tangent_view.pin_b_point.x) / 2.0),
        float(plane_point.y),
      )
    if hover:
      self.assertIsNotNone(tangent_view.alternating_face)
      final_xy = Point2D(
        float(final_xy.x),
        float(final_xy.y + alternating_side_hover_y_offset(tangent_view.alternating_face)),
      )
    return final_xy, tangent_view

  def test_tilde_goto_and_increment_move_xy_without_wrap_state(self):
    handler, io, _machine_calibration, _layer_calibration = self._build_handler(500.0, 500.0)

    error = handler.executeG_CodeLine("~goto(7174,0)")

    self.assertIsNone(error)
    self.assertEqual(io.plcLogic.xy_moves, [(7174.0, 0.0, float("inf"), None, None)])

    error = handler.executeG_CodeLine("~increment(-200,0)")
    self.assertIsNone(error)
    self.assertEqual(io.plcLogic.xy_moves[-1][:2], (6974.0, 0.0))

  def test_anchor_to_target_applies_offset_keyword_to_target_pin(self):
    handler, io, machine_calibration, layer_calibration = self._build_handler(500.0, 500.0)
    anchor_pin = "B1201"
    target_pin = "B2001"

    plan = self._expected_explicit_wrap_plan(
      layer_calibration=layer_calibration,
      machine_calibration=machine_calibration,
      anchor_pin=anchor_pin,
      target_pin=target_pin,
      offset_x=12.5,
      offset_y=-3.0,
      start_x=500.0,
      start_y=500.0,
    )

    error = handler.executeG_CodeLine("~anchorToTarget(B1201,B2001,offset=(12.5,-3.0))")

    self.assertIsNone(error)
    while handler._dispatch_pending_actions(safety_label="manual"):
      pass
    self.assertGreaterEqual(len(io.plcLogic.xy_moves), 1)
    self.assertAlmostEqual(io.plcLogic.xy_moves[-1][0], float(plan.final_xy.x), places=3)
    self.assertAlmostEqual(io.plcLogic.xy_moves[-1][1], float(plan.final_xy.y), places=3)

  def test_plain_anchor_to_target_remains_unmodified_without_offset_macro(self):
    handler, io, machine_calibration, layer_calibration = self._build_handler(500.0, 500.0)
    anchor_pin = "B1201"
    target_pin = "B2001"

    plan = self._expected_explicit_wrap_plan(
      layer_calibration=layer_calibration,
      machine_calibration=machine_calibration,
      anchor_pin=anchor_pin,
      target_pin=target_pin,
      start_x=500.0,
      start_y=500.0,
    )

    error = handler.executeG_CodeLine("~anchorToTarget(B1201,B2001)")

    self.assertIsNone(error)
    while handler._dispatch_pending_actions(safety_label="manual"):
      pass
    self.assertGreaterEqual(len(io.plcLogic.xy_moves), 1)
    self.assertAlmostEqual(io.plcLogic.xy_moves[-1][0], float(plan.final_xy.x), places=3)
    self.assertAlmostEqual(io.plcLogic.xy_moves[-1][1], float(plan.final_xy.y), places=3)

  def test_anchor_to_target_hover_keyword_offsets_alternating_side_final_y(self):
    handler, io, machine_calibration, layer_calibration = self._build_handler(500.0, 500.0)
    anchor_pin = "B2001"
    target_pin = "A800"

    final_xy, tangent_view = self._expected_explicit_wrap_final_xy(
      layer_calibration=layer_calibration,
      machine_calibration=machine_calibration,
      anchor_pin=anchor_pin,
      target_pin=target_pin,
      hover=True,
    )
    self.assertEqual(tangent_view.alternating_face, "top")

    error = handler.executeG_CodeLine("~anchorToTarget(B2001,A800,hover=True)")

    self.assertIsNone(error)
    while handler._dispatch_pending_actions(safety_label="manual"):
      pass
    self.assertGreaterEqual(len(io.plcLogic.xy_moves), 1)
    self.assertAlmostEqual(io.plcLogic.xy_moves[-1][0], float(final_xy.x), places=3)
    self.assertAlmostEqual(io.plcLogic.xy_moves[-1][1], float(final_xy.y), places=3)

  def test_anchor_to_target_hover_keyword_offsets_bottom_alternating_side_final_y(self):
    handler, io, machine_calibration, layer_calibration = self._build_handler(500.0, 500.0)
    anchor_pin = "A2401"
    target_pin = "B401"

    final_xy, tangent_view = self._expected_explicit_wrap_final_xy(
      layer_calibration=layer_calibration,
      machine_calibration=machine_calibration,
      anchor_pin=anchor_pin,
      target_pin=target_pin,
      hover=True,
    )
    self.assertEqual(tangent_view.alternating_face, "bottom")

    error = handler.executeG_CodeLine("~anchorToTarget(A2401,B401,hover=True)")

    self.assertIsNone(error)
    while handler._dispatch_pending_actions(safety_label="manual"):
      pass
    self.assertGreaterEqual(len(io.plcLogic.xy_moves), 1)
    self.assertAlmostEqual(io.plcLogic.xy_moves[-1][0], float(final_xy.x), places=3)
    self.assertAlmostEqual(io.plcLogic.xy_moves[-1][1], float(final_xy.y), places=3)

  def test_anchor_to_target_hover_keyword_does_not_change_same_side_final_xy(self):
    handler, io, machine_calibration, layer_calibration = self._build_handler(500.0, 500.0)
    anchor_pin = "B1201"
    target_pin = "B2001"

    final_xy, tangent_view = self._expected_explicit_wrap_final_xy(
      layer_calibration=layer_calibration,
      machine_calibration=machine_calibration,
      anchor_pin=anchor_pin,
      target_pin=target_pin,
      hover=True,
    )
    self.assertIsNone(tangent_view.alternating_plane)

    error = handler.executeG_CodeLine("~anchorToTarget(B1201,B2001,hover=True)")

    self.assertIsNone(error)
    while handler._dispatch_pending_actions(safety_label="manual"):
      pass
    self.assertGreaterEqual(len(io.plcLogic.xy_moves), 1)
    self.assertAlmostEqual(io.plcLogic.xy_moves[-1][0], float(final_xy.x), places=3)
    self.assertAlmostEqual(io.plcLogic.xy_moves[-1][1], float(final_xy.y), places=3)


if __name__ == "__main__":
  unittest.main()
