###############################################################################
# Name: HardwareMode.py
# Uses: Root state in which the system attempts to connect to hardware.
# Date: 2016-02-11
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from dune_winder.library.StateMachineState import StateMachineState
from dune_winder.library.StateMachine import StateMachine
from dune_winder.io.Maps.BaseIO import BaseIO
from dune_winder.library.Log import Log


class HardwareMode(StateMachineState):
  # ---------------------------------------------------------------------
  def __init__(self, stateMachine: StateMachine, state: int, io: BaseIO, log: Log):
    """
    Constructor.

    Args:
      stateMachine: Parent state machine.
      state: Integer representation of state.
      io: Instance of I/O map.
    """

    StateMachineState.__init__(self, stateMachine, state)
    self.io = io
    self.log = log
    self.isPLC_Working = True
    self.isX_AxisWorking = True
    self.isY_AxisWorking = True
    self.isZ_AxisWorking = True
    self.isStateClear = True

  # ---------------------------------------------------------------------
  def enter(self):
    """
    Enter into manual mode.

    Returns:
      True if there was an error, false if not.  The error can happen
      if there isn't a manual action to preform.
    """

    if self.isPLC_Working and self.io.plcLogic.isError():
      self.log.add(
        self.__class__.__name__,
        "HARD_ERROR",
        "PLC error reported: "
        + self.io.plcLogic.getErrorCodeString()
        + " ["
        + str(self.io.plcLogic.getErrorCode())
        + "]",
        [str(self.io.plcLogic.getErrorCode())],
      )

    return False

  # ---------------------------------------------------------------------
  def exit(self):
    """
    Function called when exiting this state.

    Returns:
      True if there was an error, false if not.
    """

    # Setup the limits.
    self.io.plcLogic.setupLimits()

    return False

  # ---------------------------------------------------------------------
  def update(self):
    """
    Update function that is called periodically.

    """

    # Hardware not communicating?
    if self.io.plc.isNotFunctional():
      if self.isPLC_Working:
        self.log.add(
          self.__class__.__name__, "HARD_ERROR", "Unable to communicate to PLC"
        )
        self.isPLC_Working = False

      # Try and initialize PLC communications.
      self.io.plc.initialize()
    else:
      if not self.isPLC_Working:
        self.log.add(
          self.__class__.__name__, "HARD_ERROR", "Communications to PLC established."
        )
        self.isPLC_Working = True

      xWorking = self.io.xAxis.isFunctional()
      yWorking = self.io.yAxis.isFunctional()
      zWorking = self.io.zAxis.isFunctional()

      isStateClear = not self.io.plcLogic.isError()

      if not self.isStateClear and isStateClear:
        self.log.add(
          self.__class__.__name__,
          "HARD_ERROR",
          "PLC error reported: "
          + self.io.plcLogic.getErrorCodeString()
          + " ["
          + str(self.io.plcLogic.getErrorCode())
          + "]",
          [str(self.io.plcLogic.getErrorCode())],
        )
        self.isStateClear = False

      if not xWorking and self.isX_AxisWorking:
        self.log.add(self.__class__.__name__, "HARD_ERROR", "Fault on x-axis.")
        self.isX_AxisWorking = False

      if not yWorking and self.isY_AxisWorking:
        self.log.add(self.__class__.__name__, "HARD_ERROR", "Fault on y-axis.")
        self.isY_AxisWorking = False

      if not zWorking and self.isZ_AxisWorking:
        self.log.add(self.__class__.__name__, "HARD_ERROR", "Fault on z-axis.")
        self.isZ_AxisWorking = False

      if xWorking and not self.isX_AxisWorking:
        self.log.add(self.__class__.__name__, "HARD_ERROR", "X-axis fault clear.")
        self.isX_AxisWorking = True

      if yWorking and not self.isY_AxisWorking:
        self.log.add(self.__class__.__name__, "HARD_ERROR", "Y-axis fault clear.")
        self.isY_AxisWorking = True

      if zWorking and not self.isZ_AxisWorking:
        self.log.add(self.__class__.__name__, "HARD_ERROR", "Z-axis fault clear.")
        self.isZ_AxisWorking = True

      # If everything is functional...
      if self.io.isFunctional():
        self.log.add(self.__class__.__name__, "HARD_ERROR", "All hardware ready.")
        self.changeState(self.stateMachine.States.STOP)
