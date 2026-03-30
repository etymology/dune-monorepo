from __future__ import annotations

import argparse
from pathlib import Path

from dune_winder.paths import PLC_ROOT
from dune_winder.plc_generated.hmi_stop_request_14 import emit_rll


DEFAULT_OUTPUT_PATH = PLC_ROOT / "HMI_Stop_Request_14" / "main" / "pasteable.rll"


def build_argument_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Generate the HMI stop-request PLC routine pasteable.rll from the ladder AST source.",
  )
  parser.add_argument(
    "--output",
    type=Path,
    default=DEFAULT_OUTPUT_PATH,
    help="Output pasteable.rll path. Defaults to plc/HMI_Stop_Request_14/main/pasteable.rll.",
  )
  parser.add_argument(
    "--check",
    action="store_true",
    help="Fail if the existing output does not match the generated ladder text.",
  )
  return parser


def main(argv=None) -> int:
  parser = build_argument_parser()
  args = parser.parse_args(argv)
  output_path = Path(args.output)
  rendered = emit_rll()

  if args.check:
    existing = output_path.read_text(encoding="utf-8") if output_path.exists() else ""
    if existing != rendered:
      print(f"generated ladder differs from {output_path}")
      return 1
    print(f"generated ladder matches {output_path}")
    return 0

  output_path.parent.mkdir(parents=True, exist_ok=True)
  output_path.write_text(rendered, encoding="utf-8")
  print(f"wrote {output_path}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
