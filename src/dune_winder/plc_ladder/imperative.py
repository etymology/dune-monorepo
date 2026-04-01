from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from typing import Callable
from typing import Literal
from typing import Protocol
from typing import TypeAlias

from .ast import InstructionCall
from .ast import Routine
from .runtime import ExpressionEvaluator
from .runtime import InstructionRuntime
from .runtime import ScanContext
from .runtime import _deep_copy


def _operand_token(value: Any) -> str:
  if value is None:
    return "?"
  if isinstance(value, bool):
    return "true" if value else "false"
  if isinstance(value, TagRef):
    return value.path
  return str(value)


def _python_name(name: str, program: str | None = None) -> str:
  parts = []
  if program:
    parts.append(program)
  parts.append(name)
  text = "_".join(parts)
  return "".join(character if character.isalnum() else "_" for character in text)


def _coerce_value(value: Any) -> Any:
  if isinstance(value, TagRef):
    return value.value
  return value


def formula_atan(value: float) -> float:
  return math.atan(float(value))


def formula_cos(value: Any) -> float:
  return math.cos(float(value))


def formula_fmod(left: Any, right: Any) -> float:
  divisor = float(right)
  if divisor == 0.0:
    return 0.0
  return math.fmod(float(left), divisor)


def formula_sin(value: float) -> float:
  return math.sin(float(value))


def formula_sqrt(value: float) -> float:
  return math.sqrt(max(float(value), 0.0))


def formula_trunc(value: float) -> int:
  return math.trunc(float(value))


class ADDCallable(Protocol):
  def __call__(self, *, source_a: Any, source_b: Any, dest: Any) -> Any: ...


class COPCallable(Protocol):
  def __call__(self, *, source: Any, dest: Any, length: Any) -> Any: ...


class CPTCallable(Protocol):
  def __call__(self, *, dest: Any, value: Any) -> Any: ...


class CTDCallable(Protocol):
  def __call__(
    self,
    counter_tag: TimerTag | TagPathOperand,
    preset: NumericOperand | None = None,
    accum: NumericOperand | None = None,
    rung_in: Any = True,
  ) -> Any: ...


class CTUCallable(Protocol):
  def __call__(
    self,
    counter_tag: TimerTag | TagPathOperand,
    preset: NumericOperand | None = None,
    accum: NumericOperand | None = None,
    rung_in: Any = True,
  ) -> Any: ...


class FFLCallable(Protocol):
  def __call__(
    self,
    *,
    source: Any,
    array: Any,
    control: Any,
    length: Any = None,
    position: Any = None,
    rung_in: bool = True,
  ) -> Any: ...


class FFUCallable(Protocol):
  def __call__(
    self,
    *,
    array: Any,
    dest: Any,
    control: Any,
    length: Any = None,
    position: Any = None,
    rung_in: bool = True,
  ) -> Any: ...


class FLLCallable(Protocol):
  def __call__(self, *, value: Any, dest: Any, length: Any) -> Any: ...


class JSRCallable(Protocol):
  def __call__(self, *, routine: Any, parameter_block: Any = None) -> Any: ...


class MAFRCallable(Protocol):
  def __call__(
    self,
    *,
    axis: AxisTag | TagPathOperand,
    motion_control: MotionControlTag | TagPathOperand,
  ) -> Any: ...


class MAMCallable(Protocol):
  def __call__(
    self,
    *,
    axis: AxisTag | TagPathOperand,
    motion_control: MotionControlTag | TagPathOperand,
    move_type: IntegerOperand,
    target: MotionTargetOperand,
    speed: NumericOperand,
    speed_units: MotionSpeedUnits,
    accel: NumericOperand,
    accel_units: MotionAccelUnits,
    decel: NumericOperand,
    decel_units: MotionAccelUnits,
    profile: MotionProfile,
    accel_jerk: NumericOperand,
    decel_jerk: NumericOperand,
    jerk_units: MotionJerkUnits,
    merge: MotionMerge,
    merge_speed: MotionMergeSpeed,
    lock_position: IntegerOperand,
    lock_direction: MotionLockDirection,
    event_distance: NumericOperand,
    calculated_data: NumericOperand,
    rung_in: bool = True,
  ) -> Any: ...


class MASCallable(Protocol):
  def __call__(
    self,
    *,
    axis: AxisTag | TagPathOperand,
    motion_control: MotionControlTag | TagPathOperand,
    stop_type: MotionStopType,
    change_decel: MotionToggle,
    decel: NumericOperand,
    decel_units: MotionAccelUnits,
    change_jerk: MotionToggle,
    jerk: NumericOperand,
    jerk_units: MotionJerkUnits,
  ) -> Any: ...


