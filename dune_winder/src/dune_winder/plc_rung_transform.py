import argparse
import re
from pathlib import Path

from dune_winder.plc_manifest import _try_update_rllscrap_manifest


COMMAND_ARGUMENTS_PATTERN = re.compile(r"([A-Za-z_][A-Za-z0-9_.]*)\(([^()\n]*)\)")
INLINE_SEPARATOR_PATTERN = re.compile(r"[(),]")
WHITESPACE_PATTERN = re.compile(r"[ \t]+")
NUMERIC_TERM_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")
PROTECTED_LPAREN = "\uFFF0"
PROTECTED_RPAREN = "\uFFF1"
PROTECTED_COMMA = "\uFFF2"
SPECIAL_FORMULA_COMMANDS = {"CMP", "CPT"}


def _split_top_level_commas(text):
  parts = []
  current = []
  paren_depth = 0
  bracket_depth = 0

  for character in text:
    if character == "," and paren_depth == 0 and bracket_depth == 0:
      parts.append("".join(current))
      current = []
      continue

    if character == "(":
      paren_depth += 1
    elif character == ")" and paren_depth > 0:
      paren_depth -= 1
    elif character == "[":
      bracket_depth += 1
    elif character == "]" and bracket_depth > 0:
      bracket_depth -= 1

    current.append(character)

  parts.append("".join(current))
  return parts


def _protect_formula_expression(text):
  return (
    text.replace("(", PROTECTED_LPAREN)
    .replace(")", PROTECTED_RPAREN)
    .replace(",", PROTECTED_COMMA)
  )


def _restore_protected_formula_expression(text):
  return (
    text.replace(PROTECTED_LPAREN, "(")
    .replace(PROTECTED_RPAREN, ")")
    .replace(PROTECTED_COMMA, ",")
  )


def _extract_balanced_call(text, start_index):
  open_index = text.find("(", start_index)
  if open_index == -1:
    return None

  depth = 1
  index = open_index + 1
  while index < len(text) and depth > 0:
    if text[index] == "(":
      depth += 1
    elif text[index] == ")":
      depth -= 1
    index += 1

  if depth != 0:
    return None

  return open_index, index, text[open_index + 1:index - 1]


def _extract_special_formula_call(text):
  call = _extract_balanced_call(text, 0)
  if call is None or call[0] != 3:
    return None

  command = text[:call[0]]
  if command not in SPECIAL_FORMULA_COMMANDS:
    return None

  return command, call[2]


def _rewrite_special_formula_call(command, arguments_text):
  if command == "CMP":
    protected_formula = _protect_formula_expression(arguments_text.strip())
    return command + "(" + protected_formula + ")"

  arguments = _split_top_level_commas(arguments_text)
  if len(arguments) < 2:
    return command + "(" + arguments_text + ")"

  first_argument = WHITESPACE_PATTERN.sub(" ", arguments[0]).strip()
  second_argument = arguments[1].strip()
  if len(arguments) > 2:
    second_argument = second_argument + "," + ",".join(arguments[2:])
  protected_expression = _protect_formula_expression(second_argument)
  return command + "(" + first_argument + "," + protected_expression + ")"


def _protect_special_command_arguments(text):
  transformed = []
  index = 0

  while index < len(text):
    command = next(
      (candidate for candidate in SPECIAL_FORMULA_COMMANDS if text.startswith(candidate + "(", index)),
      None,
    )
    if command is None:
      transformed.append(text[index])
      index += 1
      continue

    call = _extract_balanced_call(text, index)
    if call is None:
      transformed.append(text[index])
      index += 1
      continue

    open_index, end_index, arguments_text = call
    command = text[index:open_index]
    transformed.append(_rewrite_special_formula_call(command, arguments_text))
    index = end_index

  return "".join(transformed)


def _normalize_condition_term(term):
  stripped_term = term.strip()
  special_call = _extract_special_formula_call(stripped_term)
  if special_call is not None:
    command, arguments_text = special_call
    if command == "CMP":
      return "CMP " + _protect_formula_expression(arguments_text.strip())

    arguments = _split_top_level_commas(arguments_text)
    if len(arguments) >= 2:
      first_argument = WHITESPACE_PATTERN.sub(" ", arguments[0]).strip()
      second_argument = arguments[1].strip()
      if len(arguments) > 2:
        second_argument = second_argument + "," + ",".join(arguments[2:])
      return "CPT " + first_argument + " " + _protect_formula_expression(second_argument)

  command_match = COMMAND_ARGUMENTS_PATTERN.fullmatch(stripped_term)
  if command_match is None:
    return stripped_term

  command = command_match.group(1)
  arguments = [
    WHITESPACE_PATTERN.sub(" ", argument).strip()
    for argument in _split_top_level_commas(command_match.group(2))
    if argument.strip()
  ]
  if not arguments:
    return stripped_term

  return command + " " + " ".join(arguments)


def _replace_bracketed_conditions(content):
  conditions = [_normalize_condition_term(part) for part in _split_top_level_commas(content) if part.strip()]
  if not conditions:
    return "[" + content + "]"

  if all(NUMERIC_TERM_PATTERN.fullmatch(condition) for condition in conditions):
    return "[" + content + "]"

  return "BST " + "  NXB ".join(conditions) + "  BND "


def _quote_spaced_command_arguments(match):
  command = match.group(1)
  if command in SPECIAL_FORMULA_COMMANDS:
    return match.group(0)

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
  transformed = []
  index = 0

  while index < len(text):
    character = text[index]
    if character != "[":
      transformed.append(character)
      index += 1
      continue

    bracket_depth = 1
    end_index = index + 1
    while end_index < len(text) and bracket_depth > 0:
      if text[end_index] == "[":
        bracket_depth += 1
      elif text[end_index] == "]":
        bracket_depth -= 1
      end_index += 1

    if bracket_depth != 0:
      transformed.append(character)
      index += 1
      continue

    inner_text = text[index + 1:end_index - 1]
    transformed_inner = _transform_bracketed_conditions(inner_text)
    transformed.append(_replace_bracketed_conditions(transformed_inner))
    index = end_index

  return "".join(transformed)


def _quote_command_arguments(text):
  return COMMAND_ARGUMENTS_PATTERN.sub(_quote_spaced_command_arguments, text)


def _flatten_delimiters(text):
  transformed = INLINE_SEPARATOR_PATTERN.sub(" ", text)
  return transformed.replace(";", "\n")


def transform_text(text):
  transformed = _transform_bracketed_conditions(text)
  transformed = _protect_special_command_arguments(transformed)
  transformed = _quote_command_arguments(transformed)
  transformed = _flatten_delimiters(transformed)
  trailing_newline = transformed.endswith("\n")
  lines = transformed.split("\n")
  if trailing_newline:
    lines = lines[:-1]

  normalized_lines = [WHITESPACE_PATTERN.sub(" ", line).lstrip() for line in lines]
  normalized_text = "\n".join(normalized_lines)

  if trailing_newline:
    return _restore_protected_formula_expression(normalized_text + "\n")

  return _restore_protected_formula_expression(normalized_text)


def transform_file(input_path, output_path=None):
  source_path = Path(input_path)
  transformed = transform_text(source_path.read_text())

  if output_path is None:
    return transformed

  Path(output_path).write_text(transformed)
  _try_update_rllscrap_manifest(source_path)
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
