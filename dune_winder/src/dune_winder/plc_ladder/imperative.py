from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from .ast import InstructionCall
from .ast import Routine
from .runtime import ExpressionEvaluator
from .runtime import InstructionRuntime
from .runtime import ScanContext
from .runtime import _deep_copy


def _operand_token(value) -> str:
  if value is None:
    return "?"
  if isinstance(value, bool):
    return "true" if value else "false"
  return str(value)


def _python_name(name: str, program: str | None = None) -> str:
  parts = []
  if program:
    parts.append(program)
  parts.append(name)
  text = "_".join(parts)
  return "".join(character if character.isalnum() else "_" for character in text)


@dataclass
class BoundRoutineAPI:
  ctx: ScanContext
  runtime: InstructionRuntime

  def tag(self, path: str):
    return _deep_copy(self.ctx.get_value(str(path)))

  def set_tag(self, path: str, value):
    self.ctx.set_value(str(path), _deep_copy(value))
    return value

  def formula(self, expression: str):
    return self.runtime.expression_evaluator.evaluate(str(expression), self.ctx)

  def _execute(self, opcode: str, *operands, rung_in: bool = True):
    instruction = InstructionCall(
      opcode=str(opcode),
      operands=tuple(_operand_token(operand) for operand in operands),
    )
    return self.runtime.execute_instruction(instruction, bool(rung_in), self.ctx)

  def ADD(self, *, source_a, source_b, dest):
    return self.set_tag(dest, source_a + source_b)

  def COP(self, *, source, dest, length):
    return self._execute("COP", source, dest, length)

  def CPT(self, *, dest, value):
    return self.set_tag(dest, value)

  def FFL(self, *, source, array, control, length=None, position=None):
    return self._execute("FFL", source, array, control, length, position)

  def FFU(self, *, array, dest, control, length=None, position=None):
    return self._execute("FFU", array, dest, control, length, position)

  def FLL(self, *, value, dest, length):
    return self._execute("FLL", value, dest, length)

  def JSR(self, *, routine, parameter_block=None):
    return self._execute("JSR", routine, 0 if parameter_block is None else parameter_block)

  def MAFR(self, *, axis, motion_control):
    return self._execute("MAFR", axis, motion_control)

  def MAM(
    self,
    *,
    axis,
    motion_control,
    move_type,
    target,
    speed,
    speed_units,
    accel,
    accel_units,
    decel,
    decel_units,
    profile,
    accel_jerk,
    decel_jerk,
    jerk_units,
    merge,
    merge_speed,
    lock_position,
    lock_direction,
    event_distance,
    calculated_data,
  ):
    return self._execute(
      "MAM",
      axis,
      motion_control,
      move_type,
      target,
      speed,
      speed_units,
      accel,
      accel_units,
      decel,
      decel_units,
      profile,
      accel_jerk,
      decel_jerk,
      jerk_units,
      merge,
      merge_speed,
      lock_position,
      lock_direction,
      event_distance,
      calculated_data,
    )

  def MAS(
    self,
    *,
    axis,
    motion_control,
    stop_type,
    change_decel,
    decel,
    decel_units,
    change_jerk,
    jerk,
    jerk_units,
  ):
    return self._execute(
      "MAS",
      axis,
      motion_control,
      stop_type,
      change_decel,
      decel,
      decel_units,
      change_jerk,
      jerk,
      jerk_units,
    )

  def MCCM(
    self,
    *,
    coordinate_system,
    motion_control,
    move_type,
    end_position,
    circle_type,
    via_or_center,
    direction,
    speed,
    speed_units,
    accel,
    accel_units,
    decel,
    decel_units,
    profile,
    accel_jerk,
    decel_jerk,
    jerk_units,
    termination_type,
    merge,
    merge_speed,
    command_tolerance,
    lock_position,
    lock_direction,
    event_distance,
    calculated_data,
  ):
    return self._execute(
      "MCCM",
      coordinate_system,
      motion_control,
      move_type,
      end_position,
      circle_type,
      via_or_center,
      direction,
      speed,
      speed_units,
      accel,
      accel_units,
      decel,
      decel_units,
      profile,
      accel_jerk,
      decel_jerk,
      jerk_units,
      termination_type,
      merge,
      merge_speed,
      command_tolerance,
      lock_position,
      lock_direction,
      event_distance,
      calculated_data,
    )

  def MCCD(
    self,
    *,
    coordinate_system,
    motion_control,
    scope,
    speed_enable,
    speed,
    speed_units,
    accel_enable,
    accel,
    accel_units,
    decel_enable,
    decel,
    decel_units,
    accel_jerk_enable,
    accel_jerk,
    decel_jerk_enable,
    decel_jerk,
    jerk_units,
    apply_to,
  ):
    return self._execute(
      "MCCD",
      coordinate_system,
      motion_control,
      scope,
      speed_enable,
      speed,
      speed_units,
      accel_enable,
      accel,
      accel_units,
      decel_enable,
      decel,
      decel_units,
      accel_jerk_enable,
      accel_jerk,
      decel_jerk_enable,
      decel_jerk,
      jerk_units,
      apply_to,
    )

  def MCLM(
    self,
    *,
    coordinate_system,
    motion_control,
    move_type,
    target,
    speed,
    speed_units,
    accel,
    accel_units,
    decel,
    decel_units,
    profile,
    accel_jerk,
    decel_jerk,
    jerk_units,
    termination_type,
    merge,
    merge_speed,
    command_tolerance,
    lock_position,
    lock_direction,
    event_distance,
    calculated_data,
  ):
    return self._execute(
      "MCLM",
      coordinate_system,
      motion_control,
      move_type,
      target,
      speed,
      speed_units,
      accel,
      accel_units,
      decel,
      decel_units,
      profile,
      accel_jerk,
      decel_jerk,
      jerk_units,
      termination_type,
      merge,
      merge_speed,
      command_tolerance,
      lock_position,
      lock_direction,
      event_distance,
      calculated_data,
    )

  def MCS(
    self,
    *,
    coordinate_system,
    motion_control,
    stop_type,
    change_decel,
    decel,
    decel_units,
    change_jerk,
    jerk,
    jerk_units,
  ):
    return self._execute(
      "MCS",
      coordinate_system,
      motion_control,
      stop_type,
      change_decel,
      decel,
      decel_units,
      change_jerk,
      jerk,
      jerk_units,
    )

  def MOD(self, *, source_a, source_b, dest):
    left = float(source_a)
    right = float(source_b)
    result = math.fmod(left, right) if right != 0.0 else 0.0
    return self.set_tag(dest, result)

  def MOV(self, *, source, dest):
    return self.set_tag(dest, source)

  def MSF(self, *, axis, motion_control):
    return self._execute("MSF", axis, motion_control)

  def MSO(self, *, axis, motion_control):
    return self._execute("MSO", axis, motion_control)

  def OTE(self, *, output_bit, rung_in):
    self.set_tag(output_bit, bool(rung_in))
    return bool(rung_in)

  def OTL(self, *, output_bit, rung_in=True):
    if rung_in:
      self.set_tag(output_bit, True)
    return bool(rung_in)

  def OTU(self, *, output_bit, rung_in=True):
    if rung_in:
      self.set_tag(output_bit, False)
    return bool(rung_in)

  def ONS(self, *, storage_bit, output_bit=None, rung_in):
    operands = (storage_bit,) if output_bit is None else (storage_bit, output_bit)
    return self._execute("ONS", *operands, rung_in=rung_in)

  def OSF(self, *, storage_bit, output_bit, rung_in):
    return self._execute("OSF", storage_bit, output_bit, rung_in=rung_in)

  def OSR(self, *, storage_bit, output_bit, rung_in):
    return self._execute("OSR", storage_bit, output_bit, rung_in=rung_in)

  def PID(self, *operands):
    return self._execute("PID", *operands)

  def RES(self, path):
    return self._execute("RES", path)

  def SFX(self, *operands):
    return self._execute("SFX", *operands)

  def SLS(self, *operands):
    return self._execute("SLS", *operands)

  def TON(self, *, timer_tag, preset=None, accum=None, rung_in):
    return self._execute("TON", timer_tag, preset, accum, rung_in=rung_in)

  def TRN(self, *, source, dest):
    return self.set_tag(dest, math.trunc(float(source)))


