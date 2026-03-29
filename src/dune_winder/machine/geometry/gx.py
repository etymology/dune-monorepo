###############################################################################
# Name: GX_LayerGeometry.py
# Uses: Geometry common to G and X layers.
# Date: 2016-03-24
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from dune_winder.library.Geometry.location import Location

from .layer import LayerGeometry


class GX_LayerGeometry(LayerGeometry):
  # -------------------------------------------------------------------
  def __init__(self):
    """
    Constructor.
    """

    LayerGeometry.__init__(self)

    # Spacing between wires.
    # 230mm board width divided by 48 wires per board.
    self.pinSpacing = 230.0 / 48

  # -------------------------------------------------------------------
  def _configure_grid_layer_geometry(
    self,
    *,
    row_count,
    depth_mm,
    right_edge_offset,
    apa_offset_x,
  ):
    """
    Configure common geometry values for straight grid layers (G/X).

    Args:
      row_count: Nominal number of rows at scale 1.
      depth_mm: Layer depth in millimeters at scale 1.
      right_edge_offset: Offset from scaled layer length to right edge.
      apa_offset_x: X offset of APA origin.
    """

    # Number of rows.
    self.rows = int(row_count / self.scale)

    # Total number of pins.
    self.pins = self.rows * 2

    # Values to translate front/back pin numbers.
    self.frontBackOffset = self.rows
    self.frontBackModulus = self.pins

    # Spacing between pins and front to back.
    self.depth = depth_mm / self.scale

    # Locations of the two columns of pins.
    self.leftEdge = -self.boardThickness
    self.rightEdge = self.layerLength / self.scale + right_edge_offset

    # Offset from APA's (0,0,0) position.
    self.apaOffsetX = apa_offset_x
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

    # The grid parameters are a list of parameters for how the grid is
    # constructed.
    self.gridFront = [
      [self.rows, 0, self.pinSpacing, 0, 0, "0"],  # Right
      [0, 0, 0, 0, 0, "0"],  # Top
      [self.rows, 0, -self.pinSpacing, 0, 0, "0"],  # Left
      [0, 0, 0, 0, 0, "0"],  # Bottom
    ]

    # Back is identical to front.
    self.gridBack = self.gridFront
