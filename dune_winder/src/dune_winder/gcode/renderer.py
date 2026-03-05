from __future__ import annotations

from .model import CommandWord, Comment, FunctionCall, Program, ProgramLine


def _render_comment(comment: Comment) -> str:
  return "(" + str(comment.text) + ")"


def _render_command_word(command: CommandWord) -> str:
  result = command.letter + str(command.value)
  for parameter in command.parameters:
    result += " P" + str(parameter)
  return result


def render_function_call(function: FunctionCall) -> str:
  result = "G" + str(function.opcode)
  for parameter in function.parameters:
    result += " P" + str(parameter)
  return result


def render_line(line: ProgramLine) -> str:
  rendered: list[str] = []
  for item in line.items:
    if isinstance(item, Comment):
      rendered.append(_render_comment(item))
    elif isinstance(item, FunctionCall):
      rendered.append(render_function_call(item))
    elif isinstance(item, CommandWord):
      rendered.append(_render_command_word(item))
  return " ".join(rendered)


def render_program(program: Program, with_trailing_newline: bool = False) -> list[str]:
  lines = [render_line(line) for line in program.lines]
  if with_trailing_newline:
    return [line + "\n" for line in lines]
  return lines


def normalize_line_text(text: str) -> str:
  from .parser import parse_line_text

  return render_line(parse_line_text(text))