def bind_scan_context(
  ctx: ScanContext,
  *,
  expression_evaluator: ExpressionEvaluator | None = None,
) -> BoundRoutineAPI:
  return BoundRoutineAPI(
    ctx=ctx,
    runtime=InstructionRuntime(expression_evaluator=expression_evaluator),
  )


def load_imperative_routine_from_source(
  source: str,
  *,
  symbol_name: str | None = None,
) -> Callable[[ScanContext], None]:
  namespace: dict[str, object] = {}
  exec(compile(source, "<plc_ladder_imperative>", "exec"), namespace)

  routines = [
    value
    for value in namespace.values()
    if isinstance(value, Routine)
  ]
  routine_metadata = routines[0] if len(routines) == 1 else None

  default_symbol = symbol_name
  if default_symbol is None and routine_metadata is not None:
    default_symbol = _python_name(routine_metadata.name, routine_metadata.program)

  routine_fn = namespace.get(default_symbol) if default_symbol is not None else None
  if not callable(routine_fn):
    candidates = [
      value
      for name, value in namespace.items()
      if callable(value)
      and hasattr(value, "__code__")
      and value.__code__.co_filename == "<plc_ladder_imperative>"
      and not str(name).startswith("__")
    ]
    if len(candidates) != 1:
      raise ValueError("Imperative source did not define a unique routine function")
    routine_fn = candidates[0]

  routine_name = routine_metadata.name if routine_metadata is not None else getattr(routine_fn, "__name__", "main")
  routine_program = routine_metadata.program if routine_metadata is not None else None

  def execute(ctx: ScanContext):
    previous_program = ctx.current_program
    previous_routine = ctx.current_routine
    ctx.current_program = routine_program
    ctx.current_routine = routine_name
    try:
      routine_fn(ctx)
    finally:
      ctx.current_program = previous_program
      ctx.current_routine = previous_routine

  execute.__name__ = getattr(routine_fn, "__name__", "execute")
  execute.ladder_routine = routine_metadata
  execute.ladder_source = source
  return execute


__all__ = [
  "BoundRoutineAPI",
  "bind_scan_context",
  "load_imperative_routine_from_source",
]
