import unittest
import tempfile
from pathlib import Path
import os
import hashlib


from dune_winder.core.control_events import ManualModeEvent
from dune_winder.core.manual_calibration import build_nominal_calibration
from dune_winder.core.motion_service import MotionService
from dune_winder.core.process import Process
from dune_winder.core.safety_validation_service import SafetyValidationService
from dune_winder.core.x_backlash_compensation import XBacklashCompensation
from dune_winder.gcode.handler import GCodeHandler
from dune_winder.io.primitives.digital_input import DigitalInput


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


class FakeWorkspaceForRefreshMessages:
  def __init__(self, recipePath, calibrationPath):
    self._recipePath = recipePath
    self._calibrationPath = calibrationPath
    self._recipeFile = "V-layer.gc"
    self._calibrationFile = "V_Calibration.json"
    self._recipeDirectory = "C:/recipes"
    self._calibrationDirectory = "C:/config/APA"
    self._recipe = object()
    self._calibration = type(
      "StableCalibration",
      (),
      {"refreshIfChanged": lambda self: False},
    )()
    self._recipeSignature = "recipe-signature"
    self._calibrationSignature = "calibration-signature"

  def _getRecipeFullPath(self):
    return self._recipePath

  def _getCalibrationFullPath(self):
    return self._calibrationPath

  def _missingRecipeMessage(self, recipeFullPath):
    from dune_winder.core.winder_workspace import WinderWorkspace

    return WinderWorkspace._missingRecipeMessage(self, recipeFullPath)

  def _missingCalibrationMessage(self, calibFullPath):
    from dune_winder.core.winder_workspace import WinderWorkspace

    return WinderWorkspace._missingCalibrationMessage(self, calibFullPath)

  def _calculateRecipeSignature(self):
    if self._recipePath is None or not os.path.isfile(self._recipePath):
      return None
    return self._recipeSignature

  def _calculateCalibrationSignature(self):
    if self._calibrationPath is None or not os.path.isfile(self._calibrationPath):
      return None
    return self._calibrationSignature

  def _getCalibrationHashValueFromFile(self):
    from dune_winder.core.winder_workspace import WinderWorkspace

    return WinderWorkspace._getCalibrationHashValueFromFile(self)

  def refreshRecipeIfChanged(self):
    from dune_winder.core.winder_workspace import WinderWorkspace

    return WinderWorkspace.refreshRecipeIfChanged(self)

  def refreshCalibrationIfChanged(self):
    from dune_winder.core.winder_workspace import WinderWorkspace

    return WinderWorkspace.refreshCalibrationIfChanged(self)

  def _isActiveWindReload(self):
    from dune_winder.core.winder_workspace import WinderWorkspace

    return WinderWorkspace._isActiveWindReload(self)

  def _reloadRecipeWhileStopped(self, previousLines, reloadedLines, cachedPinPair=None):
    from dune_winder.core.winder_workspace import WinderWorkspace

    return WinderWorkspace._reloadRecipeWhileStopped(
      self,
      previousLines,
      reloadedLines,
      cachedPinPair=cachedPinPair,
    )

  def _findReloadLineByPinPair(self, previousLines, reloadedLines, currentLine):
    from dune_winder.core.winder_workspace import WinderWorkspace

    return WinderWorkspace._findReloadLineByPinPair(self, previousLines, reloadedLines, currentLine)

  def _getMostRecentPinPair(self, lines, currentLine):
    from dune_winder.core.winder_workspace import WinderWorkspace

    return WinderWorkspace._getMostRecentPinPair(self, lines, currentLine)

  def _findClosestPinPairLine(self, lines, pinPair, currentLine):
    from dune_winder.core.winder_workspace import WinderWorkspace

    return WinderWorkspace._findClosestPinPairLine(self, lines, pinPair, currentLine)

  @classmethod
  def _extractPinPair(cls, line):
    from dune_winder.core.winder_workspace import WinderWorkspace

    return WinderWorkspace._extractPinPair(line)


class FakeLog:
  def __init__(self):
    self.entries = []

  def add(self, source, code, message, data=None):
    self.entries.append((source, code, message, data))