class MCCDCallable(Protocol):
  def __call__(
    self,
    *,
    coordinate_system: CoordinateSystemTag | TagPathOperand,
    motion_control: MotionControlTag | TagPathOperand,
    scope: MotionScope,
    speed_enable: MotionToggle,
    speed: NumericOperand,
    speed_units: MotionSpeedUnits,
    accel_enable: MotionToggle,
    accel: NumericOperand,
    accel_units: MotionAccelUnits,
    decel_enable: MotionToggle,
    decel: NumericOperand,
    decel_units: MotionAccelUnits,
    accel_jerk_enable: MotionToggle,
    accel_jerk: NumericOperand,
    decel_jerk_enable: MotionToggle,
    decel_jerk: NumericOperand,
    jerk_units: MotionJerkUnits,
    apply_to: MotionApplyTo,
  ) -> Any: ...


class MCCMCallable(Protocol):
  def __call__(
    self,
    *,
    coordinate_system: CoordinateSystemTag | TagPathOperand,
    motion_control: MotionControlTag | TagPathOperand,
    move_type: IntegerOperand,
    end_position: TagPathOperand,
    circle_type: IntegerOperand,
    via_or_center: TagPathOperand,
    direction: IntegerOperand,
    speed: NumericOperand,
    speed_units: MotionSpeedUnits,
    accel: NumericOperand,
    accel_units: MotionAccelUnits,
    decel: NumericOperand,
    decel_units: MotionAccelUnits,
    profile: MotionProfile,
    accel_jerk: NumericOperand,
    decel_jerk: NumericOperand,
    jerk_units: MotionJerkUnits,
    termination_type: IntegerOperand,
    merge: MotionMerge,
    merge_speed: MotionMergeSpeed,
    command_tolerance: NumericOperand,
    lock_position: IntegerOperand,
    lock_direction: MotionLockDirection,
    event_distance: NumericOperand,
    calculated_data: NumericOperand,
    rung_in: bool = True,
  ) -> Any: ...


class MCLMCallable(Protocol):
  def __call__(
    self,
    *,
    coordinate_system: CoordinateSystemTag | TagPathOperand,
    motion_control: MotionControlTag | TagPathOperand,
    move_type: IntegerOperand,
    target: TagPathOperand,
    speed: NumericOperand,
    speed_units: MotionSpeedUnits,
    accel: NumericOperand,
    accel_units: MotionAccelUnits,
    decel: NumericOperand,
    decel_units: MotionAccelUnits,
    profile: MotionProfile,
    accel_jerk: NumericOperand,
    decel_jerk: NumericOperand,
    jerk_units: MotionJerkUnits,
    termination_type: IntegerOperand,
    merge: MotionMerge,
    merge_speed: MotionMergeSpeed,
    command_tolerance: NumericOperand,
    lock_position: IntegerOperand,
    lock_direction: MotionLockDirection,
    event_distance: NumericOperand,
    calculated_data: NumericOperand,
    rung_in: bool = True,
  ) -> Any: ...


class MCSCallable(Protocol):
  def __call__(
    self,
    *,
    coordinate_system: CoordinateSystemTag | TagPathOperand,
    motion_control: MotionControlTag | TagPathOperand,
    stop_type: MotionStopType,
    change_decel: MotionToggle,
    decel: NumericOperand,
    decel_units: MotionAccelUnits,
    change_jerk: MotionToggle,
    jerk: NumericOperand,
    jerk_units: MotionJerkUnits,
  ) -> Any: ...


class MODCallable(Protocol):
  def __call__(self, *, source_a: Any, source_b: Any, dest: Any) -> Any: ...


class MOVCallable(Protocol):
  def __call__(self, *, source: Any, dest: Any) -> Any: ...


class MSFCallable(Protocol):
  def __call__(
    self,
    *,
    axis: AxisTag | TagPathOperand,
    motion_control: MotionControlTag | TagPathOperand,
  ) -> Any: ...


class MSOCallable(Protocol):
  def __call__(
    self,
    *,
    axis: AxisTag | TagPathOperand,
    motion_control: MotionControlTag | TagPathOperand,
  ) -> Any: ...


class NOPCallable(Protocol):
  def __call__(self) -> Any: ...


class ONSCallable(Protocol):
  def __call__(
    self,
    *,
    storage_bit: Any,
    output_bit: Any = None,
    rung_in: Any,
  ) -> Any: ...


