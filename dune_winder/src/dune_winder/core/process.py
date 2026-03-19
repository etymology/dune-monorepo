###############################################################################
# Name: Process.py
# Uses: High-level process control.
# Date: 2016-03-01
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

import os
import re
import math
import sys
import subprocess
from dune_winder.library.Geometry.location import Location

from dune_winder.gcode.handler import GCodeHandler
from dune_winder.core.control_state_machine import ControlStateMachine
from dune_winder.core.control_events import (
  CalibrationModeEvent,
  ManualModeEvent,
  SetLoopModeEvent,
  SetManualJoggingEvent,
  StartWindEvent,
  StopMotionEvent,
)
from dune_winder.core.camera_calibration import CameraCalibration
from dune_winder.core.manual_calibration import ManualCalibration
from dune_winder.core.winder_workspace import WinderWorkspace
from dune_winder.recipes.v_template_recipe import VTemplateRecipe
from dune_winder.recipes.u_template_recipe import UTemplateRecipe

from dune_winder.machine.head_compensation import WirePathModel
from dune_winder.machine.geometry.factory import create_layer_geometry
from dune_winder.machine.geometry.layer_functions import LayerFunctions
from dune_winder.machine.calibration.defaults import DefaultLayerCalibration

from dune_winder.io.maps.base_io import BaseIO
from dune_winder.library.log import Log
from dune_winder.library.app_config import AppConfig
from dune_winder.library.time_source import TimeSource
from dune_winder.machine.settings import Settings
from dune_winder.machine.calibration.machine import MachineCalibration
from dune_winder.io.primitives.digital_input import DigitalInput
from dune_winder.queued_motion.safety import (
  MotionSafetyLimits,
  validate_xy_move_within_safety_limits,
)


