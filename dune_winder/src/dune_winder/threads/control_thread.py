###############################################################################
# Name: ControlThread.py
# Uses: Primary system control thread.  Loop runs master state machine.
# Date: 2016-02-04
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from dune_winder.machine.settings import Settings
from dune_winder.core.io_log import IO_Log
from dune_winder.threads.primary_thread import PrimaryThread
from dune_winder.library.system_time import SystemTime
from dune_winder.library.log import Log
from dune_winder.core.control_state_machine import ControlStateMachine
from dune_winder.io.Maps.base_io import BaseIO


class ControlThread(PrimaryThread):
  # ---------------------------------------------------------------------
  def __init__(
    self,
    io: BaseIO,
    log: Log,
    stateMachine: ControlStateMachine,
    systemTime: SystemTime,
    isIO_Logged: bool,
  ):
    """
    Constructor.

    Args:
      io: Instance of I/O map.
      log: Instance of system log.
      stateMachine: Instance of state machine.
      systemTime: Instance of SystemTime.
      isIO_Logged: True if I/O should be logged (typically False).
    """

    PrimaryThread.__init__(self, "ControlThread", log)
    self._io = io
    self._systemTime = systemTime
    self._stateMachine = stateMachine
    self._isIO_Logged = isIO_Logged

    if isIO_Logged:
      self._ioLog = IO_Log(Settings.IO_LOG)

  # ---------------------------------------------------------------------
  def body(self):
    """
    Body of control thread--the "main loop" of the program.
    """

    while PrimaryThread.isRunning:
      # Mark the start of this update.
      startTime = self._systemTime.get()

      # Update I/O.
      self._io.pollInputs()

      # Update state machine.
      self._stateMachine.update()

      # Mark time at end of update.
      endTime = self._systemTime.get()

      # Measure time update took.
      updateTime = endTime - startTime
      updateTime = updateTime.total_seconds()

      # Update I/O log.
      if self._isIO_Logged:
        self._ioLog.log(startTime, updateTime)

      # Calculate how long to sleep before updating again.
      # Roughly creates intervals of Settings.IO_UPDATE_TIME.
      sleepTime = Settings.IO_UPDATE_TIME - updateTime
      if sleepTime > 0:
        # Wait before updating again.
        self._systemTime.sleep(sleepTime)


# end class
