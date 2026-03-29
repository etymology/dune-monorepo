"""I/O package compatibility helpers.

The project currently contains a mix of legacy capitalized package directories
(``Devices``/``Maps``/``Primitives``) and newer lowercase imports
(``devices``/``maps``/``primitives``). Import whichever spelling exists on
disk, then register both spellings to the same module object.
"""

from importlib import import_module
import sys


_ALIASES = {
  "devices": ("devices", "Devices"),
  "maps": ("maps", "Maps"),
  "primitives": ("primitives", "Primitives"),
}


def _import_first_available(*names: str):
  last_error: ModuleNotFoundError | None = None
  for name in names:
    try:
      return import_module(f".{name}", __name__)
    except ModuleNotFoundError as exc:
      if exc.name != f"{__name__}.{name}":
        raise
      last_error = exc
  if last_error is not None:
    raise last_error
  raise ModuleNotFoundError(f"No package variants found under {__name__}")


for canonical_name, variants in _ALIASES.items():
  module = _import_first_available(*variants)
  for variant in variants:
    sys.modules[f"{__name__}.{variant}"] = module
  sys.modules[f"{__name__}.{canonical_name}"] = module
