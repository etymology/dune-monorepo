###############################################################################
# Name: ControlStateMachine.py
# Uses: Root level state machine.
# Date: 2016-02-11
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from enum import Enum, auto

from dune_winder.library.logged_state_machine import LoggedStateMachine
from dune_winder.core.control_events import SetLoopModeEvent
from dune_winder.core.hardware_mode import HardwareMode
from dune_winder.core.stop_mode import StopMode
from dune_winder.core.wind_mode import WindMode
from dune_winder.core.manual_mode import ManualMode
from dune_winder.core.calibration_mode import CalibrationMode
from dune_winder.library.time_source import TimeSource
from dune_winder.library.log import Log
from dune_winder.io.Maps.base_io import BaseIO
from dune_winder.core.g_code_handler import G_CodeHandler
from typing import Optional


class ControlStateMachine(LoggedStateMachine):
  class States(Enum):
    HARDWARE = auto()
    STOP = auto()
    WIND = auto()
    CALIBRATE = auto()
    MANUAL = auto()
    TENTION = auto()

  # end class

  # ---------------------------------------------------------------------
  def update(self):
    """
    Overridden update function.  Runs some base logic before any other
    state.
    """

    if not self._io.isFunctional():
      # If PLC reports an error mid-head-transfer, clear any queued local
      # head sequence steps before switching to hardware/error handling mode.
      if self._io.plcLogic.isError():
        self._io.head.clearQueuedTransfer()

      if self.getState() != self.States.HARDWARE:
        self.changeState(self.States.HARDWARE)
    # Emergency stop.
    elif self._io.estop.get() and self.getState() != self.States.STOP:
      self.log.add(self.__class__.__name__, "ESTOP", "Emergency stop detected.")
      self.changeState(self.States.STOP)

    LoggedStateMachine.update(self)

  # ---------------------------------------------------------------------
  def dispatch(self, event):
    """
    Handle global control events and route all others to active mode.

    Args:
      event: Event payload object.

    Returns:
      True if handled, False if ignored.
    """

    if isinstance(event, SetLoopModeEvent):
      self.windMode.setLoopMode(event.enabled)
      return True

    return LoggedStateMachine.dispatch(self, event)

  # ---------------------------------------------------------------------
  def isStopped(self):
    """
    See if state machine is in stop.

    Return:
      True if state machine is in stop.
    """
    return self.States.STOP == self.getState()

  # ---------------------------------------------------------------------
  def isInMotion(self):
    """
    Check to see if the machine is in motion.

    Returns:
      True if machine is in motion, False if not.
    """
    return self.getState() in (
      self.States.WIND,
      self.States.CALIBRATE,
      self.States.MANUAL,
      self.States.TENTION,
    )

  # ---------------------------------------------------------------------
  def isReadyForMovement(self):
    """
    Check to see if the state machine is in a state suitable for starting
    motion.

    Returns:
      True if machine can begin motion.
    """
    return self.States.STOP == self.getState() and self.stopMode.isIdle()

  # ---------------------------------------------------------------------
  def isJogging(self):
    """
    Check if manual jogging is currently active.

    Returns:
      True if jogging, False if not.
    """
    return self.manualMode.isJogging()

  # ---------------------------------------------------------------------
  def getLoopMode(self):
    """
    See if G-Code loop mode is enabled.

    Returns:
      True if loop mode enabled.
    """
    return self.windMode.getLoopMode()

  # ---------------------------------------------------------------------
  def getWindTime(self):
    """
    Return the most recent wind runtime in seconds.
    """
    return self.windMode.getWindTime()

  # ---------------------------------------------------------------------
  def resetWindTime(self):
    """
    Clear accumulated wind runtime.
    """
    self.windMode.resetWindTime()

  # ---------------------------------------------------------------------
  def __init__(self, io: BaseIO, log: Log, systemTime: TimeSource):
    """
    Constructor.

    Args:
      io: Instance of I/O map.
      log: Log file to write state changes.
      systemTime: Instance of TimeSource.
    """

    LoggedStateMachine.__init__(self, log)
    self.hardwareMode = HardwareMode(self, self.States.HARDWARE, io, log)
    self.stopMode = StopMode(self, self.States.STOP, io, log)
    self.windMode = WindMode(self, self.States.WIND, io, log)
    self.manualMode = ManualMode(self, self.States.MANUAL, io, log)
    self.calibrationMode = CalibrationMode(self, self.States.CALIBRATE, io, log)

    self.changeState(self.States.HARDWARE)

    self._io = io

    self.systemTime = systemTime

    # Runtime wiring shared by modes.
    self.gCodeHandler: Optional[G_CodeHandler] = None
    self.cameraCalibration = None
    self.machineCalibration = None


# end class
