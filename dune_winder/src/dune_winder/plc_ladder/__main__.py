from __future__ import annotations

import sys
from pathlib import Path

from .codegen import transpile_routine_to_python
from .parser import RllParser


def main() -> None:
  args = sys.argv[1:]
  if not args:
    print(
      "Usage: python -m dune_winder.plc_ladder <pasteable.rll> [more.rll ...]",
      file=sys.stderr,
    )
    sys.exit(1)

  parser = RllParser()
  rendered = []
  for arg in args:
    path = Path(arg)
    if not path.exists():
      print(f"File not found: {path}", file=sys.stderr)
      sys.exit(1)
    routine = parser.parse_routine_path(path)
    rendered.append(transpile_routine_to_python(routine))
  print("\n".join(rendered), end="")


if __name__ == "__main__":
  main()
