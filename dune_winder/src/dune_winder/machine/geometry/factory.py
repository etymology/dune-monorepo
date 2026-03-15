from .layer import LayerGeometry
from .x import X_LayerGeometry
from .v import V_LayerGeometry
from .u import U_LayerGeometry
from .g import G_LayerGeometry

_LAYERS: dict[str, type[LayerGeometry]] = {
  "X": X_LayerGeometry,
  "V": V_LayerGeometry,
  "U": U_LayerGeometry,
  "G": G_LayerGeometry,
}


def create_layer_geometry(layer_name: str) -> LayerGeometry:
  """
  Factory function that returns a LayerGeometry instance for the given layer name.

  Args:
    layer_name: Name of layer geometry to create ("X", "V", "U", or "G").

  Returns:
    Instance of the corresponding LayerGeometry subclass.

  Raises:
    ValueError: If layer_name is not one of the valid layer names.
  """
  if layer_name not in _LAYERS:
    valid = ", ".join(sorted(_LAYERS))
    raise ValueError(f"Unknown layer name {layer_name!r}. Valid layer names are: {valid}")
  return _LAYERS[layer_name]()