class _ReloadGuardFakeAxis:
  def __init__(self, position=0.0):
    self._position = position

  def getPosition(self):
    return self._position


class _ReloadGuardFakeHead:
  def __init__(self):
    self.front_back = None

  def setFrontAndBack(self, front, back):
    self.front_back = (float(front), float(back))

  def getTargetAxisPosition(self):
    return 0.0


class _ReloadGuardFakeIO:
  def __init__(self):
    self.xAxis = _ReloadGuardFakeAxis()
    self.yAxis = _ReloadGuardFakeAxis()
    self.zAxis = _ReloadGuardFakeAxis()
    self.head = _ReloadGuardFakeHead()


class _ReloadGuardFakeCalibration:
  zFront = 0.0
  zBack = 0.0


WindMode = type("WindMode", (), {})
StopMode = type("StopMode", (), {})


class _ReloadGuardControlStateMachine:
  def __init__(self, state):
    self.state = state


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
    process.workspace = FakeAPARefresh()
    process._log = FakeLog()

    result = process._refreshCalibrationBeforeExecution()

    self.assertIsNone(result)
    self.assertEqual(process.workspace.calls, ["recipe", "calibration"])
    self.assertEqual(process._log.entries, [])

  def test_refresh_before_execution_returns_error_when_recipe_refresh_fails(self):
    process = object.__new__(Process)
    process.workspace = FakeAPARefresh(recipeError=RuntimeError("recipe changed badly"))
    process._log = FakeLog()

    result = process._refreshCalibrationBeforeExecution()

    self.assertEqual(result, "recipe changed badly")
    self.assertEqual(process.workspace.calls, ["recipe"])
    self.assertEqual(len(process._log.entries), 1)
    self.assertEqual(process._log.entries[0][1], "GCODE_REFRESH")

  def test_get_layer_calibration_returns_normalized_absolute_locations(self):
    calibration = build_nominal_calibration("V")
    calibration.offset.x = 12.5
    calibration.offset.y = -7.25
    expected = calibration.getPinLocation("B400")

    process = object.__new__(Process)
    process.workspace = type(
      "Workspace",
      (),
      {
        "getCalibrationFile": lambda self: "V_Calibration.json",
        "_calibration": calibration,
      },
    )()
    process.gCodeHandler = type("Handler", (), {"getLayerCalibration": lambda self: calibration})()
    process.getRecipeLayer = lambda: "V"

    payload = process.getLayerCalibration("V")

    self.assertEqual(payload["layer"], "V")
    self.assertEqual(payload["activeLayer"], "V")
    self.assertEqual(payload["calibrationFile"], "V_Calibration.json")
    self.assertAlmostEqual(payload["locations"]["B400"]["x"], expected.x + 12.5, places=6)
    self.assertAlmostEqual(payload["locations"]["B400"]["y"], expected.y - 7.25, places=6)

  def test_get_layer_calibration_rejects_wrong_active_layer(self):
    process = object.__new__(Process)
    process.workspace = None
    process.gCodeHandler = type("Handler", (), {"getLayerCalibration": lambda self: None})()
    process.getRecipeLayer = lambda: "U"

    with self.assertRaisesRegex(ValueError, "active loaded recipe layer"):
      process.getLayerCalibration("V")

  def test_get_layer_calibration_json_reads_workspace_file(self):
    calibration = build_nominal_calibration("V")
    with tempfile.TemporaryDirectory() as temp_directory:
      path = Path(temp_directory) / "V_Calibration.json"
      calibration.save(str(path.parent), path.name)

      process = object.__new__(Process)
      process.workspace = type(
        "Workspace",
        (),
        {
          "getCalibrationFile": lambda self: path.name,
          "getCalibrationFullPath": lambda self: str(path),
          "_calibration": calibration,
        },
      )()
      process.gCodeHandler = type("Handler", (), {"getLayerCalibration": lambda self: calibration})()
      process.getRecipeLayer = lambda: "V"

      payload = process.getLayerCalibrationJson("V")

      self.assertEqual(payload["calibrationFile"], "V_Calibration.json")
      self.assertEqual(
        payload["contentHash"],
        hashlib.sha256(payload["content"].encode("utf-8")).hexdigest(),
      )
      self.assertIn("\"layer\": \"V\"", payload["content"])
  def test_refresh_before_execution_returns_actionable_missing_recipe_message(self):
    from dune_winder.core.winder_workspace import WinderWorkspace

    process = object.__new__(Process)
    process.workspace = FakeWorkspaceForRefreshMessages(
      recipePath="C:/recipes/V-layer.gc",
      calibrationPath="C:/config/APA/V_Calibration.json",
    )
    process._log = FakeLog()

    result = process._refreshCalibrationBeforeExecution()

    self.assertEqual(
      result,
      WinderWorkspace._missingRecipeMessage(process.workspace, "C:/recipes/V-layer.gc"),
    )
    self.assertEqual(len(process._log.entries), 1)

  def test_gcode_reload_rejects_line_count_changes(self):
    handler = GCodeHandler(_ReloadGuardFakeIO(), _ReloadGuardFakeCalibration(), None)
    handler.loadG_Code(["G1 X1", "G1 X2"], calibration=None)

    with self.assertRaisesRegex(ValueError, "same number of lines"):
      handler.reloadG_Code(["G1 X1"])

  def test_load_gcode_sets_head_front_and_back_from_calibration(self):
    io = _ReloadGuardFakeIO()
    handler = GCodeHandler(io, _ReloadGuardFakeCalibration(), None)

    calibration = type("Calibration", (), {"zFront": 123.4, "zBack": 567.8})()
    handler.loadG_Code(["G1 X1"], calibration=calibration)

    self.assertEqual(io.head.front_back, (123.4, 567.8))

  def test_use_layer_calibration_updates_head_front_and_back(self):
    io = _ReloadGuardFakeIO()
    handler = GCodeHandler(io, _ReloadGuardFakeCalibration(), None)

    calibration = type("Calibration", (), {"zFront": 145.0, "zBack": 270.0})()
    handler.useLayerCalibration(calibration)

    self.assertEqual(io.head.front_back, (145.0, 270.0))

  def test_refresh_before_execution_returns_error_when_recipe_line_count_changes(self):
    from dune_winder.core.winder_workspace import WinderWorkspace

    with tempfile.TemporaryDirectory() as tempDir:
      recipePath = os.path.join(tempDir, "V-layer.gc")
      calibrationPath = os.path.join(tempDir, "V_Calibration.json")

      with open(recipePath, "w", encoding="utf-8") as outputFile:
        outputFile.write("G1 X1\nG1 X2\n")
      with open(calibrationPath, "w", encoding="utf-8") as outputFile:
        outputFile.write("{}\n")

      process = object.__new__(Process)
      process.workspace = FakeWorkspaceForRefreshMessages(
        recipePath=recipePath,
        calibrationPath=calibrationPath,
      )
      process.workspace._log = FakeLog()
      process.workspace._recipeDirectory = tempDir
      process.workspace._recipeArchiveDirectory = tempDir
      process.workspace._gCodeHandler = GCodeHandler(
        _ReloadGuardFakeIO(),
        _ReloadGuardFakeCalibration(),
        None,
      )
      process.workspace._recipe = type(
        "LoadedRecipe",
        (),
        {"getLines": lambda self: ["G1 X1", "G1 X2"]},
      )()
      process.workspace._gCodeHandler.loadG_Code(["G1 X1", "G1 X2"], calibration=None)
      process.workspace._controlStateMachine = _ReloadGuardControlStateMachine(WindMode())
      process._log = FakeLog()

      process.workspace._recipeSignature = "before"
      process.workspace._calculateRecipeSignature = lambda: "after"

      with open(recipePath, "w", encoding="utf-8") as outputFile:
        outputFile.write("G1 X1\n")

      result = process._refreshCalibrationBeforeExecution()

      self.assertEqual(
        result,
        "Updated G-Code file must preserve the active execution state and keep the same number of lines.",
      )
      self.assertEqual(len(process._log.entries), 1)
      self.assertEqual(process._log.entries[0][1], "GCODE_REFRESH")
    self.assertEqual(process._log.entries[0][1], "GCODE_REFRESH")

  def test_refresh_before_execution_reseeks_by_pin_pair_when_stopped_and_line_count_changes(self):
    with tempfile.TemporaryDirectory() as tempDir:
      recipePath = os.path.join(tempDir, "V-layer.gc")
      calibrationPath = os.path.join(tempDir, "V_Calibration.json")

      with open(recipePath, "w", encoding="utf-8") as outputFile:
        outputFile.write("N1 G1 X1\nN2 G103 PA10 PB20\nN3 G1 X2\nN4 G103 PA30 PB40\n")
      with open(calibrationPath, "w", encoding="utf-8") as outputFile:
        outputFile.write("{}\n")

      process = object.__new__(Process)
      process.workspace = FakeWorkspaceForRefreshMessages(
        recipePath=recipePath,
        calibrationPath=calibrationPath,
      )
      process.workspace._log = FakeLog()
      process.workspace._recipeDirectory = tempDir
      process.workspace._recipeArchiveDirectory = tempDir
      process.workspace._gCodeHandler = GCodeHandler(
        _ReloadGuardFakeIO(),
        _ReloadGuardFakeCalibration(),
        None,
      )
      process.workspace._recipe = type(
        "LoadedRecipe",
        (),
        {
          "getLines": lambda self: [
            "N1 G1 X1",
            "N2 G103 PA10 PB20",
            "N3 G1 X2",
            "N4 G103 PA30 PB40",
          ]
        },
      )()
      process.workspace._gCodeHandler.loadG_Code(
        ["N1 G1 X1", "N2 G103 PA10 PB20", "N3 G1 X2", "N4 G103 PA30 PB40"],
        calibration=None,
      )
      process.workspace._gCodeHandler.setLine(3)
      process.workspace._controlStateMachine = _ReloadGuardControlStateMachine(StopMode())
      process._log = FakeLog()

      process.workspace._recipeSignature = "before"
      process.workspace._calculateRecipeSignature = lambda: "after"

      with open(recipePath, "w", encoding="utf-8") as outputFile:
        outputFile.write(
          "N1 G1 X1\nN2 G103 PA10 PB20\nN3 G1 X2\nN4 G1 X3\nN5 G103 PA30 PB40\nN6 G1 X4\n"
        )

      result = process._refreshCalibrationBeforeExecution()

      self.assertIsNone(result)
      self.assertEqual(process.workspace._gCodeHandler.getLine(), 4)
      self.assertEqual(len(process._log.entries), 0)

  def test_extract_pin_pair_supports_anchor_to_target_lines(self):
    process = object.__new__(Process)
    process.workspace = FakeWorkspaceForRefreshMessages(
      recipePath="C:/recipes/U-layer.gc",
      calibrationPath="C:/config/APA/U_Calibration.json",
    )

    result = process.workspace._extractPinPair(
      "N42 ~anchorToTarget(PA1601,PB1201,offset=(0,3.5),hover=True) (Foot B corner)"
    )

    self.assertEqual(result, ("anchorToTarget", "A1601", "B1201"))

  def test_refresh_before_execution_reseeks_anchor_to_target_by_pin_pair_when_line_count_matches(self):
    with tempfile.TemporaryDirectory() as tempDir:
      recipePath = os.path.join(tempDir, "U-layer.gc")
      calibrationPath = os.path.join(tempDir, "U_Calibration.json")

      originalLines = [
        "N1 ~goto(1,0)",
        "N2 ~anchorToTarget(A1601,B1201) (Foot B corner)",
        "N3 ~increment(-1,0)",
        "N4 ~anchorToTarget(B1201,B2001) (Top B corner - foot end)",
      ]
      reloadedLines = [
        "N1 ~goto(1,0)",
        "N2 ~anchorToTarget(B1201,B2001) (Top B corner - foot end)",
        "N3 ~increment(-1,0)",
        "N4 ~anchorToTarget(A1601,B1201) (Foot B corner)",
      ]

      with open(recipePath, "w", encoding="utf-8") as outputFile:
        outputFile.write("\n".join(originalLines) + "\n")
      with open(calibrationPath, "w", encoding="utf-8") as outputFile:
        outputFile.write("{}\n")

      process = object.__new__(Process)
      process.workspace = FakeWorkspaceForRefreshMessages(
        recipePath=recipePath,
        calibrationPath=calibrationPath,
      )
      process.workspace._log = FakeLog()
      process.workspace._recipeDirectory = tempDir
      process.workspace._recipeArchiveDirectory = tempDir
      process.workspace._gCodeHandler = GCodeHandler(
        _ReloadGuardFakeIO(),
        _ReloadGuardFakeCalibration(),
        None,
      )
      process.workspace._recipe = type(
        "LoadedRecipe",
        (),
        {"getLines": lambda self: list(originalLines)},
      )()
      process.workspace._gCodeHandler.loadG_Code(originalLines, calibration=None)
      process.workspace._gCodeHandler.setLine(1)
      process.workspace._controlStateMachine = _ReloadGuardControlStateMachine(StopMode())
      process._log = FakeLog()

      process.workspace._recipeSignature = "before"
      process.workspace._calculateRecipeSignature = lambda: "after"

      with open(recipePath, "w", encoding="utf-8") as outputFile:
        outputFile.write("\n".join(reloadedLines) + "\n")

      result = process._refreshCalibrationBeforeExecution()

      self.assertIsNone(result)
      self.assertEqual(process.workspace._gCodeHandler.getLine(), 3)
      self.assertEqual(len(process._log.entries), 0)

  def test_refresh_before_execution_anchor_to_target_uses_last_pin_pair_when_current_line_has_none(self):
    with tempfile.TemporaryDirectory() as tempDir:
      recipePath = os.path.join(tempDir, "U-layer.gc")
      calibrationPath = os.path.join(tempDir, "U_Calibration.json")

      originalLines = [
        "N1 ~goto(1,0)",
        "N2 ~anchorToTarget(A1601,B1201) (Foot B corner)",
        "N3 ~increment(-1,0)",
        "N4 ~anchorToTarget(B1201,B2001) (Top B corner - foot end)",
      ]
      reloadedLines = [
        "N1 ~goto(1,0)",
        "N2 ~anchorToTarget(B1201,B2001) (Top B corner - foot end)",
        "N3 ~anchorToTarget(A1601,B1201) (Foot B corner)",
        "N4 ~increment(-1,0)",
      ]

      with open(recipePath, "w", encoding="utf-8") as outputFile:
        outputFile.write("\n".join(originalLines) + "\n")
      with open(calibrationPath, "w", encoding="utf-8") as outputFile:
        outputFile.write("{}\n")

      process = object.__new__(Process)
      process.workspace = FakeWorkspaceForRefreshMessages(
        recipePath=recipePath,
        calibrationPath=calibrationPath,
      )
      process.workspace._log = FakeLog()
      process.workspace._recipeDirectory = tempDir
      process.workspace._recipeArchiveDirectory = tempDir
      process.workspace._gCodeHandler = GCodeHandler(
        _ReloadGuardFakeIO(),
        _ReloadGuardFakeCalibration(),
        None,
      )
      process.workspace._recipe = type(
        "LoadedRecipe",
        (),
        {"getLines": lambda self: list(originalLines)},
      )()
      process.workspace._gCodeHandler.loadG_Code(originalLines, calibration=None)
      process.workspace._gCodeHandler.setLine(2)
      process.workspace._controlStateMachine = _ReloadGuardControlStateMachine(StopMode())
      process._log = FakeLog()

      process.workspace._recipeSignature = "before"
      process.workspace._calculateRecipeSignature = lambda: "after"

      with open(recipePath, "w", encoding="utf-8") as outputFile:
        outputFile.write("\n".join(reloadedLines) + "\n")

      result = process._refreshCalibrationBeforeExecution()

      self.assertIsNone(result)
      self.assertEqual(process.workspace._gCodeHandler.getLine(), 2)
      self.assertEqual(len(process._log.entries), 0)

  def test_refresh_before_execution_returns_actionable_missing_calibration_message(self):
    from dune_winder.core.winder_workspace import WinderWorkspace

    process = object.__new__(Process)
    process.workspace = FakeWorkspaceForRefreshMessages(
      recipePath="C:/recipes/V-layer.gc",
      calibrationPath="C:/config/APA/V_Calibration.json",
    )
    process.workspace._recipeFile = None
    process.workspace._recipe = None
    process._log = FakeLog()

    result = process._refreshCalibrationBeforeExecution()

    self.assertEqual(
      result,
      WinderWorkspace._missingCalibrationMessage(
        process.workspace,
        "C:/config/APA/V_Calibration.json",
      ),
    )
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


