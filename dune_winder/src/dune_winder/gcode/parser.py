from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .model import CommandWord, Comment, FunctionCall, Program, ProgramLine, SUPPORTED_COMMAND_LETTERS


@dataclass
class GCodeParseError(ValueError):
  data: list[str]

  def __init__(self, message: str, data: list[str] | None = None):
    super().__init__(message)
    self.data = [] if data is None else data


def _tokenize_line(line: str) -> list[tuple[str, str]]:
  tokens: list[tuple[str, str]] = []
  current: list[str] = []
  index = 0
  while index < len(line):
    character = line[index]

    if "(" == character:
      if current:
        tokens.append(("token", "".join(current)))
        current = []

      closing = line.find(")", index + 1)
      if -1 == closing:
        comment = line[index + 1 :]
        index = len(line)
      else:
        comment = line[index + 1 : closing]
        index = closing + 1

      tokens.append(("comment", comment))
      continue

    if character.isspace():
      if current:
        tokens.append(("token", "".join(current)))
        current = []
      index += 1
      continue

    current.append(character)
    index += 1

  if current:
    tokens.append(("token", "".join(current)))

  return tokens


def _validate_numeric_parameter(
  code: str,
  parameter: str,
  command_string: str,
) -> None:
  if code in ("F", "X", "Y", "Z"):
    try:
      float(parameter)
    except ValueError as exception:
      data = [command_string, code, parameter]
      raise GCodeParseError("Invalid parameter data " + parameter, data) from exception

  elif code in ("M", "N"):
    try:
      int(parameter)
    except ValueError as exception:
      data = [command_string, code, parameter]
      raise GCodeParseError("Invalid parameter data " + parameter, data) from exception


def parse_line_text(line: str) -> ProgramLine:
  program_line = ProgramLine()
  last_item: CommandWord | FunctionCall | None = None

  for token_type, token_value in _tokenize_line(str(line)):
    if "comment" == token_type:
      program_line.append(Comment(token_value))
      continue

    command_string = token_value
    code = command_string[:1]
    parameter = command_string[1:]

    if "P" == code:
      if last_item is None:
        data = [command_string, code, parameter]
        raise GCodeParseError("Unassigned parameter " + parameter, data)

      if isinstance(last_item, CommandWord):
        _validate_numeric_parameter(last_item.letter, parameter, command_string)

      last_item.parameters.append(parameter)
      continue

    if code not in SUPPORTED_COMMAND_LETTERS:
      data = [command_string, code]
      raise GCodeParseError("Unknown parameter " + code, data)

    if "G" == code:
      item: CommandWord | FunctionCall = FunctionCall(parameter, [])
    else:
      _validate_numeric_parameter(code, parameter, command_string)
      item = CommandWord(code, parameter, [])

    program_line.append(item)
    last_item = item

  return program_line


def parse_program_lines(lines: Iterable[str]) -> Program:
  program = Program()
  for line in lines:
    program.append(parse_line_text(line))
  return program
