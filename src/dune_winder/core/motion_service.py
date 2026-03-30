###############################################################################
# Name: motion_service.py
# Uses: Manual motion commands extracted from Process.
###############################################################################

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Callable, Optional

from dune_winder.library.Geometry.location import Location
from dune_winder.core.control_events import (
  ManualModeEvent,
  SetManualJoggingEvent,
)
from dune_winder.machine.calibration.defaults import DefaultLayerCalibration

if TYPE_CHECKING:
  from dune_winder.core.control_state_machine import ControlStateMachine
  from dune_winder.core.safety_validation_service import SafetyValidationService
  from dune_winder.core.winder_workspace import WinderWorkspace
  from dune_winder.gcode.handler import GCodeHandler
  from dune_winder.io.maps.base_io import BaseIO
  from dune_winder.library.log import Log
  from dune_winder.machine.head_compensation import WirePathModel

LOG_NAME = "MotionService"


class MotionService:
  """Manual motion commands: jog, seek, head positioning, anchor points."""

  def __init__(
    self,
    io: BaseIO,
    log: Log,
    controlStateMachine: ControlStateMachine,
    safety: SafetyValidationService,
    gCodeHandler: GCodeHandler,
    headCompensation: WirePathModel,
    workspaceGetter: Callable[[], Optional[WinderWorkspace]],
  ):
    self._io = io
    self._log = log
    self._controlStateMachine = controlStateMachine
    self._safety = safety
    self._gCodeHandler = gCodeHandler
    self._headCompensation = headCompensation
    self._workspaceGetter = workspaceGetter

  # -- velocity ------------------------------------------------------------

  def maxVelocity(self, maxVelocity=None):
    if maxVelocity is not None:
      self._safety.max_velocity = maxVelocity
      self._io.plcLogic.maxVelocity(maxVelocity)
      self._gCodeHandler.setLimitVelocity(maxVelocity)
    return self._safety.max_velocity

  # -- servo ---------------------------------------------------------------

  def servoDisable(self):
    if self._controlStateMachine.isInMotion():
      self._log.add(LOG_NAME, "SERVO", "Idling servo control.")
      self._controlStateMachine.dispatch(ManualModeEvent(idleServos=True))

  # -- jog -----------------------------------------------------------------

  def jogXY(self, xVelocity, yVelocity, acceleration=None, deceleration=None):
    isError = False
    if (
      0 != xVelocity or 0 != yVelocity
    ) and self._controlStateMachine.isReadyForMovement():
      x = self._io.xAxis.getPosition()
      self._io.yAxis.getPosition()
      self._io.zAxis.getPosition()
      if (
        x < self._safety.transfer_left or x > self._safety.transfer_right
      ):
        if xVelocity != 0:
          xVelocity = math.copysign(self._safety.max_slow_velocity, xVelocity)
        if yVelocity != 0:
          yVelocity = math.copysign(self._safety.max_slow_velocity, yVelocity)

      self._log.add(
        LOG_NAME,
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

      self._controlStateMachine.dispatch(ManualModeEvent(isJogging=True))
      self._io.plcLogic.jogXY(xVelocity, yVelocity, acceleration, deceleration)
    elif (
      0 == xVelocity
      and 0 == yVelocity
      and self._controlStateMachine.isJogging()
    ):
      self._log.add(LOG_NAME, "JOG", "Jog X/Y stop.")
      self._controlStateMachine.dispatch(SetManualJoggingEvent(False))
      self._io.plcLogic.jogXY(xVelocity, yVelocity)
    else:
      isError = True
      self._log.add(
        LOG_NAME,
        "JOG",
        "Jog X/Y request ignored.",
        [xVelocity, yVelocity, acceleration, deceleration],
      )

    return isError

  def jogZ(self, velocity):
    isError = False
    if 0 != velocity and self._controlStateMachine.isReadyForMovement():
      self._log.add(
        LOG_NAME, "JOG", "Jog Z at " + str(velocity) + ".", [velocity]
      )
      self._controlStateMachine.dispatch(ManualModeEvent(isJogging=True))
      self._io.plcLogic.jogZ(velocity)
    elif 0 == velocity and self._controlStateMachine.isJogging():
      self._log.add(LOG_NAME, "JOG", "Jog Z stop.")
      self._controlStateMachine.dispatch(SetManualJoggingEvent(False))
      self._io.plcLogic.jogZ(velocity)
    else:
      isError = True
      self._log.add(
        LOG_NAME, "JOG", "Jog Z request ignored.", [velocity]
      )

    return isError

  # -- seek ----------------------------------------------------------------

  def manualSeekXY(
    self,
    xPosition=None,
    yPosition=None,
    velocity=None,
    acceleration=None,
    deceleration=None,
  ):
    isError = True
    if self._controlStateMachine.isReadyForMovement():
      currentX = float(self._io.xAxis.getPosition())
      currentY = float(self._io.yAxis.getPosition())
      targetX = currentX if xPosition is None else float(xPosition)
      targetY = currentY if yPosition is None else float(yPosition)

      error = self._safety.validate_xy_move_target(currentX, currentY, targetX, targetY)
      if error is not None:
        self._log.add(
          LOG_NAME,
          "JOG",
          "Manual move X/Y ignored.",
          [xPosition, yPosition, velocity, acceleration, deceleration, error],
        )
      else:
        isError = False
        self._log.add(
          LOG_NAME,
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
        self._controlStateMachine.dispatch(
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
        LOG_NAME,
        "JOG",
        "Manual move X/Y ignored.",
        [xPosition, yPosition, velocity, acceleration, deceleration],
      )

    return isError

  def manualSeekZ(self, position, velocity=None):
    isError = True
    if self._controlStateMachine.isReadyForMovement():
      isError = False
      self._log.add(
        LOG_NAME,
        "JOG",
        "Manual move Z to " + str(position) + " at " + str(velocity) + ".",
        [position, velocity],
      )
      self._controlStateMachine.dispatch(
        ManualModeEvent(seekZ=position, velocity=velocity)
      )
    else:
      self._log.add(
        LOG_NAME, "JOG", "Manual move Z ignored.", [position, velocity]
      )

    return isError

  def manualHeadPosition(self, position, velocity):
    isError = True

    if (
      self._controlStateMachine.isReadyForMovement()
      and self._io.head.getPosition() != position
    ):
      isError = False

      self._log.add(
        LOG_NAME,
        "HEAD",
        "Manual head position to " + str(position) + " at " + str(velocity) + ".",
        [position, velocity],
      )
      self._controlStateMachine.dispatch(
        ManualModeEvent(setHeadPosition=position, velocity=velocity)
      )

    else:
      self._log.add(
        LOG_NAME,
        "HEAD",
        "Manual head position ignored.",
        [position, velocity],
      )

    return isError

  # -- pin seek ------------------------------------------------------------

  def seekPin(self, pin, velocity):
    calibration = self._gCodeHandler.getLayerCalibration()

    isError = True

    if calibration:
      pinNameA = pin
      pinNameB = pin
      if " " in pin:
        [pinNameA, pinNameB] = pin.split(" ")

      if calibration.getPinExists(pinNameA) and calibration.getPinExists(pinNameB):
        self._log.add(
          LOG_NAME,
          "SEEK_PIN",
          "Manual pin seek " + pin + " at " + str(velocity) + ".",
          [pin, velocity],
        )

        pinA = calibration.getPinLocation(pinNameA)
        pinB = calibration.getPinLocation(pinNameB)
        position = pinA.center(pinB)
        position = position.add(calibration.offset)

        self.manualSeekXY(position.x, position.y, velocity)
        isError = False
      else:
        self._log.add(
          LOG_NAME,
          "SEEK_PIN",
          "Manual pin seek request ignored--pin(s) does not exist.",
          [pin, velocity],
        )
    else:
      self._log.add(
        LOG_NAME,
        "SEEK_PIN",
        "Manual pin seek request ignored--no calibration loaded.",
        [pin, velocity],
      )

    return isError

  def seekPinNominal(self, pin, velocity):
    isError = True
    workspace = self._workspaceGetter()
    if workspace:
      layer = workspace.getLayer()

      calibration = DefaultLayerCalibration(None, None, layer)

      if calibration.getPinExists(pin):
        self._log.add(
          LOG_NAME,
          "SEEK_PIN_NOMINAL",
          "Nominal pin seek " + pin + " at " + str(velocity) + ".",
          [pin, velocity],
        )

        position = calibration.getPinLocation(pin)
        position = position.add(calibration.offset)

        self.manualSeekXY(position.x, position.y, velocity)
        isError = False
      else:
        self._log.add(
          LOG_NAME,
          "SEEK_PIN_NOMINAL",
          "Nominal pin seek request ignored--pin(s) does not exist.",
          [pin, velocity],
        )
    else:
      self._log.add(
        LOG_NAME,
        "SEEK_PIN_NOMINAL",
        "Nominal pin seek request ignored--no workspace loaded.",
        [pin, velocity],
      )

    return isError

  # -- anchor / head angle -------------------------------------------------

  def setAnchorPoint(self, pinA, pinB=None):
    calibration = self._gCodeHandler.getLayerCalibration()

    isError = True

    if calibration:
      pinA = calibration.getPinLocation(pinA)

      if pinA:
        if pinB:
          pinB = calibration.getPinLocation(pinB)

          if pinB:
            location = pinA.center(pinB)
        else:
          location = pinA

        location = location.add(calibration.offset)

        self._headCompensation.anchorPoint(location)
        isError = False

    return isError

  def getHeadAngle(self):
    result = 0
    if self._io.isFunctional():
      x = self._io.xAxis.getPosition()
      y = self._io.yAxis.getPosition()
      z = self._io.zAxis.getPosition()

      location = Location(x, y, z)

      result = self._headCompensation.getHeadAngle(location)

    return result