class _ControlStateMachineForEOTRecover:
  class States:
    STOP = "STOP"

  def __init__(self):
    self.changed_to = []

  def changeState(self, state):
    self.changed_to.append(state)
    return False


class _PLCLogicForEOTRecover:
  def __init__(self):
    self.calls = 0

  def recoverEOT(self):
    self.calls += 1


class _IOForEOTRecover:
  def __init__(self):
    self.plcLogic = _PLCLogicForEOTRecover()


class _GCodeHandlerForManualGCode:
  def __init__(self):
    self.lines = []
    self.skipFlags = []

  def executeG_CodeLine(self, line, skip_before_execute_callback=False):
    self.lines.append(line)
    self.skipFlags.append(skip_before_execute_callback)
    return None


class _ManualModeState:
  pass


class _IdleStopState:
  pass


class _PLCLogicBlocker:
  def getReadinessBlocker(self):
    return {
      "state": "READY",
      "moveType": "RESET",
      "queuedSafeZMove": {"kind": "z", "position": 418.0},
    }


class _HeadBlocker:
  def getReadinessBlocker(self):
    return {
      "state": "LATCHING",
      "transfer": {
        "stagePresent": True,
        "fixedPresent": True,
        "stageLatched": False,
        "fixedLatched": True,
        "actuatorPos": 3,
      },
    }


