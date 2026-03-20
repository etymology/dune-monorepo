import argparse
import re
from pathlib import Path


BRACKETED_CONDITIONS_PATTERN = re.compile(r"\[([^\[\]]+)\]")
COMMAND_ARGUMENTS_PATTERN = re.compile(r"([A-Za-z_][A-Za-z0-9_.]*)\(([^()\n]*)\)")
INLINE_SEPARATOR_PATTERN = re.compile(r"[(),]")
WHITESPACE_PATTERN = re.compile(r"[ \t]+")
NUMERIC_TERM_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")


def _split_top_level_commas(text):
  parts = []
  current = []
  depth = 0

  for character in text:
    if character == "," and depth == 0:
      parts.append("".join(current))
      current = []
      continue

    if character == "(":
      depth += 1
    elif character == ")" and depth > 0:
      depth -= 1

    current.append(character)

  parts.append("".join(current))
  return parts


def _normalize_condition_term(term):
  stripped_term = term.strip()
  command_match = COMMAND_ARGUMENTS_PATTERN.fullmatch(stripped_term)
  if command_match is None:
    return stripped_term

  command = command_match.group(1)
  argument = WHITESPACE_PATTERN.sub(" ", command_match.group(2)).strip()
  if not argument:
    return stripped_term

  return command + " " + argument


def _replace_bracketed_conditions(match):
  conditions = [
    _normalize_condition_term(part)
    for part in _split_top_level_commas(match.group(1))
    if part.strip()
  ]
  if not conditions:
    return match.group(0)

  if all(NUMERIC_TERM_PATTERN.fullmatch(condition) for condition in conditions):
    return match.group(0)

  return "BST " + "  NXB ".join(conditions) + "  BND "


def _quote_spaced_command_arguments(match):
  command = match.group(1)
  arguments = _split_top_level_commas(match.group(2))
  normalized_arguments = []

  for argument in arguments:
    normalized_argument = WHITESPACE_PATTERN.sub(" ", argument).strip()
    if (
      " " in normalized_argument
      and not normalized_argument.startswith('"')
      and not normalized_argument.endswith('"')
    ):
      normalized_argument = '"' + normalized_argument + '"'
    normalized_arguments.append(normalized_argument)

  return command + "(" + ",".join(normalized_arguments) + ")"


def _transform_bracketed_conditions(text):
  return BRACKETED_CONDITIONS_PATTERN.sub(_replace_bracketed_conditions, text)


def _quote_command_arguments(text):
  return COMMAND_ARGUMENTS_PATTERN.sub(_quote_spaced_command_arguments, text)


def _flatten_delimiters(text):
  transformed = INLINE_SEPARATOR_PATTERN.sub(" ", text)
  return transformed.replace(";", "\n")


def transform_text(text):
  transformed = _transform_bracketed_conditions(text)
  transformed = _quote_command_arguments(transformed)
  transformed = _flatten_delimiters(transformed)
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
