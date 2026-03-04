###############################################################################
# Name: LayerUV_Recipe.py
# Uses: Common functions shared by U and V layer recipe.
# Date: 2016-04-06
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

import math

from dune_winder.library.Geometry.Location import Location

from .G_CodeFunctions.WireLengthG_Code import WireLengthG_Code
from .G_CodeFunctions.SeekTransferG_Code import SeekTransferG_Code
from .G_CodeFunctions.OffsetG_Code import OffsetG_Code
from .G_CodeFunctions.ArmCorrectG_Code import ArmCorrectG_Code
from .G_CodeFunctions.AnchorPointG_Code import AnchorPointG_Code
from .G_CodeFunctions.TransferCorrectG_Code import TransferCorrectG_Code

from .RecipeGenerator import RecipeGenerator
from .HeadPosition import HeadPosition
from .G_CodePath import G_CodePath


class LayerUV_Recipe(RecipeGenerator):
  OVERSHOOT = 200

  # ---------------------------------------------------------------------
  def __init__(self, geometry):
    """
    Constructor.

    Args:
      geometry - Instance (or child) of UV_LayerGeometry.
    """
    RecipeGenerator.__init__(self, geometry)

    self.orientations = {}
    self.anchorOrientations = {}

  # -------------------------------------------------------------------
  def _createNode(self, grid, orientation, side, depth, startPin, direction):
    """
    Create nodes.
    This is a list of pins starting with the bottom left corner moving in
    a clockwise direction.

    Args:
      grid: Grid parameters from geometry.
      orientation: True/False for orientation.
      side: F/B for front/back.
      depth: Thickness of layer.
      startPin: Starting pin number closest to (0,0).
      direction: +1/-1 for incrementing starting pin number.

    Returns:
      Adds to 'self.nodes'.
      Nothing is returned.
    """

    if orientation:
      pass
    else:
      pass

    # A wire can have 8 orientations, but 4 of these have identical angles.
    # This is a lookup table to translate wire orientation to an angle.
    angle180 = math.radians(180)
    orientationAngles = {
      "TR": -self.geometry.angle,
      "RT": -self.geometry.angle,
      "TL": self.geometry.angle,
      "LT": self.geometry.angle,
      "BL": -self.geometry.angle + angle180,
      "LB": -self.geometry.angle + angle180,
      "BR": self.geometry.angle + angle180,
      "RB": self.geometry.angle + angle180,
    }

    # Lookup table for what pin to center the wire.  Centering is always the
    # target pin, and the pin to the left or right.
    if orientation:
      # Left  Top   Right  Bottom
      centering = [+1, -1, +1, -1]
    else:
      centering = [-1, +1, -1, +1]

    x = 0
    y = 0
    setIndex = 0
    pinNumber = startPin
    for parameter in grid:
      count = parameter[0]
      xInc = parameter[1]
      yInc = parameter[2]
      x += parameter[3]
      y += parameter[4]
      anchorOrientation = parameter[5]

      for _ in range(0, count):
        location = Location(round(x, 5) + 0, round(y, 5) + 0, depth)
        pin = side + str(pinNumber)
        self.nodes[pin] = location
        self.centering[pin] = centering[setIndex]
        self.anchorOrientations[pin] = anchorOrientation
        self.orientations[pin] = orientationAngles[anchorOrientation]

        pinNumber += direction

        if 0 == pinNumber:
          pinNumber = self.geometry.pins
        elif pinNumber > self.geometry.pins:
          pinNumber = 1

        x += xInc
        y += yInc

      # Backup for last position.
      x -= xInc
      y -= yInc
      setIndex += 1

  # -------------------------------------------------------------------
  def _createNet(self, windSteps, direction=1):
    """
    Create net list.  This is a path of node indexes specifying the order in which they are
    connected.

    Args:
      windSteps: Number of steps needed to complete the wind.
      direction: Initial direction (1 or -1).
    """
    # Number of items in above list.
    repeat = len(self.net)

    # # Initial direction.
    # direction = 1

    # All remaining net locations are based off a simple the previous locations.
    for netNumber in range(repeat, windSteps):
      pin = self.net[netNumber - repeat]
      side = pin[0]
      number = int(pin[1:])
      self.net.append(side + str(number + direction))
      direction = -direction

  # ---------------------------------------------------------------------
  def _nextNet(self):
    """
    Advance to the next net in list.  Pushes length calculation to next G-Code
    and builds the path node list.

    Returns:
      True if there is an other net, False net list if finished.
    """

    result = False

    if self.netIndex < len(self.net):
      lastNet = self.net[self.netIndex]

    # Get the next net.
    self.netIndex += 1

    if self.netIndex < len(self.net):
      # The orientation specifies one of four points on the pin the wire will
      # contact: upper/lower left/right.  This comes from the orientation
      # look-up table.
      net = self.net[self.netIndex]
      orientation = self.orientations[net]
      anchorOrientation = self.anchorOrientations[lastNet]

      # Location of the the next pin.
      location = self.location(self.netIndex)

      # Add the pin location to the base path.
      self.basePath.push(location.x, location.y, location.z)

      # Add the offset pin location to the node path and get the length of this
      # piece of wire.
      length = self.nodePath.pushOffset(location, self.geometry.pinRadius, orientation)

      # Push a G-Code length function to the next G-Code command to specify the
      # amount of wire consumed by this move.
      self.gCodePath.pushG_Code(WireLengthG_Code(length))

      # Push the anchor point of the last placed wire.
      self.gCodePath.pushG_Code(AnchorPointG_Code(lastNet, anchorOrientation))

      result = True

    return result

  # ---------------------------------------------------------------------
  def _wrapCenter(self):
    """
    Sequence for wrapping around the top in the center.
    """

    # To center pin.
    if self._nextNet():
      self.gCodePath.pushG_Code(self.pinCenterTarget("XY"))
      self.gCodePath.pushG_Code(SeekTransferG_Code())
      self.gCodePath.pushG_Code(ArmCorrectG_Code())
      self.gCodePath.push()
      self.z.set(HeadPosition.OTHER_SIDE)

    if self._nextNet():
      # Hook pin and line up with next pin on other side.
      self.gCodePath.pushG_Code(self.pinCenterTarget("X"))
      self.gCodePath.pushG_Code(TransferCorrectG_Code("X"))
      self.gCodePath.push()

      # Go to other side and seek past pin so it is hooked with next move.
      self.gCodePath.pushG_Code(self.pinCenterTarget("Y"))
      self.gCodePath.pushG_Code(OffsetG_Code(y=-LayerUV_Recipe.OVERSHOOT))
      self.gCodePath.push()

  # ---------------------------------------------------------------------
  def _wrapEdge(self, direction):
    """
    Sequence for wrapping around the bottom left/right edges.

    Args:
      direction: -1 for left side, 1 for right side.
    """

    # Direction corrected overshoot.
    xOffset = direction * LayerUV_Recipe.OVERSHOOT

    # Column pin.
    if self._nextNet():
      self.gCodePath.pushG_Code(self.pinCenterTarget("XY"))
      self.gCodePath.pushG_Code(SeekTransferG_Code())
      self.gCodePath.pushG_Code(ArmCorrectG_Code())
      self.gCodePath.push()
      self.z.set(HeadPosition.PARTIAL)

    # Column, other side.
    if self._nextNet():
      self.gCodePath.pushG_Code(self.pinCenterTarget("Y"))
      self.gCodePath.push()
      self.z.set(HeadPosition.OTHER_SIDE)
      self.gCodePath.pushG_Code(self.pinCenterTarget("Y"))
      self.gCodePath.pushG_Code(TransferCorrectG_Code("Y"))
      self.gCodePath.push()
      self.gCodePath.pushG_Code(self.pinCenterTarget("X"))
      self.gCodePath.pushG_Code(OffsetG_Code(x=xOffset))
      self.gCodePath.push()

    if self._nextNet():
      # Anchor point is set--find a path between.
      self.gCodePath.pushG_Code(self.pinCenterTarget("XY"))
      self.gCodePath.pushG_Code(SeekTransferG_Code())
      self.gCodePath.pushG_Code(ArmCorrectG_Code())
      self.gCodePath.push()
      self.z.set(HeadPosition.OTHER_SIDE)

    if self._nextNet():
      self.gCodePath.pushG_Code(self.pinCenterTarget("X"))
      self.gCodePath.pushG_Code(TransferCorrectG_Code("X"))
      self.gCodePath.push()
      self.gCodePath.pushG_Code(self.pinCenterTarget("Y"))
      self.gCodePath.pushG_Code(OffsetG_Code(y=LayerUV_Recipe.OVERSHOOT))
      self.gCodePath.push()

  # ---------------------------------------------------------------------
  def _wind(self, start1, start2, direction, windsOverride=None):
    """
    Wind the layer using the class parameters.

    Args:
      start1: Starting pin locations for first half.
      start2: Starting pin locations for second half.
      windsOverride: Set to specify the number to winds to make before stopping.
        Normally left to None.

    Returns:
      Sets up self.gCodePath, self.nodePath, and self.basePath.
      Nothing is returned by function.
    """

    # Current net.
    self.netIndex = 0

    net = self.net[self.netIndex]

    self.nodePath.pushOffset(
      self.location(self.netIndex), self.geometry.pinRadius, self.orientations[net]
    )

    self.gCodePath = G_CodePath()
    self.z = HeadPosition(self.gCodePath, self.geometry, HeadPosition.FRONT)
    self.z.set(HeadPosition.BACK)

    self.gCodePath.pushG_Code(self.pinCenterTarget("XY", start1))
    self.gCodePath.push()
    self.basePath.push(
      self.gCodePath.last.x, self.gCodePath.last.y, self.gCodePath.last.z
    )

    # To wind half the layer, divide by half and the number of steps in a
    # circuit.
    totalCount = self.geometry.pins / 6 + 1
    halfCount = self.geometry.pins / 12

    if windsOverride:
      totalCount = windsOverride
      halfCount = totalCount / 2

    # A single loop completes one circuit of the APA starting and ending on the
    # lower left.
    for index in range(1, totalCount + 1):
      self._wrapCenter()
      self._wrapEdge(direction)
      self._wrapCenter()
      self._wrapEdge(-direction)

      self.gCodePath.pushComment("Loop " + str(index) + " of " + str(totalCount))
      self.gCodePath.push()

      if halfCount == index:
        self.firstHalf = self.gCodePath
        self.gCodePath = G_CodePath()
        self.gCodePath.pushG_Code(self.pinCenterTarget("XY", start2))
        self.gCodePath.push()
        self.z = HeadPosition(self.gCodePath, self.geometry, HeadPosition.FRONT)
        self.z.set(HeadPosition.BACK)

    if self.firstHalf:
      self.secondHalf = self.gCodePath
    else:
      self.firstHalf = self.gCodePath

    self.gCodePath = None
