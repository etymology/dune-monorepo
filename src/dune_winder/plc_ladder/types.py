from __future__ import annotations

import copy
from dataclasses import dataclass


@dataclass
class PLCStruct(dict):
  udt_name: str

  def __init__(self, udt_name: str, values=None):
    dict.__init__(self, values or {})
    self.udt_name = str(udt_name)

  def clone(self) -> "PLCStruct":
    return PLCStruct(self.udt_name, copy.deepcopy(dict(self)))


class Timer(PLCStruct):
  def __init__(self, values=None):
    super().__init__("TIMER", values)


class Control(PLCStruct):
  def __init__(self, values=None):
    super().__init__("CONTROL", values)


class MotionInstruction(PLCStruct):
  def __init__(self, values=None):
    super().__init__("MOTION_INSTRUCTION", values)


class CoordinateSystem(PLCStruct):
  def __init__(self, values=None):
    super().__init__("COORDINATE_SYSTEM", values)


class MotionSeg(PLCStruct):
  def __init__(self, values=None):
    super().__init__("MotionSeg", values)


KNOWN_STRUCT_TYPES = {
  "TIMER": Timer,
  "CONTROL": Control,
  "MOTION_INSTRUCTION": MotionInstruction,
  "COORDINATE_SYSTEM": CoordinateSystem,
  "MotionSeg": MotionSeg,
}


def default_atomic_value(data_type_name: str | None):
  if data_type_name is None:
    return 0

  normalized = str(data_type_name).upper()
  if normalized == "BOOL":
    return False
  if normalized in {"REAL", "LREAL"}:
    return 0.0
  if normalized in {"STRING"}:
    return ""
  return 0


def make_struct_instance(udt_name: str, values=None) -> PLCStruct:
  cls = KNOWN_STRUCT_TYPES.get(str(udt_name), PLCStruct)
  if cls is PLCStruct:
    return PLCStruct(str(udt_name), values)
  return cls(values)
