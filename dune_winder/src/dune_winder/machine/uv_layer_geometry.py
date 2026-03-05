###############################################################################
# Name: UV_LayerGeometry.py
# Uses: Geometry common to the induction (U and V) layers.
# Date: 2016-03-24
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

import math

from dune_winder.library.Geometry.location import Location

from .layer_geometry import LayerGeometry


class UV_LayerGeometry(LayerGeometry):
  # -------------------------------------------------------------------
  def __init__(self):
    """
    Constructor.
    """

    LayerGeometry.__init__(self)

    # The APA frame is divided into pitches--a place were two wires cross.
    self.pitches = 400

    self.rows = self.pitches / self.scale
    self.columns = 2 * self.rows

    # Spacing between pins and front to back.
    self.deltaX = 8.0
    self.deltaY = 5.75

    # Nominal slope of lines.
    self.slope = self.deltaY / self.deltaX

    # Diagonal length of pitch.
    self.lengthXY = math.sqrt(self.deltaX**2 + self.deltaY**2)

    # Primary angle (in radians) between wires.
    self.angle = math.atan(self.deltaY / self.deltaX)

    # Distance between wires.
    self.wireSpacing = self.deltaY / math.sqrt(self.deltaY**2 / self.deltaX**2 + 1)

    #
    # Data about the pins.
    #

    # Nominal pin diameter is based on the board thickness and the X/Y ratio.
    # The manufactured diameter is 2.43mm.
    self.pinRadius = (
      self.deltaX * self.boardHalfThickness / self.lengthXY - self.wireRadius
    )
    self.pinDiameter = self.pinRadius * 2
    self.pinHeight = 2

  # -------------------------------------------------------------------
  def _configure_induction_layer(
    self,
    *,
    pins,
    front_back_offset,
    front_back_modulus,
    depth_mm,
    start_pin_front,
  ):
    """
    Configure shared state for U/V induction layers.

    Args:
      pins: Total number of pins.
      front_back_offset: Pin offset between front/back sides.
      front_back_modulus: Modulus for front/back pin translation.
      depth_mm: Layer depth in millimeters at scale 1.
      start_pin_front: First front-side pin.
    """

    # Total number of pins.
    self.pins = pins

    # Values to translate front/back pin numbers.
    self.frontBackOffset = front_back_offset
    self.frontBackModulus = front_back_modulus

    # Spacing between pins and front to back.
    self.depth = depth_mm / self.scale

    # Travel for partial Z.  Should place head level with board and below pin
    # height.
    self.mostlyRetract = (self.zTravel - self.depth) / (2 * self.scale)
    self.mostlyExtend = (self.zTravel + self.depth) / (2 * self.scale)

    self.startPinFront = start_pin_front
    self.directionFront = -1
    self.startPinBack = 1
    self.directionBack = 1

  # -------------------------------------------------------------------
  def _set_apa_offset(self, x, y, z=0):
    """
    Set APA origin offset.

    Args:
      x: X offset.
      y: Y offset.
      z: Z offset.
    """
    self.apaOffsetX = x
    self.apaOffsetY = y
    self.apaOffsetZ = z
    self.apaOffset = Location(self.apaOffsetX, self.apaOffsetY, self.apaOffsetZ)
