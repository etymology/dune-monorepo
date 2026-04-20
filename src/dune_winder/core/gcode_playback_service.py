###############################################################################
# Name: gcode_playback_service.py
# Uses: G-Code playback control and manual execution extracted from Process.
###############################################################################

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable, Optional

from dune_winder.core.control_events import (
  ManualModeEvent,
  SetLoopModeEvent,
  StartWindEvent,
  StopMotionEvent,
)

if TYPE_CHECKING:
  from dune_winder.core.control_state_machine import ControlStateMachine
  from dune_winder.core.safety_validation_service import SafetyValidationService
  from dune_winder.core.winder_workspace import WinderWorkspace
  from dune_winder.gcode.handler import GCodeHandler
  from dune_winder.io.maps.base_io import BaseIO
  from dune_winder.library.log import Log
  from dune_winder.core.x_backlash_compensation import XBacklashCompensation

LOG_NAME = "GCodePlaybackService"


class GCodePlaybackService:
  """G-Code playback, line control, and manual G-code execution."""

  def __init__(
    self,
    gCodeHandler: GCodeHandler,
    controlStateMachine: ControlStateMachine,
    log: Log,
    io: BaseIO,
    safety: SafetyValidationService,
    xBacklash: XBacklashCompensation,
    workspaceGetter: Callable[[], Optional[WinderWorkspace]],
  ):
    self._gCodeHandler = gCodeHandler
    self._controlStateMachine = controlStateMachine
    self._log = log
    self._io = io
    self._safety = safety
    self._xBacklash = xBacklash
    self._workspaceGetter = workspaceGetter

  # -- run control ---------------------------------------------------------

  # ---------------------------------------------------------------------
  def _issueDirectStop(self):
    plcLogic = getattr(self._io, "plcLogic", None)
    if plcLogic is not None and hasattr(plcLogic, "stopSeek"):
      plcLogic.stopSeek()

    head = getattr(self._io, "head", None)
    if head is not None and hasattr(head, "stop"):
      head.stop()

  # ---------------------------------------------------------------------
  def start(self):
    if self._controlStateMachine.isReadyForMovement():
      self._controlStateMachine.dispatch(StartWindEvent())

  def stop(self):
    self._issueDirectStop()
    if self._controlStateMachine.isInMotion():
      self._controlStateMachine.dispatch(StopMotionEvent())

  def stopNextLine(self):
    if self._controlStateMachine.isInMotion() and self._gCodeHandler.isG_CodeLoaded():
      self._gCodeHandler.stopNext()

  def step(self):
    if (
      self._controlStateMachine.isReadyForMovement()
      and self._gCodeHandler.isG_CodeLoaded()
    ):
      self._gCodeHandler.singleStep = True
      self._controlStateMachine.dispatch(StartWindEvent())

  # -- line management -----------------------------------------------------

  def getG_CodeList(self, center, delta):
    result = []
    if self._gCodeHandler.isG_CodeLoaded():
      if center is None:
        center = self._gCodeHandler.getLine()
      result = self._gCodeHandler.fetchLines(center, delta)
    return result

  def setG_CodeLine(self, line):
    isError = True
    if self._gCodeHandler.isG_CodeLoaded():
      initialLine = self._gCodeHandler.getLine()
      isError = self._gCodeHandler.setLine(line)

      if not isError:
        self._log.add(
          LOG_NAME,
          "LINE",
          "G-Code line changed from " + str(initialLine) + " to " + str(line),
          [initialLine, line],
        )

    if isError:
      self._log.add(
        LOG_NAME,
        "LINE",
        "Unable to change G-Code line changed to " + str(line),
        [line],
      )

    return isError

  def getG_CodeDirection(self):
    result = True
    if self._gCodeHandler.isG_CodeLoaded():
      result = self._gCodeHandler.getDirection()
    return result

  def getLayerCalibration(self):
    calibration = self._gCodeHandler.getLayerCalibration()
    if calibration is None:
      return None

    def pin_sort_key(name):
      text = str(name)
      prefix_rank = 0 if text.startswith("A") else 1 if text.startswith("B") else 2
      suffix = text[1:]
      try:
        pin_number = int(suffix)
      except (TypeError, ValueError):
        pin_number = 0
      return (prefix_rank, pin_number, text)

    offset = getattr(calibration, "offset", None)
    offset_x = float(getattr(offset, "x", 0.0))
    offset_y = float(getattr(offset, "y", 0.0))
    offset_z = float(getattr(offset, "z", 0.0))

    pins = []
    for pin_name in sorted(calibration.getPinNames(), key=pin_sort_key):
      location = calibration.getPinLocation(pin_name)
      pins.append(
        {
          "name": str(pin_name),
          "x": float(getattr(location, "x", 0.0)) + offset_x,
          "y": float(getattr(location, "y", 0.0)) + offset_y,
          "z": float(getattr(location, "z", 0.0)) + offset_z,
        }
      )

    return {
      "layer": getattr(calibration, "_layer", None),
      "zFront": float(getattr(calibration, "zFront", 0.0)),
      "zBack": float(getattr(calibration, "zBack", 0.0)),
      "offset": {
        "x": offset_x,
        "y": offset_y,
        "z": offset_z,
      },
      "pins": pins,
    }

  def setG_CodeDirection(self, isForward):
    isError = True
    if self._gCodeHandler.isG_CodeLoaded():
      initialDirection = self._gCodeHandler.getDirection()
      isError = self._gCodeHandler.setDirection(isForward)

      if not isError:
        self._log.add(
          LOG_NAME,
          "DIRECTION",
          "G-Code direction changed from "
          + str(initialDirection)
          + " to "
          + str(isForward),
          [initialDirection, isForward],
        )

    if isError:
      self._log.add(
        LOG_NAME,
        "LINE",
        "Unable to change G-Code direction changed to " + str(isForward),
        [isForward],
      )

    return isError

  def setG_CodeRunToLine(self, line):
    isError = True
    if self._gCodeHandler.isG_CodeLoaded():
      initialRunTo = self._gCodeHandler.runToLine
      self._gCodeHandler.runToLine = line
      isError = False

      if not isError:
        self._log.add(
          LOG_NAME,
          "RUN_TO",
          "G-Code finial line changed from " + str(initialRunTo) + " to " + str(line),
          [initialRunTo, line],
        )

    if isError:
      self._log.add(
        LOG_NAME,
        "LINE",
        "Unable to change G-Code run to line to " + str(line),
        [line],
      )

    return isError

  # -- loop / velocity scale -----------------------------------------------

  def getG_CodeLoop(self):
    return self._controlStateMachine.getLoopMode()

  def setG_CodeLoop(self, isLoopMode):
    currentLoopMode = self._controlStateMachine.getLoopMode()

    self._log.add(
      LOG_NAME,
      "LOOP",
      "G-Code loop mode set from " + str(currentLoopMode) + " to " + str(isLoopMode),
      [currentLoopMode, isLoopMode],
    )

    self._controlStateMachine.dispatch(SetLoopModeEvent(isLoopMode))

  def setG_CodeVelocityScale(self, scaleFactor=1.0):
    self._log.add(
      LOG_NAME,
      "VELOCITY_SCALE",
      "G-Code velocity scale change from "
      + str(self._gCodeHandler.getVelocityScale())
      + " to "
      + str(scaleFactor),
      [self._gCodeHandler.getVelocityScale(), scaleFactor],
    )

    self._gCodeHandler.setVelocityScale(scaleFactor)

  # -- position logging ----------------------------------------------------

  def getPositionLogging(self):
    return self._gCodeHandler.isPositionLogging()

  def setPositionLogging(self, isEnabled):
    fileName = None
    workspace = self._workspaceGetter()
    if isEnabled:
      if workspace:
        fileName = workspace.getPath() + "positionLog.csv"
        self._log.add(
          LOG_NAME,
          "POSITION_LOGGING",
          "Position logging begins",
          [1, fileName],
        )
      else:
        self._log.add(
          LOG_NAME,
          "POSITION_LOGGING",
          "Position logging request ignored.  No workspace loaded.",
          [-1],
        )
    else:
      self._log.add(LOG_NAME, "POSITION_LOGGING", "Position logging ends", [0])

    self._gCodeHandler.startPositionLogging(fileName)

    return self.getPositionLogging()

  # -- queued motion preview -----------------------------------------------

  def getQueuedMotionPreview(self):
    return self._gCodeHandler.getQueuedMotionPreview()

  def getQueuedMotionUseMaxSpeed(self):
    return self._gCodeHandler.getQueuedMotionUseMaxSpeed()

  def setQueuedMotionUseMaxSpeed(self, enabled):
    enabled = bool(enabled)
    current = self._gCodeHandler.getQueuedMotionUseMaxSpeed()
    if current == enabled:
      return current

    current = self._gCodeHandler.setQueuedMotionUseMaxSpeed(enabled)
    self._log.add(
      LOG_NAME,
      "QUEUED_PREVIEW_MAX_SPEED",
      "Enabled queued-motion default maximum speed."
      if current
      else "Disabled queued-motion default maximum speed.",
    )
    return current

  def continueQueuedMotionPreview(self):
    accepted = self._gCodeHandler.continueQueuedMotionPreview()
    if accepted:
      self._log.add(
        LOG_NAME,
        "QUEUED_PREVIEW_CONTINUE",
        "Approved queued G113 path preview.",
      )
    return accepted

  def cancelQueuedMotionPreview(self):
    cancelled = self._gCodeHandler.cancelQueuedMotionPreview()
    if cancelled:
      self._log.add(
        LOG_NAME,
        "QUEUED_PREVIEW_CANCEL",
        "Cancelled queued G113 path preview before execution.",
      )
    return cancelled

  # -- refresh callback ----------------------------------------------------

  def refreshCalibrationBeforeExecution(self):
    workspace = self._workspaceGetter()
    if not workspace:
      return None

    try:
      workspace.refreshRecipeIfChanged()
      workspace.refreshCalibrationIfChanged()
    except Exception as exception:
      self._log.add(
        LOG_NAME,
        "GCODE_REFRESH",
        "Failed to refresh runtime files from disk before G-Code execution.",
        [str(exception)],
      )
      return str(exception)

    return None

  # -- manual G-code execution ---------------------------------------------

  def executeG_CodeLine(self, line: str):
    error = None
    if not self._controlStateMachine.isReadyForMovement():
      error = self._safety.manual_movement_blocker_message()
      self._log.add(
        LOG_NAME,
        "MANUAL_GCODE",
        "Failed to execute manual G-Code line as machine was not ready.",
        [line, error],
      )

    else:
      # Check the format of the string matches a VALID PATTERN
      xy = r"(\ *[X]\d{1,4}(\.\d{1,2})?\ *[Y]\d{1,4}(\.\d{1,2})?\ *$)"
      x_only = r"(\ *[X]\d{1,4}(\.\d{1,2})?\ *$)"
      y_only = r"(\ *[Y]\d{1,4}(\.\d{1,2})?\ *$)"
      gxy = r"(\ *[G]105\ *[P][XY]-?\d{1,3}(\.\d{1,2})?\ *$)"
      gx_y = (
        r"(\ *[G]105\ *[P][X]-?\d{1,3}(\.\d{1,2})?\ *[P][Y]-?\d{1,3}(\.\d{1,2})?\ *$)"
      )
      xyf = r"(\ *[X]\d{1,4}(\.\d{1,2})?\ *[Y]\d{1,4}(\.\d{1,2})?\ *[F]\d{1,4}\ *$)"
      fxy = r"(\ *[F]\d{1,4}\ *[X]\d{1,4}(\.\d{1,2})?\ *[Y]\d{1,4}(\.\d{1,2})?\ *$)"
      xf = r"(\ *[X]\d{1,4}(\.\d{1,2})?\ *[F]\d{1,4}\ *$)"
      fx = r"(\ *[F]\d{1,4}\ *[X]\d{1,4}(\.\d{1,2})?\ *$)"
      yf = r"(\ *[Y]\d{1,4}(\.\d{1,2})?\ *[F]\d{1,4}\ *$)"
      fy = r"(\ *[F]\d{1,4}\ *[Y]\d{1,4}(\.\d{1,2})?\ *$)"
      xz = r"(\ *[X]\d{1,4}(\.\d{1,2})?\ *[Z]\d{1,3}(\.\d{1,2})?\ *$)"
      xzf = r"(\ *[X]\d{1,4}(\.\d{1,2})?\ *[Z]\d{1,3}(\.\d{1,2})?\ *[F]\d{1,4}\ *$)"
      fxz = r"(\ *[F]\d{1,4}\ *[X]\d{1,4}(\.\d{1,2})?\ *[Z]\d{1,3}(\.\d{1,2})?\ *$)"
      yz = r"(\ *[Y]\d{1,4}(\.\d{1,2})?\ *[Z]\d{1,3}(\.\d{1,2})?\ *$)"
      yzf = r"(\ *[Y]\d{1,4}(\.\d{1,2})?\ *[Z]\d{1,3}(\.\d{1,2})?\ *[F]\d{1,4}\ *$)"
      fyz = r"(\ *[F]\d{1,4}\ *[Y]\d{1,4}(\.\d{1,2})?\ *[Z]\d{1,3}(\.\d{1,2})?\ *$)"
      f_only = r"(\ *[F]\d{1,4}(\.\d{1,2})?\ *$)"
      gxyf = r"(\ *[G]105\ *[P][XY]-?\d{1,3}(\.\d{1,2})?\ *[F]\d{1,4}\ *$)"
      gx_yf = r"(\ *[G]105\ *[P][X]-?\d{1,3}(\.\d{1,2})?\ *[P][Y]-?\d{1,3}(\.\d{1,2})?\ *[F]\d{1,4}\ *$)"
      gp = r"(\ *[G]106\ *P[0123]\ *$)"
      g206 = r"(\ *[G]206\ *P[0123]\ *$)"
      z_move = r"(\ *[Z]\d{1,3}(\.\d{1,2})?\ *$)"
      zf = r"(\ *[Z]\d{1,3}(\.\d{1,2})?\ *[F]\d{1,4}\ *$)"
      fz = r"(\ *[F]\d{1,4}\ *[Z]\d{1,3}(\.\d{1,2})?\ *$)"
      absoluteXYMovePattern = "|".join([xy, x_only, y_only, xyf, fxy, xf, fx, yf, fy])
      absoluteXZMovePattern = "|".join([xz, xzf, fxz])
      absoluteYZMovePattern = "|".join([yz, yzf, fyz])
      relativeXYMovePattern = "|".join([gxy, gxyf, gx_y, gx_yf])
      if not re.match(
        absoluteXYMovePattern
        + "|"
        + absoluteXZMovePattern
        + "|"
        + absoluteYZMovePattern
        + "|"
        + relativeXYMovePattern
        + "|"
        + gp
        + "|"
        + g206
        + "|"
        + f_only
        + "|"
        + z_move
        + "|"
        + zf
        + "|"
        + fz,
        line,
      ):
        error = (
          "Unsupported manual G-code format. "
          "Supported moves are X/Y, X/Z, Y/Z, G105 P... transfer moves, G206 P0-3, and F-only lines: "
          + line
        )

      # Check that X and Y input coordinate are within limits
      rawXPosition = float(self._io.xAxis.getPosition())
      yPosition = float(self._io.yAxis.getPosition())
      xPosition = self._xBacklash.getEffectiveX(rawXPosition)
      self._io.zAxis.getPosition()
      codeLineSplit = line.split()
      x = xPosition
      y = yPosition
      isXYMove = re.match(absoluteXYMovePattern + "|" + relativeXYMovePattern, line)
      isXZMove = re.match(absoluteXZMovePattern, line)
      isYZMove = re.match(absoluteYZMovePattern, line)
      isRelativeXYMove = re.match(relativeXYMovePattern, line)

      for cmd in codeLineSplit:
        if "X" in cmd and (isXYMove or isXZMove):
          xCmd = cmd.split("X")
          x = float(xCmd[1])
          if isRelativeXYMove:
            x += xPosition

        if "Y" in cmd and (isXYMove or isYZMove):
          yCmd = cmd.split("Y")
          y = float(yCmd[1])
          if isRelativeXYMove:
            y += yPosition

        if "F" in cmd and re.match(
          "|".join([xyf, fxy, xf, fx, yf, fy, xzf, fxz, zf, fz, gxyf, gx_yf, f_only]),
          line,
        ):
          velocity = float(cmd.split("F")[1])
          if velocity < 0 or velocity > self._safety.max_velocity:
            error = (
              "Invalid F-axis Speed, exceeding limit [0.0 , "
              + str(self._safety.max_velocity)
              + "]"
            )

        if "Z" in cmd and re.match(
          "|".join([z_move, xz, xzf, fxz, yz, yzf, fyz, zf, fz]),
          line,
        ):
          zCmd = cmd.split("Z")
          z_target = float(zCmd[1])
          if (
            z_target < self._safety.zlimit_front or z_target > self._safety.zlimit_rear
          ):
            error = (
              "Invalid Z-axis Coordinates, exceeding limit ["
              + str(z_target)
              + " > "
              + str(self._safety.zlimit_rear)
              + "]"
            )

      if error is None and isXYMove:
        error = self._safety.validate_xy_move_target(xPosition, yPosition, x, y)
      elif (
        error is None
        and isXZMove
        and (x < self._safety.limit_left or x > self._safety.limit_right)
      ):
        error = (
          "Invalid X-axis Coordinates, exceeding limit ["
          + str(self._safety.limit_left)
          + " , "
          + str(self._safety.limit_right)
          + "]"
        )
      elif error is None and isYZMove:
        limits = self._safety.current_motion_safety_limits()
        if y < limits.limit_bottom or y > limits.limit_top:
          error = (
            "Invalid Y-axis Coordinates, exceeding limit ["
            + str(limits.limit_bottom)
            + " , "
            + str(limits.limit_top)
            + "]"
          )

      if error is not None:
        self._log.add(
          LOG_NAME,
          "MANUAL_GCODE",
          "Failed to execute manual G-Code line.",
          [line, error],
        )
      else:
        lineToExecute = line
        if re.match(x_only + "|" + xf + "|" + fx, line):
          lineToExecute = line.strip() + " Y" + str(yPosition)
        elif re.match(y_only + "|" + yf + "|" + fy, line):
          lineToExecute = line.strip() + " X" + str(xPosition)

        errorData = self._gCodeHandler.executeG_CodeLine(
          lineToExecute,
          skip_before_execute_callback=True,
        )

        if errorData:
          error = errorData["message"]
          self._log.add(
            LOG_NAME,
            "MANUAL_GCODE",
            "Failed to execute manual G-Code line.",
            [line, error],
          )
        else:
          self._controlStateMachine.dispatch(ManualModeEvent(executeGCode=True))

          self._log.add(
            LOG_NAME,
            "MANUAL_GCODE",
            "Execute manual G-Code line.",
            [line],
          )

    return error
