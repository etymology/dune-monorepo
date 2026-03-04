###############################################################################
# Name: Camera.py
# Uses: Abstract class for vision system camera.
# Date: 2016-05-19
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from .IO_Point import IO_Point
from abc import ABCMeta, abstractmethod


class Camera(IO_Point, metaclass=ABCMeta):
  # Make class abstract.
  list = []
  map = {}

  # ---------------------------------------------------------------------
  def __init__(self, name):
    """
    Constructor.

    Args:
      name: Name of camera.
    """

    # Make sure this name isn't already in use.
    assert name not in Camera.list

    IO_Point.__init__(self, name)

    Camera.list.append(self)
    Camera.map[name] = self

  # ---------------------------------------------------------------------
  @abstractmethod
  def isOnline(self):
    """
    See if camera is online.

    Returns:
      True if online, False if not.
    """
    pass

  # ---------------------------------------------------------------------
  @abstractmethod
  def trigger(self):
    """
    Trigger an image acquisition.
    """
    pass

  # ---------------------------------------------------------------------
  @abstractmethod
  def setPattern(self, pattern):
    """
    Select which pattern recognition program should be used.

    Args:
      pattern - Which pattern to use.
    """
    pass

  # ---------------------------------------------------------------------
  @abstractmethod
  def getPattern(self):
    """
    Return which pattern recognition program is be used.

    Returns:
      Pattern recognition program is be used.
    """
    pass