class _ControlStateMachineNotReady:
  def __init__(self):
    self.state = _ManualModeState()
    self.stopMode = type("StopMode", (), {})()
    self.stopMode.stopStateMachine = type("StopStateMachine", (), {})()
    self.stopMode.stopStateMachine.state = _IdleStopState()

  def isReadyForMovement(self):
    return False


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

    safety = object.__new__(SafetyValidationService)
    safety._io = process._io
    safety._controlStateMachine = process.controlStateMachine
    safety._maxVelocity = 300.0
    safety._maxSlowVelocity = 50.0
    safety._transferLeft = -1000.0
    safety._transferRight = 10000.0
    safety._limitLeft = -1000.0
    safety._limitRight = 10000.0
    safety._limitTop = 10000.0
    safety._limitBottom = -1000.0
    safety._zlimitFront = 0.0
    safety._zlimitRear = 100.0
    safety._headwardPivotX = 150.0
    safety._headwardPivotY = 1400.0
    safety._headwardPivotXTolerance = 150.0
    safety._headwardPivotYTolerance = 300.0
    safety._transferLeftMargin = 10.0
    safety._transferYThreshold = 1000.0
    safety._queuedMotionZCollisionThreshold = 100.0
    safety._arcMaxStepRad = 0.05235987755982989
    safety._arcMaxChord = 5.0
    safety._apaCollisionBottomY = 50.0
    safety._apaCollisionTopY = 2250.0
    safety._transferZoneHeadMinX = 400.0
    safety._transferZoneHeadMaxX = 500.0
    safety._transferZoneFootMinX = 7100.0
    safety._transferZoneFootMaxX = 7200.0
    safety._supportCollisionBottomMinY = 80.0
    safety._supportCollisionBottomMaxY = 450.0
    safety._supportCollisionMiddleMinY = 1050.0
    safety._supportCollisionMiddleMaxY = 1550.0
    safety._supportCollisionTopMinY = 2200.0
    safety._supportCollisionTopMaxY = 2650.0
    safety._geometryEpsilon = 1e-9
    process._safety = safety
    process._xBacklash = XBacklashCompensation(2.0)
    process._motion = MotionService(
      process._io, process._log, process.controlStateMachine,
      safety, process.gCodeHandler, None, process._xBacklash,
      lambda: None,
    )

    return process

  def test_execute_manual_gcode_accepts_x_only_and_keeps_current_y(self):
    process = self._build_process_for_manual_gcode(x_position=11.0, y_position=22.0)

    error = process.executeG_CodeLine("X4")

    self.assertIsNone(error)
    self.assertEqual(process.gCodeHandler.lines, ["X4 Y22.0"])
    self.assertEqual(process.gCodeHandler.skipFlags, [True])
    self.assertEqual(len(process.controlStateMachine.events), 1)
    self.assertIsInstance(process.controlStateMachine.events[0], ManualModeEvent)
    self.assertTrue(process.controlStateMachine.events[0].executeGCode)

  def test_execute_manual_gcode_accepts_y_only_and_keeps_current_x(self):
    process = self._build_process_for_manual_gcode(x_position=11.0, y_position=22.0)

    error = process.executeG_CodeLine("Y3")

    self.assertIsNone(error)
    self.assertEqual(process.gCodeHandler.lines, ["Y3 X11.0"])

  def test_execute_manual_gcode_uses_effective_x_for_y_only_move(self):
    process = self._build_process_for_manual_gcode(x_position=11.0, y_position=22.0)
    process._xBacklash.setBacklashMm(2.0)
    process._xBacklash.noteCommand(0.0, 5.0)

    error = process.executeG_CodeLine("Y3")

    self.assertIsNone(error)
    self.assertEqual(process.gCodeHandler.lines, ["Y3 X9.0"])

  def test_execute_manual_gcode_accepts_feed_only_without_movement(self):
    process = self._build_process_for_manual_gcode(x_position=11.0, y_position=22.0)

    error = process.executeG_CodeLine("F120")

    self.assertIsNone(error)
    self.assertEqual(process.gCodeHandler.lines, ["F120"])

  def test_execute_manual_gcode_accepts_z_move_with_feed(self):
    process = self._build_process_for_manual_gcode(x_position=11.0, y_position=22.0)

    error = process.executeG_CodeLine("Z42 F1")

    self.assertIsNone(error)
    self.assertEqual(process.gCodeHandler.lines, ["Z42 F1"])

  def test_execute_manual_gcode_accepts_feed_before_z_move(self):
    process = self._build_process_for_manual_gcode(x_position=11.0, y_position=22.0)

    error = process.executeG_CodeLine("F1 Z42")

    self.assertIsNone(error)
    self.assertEqual(process.gCodeHandler.lines, ["F1 Z42"])

  def test_execute_manual_gcode_accepts_xz_move(self):
    process = self._build_process_for_manual_gcode(x_position=11.0, y_position=22.0)

    error = process.executeG_CodeLine("X4 Z6")

    self.assertIsNone(error)
    self.assertEqual(process.gCodeHandler.lines, ["X4 Z6"])

  def test_execute_manual_gcode_accepts_four_digit_feed(self):
    process = self._build_process_for_manual_gcode(x_position=11.0, y_position=22.0)
    process._safety._maxVelocity = 1200.0

    error = process.executeG_CodeLine("A1200")

    self.assertIsNone(error)
    self.assertEqual(process.gCodeHandler.lines, ["A1200"])

  def test_execute_manual_gcode_rejects_feed_above_max_velocity(self):
    process = self._build_process_for_manual_gcode(x_position=11.0, y_position=22.0)

    error = process.executeG_CodeLine("A301")

    self.assertIn("Invalid F-axis Speed, exceeding limit", error)
    self.assertEqual(process.gCodeHandler.lines, [])

  def test_execute_manual_gcode_rejects_pivot_keepout_crossing(self):
    process = self._build_process_for_manual_gcode(x_position=400.0, y_position=1400.0)

    error = process.executeG_CodeLine("X100 Y1400")

    self.assertIn("pivot keepout", error)
    self.assertEqual(process.gCodeHandler.lines, [])

  def test_execute_manual_gcode_reports_specific_blockers_when_not_ready(self):
    process = self._build_process_for_manual_gcode()
    process.controlStateMachine = _ControlStateMachineNotReady()
    process._safety._controlStateMachine = process.controlStateMachine
    process._io.plcLogic = _PLCLogicBlocker()
    process._io.head = _HeadBlocker()

    error = process.executeG_CodeLine("X4")

    self.assertIn("control=_ManualModeState", error)
    self.assertIn("stop=_IdleStopState", error)
    self.assertIn("plc=READY,move=RESET,queued_safe_z", error)
    self.assertIn(
      "head=LATCHING,transfer=stagePresent=True,fixedPresent=True,"
      "stageLatched=False,fixedLatched=True,actuatorPos=3",
      error,
    )
    self.assertEqual(process.gCodeHandler.lines, [])

  def test_manual_seek_xy_rejects_out_of_bounds_target(self):
    process = self._build_process_for_manual_gcode(x_position=10.0, y_position=20.0)
    process._safety._limitLeft = 0.0
    process._safety._limitRight = 100.0
    process._safety._limitBottom = 0.0
    process._safety._limitTop = 100.0

    isError = process.manualSeekXY(xPosition=120.0, yPosition=20.0)

    self.assertTrue(isError)
    self.assertEqual(process.gCodeHandler.lines, [])
    self.assertEqual(process.controlStateMachine.events, [])

  def test_manual_seek_xy_rejects_pivot_keepout_crossing(self):
    process = self._build_process_for_manual_gcode(x_position=400.0, y_position=1400.0)

    isError = process.manualSeekXY(xPosition=100.0, yPosition=1400.0)

    self.assertTrue(isError)
    self.assertEqual(process.controlStateMachine.events, [])

  def test_manual_seek_xy_accepts_safe_target(self):
    process = self._build_process_for_manual_gcode(x_position=400.0, y_position=100.0)

    isError = process.manualSeekXY(xPosition=500.0, yPosition=200.0)

    self.assertFalse(isError)
    self.assertEqual(len(process.controlStateMachine.events), 1)
    self.assertIsInstance(process.controlStateMachine.events[0], ManualModeEvent)
    self.assertEqual(process.controlStateMachine.events[0].seekX, 502.0)
    self.assertEqual(process.controlStateMachine.events[0].seekY, 200.0)

  def test_manual_seek_xy_reversal_uses_unbiased_raw_target(self):
    process = self._build_process_for_manual_gcode(x_position=112.0, y_position=100.0)
    process._xBacklash.setBacklashMm(2.0)
    process._xBacklash.noteCommand(100.0, 110.0)

    isError = process.manualSeekXY(xPosition=109.0, yPosition=200.0)

    self.assertFalse(isError)
    self.assertEqual(process.controlStateMachine.events[0].seekX, 109.0)

  def test_manual_seek_xy_skips_sub_resolution_noop_without_entering_manual_mode(self):
    process = self._build_process_for_manual_gcode(x_position=112.0, y_position=100.0)
    process._xBacklash.setBacklashMm(2.0)
    process._xBacklash.noteCommand(100.0, 110.0)

    isError = process.manualSeekXY(xPosition=110.02, yPosition=100.03)

    self.assertFalse(isError)
    self.assertEqual(process.controlStateMachine.events, [])

  def test_get_real_x_position_uses_backlash_compensated_x(self):
    process = self._build_process_for_manual_gcode(x_position=112.0, y_position=100.0)
    process._xBacklash.setBacklashMm(2.0)
    process._xBacklash.noteCommand(100.0, 110.0)

    self.assertEqual(process.getRealXPosition(), 110.0)


class MotionServiceTests(unittest.TestCase):
  def test_recover_eot_returns_control_state_machine_to_stop_mode(self):
    io = _IOForEOTRecover()
    control = _ControlStateMachineForEOTRecover()
    service = MotionService(
      io,
      FakeLog(),
      control,
      safety=None,
      gCodeHandler=None,
      headCompensation=None,
      xBacklash=None,
      workspaceGetter=lambda: None,
    )

    service.recoverEOT()

    self.assertEqual(io.plcLogic.calls, 1)
    self.assertEqual(control.changed_to, ["STOP"])
