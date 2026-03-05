###############################################################################
# Name: G_LayerGeometry.py
# Uses: Geometry specific to the 2nd grid layer, G.
# Date: 2016-03-23
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################


from dune_winder.library.Geometry.Location import Location

from .GX_LayerGeometry import GX_LayerGeometry


class G_LayerGeometry(GX_LayerGeometry):
  # -------------------------------------------------------------------
  def __init__(self):
    """
    Constructor.
    """

    GX_LayerGeometry.__init__(self)

    # Number of rows.
    self.rows = int(481 / self.scale)

    # Total number of pins.
    self.pins = self.rows * 2

    # Values to translate front/back pin numbers.
    self.frontBackOffset = self.rows
    self.frontBackModulus = self.pins

    # Spacing between pins and front to back.
    self.depth = 114.2 / self.scale

    # Locations of the two columns of pins.
    self.leftEdge = -self.boardThickness
    self.rightEdge = (
      self.layerLength / self.scale + self.boardSpacing + self.boardThickness
    )

    # Offset from APA's (0,0,0) position.
    self.apaOffsetX = -13.23 + self.boardThickness
    self.apaOffsetY = 0
    self.apaOffsetZ = (self.apaThickness - self.depth) / 2

    self.apaOffset = Location(self.apaOffsetX, self.apaOffsetY, self.apaOffsetZ)

    # Travel for partial Z.  Should place head level with board and below pin
    # height.
    self.mostlyRetract = (self.zTravel - self.depth) / (2 * self.scale)
    self.mostlyExtend = (self.zTravel + self.depth) / (2 * self.scale)

    self.startPinFront = self.pins / 2 + 1
    self.directionFront = 1
    self.startPinBack = 1
    self.directionBack = 1

    # The grid parameters are a list of parameters for how the grid is constructed.
    # Columns:
    #   Count - Number of pins this row in the table represents.
    #   dx - Change in x each iteration.
    #   dy - Change in y each iteration.
    #   off.x - Starting x offset for initial position of first pin in this set.
    #   off.y - Starting y offset for initial position of first pin in this set.
    #   ort - Wire orientation.
    self.gridFront = [
      # Count      dx                dy  off.x  off.y  ort.
      [self.rows, 0, self.pinSpacing, 0, 0, "0"],  # Right
      [0, 0, 0, 0, 0, "0"],  # Top
      [self.rows, 0, -self.pinSpacing, 0, 0, "0"],  # Left
      [0, 0, 0, 0, 0, "0"],  # Bottom
    ]

    # Back is identical to front.
    self.gridBack = self.gridFront
