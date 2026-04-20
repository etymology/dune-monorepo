from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class Opcode(IntEnum):
  LATCH = 100
  WIRE_LENGTH = 101
  SEEK_TRANSFER = 102
  PIN_CENTER = 103
  CLIP = 104
  OFFSET = 105
  HEAD_LOCATION = 106
  DELAY = 107
  ARM_CORRECT = 108
  ANCHOR_POINT = 109
  TRANSFER_CORRECT = 110
  BREAK_POINT = 111
  TENSION_TESTING = 112
  QUEUE_MERGE = 113
  WRAP_GOTO = 114
  WRAP_INCREMENT = 115
  WRAP_ANCHOR = 116
  WRAP_B = 117
  WRAP_B_TO_A = 118
  HEAD_TRANSFER = 206


@dataclass(frozen=True)
class OpcodeSpec:
  opcode: Opcode
  name: str
  parameter_shape: str
  description: str


@dataclass
class Comment:
  text: str


@dataclass
class CommandWord:
  letter: str
  value: Any
  parameters: list[Any] = field(default_factory=list)

  def values(self) -> list[Any]:
    return [self.value] + list(self.parameters)


@dataclass
class FunctionCall:
  opcode: Any
  parameters: list[Any] = field(default_factory=list)

  def as_legacy_parameter_list(self) -> list[Any]:
    return [self.opcode] + list(self.parameters)

  def opcode_as_int(self) -> int:
    return int(self.opcode)


@dataclass
class MacroCall:
  text: str


LineItem = CommandWord | FunctionCall | Comment | MacroCall


@dataclass
class ProgramLine:
  items: list[LineItem] = field(default_factory=list)

  def append(self, item: LineItem) -> None:
    self.items.append(item)


@dataclass
class Program:
  lines: list[ProgramLine] = field(default_factory=list)

  def append(self, line: ProgramLine) -> None:
    self.lines.append(line)


_OPCODE_SPECS = (
  OpcodeSpec(Opcode.LATCH, "LATCH", "none", "No parameters."),
  OpcodeSpec(Opcode.WIRE_LENGTH, "WIRE_LENGTH", "length", "Wire length in mm."),
  OpcodeSpec(Opcode.SEEK_TRANSFER, "SEEK_TRANSFER", "none", "Seek transfer edge."),
  OpcodeSpec(Opcode.PIN_CENTER, "PIN_CENTER", "pin_a,pin_b,axes", "Center between pins."),
  OpcodeSpec(Opcode.CLIP, "CLIP", "none", "Clip XY to transfer area."),
  OpcodeSpec(Opcode.OFFSET, "OFFSET", "axis+delta...", "Relative coordinate offsets."),
  OpcodeSpec(Opcode.HEAD_LOCATION, "HEAD_LOCATION", "location", "Head side/position."),
  OpcodeSpec(Opcode.DELAY, "DELAY", "milliseconds", "Delay before continuing."),
  OpcodeSpec(Opcode.ARM_CORRECT, "ARM_CORRECT", "none", "Apply arm compensation."),
  OpcodeSpec(Opcode.ANCHOR_POINT, "ANCHOR_POINT", "pin,orientation", "Set wire anchor."),
  OpcodeSpec(
    Opcode.TRANSFER_CORRECT,
    "TRANSFER_CORRECT",
    "axis",
    "Apply transfer-area correction.",
  ),
  OpcodeSpec(Opcode.BREAK_POINT, "BREAK_POINT", "none", "Stop execution after line."),
  OpcodeSpec(
    Opcode.TENSION_TESTING,
    "TENSION_TESTING",
    "wire_index",
    "Enable tension testing mode.",
  ),
  OpcodeSpec(
    Opcode.QUEUE_MERGE,
    "QUEUE_MERGE",
    "mode",
    "Mark the current XY waypoint as mergeable for queued motion.",
  ),
  OpcodeSpec(
    Opcode.WRAP_GOTO,
    "WRAP_GOTO",
    "axis+target...",
    "Absolute XY move for wrap-mode recipes.",
  ),
  OpcodeSpec(
    Opcode.WRAP_INCREMENT,
    "WRAP_INCREMENT",
    "axis+delta...",
    "Relative XY move for wrap-mode recipes.",
  ),
  OpcodeSpec(
    Opcode.WRAP_ANCHOR,
    "WRAP_ANCHOR",
    "pin",
    "Set the wrap anchor pin without moving.",
  ),
  OpcodeSpec(
    Opcode.WRAP_B,
    "WRAP_B",
    "pin",
    "Wrap a B-side pin using the current wrap anchor.",
  ),
  OpcodeSpec(
    Opcode.WRAP_B_TO_A,
    "WRAP_B_TO_A",
    "pin",
    "Translate a B-side pin to A and wrap it using the current wrap anchor.",
  ),
  OpcodeSpec(
    Opcode.HEAD_TRANSFER,
    "HEAD_TRANSFER",
    "location",
    "Head transfer command.",
  ),
)


OPCODE_CATALOG = {int(spec.opcode): spec for spec in _OPCODE_SPECS}
OPCODE_NAME_CATALOG = {spec.name: spec for spec in _OPCODE_SPECS}
SUPPORTED_COMMAND_LETTERS = frozenset(("F", "G", "M", "N", "O", "P", "X", "Y", "Z"))
