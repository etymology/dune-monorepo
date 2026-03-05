###############################################################################
# Name: GeometrySelection.py
# Uses: Create layer geometry based on layer name.
# Date: 2016-11-01
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from .layer_geometry import LayerGeometry
from .x_layer_geometry import X_LayerGeometry
from .v_layer_geometry import V_LayerGeometry
from .u_layer_geometry import U_LayerGeometry
from .g_layer_geometry import G_LayerGeometry


class GeometrySelection(LayerGeometry):
  # -------------------------------------------------------------------
  def __new__(_, layerName: str):
    """
    The new operator will actually not create an instance of this class, but
    rather an instance of the requested layer's geometry class.

    Args:
      layerName: Name of layer geometry to create (X/V/U/G).

    Returns:
      Instance of the requested layer geometry.
    """

    # Lookup table of layer geometries.
    LAYERS = {
      "X": X_LayerGeometry,
      "V": V_LayerGeometry,
      "U": U_LayerGeometry,
      "G": G_LayerGeometry,
    }

    # Select requested geometry.
    specificLayer = LAYERS[layerName]

    # Return instance of specified layer.
    return specificLayer()


# Unit test.
if __name__ == "__main__":
  xGeometry = GeometrySelection("X")
  vGeometry = GeometrySelection("V")
  uGeometry = GeometrySelection("U")
  gGeometry = GeometrySelection("G")

  assert isinstance(xGeometry, X_LayerGeometry)
  assert isinstance(vGeometry, V_LayerGeometry)
  assert isinstance(uGeometry, U_LayerGeometry)
  assert isinstance(gGeometry, G_LayerGeometry)
