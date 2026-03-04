###############################################################################
# Name: Line.py
# Uses: 2d line in the form of "m x + b" where m is the slope and b is the
#       Y-Intercept.
# Date: 2016-03-23
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

import math

from .Location import Location
from .Segment import Segment


class Line:
  """
  2d line in the form of "m x + b" where m is the slope and b is the Y-Intercept.
  """

  VERTICLE_SLOPE = float("inf")

  # ---------------------------------------------------------------------
  @staticmethod
  def fromAngle(angle, intercept):
    """
    Create a line from an angle and intercept, or vector.

    Args:
      angle: Angle in radians.
      intercept: Y-intercept.

    Returns:
      Instance of Line.
    """
    slope = math.tan(angle)

    return Line(slope, intercept)

  # ---------------------------------------------------------------------
  @staticmethod
  def fromSegment(segment):
    """
    Create a line from a line segment.  Useful for extending line segments.

    Args:
      segment: Instance of Segment to create line from.

    Returns:
      Instance of Line.
    """
    slope = segment.slope()
    if slope != float("inf"):
      intercept = segment.intercept()
    else:
      intercept = segment.start.x

    return Line(slope, intercept)

  # ---------------------------------------------------------------------
  @staticmethod
  def fromLocationAndSlope(location, slope):
    """
    Create a line from a single location and a slope.

    Args:
      location: Instance of Location as a known point along the line.
      slope: The slope of the line.

    Returns:
      Instance of Line.
    """
    intercept = location.y - slope * location.x
    return Line(slope, intercept)

  # ---------------------------------------------------------------------
  @staticmethod
  def fromLocations(start, finish):
    """
    Create a line from two locations.

    Args:
      start: Instance of Location for the starting position.
      finish: Instance of Location for the finishing position.

    Returns:
      Instance of Line.
    """
    segment = Segment(start, finish)
    return Line.fromSegment(segment)

  # ---------------------------------------------------------------------
  def __init__(self, slope, intercept):
    """
    Constructor.

    Lines are represented in the form y = m x + b where m is the slope
    and b is the y-intercept.

    Args:
      slope - Slope of line (rise over run).
      intercept - Y-intercept of line (m x + b = 0).
    """
    self.slope = slope
    self.intercept = intercept

  # ---------------------------------------------------------------------
  def intersection(self, line):
    """
    Return the point at which this line and an other intersect one an other.

    Args:
      line: Instance of Line to check for intersection.

    Returns:
      Instance of Location with the point of the intersection.  The location
      will have infinite values for x and y if there is no intersection (i.e.
      the lines are parallel).
    """

    interceptDelta = self.intercept - line.intercept

    x = float("inf")
    y = float("inf")

    # Vertical lines?
    if float("inf") == line.slope or float("inf") == self.slope:
      # If both lines are not vertical...
      if line.slope != self.slope:
        # Calculate positions from the non-vertical line.
        if float("inf") == line.slope:
          x = line.intercept
          y = self.getY(x)
        else:
          x = self.intercept
          y = line.getY(x)
    else:
      slopeDelta = line.slope - self.slope

      # If we have a slope and it is a number.
      if 0 != slopeDelta and slopeDelta == slopeDelta:
        x = interceptDelta / slopeDelta

      y = self.getY(x)

    return Location(x, y)

  # ---------------------------------------------------------------------
  def getAngle(self):
    """
    Get the angle of the line.

    Returns:
      Angle in radians.
    """
    return math.atan(self.slope)

  # ---------------------------------------------------------------------
  def getY(self, x):
    """
    From a given X, get Y.

    Args:
      x: X position along line.

    Returns:
      The y position corresponding to this x position.  Returns infinite if
      the line is horizontal.
    """
    return x * self.slope + self.intercept

  # ---------------------------------------------------------------------
  def getX(self, y):
    """
    From a given Y, get X.

    Args:
      y: Y position along line.

    Returns:
      The x position corresponding to this y position.  Returns infinite if
      the line is horizontal.
    """
    return (y - self.intercept) / self.slope

  # ---------------------------------------------------------------------
  def __str__(self):
    """
    Get a string representation of object.

    Returns
      String representation of object in form y = m x + b where m is the
      slope, and b is the intercept.
    """
    xTerm = str(self.slope) + "x + "
    if float("inf") == self.slope:
      xTerm = ""

    return "y = " + xTerm + str(self.intercept)
