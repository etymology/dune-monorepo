from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass
from dataclasses import field

from .ast import Branch
from .ast import InstructionCall
from .ast import Node
from .ast import Routine
from .jsr_registry import JSRRegistry
from .tags import PathSegment
from .tags import TagStore
from .tags import split_tag_path
from .types import PLCStruct


FORMULA_FUNCTIONS = {
  "ABS": abs,
  "ATN": math.atan,
  "COS": math.cos,
  "SIN": math.sin,
  "SQR": lambda value: math.sqrt(max(float(value), 0.0)),
  "MOD": lambda left, right: math.fmod(float(left), float(right)) if float(right) != 0 else 0.0,
}

NUMERIC_PATTERN = re.compile(
  r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$"
)
IDENTIFIER_PATTERN = re.compile(
  r"(?<![A-Za-z0-9_.])"
  r"([A-Za-z_][A-Za-z0-9_:]*(?:\[[^\]]+\])*(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]+\])*)*)"
)


def _path_to_string(segments: tuple[PathSegment, ...]) -> str:
  parts = []
  for segment in segments:
    text = segment.name
    for index in segment.indexes:
      text += f"[{index}]"
    parts.append(text)
  return ".".join(parts)


def _coerce_bool(value) -> bool:
  if isinstance(value, str):
    return value.strip().lower() not in {"", "0", "false", "no", "off"}
  return bool(value)


def _coerce_int(value) -> int:
  if isinstance(value, bool):
    return 1 if value else 0
  return int(float(value))


def _coerce_float(value) -> float:
  if isinstance(value, bool):
    return 1.0 if value else 0.0
  return float(value)


def _zero_like(value):
  if isinstance(value, PLCStruct):
    return value.__class__({key: _zero_like(item) for key, item in value.items()})
  if isinstance(value, dict):
    return {key: _zero_like(item) for key, item in value.items()}
  if isinstance(value, list):
    return [_zero_like(item) for item in value]
  if isinstance(value, bool):
    return False
  if isinstance(value, float):
    return 0.0
  if isinstance(value, str):
    return ""
  return 0


def _deep_copy(value):
  return copy.deepcopy(value)


@dataclass
class ActiveMotion:
  control_path: str
  component_paths: tuple[str, ...]
  start_positions: tuple[float, ...]
  target_positions: tuple[float, ...]
  speed: float
  acceleration: float
  total_scans: int
  remaining_scans: int
  axis_paths: tuple[str, ...] = ()
  coordinate_path: str | None = None
  command_name: str = ""
  direction: int | None = None
  pending: bool = False


@dataclass
class RuntimeState:
  scan_time_ms: int = 100
  axis_moves: dict[str, ActiveMotion] = field(default_factory=dict)
  coordinate_moves: dict[str, ActiveMotion] = field(default_factory=dict)
  coordinate_pending_moves: dict[str, ActiveMotion] = field(default_factory=dict)


@dataclass
class ScanContext:
  tag_store: TagStore
  jsr_registry: JSRRegistry
  runtime_state: RuntimeState = field(default_factory=RuntimeState)
  builtin_values: dict[str, object] = field(default_factory=dict)
  current_program: str | None = None
  current_routine: str | None = None
  scan_count: int = 0

  @property
  def scan_dt_seconds(self) -> float:
    return self.runtime_state.scan_time_ms / 1000.0

  def get_value(self, path: str, program: str | None = None):
    target_program = self.current_program if program is None else program
    try:
      return self.tag_store.get(path, program=target_program)
    except KeyError:
      unique_program = self._unique_program_for_path(path) if target_program is None else None
      if unique_program is not None:
        try:
          return self.tag_store.get(path, program=unique_program)
        except KeyError:
          pass
      return self.builtin_values.get(str(path), 0)

  def set_value(self, path: str, value, program: str | None = None):
    target_program = self.current_program if program is None else program
    try:
      return self.tag_store.set(path, value, program=target_program)
    except KeyError:
      unique_program = self._unique_program_for_path(path) if target_program is None else None
      if unique_program is not None:
        return self.tag_store.set(path, value, program=unique_program)
      self.builtin_values[str(path)] = _deep_copy(value)
      return value

  def exists(self, path: str, program: str | None = None) -> bool:
    target_program = self.current_program if program is None else program
    if self.tag_store.exists(path, program=target_program):
      return True
    unique_program = self._unique_program_for_path(path) if target_program is None else None
    if unique_program is not None and self.tag_store.exists(path, program=unique_program):
      return True
    return str(path) in self.builtin_values

  def _unique_program_for_path(self, path: str) -> str | None:
    segments = split_tag_path(path)
    if not segments:
      return None
    root_name = segments[0].name
    matches = [
      program_name
      for program_name, tags in self.tag_store._program_tags.items()
      if root_name in tags
    ]
    if len(matches) == 1:
      return matches[0]
    return None

  def resolve_operand(self, token: str):
    text = str(token)
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
      return text[1:-1]
    if text == "?":
      return None
    if NUMERIC_PATTERN.fullmatch(text):
      if "." in text or "e" in text.lower():
        return float(text)
      return int(text)
    if text.lower() in {"true", "false"}:
      return text.lower() == "true"
    if self.exists(text):
      return self.get_value(text)
    return text


