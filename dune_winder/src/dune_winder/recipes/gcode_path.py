###############################################################################
# Name: gcode_path.py
# Uses: Path representation with canonical G-code FunctionCall instructions.
###############################################################################

import random

from dune_winder.gcode.model import FunctionCall, Opcode
from dune_winder.gcode.parser import parse_line_text
from dune_winder.gcode.renderer import render_function_call
from dune_winder.library.Geometry.Location import Location

from .Path3d import Path3d
from .gcode_functions import HEAD_LOCATION_BACK


class GCodePath(Path3d):
  """A path that includes canonical G-code function calls."""

  def __init__(self, offset=Location()):
    Path3d.__init__(self, offset)

    # Keyed by path index; each value is a list of FunctionCall objects.
    self._gCode = {}
    self._comment = {}
    self._seekForceX = []
    self._seekForceY = []
    self._seekForceZ = []

  def _asFunctionCall(self, gCode):
    if isinstance(gCode, FunctionCall):
      return gCode

    if hasattr(gCode, "as_function_call"):
      return gCode.as_function_call()

    if hasattr(gCode, "toG_Code"):
      parsed = parse_line_text(gCode.toG_Code())
      for item in parsed.items:
        if isinstance(item, FunctionCall):
          return item

    raise TypeError("Unsupported G-Code function object: " + repr(gCode))

  def pushComment(self, comment):
    index = len(self.path)
    self._comment[index] = comment

  def push_gcode(self, gCode):
    functionCall = self._asFunctionCall(gCode)
    index = len(self.path)
    if index in self._gCode:
      self._gCode[index].append(functionCall)
    else:
      self._gCode[index] = [functionCall]

  def pushG_Code(self, gCode):
    self.push_gcode(gCode)

  def pushSeekForce(self, forceX=False, forceY=False, forceZ=False):
    index = len(self.path)
    if forceX:
      self._seekForceX.append(index)
    if forceY:
      self._seekForceY.append(index)
    if forceZ:
      self._seekForceZ.append(index)

  def toG_Code(self, output, name, isCommentOut=False):
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
          output.write(" " + render_function_call(gCode))

      if index in self._comment:
        output.write(" ( " + self._comment[index] + " )")

      output.write("\n")
      lineNumber += 1

  def _pointLabel(self, output, location, text, layer=None):
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

  def toSketchUpRuby(self, output, layer, half="", enableLables=True):
    Path3d.toSketchUpRuby(self, output, "G-Code path " + layer + "-" + half)

    if enableLables:
      output.write('layer = Sketchup.active_model.layers.add "G-Codes"' + "\n")
      for index, gCodeList in self._gCode.items():
        location = self.path[index]

        for gCode in gCodeList:
          function = int(gCode.opcode)
          parameters = list(gCode.parameters)

          if int(Opcode.LATCH) == function:
            side = "front"
            if parameters and HEAD_LOCATION_BACK == int(parameters[0]):
              side = "back"

            self._pointLabel(output, location, "Z-latch " + side, "layer")

          if int(Opcode.SEEK_TRANSFER) == function:
            self._pointLabel(output, location, "Seek transfer", "layer")

          if int(Opcode.PIN_CENTER) == function:
            self._pointLabel(
              output,
              location,
              "Center " + str(parameters[0]) + "-" + str(parameters[1]),
              "layer",
            )

          if int(Opcode.OFFSET) == function:
            self._pointLabel(output, location, "Offset", "layer")
