###############################################################################
# Name: Segment.py
# Uses: A segment is two points connected by a line.
# Date: 2016-03-23
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################
import math


class Segment:
  """
  A segment is two points connected by a line.
  """

  # ---------------------------------------------------------------------
  def __init__(self, start, finish):
    """
    Constructor.

    Args:
      start: Instance of Location defining the starting location.
      finish: Instance of Location defining the finishing location.
    """
    self.start = start
    self.finish = finish

  # ---------------------------------------------------------------------
  def deltaX(self):
    """
    Get the distance between x of segment.

    Returns:
      Distance between x of segment.
    """
    return self.start.x - self.finish.x

  # ---------------------------------------------------------------------
  def deltaY(self):
    """
    Get the distance between y of segment.

    Returns:
      Distance between y of segment.
    """
    return self.start.y - self.finish.y

  # ---------------------------------------------------------------------
  def deltaZ(self):
    """
    Get the distance between z of segment.

    Returns:
      Distance between z of segment.
    """
    return self.start.z - self.finish.z

  # ---------------------------------------------------------------------
  def length(self):
    """
    Return the length of segment.

    Returns:
      Length of segment.
    """
    deltaX = self.deltaX()
    deltaY = self.deltaY()
    deltaZ = self.deltaZ()

    # Thank you Pythagoras.
    return math.sqrt(deltaX**2 + deltaY**2 + deltaZ**2)

  # ---------------------------------------------------------------------
  def slope(self):
    """
    Slope of X/Y.

    Returns:
      Slope of the X/Y part of the line.  Returns infinite if there is no
      slope (i.e. no delta X).
    """
    deltaX = self.deltaX()
    deltaY = self.deltaY()

    slope = float("inf")
    if 0 != deltaX:
      slope = deltaY / deltaX

    return slope

  # ---------------------------------------------------------------------
  def intercept(self):
    """
    Y-Intercept of X/Y.

    Returns:
      Y-Intercept of X/Y.  Returns infinite if there is no
      slope (i.e. no delta X).
    """
    return self.start.y - self.slope() * self.start.x

  # ---------------------------------------------------------------------
  def isPoint(self):
    """
    Check to see if this segment is actual a single point.

    Returns:
      True if segment is a point rather than a line segment.
    """
    return (self.start.x == self.finish.x) and (self.start.y == self.finish.y)

  # ---------------------------------------------------------------------
  def __str__(self):
    """
    Get a string representation of object.

    Returns
      String representation of object in form (x1, y1, z1)-(x2, y2, z2) where
      xn/yn/zn are numbers and n is 1 for starting location, 2 for finishing.
    """
    return str(self.start) + "-" + str(self.finish)
