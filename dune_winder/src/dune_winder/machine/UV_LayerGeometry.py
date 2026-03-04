###############################################################################
# Name: UV_LayerGeometry.py
# Uses: Geometry common to the induction (U and V) layers.
# Date: 2016-03-24
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

import math
from .LayerGeometry import LayerGeometry


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
