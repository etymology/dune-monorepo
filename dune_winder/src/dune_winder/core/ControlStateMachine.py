###############################################################################
# Name: ControlStateMachine.py
# Uses: Root level state machine.
# Date: 2016-02-11
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from dune_winder.library.LoggedStateMachine import LoggedStateMachine
from dune_winder.core.HardwareMode import HardwareMode
from dune_winder.core.StopMode import StopMode
from dune_winder.core.WindMode import WindMode
from dune_winder.core.ManualMode import ManualMode
from dune_winder.core.CalibrationMode import CalibrationMode
from dune_winder.library.TimeSource import TimeSource
from dune_winder.library.Log import Log
from dune_winder.io.Maps.BaseIO import BaseIO
from dune_winder.core.G_CodeHandler import G_CodeHandler
from typing import Optional

class ControlStateMachine(LoggedStateMachine):
  class States:
    HARDWARE = (0,)
    STOP = (1,)
    WIND = (2,)
    CALIBRATE = (3,)
    MANUAL = (4,)
    TENTION = 5

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
    return (
      self.States.HARDWARE != self.getState() or self.States.STOP != self.getState()
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

    self.windTime = 0

    # Wind mode.
    self.startRequest = False
    self.stopRequest = False
    self.stopNextRequest = (
      False  # True to stop after completing the current G-Code line.
    )
    self.loopMode = False  # True to continuously loop the G-Code.
    self.positionLogging = False  # True to log resulting position after each move.
    self.gCodeHandler: Optional[G_CodeHandler] = None

    # Manual mode options.
    self.manualRequest = False
    self.isJogging = False
    self.idleServos = False
    self.executeGCode = False
    self.setHeadPosition = None

    # Calibration mode options.
    self.calibrationRequest = False
    self.cameraCalibration = None

    # Manual/calibration mode options.
    self.seekX = None
    self.seekY = None
    self.seekZ = None
    self.seekVelocity = None
    self.seekAcceleration = None
    self.seekDeceleration = None


# end class