class Process:
  # ---------------------------------------------------------------------
  def __init__(
    self,
    io: BaseIO,
    log: Log,
    configuration: AppConfig,
    systemTime: TimeSource,
    machineCalibration: MachineCalibration,
  ):
    """
    Constructor.

    Args:
      io: Instance of I/O map.
      log: Log file to write state changes.
      configuration: Instance of AppConfig.
      systemTime: Instance of TimeSource.
      machineCalibration: Machine calibration instance.
    """
    self._io = io
    self._log = log
    self._configuration = configuration
    self._systemTime = systemTime

    self.controlStateMachine = ControlStateMachine(io, log, systemTime)
    self.headCompensation = WirePathModel(machineCalibration)

    self.workspace = None

    # path = self._configuration.get("workspaceLogDirectory")
    # if not os.path.exists(path):
    #   os.makedirs(path)

    # path = self._configuration.get("recipeArchiveDirectory")
    # if not os.path.exists(path):
    #   os.makedirs(path)

    path = Settings.RECIPE_DIR
    if not os.path.exists(path):
      raise Exception("Recipe directory (" + path + ") does not exist.")

    self._workspaceDirectory = Settings.CACHE_DIR
    self._workspaceCalibrationDirectory = Settings.APA_CALIBRATION_DIR

    if not os.path.isdir(self._workspaceDirectory):
      os.makedirs(self._workspaceDirectory)

    self.gCodeHandler = GCodeHandler(
      io, machineCalibration, self.headCompensation, configuration=configuration
    )
    self.gCodeHandler.setBeforeExecuteLineCallback(self._refreshCalibrationBeforeExecution)
    self.controlStateMachine.gCodeHandler = self.gCodeHandler

    self._maxVelocity = float(configuration.maxVelocity)
    self._maxSlowVelocity = float(configuration.maxSlowVelocity)

    # Setup initial limits on velocity and acceleration.
    io.plcLogic.setupLimits(
      self._maxVelocity,
      float(configuration.maxAcceleration),
      float(configuration.maxDeceleration),
    )

    self._cameraURL = configuration.cameraURL

    # Setup extended/retracted positions for head.
    io.head.setExtendedAndRetracted(machineCalibration.zFront, machineCalibration.zBack)

    # By default, the G-Code handler will use maximum velocity.
    self.gCodeHandler.setLimitVelocity(self._maxVelocity)

    # Set the limits to prevent manually inputting wrong coordinate values
    self._machineCalibration = machineCalibration
    self._transferLeft = self._calibration_float("transferLeft", 0.0)
    self._transferRight = self._calibration_float("transferRight", 0.0)
    self._transferLeftMargin = self._calibration_float("transferLeftMargin", 10.0)
    self._transferYThreshold = self._calibration_float("transferYThreshold", 1000.0)
    self._limitLeft = self._calibration_float("limitLeft", 0.0)
    self._limitRight = self._calibration_float("limitRight", 0.0)
    self._limitTop = self._calibration_float("limitTop", 0.0)
    self._limitBottom = self._calibration_float("limitBottom", 0.0)
    self._zlimitFront = self._calibration_float("zLimitFront", 0.0)
    self._zlimitRear = self._calibration_float("zLimitRear", 0.0)
    self._queuedMotionZCollisionThreshold = self._calibration_float(
      "queuedMotionZCollisionThreshold", self._calibration_float("zBack", 0.0)
    )
    self._arcMaxStepRad = self._calibration_float("arcMaxStepRad", math.radians(3.0))
    self._arcMaxChord = self._calibration_float("arcMaxChord", 5.0)
    self._apaCollisionBottomY = self._calibration_float("apaCollisionBottomY", 50.0)
    self._apaCollisionTopY = self._calibration_float("apaCollisionTopY", 2250.0)
    self._transferZoneHeadMinX = self._calibration_float("transferZoneHeadMinX", 400.0)
    self._transferZoneHeadMaxX = self._calibration_float("transferZoneHeadMaxX", 500.0)
    self._transferZoneFootMinX = self._calibration_float("transferZoneFootMinX", 7100.0)
    self._transferZoneFootMaxX = self._calibration_float("transferZoneFootMaxX", 7200.0)
    self._supportCollisionBottomMinY = self._calibration_float(
      "supportCollisionBottomMinY", 80.0
    )
    self._supportCollisionBottomMaxY = self._calibration_float(
      "supportCollisionBottomMaxY", 450.0
    )
    self._supportCollisionMiddleMinY = self._calibration_float(
      "supportCollisionMiddleMinY", 1050.0
    )
    self._supportCollisionMiddleMaxY = self._calibration_float(
      "supportCollisionMiddleMaxY", 1550.0
    )
    self._supportCollisionTopMinY = self._calibration_float(
      "supportCollisionTopMinY", 2200.0
    )
    self._supportCollisionTopMaxY = self._calibration_float(
      "supportCollisionTopMaxY", 2650.0
    )
    self._geometryEpsilon = self._calibration_float("geometryEpsilon", 1e-9)
    self._headwardPivotX = self._calibration_float("headwardPivotX", 150.0)
    self._headwardPivotY = self._calibration_float("headwardPivotY", 1400.0)
    self._headwardPivotXTolerance = self._calibration_float(
      "headwardPivotXTolerance", 150.0
    )
    self._headwardPivotYTolerance = self._calibration_float(
      "headwardPivotYTolerance", 300.0
    )

    self.cameraCalibration = CameraCalibration(io)
    self.cameraCalibration.pixelsPer_mm(configuration.pixelsPer_mm)
    self.manualCalibration = ManualCalibration(self)
    self.vTemplateRecipe = VTemplateRecipe(self)
    self.uTemplateRecipe = UTemplateRecipe(self)

    self.controlStateMachine.cameraCalibration = self.cameraCalibration
    self.controlStateMachine.machineCalibration = self._machineCalibration

  # ---------------------------------------------------------------------
  def _calibration_float(self, key, default):
    value = None
    try:
      value = self._machineCalibration.get(key)
    except Exception:
      value = None

    if value is None:
      self._machineCalibration.set(key, default)
      value = default

    return float(value)

  # ---------------------------------------------------------------------
  def _current_motion_safety_limits(self):
    return MotionSafetyLimits(
      limit_left=float(self._limitLeft),
      limit_right=float(self._limitRight),
      limit_bottom=float(self._limitBottom),
      limit_top=float(self._limitTop),
      transfer_left=float(self._transferLeft),
      transfer_right=float(self._transferRight),
      transfer_left_margin=float(self._transferLeftMargin),
      transfer_y_threshold=float(self._transferYThreshold),
      headward_pivot_x=float(self._headwardPivotX),
      headward_pivot_y=float(self._headwardPivotY),
      headward_pivot_x_tolerance=float(self._headwardPivotXTolerance),
      headward_pivot_y_tolerance=float(self._headwardPivotYTolerance),
      queued_motion_z_collision_threshold=float(self._queuedMotionZCollisionThreshold),
      arc_max_step_rad=float(self._arcMaxStepRad),
      arc_max_chord=float(self._arcMaxChord),
      apa_collision_bottom_y=float(self._apaCollisionBottomY),
      apa_collision_top_y=float(self._apaCollisionTopY),
      transfer_zone_head_min_x=float(self._transferZoneHeadMinX),
      transfer_zone_head_max_x=float(self._transferZoneHeadMaxX),
      transfer_zone_foot_min_x=float(self._transferZoneFootMinX),
      transfer_zone_foot_max_x=float(self._transferZoneFootMaxX),
      support_collision_bottom_min_y=float(self._supportCollisionBottomMinY),
      support_collision_bottom_max_y=float(self._supportCollisionBottomMaxY),
      support_collision_middle_min_y=float(self._supportCollisionMiddleMinY),
      support_collision_middle_max_y=float(self._supportCollisionMiddleMaxY),
      support_collision_top_min_y=float(self._supportCollisionTopMinY),
      support_collision_top_max_y=float(self._supportCollisionTopMaxY),
      geometry_epsilon=float(self._geometryEpsilon),
    )

  # ---------------------------------------------------------------------
  def _validate_xy_move_target(self, startX, startY, targetX, targetY):
    try:
      validate_xy_move_within_safety_limits(
        (float(startX), float(startY)),
        (float(targetX), float(targetY)),
        self._current_motion_safety_limits(),
      )
    except ValueError as exception:
      return str(exception)
    return None

  # ---------------------------------------------------------------------
  def getRecipes(self):
    """
    Return a list of available recipes based on the files in the recipe
    directory.

    Returns:
      List of available recipes.
    """

    # Fetch all files in recipe directory.
    recipeList = os.listdir(Settings.RECIPE_DIR)
    # if self.workspace is not None and self.workspace.getLayer() is not None:
    #   # recipeList = os.listdir(self.workspace.getPathLayer())
    #   recipeList = [
    #     f
    #     for f in os.listdir(self.workspace.getPathLayer())
    #     if (
    #       os.path.isfile(self.workspace.getPathLayer() + f) and self.workspace.getLayer() + "_" in f
    #     )
    #   ]
    # Filter just the G-Code file extension.
    expression = re.compile(r"\.gc$")
    recipeList = [index for index in recipeList if expression.search(index)]

    return recipeList

  # ---------------------------------------------------------------------
  # def getTensionFiles(self):
  #   """
  #   Return a list of available file names based on the files in the workspace
  #   directory.

  #   Returns:
  #     List of available tension template files with name format [X,V,U,G]_*ension*.xlsx
  #   """

  #   # Fetch all files in recipe directory.
  #   tensionList = os.listdir(self._configuration.get("recipeDirectory"))
  #   if self.workspace is not None and self.workspace.getLayer() is not None:
  #     # recipeList = os.listdir(self.workspace.getPathLayer())
  #     tensionList = [
  #       f
  #       for f in os.listdir(self.workspace.getPathLayer())
  #       if (
  #         os.path.isfile(self.workspace.getPathLayer() + f)
  #         and self.workspace.getLayer() + "_" in f
  #         and "ension" in f
  #       )
  #     ]

  #   # Filter just the G-Code file extension.
  #   expression = re.compile(r"\.xlsx$")
  #   tensionList = [index for index in tensionList if expression.search(index)]

  #   return tensionList

  # ---------------------------------------------------------------------
  def start(self):
    """
    Request that the winding process begin.
    """
    if self.controlStateMachine.isReadyForMovement():
      self.controlStateMachine.dispatch(StartWindEvent())

  # ---------------------------------------------------------------------
  def _refreshCalibrationBeforeExecution(self):
    """
    Refresh active runtime files if they changed on disk before line execution.

    Returns:
      None on success, or an error message string on failure.
    """
    if not self.workspace:
      return None

    try:
      self.workspace.refreshRecipeIfChanged()
      self.workspace.refreshCalibrationIfChanged()
    except Exception as exception:
      self._log.add(
        self.__class__.__name__,
        "GCODE_REFRESH",
        "Failed to refresh runtime files from disk before G-Code execution.",
        [str(exception)],
      )
      return "Failed to refresh G-Code or calibration from disk."

    return None

  # ---------------------------------------------------------------------
  def stop(self):
    """
    Request that the winding process stop.
    """
    if self.controlStateMachine.isInMotion():
      self.controlStateMachine.dispatch(StopMotionEvent())

  # ---------------------------------------------------------------------
  def stopNextLine(self):
    """
    Stop winding process after completing the next line.
    """
    if self.controlStateMachine.isInMotion() and self.gCodeHandler.isG_CodeLoaded():
      self.gCodeHandler.stopNext()

  # ---------------------------------------------------------------------
  def _getUiAxisSnapshot(self, axis):
    return {
      "functional": axis.isFunctional(),
      "moving": axis.isSeeking(),
      "desiredPosition": axis.getDesiredPosition(),
      "position": axis.getPosition(),
      "velocity": axis.getVelocity(),
      "acceleration": axis.getAcceleration(),
      "seekStartPosition": axis.getSeekStartPosition(),
    }

  # ---------------------------------------------------------------------
  def _getUiInputSnapshot(self):
    inputs = {}
    for ioPoint in DigitalInput.digital_input_instances:
      inputs[ioPoint.getName()] = ioPoint.get()

    return inputs

  # ---------------------------------------------------------------------
  def _getUiHeadSide(self):
    headSide = 0
    if self._io.Z_Stage_Present.get():
      headSide += 1

    if self._io.Z_Fixed_Present.get():
      headSide += 2

    return headSide

  # ---------------------------------------------------------------------
  def getUiSnapshot(self):
    xAxis = self._getUiAxisSnapshot(self._io.xAxis)
    yAxis = self._getUiAxisSnapshot(self._io.yAxis)
    zAxis = self._getUiAxisSnapshot(self._io.zAxis)

    headAngle = 0
    if self._io.isFunctional():
      location = Location(
        xAxis["position"],
        yAxis["position"],
        zAxis["position"],
      )
      headAngle = self.headCompensation.getHeadAngle(location)

    return {
      "axes": {
        "x": xAxis,
        "y": yAxis,
        "z": zAxis,
      },
      "headAngle": headAngle,
      "headSide": self._getUiHeadSide(),
      "inputs": self._getUiInputSnapshot(),
      "plcNotFunctional": self._io.plc.isNotFunctional(),
    }

  # ---------------------------------------------------------------------
  def getQueuedMotionPreview(self):
    return self.gCodeHandler.getQueuedMotionPreview()

  # ---------------------------------------------------------------------
  def getQueuedMotionUseMaxSpeed(self):
    return self.gCodeHandler.getQueuedMotionUseMaxSpeed()

  # ---------------------------------------------------------------------
  def setQueuedMotionUseMaxSpeed(self, enabled):
    enabled = bool(enabled)
    current = self.gCodeHandler.getQueuedMotionUseMaxSpeed()
    if current == enabled:
      return current

    current = self.gCodeHandler.setQueuedMotionUseMaxSpeed(enabled)
    self._log.add(
      self.__class__.__name__,
      "QUEUED_PREVIEW_MAX_SPEED",
      "Enabled queued-motion default maximum speed."
      if current
      else "Disabled queued-motion default maximum speed.",
    )
    return current

  # ---------------------------------------------------------------------
  def continueQueuedMotionPreview(self):
    accepted = self.gCodeHandler.continueQueuedMotionPreview()
    if accepted:
      self._log.add(
        self.__class__.__name__,
        "QUEUED_PREVIEW_CONTINUE",
        "Approved queued G113 path preview.",
      )
    return accepted

  # ---------------------------------------------------------------------
  def cancelQueuedMotionPreview(self):
    cancelled = self.gCodeHandler.cancelQueuedMotionPreview()
    if cancelled:
      self._log.add(
        self.__class__.__name__,
        "QUEUED_PREVIEW_CANCEL",
        "Cancelled queued G113 path preview before execution.",
      )
    return cancelled

  # ---------------------------------------------------------------------
  def step(self):
    """
    Run just one line of G-Code, then stop.
    """
    if (
      self.controlStateMachine.isReadyForMovement()
      and self.gCodeHandler.isG_CodeLoaded()
    ):
      self.gCodeHandler.singleStep = True
      self.controlStateMachine.dispatch(StartWindEvent())

  # ---------------------------------------------------------------------
  def acknowledgeError(self):
    """
    Request that the winding process stop.
    """
    if self._io.plcLogic.isError():
      self._log.add(
        self.__class__.__name__, "ERROR_RESET", "PLC error acknowledgment and clear."
      )

    self._io.plcLogic.reset()

  # ---------------------------------------------------------------------
  # Phil Heath (PWH)
  # Added 19/08/2021 for the PLC_Init button
  #
  # ---------------------------------------------------------------------
  def acknowledgePLC_Init(self):
    #  """
    #  Request that the winding process init.
    #  """

    print("Hello World!")
    self._io.plcLogic.PLC_init()

  # ---------------------------------------------------------------------
  def servoDisable(self):
    """
    Disable motor servo control, thus idling the axises.
    """
    if self.controlStateMachine.isInMotion():
      self._log.add(self.__class__.__name__, "SERVO", "Idling servo control.")
      self.controlStateMachine.dispatch(ManualModeEvent(idleServos=True))

  # ---------------------------------------------------------------------
  def getG_CodeList(self, center, delta):
    """
    Fetch a sub-set of the loaded G-Code self.lines.  Useful for showing what
    has recently executed, and what is to come.

    Args:
      center: Where to center the list.
      delta: Number of entries to read +/- center.

    Returns:
      List of G-Code lines, or empty list of no G-Code is loaded.
    """
    result = []
    if self.gCodeHandler.isG_CodeLoaded():
      if center is None:
        center = self.gCodeHandler.getLine()

      result = self.gCodeHandler.fetchLines(center, delta)

    return result

  # ---------------------------------------------------------------------
  def setG_CodeLine(self, line):
    """
    Set a new line number from loaded recipe to seek.

    Args:
      line: Line number.

    Returns:
      True if there was an error, False if not.
    """
    isError = True
    if self.gCodeHandler.isG_CodeLoaded():
      initialLine = self.gCodeHandler.getLine()
      isError = self.gCodeHandler.setLine(line)

      if not isError:
        self._log.add(
          self.__class__.__name__,
          "LINE",
          "G-Code line changed from " + str(initialLine) + " to " + str(line),
          [initialLine, line],
        )

    if isError:
      self._log.add(
        self.__class__.__name__,
        "LINE",
        "Unable to change G-Code line changed to " + str(line),
        [line],
      )

    return isError

  # ---------------------------------------------------------------------
  def getPositionLogging(self):
    """
    Check to see if position logging is enabled.

    Returns:
      True if position logging is enabled.
    """

    return self.gCodeHandler.isPositionLogging()

  # ---------------------------------------------------------------------
  def setPositionLogging(self, isEnabled):
    """
    Enable/disable position logging.  Test function.

    Args:
      isEnabled: True to enable logging, False to disable/stop.

    Returns:
      True if logging was enabled, False if not.
    """
    fileName = None
    if isEnabled:
      if self.workspace:
        fileName = self.workspace.getPath() + "positionLog.csv"
        self._log.add(
          self.__class__.__name__,
          "POSITION_LOGGING",
          "Position logging begins",
          [1, fileName],
        )
      else:
        self._log.add(
          self.__class__.__name__,
          "POSITION_LOGGING",
          "Position logging request ignored.  No workspace loaded.",
          [-1],
        )
    else:
      self._log.add(
        self.__class__.__name__, "POSITION_LOGGING", "Position logging ends", [0]
      )

    self.gCodeHandler.startPositionLogging(fileName)

    return self.getPositionLogging()

  # ---------------------------------------------------------------------
  def getG_CodeDirection(self):
    """
    Get the direction of G-Code execution.

    Returns:
      True for normal direction, False to run in reverse.  True if no G-Code
      is loaded.
    """
    result = True
    if self.gCodeHandler.isG_CodeLoaded():
      result = self.gCodeHandler.getDirection()

    return result

  # ---------------------------------------------------------------------
  def setG_CodeDirection(self, isForward):
    """
    Set the direction of G-Code execution.

    Args:
      isForward: True for normal direction, False to run in reverse.
    """
    isError = True
    if self.gCodeHandler.isG_CodeLoaded():
      initialDirection = self.gCodeHandler.getDirection()
      isError = self.gCodeHandler.setDirection(isForward)

      if not isError:
        self._log.add(
          self.__class__.__name__,
          "DIRECTION",
          "G-Code direction changed from "
          + str(initialDirection)
          + " to "
          + str(isForward),
          [initialDirection, isForward],
        )

    if isError:
      self._log.add(
        self.__class__.__name__,
        "LINE",
        "Unable to change G-Code direction changed to " + str(isForward),
        [isForward],
      )

    return isError

  # ---------------------------------------------------------------------
  def setG_CodeRunToLine(self, line):
    """
    Set the line number to run G-Code and then stop.
    """
    isError = True
    if self.gCodeHandler.isG_CodeLoaded():
      initialRunTo = self.gCodeHandler.runToLine
      # isError = self.gCodeHandler.setDirection( isForward )
      self.gCodeHandler.runToLine = line
      isError = False

      if not isError:
        self._log.add(
          self.__class__.__name__,
          "RUN_TO",
          "G-Code finial line changed from " + str(initialRunTo) + " to " + str(line),
          [initialRunTo, line],
        )

    if isError:
      self._log.add(
        self.__class__.__name__,
        "LINE",
        "Unable to change G-Code run to line to " + str(line),
        [line],
      )

    return isError

  # ---------------------------------------------------------------------
  def getG_CodeLoop(self):
    """
    See if G-Code should loop continuously.

    Returns:
      True if G-Code should loop.
    """
    return self.controlStateMachine.getLoopMode()

  # ---------------------------------------------------------------------
  def setG_CodeLoop(self, isLoopMode):
    """
    Specify if the G-Code should loop continuously.  Useful for testing
    but not production.

    Args:
      isLoopMode: True if G-Code should loop.
    """
    currentLoopMode = self.controlStateMachine.getLoopMode()

    self._log.add(
      self.__class__.__name__,
      "LOOP",
      "G-Code loop mode set from "
      + str(currentLoopMode)
      + " to "
      + str(isLoopMode),
      [currentLoopMode, isLoopMode],
    )

    self.controlStateMachine.dispatch(SetLoopModeEvent(isLoopMode))

  # ---------------------------------------------------------------------
  def setG_CodeVelocityScale(self, scaleFactor=1.0):
    """
    Set the velocity scale factor that limits the speed of all motions.

    Args:
      scaleFactor: New scale factor (typically between 0.0-1.0, although > 1 is
                   allowed).
    """
    self._log.add(
      self.__class__.__name__,
      "VELOCITY_SCALE",
      "G-Code velocity scale change from "
      + str(self.gCodeHandler.getVelocityScale())
      + " to "
      + str(scaleFactor),
      [self.gCodeHandler.getVelocityScale(), scaleFactor],
    )

    self.gCodeHandler.setVelocityScale(scaleFactor)

  # ---------------------------------------------------------------------
  def getWorkspaceState(self):
    if self.workspace is not None:
      return self.workspace.toDictionary()

    return WinderWorkspace.readState(self._workspaceDirectory)

  # ---------------------------------------------------------------------
  def getRecipeName(self):
    """
    Return the name of the loaded recipe.

    Returns:
      String name of the loaded recipe.  Empty string if no recipe loaded.
    """
    result = ""
    if self.workspace:
      result = self.workspace.getRecipe()

    return result

  # ---------------------------------------------------------------------
  def getRecipeLayer(self):
    """
    Return the current layer of the active workspace.

    Returns:
      String name of the current layer.  None if no recipe
      loaded.
    """
    result = None
    if self.workspace:
      result = self.workspace.getLayer()

    return result

  # ---------------------------------------------------------------------
  def getRecipePeriod(self):
    """
    Return the detected repeating line period of the loaded recipe.

    Returns:
      Integer recipe period in lines, or None if no recipe is loaded or the
      recipe does not have a detectable repeated body.
    """
    result = None
    if self.workspace:
      result = self.workspace.getRecipePeriod()

    return result

  # ---------------------------------------------------------------------
  def getWrapSeekLine(self, wrap):
    """
    Return the G-Code line index to seek to for the requested wrap number.

    Args:
      wrap: Requested wrap number (1-based).

    Returns:
      Zero-based line index suitable for setG_CodeLine(), or None if no workspace or
      recipe is loaded.
    """
    result = None
    if self.workspace:
      result = self.workspace.getWrapSeekLine(wrap)

    return result

  # ---------------------------------------------------------------------
  def _openInEditor(self, filePath):
    """
    Open the specified file path in a text editor.

    Args:
      filePath: Full path to file.

    Returns:
      True on success, False otherwise.
    """
    try:
      editor = os.environ.get("WINDER_TEXT_EDITOR")
      if editor:
        subprocess.Popen([editor, filePath])
      elif os.name == "nt":
        os.startfile(filePath)
      elif sys.platform == "darwin":
        subprocess.Popen(["open", "-t", filePath])
      else:
        subprocess.Popen(["xdg-open", filePath])
      return True
    except Exception:
      return False

  # ---------------------------------------------------------------------
  def openRecipeInEditor(self, recipeFile=None):
    """
    Open the selected/loaded G-Code recipe in a text editor.

    Args:
      recipeFile: Optional recipe file name to open.

    Returns:
      True on success, otherwise a failure message.
    """
    if not recipeFile:
      recipeFile = self.getRecipeName()
    if not recipeFile:
      return "No G-Code file selected."

    recipeDirectory = os.path.abspath(Settings.RECIPE_DIR)
    filePath = os.path.abspath(os.path.join(recipeDirectory, recipeFile))
    if not filePath.startswith(recipeDirectory + os.sep):
      return "Invalid recipe path."
    if not os.path.isfile(filePath):
      return "G-Code file not found: " + filePath

    if self._openInEditor(filePath):
      self._log.add("Process", "OPEN", "Open G-Code file in editor.", [filePath])
      return True

    return "Failed to open G-Code file."

  # ---------------------------------------------------------------------
  def openCalibrationInEditor(self):
    """
    Open the current calibration file in a text editor.

    Returns:
      True on success, otherwise a failure message.
    """
    if not self.workspace:
      return "No workspace loaded."

    filePath = self.workspace.getCalibrationFullPath()
    if not filePath:
      return "No calibration file available."

    calibrationDirectory = os.path.abspath(self._workspaceCalibrationDirectory)
    filePath = os.path.abspath(filePath)
    if not filePath.startswith(calibrationDirectory + os.sep):
      return "Invalid calibration path."
    if not os.path.isfile(filePath):
      return "Calibration file not found: " + filePath

    if self._openInEditor(filePath):
      self._log.add("Process", "OPEN", "Open calibration file in editor.", [filePath])
      return True

    return "Failed to open calibration file."

  # ---------------------------------------------------------------------
  def getForecastWrap(self):
    """
    Deprecated.
    Forecasting is now performed in the WebUI from log.getRecent() data.

    Returns:
      None
    """
    return None

  # ---------------------------------------------------------------------
  def maxVelocity(self, maxVelocity=None):
    """
    Set/get the maximum velocity used by PLC logic and G-Code handler.

    Args:
      maxVelocity: New maximum velocity (optional).

    Returns:
      Maximum velocity.
    """

    if maxVelocity is not None:
      self._maxVelocity = maxVelocity
      self._io.plcLogic.maxVelocity(maxVelocity)
      self.gCodeHandler.setLimitVelocity(maxVelocity)

    return self._maxVelocity

  # ---------------------------------------------------------------------
  def loadWorkspace(self):
    """Load the single runtime workspace from disk."""
    createNew = not os.path.isfile(
      os.path.join(self._workspaceDirectory, WinderWorkspace.FILE_NAME)
    )
    self.controlStateMachine.resetWindTime()
    self.workspace = WinderWorkspace(
      self.gCodeHandler,
      self._workspaceDirectory,
      self._workspaceCalibrationDirectory,
      Settings.RECIPE_DIR,
      Settings.RECIPE_ARCHIVE_DIR,
      self._log,
      self._systemTime,
      createNew,
    )

  # ---------------------------------------------------------------------
  def closeWorkspace(self):
    """Close the workspace and persist its state."""
    if self.workspace:
      self.workspace.addWindTime(self.controlStateMachine.getWindTime())
      self.controlStateMachine.resetWindTime()
      self.workspace.close()
      self.workspace = None

  # ---------------------------------------------------------------------
  def jogXY(self, xVelocity, yVelocity, acceleration=None, deceleration=None):
    """
    Jog the X/Y axis at a given velocity.

    Args:
      xVelocity: Speed of x axis in m/s.  Allows negative for reverse, 0 to stop.
      yVelocity: Speed of y axis in m/s.  Allows negative for reverse, 0 to stop.
      acceleration: Maximum positive acceleration.  None for default.
      deceleration: Maximum negative acceleration.  None for default.
      Safe Zone: If JogXY is working outside the _transferRight and _transferLeft regions
                 then the velocity of the Jog will be reduced to maxSlowVelocity in X and Y.
    Returns:
      True if there was an error, False if not.
    """

    isError = False
    if (
      0 != xVelocity or 0 != yVelocity
    ) and self.controlStateMachine.isReadyForMovement():
      # Current coordinates to find out if we are in Safety Zone
      x = self._io.xAxis.getPosition()
      self._io.yAxis.getPosition()
      self._io.zAxis.getPosition()
      if (
        x < self._transferLeft or x > self._transferRight
      ):  # reduce the Job velocity to maxSlowVelocity
        if xVelocity != 0:
          xVelocity = math.copysign(self._maxSlowVelocity, xVelocity)
        if yVelocity != 0:
          yVelocity = math.copysign(self._maxSlowVelocity, yVelocity)

      self._log.add(
        self.__class__.__name__,
        "JOG",
        "Jog X/Y at "
        + str(xVelocity)
        + ", "
        + str(yVelocity)
        + " m/s, "
        + str(acceleration)
        + ", "
        + str(deceleration)
        + " m/s^2.",
        [xVelocity, yVelocity, acceleration, deceleration],
      )

      self.controlStateMachine.dispatch(ManualModeEvent(isJogging=True))
      self._io.plcLogic.jogXY(xVelocity, yVelocity, acceleration, deceleration)
    elif (
      0 == xVelocity
      and 0 == yVelocity
      and self.controlStateMachine.isJogging()
    ):
      self._log.add(self.__class__.__name__, "JOG", "Jog X/Y stop.")
      self.controlStateMachine.dispatch(SetManualJoggingEvent(False))
      self._io.plcLogic.jogXY(xVelocity, yVelocity)
    else:
      isError = True
      self._log.add(
        self.__class__.__name__,
        "JOG",
        "Jog X/Y request ignored.",
        [xVelocity, yVelocity, acceleration, deceleration],
      )

    return isError

  # ---------------------------------------------------------------------
  def manualSeekXY(
    self,
    xPosition=None,
    yPosition=None,
    velocity=None,
    acceleration=None,
    deceleration=None,
  ):
    """
    Seek an X/Y location.

    Args:
      xPosition: New position in meters of x.
      yPosition: New position in meters of y.
      velocity: Maximum velocity.  None for last velocity used.
      acceleration: Maximum positive acceleration.  None for default.
      deceleration: Maximum negative acceleration.  None for default.
    Returns:
      True if there was an error, False if not.
    """

    isError = True
    if self.controlStateMachine.isReadyForMovement():
      currentX = float(self._io.xAxis.getPosition())
      currentY = float(self._io.yAxis.getPosition())
      targetX = currentX if xPosition is None else float(xPosition)
      targetY = currentY if yPosition is None else float(yPosition)

      error = self._validate_xy_move_target(currentX, currentY, targetX, targetY)
      if error is not None:
        self._log.add(
          self.__class__.__name__,
          "JOG",
          "Manual move X/Y ignored.",
          [xPosition, yPosition, velocity, acceleration, deceleration, error],
        )
      else:
        isError = False
        self._log.add(
          self.__class__.__name__,
          "JOG",
          "Manual move X/Y to ("
          + str(xPosition)
          + ", "
          + str(yPosition)
          + ") at "
          + str(velocity)
          + ", "
          + str(acceleration)
          + ", "
          + str(deceleration)
          + " m/s^2.",
          [xPosition, yPosition, velocity, acceleration, deceleration],
        )
        self.controlStateMachine.dispatch(
          ManualModeEvent(
            seekX=xPosition,
            seekY=yPosition,
            velocity=velocity,
            acceleration=acceleration,
            deceleration=deceleration,
          )
        )
    else:
      self._log.add(
        self.__class__.__name__,
        "JOG",
        "Manual move X/Y ignored.",
        [xPosition, yPosition, velocity, acceleration, deceleration],
      )

    return isError

  # ---------------------------------------------------------------------
  def manualSeekZ(self, position, velocity=None):
    """
    Seek an Z location.

    Args:
      position: New position in meters of z.
      velocity: Maximum velocity.  None for last velocity used.
    Returns:
      True if there was an error, False if not.
    """

    isError = True
    if self.controlStateMachine.isReadyForMovement():
      isError = False
      self._log.add(
        self.__class__.__name__,
        "JOG",
        "Manual move Z to " + str(position) + " at " + str(velocity) + ".",
        [position, velocity],
      )
      self.controlStateMachine.dispatch(
        ManualModeEvent(seekZ=position, velocity=velocity)
      )
    else:
      self._log.add(
        self.__class__.__name__, "JOG", "Manual move Z ignored.", [position, velocity]
      )

    return isError

  # ---------------------------------------------------------------------
  def manualHeadPosition(self, position, velocity):
    """
    Manually position the head.

    Args:
      position: One of the Head positions (RETRACTED/FRONT/BACK/EXTENDED).
      velocity: Maximum speed at which to move.

    Returns:
      True if there was an error, False if not.
    """
    isError = True

    if (
      self.controlStateMachine.isReadyForMovement()
      and self._io.head.getPosition() != position
    ):
      isError = False

      self._log.add(
        self.__class__.__name__,
        "HEAD",
        "Manual head position to " + str(position) + " at " + str(velocity) + ".",
        [position, velocity],
      )
      self.controlStateMachine.dispatch(
        ManualModeEvent(setHeadPosition=position, velocity=velocity)
      )

    else:
      self._log.add(
        self.__class__.__name__,
        "HEAD",
        "Manual head position ignored.",
        [position, velocity],
      )

    return isError

  # ---------------------------------------------------------------------
  def jogZ(self, velocity):
    """
    Jog the Z axis at a given velocity.

    Args:
      velocity: Speed of z axis in m/s.  Allows negative for reverse, 0 to stop.

    Returns:
      True if there was an error, False if not.
    """

    isError = False
    if 0 != velocity and self.controlStateMachine.isReadyForMovement():
      self._log.add(
        self.__class__.__name__, "JOG", "Jog Z at " + str(velocity) + ".", [velocity]
      )
      self.controlStateMachine.dispatch(ManualModeEvent(isJogging=True))
      self._io.plcLogic.jogZ(velocity)
    elif 0 == velocity and self.controlStateMachine.isJogging():
      self._log.add(self.__class__.__name__, "JOG", "Jog Z stop.")
      self.controlStateMachine.dispatch(SetManualJoggingEvent(False))
      self._io.plcLogic.jogZ(velocity)
    else:
      isError = True
      self._log.add(
        self.__class__.__name__, "JOG", "Jog Z request ignored.", [velocity]
      )

    return isError

  # ---------------------------------------------------------------------
  def seekPin(self, pin, velocity):
    """
    Manually seek out a pin location.

    Args:
      pin - Name of pin to seek.
      velocity: Speed of z axis in m/s.

    Returns:
      True if there was an error, False if not.
    """
    calibration = self.gCodeHandler.getLayerCalibration()

    isError = True

    # Do we have a calibration file?
    if calibration:
      # Two pins may be specified.  If they are, get both names.  If not, set
      # both names to the single name given.
      pinNameA = pin
      pinNameB = pin
      if " " in pin:
        [pinNameA, pinNameB] = pin.split(" ")

      # Does request pin exist?
      if calibration.getPinExists(pinNameA) and calibration.getPinExists(pinNameB):
        self._log.add(
          self.__class__.__name__,
          "SEEK_PIN",
          "Manual pin seek " + pin + " at " + str(velocity) + ".",
          [pin, velocity],
        )

        # Get the center of the pins.
        pinA = calibration.getPinLocation(pinNameA)
        pinB = calibration.getPinLocation(pinNameB)
        position = pinA.center(pinB)
        position = position.add(calibration.offset)

        # Run a manual seek to pin/center position.
        self.manualSeekXY(position.x, position.y, velocity)
        isError = False
      else:
        self._log.add(
          self.__class__.__name__,
          "SEEK_PIN",
          "Manual pin seek request ignored--pin(s) does not exist.",
          [pin, velocity],
        )
    else:
      self._log.add(
        self.__class__.__name__,
        "SEEK_PIN",
        "Manual pin seek request ignored--no calibration loaded.",
        [pin, velocity],
      )

    return isError

  # ---------------------------------------------------------------------
  def seekPinNominal(self, pin, velocity):
    """
    Seek out the nominal pin location.
    Useful for calibration scan setup.

    Args:
      pin - Name of pin to seek.
      velocity: Speed of z axis in m/s.

    Returns:
      True if there was an error, False if not.
    """
    isError = True
    if self.workspace:
      # Get the name of this layer.
      layer = self.workspace.getLayer()

      # Get the default calibration for this layer.
      calibration = DefaultLayerCalibration(None, None, layer)

      # Does request pin exist?
      if calibration.getPinExists(pin):
        self._log.add(
          self.__class__.__name__,
          "SEEK_PIN_NOMINAL",
          "Nominal pin seek " + pin + " at " + str(velocity) + ".",
          [pin, velocity],
        )

        # Get the center of the pins.
        position = calibration.getPinLocation(pin)
        position = position.add(calibration.offset)

        # Run a manual seek to pin position.
        self.manualSeekXY(position.x, position.y, velocity)
        isError = False
      else:
        self._log.add(
          self.__class__.__name__,
          "SEEK_PIN_NOMINAL",
          "Nominal pin seek request ignored--pin(s) does not exist.",
          [pin, velocity],
        )
    else:
      self._log.add(
        self.__class__.__name__,
        "SEEK_PIN_NOMINAL",
        "Nominal pin seek request ignored--no workspace loaded.",
        [pin, velocity],
      )

    return isError

  # ---------------------------------------------------------------------
  def setAnchorPoint(self, pinA, pinB=None):
    """
    Specify the anchor point--location where the wire is assume to be fixed.

    Args:
      pinA - Pin name.  First name when using pin centering.
      pinB - Pin name.  Second name for pin centering, omit to use just one pin.
    """
    calibration = self.gCodeHandler.getLayerCalibration()

    isError = True

    # Do we have a calibration file?
    if calibration:
      # Get first pin location.
      pinA = calibration.getPinLocation(pinA)

      if pinA:
        # Do we have a second pin?
        if pinB:
          # Center between two pins.
          pinB = calibration.getPinLocation(pinB)

          if pinB:
            location = pinA.center(pinB)
        else:
          # Use the specified location.
          location = pinA

        location = location.add(calibration.offset)

        self.headCompensation.anchorPoint(location)
        isError = False

    return isError

  # ---------------------------------------------------------------------
  def getHeadAngle(self):
    """
    Get the current angle of the arm based on machine position and the last
    anchor point.

    Args:
      location: Location of actual machine position.

    Returns:
      Angle of the arm (-pi to +pi).
    """

    result = 0
    if self._io.isFunctional():
      x = self._io.xAxis.getPosition()
      y = self._io.yAxis.getPosition()
      z = self._io.zAxis.getPosition()

      # $$$FUTURE - This doesn't work.  Not too important.  Fix it one day.
      # if self._io.head.BACK == self._io.head.getSide() :
      #   print "Back"
      #   z = self._io.head.getTargetAxisPosition()

      location = Location(x, y, z)

      result = self.headCompensation.getHeadAngle(location)

    return result

  # ---------------------------------------------------------------------
  def executeG_CodeLine(self, line: str):
    """
    Run a line of G-code.

    Args:
      line: G-Code to execute.

    Returns:
      Failure data.  None if there was no failure.
    """
    error = None
    if not self.controlStateMachine.isReadyForMovement():
      error = "Machine not ready."
      self._log.add(
        self.__class__.__name__,
        "MANUAL_GCODE",
        "Failed to execute manual G-Code line as machine was not ready.",
        [line],
      )

    else:
      # Check the format of the string matches a VALID PATTERN
      xy = r"(\ *[X]\d{1,4}(\.\d{1,2})?\ *[Y]\d{1,4}(\.\d{1,2})?\ *$)"  # 'X1234 Y1234','X0 Y1234'
      x_only = r"(\ *[X]\d{1,4}(\.\d{1,2})?\ *$)"  # 'X1234'
      y_only = r"(\ *[Y]\d{1,4}(\.\d{1,2})?\ *$)"  # 'Y1234'
      gxy = r"(\ *[G]105\ *[P][XY]-?\d{1,3}(\.\d{1,2})?\ *$)"  # 'G105 PX123','G105  PY123',G105  PY-12', 'G105  PX-123'
      gx_y = r"(\ *[G]105\ *[P][X]-?\d{1,3}(\.\d{1,2})?\ *[P][Y]-?\d{1,3}(\.\d{1,2})?\ *$)"  # 'G105  PX123 PY123'
      xyf = r"(\ *[X]\d{1,4}(\.\d{1,2})?\ *[Y]\d{1,4}(\.\d{1,2})?\ *[F]\d{1,4}\ *$)"  # 'X1234 Y1234 F1234'
      fxy = r"(\ *[F]\d{1,4}\ *[X]\d{1,4}(\.\d{1,2})?\ *[Y]\d{1,4}(\.\d{1,2})?\ *$)"  # 'F1234 X1234 Y1234'
      xf = r"(\ *[X]\d{1,4}(\.\d{1,2})?\ *[F]\d{1,4}\ *$)"  # 'X1234 F1234'
      fx = r"(\ *[F]\d{1,4}\ *[X]\d{1,4}(\.\d{1,2})?\ *$)"  # 'F1234 X1234'
      yf = r"(\ *[Y]\d{1,4}(\.\d{1,2})?\ *[F]\d{1,4}\ *$)"  # 'Y1234 F1234'
      fy = r"(\ *[F]\d{1,4}\ *[Y]\d{1,4}(\.\d{1,2})?\ *$)"  # 'F1234 Y1234'
      xz = r"(\ *[X]\d{1,4}(\.\d{1,2})?\ *[Z]\d{1,3}(\.\d{1,2})?\ *$)"  # 'X1234 Z123'
      xzf = r"(\ *[X]\d{1,4}(\.\d{1,2})?\ *[Z]\d{1,3}(\.\d{1,2})?\ *[F]\d{1,4}\ *$)"  # 'X1234 Z123 F1234'
      fxz = r"(\ *[F]\d{1,4}\ *[X]\d{1,4}(\.\d{1,2})?\ *[Z]\d{1,3}(\.\d{1,2})?\ *$)"  # 'F1234 X1234 Z123'
      f_only = r"(\ *[F]\d{1,4}(\.\d{1,2})?\ *$)"  # 'F1234', 'F1234.45'
      gxyf = r"(\ *[G]105\ *[P][XY]-?\d{1,3}(\.\d{1,2})?\ *[F]\d{1,4}\ *$)"  # 'G105 PX123 F1234','G105 PY123 F1234'
      gx_yf = r"(\ *[G]105\ *[P][X]-?\d{1,3}(\.\d{1,2})?\ *[P][Y]-?\d{1,3}(\.\d{1,2})?\ *[F]\d{1,4}\ *$)"  # 'G105  PX123 PY123 F1234'
      gp = r"(\ *[G]106\ *P[0123]\ *$)"  # 'G106 P0', ..., 'G106 P4'
      z_move = r"(\ *[Z]\d{1,3}(\.\d{1,2})?\ *$)"  # 'Z123' , 'Z-123' , 'Z123.45'
      absoluteXYMovePattern = "|".join([xy, x_only, y_only, xyf, fxy, xf, fx, yf, fy])
      absoluteXZMovePattern = "|".join([xz, xzf, fxz])
      relativeXYMovePattern = "|".join([gxy, gxyf, gx_y, gx_yf])
      if not re.match(
        absoluteXYMovePattern
        + "|"
        + absoluteXZMovePattern
        + "|"
        + relativeXYMovePattern
        + "|"
        + gp
        + "|"
        + f_only
        + "|"
        + z_move,
        line,
      ):
        error = (
          "Invalid G-code format or coordinates exceeding the maximun digits allowed [X1234] : "
          + line
        )

      # Check that X and Y input coordinate are within limits
      # Get the current positions
      xPosition = float(self._io.xAxis.getPosition())
      yPosition = float(self._io.yAxis.getPosition())
      self._io.zAxis.getPosition()
      codeLineSplit = line.split()
      x = xPosition
      y = yPosition
      isXYMove = re.match(absoluteXYMovePattern + "|" + relativeXYMovePattern, line)
      isXZMove = re.match(absoluteXZMovePattern, line)
      isRelativeXYMove = re.match(relativeXYMovePattern, line)

      for cmd in codeLineSplit:
        if "X" in cmd and (isXYMove or isXZMove):
          xCmd = cmd.split("X")
          x = float(xCmd[1])
          if isRelativeXYMove:
            x += xPosition

        if "Y" in cmd and isXYMove:
          yCmd = cmd.split("Y")
          y = float(yCmd[1])
          if isRelativeXYMove:
            y += yPosition

        if "F" in cmd and re.match(
          "|".join([xyf, fxy, xf, fx, yf, fy, xzf, fxz, gxyf, gx_yf, f_only]),
          line,
        ):
          velocity = float(cmd.split("F")[1])
          if velocity < 0 or velocity > self._maxVelocity:
            error = (
              "Invalid F-axis Speed, exceeding limit [0.0 , "
              + str(self._maxVelocity)
              + "]"
            )
          
        if "Z" in cmd and re.match("|".join([z_move, xz, xzf, fxz]), line):
          zCmd = cmd.split("Z")
          z_target = float(zCmd[1])
          if z_target < self._zlimitFront or z_target > self._zlimitRear:
            error = (
              "Invalid Z-axis Coordinates, exceeding limit ["
              + str(z_target)
              + " > "
              + str(self._zlimitRear)
              + "]"
            )

      if error is None and isXYMove:
        error = self._validate_xy_move_target(xPosition, yPosition, x, y)
      elif error is None and isXZMove and (x < self._limitLeft or x > self._limitRight):
        error = (
          "Invalid X-axis Coordinates, exceeding limit ["
          + str(self._limitLeft)
          + " , "
          + str(self._limitRight)
          + "]"
        )

      if error is not None:
        self._log.add(
          self.__class__.__name__,
          "MANUAL_GCODE",
          "Failed to execute manual G-Code line. Coordinates exceeding limit.",
          [line],
        )
      else:
        lineToExecute = line
        if re.match(x_only+'|'+xf+'|'+fx, line):
          lineToExecute = line.strip() + " Y" + str(yPosition)
        elif re.match(y_only+'|'+yf+'|'+fy, line):
          lineToExecute = line.strip() + " X" + str(xPosition)

        # Excute G_CodeLine
        errorData = self.gCodeHandler.executeG_CodeLine(lineToExecute)

        if errorData:
          error = errorData["message"]
          self._log.add(
            self.__class__.__name__,
            "MANUAL_GCODE",
            "Failed to execute manual G-Code line.",
            [line, error],
          )
        else:
          self.controlStateMachine.dispatch(ManualModeEvent(executeGCode=True))

          self._log.add(
            self.__class__.__name__,
            "MANUAL_GCODE",
            "Execute manual G-Code line.",
            [line],
          )

    return error

  # ---------------------------------------------------------------------
  def setCameraImageURL(self, url):
    """
    Set the URL for the camera image.  Override function for simulator.
    """
    self._cameraURL = url

  # ---------------------------------------------------------------------
  def getCameraImageURL(self):
    """
    Get the URL for the camera image.
    Returns the web-server proxy path so the browser can load it over HTTP
    (the underlying FTP URL is not loadable directly in modern browsers).
    """
    return "/camera_image"

  # ---------------------------------------------------------------------
  def startCalibrate(
    self,
    side,
    startPin,
    endPin,
    maxPins,
    deltaX,
    deltaY,
    velocity=None,
    acceleration=None,
    deceleration=None,
  ):
    """
    Begin the calibration sequence.

    Args:
      side: Front/back (F/B).
      startPin: First pin in scan.
      endPin: Last pin in scan.
      maxPin: The number of pin before wrap occurs.
      deltaX: Nominal change in X for next pin.  (Can be 0 for Y traverse.)
      deltaY: Nominal change in Y for next pin.  (Can be 0 for X traverse.)
      velocity: Maximum velocity.  None for last velocity used.
      acceleration: Maximum positive acceleration.  None for default.
      deceleration: Maximum negative acceleration.  None for default.
    """

    if not self.controlStateMachine.isReadyForMovement():
      self._log.add(
        self.__class__.__name__,
        "CALIBRATION_ERROR",
        "Calibration scan error--machine not idle.",
        [startPin, endPin, deltaX, deltaY, velocity, acceleration, deceleration],
      )
      isError = True
    else:
      # Determine direction of travel.
      pinDelta = endPin - startPin
      if pinDelta < 0:
        direction = -1
      else:
        direction = 1

      # Get the scan parameters setup.
      self.cameraCalibration.setupCalibration(side, startPin, direction, maxPins)
      self._io.camera.startScan(deltaX, deltaY)

      # Setup seek location.
      # The seek distance is the distance for the number of pins expected, plus
      # 1/2 to be sure the last pin is found.
      pinCount = abs(pinDelta)
      xPosition = self._io.xAxis.getPosition() + deltaX * (pinCount + 0.5)
      yPosition = self._io.yAxis.getPosition() + deltaY * (pinCount + 0.5)

      # Begin the seek by switching into calibration mode.
      self.controlStateMachine.dispatch(
        CalibrationModeEvent(
          seekX=xPosition,
          seekY=yPosition,
          velocity=velocity,
          acceleration=acceleration,
          deceleration=deceleration,
        )
      )

      self._log.add(
        self.__class__.__name__,
        "CALIBRATION",
        "Calibration scan from pin "
        + str(startPin)
        + " to "
        + str(endPin)
        + ".  X/Y to ("
        + str(xPosition)
        + ", "
        + str(yPosition)
        + ") at "
        + str(velocity)
        + ", "
        + str(acceleration)
        + ", "
        + str(deceleration)
        + " m/s^2.",
        [startPin, endPin, xPosition, yPosition, velocity, acceleration, deceleration],
      )

      isError = False

    return isError

  # ---------------------------------------------------------------------
  def getLayerPinGeometry(self):
    """
    Get the pin geometry for current layer.

    Returns:
      A array of two sides.  Each side is a dictionary of of what pin number is
      on each edge corner.  There are eight edge corners (4 edges, 2 sides to
      each edge).  Returns None if no workspace is loaded.
    """
    result = None
    if self.workspace is not None:
      layer = self.workspace.getLayer()
      assert layer is not None
      geometry = create_layer_geometry(layer)

      pinFront = geometry.startPinFront
      pinBack = geometry.startPinBack

      # Edges starting on bottom right and moving counter-clockwise.
      edges = ["RB", "RT", "TR", "TL", "LT", "LB", "BL", "BR"]

      front = {}
      back = {}
      frontSumX = 0
      frontSumY = 0
      backSumX = 0
      backSumY = 0
      for edgeIndex in range(0, 4):
        frontCount = geometry.gridFront[edgeIndex][0]
        frontDeltaX = geometry.gridFront[edgeIndex][1]
        frontDeltaY = geometry.gridFront[edgeIndex][2]
        backCount = geometry.gridBack[edgeIndex][0]
        backDeltaX = geometry.gridBack[edgeIndex][1]
        backDeltaY = geometry.gridBack[edgeIndex][2]

        frontSumX += geometry.gridFront[edgeIndex][3]
        frontSumY += geometry.gridFront[edgeIndex][4]
        backSumX += geometry.gridBack[edgeIndex][3]
        backSumY += geometry.gridBack[edgeIndex][4]

        # Offset between front/back side pins.
        # This is either an offset in X or Y, and really just for the U-layer.
        offsetX = backSumX - frontSumX
        offsetY = backSumY - frontSumY

        # Forward.
        edge = edges[edgeIndex * 2 + 0]
        front[edge] = [pinFront, frontDeltaX, frontDeltaY, offsetX, offsetY]
        back[edge] = [pinBack, backDeltaX, backDeltaY, -offsetX, -offsetY]

        frontCount -= 1
        frontCount *= geometry.directionFront
        backCount -= 1
        backCount *= geometry.directionBack

        pinFront = LayerFunctions.offsetPin(geometry, pinFront, frontCount)
        pinBack = LayerFunctions.offsetPin(geometry, pinBack, backCount)

        # Reverse.
        edge = edges[edgeIndex * 2 + 1]
        front[edge] = [pinFront, -frontDeltaX, -frontDeltaY, offsetX, offsetY]
        back[edge] = [pinBack, -backDeltaX, -backDeltaY, -offsetX, -offsetY]

        pinFront = LayerFunctions.offsetPin(geometry, pinFront, geometry.directionFront)
        pinBack = LayerFunctions.offsetPin(geometry, pinBack, geometry.directionBack)

      result = [front, back, geometry.pins]

    return result

  # ---------------------------------------------------------------------
  def commitCalibration(self, side, offsetX, offsetY):
    """
    Commit the scan data to the calibration file.

    Args:
      side: Front side is `0`, back side is `1`.
      offsetX: Offset in X from current side to other side.
      offsetY: Offset in Y from current side to other side.

    Returns:
      True if there was an error, False if not.
    """
    isError = True
    if self.workspace is not None:
      isError = False
      layer = self.workspace.getLayer()
      assert layer is not None
      geometry = create_layer_geometry(layer)
      calibration = self.gCodeHandler.getLayerCalibration()
      calibrationFileName = calibration.getFileName()
      cameraDataPath = self.workspace.getPath() + "Scans"

      # Create directory if it doesn't exist.
      if not os.path.exists(cameraDataPath):
        os.makedirs(cameraDataPath)

      cameraDataFile = str(self._systemTime.get())
      cameraDataFile = (
        cameraDataFile.replace(" ", "_").replace(":", "_").replace(".", "_")
      )
      cameraDataFile += ".csv"

      isFrontSide = side == 0

      self.cameraCalibration.commitCalibration(
        calibration, geometry, isFrontSide, offsetX, offsetY
      )

      cameraDataHash = self.cameraCalibration.save(cameraDataPath, cameraDataFile)
      calibration.save()
      self.workspace._useCalibration(calibration, calibrationFileName)

      self._log.add(
        self.__class__.__name__,
        "CALIBRATION_SAVED",
        "Updated calibration information from scan for layer "
        + layer
        + " to "
        + calibrationFileName
        + ".",
        [
          layer,
          calibrationFileName,
          calibration.hashValue,
          cameraDataFile,
          cameraDataHash,
        ],
      )

    return isError

  # ---------------------------------------------------------------------
  def cameraSeekCenter(self, velocity=None):
    """
    Seek to the center of the pin currently in view.
    Only useful if camera has a pin location to work with.

    Args:
      velocity: Seek velocity.

    Returns:
      True if there was an error, False if not.
    """
    isError = False
    [x, y] = self.cameraCalibration.centerCurrentLocation()
    if x is not None and y is not None:
      self.manualSeekXY(x, y, velocity)

      self._log.add(
        self.__class__.__name__,
        "PIN_CENTER",
        "Seeking pin center: " + str(x) + " " + str(y) + ".",
        [x, y],
      )
    else:
      isError = True
      self._log.add(
        self.__class__.__name__, "PIN_CENTER", "Failed to find a pin center to seek."
      )

    return isError


# end class
