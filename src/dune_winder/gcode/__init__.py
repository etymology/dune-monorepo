"""Canonical G-code domain model and helpers."""

from .handler import GCodeHandler
from .handler_base import GCodeHandlerBase
from .model import (
  OPCODE_CATALOG,
  OPCODE_NAME_CATALOG,
  CommandWord,
  Comment,
  FunctionCall,
  Opcode,
  OpcodeSpec,
  Program,
  ProgramLine,
  SUPPORTED_COMMAND_LETTERS,
)
from .parser import GCodeParseError, parse_line_text, parse_program_lines
from .renderer import (
  normalize_line_text,
  render_function_call,
  render_line,
  render_program,
)
from .runtime import execute_program, execute_program_line, execute_text_line
from .runtime import GCodeCallbacks, GCodeExecutionError, GCodeProgramExecutor

__all__ = [
  "CommandWord",
  "Comment",
  "FunctionCall",
  "GCodeCallbacks",
  "GCodeHandler",
  "GCodeHandlerBase",
  "GCodeExecutionError",
  "GCodeProgramExecutor",
  "GCodeParseError",
  "OPCODE_CATALOG",
  "OPCODE_NAME_CATALOG",
  "Opcode",
  "OpcodeSpec",
  "Program",
  "ProgramLine",
  "SUPPORTED_COMMAND_LETTERS",
  "execute_program",
  "execute_program_line",
  "execute_text_line",
  "normalize_line_text",
  "parse_line_text",
  "parse_program_lines",
  "render_function_call",
  "render_line",
  "render_program",
]
