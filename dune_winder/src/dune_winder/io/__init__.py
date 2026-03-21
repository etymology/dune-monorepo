"""I/O package compatibility helpers.

Historically this project used capitalized subpackage directories (for example
``Devices``), while the checked-in package layout is now lowercase
(``devices``). Register aliases for both spellings so legacy imports and newer
imports resolve to the same module objects.
"""

from importlib import import_module
import sys


_ALIASES = {
  "Devices": "devices",
  "Maps": "maps",
  "Primitives": "primitives",
}

for legacy_name, package_name in _ALIASES.items():
  module = import_module(f".{package_name}", __name__)
  sys.modules[f"{__name__}.{package_name}"] = module
  sys.modules[f"{__name__}.{legacy_name}"] = module
