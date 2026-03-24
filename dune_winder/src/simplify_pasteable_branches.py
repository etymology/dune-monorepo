from __future__ import annotations

import argparse
from pathlib import Path

from dune_winder.plc_ladder.branch_simplifier import iter_pasteable_files
from dune_winder.plc_ladder.branch_simplifier import simplify_file


DEFAULT_ROUTINE_DIR = Path(__file__).resolve().parents[1] / "plc"


def build_argument_parser():
  parser = argparse.ArgumentParser(
    description=(
      "Expand condition-only BST/NXB/BND branches in pasteable.rll files into "
      "plain ladder rungs. When a shared suffix should not be duplicated, "
      "the simplifier emits generated helper BOOL tags and rewrites the rung "
      "through OTU/OTL/XIC helper logic. Branches that still need JMP/LBL "
      "lowering are reported and left unchanged."
    )
  )
  parser.add_argument(
    "target",
    nargs="?",
    default=DEFAULT_ROUTINE_DIR,
    type=Path,
    help=(
      "A pasteable.rll file or a directory to scan recursively. "
      "Defaults to plc/ at the repo root."
    ),
  )
  parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Report changes and flagged rungs without rewriting files.",
  )
  return parser


def _iter_targets(target: Path):
  if target.is_file():
    yield target
    return
  yield from iter_pasteable_files(target)


def main(argv=None):
  parser = build_argument_parser()
  args = parser.parse_args(argv)

  target = args.target.resolve()
  if not target.exists():
    raise FileNotFoundError(f"Target does not exist: {target}")
  if target.is_file() and target.name != "pasteable.rll":
    raise ValueError(f"Expected a pasteable.rll file, got: {target}")

  changed_files = 0
  flagged_rungs = 0
  helper_tags = 0
  processed_files = 0

  for path in _iter_targets(target):
    report = simplify_file(path, write_changes=not args.dry_run)
    processed_files += 1

    if report.changed:
      action = "would update" if args.dry_run else "updated"
      print(
        f"{action} {path}: "
        f"{report.original_rung_count} -> {report.emitted_rung_count} rungs"
      )
      changed_files += 1

    if report.helper_tags:
      print(f"helper BOOL tags needed for {path}: {', '.join(report.helper_tags)}")
      helper_tags += len(report.helper_tags)

    for issue in report.issues:
      print(f"flagged {path}:{issue.rung_number}: {issue.reason}")
      print(f"  {issue.source_rung}")
      flagged_rungs += 1

  if processed_files == 0:
    print("no pasteable.rll files found")
    return

  print(
    f"processed {processed_files} file(s), "
    f"{changed_files} changed, "
    f"{helper_tags} helper tag(s), "
    f"{flagged_rungs} rung(s) flagged"
  )


if __name__ == "__main__":
  main()
