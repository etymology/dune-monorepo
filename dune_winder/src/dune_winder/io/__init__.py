"""I/O package compatibility helpers.

Historically this project used capitalized subpackage directories (for
example ``Primitives``), while most imports now use lowercase package names
(``primitives``). Registering aliases here keeps both working.
"""

from importlib import import_module
import sys


_ALIASES = {
  "devices": "Devices",
  "maps": "Maps",
  "primitives": "Primitives",
  "systems": "Systems",
  "types": "Types",
}

for alias, target in _ALIASES.items():
  module = import_module(f".{target}", __name__)
  sys.modules[f"{__name__}.{alias}"] = module
