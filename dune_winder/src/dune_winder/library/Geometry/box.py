###############################################################################
# Name: Box.py
# Uses: Defines a box.
# Date: 2016-03-29
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from dune_winder.library.Geometry.location import Location
from dune_winder.library.Geometry.line import Line


class Box:
  # -------------------------------------------------------------------
  def _intersection(self, start, lineA, lineB, limits, limit, limitValue):
    """
    Intersect two lines.  If that point happened before the start point,
    return it.  Otherwise return the start point.

    Args:
      start - Starting location.
      lineA - First line.
      lineB - Second line.
      limit - Map of limits used bound the location.
      limitValue - Edge to limit.

    Returns:
      Instance of Location.
    """

    # Get the intersection.
    destination = lineA.intersection(lineB)

    # If this is the first intersection before any others, use it and
    # set new limits.
    if (
      destination.x >= limits["minX"]
      and destination.x <= limits["maxX"]
      and destination.y >= limits["minY"]
      and destination.y <= limits["maxY"]
      and destination.x != float("inf")
      and destination.y != float("inf")
    ):
      start = destination
      limits[limit] = limitValue

    return start

  # -------------------------------------------------------------------
  def intersectSegment(self, segment):
    """
    Figure out where a segment will intersect the box.  The segment is extended
    until the end point makes an intersection.

    Args:
      segment: Segment to intersect with.  Must be located inside the box.

    Returns:
      An instance of Location where the end point of the line intersects the
      box.  None if the segment is actually a point.
    """

    destination = None
    if not segment.isPoint():
      # Create a line form the segment.
      line = Line.fromSegment(segment)

      # Python has no ability to pass integers by reference, so we use a
      # dictionary.
      limits = {}
      limits["minX"] = float("-inf")
      limits["minY"] = float("-inf")
      limits["maxX"] = float("inf")
      limits["maxY"] = float("inf")

      # Initial destination.
      destination = Location()

      if segment.start.x > segment.finish.x:
        lineLeft = Line(Line.VERTICLE_SLOPE, self._left)
        destination = self._intersection(
          destination, line, lineLeft, limits, "minX", self._left
        )
      elif segment.start.x < segment.finish.x:
        lineRight = Line(Line.VERTICLE_SLOPE, self._right)
        destination = self._intersection(
          destination, line, lineRight, limits, "maxX", self._right
        )

      if segment.start.y < segment.finish.y:
        lineTop = Line(0, self._top)
        destination = self._intersection(
          destination, line, lineTop, limits, "maxY", self._top
        )
      elif segment.start.y > segment.finish.y:
        lineBottom = Line(0, self._bottom)
        destination = self._intersection(
          destination, line, lineBottom, limits, "minY", self._bottom
        )

    return destination

  # -------------------------------------------------------------------
  def __init__(self, left, top, right, bottom):
    """
    Constructor.

    Args:
      left: Location (x) of left side.
      top: Location (y) of top side.
      right: Location (x) of right side.
      bottom: Location (y) of bottom side.
    """
    self._left = left
    self._top = top
    self._right = right
    self._bottom = bottom

  # ---------------------------------------------------------------------
  def __str__(self):
    """
    Get a string representation of object.

    Returns:
      String with the four corners of the box starting on the bottom left
      and moving clockwise.
    """
    return (
      "[ "
      + str(self._left)
      + ", "
      + str(self._top)
      + ", "
      + str(self._right)
      + ", "
      + str(self._bottom)
      + "]"
    )
