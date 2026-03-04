###############################################################################
# Name: G_CodePath.py
# Uses: A specific path that includes G-Code instructions.
# Date: 2016-03-23
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

import random

from dune_winder.library.Geometry.Location import Location
from dune_winder.machine.G_Codes import G_Codes

from .Path3d import Path3d
from .G_CodeFunctions.HeadLocationG_Code import HeadLocationG_Code


class G_CodePath(Path3d):
  """
  A specific path that includes G-Code instructions.
  """

  # ---------------------------------------------------------------------
  def __init__(self, offset=Location()):
    """
    Constructor.
    """
    Path3d.__init__(self, offset)

    # Dictionary of what G-Code functions are mapped to what path locations.
    # The dictionary key is the index into self.path at which the G-Code functions
    # occur.  Each dictionary entry contains a list of G_Code objects.
    self._gCode = {}
    self._comment = {}
    self._seekForceX = []
    self._seekForceY = []
    self._seekForceZ = []

  # ---------------------------------------------------------------------
  def pushComment(self, comment):
    """
    Add a comment to line.

    Args:
      comment: Test of comment.
    """
    index = len(self.path)
    self._comment[index] = comment

  # ---------------------------------------------------------------------
  def pushG_Code(self, gCode):
    """
    Add a G-Code function to the next path entry.  Call before calling any
    'push' functions.  Can be called more than once per path point.

    Args:
      gCode: Instance of G_Code to insert.
    """
    index = len(self.path)
    if index in self._gCode:
      self._gCode[index].append(gCode)
    else:
      self._gCode[index] = [gCode]

  # ---------------------------------------------------------------------
  def pushSeekForce(self, forceX=False, forceY=False, forceZ=False):
    """
    Force one or more of the axises to print their position.  Needed when an
    edge seek has been done.

    Args:
      forceX - Cause X position is output.
      forceY - Cause Y position is output.
      forceZ - Cause Z position is output.
    """
    index = len(self.path)
    if forceX:
      self._seekForceX.append(index)

    if forceY:
      self._seekForceY.append(index)

    if forceZ:
      self._seekForceZ.append(index)

  # ---------------------------------------------------------------------
  def toG_Code(self, output, name, isCommentOut=False):
    """
    Turn path into G-Code text.

    Args:
      output: Open file to place output.
      name: Name to put in header of G-Code file.
      isCommendOut: Deprecated.  Leave False.
    """
    if isCommentOut:
      output.write("# ")

    output.write("( " + name + " )\n")
    lineNumber = 1

    lastX = 0
    lastY = 0
    lastZ = 0

    for index, point in enumerate(self.path):
      if isCommentOut:
        output.write("# ")

      output.write("N" + str(lineNumber))

      if index in self._seekForceX:
        lastX = None

      if index in self._seekForceY:
        lastY = None

      if index in self._seekForceZ:
        lastZ = None

      if lastX != point.x:
        output.write(" X" + str(point.x))
        lastX = point.x

      if lastY != point.y:
        output.write(" Y" + str(point.y))
        lastY = point.y

      if lastZ != point.z:
        output.write(" Z" + str(point.z))
        lastZ = point.z

      if index in self._gCode:
        for gCode in self._gCode[index]:
          output.write(" " + gCode.toG_Code())

      if index in self._comment:
        output.write(" ( " + self._comment[index] + " )")

      output.write("\n")
      lineNumber += 1

  # ---------------------------------------------------------------------
  def _pointLabel(self, output, location, text, layer=None):
    """
    Make a SketchUp label at specified location.

    Args:
      output: Open file for output.
      location: The location to label.
      text: The text to place on this label.
    """
    x = location.x / 25.4
    y = location.y / 25.4
    z = location.z / 25.4

    output.write(
      "point = Geom::Point3d.new [ "
      + str(x)
      + ","
      + str(z)
      + ","
      + str(y)
      + " ]"
      + "\n"
    )

    x = random.uniform(-3, 3)
    y = random.uniform(-3, 3)

    output.write("vector = Geom::Vector3d.new " + str(x) + ",0," + str(y) + "\n")
    output.write(
      'label = Sketchup.active_model.entities.add_text "'
      + text
      + '", point, vector'
      + "\n"
    )

    if layer:
      output.write("label.layer = " + layer + "\n")

  # ---------------------------------------------------------------------
  def toSketchUpRuby(self, output, layer, half="", enableLables=True):
    """
    Turn path into Ruby code for use in SketchUp.  Labels G-Code functions.
    Useful for visualizing paths.

    Args:
      output: Open file for output.
      half: Layer label for which half.
      enables: True to enable labels G-Code labels.
    """
    Path3d.toSketchUpRuby(self, output, "G-Code path " + layer + "-" + half)

    if enableLables:
      output.write('layer = Sketchup.active_model.layers.add "G-Codes"' + "\n")
      for index, gCodeList in self._gCode.items():
        location = self.path[index]

        for gCode in gCodeList:
          function = int(gCode.getFunction())

          if G_Codes.LATCH == function:
            side = "front"
            if HeadLocationG_Code.BACK == int(gCode.getParameter(0)):
              side = "back"

            self._pointLabel(output, location, "Z-latch " + side, "layer")

          if G_Codes.SEEK_TRANSFER == function:
            self._pointLabel(output, location, "Seek transfer", "layer")

          if G_Codes.PIN_CENTER == function:
            self._pointLabel(
              output,
              location,
              "Center " + gCode.getParameter(0) + "-" + gCode.getParameter(1),
              "layer",
            )

          if G_Codes.OFFSET == function:
            self._pointLabel(output, location, "Offset", "layer")
