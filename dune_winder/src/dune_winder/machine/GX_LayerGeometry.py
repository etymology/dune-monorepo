###############################################################################
# Name: GX_LayerGeometry.py
# Uses: Geometry common to G and X layers.
# Date: 2016-03-24
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from .LayerGeometry import LayerGeometry


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
