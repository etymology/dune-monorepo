###############################################################################
# Name: V_LayerGeometry.py
# Uses: Geometry specific to the 2nd induction layer, V.
# Date: 2016-03-23
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from .UV_LayerGeometry import UV_LayerGeometry

from dune_winder.library.Geometry.Location import Location


class V_LayerGeometry(UV_LayerGeometry):
  # -------------------------------------------------------------------
  def __init__(self):
    """
    Constructor.
    """

    UV_LayerGeometry.__init__(self)

    # Total number of pins.
    self.pins = 2 * self.rows + 2 * self.columns - 1

    # Values to translate front/back pin numbers.
    self.frontBackOffset = self.rows - 1
    self.frontBackModulus = self.pins

    # Spacing between pins and front to back.
    self.depth = 95.2 / self.scale

    # Travel for partial Z.  Should place head level with board and below pin
    # height.
    self.mostlyRetract = (self.zTravel - self.depth) / (2 * self.scale)
    self.mostlyExtend = (self.zTravel + self.depth) / (2 * self.scale)

    self.startPinFront = 399
    self.directionFront = -1
    self.startPinBack = 1
    self.directionBack = 1

    # Alias names for several equations.
    # This makes the patterns in the equations more obvious.
    x = self.deltaX
    y = self.deltaY
    t = self.boardHalfThickness
    s = self.boardSpacing

    # Offset from APA's (0,0,0) position.
    # (Around -1.2712, -1.5875).
    self.apaOffsetX = -t * x / y + t - x / 2 + s
    self.apaOffsetY = -t
    self.apaOffsetZ = 0

    self.apaOffset = Location(self.apaOffsetX, self.apaOffsetY, self.apaOffsetZ)

    # Offsets of pins.
    offsetX0 = 0
    offsetX1 = t * x / y  # ~2.2086956522
    offsetX2 = t * x / y + x / 2  # ~6.2086956522
    offsetX3 = -t * x / y - x / 2  # ~-6.2086956522

    offsetY0 = t + y  # 7.3375
    offsetY1 = t + y  # 7.3375
    offsetY2 = -t - y / 2  # -4.4625
    offsetY3 = -t - y / 2  # -4.4625

    # The grid parameters are a list of parameters for how the grid is constructed.
    # Columns:
    #   Count - Number of pins this row in the table represents.
    #   dx - Change in x each iteration.
    #   dy - Change in y each iteration.
    #   off.x - Starting x offset for initial position of first pin in this set.
    #   off.y - Starting y offset for initial position of first pin in this set.
    #   ort - Wire orientation.
    self.gridFront = [
      # Count                    dx            dy     off.x     off.y  ort.
      [self.rows - 1, 0, self.deltaY, offsetX0, offsetY0, "BL"],  # Right
      [self.columns, self.deltaX, 0, offsetX1, offsetY1, "LB"],  # Top
      [self.rows, 0, -self.deltaY, offsetX2, offsetY2, "TR"],  # Left
      [self.columns, -self.deltaX, 0, offsetX3, offsetY3, "RT"],  # Bottom
    ]

    # Back is identical to front except for orientation.
    self.gridBack = [
      # Count                    dx            dy     off.x     off.y  ort.
      [self.rows - 1, 0, self.deltaY, offsetX0, offsetY0, "TL"],  # Right
      [self.columns, self.deltaX, 0, offsetX1, offsetY1, "RB"],  # Top
      [self.rows, 0, -self.deltaY, offsetX2, offsetY2, "BR"],  # Left
      [self.columns, -self.deltaX, 0, offsetX3, offsetY3, "LT"],  # Bottom
    ]
