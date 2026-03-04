###############################################################################
# Name: LayerGeometry.py
# Uses: Geometry common to all layers.
# Date: 2016-03-23
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from .APA_Geometry import APA_Geometry


class LayerGeometry(APA_Geometry):
  # -------------------------------------------------------------------
  def __init__(self):
    """
    Constructor.
    """

    APA_Geometry.__init__(self)

    # Pitches are the number of wire crossings.
    self.pitches = 400

    # Spacing between pins and X/Y.
    self.pitchX = 8.0
    self.pitchY = 5.75

    # Diameter of the wire (in mm).
    self.wireDiameter = 0.15
    self.wireRadius = self.wireDiameter / 2

    # Thickness of each layer board.
    self.boardThickness = 3.175  # 1/8"
    self.boardHalfThickness = self.boardThickness / 2

    # Spacing between board.
    self.boardSpacing = 3.35

    # Length of the layer on the frame.
    # Around 6393.8923913044
    self.layerLength = (
      (2 * self.pitches - 0.5) * self.pitchX
      + self.boardThickness * (self.pitchX / self.pitchY - 1)
      - self.boardSpacing
    )

    # Edge name to grid index.
    self.edgeToGridIndex = {"L": 0, "T": 1, "R": 2, "B": 3}
