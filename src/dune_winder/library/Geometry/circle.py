###############################################################################
# Name: Circle.py
# Uses: Defines intermediate circle.
# Date: 2016-08-26
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

import math
from dune_winder.library.Geometry.location import Location


class Circle:
  # -------------------------------------------------------------------
  def tangentPoint(self, orientationString, target):
    """
    Return the location where intermediate line runs tangent to the target location.

    Args:
      orientationString: Defines quadrant for which to of two tangent points are
        returned.  String in form nn where n=T/B/L/R for top/bottom/left/right.
      target: Instance of Location defining the point at which the tangent line
        originates.

    Returns:
      Instance of Location, or None if the orientation make intermediate tangent line
      impossible.
    """

    result = None

    deltaX = self._center.x - target.x
    deltaY = self._center.y - target.y

    ORIENTATION_TABLE = {
      #  ex ey   a   x   y
      "RT": [1, 1, 1, 1, 1],
      "TR": [-1, -1, -1, 1, 1],
      "BL": [1, 1, -1, 1, -1],
      "LB": [-1, -1, 1, 1, -1],
      "TL": [1, -1, 1, 1, 1],
      "LT": [-1, 1, -1, 1, 1],
      "RB": [1, -1, -1, 1, -1],
      "BR": [-1, 1, 1, 1, -1],
    }

    orientationString = orientationString.upper()
    assert orientationString in ORIENTATION_TABLE

    def sign(intermediate):
      return (intermediate > 0) - (intermediate < 0)

    orientation = ORIENTATION_TABLE[orientationString]
    if orientation[0] == -sign(deltaX) and orientation[1] == -sign(deltaY):
      intermediate = deltaY * math.sqrt(deltaX**2 + deltaY**2 - self._radius**2)
      intermediate *= orientation[2]
      intermediate = (-self._radius * deltaX) - intermediate
      intermediate /= deltaX**2 + deltaY**2

      x = orientation[3] * intermediate * self._radius + self._center.x
      y = (
        orientation[4] * self._radius * math.sqrt(1 - intermediate**2) + self._center.y
      )

      result = Location(x, y, self._center.z)

    return result

  # -------------------------------------------------------------------
  def __init__(self, center, radius):
    """
    Constructor.

    Args:
      center: Instance of Location defining the center of the circle.
      radius: Radius of circle.

    Notes:
      Circles are always 2d and in the X/Y plane.  The Z component is preserved
      but otherwise unused.
    """
    self._center = center
    self._radius = radius

  # ---------------------------------------------------------------------
  def __str__(self):
    """
    Get intermediate string representation of object.

    Returns:
      String with the center and radius of circle.
    """
    return "[ " + str(self._center) + "-" + str(self._radius) + "]"
