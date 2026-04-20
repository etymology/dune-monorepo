from __future__ import annotations

import unittest

from dune_winder.gcode.handler import GCodeHandler
from dune_winder.library.Geometry.location import Location
from dune_winder.machine.calibration.layer import LayerCalibration
from dune_winder.machine.calibration.machine import MachineCalibration
from dune_winder.machine.geometry.uv_tangency import compute_uv_tangent_view, UvTangentViewRequest
from dune_winder.machine.geometry.uv_wrap_geometry import Point2D, Point3D, RectBounds, b_to_a_pin
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


def _transfer_bounds(machine_calibration: MachineCalibration) -> RectBounds:
  return RectBounds(
    left=float(machine_calibration.transferLeft),
    top=float(machine_calibration.transferTop),
    right=float(machine_calibration.transferRight),
    bottom=float(machine_calibration.transferBottom),
  )


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

  def test_tilde_goto_and_increment_move_xy_without_wrap_state(self):
    handler, io, _machine_calibration, _layer_calibration = self._build_handler(500.0, 500.0)

    error = handler.executeG_CodeLine("~goto(7174,0)")

    self.assertIsNone(error)
    self.assertEqual(io.plcLogic.xy_moves, [(7174.0, 0.0, float("inf"), None, None)])

    error = handler.executeG_CodeLine("~increment(-200,0)")
    self.assertIsNone(error)
    self.assertEqual(io.plcLogic.xy_moves[-1][:2], (6974.0, 0.0))

  def test_same_side_anchor_to_target_dispatches_xy_then_head(self):
    machine_calibration = _load_machine_calibration()
    layer_calibration = _load_layer_calibration("U")
    anchor_pin = "B1201"
    target_pin = "B2001"

    tangent_view = compute_uv_tangent_view(
      UvTangentViewRequest(layer="U", pin_a=anchor_pin, pin_b=target_pin)
    )
    plan_xy = tangent_view.arm_corrected_outbound_point
    self.assertIsNotNone(plan_xy)
    initial_x = float(plan_xy.x + 10.0)
    initial_y = float(plan_xy.y + 10.0)
    handler, io, machine_calibration, layer_calibration = self._build_handler(initial_x, initial_y)

    error = handler.executeG_CodeLine("~anchorToTarget(B1201,B2001)")

    self.assertIsNone(error)

    self.assertTrue(handler._dispatch_pending_actions(safety_label="manual"))
    self.assertEqual(len(io.plcLogic.xy_moves), 1)

    self.assertTrue(handler._dispatch_pending_actions(safety_label="manual"))
    self.assertEqual(len(io.head.transfer_moves), 1)
    self.assertEqual(io.head.transfer_moves[0][0], 3)

    self.assertTrue(handler._dispatch_pending_actions(safety_label="manual"))
    self.assertEqual(len(io.plcLogic.xy_moves), 2)
    self.assertAlmostEqual(io.plcLogic.xy_moves[1][0], float(plan_xy.x), places=3)
    self.assertAlmostEqual(io.plcLogic.xy_moves[1][1], float(plan_xy.y), places=3)

    while handler._dispatch_pending_actions(safety_label="manual"):
      pass

    self.assertEqual(len(io.head.transfer_moves), 2)
    self.assertEqual(io.head.transfer_moves[1][0], 2)

  def test_opposite_side_anchor_to_target_uses_transfer_then_head_then_reports_projected_xy_error(self):
    machine_calibration = _load_machine_calibration()
    transfer_bounds = _transfer_bounds(machine_calibration)
    initial_x = float(transfer_bounds.right + 10.0)
    initial_y = float(transfer_bounds.top + 10.0)
    handler, io, machine_calibration, layer_calibration = self._build_handler(initial_x, initial_y)
    anchor_pin = "B2001"
    source_b_pin = "B1201"
    target_pin = b_to_a_pin("U", source_b_pin)

    tangent_view = compute_uv_tangent_view(
      UvTangentViewRequest(layer="U", pin_a=anchor_pin, pin_b=target_pin)
    )
    self.assertEqual(tangent_view.alternating_plane, "yz")

    error = handler.executeG_CodeLine("~anchorToTarget(B2001,A1601)")

    self.assertIsNone(error)

    self.assertTrue(handler._dispatch_pending_actions(safety_label="manual"))
    self.assertEqual(len(io.head.transfer_moves), 1)
    self.assertEqual(io.head.transfer_moves[0][0], 0)

    self.assertTrue(handler._dispatch_pending_actions(safety_label="manual"))
    self.assertEqual(len(io.plcLogic.xy_moves), 1)
    self.assertAlmostEqual(io.plcLogic.xy_moves[0][0], float(transfer_bounds.right), places=3)
    self.assertAlmostEqual(io.plcLogic.xy_moves[0][1], float(transfer_bounds.top), places=3)

    self.assertFalse(handler._dispatch_pending_actions(safety_label="manual"))
    self.assertTrue(handler._isG_CodeError)
    self.assertIn("outside", handler._isG_CodeErrorMessage)


if __name__ == "__main__":
  unittest.main()
