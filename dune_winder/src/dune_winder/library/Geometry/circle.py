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


if __name__ == "__main__":
  from dune_winder.library.math_extra import MathExtra

  tests = [
    {
      "circle": Circle(Location(0, 0), 9),
      "position": Location(45, 45),
      "results": {
        "TR": None,
        "TL": None,
        "RB": None,
        "RT": None,
        "BL": None,
        "BR": Location(7.2, -5.4),
        "LT": Location(-5.4, 7.2),
        "LB": None,
      },
    },
    {
      "circle": Circle(Location(0, 0), 9),
      "position": Location(-45, 45),
      "results": {
        "TR": None,
        "TL": None,
        "RB": None,
        "RT": Location(5.4, 7.2),
        "BL": Location(-7.2, -5.4),
        "BR": None,
        "LT": None,
        "LB": None,
      },
    },
    {
      "circle": Circle(Location(0, 0), 9),
      "position": Location(-45, -45),
      "results": {
        "TR": None,
        "TL": Location(-7.2, 5.4),
        "RB": Location(5.4, -7.2),
        "RT": None,
        "BL": None,
        "BR": None,
        "LT": None,
        "LB": None,
      },
    },
    {
      "circle": Circle(Location(0, 0), 9),
      "position": Location(45, -45),
      "results": {
        "TR": Location(7.2, 5.4),
        "TL": None,
        "RB": None,
        "RT": None,
        "BL": None,
        "BR": None,
        "LT": None,
        "LB": Location(-5.4, -7.2),
      },
    },
    # Location based on actual drawing.
    {
      "circle": Circle(Location(588.274, 170.594), 1.215),
      "position": Location(598.483, 166.131),
      "results": {
        "TR": Location(588.8791774, 171.6475584),
        "TL": None,
        "RB": None,
        "RT": None,
        "BL": None,
        "BR": None,
        "LT": None,
        "LB": Location(587.9116216, 169.4342988),
      },
    },
  ]

  # For each of the tests...
  for test in tests:
    circle = test["circle"]

    # Setup position
    position = test["position"]

    # For each orientation result...
    results = test["results"]
    for orientation in results:
      # Get tangent point.
      location = circle.tangentPoint(orientation, position)

      # Verify result.
      if results[orientation]:
        assert MathExtra.isclose(location.x, results[orientation].x)
        assert MathExtra.isclose(location.y, results[orientation].y)
      else:
        assert location is None
