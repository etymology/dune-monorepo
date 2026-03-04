###############################################################################
# Name: ManualMode.py
# Uses: Update function for manual mode.
# Date: 2016-02-16
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from dune_winder.library.StateMachineState import StateMachineState
from dune_winder.io.Maps.ProductionIO import ProductionIO
from dune_winder.library.Log import Log


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

    # If executing a G-Code line.
    if self.stateMachine.executeGCode:
      self.stateMachine.executeGCode = False
      isError = False

    # X/Y axis move?
    if self.stateMachine.seekX is not None or self.stateMachine.seekY is not None:
      x = self.stateMachine.seekX
      if x is None:
        x = self._io.xAxis.getPosition()

      y = self.stateMachine.seekY
      if y is None:
        y = self._io.yAxis.getPosition()

      self._io.plcLogic.setXY_Position(
        x,
        y,
        self.stateMachine.seekVelocity,
        self.stateMachine.seekAcceleration,
        self.stateMachine.seekDeceleration,
      )

      self.stateMachine.seekX = None
      self.stateMachine.seekY = None
      self.stateMachine.seekVelocity = None
      self.stateMachine.seekAcceleration = None
      self.stateMachine.seekDeceleration = None
      isError = False

    if self.stateMachine.isJogging:
      self._wasJogging = True
      isError = False

    if self.stateMachine.seekZ is not None:
      self._io.plcLogic.setZ_Position(
        self.stateMachine.seekZ, self.stateMachine.seekVelocity
      )
      self.stateMachine.seekZ = None
      isError = False

    # Move the head?
    if self.stateMachine.setHeadPosition is not None:
      isError = self._io.head.setHeadPosition(
        self.stateMachine.setHeadPosition, self.stateMachine.seekVelocity
      )

      if isError:
        self._log.add(
          self.__class__.__name__, "SEEK_HEAD", "Head position request failed."
        )

      self.stateMachine.setHeadPosition = None

    # Shutoff servo control.
    if self.stateMachine.idleServos:
      self._io.plcLogic.servoDisable()
      self.stateMachine.idleServos = False
      isError = False

    return isError

  def update(self):
    """
    Update function that is called periodically.

    """

    # If stop requested...
    if self.stateMachine.stopRequest:
      # We didn't finish this line.  Run it again.
      self._io.plcLogic.stopSeek()
      self._io.head.stop()
      self._log.add(self.__class__.__name__, "SEEK_STOP", "Seek stop requested")
      self._noteSeekStop = True
      self.stateMachine.stopRequest = False

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

      self.changeState(self.stateMachine.States.STOP)


# end class