class _RoutineJump(RuntimeError):
  def __init__(self, label: str):
    super().__init__(label)
    self.label = str(label)


class ExpressionEvaluator:
  def evaluate(self, expression: str, ctx: ScanContext):
    source = str(expression).strip()
    transformed = re.sub(r"<>", "!=", source)
    transformed = re.sub(r"(?<![<>=!])=(?!=)", "==", transformed)
    transformed = IDENTIFIER_PATTERN.sub(
      lambda match: self._replace_identifier(match, transformed),
      transformed,
    )

    def resolve(name: str):
      return ctx.get_value(name)

    environment = {"__builtins__": {}}
    environment.update(FORMULA_FUNCTIONS)
    environment["resolve"] = resolve
    try:
      return eval(transformed, environment, {})
    except ZeroDivisionError:
      return float("inf")

  def _replace_identifier(self, match: re.Match[str], text: str) -> str:
    identifier = match.group(1)
    end = match.end(1)
    if end < len(text) and text[end] == "(" and identifier.upper() in FORMULA_FUNCTIONS:
      return identifier.upper()
    if identifier in {"and", "or", "not"}:
      return identifier
    return f'resolve("{identifier}")'


class RoutineExecutor:
  def __init__(self, expression_evaluator: ExpressionEvaluator | None = None):
    self.expression_evaluator = expression_evaluator or ExpressionEvaluator()

  def execute_routine(self, routine: Routine, ctx: ScanContext):
    previous_program = ctx.current_program
    previous_routine = ctx.current_routine
    ctx.current_program = routine.program
    ctx.current_routine = routine.name

    labels = self._label_index(routine)
    index = 0
    try:
      while 0 <= index < len(routine.rungs):
        try:
          self._execute_rung(routine.rungs[index].nodes, True, ctx)
          index += 1
        except _RoutineJump as jump:
          index = labels.get(jump.label, len(routine.rungs))
    finally:
      ctx.current_program = previous_program
      ctx.current_routine = previous_routine

  def advance_runtime(self, ctx: ScanContext):
    self._advance_axis_moves(ctx)
    self._advance_coordinate_moves(ctx)
    ctx.scan_count += 1

  def _label_index(self, routine: Routine) -> dict[str, int]:
    labels = {}
    for index, rung in enumerate(routine.rungs):
      if not rung.nodes:
        continue
      node = rung.nodes[0]
      if isinstance(node, InstructionCall) and node.opcode == "LBL" and node.operands:
        labels[str(node.operands[0])] = index
    return labels

  def _execute_rung(self, nodes: tuple[Node, ...], condition_in: bool, ctx: ScanContext) -> bool:
    condition = bool(condition_in)
    for node in nodes:
      if isinstance(node, Branch):
        condition = self._execute_branch(node, condition, ctx)
        continue
      condition = self._execute_instruction(node, condition, ctx)
    return condition

  def _execute_branch(self, branch: Branch, condition_in: bool, ctx: ScanContext) -> bool:
    results = []
    for branch_nodes in branch.branches:
      results.append(self._execute_rung(branch_nodes, condition_in, ctx))
    return any(results)

  def _execute_instruction(self, instruction: InstructionCall, condition_in: bool, ctx: ScanContext) -> bool:
    opcode = instruction.opcode
    operands = instruction.operands

    if opcode == "XIC":
      return bool(condition_in) and _coerce_bool(ctx.get_value(operands[0]))
    if opcode == "XIO":
      return bool(condition_in) and not _coerce_bool(ctx.get_value(operands[0]))
    if opcode == "CMP":
      return bool(condition_in) and _coerce_bool(self.expression_evaluator.evaluate(operands[0], ctx))
    if opcode in {"EQU", "NEQ", "GEQ", "GRT", "LEQ", "LES"}:
      return self._execute_compare(opcode, operands, condition_in, ctx)
    if opcode == "LIM":
      return self._execute_limit(operands, condition_in, ctx)
    if opcode == "ONS":
      return self._execute_ons(operands, condition_in, ctx)
    if opcode == "OSR":
      return self._execute_osr(operands, condition_in, ctx)
    if opcode == "OTE":
      ctx.set_value(operands[0], bool(condition_in))
      return bool(condition_in)
    if opcode == "OTL":
      if condition_in:
        ctx.set_value(operands[0], True)
      return bool(condition_in)
    if opcode == "OTU":
      if condition_in:
        ctx.set_value(operands[0], False)
      return bool(condition_in)
    if opcode == "MOV":
      if condition_in:
        ctx.set_value(operands[1], _deep_copy(ctx.resolve_operand(operands[0])))
      return bool(condition_in)
    if opcode == "ADD":
      if condition_in:
        left = ctx.resolve_operand(operands[0])
        right = ctx.resolve_operand(operands[1])
        ctx.set_value(operands[2], left + right)
      return bool(condition_in)
    if opcode == "CPT":
      if condition_in:
        result = self.expression_evaluator.evaluate(operands[1], ctx)
        ctx.set_value(operands[0], result)
      return bool(condition_in)
    if opcode == "TON":
      self._execute_ton(operands[0], bool(condition_in), ctx)
      return bool(condition_in)
    if opcode == "RES":
      if condition_in:
        self._reset_structure(operands[0], ctx)
      return bool(condition_in)
    if opcode == "COP":
      if condition_in:
        values = self._read_block(operands[0], _coerce_int(ctx.resolve_operand(operands[2])), ctx)
        self._write_block(operands[1], values, ctx)
      return bool(condition_in)
    if opcode == "FLL":
      if condition_in:
        fill_value = ctx.resolve_operand(operands[0])
        count = _coerce_int(ctx.resolve_operand(operands[2]))
        self._write_block(operands[1], [_deep_copy(fill_value) for _ in range(count)], ctx, fill_mode=True)
      return bool(condition_in)
    if opcode == "FFL":
      if condition_in:
        self._execute_ffl(operands, ctx)
      else:
        self._set_control_enabled(operands[2], False, ctx)
      return bool(condition_in)
    if opcode == "FFU":
      if condition_in:
        self._execute_ffu(operands, ctx)
      else:
        self._set_control_enabled(operands[2], False, ctx)
      return bool(condition_in)
    if opcode == "JSR":
      if condition_in:
        target = self._resolve_jsr_target(operands[0], ctx)
        if target is not None:
          target(ctx)
      return bool(condition_in)
    if opcode == "JMP":
      if condition_in:
        raise _RoutineJump(operands[0])
      return bool(condition_in)
    if opcode == "LBL":
      return bool(condition_in)
    if opcode == "NOP":
      return bool(condition_in)
    if opcode == "MSO":
      if condition_in:
        self._servo_on(operands[0], operands[1], ctx)
      return bool(condition_in)
    if opcode == "MSF":
      if condition_in:
        self._servo_off(operands[0], operands[1], ctx)
      return bool(condition_in)
    if opcode == "MAFR":
      if condition_in:
        self._fault_reset(operands[0], operands[1], ctx)
      return bool(condition_in)
    if opcode == "MAS":
      if condition_in:
        self._stop_axis(operands[0], operands[1], ctx)
      return bool(condition_in)
    if opcode == "MCS":
      if condition_in:
        self._stop_coordinate(operands[0], operands[1], ctx)
      return bool(condition_in)
    if opcode == "MAM":
      if condition_in:
        self._start_axis_move(operands, ctx)
      else:
        self._disarm_motion_control(operands[1], ctx)
      return bool(condition_in)
    if opcode in {"MCLM", "MCCM"}:
      if condition_in:
        self._start_coordinate_move(opcode, operands, ctx)
      else:
        self._disarm_motion_control(operands[1], ctx)
      return bool(condition_in)
    if opcode == "MCCD":
      if condition_in:
        self._change_coordinate_dynamics(operands, ctx)
      return bool(condition_in)

    raise ValueError(f"Unsupported runtime opcode {opcode!r}")

  def _execute_compare(self, opcode: str, operands, condition_in: bool, ctx: ScanContext) -> bool:
    if not condition_in:
      return False
    left = ctx.resolve_operand(operands[0])
    right = ctx.resolve_operand(operands[1])
    if opcode == "EQU":
      return left == right
    if opcode == "NEQ":
      return left != right
    if opcode == "GEQ":
      return left >= right
    if opcode == "GRT":
      return left > right
    if opcode == "LEQ":
      return left <= right
    if opcode == "LES":
      return left < right
    return False

  def _execute_limit(self, operands, condition_in: bool, ctx: ScanContext) -> bool:
    if not condition_in:
      return False
    low = ctx.resolve_operand(operands[0])
    value = ctx.resolve_operand(operands[1])
    high = ctx.resolve_operand(operands[2])
    return low <= value <= high

  def _execute_ons(self, operands, condition_in: bool, ctx: ScanContext) -> bool:
    storage_path = operands[0]
    previous = _coerce_bool(ctx.get_value(storage_path))
    pulse = bool(condition_in) and not previous
    ctx.set_value(storage_path, bool(condition_in))
    if len(operands) > 1:
      ctx.set_value(operands[1], pulse)
    return pulse

  def _execute_osr(self, operands, condition_in: bool, ctx: ScanContext) -> bool:
    storage_path = operands[0]
    output_path = operands[1]
    previous = _coerce_bool(ctx.get_value(storage_path))
    pulse = bool(condition_in) and not previous
    ctx.set_value(storage_path, bool(condition_in))
    ctx.set_value(output_path, pulse)
    return pulse

  def _execute_ton(self, timer_path: str, condition_in: bool, ctx: ScanContext):
    timer = _deep_copy(ctx.get_value(timer_path))
    timer["EN"] = bool(condition_in)
    if condition_in:
      timer["ACC"] = int(timer.get("ACC", 0)) + int(ctx.runtime_state.scan_time_ms)
      timer["DN"] = int(timer.get("ACC", 0)) >= int(timer.get("PRE", 0))
      if timer["DN"]:
        timer["ACC"] = max(int(timer.get("ACC", 0)), int(timer.get("PRE", 0)))
      timer["TT"] = bool(timer["EN"]) and not bool(timer["DN"])
    else:
      timer["ACC"] = 0
      timer["TT"] = False
      timer["DN"] = False
    ctx.set_value(timer_path, timer)

  def _reset_structure(self, path: str, ctx: ScanContext):
    value = _deep_copy(ctx.get_value(path))
    if isinstance(value, dict) and {"PRE", "ACC", "EN", "TT", "DN"} <= set(value):
      value["ACC"] = 0
      value["EN"] = False
      value["TT"] = False
      value["DN"] = False
      ctx.set_value(path, value)
      return
    if isinstance(value, dict) and {"LEN", "POS", "EN", "EU", "DN", "EM", "ER", "UL", "IN", "FD"} <= set(value):
      value["POS"] = 0
      value["EN"] = False
      value["EU"] = False
      value["DN"] = False
      value["EM"] = True
      value["ER"] = False
      value["UL"] = False
      value["IN"] = False
      value["FD"] = False
      ctx.set_value(path, value)
      return
    if isinstance(value, dict) and {"EN", "DN", "ER", "PC", "IP", "ERR", "EXERR"} <= set(value):
      preserved_flags = value.get("FLAGS", 0)
      value = _zero_like(value)
      value["FLAGS"] = preserved_flags
      ctx.set_value(path, value)
      return
    ctx.set_value(path, _zero_like(value))

  def _read_block(self, path: str, count: int, ctx: ScanContext):
    if count <= 1:
      return [_deep_copy(ctx.get_value(path))]

    parent_path, start_index = self._array_parent(path)
    array = _deep_copy(ctx.get_value(parent_path))
    return [_deep_copy(array[start_index + offset]) for offset in range(count)]

  def _write_block(self, path: str, values, ctx: ScanContext, fill_mode: bool = False):
    if len(values) <= 1 and not fill_mode:
      ctx.set_value(path, _deep_copy(values[0]))
      return

    parent_path, start_index = self._array_parent(path)
    array = _deep_copy(ctx.get_value(parent_path))
    template = array[start_index] if start_index < len(array) else 0
    for offset, value in enumerate(values):
      if start_index + offset >= len(array):
        break
      item = _zero_like(template) if fill_mode and value == 0 else _deep_copy(value)
      if fill_mode and value == 0 and isinstance(template, (dict, list, PLCStruct)):
        item = _zero_like(template)
      array[start_index + offset] = item
    ctx.set_value(parent_path, array)

  def _array_parent(self, path: str) -> tuple[str, int]:
    segments = list(split_tag_path(path))
    if not segments:
      raise KeyError(path)
    final = segments[-1]
    if not final.indexes:
      raise KeyError(path)
    start_index = int(final.indexes[-1])
    segments[-1] = PathSegment(final.name, final.indexes[:-1])
    parent_path = _path_to_string(tuple(segments)).rstrip(".")
    return parent_path, start_index

  def _execute_ffl(self, operands, ctx: ScanContext):
    source_path, array_path, control_path = operands[:3]
    control = _deep_copy(ctx.get_value(control_path))
    array = _deep_copy(ctx.get_value(self._array_parent(array_path)[0]))
    position = int(control.get("POS", 0))
    length = int(control.get("LEN", len(array)))
    control["EN"] = True
    control["IN"] = True
    control["EU"] = True
    control["UL"] = False
    if position < min(length, len(array)):
      array[position] = _deep_copy(ctx.get_value(source_path))
      position += 1
    control["POS"] = position
    control["DN"] = position >= length
    control["EM"] = position == 0
    ctx.set_value(self._array_parent(array_path)[0], array)
    ctx.set_value(control_path, control)

  def _execute_ffu(self, operands, ctx: ScanContext):
    array_path, dest_path, control_path = operands[:3]
    parent_path, _ = self._array_parent(array_path)
    control = _deep_copy(ctx.get_value(control_path))
    array = _deep_copy(ctx.get_value(parent_path))
    position = int(control.get("POS", 0))
    control["EN"] = True
    control["IN"] = True
    control["EU"] = False
    control["UL"] = True
    if position > 0 and array:
      ctx.set_value(dest_path, _deep_copy(array[0]))
      zero_value = _zero_like(array[0])
      for index in range(position - 1):
        array[index] = _deep_copy(array[index + 1])
      array[position - 1] = zero_value
      position -= 1
    control["POS"] = position
    control["DN"] = False
    control["EM"] = position == 0
    ctx.set_value(parent_path, array)
    ctx.set_value(control_path, control)

  def _set_control_enabled(self, control_path: str, enabled: bool, ctx: ScanContext):
    control = _deep_copy(ctx.get_value(control_path))
    control["EN"] = bool(enabled)
    control["IN"] = bool(enabled)
    ctx.set_value(control_path, control)

  def _resolve_jsr_target(self, routine_name: str, ctx: ScanContext):
    if ctx.current_program is not None:
      qualified = ctx.jsr_registry.resolve(f"{ctx.current_program}:{routine_name}")
      if qualified is not None:
        return qualified
    return ctx.jsr_registry.resolve(routine_name)

  def _servo_on(self, axis_path: str, control_path: str, ctx: ScanContext):
    axis = _deep_copy(ctx.get_value(axis_path))
    axis["DriveEnableStatus"] = True
    ctx.set_value(axis_path, axis)
    control = _deep_copy(ctx.get_value(control_path))
    control["EN"] = True
    control["DN"] = True
    control["PC"] = True
    control["IP"] = False
    control["ER"] = False
    ctx.set_value(control_path, control)

  def _servo_off(self, axis_path: str, control_path: str, ctx: ScanContext):
    axis = _deep_copy(ctx.get_value(axis_path))
    axis["DriveEnableStatus"] = False
    axis["CoordinatedMotionStatus"] = False
    ctx.set_value(axis_path, axis)
    control = _deep_copy(ctx.get_value(control_path))
    control["EN"] = True
    control["DN"] = True
    control["PC"] = True
    control["IP"] = False
    control["ER"] = False
    ctx.set_value(control_path, control)

  def _fault_reset(self, axis_path: str, control_path: str, ctx: ScanContext):
    axis = _deep_copy(ctx.get_value(axis_path))
    axis["PhysicalAxisFault"] = False
    axis["ModuleFault"] = False
    axis["MotionFault"] = False
    ctx.set_value(axis_path, axis)
    control = _deep_copy(ctx.get_value(control_path))
    control["DN"] = True
    control["PC"] = True
    control["IP"] = False
    control["ER"] = False
    ctx.set_value(control_path, control)

  def _stop_axis(self, axis_path: str, control_path: str, ctx: ScanContext):
    ctx.runtime_state.axis_moves.pop(axis_path, None)
    axis = _deep_copy(ctx.get_value(axis_path))
    axis["ActualVelocity"] = 0.0
    axis["CommandAcceleration"] = 0.0
    axis["CoordinatedMotionStatus"] = False
    ctx.set_value(axis_path, axis)
    control = _deep_copy(ctx.get_value(control_path))
    control["PC"] = True
    control["DN"] = True
    control["IP"] = False
    ctx.set_value(control_path, control)

  def _stop_coordinate(self, coordinate_path: str, control_path: str, ctx: ScanContext):
    active = ctx.runtime_state.coordinate_moves.pop(coordinate_path, None)
    pending = ctx.runtime_state.coordinate_pending_moves.pop(coordinate_path, None)
    for motion in (active, pending):
      if motion is None:
        continue
      motion_control = _deep_copy(ctx.get_value(motion.control_path))
      motion_control["IP"] = False
      motion_control["PC"] = True
      motion_control["DN"] = True
      ctx.set_value(motion.control_path, motion_control)
      self._clear_component_velocities(motion.component_paths, ctx)

    coordinate = _deep_copy(ctx.get_value(coordinate_path))
    coordinate["MovePendingStatus"] = False
    coordinate["MovePendingQueueFullStatus"] = False
    coordinate["MoveStatus"] = False
    coordinate["MotionStatus"] = False
    coordinate["StoppingStatus"] = True
    ctx.set_value(coordinate_path, coordinate)

    control = _deep_copy(ctx.get_value(control_path))
    control["PC"] = True
    control["DN"] = True
    control["IP"] = False
    ctx.set_value(control_path, control)

  def _start_axis_move(self, operands, ctx: ScanContext):
    axis_path = operands[0]
    control_path = operands[1]
    control = _deep_copy(ctx.get_value(control_path))
    if control.get("EN"):
      return
    existing = ctx.runtime_state.axis_moves.get(axis_path)
    if existing is not None and existing.control_path == control_path:
      return
    target = _coerce_float(ctx.resolve_operand(operands[3]))
    speed = max(_coerce_float(ctx.resolve_operand(operands[4])), 1e-6)
    acceleration = _coerce_float(ctx.resolve_operand(operands[6]))
    component_path = f"{axis_path}.ActualPosition"
    start_position = _coerce_float(ctx.get_value(component_path))
    scans = self._motion_scan_count(abs(target - start_position), speed, ctx)

    control["EN"] = True
    control["DN"] = False
    control["ER"] = False
    control["PC"] = False
    control["IP"] = True
    ctx.set_value(control_path, control)

    axis = _deep_copy(ctx.get_value(axis_path))
    axis["CommandAcceleration"] = acceleration
    axis["ActualVelocity"] = speed if target >= start_position else -speed
    axis["MoveStatus"] = True
    ctx.set_value(axis_path, axis)

    ctx.runtime_state.axis_moves[axis_path] = ActiveMotion(
      control_path=control_path,
      component_paths=(component_path,),
      start_positions=(start_position,),
      target_positions=(target,),
      speed=speed,
      acceleration=acceleration,
      total_scans=scans,
      remaining_scans=scans,
      axis_paths=(axis_path,),
      command_name="MAM",
    )

  def _start_coordinate_move(self, opcode: str, operands, ctx: ScanContext):
    coordinate_path = operands[0]
    control_path = operands[1]
    control = _deep_copy(ctx.get_value(control_path))
    if control.get("EN"):
      return
    active_motion = ctx.runtime_state.coordinate_moves.get(coordinate_path)
    if active_motion is not None and active_motion.control_path == control_path:
      return
    pending_motion = ctx.runtime_state.coordinate_pending_moves.get(coordinate_path)
    if pending_motion is not None and pending_motion.control_path == control_path:
      return
    target_paths = self._coordinate_component_paths(coordinate_path)
    target_positions = self._resolve_coordinate_target(coordinate_path, operands[3], ctx)
    speed_index = 6 if opcode == "MCCM" else 4
    accel_index = 8 if opcode == "MCCM" else 6
    speed = max(_coerce_float(ctx.resolve_operand(operands[speed_index])), 1e-6)
    acceleration = _coerce_float(ctx.resolve_operand(operands[accel_index]))
    start_positions = tuple(_coerce_float(ctx.get_value(path)) for path in target_paths)
    distance = math.sqrt(
      sum((target - start) * (target - start) for start, target in zip(start_positions, target_positions))
    )
    scans = self._motion_scan_count(distance, speed, ctx)

    control["EN"] = True
    control["DN"] = False
    control["ER"] = False
    control["PC"] = False
    control["IP"] = True
    ctx.set_value(control_path, control)

    coordinate = _deep_copy(ctx.get_value(coordinate_path))
    coordinate["MoveStatus"] = True
    coordinate["MotionStatus"] = True

    motion = ActiveMotion(
      control_path=control_path,
      component_paths=target_paths,
      start_positions=start_positions,
      target_positions=target_positions,
      speed=speed,
      acceleration=acceleration,
      total_scans=scans,
      remaining_scans=scans,
      axis_paths=self._coordinate_axis_paths(coordinate_path),
      coordinate_path=coordinate_path,
      command_name=opcode,
      direction=_coerce_int(ctx.resolve_operand(operands[6])) if opcode == "MCCM" else None,
    )

    if coordinate_path in ctx.runtime_state.coordinate_moves:
      coordinate["MovePendingStatus"] = True
      coordinate["MovePendingQueueFullStatus"] = coordinate_path in ctx.runtime_state.coordinate_pending_moves
      motion.pending = True
      ctx.runtime_state.coordinate_pending_moves[coordinate_path] = motion
    else:
      coordinate["MovePendingStatus"] = False
      coordinate["MovePendingQueueFullStatus"] = False
      ctx.runtime_state.coordinate_moves[coordinate_path] = motion
      self._apply_motion_velocities(motion, ctx)
    ctx.set_value(coordinate_path, coordinate)

  def _change_coordinate_dynamics(self, operands, ctx: ScanContext):
    coordinate_path = operands[0]
    speed = _coerce_float(ctx.resolve_operand(operands[4]))
    acceleration = _coerce_float(ctx.resolve_operand(operands[7]))
    motion = ctx.runtime_state.coordinate_moves.get(coordinate_path)
    if motion is None:
      return
    motion.speed = max(speed, 1e-6)
    motion.acceleration = acceleration
    self._apply_motion_velocities(motion, ctx)

  def _disarm_motion_control(self, control_path: str, ctx: ScanContext):
    control = _deep_copy(ctx.get_value(control_path))
    control["EN"] = False
    ctx.set_value(control_path, control)

  def _motion_scan_count(self, distance: float, speed: float, ctx: ScanContext) -> int:
    travel_time = distance / max(speed, 1e-6)
    return max(1, int(math.ceil(travel_time / max(ctx.scan_dt_seconds, 1e-6))))

  def _coordinate_component_paths(self, coordinate_path: str) -> tuple[str, ...]:
    if coordinate_path == "X_Y":
      return ("X_axis.ActualPosition", "Y_axis.ActualPosition")
    if coordinate_path == "xz":
      return ("X_axis.ActualPosition", "Z_axis.ActualPosition")
    return ("X_axis.ActualPosition", "Y_axis.ActualPosition")

  def _coordinate_axis_paths(self, coordinate_path: str) -> tuple[str, ...]:
    if coordinate_path == "X_Y":
      return ("X_axis", "Y_axis")
    if coordinate_path == "xz":
      return ("X_axis", "Z_axis")
    return ("X_axis", "Y_axis")

  def _resolve_coordinate_target(self, coordinate_path: str, operand: str, ctx: ScanContext) -> tuple[float, ...]:
    path = str(operand)
    value = ctx.resolve_operand(path)
    if isinstance(value, list):
      return tuple(_coerce_float(item) for item in value[:2])

    if path.endswith("[0]"):
      root_path = path[:-3]
      root_value = ctx.get_value(root_path)
      if isinstance(root_value, list):
        return tuple(_coerce_float(item) for item in root_value[:2])

    if coordinate_path == "X_Y" and ctx.exists("X_POSITION") and ctx.exists("Y_POSITION"):
      return (
        _coerce_float(ctx.get_value("X_POSITION")),
        _coerce_float(ctx.get_value("Y_POSITION")),
      )
    if coordinate_path == "xz" and ctx.exists("xz_position_target"):
      target = ctx.get_value("xz_position_target")
      return tuple(_coerce_float(item) for item in target[:2])

    raise KeyError(f"Cannot resolve coordinate target from {operand!r}")

  def _apply_motion_velocities(self, motion: ActiveMotion, ctx: ScanContext):
    remaining_time = max(motion.remaining_scans, 1) * max(ctx.scan_dt_seconds, 1e-6)
    for axis_path, component_path, start, target in zip(
      motion.axis_paths,
      motion.component_paths,
      motion.start_positions,
      motion.target_positions,
    ):
      velocity = (target - start) / remaining_time
      axis = _deep_copy(ctx.get_value(axis_path))
      axis["ActualVelocity"] = velocity
      axis["CommandAcceleration"] = motion.acceleration
      axis["CoordinatedMotionStatus"] = True
      axis["MoveStatus"] = True
      ctx.set_value(axis_path, axis)

    if motion.coordinate_path is not None:
      coordinate = _deep_copy(ctx.get_value(motion.coordinate_path))
      coordinate["MoveStatus"] = True
      coordinate["MotionStatus"] = True
      coordinate["StoppingStatus"] = False
      ctx.set_value(motion.coordinate_path, coordinate)

  def _clear_component_velocities(self, component_paths: tuple[str, ...], ctx: ScanContext):
    for component_path in component_paths:
      if component_path.startswith("X_axis."):
        axis_path = "X_axis"
      elif component_path.startswith("Y_axis."):
        axis_path = "Y_axis"
      else:
        axis_path = "Z_axis"
      axis = _deep_copy(ctx.get_value(axis_path))
      axis["ActualVelocity"] = 0.0
      axis["CommandAcceleration"] = 0.0
      axis["CoordinatedMotionStatus"] = False
      axis["MoveStatus"] = False
      ctx.set_value(axis_path, axis)

  def _advance_axis_moves(self, ctx: ScanContext):
    completed = []
    for axis_path, motion in ctx.runtime_state.axis_moves.items():
      motion.remaining_scans -= 1
      progress = 1.0 - max(motion.remaining_scans, 0) / max(motion.total_scans, 1)
      position = motion.start_positions[0] + (
        (motion.target_positions[0] - motion.start_positions[0]) * progress
      )
      ctx.set_value(motion.component_paths[0], position)
      if motion.remaining_scans <= 0:
        self._finish_motion(motion, ctx)
        completed.append(axis_path)
    for axis_path in completed:
      ctx.runtime_state.axis_moves.pop(axis_path, None)

  def _advance_coordinate_moves(self, ctx: ScanContext):
    completed = []
    for coordinate_path, motion in ctx.runtime_state.coordinate_moves.items():
      motion.remaining_scans -= 1
      progress = 1.0 - max(motion.remaining_scans, 0) / max(motion.total_scans, 1)
      for component_path, start, target in zip(
        motion.component_paths,
        motion.start_positions,
        motion.target_positions,
      ):
        value = start + ((target - start) * progress)
        ctx.set_value(component_path, value)

      if motion.remaining_scans <= 0:
        self._finish_motion(motion, ctx)
        completed.append(coordinate_path)

    for coordinate_path in completed:
      ctx.runtime_state.coordinate_moves.pop(coordinate_path, None)
      pending = ctx.runtime_state.coordinate_pending_moves.pop(coordinate_path, None)
      coordinate = _deep_copy(ctx.get_value(coordinate_path))
      if pending is None:
        coordinate["MovePendingStatus"] = False
        coordinate["MovePendingQueueFullStatus"] = False
        coordinate["MoveStatus"] = False
        coordinate["MotionStatus"] = False
        ctx.set_value(coordinate_path, coordinate)
        continue

      pending.pending = False
      coordinate["MovePendingStatus"] = False
      coordinate["MovePendingQueueFullStatus"] = False
      ctx.set_value(coordinate_path, coordinate)
      ctx.runtime_state.coordinate_moves[coordinate_path] = pending
      self._apply_motion_velocities(pending, ctx)

  def _finish_motion(self, motion: ActiveMotion, ctx: ScanContext):
    for component_path, target in zip(motion.component_paths, motion.target_positions):
      ctx.set_value(component_path, target)

    control = _deep_copy(ctx.get_value(motion.control_path))
    control["IP"] = False
    control["PC"] = True
    control["DN"] = True
    control["ER"] = False
    ctx.set_value(motion.control_path, control)

    self._clear_component_velocities(motion.component_paths, ctx)
    for axis_path in motion.axis_paths:
      axis = _deep_copy(ctx.get_value(axis_path))
      axis["ActualPosition"] = ctx.get_value(f"{axis_path}.ActualPosition")
      ctx.set_value(axis_path, axis)
