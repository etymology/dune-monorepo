import argparse
import re
from pathlib import Path


BRACKETED_CONDITIONS_PATTERN = re.compile(r"\[([^\[\]]+)\]")
INLINE_SEPARATOR_PATTERN = re.compile(r"[(),]")
WHITESPACE_PATTERN = re.compile(r"[ \t]+")


def _replace_bracketed_conditions(match):
  conditions = [part.strip() for part in match.group(1).split(",") if part.strip()]
  if not conditions:
    return ""

  return "BST " + "  NXB ".join(conditions) + "  BND"


def transform_text(text):
  transformed = BRACKETED_CONDITIONS_PATTERN.sub(_replace_bracketed_conditions, text)
  transformed = INLINE_SEPARATOR_PATTERN.sub(" ", transformed)
  transformed = transformed.replace(";", "\n")
  trailing_newline = transformed.endswith("\n")
  lines = transformed.split("\n")
  if trailing_newline:
    lines = lines[:-1]

  normalized_lines = [WHITESPACE_PATTERN.sub(" ", line).lstrip() for line in lines]
  normalized_text = "\n".join(normalized_lines)

  if trailing_newline:
    return normalized_text + "\n"

  return normalized_text


def transform_file(input_path, output_path=None):
  source_path = Path(input_path)
  transformed = transform_text(source_path.read_text())

  if output_path is None:
    return transformed

  Path(output_path).write_text(transformed)
  return transformed


def build_argument_parser():
  parser = argparse.ArgumentParser(
    description=(
      "Transform bracketed PLC condition lists into BST/NXB/BND form, "
      "replace parentheses and commas with spaces, and replace semicolons "
      "with newlines."
    )
  )
  parser.add_argument("input_file", help="Path to the source .txt file.")
  parser.add_argument(
    "-o",
    "--output",
    help="Write transformed output to this file. Defaults to stdout.",
  )
  parser.add_argument(
    "--in-place",
    action="store_true",
    help="Overwrite the input file with the transformed content.",
  )
  return parser


def main(argv=None):
  parser = build_argument_parser()
  args = parser.parse_args(argv)

  if args.output and args.in_place:
    parser.error("Use either --output or --in-place, not both.")

  if args.in_place:
    output_path = args.input_file
  else:
    output_path = args.output

  transformed = transform_file(args.input_file, output_path)

  if output_path is None:
    print(transformed, end="")


if __name__ == "__main__":
  main()
