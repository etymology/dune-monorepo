from __future__ import annotations

from typing import Callable

from .model import Program, ProgramLine
from .parser import GCodeParseError, parse_line_text


CallbackLookup = Callable[[str], Callable | None]


class GCodeExecutionError(Exception):
  def __init__(self, message, data=None):
    Exception.__init__(self, message)
    if data is None:
      data = []
    self.data = data


class GCodeCallbacks:
  def __init__(self):
    self._callbacks = {"on_instruction": None}

  def get(self, code):
    return self._callbacks[code]

  def getCallback(self, code):
    return self.get(code)

  def register(self, code, callback):
    if code != "on_instruction":
      raise KeyError("Only 'on_instruction' callbacks are supported.")
    self._callbacks[code] = callback

  def registerCallback(self, code, callback):
    self.register(code, callback)


class GCodeProgramExecutor:
  def __init__(self, lines, callbacks: GCodeCallbacks):
    self.lines = list(map(str.strip, lines))
    self._callbacks = callbacks

  def fetch_lines(self, center, delta):
    bottom = center - delta
    top = center + delta + 1
    start = max(bottom, 0)
    end = min(top, len(self.lines))
    result = self.lines[start:end]

    if delta > center:
      result = [""] * (delta - center) + result

    if top > len(self.lines):
      spaces = top - len(self.lines)
      result = result + [""] * spaces

    return result

  def fetchLines(self, center, delta):
    return self.fetch_lines(center, delta)

  def line_count(self):
    return len(self.lines)

  def getLineCount(self):
    return self.line_count()

  def execute_line(self, line: str):
    try:
      execute_text_line(line, self._callbacks.get)
    except GCodeParseError as exception:
      raise GCodeExecutionError(str(exception), exception.data) from exception

  def execute(self, line):
    self.execute_line(line)

  def execute_next_line(self, line_number):
    if line_number < len(self.lines):
      self.execute_line(self.lines[line_number])

  def executeNextLine(self, lineNumber):
    self.execute_next_line(lineNumber)


def execute_program_line(line: ProgramLine, callback_lookup: CallbackLookup) -> None:
  callback = callback_lookup("on_instruction")
  if callback is not None:
    callback(line)


def execute_program(program: Program, callback_lookup: CallbackLookup) -> None:
  for line in program.lines:
    execute_program_line(line, callback_lookup)


def execute_text_line(line: str, callback_lookup: CallbackLookup) -> None:
  execute_program_line(parse_line_text(line), callback_lookup)
