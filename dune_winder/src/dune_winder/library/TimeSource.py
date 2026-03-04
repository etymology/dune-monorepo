###############################################################################
# Name: TimeSource.py
# Uses: Abstract class for a source of time.
# Date: 2016-02-12
# Author(s):
#   Andrew Que <aque@bb7.com>
# Notes:
#     A time source provides a reference of forward-moving time.  This
#   typically just comes from the system clock, but could also come from a
#   simulated source.  The time source must only increase, but is not required
#   to do so in even increments.
#     What objects are actually returned are irrelevant to this unit, but
#   need to stay consistent in the implementation used.  It will typically
#   be a time.time() object.
###############################################################################

from abc import ABCMeta, abstractmethod


class TimeSource(metaclass=ABCMeta):
  # Make class abstract.
  @abstractmethod
  def sleep(self, sleepTime):
    """
    Sleep for specified time (in seconds).

    Args:
      sleepTime: Time to sleep (in seconds and can be fractional).
    """
    pass

  # -------------------------------------------------------------------
  @abstractmethod
  def get(self):
    """
    Return the current time.

    Returns:
      Returns current time.
    """

    pass

  # -------------------------------------------------------------------
  @abstractmethod
  def getDelta(self, then, now):
    """
    Return the amount of time between two time stamps.

    Args:
      then - Starting time.
      now - Current time.  If omitted, the current time is used.

    Returns:
      Time between to time stamps.
    """

    pass

  # -------------------------------------------------------------------
  def getElapsedString(self, seconds):
    """
    Return a string representing elapsed time.

    Args:
      seconds - Elapsed seconds.

    Returns:
      String representing elapsed time.

    Example:
      1d 2h 3m 4.567s
      For 1 day, 2 hours, 3 minutes, 4.567 seconds.
    """

    deltaString = ""
    days = int(seconds / (60 * 60 * 24))
    seconds -= days * (60 * 60 * 24)

    hours = int(seconds / (60 * 60))
    seconds -= hours * (60 * 60)

    minutes = int(seconds / (60))
    seconds -= minutes * (60)

    if days > 0:
      deltaString += str(days) + "d "

    if hours > 0:
      deltaString += str(hours) + "h "

    if minutes > 0:
      deltaString += str(minutes) + "m "

    deltaString += "{:2.3f}s".format(seconds)

    return deltaString