class OSFCallable(Protocol):
  def __call__(self, *, storage_bit: Any, output_bit: Any, rung_in: Any) -> Any: ...


class OSRCallable(Protocol):
  def __call__(self, *, storage_bit: Any, output_bit: Any, rung_in: Any) -> Any: ...


class OTLCallable(Protocol):
  def __call__(self, *, output_bit: Any, rung_in: bool = True) -> bool: ...


class OTUCallable(Protocol):
  def __call__(self, *, output_bit: Any, rung_in: bool = True) -> bool: ...


class PIDCallable(Protocol):
  def __call__(
    self,
    *,
    control_block: Any,
    process_variable: Any,
    tieback: Any,
    control_variable: Any,
    feedforward: Any,
    alarm_disable: Any,
    hold: Any,
  ) -> Any: ...


class RESCallable(Protocol):
  def __call__(self, path: Any) -> Any: ...


class SFXCallable(Protocol):
  def __call__(self, *operands: Any) -> Any: ...


class SLSCallable(Protocol):
  def __call__(self, *operands: Any) -> Any: ...


class TONCallable(Protocol):
  def __call__(
    self,
    *,
    timer_tag: Any,
    preset: Any = None,
    accum: Any = None,
    rung_in: Any,
  ) -> Any: ...


class TRNCallable(Protocol):
  def __call__(self, *, source: Any, dest: Any) -> Any: ...


class TagRef:
  __slots__ = ("_ctx", "_path")

  def __init__(self, ctx: ScanContext, path: str):
    self._ctx = ctx
    self._path = str(path)

  @property
  def path(self) -> str:
    return self._path

  @property
  def value(self) -> Any:
    return self._ctx.get_value(self._path)

  def set(self, value: Any) -> Any:
    resolved = _deep_copy(_coerce_value(value))
    self._ctx.set_value(self._path, resolved)
    return resolved

  def __getattr__(self, name: str) -> TagRef:
    if name.startswith("__"):
      raise AttributeError(name)
    return TagRef(self._ctx, f"{self._path}.{name}")

  def __getitem__(self, index: Any) -> TagRef:
    return TagRef(self._ctx, f"{self._path}[{index}]")

  def __repr__(self) -> str:
    return f"TagRef(path={self._path!r}, value={self.value!r})"

  def __str__(self) -> str:
    return self._path

  def __bool__(self) -> bool:
    return bool(self.value)

  def __int__(self) -> int:
    return int(self.value)

  def __float__(self) -> float:
    return float(self.value)

  def __abs__(self) -> Any:
    return abs(self.value)

  def __neg__(self) -> Any:
    return -self.value

  def __pos__(self) -> Any:
    return +self.value

  def _binary(self, other: Any, operator: Callable[[Any, Any], Any]) -> Any:
    return operator(self.value, _coerce_value(other))

  def _rbinary(self, other: Any, operator: Callable[[Any, Any], Any]) -> Any:
    return operator(_coerce_value(other), self.value)

  def __add__(self, other: Any) -> Any:
    return self._binary(other, lambda left, right: left + right)

  def __radd__(self, other: Any) -> Any:
    return self._rbinary(other, lambda left, right: left + right)

  def __sub__(self, other: Any) -> Any:
    return self._binary(other, lambda left, right: left - right)

  def __rsub__(self, other: Any) -> Any:
    return self._rbinary(other, lambda left, right: left - right)

  def __mul__(self, other: Any) -> Any:
    return self._binary(other, lambda left, right: left * right)

  def __rmul__(self, other: Any) -> Any:
    return self._rbinary(other, lambda left, right: left * right)

  def __truediv__(self, other: Any) -> Any:
    return self._binary(
      other,
      lambda left, right: float("inf") if float(right) == 0.0 else left / right,
    )

  def __rtruediv__(self, other: Any) -> Any:
    return self._rbinary(
      other,
      lambda left, right: float("inf") if float(right) == 0.0 else left / right,
    )

  def __mod__(self, other: Any) -> Any:
    return self._binary(other, lambda left, right: left % right)

  def __rmod__(self, other: Any) -> Any:
    return self._rbinary(other, lambda left, right: left % right)

  def __eq__(self, other) -> bool:
    return self._binary(other, lambda left, right: left == right)

  def __ne__(self, other) -> bool:
    return self._binary(other, lambda left, right: left != right)

  def __lt__(self, other) -> bool:
    return self._binary(other, lambda left, right: left < right)

  def __le__(self, other) -> bool:
    return self._binary(other, lambda left, right: left <= right)

  def __gt__(self, other) -> bool:
    return self._binary(other, lambda left, right: left > right)

  def __ge__(self, other) -> bool:
    return self._binary(other, lambda left, right: left >= right)


