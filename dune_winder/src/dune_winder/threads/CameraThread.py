###############################################################################
# Name: CameraThread.py
# Uses: Thread for camera updates.
# Date: 2016-12-15
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from dune_winder.library.SystemSemaphore import SystemSemaphore
from dune_winder.threads.PrimaryThread import PrimaryThread


class CameraThread(PrimaryThread):
  SHUTDOWN_COUNT = 5

  # Amount of time to sleep if FIFO is empty.
  SLEEP_TIME = 0.050

  # ---------------------------------------------------------------------
  def __init__(self, camera, log, systemTime):
    """
    Constructor.

    Args:
      camera: Instance of IO.Systems.Camera.
      log: Instance of system log.
      systemTime: Instance of SystemTime.
    """
    PrimaryThread.__init__(self, "CameraThread", log)
    self._camera = camera
    self._isRunning = False
    self._semaphore = SystemSemaphore(0)
    self._systemTime = systemTime
    self._shutdownCount = 0
    camera.setCallback(self._setEnable)

  # ---------------------------------------------------------------------
  def _setEnable(self, isEnabled):
    """
    Camera trigger enable callback.  Private.

    Args:
      isEnabled: True if enabling camera trigger, False if disabling.
    """

    self._isRunning = isEnabled

    if isEnabled:
      self._semaphore.release()
    else:
      self._shutdownCount = CameraThread.SHUTDOWN_COUNT

  # ---------------------------------------------------------------------
  def body(self):
    """
    Body of camera thread.
    """
    hasData = False
    while PrimaryThread.isRunning:
      # If not running, wait.
      # NOTE: If we had data last time, keep running until we do not.  Makes
      # sure FIFO is empty before pausing thread.
      if not self._isRunning and not hasData and 0 == self._shutdownCount:
        self._semaphore.acquire()

      # If not shutting down...
      if PrimaryThread.isRunning:
        if self._shutdownCount > 0:
          self._shutdownCount -= 1

        # Assume there will be no sleep (a yield only).
        sleepTime = 0

        # Update camera if running...
        if self._isRunning or self._shutdownCount > 0:
          hasData = self._camera.poll()

          # If there was no data to read, sleep for awhile.  Otherwise, read
          # again soon.
          if not hasData:
            sleepTime = CameraThread.SLEEP_TIME

        # Yield thread time.
        self._systemTime.sleep(sleepTime)


# end class
