###############################################################################
# Name: WindMode.py
# Uses: Main control mode for winding process.
# Date: 2016-02-11
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from dune_winder.library.state_machine_state import StateMachineState
from dune_winder.core.control_events import SetLoopModeEvent, StopMotionEvent
from dune_winder.io.Maps.base_io import BaseIO
from dune_winder.library.log import Log


class WindMode(StateMachineState):
  # ---------------------------------------------------------------------
  def __init__(
    self, stateMachine, state: int, io: BaseIO, log: Log
  ):
    """
    Constructor.

    Args:
      stateMachine: Parent state machine.
      state: Integer representation of state.
      io: Instance of I/O map.
      gCodeHandler: Instance of G-Code handler.
    """

    StateMachineState.__init__(self, stateMachine, state)
    self._io = io
    self._log = log
    self._startTime = None
    self._currentLine = 0
    self._stopRequested = False
    self._loopMode = False
    self._windTime = 0

  # ---------------------------------------------------------------------
  def enter(self):
    """
    Function called when entering this state.

    Returns:
      True if there was an error, false if not.
    """
    isError = False

    if (
      self.stateMachine.gCodeHandler is None
      or not self.stateMachine.gCodeHandler.isG_CodeLoaded()
    ):
      isError = True
      self._log.add(
        self.__class__.__name__,
        "WIND",
        "Wind cannot start because no there is no G-Code file loaded to execute.",
      )

    if not isError and self.stateMachine.gCodeHandler.isDone():
      print("isError = ", isError)
      print(
        "self.stateMachine.gCodeHandler.isDone() = ",
        self.stateMachine.gCodeHandler.isDone(),
      )
      isError = True
      self._log.add(
        self.__class__.__name__, "WIND", "Wind cannot start because G-Code is finished."
      )

    if not isError:
      self._startTime = self.stateMachine.systemTime.get()
      self._windTime = 0
      self._stopRequested = False
      self._log.add(
        self.__class__.__name__,
        "WIND",
        "G-Code execution begins at line "
        + str(self.stateMachine.gCodeHandler.getLine() + 2),
        [self.stateMachine.gCodeHandler.getLine() + 2],
      )

    return isError

  # ---------------------------------------------------------------------
  def exit(self):
    """
    Function called when exiting this state.

    Returns:
      True if there was an error, false if not.
    """

    self._windTime += self.stateMachine.systemTime.getDelta(self._startTime)

    deltaString = self.stateMachine.systemTime.getElapsedString(self._windTime)

    # Log message that wind is complete.
    self._log.add(
      self.__class__.__name__,
      "WIND_TIME",
      "Wind ran for " + deltaString + ".",
      [self._windTime],
    )

    self.stateMachine.gCodeHandler.stop()
    return False

  # ---------------------------------------------------------------------
  def update(self):
    """
    Update function that is called periodically.
    """
    # Want to print G-Code line

    # If stop requested...
    if self._stopRequested:  # and self.io.Tension_10N.get() :
      # We didn't finish this line.  Run it again.
      self._io.plcLogic.stopSeek()
      self.changeState(self.stateMachine.States.STOP)
      self._stopRequested = False
    else:
      # Update G-Code handler.
      isDone = self.stateMachine.gCodeHandler.poll()

      if self.stateMachine.gCodeHandler.isG_CodeError():
        # Log message that wind is complete.
        self._log.add(
          self.__class__.__name__,
          "WIND_ERROR",
          "G-Code error.  " + self.stateMachine.gCodeHandler.getG_CodeErrorMessage(),
          self.stateMachine.gCodeHandler.getG_CodeErrorData(),
        )

        self.stateMachine.gCodeHandler.clearCodeError()

        isDone = True

      # if self.stateMachine.gCodeHandler.isTensionError():
      #   # Log message that wind is complete.
      #   self._log.add(
      #     self.__class__.__name__,
      #     "TENSION_ERROR",
      #     "Tension error. " + self.stateMachine.gCodeHandler.getTensionErrorMessage(),
      #     self.stateMachine.gCodeHandler.getTensionErrorData(),
      #   )
      #   self.stateMachine.gCodeHandler.clearTensionError()

      # Is G-Code execution complete?
      if not isDone:
        if self.stateMachine.gCodeHandler.isG_CodeLoaded():
          line = self.stateMachine.gCodeHandler.getLine()
          if self._currentLine != line:
            # Log message that wind is complete.
            self._log.add(
              self.__class__.__name__,
              "LINE",
              "G-Code executing line N" + str(line + 2),
              [self._currentLine + 2, line + 2],
            )

            # if (
            #   self.stateMachine.gCodeHandler._frequency > 0
            #   and self.stateMachine.gCodeHandler._wireTension > 0
            #   and not self.stateMachine.gCodeHandler._tensionTesting
            # ):
            #   # Log message that tension measurement was carried out successfully.
            #   self._log.add(
            #     self.__class__.__name__,
            #     "TENSION",
            #     "Tension measurement executed on wire "
            #     + str(self.stateMachine.gCodeHandler._wireTension)
            #     + " , frequency = "
            #     + str(self.stateMachine.gCodeHandler._frequency)
            #     + "  ",
            #     [
            #       self.stateMachine.gCodeHandler._wireTension,
            #       self.stateMachine.gCodeHandler._frequency,
            #     ],
            #   )
          self._currentLine = line

      # Is G-Code execution complete?
      if isDone:
        # Log message that wind is complete.
        self._log.add(self.__class__.__name__, "WIND", "G-Code execution complete")

        if self._loopMode:
          # Rewind.
          self.stateMachine.gCodeHandler.setLine(-1)
        else:
          # Return to stopped state.
          self.changeState(self.stateMachine.States.STOP)

  # ---------------------------------------------------------------------
  def handle(self, event):
    """
    Handle events while wind mode is active.
    """

    if isinstance(event, StopMotionEvent):
      self._stopRequested = True
      return True

    if isinstance(event, SetLoopModeEvent):
      self.setLoopMode(event.enabled)
      return True

    return False

  # ---------------------------------------------------------------------
  def getLoopMode(self):
    return self._loopMode

  # ---------------------------------------------------------------------
  def setLoopMode(self, enabled):
    self._loopMode = enabled

  # ---------------------------------------------------------------------
  def getWindTime(self):
    return self._windTime

  # ---------------------------------------------------------------------
  def resetWindTime(self):
    self._windTime = 0