class SupportsBoolTag(Protocol):
  path: str

  @property
  def value(self) -> bool: ...

  def set(self, value: bool) -> bool: ...

  def __bool__(self) -> bool: ...


class SupportsIntTag(Protocol):
  path: str

  @property
  def value(self) -> int: ...

  def set(self, value: int) -> int: ...

  def __bool__(self) -> bool: ...
  def __int__(self) -> int: ...


class SupportsRealTag(Protocol):
  path: str

  @property
  def value(self) -> float: ...

  def set(self, value: float) -> float: ...

  def __bool__(self) -> bool: ...
  def __float__(self) -> float: ...


class SupportsStringTag(Protocol):
  path: str

  @property
  def value(self) -> str: ...

  def set(self, value: str) -> str: ...


class SupportsArrayTag(Protocol):
  path: str

  def __getitem__(self, index: Any) -> TagRef: ...


BoolTag: TypeAlias = TagRef | SupportsBoolTag
IntTag: TypeAlias = TagRef | SupportsIntTag
RealTag: TypeAlias = TagRef | SupportsRealTag
StringTag: TypeAlias = TagRef | SupportsStringTag
ArrayTag: TypeAlias = TagRef | SupportsArrayTag
NumericTag: TypeAlias = IntTag | RealTag


class SupportsTimerTag(Protocol):
  PRE: IntTag
  ACC: IntTag
  EN: BoolTag
  TT: BoolTag
  DN: BoolTag


class SupportsControlTag(Protocol):
  POS: IntTag


class SupportsMotionControlTag(Protocol):
  FLAGS: IntTag
  EN: BoolTag
  DN: BoolTag
  ER: BoolTag
  PC: BoolTag
  IP: BoolTag


class SupportsAxisTag(Protocol):
  ActualPosition: RealTag
  ActualVelocity: RealTag
  CommandAcceleration: RealTag
  DriveEnableStatus: BoolTag
  CoordinatedMotionStatus: BoolTag
  MoveStatus: BoolTag
  PhysicalAxisFault: BoolTag
  ModuleFault: BoolTag
  MotionFault: BoolTag
  SafeTorqueOffInhibit: BoolTag
  SLSActiveStatus: BoolTag


class SupportsCoordinateSystemTag(Protocol):
  ActualPosition: RealTag
  MovePendingStatus: BoolTag
  MovePendingQueueFullStatus: BoolTag
  MoveStatus: BoolTag
  MotionStatus: BoolTag
  StoppingStatus: BoolTag
  PhysicalAxisFault: BoolTag


class SupportsMotionSegTag(Protocol):
  Valid: BoolTag
  Seq: IntTag
  XY: ArrayTag
  Speed: RealTag
  Accel: RealTag
  Decel: RealTag
  JerkAccel: RealTag
  JerkDecel: RealTag
  TermType: IntTag
  SegType: IntTag
  CircleType: IntTag
  ViaCenter: ArrayTag
  Direction: IntTag


TimerTag: TypeAlias = TagRef | SupportsTimerTag
ControlTag: TypeAlias = TagRef | SupportsControlTag
MotionControlTag: TypeAlias = TagRef | SupportsMotionControlTag
AxisTag: TypeAlias = TagRef | SupportsAxisTag
CoordinateSystemTag: TypeAlias = TagRef | SupportsCoordinateSystemTag
MotionSegTag: TypeAlias = TagRef | SupportsMotionSegTag

TagPathOperand: TypeAlias = str | TagRef
IntegerOperand: TypeAlias = int | IntTag
NumericOperand: TypeAlias = int | float | NumericTag
MotionTargetOperand: TypeAlias = TagPathOperand | NumericOperand
MotionProfile: TypeAlias = Literal["Trapezoidal", "S-Curve"]
MotionSpeedUnits: TypeAlias = Literal["Units per sec"]
MotionAccelUnits: TypeAlias = Literal["Units per sec2"]
MotionJerkUnits: TypeAlias = Literal["Units per sec3", "% of Time"]
MotionStopType: TypeAlias = Literal["All", "Move", "Jog"]
MotionToggle: TypeAlias = Literal["Yes", "No"]
MotionMerge: TypeAlias = Literal["Disabled", "All", "Coordinated motion"] | str | int
MotionMergeSpeed: TypeAlias = Literal["Programmed"] | NumericOperand
MotionLockDirection: TypeAlias = Literal["None"] | str
MotionScope: TypeAlias = Literal["Coordinated Move"] | str
MotionApplyTo: TypeAlias = Literal["Active Motion"] | str | int


