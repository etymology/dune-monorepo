import unittest

from dune_winder.core.g_code_handler import G_CodeHandler
from dune_winder.machine.default_calibration import DefaultMachineCalibration
from dune_winder.machine.head_compensation import WirePathModel


class _Axis:
  def __init__(self, position):
    self._position = float(position)

  def getPosition(self):
    return self._position


class _PLCLogic:
  def __init__(self):
    self.moves = []
    self._maxAcceleration = 1000.0
    self._maxDeceleration = 1000.0

  def isReady(self):
    return True

  def setXY_Position(self, x, y, velocity=None, acceleration=None, deceleration=None):
    self.moves.append((float(x), float(y), velocity, acceleration, deceleration))

  def setZ_Position(self, z, velocity=None):
    raise AssertionError("Unexpected Z move")

  def move_latch(self):
    raise AssertionError("Unexpected latch move")


class _Head:
  def isReady(self):
    return True

  def readCurrentPosition(self):
    return 0

  def setHeadPosition(self, position, velocity=None):
    raise AssertionError("Unexpected head move")

  def stop(self):
    return None

  def getTargetAxisPosition(self):
    return 0.0


class _IO:
  def __init__(self, x, y, z=0.0):
    self.xAxis = _Axis(x)
    self.yAxis = _Axis(y)
    self.zAxis = _Axis(z)
    self.plcLogic = _PLCLogic()
    self.head = _Head()


class GCodeHandlerSafetyTests(unittest.TestCase):
  def _handler(self, start_x, start_y):
    calibration = DefaultMachineCalibration()
    io = _IO(start_x, start_y)
    handler = G_CodeHandler(io, calibration, WirePathModel(calibration))
    handler._delay = 0
    return handler, io

  def test_execute_manual_line_blocks_unsafe_legacy_xy_move(self):
    handler, io = self._handler(400.0, 1400.0)

    error = handler.executeG_CodeLine("X100 Y1400")

    self.assertIsNotNone(error)
    self.assertIn("pivot keepout", error["message"])
    self.assertEqual(io.plcLogic.moves, [])

  def test_execute_manual_line_allows_safe_legacy_xy_move(self):
    handler, io = self._handler(400.0, 100.0)

    error = handler.executeG_CodeLine("X500 Y200")

    self.assertIsNone(error)
    self.assertEqual(len(io.plcLogic.moves), 1)
    self.assertEqual(io.plcLogic.moves[0][:2], (500.0, 200.0))


if __name__ == "__main__":
  unittest.main()
