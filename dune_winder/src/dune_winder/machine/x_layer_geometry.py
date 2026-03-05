###############################################################################
# Name: X_LayerGeometry.py
# Uses: Geometry specific to the 1st grid layer, X.
# Date: 2016-03-23
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from .gx_layer_geometry import GX_LayerGeometry


class X_LayerGeometry(GX_LayerGeometry):
  # -------------------------------------------------------------------
  def __init__(self):
    """
    Constructor.
    """

    GX_LayerGeometry.__init__(self)
    self._configure_grid_layer_geometry(
      row_count=480,
      depth_mm=85.7,
      right_edge_offset=2 * self.boardSpacing,
      apa_offset_x=0,
    )