@dataclass
class BoundRoutineAPI:
  ctx: ScanContext
  runtime: InstructionRuntime

  def tag(self, path: str) -> Any:
    return _deep_copy(self.ctx.get_value(self._normalize_reference(path)))

  def ref(self, path: str) -> TagRef:
    return TagRef(self.ctx, self._normalize_reference(path))

  def set_tag(self, path: str, value: Any) -> Any:
    stored = _deep_copy(self._normalize_value(value))
    self.ctx.set_value(self._normalize_reference(path), stored)
    return stored

  def formula(self, expression: str) -> Any:
    return self.runtime.expression_evaluator.evaluate(str(expression), self.ctx)

  def _normalize_reference(self, operand: Any) -> str:
    if isinstance(operand, TagRef):
      return operand.path
    return str(operand)

  def _normalize_value(self, operand: Any) -> Any:
    return _deep_copy(_coerce_value(operand))

  def _execute(self, opcode: str, *operands: Any, rung_in: bool = True) -> Any:
    instruction = InstructionCall(
      opcode=str(opcode),
      operands=tuple(_operand_token(operand) for operand in operands),
    )
    return self.runtime.execute_instruction(instruction, bool(rung_in), self.ctx)

  def ADD(self, *, source_a: Any, source_b: Any, dest: Any) -> Any:
    return self.set_tag(dest, source_a + source_b)

  def COP(self, *, source: Any, dest: Any, length: Any) -> Any:
    return self._execute(
      "COP",
      self._normalize_reference(source),
      self._normalize_reference(dest),
      self._normalize_value(length),
    )

  def CPT(self, *, dest: Any, value: Any) -> Any:
    return self.set_tag(dest, value)

  def CTD(
    self,
    counter_tag: TimerTag | TagPathOperand,
    preset: NumericOperand | None = None,
    accum: NumericOperand | None = None,
    rung_in: Any = True,
  ) -> Any:
    return self._execute(
      "CTD",
      self._normalize_reference(counter_tag),
      self._normalize_value(preset),
      self._normalize_value(accum),
      rung_in=rung_in,
    )

  def CTU(
    self,
    counter_tag: TimerTag | TagPathOperand,
    preset: NumericOperand | None = None,
    accum: NumericOperand | None = None,
    rung_in: Any = True,
  ) -> Any:
    return self._execute(
      "CTU",
      self._normalize_reference(counter_tag),
      self._normalize_value(preset),
      self._normalize_value(accum),
      rung_in=rung_in,
    )

  def FFL(
    self,
    *,
    source: Any,
    array: Any,
    control: Any,
    length: Any = None,
    position: Any = None,
    rung_in: bool = True,
  ) -> Any:
    return self._execute(
      "FFL",
      self._normalize_reference(source),
      self._normalize_reference(array),
      self._normalize_reference(control),
      self._normalize_value(length),
      self._normalize_value(position),
      rung_in=rung_in,
    )

  def FFU(
    self,
    *,
    array: Any,
    dest: Any,
    control: Any,
    length: Any = None,
    position: Any = None,
    rung_in: bool = True,
  ) -> Any:
    return self._execute(
      "FFU",
      self._normalize_reference(array),
      self._normalize_reference(dest),
      self._normalize_reference(control),
      self._normalize_value(length),
      self._normalize_value(position),
      rung_in=rung_in,
    )

  def FLL(self, *, value: Any, dest: Any, length: Any) -> Any:
    return self._execute(
      "FLL",
      self._normalize_value(value),
      self._normalize_reference(dest),
      self._normalize_value(length),
    )

  def JSR(self, *, routine: Any, parameter_block: Any = None) -> Any:
    return self._execute(
      "JSR",
      routine,
      0 if parameter_block is None else self._normalize_value(parameter_block),
    )

  def MAFR(
    self,
    *,
    axis: AxisTag | TagPathOperand,
    motion_control: MotionControlTag | TagPathOperand,
  ) -> Any:
    return self._execute(
      "MAFR",
      self._normalize_reference(axis),
      self._normalize_reference(motion_control),
    )

  def MAM(
    self,
    *,
    axis: AxisTag | TagPathOperand,
    motion_control: MotionControlTag | TagPathOperand,
    move_type: IntegerOperand,
    target: MotionTargetOperand,
    speed: NumericOperand,
    speed_units: MotionSpeedUnits,
    accel: NumericOperand,
    accel_units: MotionAccelUnits,
    decel: NumericOperand,
    decel_units: MotionAccelUnits,
    profile: MotionProfile,
    accel_jerk: NumericOperand,
    decel_jerk: NumericOperand,
    jerk_units: MotionJerkUnits,
    merge: MotionMerge,
    merge_speed: MotionMergeSpeed,
    lock_position: IntegerOperand,
    lock_direction: MotionLockDirection,
    event_distance: NumericOperand,
    calculated_data: NumericOperand,
    rung_in: bool = True,
  ) -> Any:
    return self._execute(
      "MAM",
      self._normalize_reference(axis),
      self._normalize_reference(motion_control),
      self._normalize_value(move_type),
      self._normalize_reference(target),
      self._normalize_value(speed),
      speed_units,
      self._normalize_value(accel),
      accel_units,
      self._normalize_value(decel),
      decel_units,
      profile,
      self._normalize_value(accel_jerk),
      self._normalize_value(decel_jerk),
      jerk_units,
      merge,
      merge_speed,
      lock_position,
      lock_direction,
      event_distance,
      calculated_data,
      rung_in=rung_in,
    )

  def MAS(
    self,
    *,
    axis: AxisTag | TagPathOperand,
    motion_control: MotionControlTag | TagPathOperand,
    stop_type: MotionStopType,
    change_decel: MotionToggle,
    decel: NumericOperand,
    decel_units: MotionAccelUnits,
    change_jerk: MotionToggle,
    jerk: NumericOperand,
    jerk_units: MotionJerkUnits,
  ) -> Any:
    return self._execute(
      "MAS",
      self._normalize_reference(axis),
      self._normalize_reference(motion_control),
      stop_type,
      change_decel,
      self._normalize_value(decel),
      decel_units,
      change_jerk,
      self._normalize_value(jerk),
      jerk_units,
    )

  def MCCM(
    self,
    *,
    coordinate_system: CoordinateSystemTag | TagPathOperand,
    motion_control: MotionControlTag | TagPathOperand,
    move_type: IntegerOperand,
    end_position: TagPathOperand,
    circle_type: IntegerOperand,
    via_or_center: TagPathOperand,
    direction: IntegerOperand,
    speed: NumericOperand,
    speed_units: MotionSpeedUnits,
    accel: NumericOperand,
    accel_units: MotionAccelUnits,
    decel: NumericOperand,
    decel_units: MotionAccelUnits,
    profile: MotionProfile,
    accel_jerk: NumericOperand,
    decel_jerk: NumericOperand,
    jerk_units: MotionJerkUnits,
    termination_type: IntegerOperand,
    merge: MotionMerge,
    merge_speed: MotionMergeSpeed,
    command_tolerance: NumericOperand,
    lock_position: IntegerOperand,
    lock_direction: MotionLockDirection,
    event_distance: NumericOperand,
    calculated_data: NumericOperand,
    rung_in: bool = True,
  ) -> Any:
    return self._execute(
      "MCCM",
      self._normalize_reference(coordinate_system),
      self._normalize_reference(motion_control),
      self._normalize_value(move_type),
      self._normalize_reference(end_position),
      self._normalize_value(circle_type),
      self._normalize_reference(via_or_center),
      self._normalize_value(direction),
      self._normalize_value(speed),
      speed_units,
      self._normalize_value(accel),
      accel_units,
      self._normalize_value(decel),
      decel_units,
      profile,
      self._normalize_value(accel_jerk),
      self._normalize_value(decel_jerk),
      jerk_units,
      self._normalize_value(termination_type),
      merge,
      merge_speed,
      self._normalize_value(command_tolerance),
      lock_position,
      lock_direction,
      event_distance,
      calculated_data,
      rung_in=rung_in,
    )

  def MCCD(
    self,
    *,
    coordinate_system: CoordinateSystemTag | TagPathOperand,
    motion_control: MotionControlTag | TagPathOperand,
    scope: MotionScope,
    speed_enable: MotionToggle,
    speed: NumericOperand,
    speed_units: MotionSpeedUnits,
    accel_enable: MotionToggle,
    accel: NumericOperand,
    accel_units: MotionAccelUnits,
    decel_enable: MotionToggle,
    decel: NumericOperand,
    decel_units: MotionAccelUnits,
    accel_jerk_enable: MotionToggle,
    accel_jerk: NumericOperand,
    decel_jerk_enable: MotionToggle,
    decel_jerk: NumericOperand,
    jerk_units: MotionJerkUnits,
    apply_to: MotionApplyTo,
  ) -> Any:
    return self._execute(
      "MCCD",
      self._normalize_reference(coordinate_system),
      self._normalize_reference(motion_control),
      scope,
      speed_enable,
      self._normalize_value(speed),
      speed_units,
      accel_enable,
      self._normalize_value(accel),
      accel_units,
      decel_enable,
      self._normalize_value(decel),
      decel_units,
      accel_jerk_enable,
      self._normalize_value(accel_jerk),
      decel_jerk_enable,
      self._normalize_value(decel_jerk),
      jerk_units,
      self._normalize_value(apply_to),
    )

  def MCLM(
    self,
    *,
    coordinate_system: CoordinateSystemTag | TagPathOperand,
    motion_control: MotionControlTag | TagPathOperand,
    move_type: IntegerOperand,
    target: TagPathOperand,
    speed: NumericOperand,
    speed_units: MotionSpeedUnits,
    accel: NumericOperand,
    accel_units: MotionAccelUnits,
    decel: NumericOperand,
    decel_units: MotionAccelUnits,
    profile: MotionProfile,
    accel_jerk: NumericOperand,
    decel_jerk: NumericOperand,
    jerk_units: MotionJerkUnits,
    termination_type: IntegerOperand,
    merge: MotionMerge,
    merge_speed: MotionMergeSpeed,
    command_tolerance: NumericOperand,
    lock_position: IntegerOperand,
    lock_direction: MotionLockDirection,
    event_distance: NumericOperand,
    calculated_data: NumericOperand,
    rung_in: bool = True,
  ) -> Any:
    return self._execute(
      "MCLM",
      self._normalize_reference(coordinate_system),
      self._normalize_reference(motion_control),
      self._normalize_value(move_type),
      self._normalize_reference(target),
      self._normalize_value(speed),
      speed_units,
      self._normalize_value(accel),
      accel_units,
      self._normalize_value(decel),
      decel_units,
      profile,
      self._normalize_value(accel_jerk),
      self._normalize_value(decel_jerk),
      jerk_units,
      self._normalize_value(termination_type),
      merge,
      merge_speed,
      self._normalize_value(command_tolerance),
      lock_position,
      lock_direction,
      event_distance,
      calculated_data,
      rung_in=rung_in,
    )

  def MCS(
    self,
    *,
    coordinate_system: CoordinateSystemTag | TagPathOperand,
    motion_control: MotionControlTag | TagPathOperand,
    stop_type: MotionStopType,
    change_decel: MotionToggle,
    decel: NumericOperand,
    decel_units: MotionAccelUnits,
    change_jerk: MotionToggle,
    jerk: NumericOperand,
    jerk_units: MotionJerkUnits,
  ) -> Any:
    return self._execute(
      "MCS",
      self._normalize_reference(coordinate_system),
      self._normalize_reference(motion_control),
      stop_type,
      change_decel,
      self._normalize_value(decel),
      decel_units,
      change_jerk,
      self._normalize_value(jerk),
      jerk_units,
    )

  def MOD(self, *, source_a: Any, source_b: Any, dest: Any) -> Any:
    left = float(source_a)
    right = float(source_b)
    result = math.fmod(left, right) if right != 0.0 else 0.0
    return self.set_tag(dest, result)

  def MOV(self, *, source: Any, dest: Any) -> Any:
    return self.set_tag(dest, source)

  def MSF(
    self,
    *,
    axis: AxisTag | TagPathOperand,
    motion_control: MotionControlTag | TagPathOperand,
  ) -> Any:
    return self._execute(
      "MSF",
      self._normalize_reference(axis),
      self._normalize_reference(motion_control),
    )

  def MSO(
    self,
    *,
    axis: AxisTag | TagPathOperand,
    motion_control: MotionControlTag | TagPathOperand,
  ) -> Any:
    return self._execute(
      "MSO",
      self._normalize_reference(axis),
      self._normalize_reference(motion_control),
    )

  def NOP(self) -> Any:
    return self._execute("NOP")

  def OTE(self, *, output_bit: Any, rung_in: Any) -> bool:
    self.set_tag(output_bit, bool(rung_in))
    return bool(rung_in)

  def OTL(self, *, output_bit: Any, rung_in: bool = True) -> bool:
    if rung_in:
      self.set_tag(output_bit, True)
    return bool(rung_in)

  def OTU(self, *, output_bit: Any, rung_in: bool = True) -> bool:
    if rung_in:
      self.set_tag(output_bit, False)
    return bool(rung_in)

  def ONS(
    self,
    *,
    storage_bit: Any,
    output_bit: Any = None,
    rung_in: Any,
  ) -> Any:
    operands = (
      (self._normalize_reference(storage_bit),)
      if output_bit is None
      else (
        self._normalize_reference(storage_bit),
        self._normalize_reference(output_bit),
      )
    )
    return self._execute("ONS", *operands, rung_in=rung_in)

  def OSF(self, *, storage_bit: Any, output_bit: Any, rung_in: Any) -> Any:
    return self._execute(
      "OSF",
      self._normalize_reference(storage_bit),
      self._normalize_reference(output_bit),
      rung_in=rung_in,
    )

  def OSR(self, *, storage_bit: Any, output_bit: Any, rung_in: Any) -> Any:
    return self._execute(
      "OSR",
      self._normalize_reference(storage_bit),
      self._normalize_reference(output_bit),
      rung_in=rung_in,
    )

  def PID(
    self,
    *,
    control_block: Any,
    process_variable: Any,
    tieback: Any,
    control_variable: Any,
    feedforward: Any,
    alarm_disable: Any,
    hold: Any,
  ) -> Any:
    return self._execute(
      "PID",
      self._normalize_reference(control_block),
      self._normalize_value(process_variable),
      self._normalize_value(tieback),
      self._normalize_reference(control_variable),
      self._normalize_value(feedforward),
      self._normalize_value(alarm_disable),
      self._normalize_value(hold),
    )

  def RES(self, path: Any) -> Any:
    return self._execute("RES", self._normalize_reference(path))

  def SFX(self, *operands: Any) -> Any:
    return self._execute("SFX", *operands)

  def SLS(self, *operands: Any) -> Any:
    return self._execute("SLS", *operands)

  def TON(
    self,
    *,
    timer_tag: Any,
    preset: Any = None,
    accum: Any = None,
    rung_in: Any,
  ) -> Any:
    return self._execute(
      "TON",
      self._normalize_reference(timer_tag),
      self._normalize_value(preset),
      self._normalize_value(accum),
      rung_in=rung_in,
    )

  def TRN(self, *, source: Any, dest: Any) -> Any:
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
  namespace: dict[str, Any] = {}
  exec(compile(source, "<plc_ladder_imperative>", "exec"), namespace)

  routines = [value for value in namespace.values() if isinstance(value, Routine)]
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

  routine_name = (
    routine_metadata.name
    if routine_metadata is not None
    else getattr(routine_fn, "__name__", "main")
  )
  routine_program = routine_metadata.program if routine_metadata is not None else None

  def execute(ctx: ScanContext) -> None:
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
  "ADDCallable",
  "ArrayTag",
  "AxisTag",
  "BoundRoutineAPI",
  "BoolTag",
  "COPCallable",
  "ControlTag",
  "CoordinateSystemTag",
  "CPTCallable",
  "CTDCallable",
  "CTUCallable",
  "FFLCallable",
  "FFUCallable",
  "FLLCallable",
  "IntTag",
  "JSRCallable",
  "MAFRCallable",
  "MAMCallable",
  "MASCallable",
  "MCCDCallable",
  "MCCMCallable",
  "MCLMCallable",
  "MCSCallable",
  "MODCallable",
  "MOVCallable",
  "MotionAccelUnits",
  "MotionApplyTo",
  "MotionControlTag",
  "MotionJerkUnits",
  "MotionLockDirection",
  "MotionMerge",
  "MotionMergeSpeed",
  "MotionProfile",
  "MotionScope",
  "MotionSegTag",
  "MotionSpeedUnits",
  "MotionStopType",
  "MotionTargetOperand",
  "MotionToggle",
  "MSFCallable",
  "MSOCallable",
  "NOPCallable",
  "NumericOperand",
  "ONSCallable",
  "OSFCallable",
  "OSRCallable",
  "OTLCallable",
  "OTUCallable",
  "PIDCallable",
  "RealTag",
  "RESCallable",
  "SFXCallable",
  "SLSCallable",
  "StringTag",
  "TagRef",
  "TagPathOperand",
  "TimerTag",
  "TONCallable",
  "TRNCallable",
  "bind_scan_context",
  "formula_atan",
  "formula_cos",
  "formula_fmod",
  "formula_sin",
  "formula_sqrt",
  "formula_trunc",
  "load_imperative_routine_from_source",
]
