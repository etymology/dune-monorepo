###############################################################################
# Name: Process.py
# Uses: High-level process control.
# Date: 2016-03-01
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from __future__ import annotations

import hashlib
import json
import os
from typing import Optional

from dune_winder.gcode.handler import GCodeHandler
from dune_winder.core.control_state_machine import ControlStateMachine
from dune_winder.core.control_events import (
  ManualModeEvent,
)
from dune_winder.core.gcode_playback_service import GCodePlaybackService
from dune_winder.core.manual_calibration import ManualCalibration, normalize_calibration
from dune_winder.core.recipe_service import RecipeService
from dune_winder.core.runtime_state_service import RuntimeStateService
from dune_winder.core.winder_workspace import WinderWorkspace
from dune_winder.recipes.v_template_recipe import VTemplateRecipe
from dune_winder.recipes.u_template_recipe import UTemplateRecipe

from dune_winder.machine.head_compensation import WirePathModel
from dune_winder.io.maps.base_io import BaseIO
from dune_winder.library.log import Log
from dune_winder.library.app_config import AppConfig
from dune_winder.library.time_source import TimeSource
from dune_winder.machine.settings import Settings
from dune_winder.machine.calibration.machine import MachineCalibration
from dune_winder.core.motion_service import MotionService
from dune_winder.core.safety_validation_service import SafetyValidationService
from dune_winder.core.x_backlash_compensation import XBacklashCompensation
from dune_winder.machine.geometry.factory import create_layer_geometry


