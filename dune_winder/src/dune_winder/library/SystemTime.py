###############################################################################
# Name: SystemTime.py
# Uses: Normal system time source.
# Date: 2016-02-12
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

import time
import datetime
from dune_winder.library.TimeSource import TimeSource


class SystemTime(TimeSource):
  # -------------------------------------------------------------------
  def sleep(self, sleepTime):
    """
    Sleep for specified time (in seconds).

    Args:
      sleepTime: Time to sleep (in seconds and can be fractional).
    """
    time.sleep(sleepTime)

  # -------------------------------------------------------------------
  def get(self):
    """
    Return the current time.

    Returns:
      Returns current time.
    """

    return datetime.datetime.utcnow()

  # -------------------------------------------------------------------
  def getDelta(self, then, now=None):
    """
    Return the amount of time between two time stamps.

    Args:
      then - Starting time.
      now - Current time.  If omitted, the current time is used.

    Returns:
      Time between to time stamps.
    """

    if now is None:
      now = self.get()

    delta = now - then

    return delta.total_seconds()
