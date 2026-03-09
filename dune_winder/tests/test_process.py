import unittest

from dune_winder.core.control_events import ManualModeEvent
from dune_winder.core.process import Process
from dune_winder.io.Primitives.digital_input import DigitalInput


class FakeAxis:
  def __init__(
    self,
    functional,
    moving,
    desiredPosition,
    position,
    velocity,
    acceleration,
    seekStartPosition,
  ):
    self._functional = functional
    self._moving = moving
    self._desiredPosition = desiredPosition
    self._position = position
    self._velocity = velocity
    self._acceleration = acceleration
    self._seekStartPosition = seekStartPosition

  def isFunctional(self):
    return self._functional

  def isSeeking(self):
    return self._moving

  def getDesiredPosition(self):
    return self._desiredPosition

  def getPosition(self):
    return self._position

  def getVelocity(self):
    return self._velocity

  def getAcceleration(self):
    return self._acceleration

  def getSeekStartPosition(self):
    return self._seekStartPosition


class FakeValue:
  def __init__(self, value):
    self._value = value

  def get(self):
    return self._value


class FakeNamedInput:
  def __init__(self, name, value):
    self._name = name
    self._value = value

  def getName(self):
    return self._name

  def get(self):
    return self._value


class FakePLC:
  def __init__(self, isNotFunctional):
    self._isNotFunctional = isNotFunctional

  def isNotFunctional(self):
    return self._isNotFunctional


class FakeIO:
  def __init__(self, isFunctional):
    self._isFunctional = isFunctional
    self.xAxis = FakeAxis(True, False, 1.0, 1.5, 0.25, 0.5, 0.9)
    self.yAxis = FakeAxis(True, True, 2.0, 2.5, 0.75, -0.5, 1.8)
    self.zAxis = FakeAxis(False, False, 3.0, 3.5, 1.25, 1.5, 2.7)
    self.Z_Stage_Present = FakeValue(True)
    self.Z_Fixed_Present = FakeValue(False)
    self.plc = FakePLC(True)

  def isFunctional(self):
    return self._isFunctional


class FakeHeadCompensation:
  def __init__(self, angle):
    self.angle = angle
    self.locations = []

  def getHeadAngle(self, location):
    self.locations.append((location.x, location.y, location.z))
    return self.angle


class FakeAPARefresh:
  def __init__(self, recipeError=None, calibrationError=None):
    self.calls = []
    self.recipeError = recipeError
    self.calibrationError = calibrationError

  def refreshRecipeIfChanged(self):
    self.calls.append("recipe")
    if self.recipeError:
      raise self.recipeError

  def refreshCalibrationIfChanged(self):
    self.calls.append("calibration")
    if self.calibrationError:
      raise self.calibrationError


class FakeLog:
  def __init__(self):
    self.entries = []

  def add(self, source, code, message, data=None):
    self.entries.append((source, code, message, data))


class ProcessSnapshotTests(unittest.TestCase):
  def setUp(self):
    self._originalInputs = list(DigitalInput.digital_input_instances)

  def tearDown(self):
    DigitalInput.digital_input_instances = self._originalInputs

  def test_get_ui_snapshot_collects_axes_inputs_and_head_state(self):
    process = object.__new__(Process)
    process._io = FakeIO(True)
    process.headCompensation = FakeHeadCompensation(1.234)
    DigitalInput.digital_input_instances = [
      FakeNamedInput("Gate_Key", True),
      FakeNamedInput("Light_Curtain", False),
    ]

    snapshot = process.getUiSnapshot()

    self.assertEqual(snapshot["headSide"], 1)
    self.assertAlmostEqual(snapshot["headAngle"], 1.234)
    self.assertEqual(snapshot["plcNotFunctional"], True)
    self.assertEqual(snapshot["inputs"]["Gate_Key"], True)
    self.assertEqual(snapshot["inputs"]["Light_Curtain"], False)
    self.assertEqual(snapshot["axes"]["x"]["position"], 1.5)
    self.assertEqual(snapshot["axes"]["y"]["moving"], True)
    self.assertEqual(snapshot["axes"]["z"]["functional"], False)
    self.assertEqual(
      process.headCompensation.locations,
      [(1.5, 2.5, 3.5)],
    )

  def test_get_ui_snapshot_uses_zero_angle_when_io_not_functional(self):
    process = object.__new__(Process)
    process._io = FakeIO(False)
    process.headCompensation = FakeHeadCompensation(9.9)
    DigitalInput.digital_input_instances = []

    snapshot = process.getUiSnapshot()

    self.assertEqual(snapshot["headAngle"], 0)
    self.assertEqual(process.headCompensation.locations, [])

  def test_refresh_before_execution_checks_recipe_then_calibration(self):
    process = object.__new__(Process)
    process.apa = FakeAPARefresh()
    process._log = FakeLog()

    result = process._refreshCalibrationBeforeExecution()

    self.assertIsNone(result)
    self.assertEqual(process.apa.calls, ["recipe", "calibration"])
    self.assertEqual(process._log.entries, [])

  def test_refresh_before_execution_returns_error_when_recipe_refresh_fails(self):
    process = object.__new__(Process)
    process.apa = FakeAPARefresh(recipeError=RuntimeError("recipe changed badly"))
    process._log = FakeLog()

    result = process._refreshCalibrationBeforeExecution()

    self.assertEqual(result, "Failed to refresh G-Code or calibration from disk.")
    self.assertEqual(process.apa.calls, ["recipe"])
    self.assertEqual(len(process._log.entries), 1)
    self.assertEqual(process._log.entries[0][1], "GCODE_REFRESH")


