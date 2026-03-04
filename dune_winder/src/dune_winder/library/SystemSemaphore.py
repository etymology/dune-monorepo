###############################################################################
# Name: SystemSemaphore.py
# Uses: Semaphores that also unblock on system shutdown.
# Date: 2016-02-10
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

import threading


class SystemSemaphore:
  _activeList = []
  _isActive = True

  # ---------------------------------------------------------------------
  def __init__(self, count=1):
    """
    Constructor.

    Args:
      count: Initial semaphore count.

    """

    self._semaphore = threading.Semaphore(count)

  # ---------------------------------------------------------------------
  def acquire(self):
    """
    Acquire the semaphore. (Identical to threading.Semaphore.acquire)

    """

    if SystemSemaphore._isActive:
      SystemSemaphore._activeList.append(self)
      self._semaphore.acquire()

  # ---------------------------------------------------------------------
  def release(self):
    """
    Release the semaphore. (Identical to threading.Semaphore.release)

    """

    self._semaphore.release()
    if self in SystemSemaphore._activeList:
      SystemSemaphore._activeList.remove(self)

  # ---------------------------------------------------------------------
  @staticmethod
  def releaseAll():
    """
    Force the release of all blocked semaphores.

    """

    SystemSemaphore._isActive = False
    for semaphore in SystemSemaphore._activeList:
      semaphore._semaphore.release()

    SystemSemaphore._activeList = []
