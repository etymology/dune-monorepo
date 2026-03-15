###############################################################################
# Name: ManualMode.py
# Uses: Update function for manual mode.
# Date: 2016-02-16
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from typing import Optional

from dune_winder.core.control_events import (
  ManualModeEvent,
  SetManualJoggingEvent,
  StopMotionEvent,
)
from dune_winder.library.state_machine_state import StateMachineState
from dune_winder.io.maps.production_io import ProductionIO
from dune_winder.library.log import Log


class ManualMode(StateMachineState):
  def __init__(
    self, stateMachine, state, io: ProductionIO, log: Log
  ):
    """
    Constructor.

    Args:
      stateMachine: Parent state machine.
      state: Integer representation of state.
      io: Instance of I/O map.
      manualCommand: Instance of Control.ManualCommand
    """

    StateMachineState.__init__(self, stateMachine, state)
    self._io = io
    self._log = log
    self._wasJogging = False
    self._wasSeekingZ = False
    self._noteSeekStop = False
    self._isJogging = False
    self._stopRequested = False
    self._request: Optional[ManualModeEvent] = None

  # ---------------------------------------------------------------------
  def setRequest(self, request: ManualModeEvent):
    self._request = request
    if request.isJogging:
      self._isJogging = True

  # ---------------------------------------------------------------------
  def isJogging(self):
    return self._isJogging

  # ---------------------------------------------------------------------
  def enter(self):
    """
    Enter into manual mode.

    Returns:
      True if there was an error, false if not.  The error can happen
      if there isn't a manual action to preform.
    """
    isError = True

    self._wasJogging = False
    self._noteSeekStop = False
    self._stopRequested = False

    request = self._request
    self._request = None

    if request is None:
      return True

    # If executing a G-Code line.
    if request.executeGCode:
      isError = False

    # X/Y axis move?
    if request.seekX is not None or request.seekY is not None:
      x = request.seekX
      if x is None:
        x = self._io.xAxis.getPosition()

      y = request.seekY
      if y is None:
        y = self._io.yAxis.getPosition()

      self._io.plcLogic.setXY_Position(
        x,
        y,
        request.velocity,
        request.acceleration,
        request.deceleration,
      )

      isError = False

    if request.isJogging:
      self._wasJogging = True
      isError = False

    if request.seekZ is not None:
      self._io.plcLogic.setZ_Position(request.seekZ, request.velocity)
      isError = False

    # Move the head?
    if request.setHeadPosition is not None:
      isError = self._io.head.setHeadPosition(
        request.setHeadPosition, request.velocity
      )

      if isError:
        self._log.add(
          self.__class__.__name__, "SEEK_HEAD", "Head position request failed."
        )

    # Shutoff servo control.
    if request.idleServos:
      self._io.plcLogic.servoDisable()
      isError = False

    return isError

  # ---------------------------------------------------------------------
  def update(self):
    """
    Update function that is called periodically.

    """

    # If stop requested...
    if self._stopRequested:
      # We didn't finish this line.  Run it again.
      self._io.plcLogic.stopSeek()
      self._io.head.stop()
      self._log.add(self.__class__.__name__, "SEEK_STOP", "Seek stop requested")
      self._noteSeekStop = True
      self._stopRequested = False

    # Is movement done?
    if self._io.plcLogic.isReady() and self._io.head.isReady():
      # If we were seeking and stopped pre-maturely, note where.
      if self._noteSeekStop:
        x = self._io.xAxis.getPosition()
        y = self._io.yAxis.getPosition()
        z = self._io.zAxis.getPosition()
        self._log.add(
          self.__class__.__name__,
          "SEEK_STOP_LOCATION",
          "Seek stopped at (" + str(x) + "," + str(y) + "," + str(z) + ")",
          [x, y, z],
        )

      # If we were jogging, note where it stopped.
      if self._wasJogging:
        x = self._io.xAxis.getPosition()
        y = self._io.yAxis.getPosition()
        z = self._io.zAxis.getPosition()
        self._log.add(
          self.__class__.__name__,
          "JOG_STOP",
          "Jog stopped at (" + str(x) + "," + str(y) + "," + str(z) + ")",
          [x, y, z],
        )

      self._isJogging = False
      self.changeState(self.stateMachine.States.STOP)

  # ---------------------------------------------------------------------
  def handle(self, event):
    if isinstance(event, StopMotionEvent):
      self._stopRequested = True
      return True

    if isinstance(event, SetManualJoggingEvent):
      self._isJogging = event.isJogging
      return True

    return False


# end class
