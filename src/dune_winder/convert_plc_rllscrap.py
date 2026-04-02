import argparse
import re
from pathlib import Path

from dune_winder.paths import PLC_ROOT
from dune_winder.plc_ladder.metadata import load_plc_metadata
from dune_winder.plc_manifest import _try_update_rllscrap_manifest
from dune_winder.plc_rung_transform import transform_text


DEFAULT_ROUTINE_DIR = PLC_ROOT


def build_argument_parser():
  parser = argparse.ArgumentParser(
    description=(
      "Convert every checked-in studio_copy.rllscrap file in a PLC program "
      "directory into a sibling pasteable.rll file using the standard PLC "
      "rung transformation, including formula-aware handling for CPT and CMP."
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
      "Defaults to plc/ at the repo root."
    ),
  )
  parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Show which files would be converted without writing output files.",
  )
  return parser


TIMER_COUNTER_PATTERN = re.compile(
  r"(TON|CTU) (\S+) \? \?"
)


def _resolve_tag_arguments(match, plc_metadata, program):
  instruction = match.group(1)
  tag_name = match.group(2)
  tag = plc_metadata.get_tag_definition(tag_name, program=program)
  if tag is None or not isinstance(tag.value, dict):
    return match.group(0)
  pre = tag.value.get("PRE")
  acc = tag.value.get("ACC")
  if pre is None or acc is None:
    return match.group(0)
  return f"{instruction} {tag_name} {pre} {acc}"


def resolve_timer_counter_args(text, plc_metadata, program):
  return TIMER_COUNTER_PATTERN.sub(
    lambda m: _resolve_tag_arguments(m, plc_metadata, program),
    text,
  )


def iter_rllscrap_files(routine_dir: Path):
  yield from sorted(routine_dir.rglob("studio_copy.rllscrap"))


def convert_directory(routine_dir: Path, dry_run: bool = False) -> int:
  source_dir = routine_dir.resolve()
  if not source_dir.is_dir():
    raise FileNotFoundError(f"Routine directory does not exist: {source_dir}")

  plc_metadata = load_plc_metadata(source_dir)

  converted = 0
  for input_path in iter_rllscrap_files(source_dir):
    output_path = input_path.with_name("pasteable.rll")
    relative_input_path = input_path.relative_to(source_dir)
    relative_output_path = output_path.relative_to(source_dir)
    if dry_run:
      print(f"would convert {relative_input_path} -> {relative_output_path}")
    else:
      program = input_path.parent.parent.name
      transformed = transform_text(input_path.read_text())
      resolved = resolve_timer_counter_args(transformed, plc_metadata, program)
      output_path.write_text(resolved)
      _try_update_rllscrap_manifest(input_path)
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
