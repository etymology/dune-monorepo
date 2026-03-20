import argparse
from pathlib import Path

from dune_winder.plc_rung_transform import transform_file


DEFAULT_ROUTINE_DIR = Path(__file__).resolve().parents[1] / "plc_routines"


def build_argument_parser():
  parser = argparse.ArgumentParser(
    description=(
      "Convert every checked-in studio_copy.rllscrap file in a PLC program "
      "directory into a sibling pasteable.rll file using the standard PLC "
      "rung transformation."
    )
  )
  parser.add_argument(
    "routine_dir",
    nargs="?",
    default=DEFAULT_ROUTINE_DIR,
    type=Path,
    help=(
      "Directory containing PLC program folders with checked-in "
      "studio_copy.rllscrap files. "
      "Defaults to plc_routines/ at the repo root."
    ),
  )
  parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Show which files would be converted without writing output files.",
  )
  return parser


def iter_rllscrap_files(routine_dir: Path):
  yield from sorted(routine_dir.rglob("studio_copy.rllscrap"))


def convert_directory(routine_dir: Path, dry_run: bool = False) -> int:
  source_dir = routine_dir.resolve()
  if not source_dir.is_dir():
    raise FileNotFoundError(f"Routine directory does not exist: {source_dir}")

  converted = 0
  for input_path in iter_rllscrap_files(source_dir):
    output_path = input_path.with_name("pasteable.rll")
    relative_input_path = input_path.relative_to(source_dir)
    relative_output_path = output_path.relative_to(source_dir)
    if dry_run:
      print(f"would convert {relative_input_path} -> {relative_output_path}")
    else:
      transform_file(input_path, output_path)
      print(f"converted {relative_input_path} -> {relative_output_path}")
    converted += 1

  return converted


def main(argv=None):
  parser = build_argument_parser()
  args = parser.parse_args(argv)

  converted = convert_directory(args.routine_dir, dry_run=args.dry_run)
  if converted == 0:
    print("no .rllscrap files found")


if __name__ == "__main__":
  main()
