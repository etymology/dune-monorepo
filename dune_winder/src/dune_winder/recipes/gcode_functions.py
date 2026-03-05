"""Canonical recipe helpers that construct gcode FunctionCall objects."""

from dune_winder.gcode.model import FunctionCall, Opcode

HEAD_LOCATION_FRONT = 0
HEAD_LOCATION_PARTIAL_FRONT = 1
HEAD_LOCATION_PARTIAL_BACK = 2
HEAD_LOCATION_BACK = 3


def _function(opcode: Opcode, parameters=None):
  if parameters is None:
    parameters = []
  return FunctionCall(int(opcode), list(parameters))


def latch():
  return _function(Opcode.LATCH)


def wire_length(length):
  return _function(Opcode.WIRE_LENGTH, [length])


def seek_transfer():
  return _function(Opcode.SEEK_TRANSFER)


def pin_center(pins, axises="XY"):
  parameters = list(pins)
  parameters.append(axises)
  return _function(Opcode.PIN_CENTER, parameters)


def clip():
  return _function(Opcode.CLIP)


def offset(x=None, y=None, z=None):
  parameters = []
  if x is not None:
    parameters.append("X" + str(x))
  if y is not None:
    parameters.append("Y" + str(y))
  if z is not None:
    parameters.append("Z" + str(z))
  return _function(Opcode.OFFSET, parameters)


def head_location(location):
  return _function(Opcode.HEAD_LOCATION, [location])


def delay(milliseconds):
  return _function(Opcode.DELAY, [milliseconds])


def arm_correct():
  return _function(Opcode.ARM_CORRECT)


def anchor_point(pin, orientation=None):
  if orientation is None:
    orientation = "0"
  return _function(Opcode.ANCHOR_POINT, [pin, orientation])


def transfer_correct(axis):
  return _function(Opcode.TRANSFER_CORRECT, [axis])


def break_point():
  return _function(Opcode.BREAK_POINT)


def tension_testing(wire_index):
  return _function(Opcode.TENSION_TESTING, [wire_index])
