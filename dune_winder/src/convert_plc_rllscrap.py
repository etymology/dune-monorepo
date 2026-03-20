import argparse
from pathlib import Path

from dune_winder.plc_rung_transform import transform_file


def build_argument_parser():
  parser = argparse.ArgumentParser(
    description=(
      "Convert every .rllscrap file in a PLC routines directory into a "
      "same-name .rll file using the standard PLC rung transformation."
    )
  )
  parser.add_argument(
    "routine_dir",
    nargs="?",
    default=Path(__file__).resolve().parent / "plc_routines",
    type=Path,
    help="Directory containing .rllscrap files. Defaults to src/plc_routines.",
  )
  parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Show which files would be converted without writing output files.",
  )
  return parser


def iter_rllscrap_files(routine_dir: Path):
  yield from sorted(routine_dir.glob("*.rllscrap"))


def convert_directory(routine_dir: Path, dry_run: bool = False) -> int:
  source_dir = routine_dir.resolve()
  if not source_dir.is_dir():
    raise FileNotFoundError(f"Routine directory does not exist: {source_dir}")

  converted = 0
  for input_path in iter_rllscrap_files(source_dir):
    output_path = input_path.with_suffix(".rll")
    if dry_run:
      print(f"would convert {input_path.name} -> {output_path.name}")
    else:
      transform_file(input_path, output_path)
      print(f"converted {input_path.name} -> {output_path.name}")
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