class _AxisForManualGCode:
  def __init__(self, position):
    self._position = position

  def getPosition(self):
    return self._position


class _ControlStateMachineForManualGCode:
  def __init__(self):
    self.events = []

  def isReadyForMovement(self):
    return True

  def dispatch(self, event):
    self.events.append(event)
    return True


class _GCodeHandlerForManualGCode:
  def __init__(self):
    self.lines = []

  def executeG_CodeLine(self, line):
    self.lines.append(line)
    return None


class ProcessManualGCodeTests(unittest.TestCase):
  def _build_process_for_manual_gcode(self, x_position=10.0, y_position=20.0):
    process = object.__new__(Process)
    process._io = type("IO", (), {})()
    process._io.xAxis = _AxisForManualGCode(x_position)
    process._io.yAxis = _AxisForManualGCode(y_position)
    process._io.zAxis = _AxisForManualGCode(5.0)
    process._log = FakeLog()
    process.controlStateMachine = _ControlStateMachineForManualGCode()
    process.gCodeHandler = _GCodeHandlerForManualGCode()

    process._transferLeft = -1000.0
    process._transferRight = 10000.0
    process._limitLeft = -1000.0
    process._limitRight = 10000.0
    process._limitTop = 10000.0
    process._limitBottom = -1000.0
    process._zlimitFront = 0.0
    process._zlimitRear = 100.0
    process._maxVelocity = 300.0

    return process

  def test_execute_manual_gcode_accepts_x_only_and_keeps_current_y(self):
    process = self._build_process_for_manual_gcode(x_position=11.0, y_position=22.0)

    error = process.executeG_CodeLine("X4")

    self.assertIsNone(error)
    self.assertEqual(process.gCodeHandler.lines, ["X4 Y22.0"])
    self.assertEqual(len(process.controlStateMachine.events), 1)
    self.assertIsInstance(process.controlStateMachine.events[0], ManualModeEvent)
    self.assertTrue(process.controlStateMachine.events[0].executeGCode)

  def test_execute_manual_gcode_accepts_y_only_and_keeps_current_x(self):
    process = self._build_process_for_manual_gcode(x_position=11.0, y_position=22.0)

    error = process.executeG_CodeLine("Y3")

    self.assertIsNone(error)
    self.assertEqual(process.gCodeHandler.lines, ["Y3 X11.0"])

  def test_execute_manual_gcode_accepts_feed_only_without_movement(self):
    process = self._build_process_for_manual_gcode(x_position=11.0, y_position=22.0)

    error = process.executeG_CodeLine("F120")

    self.assertIsNone(error)
    self.assertEqual(process.gCodeHandler.lines, ["F120"])

  def test_execute_manual_gcode_rejects_feed_above_max_velocity(self):
    process = self._build_process_for_manual_gcode(x_position=11.0, y_position=22.0)

    error = process.executeG_CodeLine("F301")

    self.assertIn("Invalid F-axis Speed, exceeding limit", error)
    self.assertEqual(process.gCodeHandler.lines, [])
