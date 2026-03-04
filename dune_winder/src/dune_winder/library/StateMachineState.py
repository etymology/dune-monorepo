###############################################################################
# Name: StateMachineState.py
# Uses: Template of a state of a state machine.
# Date: 2016-02-10
# Author(s):
#   Andrew Que <aque@bb7.com>
# Notes:
#   State machines have one or more states.  This class needs to have a parent
#   'StateMachine' and contains a template that defines functions that need to
#   run when the state machine transitions into, and out of the state, as well
#   as the logic for the state.
###############################################################################
class StateMachineState:
  # ---------------------------------------------------------------------
  def __init__(self, stateMachine, stateIndex: int):
    """
    Constructor.

    Args:
      stateMachine: Parent state machine.
      stateIndex: Number that represents this state.

    """

    self.stateMachine = stateMachine
    self.stateMachine.addState(self, stateIndex)

  # ---------------------------------------------------------------------
  def changeState(self, state):
    """
    Transition to a new state.

    Args:
      newState: The state to transition into.

    Returns:
      True if there was an error, false if not.
    """

    return self.stateMachine.changeState(state)

  # ---------------------------------------------------------------------
  def enter(self):
    """
    Function called when entering this state.

    Returns:
      True if there was an error, false if not.
    """

    return False

  # ---------------------------------------------------------------------
  def exit(self):
    """
    Function called when exiting this state.

    Returns:
      True if there was an error, false if not.
    """

    return False

  # ---------------------------------------------------------------------
  def update(self):
    """
    Update the state logic. Call periodically.

    """

    return False
