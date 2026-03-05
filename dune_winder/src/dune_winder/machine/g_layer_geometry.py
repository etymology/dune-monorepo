###############################################################################
# Name: G_LayerGeometry.py
# Uses: Geometry specific to the 2nd grid layer, G.
# Date: 2016-03-23
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from .gx_layer_geometry import GX_LayerGeometry


class G_LayerGeometry(GX_LayerGeometry):
  # -------------------------------------------------------------------
  def __init__(self):
    """
    Constructor.
    """

    GX_LayerGeometry.__init__(self)
    self._configure_grid_layer_geometry(
      row_count=481,
      depth_mm=114.2,
      right_edge_offset=self.boardSpacing + self.boardThickness,
      apa_offset_x=-13.23 + self.boardThickness,
    )
