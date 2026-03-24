import argparse
import sys
from pathlib import Path

# Allow running as a standalone script: python3 src/dune_winder/plc_import.py
if __name__ == "__main__":
  sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dune_winder.plc_metadata_export import (
  _load_main_routine_overrides,
  fetch_plc_snapshot,
  write_plc_snapshot,
)
from dune_winder.plc_tag_values_export import fetch_and_write_tag_values


DEFAULT_PLC_PATH = "192.168.140.13"
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parents[2] / "plc"


def build_argument_parser():
  parser = argparse.ArgumentParser(
    description=(
      "Connect to a Studio 5000 PLC with pycomm3 and import metadata and/or "
      "tag values into the plc/ directory tree. "
      "By default both metadata and values are imported."
    )
  )
  parser.add_argument(
    "plc_path",
    nargs="?",
    default=DEFAULT_PLC_PATH,
    help=f"PLC connection path or IP address (default: {DEFAULT_PLC_PATH}).",
  )
  parser.add_argument(
    "--output-root",
    type=Path,
    default=DEFAULT_OUTPUT_ROOT,
    help="Directory to populate. Defaults to plc/ at the repo root.",
  )

  action_group = parser.add_mutually_exclusive_group()
  action_group.add_argument(
    "--metadata-only",
    action="store_true",
    help="Import only metadata (tag definitions, programs, routines).",
  )
  action_group.add_argument(
    "--values-only",
    action="store_true",
    help="Import only tag values into existing metadata JSON files.",
  )

  parser.add_argument(
    "--main-routine-map",
    type=Path,
    default=None,
    help=(
      "Optional JSON file mapping program names to main routine names. "
      "Only used when importing metadata."
    ),
  )
  parser.add_argument(
    "--dry-run",
    action="store_true",
    help=(
      "Fetch and summarise PLC metadata without writing files. "
      "Suppresses the values import step."
    ),
  )
  return parser


def main(argv=None):
  parser = build_argument_parser()
  args = parser.parse_args(argv)

  run_metadata = not args.values_only
  run_values = not args.metadata_only and not args.dry_run

  if run_metadata:
    overrides = _load_main_routine_overrides(args.main_routine_map)
    snapshot = fetch_plc_snapshot(args.plc_path, main_routine_overrides=overrides)

    if args.dry_run:
      print(
        f"would export {len(snapshot['controller_level_tags'])} controller-level tags "
        f"and {len(snapshot['programs'])} programs to {args.output_root}"
      )
      for program_name in sorted(snapshot["programs"]):
        program_definition = snapshot["programs"][program_name]
        print(
          f"{program_name}: main={program_definition['main_routine_name']} "
          f"subroutines={len(program_definition['subroutines'])} "
          f"program_tags={len(program_definition['program_tags'])}"
        )
    else:
      write_plc_snapshot(snapshot, args.output_root)
      print(
        f"exported {len(snapshot['controller_level_tags'])} controller-level tags "
        f"and {len(snapshot['programs'])} programs to {args.output_root}"
      )

  if run_values:
    result = fetch_and_write_tag_values(args.plc_path, output_root=args.output_root)
    print(
      f"exported values for {result['tag_count']} tags across "
      f"{result['file_count']} JSON files in {args.output_root}"
    )


if __name__ == "__main__":
  main()