class Process:
  # ---------------------------------------------------------------------
  def _motionService(self):
    motion = getattr(self, "_motion", None)
    if motion is None:
      motion = MotionService(
        self._io,
        self._log,
        self.controlStateMachine,
        self._safety,
        self.gCodeHandler,
        self.headCompensation,
        self._xBacklash,
        lambda: self.workspace,
      )
      self._motion = motion
    return motion

  # ---------------------------------------------------------------------
  def _playbackService(self):
    playback = getattr(self, "_playback", None)
    if playback is None:
      playback = GCodePlaybackService(
        self.gCodeHandler,
        self.controlStateMachine,
        self._log,
        self._io,
        self._safety,
        self._xBacklash,
        lambda: getattr(self, "workspace", None),
      )
      self._playback = playback
    return playback

  # ---------------------------------------------------------------------
  def _recipeService(self):
    recipe = getattr(self, "_recipe", None)
    if recipe is None:
      recipe = RecipeService(
        workspaceGetter=lambda: getattr(self, "workspace", None),
        workspaceSetter=lambda workspace: setattr(self, "workspace", workspace),
        workspaceDirectory=getattr(self, "_workspaceDirectory", Settings.CACHE_DIR),
        workspaceCalibrationDirectory=getattr(
          self, "_workspaceCalibrationDirectory", Settings.APA_CALIBRATION_DIR
        ),
        gCodeHandler=getattr(self, "gCodeHandler", None),
        log=getattr(self, "_log", None),
        systemTime=getattr(self, "_systemTime", None),
        controlStateMachine=getattr(self, "controlStateMachine", None),
        resetWindTime=getattr(getattr(self, "controlStateMachine", None), "resetWindTime", None),
        getWindTime=getattr(getattr(self, "controlStateMachine", None), "getWindTime", None),
      )
      self._recipe = recipe
    return recipe

  # ---------------------------------------------------------------------
  def _runtimeStateService(self):
    runtimeState = getattr(self, "_runtimeState", None)
    if runtimeState is None:
      runtimeState = RuntimeStateService(
        self._io,
        self.headCompensation,
        workspaceGetter=lambda: getattr(self, "workspace", None),
        workspaceStateReader=lambda: WinderWorkspace.readState(
          getattr(self, "_workspaceDirectory", Settings.CACHE_DIR)
        ),
      )
      self._runtimeState = runtimeState
    return runtimeState

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
    self._xBacklash = XBacklashCompensation(configuration.xBacklashCompensationMm)

    self.workspace: Optional[WinderWorkspace] = None

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
      io,
      machineCalibration,
      self.headCompensation,
      configuration=configuration,
      xBacklash=self._xBacklash,
    )
    self.controlStateMachine.gCodeHandler = self.gCodeHandler

    maxVelocity = float(configuration.maxVelocity)
    maxSlowVelocity = float(configuration.maxSlowVelocity)

    # Setup initial limits on velocity and acceleration.
    io.plcLogic.setupLimits(
      maxVelocity,
      float(configuration.maxAcceleration),
      float(configuration.maxDeceleration),
    )

    # Setup extended/retracted positions for head.
    io.head.setExtendedAndRetracted(machineCalibration.zFront, machineCalibration.zBack)

    # By default, the G-Code handler will use maximum velocity.
    self.gCodeHandler.setLimitVelocity(maxVelocity)

    self._machineCalibration = machineCalibration
    self._safety = SafetyValidationService(
      machineCalibration, io, self.controlStateMachine,
      maxVelocity, maxSlowVelocity,
    )
    self._motion = MotionService(
      io, log, self.controlStateMachine, self._safety,
      self.gCodeHandler, self.headCompensation, self._xBacklash,
      lambda: self.workspace,
    )
    self._playback = GCodePlaybackService(
      self.gCodeHandler, self.controlStateMachine, log, io,
      self._safety, self._xBacklash, lambda: self.workspace,
    )
    self.gCodeHandler.setBeforeExecuteLineCallback(self._playback.refreshCalibrationBeforeExecution)

    self._recipe = RecipeService(
      workspaceGetter=lambda: self.workspace,
      workspaceSetter=lambda workspace: setattr(self, "workspace", workspace),
      workspaceDirectory=self._workspaceDirectory,
      workspaceCalibrationDirectory=self._workspaceCalibrationDirectory,
      gCodeHandler=self.gCodeHandler,
      log=self._log,
      systemTime=self._systemTime,
      controlStateMachine=self.controlStateMachine,
      resetWindTime=self.controlStateMachine.resetWindTime,
      getWindTime=self.controlStateMachine.getWindTime,
    )
    self._runtimeState = RuntimeStateService(
      self._io,
      self.headCompensation,
      workspaceGetter=lambda: self.workspace,
      workspaceStateReader=lambda: WinderWorkspace.readState(self._workspaceDirectory),
    )

    self.manualCalibration = ManualCalibration(self)
    self.vTemplateRecipe = VTemplateRecipe(self)
    self.uTemplateRecipe = UTemplateRecipe(self)

    self.controlStateMachine.machineCalibration = self._machineCalibration

  # ---------------------------------------------------------------------
  def _validate_xy_move_target(self, startX, startY, targetX, targetY):
    return self._safety.validate_xy_move_target(startX, startY, targetX, targetY)

  # ---------------------------------------------------------------------
  def getRecipes(self):
    return self._recipeService().getRecipes()

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
    self._playbackService().start()

  # ---------------------------------------------------------------------
  def stop(self):
    self._playbackService().stop()

  # ---------------------------------------------------------------------
  def stopNextLine(self):
    self._playbackService().stopNextLine()

  # ---------------------------------------------------------------------
  def getUiSnapshot(self):
    return self._runtimeStateService().getUiSnapshot()

  # ---------------------------------------------------------------------
  def getQueuedMotionPreview(self):
    return self._playbackService().getQueuedMotionPreview()

  # ---------------------------------------------------------------------
  def getQueuedMotionUseMaxSpeed(self):
    return self._playbackService().getQueuedMotionUseMaxSpeed()

  # ---------------------------------------------------------------------
  def setQueuedMotionUseMaxSpeed(self, enabled):
    return self._playbackService().setQueuedMotionUseMaxSpeed(enabled)

  # ---------------------------------------------------------------------
  def continueQueuedMotionPreview(self):
    return self._playbackService().continueQueuedMotionPreview()

  # ---------------------------------------------------------------------
  def cancelQueuedMotionPreview(self):
    return self._playbackService().cancelQueuedMotionPreview()

  # ---------------------------------------------------------------------
  def step(self):
    self._playbackService().step()

  # ---------------------------------------------------------------------
  def _refreshCalibrationBeforeExecution(self):
    if not hasattr(self, "gCodeHandler"):
      workspace = getattr(self, "workspace", None)
      if not workspace:
        return None

      try:
        workspace.refreshRecipeIfChanged()
        workspace.refreshCalibrationIfChanged()
      except Exception as exception:
        self._log.add(
          "GCodePlaybackService",
          "GCODE_REFRESH",
          "Failed to refresh runtime files from disk before G-Code execution.",
          [str(exception)],
        )
        return str(exception)
      return None

    return self._playbackService().refreshCalibrationBeforeExecution()

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
    self._motionService().servoDisable()

  # ---------------------------------------------------------------------
  def eotRecover(self):
    self._motionService().recoverEOT()

  # ---------------------------------------------------------------------
  def getG_CodeList(self, center, delta):
    return self._playbackService().getG_CodeList(center, delta)

  # ---------------------------------------------------------------------
  def setG_CodeLine(self, line):
    return self._playbackService().setG_CodeLine(line)

  # ---------------------------------------------------------------------
  def getPositionLogging(self):
    return self._playbackService().getPositionLogging()

  # ---------------------------------------------------------------------
  def setPositionLogging(self, isEnabled):
    return self._playbackService().setPositionLogging(isEnabled)

  # ---------------------------------------------------------------------
  def getG_CodeDirection(self):
    return self._playbackService().getG_CodeDirection()

  # ---------------------------------------------------------------------
  def setG_CodeDirection(self, isForward):
    return self._playbackService().setG_CodeDirection(isForward)

  # ---------------------------------------------------------------------
  def setG_CodeRunToLine(self, line):
    return self._playbackService().setG_CodeRunToLine(line)

  # ---------------------------------------------------------------------
  def getG_CodeLoop(self):
    return self._playbackService().getG_CodeLoop()

  # ---------------------------------------------------------------------
  def setG_CodeLoop(self, isLoopMode):
    return self._playbackService().setG_CodeLoop(isLoopMode)

  # ---------------------------------------------------------------------
  def setG_CodeVelocityScale(self, scaleFactor=1.0):
    return self._playbackService().setG_CodeVelocityScale(scaleFactor)

  # ---------------------------------------------------------------------
  def getWorkspaceState(self):
    return self._runtimeStateService().getWorkspaceState()

  # ---------------------------------------------------------------------
  def getRecipeName(self):
    return self._recipeService().getRecipeName()

  # ---------------------------------------------------------------------
  def getRecipeLayer(self):
    return self._recipeService().getRecipeLayer()

  # ---------------------------------------------------------------------
  def getRecipePeriod(self):
    return self._recipeService().getRecipePeriod()

  def getLayerCalibration(self):
    return self._playbackService().getLayerCalibration()

  # ---------------------------------------------------------------------
  def getWrapSeekLine(self, wrap):
    return self._recipeService().getWrapSeekLine(wrap)

  # ---------------------------------------------------------------------
  def _getActiveLayerCalibration(self, layer):
    requestedLayer = str(layer).strip().upper()
    activeLayer = self.getRecipeLayer()
    if activeLayer != requestedLayer:
      raise ValueError(
        "Requested layer " + requestedLayer
        + " does not match active loaded recipe layer "
        + str(activeLayer) + "."
      )

    calibration = None
    if self.workspace is not None:
      calibration = getattr(self.workspace, "_calibration", None)

    if calibration is None and hasattr(self.gCodeHandler, "getLayerCalibration"):
      calibration = self.gCodeHandler.getLayerCalibration()

    if calibration is None:
      raise ValueError("No layer calibration is loaded for active layer " + requestedLayer + ".")

    calibrationLayer = getattr(calibration, "_layer", None)
    if calibrationLayer not in (None, "", requestedLayer):
      raise ValueError(
        "Loaded calibration layer " + str(calibrationLayer)
        + " does not match requested layer " + requestedLayer + "."
      )

    return calibration

  # ---------------------------------------------------------------------
  def getLayerCalibration(self, layer):
    requestedLayer = str(layer).strip().upper()
    calibration = self._getActiveLayerCalibration(requestedLayer)
    normalized = normalize_calibration(calibration, requestedLayer)
    geometry = create_layer_geometry(requestedLayer)

    calibrationFile = None
    if self.workspace is not None and hasattr(self.workspace, "getCalibrationFile"):
      calibrationFile = self.workspace.getCalibrationFile()
    if not calibrationFile and hasattr(calibration, "getFileName"):
      calibrationFile = calibration.getFileName()

    return {
      "layer": requestedLayer,
      "activeLayer": self.getRecipeLayer(),
      "calibrationFile": calibrationFile,
      "source": "workspace" if self.workspace is not None else "runtime",
      "pinDiameterMm": float(geometry.pinDiameter),
      "locations": {
        pinName: {
          "x": float(location.x),
          "y": float(location.y),
          "z": float(location.z),
        }
        for pinName in normalized.getPinNames()
        for location in [normalized.getPinLocation(pinName)]
      },
    }

  # ---------------------------------------------------------------------
  def getLayerCalibrationJson(self, layer):
    requestedLayer = str(layer).strip().upper()
    calibration = self._getActiveLayerCalibration(requestedLayer)

    calibrationFile = None
    calibrationPath = None
    if self.workspace is not None:
      if hasattr(self.workspace, "getCalibrationFile"):
        calibrationFile = self.workspace.getCalibrationFile()
      if hasattr(self.workspace, "getCalibrationFullPath"):
        calibrationPath = self.workspace.getCalibrationFullPath()

    if not calibrationFile and hasattr(calibration, "getFileName"):
      calibrationFile = calibration.getFileName()
    if calibrationPath is None and hasattr(calibration, "getFullFileName"):
      calibrationPath = calibration.getFullFileName()

    if calibrationPath and os.path.isfile(calibrationPath):
      with open(calibrationPath, encoding="utf-8") as handle:
        content = handle.read()
    elif hasattr(calibration, "_to_dict"):
      content = json.dumps(calibration._to_dict(), indent=2)
    else:
      raise ValueError("Calibration JSON content is not available for active layer " + requestedLayer + ".")

    contentHash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    return {
      "layer": requestedLayer,
      "activeLayer": self.getRecipeLayer(),
      "calibrationFile": calibrationFile,
      "source": "workspace" if self.workspace is not None else "runtime",
      "contentHash": contentHash,
      "content": content,
    }

  # ---------------------------------------------------------------------
  def openRecipeInEditor(self, recipeFile=None):
    return self._recipeService().openRecipeInEditor(recipeFile)

  # ---------------------------------------------------------------------
  def openCalibrationInEditor(self):
    return self._recipeService().openCalibrationInEditor()

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
    return self._motionService().maxVelocity(maxVelocity)

  # ---------------------------------------------------------------------
  def loadWorkspace(self):
    self._recipeService().loadWorkspace()

  # ---------------------------------------------------------------------
  def closeWorkspace(self):
    self._recipeService().closeWorkspace()

  # ---------------------------------------------------------------------
  def jogXY(self, xVelocity, yVelocity, acceleration=None, deceleration=None):
    return self._motionService().jogXY(xVelocity, yVelocity, acceleration, deceleration)

  # ---------------------------------------------------------------------
  def manualSeekXY(
    self, xPosition=None, yPosition=None, velocity=None,
    acceleration=None, deceleration=None,
  ):
    return self._motionService().manualSeekXY(
      xPosition, yPosition, velocity, acceleration, deceleration
    )

  # ---------------------------------------------------------------------
  def manualSeekZ(self, position, velocity=None):
    return self._motionService().manualSeekZ(position, velocity)

  # ---------------------------------------------------------------------
  def manualHeadPosition(self, position, velocity):
    return self._motionService().manualHeadPosition(position, velocity)

  # ---------------------------------------------------------------------
  def jogZ(self, velocity):
    return self._motionService().jogZ(velocity)

  # ---------------------------------------------------------------------
  def seekPin(self, pin, velocity):
    return self._motionService().seekPin(pin, velocity)

  # ---------------------------------------------------------------------
  def seekPinNominal(self, pin, velocity):
    return self._motionService().seekPinNominal(pin, velocity)

  # ---------------------------------------------------------------------
  def setAnchorPoint(self, pinA, pinB=None):
    return self._motionService().setAnchorPoint(pinA, pinB)

  # ---------------------------------------------------------------------
  def getHeadAngle(self):
    return self._motionService().getHeadAngle()

  # ---------------------------------------------------------------------
  def executeG_CodeLine(self, line: str):
    return self._playbackService().executeG_CodeLine(line)

  # ---------------------------------------------------------------------
  def getRealXPosition(self):
    return self._xBacklash.getEffectiveX(self._io.xAxis.getPosition())

# end class
