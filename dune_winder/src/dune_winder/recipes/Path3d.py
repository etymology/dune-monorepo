###############################################################################
# Name: Path3d.py
# Uses: A list of Location objects that define a path.
# Date: 2016-03-23
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

import math

from dune_winder.library.Geometry.Location import Location
from dune_winder.library.Geometry.Segment import Segment


class Path3d:
  """
  A list of Location objects that define a path.
  """

  # ---------------------------------------------------------------------
  def __init__(self, baseOffset=Location()):
    """
    Constructor.
    """
    self.path = []
    self.last = Location()
    self.baseOffset = baseOffset

  # ---------------------------------------------------------------------
  def pushOffset(self, location, radius=0, angle=0):
    """
    Add an offset position to path.  Offset specified as a radius and angle.

    Args:
      location: Instance of Location specifying 2d location (z is ignored).
      z: The z-coordinate.
      radius: Radius to offset by.
      angle: Angle of offset.

    Returns:
      The length between this new position and the previous position.
    """
    offsetX = radius * math.sin(angle)
    offsetY = radius * math.cos(angle)

    return self.push(location.x + offsetX, location.y + offsetY, location.z)

  # ---------------------------------------------------------------------
  def push(self, x=None, y=None, z=None):
    """
    Add an offset position to path.  Offset specified as a radius and angle.

    Args:
      x: The x-coordinate.
      y: The y-coordinate.
      z: The z-coordinate.

    Returns:
      The length between this new position and the previous position.
    """

    if x is None:
      x = self.last.x - self.baseOffset.x

    if y is None:
      y = self.last.y - self.baseOffset.y

    if z is None:
      z = self.last.z - self.baseOffset.z

    x += self.baseOffset.x
    y += self.baseOffset.y
    z += self.baseOffset.z

    location = Location(x, y, z)
    self.path.append(location)

    segment = Segment(self.last, location)

    length = 0
    if self.last is not None:
      length = segment.length()

    self.last = location

    return length

  # ---------------------------------------------------------------------
  def toSketchUpRuby(self, output, name="Path"):
    """
    Turn path into Ruby code for use in SketchUp.  Useful for visualizing
    paths.

    Args:
      output: Open file for output.
      name: Name of SketchUp layer for output.
    """

    output.write('layer = Sketchup.active_model.layers.add "' + name + '"' + "\n")
    output.write("oldLayer = Sketchup.active_model.active_layer" + "\n")
    output.write("Sketchup.active_model.active_layer = layer" + "\n")
    output.write("line = Sketchup.active_model.entities.add_line ")

    isFirst = True
    for point in self.path:
      # Convert millimeters to inches.  Sketch-up always works in inches.
      x = point.x / 25.4
      y = point.y / 25.4
      z = point.z / 25.4

      # Add a comma if not the first item in list.
      if not isFirst:
        output.write(",")
      else:
        isFirst = False

      output.write("[" + str(x) + "," + str(z) + "," + str(y) + "]")

    output.write("\n")
    output.write("Sketchup.active_model.active_layer = oldLayer" + "\n")

  # ---------------------------------------------------------------------
  def totalLength(self):
    """
    Get the total length of path.

    Returns:
      Total length of path.
    """
    length = 0
    lastPoint = self.path[0]
    for point in self.path[1:]:
      segment = Segment(lastPoint, point)
      length += segment.length()
      lastPoint = point

    return length

  # ---------------------------------------------------------------------
  def __len__(self):
    """
    Return number of nodes in path.

    Returns:
      Number of nodes in path.
    """
    return len(self.path)
