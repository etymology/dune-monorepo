###############################################################################
# Name: StopMode.py
# Uses: Root state in which there is no machine motion.
# Date: 2016-02-11
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from dune_winder.library.state_machine_state import StateMachineState
from dune_winder.library.logged_state_machine import LoggedStateMachine
from dune_winder.io.Maps.base_io import BaseIO


class StopMode(StateMachineState):
  # ====================================
  # Idle mode.
  # Idle means the machine isn't moving, but is ready to move.
  # ====================================
  class Idle(StateMachineState):
    # -------------------------------------------------------------------
    def __init__(self, stateMachine, state, io, control):
      """
      Constructor.

      Args:
        stateMachine: Parent state machine.
        state: Integer representation of state.
        io: Instance of I/O map.
        control: Instance of primary control state machine.
      """

      StateMachineState.__init__(self, stateMachine, state)
      self.io = io
      self.control = control

    # -------------------------------------------------------------------
    def update(self):
      """
      Periodic update function. Checks for critical I/O changes or a request for mode change.

      """

      # Check for E-Stop.
      if self.io.estop.get():
        self.changeState(self.stateMachine.States.ESTOP)
      elif self.io.park.get():
        self.changeState(self.stateMachine.States.PARK)
      elif self.control.startRequest:
        self.control.changeState(self.control.States.WIND)
        self.control.startRequest = False
      elif self.control.manualRequest:
        self.control.changeState(self.control.States.MANUAL)
        self.control.manualRequest = False
      elif self.control.calibrationRequest:
        self.control.changeState(self.control.States.CALIBRATE)
        self.control.calibrationRequest = False

  # ====================================
  # Emergency stop.
  # Emergency stop is active and machine cannot change into any other mode
  # until this is clear.
  # ====================================
  class EStop(StateMachineState):
    # -------------------------------------------------------------------
    def __init__(self, stateMachine, state, io: BaseIO, control):
      """
      Constructor.

      Args:
        stateMachine: Parent state machine.
        state: Integer representation of state.
        io: Instance of I/O map.
        control: Instance of primary control state machine.

      """

      StateMachineState.__init__(self, stateMachine, state)
      self.io = io
      self.control = control

    # -------------------------------------------------------------------
    def update(self):
      """
      Periodic update function. Waits for E-Stop to clear.

      """

      # Not allowed to change to other modes until E-Stop is clear.
      if not self.io.estop.get():
        self.changeState(self.stateMachine.States.IDLE)

  # ====================================
  # Parked.
  # Head is locked in the park position.  Motors are unable to move and
  # mode changes are not allowed until park is clear.  Can switch to ESTOP
  # should that occur.
  # ====================================
  class Park(StateMachineState):
    # -------------------------------------------------------------------
    def __init__(self, stateMachine, state, io, control):
      """
      Constructor.

      Args:
        stateMachine: Parent state machine.
        state: Integer representation of state.
        io: Instance of I/O map.
        control: Instance of primary control state machine.

      """

      StateMachineState.__init__(self, stateMachine, state)
      self.io = io
      self.control = control

    # -------------------------------------------------------------------
    def update(self):
      """
      Periodic update function. Waits for Park to clear, or E-Stop.

      """

      # Check for E-Stop.
      if self.io.estop.get():
        self.changeState(self.stateMachine.States.ESTOP)
      # See if still in park.
      elif not self.io.park.get():
        self.changeState(self.stateMachine.States.IDLE)

  # =====================================================================
  # Sub-state machine for stop modes.
  # =====================================================================
  class StopStateMachine(LoggedStateMachine):
    class States:
      IDLE = 0
      ESTOP = 1
      PARK = 2

    # end class

    # -------------------------------------------------------------------
    def __init__(self, control, io: BaseIO, log):
      """
      Constructor.

      Args:
        control: Instance of primary control state machine.
        io: Instance of I/O map.
        log: Log file to write state changes.

      """

      LoggedStateMachine.__init__(self, log)
      StopMode.Idle(self, self.States.IDLE, io, control)
      StopMode.EStop(self, self.States.ESTOP, io, control)
      StopMode.Park(self, self.States.PARK, io, control)

      self.changeState(self.States.IDLE)

  # end class

  # ---------------------------------------------------------------------
  def __init__(self, stateMachine, state, io, log):
    """
    Constructor.

    Args:
      stateMachine: Parent state machine.
      state: Integer representation of state.
      io: Instance of I/O map.
      log: Log file to write state changes.
    """

    StateMachineState.__init__(self, stateMachine, state)

    self.io = io
    self.stateMachine = stateMachine
    self.stopStateMachine = self.StopStateMachine(stateMachine, io, log)

  # ---------------------------------------------------------------------
  def update(self):
    """
    Update function that is called periodically.

    """

    # Update active sub-state.
    self.stopStateMachine.update()

  # ---------------------------------------------------------------------
  def isIdle(self):
    """
    Return true if the sub-state idle.

    Returns:
      True if the sub-state idle.
    """
    return self.stopStateMachine.States.IDLE == self.stopStateMachine.getState()
