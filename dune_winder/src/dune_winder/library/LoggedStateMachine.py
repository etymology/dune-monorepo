###############################################################################
# Name: LoggedStateMachine.py
# Uses: A state machine whose transitions are logged.
# Date: 2016-02-10
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################
from .StateMachine import StateMachine
from dune_winder.library.Log import Log


class LoggedStateMachine(StateMachine):
  # ---------------------------------------------------------------------
  def __init__(self, log: Log):
    """
    Constructor.

    Args:
      log: Log file to write transitions.

    """

    StateMachine.__init__(self)
    self.log = log

  # ---------------------------------------------------------------------
  def changeState(self, newState):
    """
    Transition to a new state.

    Args:
      newState: The state to transition into.

    Returns:
      True if there was an error, false if not.
    """

    oldModeName = "<None>"
    if self.state:
      oldModeName = self.state.__class__.__name__

    isError = StateMachine.changeState(self, newState)

    newModeName = "<None>"
    newState = self.states[newState]
    if newState:
      newModeName = newState.__class__.__name__

    message = "Mode changed from "
    if isError:
      message = "Failed to change mode from "

    # Log mode change.
    self.log.add(
      self.__class__.__name__,
      "MODE",
      message + oldModeName + " to " + newModeName,
      [oldModeName, newModeName],
    )

    return isError
