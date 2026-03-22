from __future__ import annotations

import re

from .ast import Branch
from .ast import InstructionCall
from .ast import Node
from .ast import Rung
from .ast import Routine
from .codegen_support import load_routine_from_source
from .emitter import RllEmitter


NUMERIC_PATTERN = re.compile(
  r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$"
)
VALID_PATH_PATTERN = re.compile(
  r"^[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]+\])*(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]+\])*)*$"
)
IDENTIFIER_PATTERN = re.compile(
  r"(?<![A-Za-z0-9_.])"
  r"([A-Za-z_][A-Za-z0-9_:]*(?:\[[^\]]+\])*(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]+\])*)*)"
)
STRING_LITERAL_PATTERN = re.compile(r'"[^"]*"')

FORMULA_NAME_MAP = {
  "ABS": "abs",
  "ATN": "atan",
  "COS": "cos",
  "MOD": "fmod",
  "SIN": "sin",
  "SQR": "sqrt",
}

PREDICATE_OPERATORS = {
  "EQU": "==",
  "NEQ": "!=",
  "GEQ": ">=",
  "GRT": ">",
  "LEQ": "<=",
  "LES": "<",
}

NAMED_ARGUMENTS = {
  "MAFR": ("axis", "motion_control"),
  "MAM": (
    "axis",
    "motion_control",
    "move_type",
    "target",
    "speed",
    "speed_units",
    "accel",
    "accel_units",
    "decel",
    "decel_units",
    "profile",
    "accel_jerk",
    "decel_jerk",
    "jerk_units",
    "merge",
    "merge_speed",
    "lock_position",
    "lock_direction",
    "event_distance",
    "calculated_data",
  ),
  "MAS": (
    "axis",
    "motion_control",
    "stop_type",
    "change_decel",
    "decel",
    "decel_units",
    "change_jerk",
    "jerk",
    "jerk_units",
  ),
  "MCCM": (
    "coordinate_system",
    "motion_control",
    "move_type",
    "end_position",
    "circle_type",
    "via_or_center",
    "direction",
    "speed",
    "speed_units",
    "accel",
    "accel_units",
    "decel",
    "decel_units",
    "profile",
    "accel_jerk",
    "decel_jerk",
    "jerk_units",
    "termination_type",
    "merge",
    "merge_speed",
    "command_tolerance",
    "lock_position",
    "lock_direction",
    "event_distance",
    "calculated_data",
  ),
  "MCCD": (
    "coordinate_system",
    "motion_control",
    "scope",
    "speed_enable",
    "speed",
    "speed_units",
    "accel_enable",
    "accel",
    "accel_units",
    "decel_enable",
    "decel",
    "decel_units",
    "accel_jerk_enable",
    "accel_jerk",
    "decel_jerk_enable",
    "decel_jerk",
    "jerk_units",
    "apply_to",
  ),
  "MCLM": (
    "coordinate_system",
    "motion_control",
    "move_type",
    "target",
    "speed",
    "speed_units",
    "accel",
    "accel_units",
    "decel",
    "decel_units",
    "profile",
    "accel_jerk",
    "decel_jerk",
    "jerk_units",
    "termination_type",
    "merge",
    "merge_speed",
    "command_tolerance",
    "lock_position",
    "lock_direction",
    "event_distance",
    "calculated_data",
  ),
  "MCS": (
    "coordinate_system",
    "motion_control",
    "stop_type",
    "change_decel",
    "decel",
    "decel_units",
    "change_jerk",
    "jerk",
    "jerk_units",
  ),
  "MSF": ("axis", "motion_control"),
  "MSO": ("axis", "motion_control"),
  "OSF": ("storage_bit", "output_bit", "rung_in"),
  "OSR": ("storage_bit", "output_bit", "rung_in"),
  "PID": (
    "control_block",
    "process_variable",
    "tieback",
    "control_variable",
    "feedforward",
    "alarm_disable",
    "hold",
  ),
  "SFX": (
    "control_tag",
    "time_units",
    "home_window",
    "home_speed",
    "home_accel",
    "home_decel",
    "feedback_position",
    "feedback_velocity",
    "valid_bit",
    "fault_bit",
    "home_trigger",
    "reset",
    "homed_status",
    "fault_status",
  ),
  "SLS": (
    "control_tag",
    "mode_a",
    "mode_b",
    "speed_limit",
    "active_limit",
    "feedback_tag",
    "request_bit",
    "reset_bit",
    "active_status",
    "limit_status",
    "fault_status",
  ),
  "TON": ("timer_tag", "preset", "accum", "rung_in"),
}


class StructuredPythonCodeGenerator:
  def generate_routine(self, routine: Routine) -> str:
    imports = ", ".join(self._imports_for(routine))
    routine_name = self._python_name(routine)
    lines = [
      f"from dune_winder.plc_ladder.codegen_support import {imports}",
      "",
      "",
      f"{routine_name} = ROUTINE(",
      f"  name={routine.name!r},",
    ]
    if routine.program is not None:
      lines.append(f"  program={routine.program!r},")
    if routine.source_path is not None:
      lines.append(f"  source_path={str(routine.source_path)!r},")

    lines.append("  rungs=(")
    for rung in routine.rungs:
      lines.append("    RUNG(")
      for rendered in self._render_rung_nodes(rung):
        lines.append("      " + rendered)
      lines.append("    ),")
    lines.append("  ),")
    lines.append(")")
    return "\n".join(lines) + "\n"

  def _python_name(self, routine: Routine) -> str:
    parts = []
    if routine.program:
      parts.append(routine.program)
    parts.append(routine.name)
    text = "_".join(parts)
    return "".join(character if character.isalnum() else "_" for character in text)

  def _render_rung_nodes(self, rung: Rung):
    rendered = []
    for node in rung.nodes:
      rendered.append(self._render_node(node) + ",")
    return rendered

  def _imports_for(self, routine: Routine) -> tuple[str, ...]:
    imports = {"BRANCH", "ROUTINE", "RUNG"}
    for rung in routine.rungs:
      self._collect_imports(rung.nodes, imports)
    return tuple(sorted(imports))

  def _collect_imports(self, nodes: tuple[Node, ...], imports: set[str]):
    for node in nodes:
      if isinstance(node, InstructionCall):
        imports.add(node.opcode)
        continue
      if isinstance(node, Branch):
        imports.add("BRANCH")
        for branch in node.branches:
          self._collect_imports(branch, imports)
        continue
      raise TypeError(f"Unsupported AST node: {type(node)!r}")

  def _render_node(self, node: Node) -> str:
    if isinstance(node, InstructionCall):
      if not node.operands:
        return f"{node.opcode}()"
      operand_list = ", ".join(repr(operand) for operand in node.operands)
      return f"{node.opcode}({operand_list})"
    if isinstance(node, Branch):
      branch_text = ", ".join(
        "[" + ", ".join(self._render_node(child) for child in branch) + "]"
        for branch in node.branches
      )
      return f"BRANCH({branch_text})"
    raise TypeError(f"Unsupported AST node: {type(node)!r}")


class PythonCodeGenerator:
  def __init__(self):
    self._emitter = RllEmitter()
    self._temp_counter = 0

  def generate_routine(self, routine: Routine) -> str:
    self._assert_supported(routine)
    self._temp_counter = 0

    lines = []
    imports = self._math_imports_for(routine)
    if imports:
      lines.append(f"from math import {', '.join(imports)}")
      lines.append("")

    for index, rung in enumerate(routine.rungs):
      if index:
        lines.append("")
      lines.append(f"# rung {index}")
      lines.append(f"# {self._emitter.emit_rung(rung).strip()}")
      rung_lines, _ = self._lower_nodes(rung.nodes, [], 0)
      if rung_lines:
        lines.extend(rung_lines)
      else:
        lines.append("pass")

    return "\n".join(lines) + "\n"

  def _assert_supported(self, routine: Routine):
    unsupported = set()
    for rung in routine.rungs:
      self._collect_unsupported(rung.nodes, unsupported)
    if unsupported:
      items = ", ".join(sorted(unsupported))
      raise NotImplementedError(
        f"Imperative ladder translation does not support {items} in routine {routine.name!r}"
      )

  def _collect_unsupported(self, nodes: tuple[Node, ...], unsupported: set[str]):
    for node in nodes:
      if isinstance(node, Branch):
        for branch in node.branches:
          self._collect_unsupported(branch, unsupported)
        continue
      if node.opcode in {"JMP", "LBL"}:
        unsupported.add(node.opcode)

  def _math_imports_for(self, routine: Routine) -> tuple[str, ...]:
    imports = set()
    for rung in routine.rungs:
      self._collect_math_imports(rung.nodes, imports)
    return tuple(sorted(imports))

  def _collect_math_imports(self, nodes: tuple[Node, ...], imports: set[str]):
    for node in nodes:
      if isinstance(node, Branch):
        for branch in node.branches:
          self._collect_math_imports(branch, imports)
        continue
      if node.opcode == "TRN":
        imports.add("trunc")
      if node.opcode == "MOD":
        imports.add("fmod")
      for operand in node.operands:
        text = str(operand)
        if "ATN(" in text:
          imports.add("atan")
        if "COS(" in text:
          imports.add("cos")
        if "MOD(" in text:
          imports.add("fmod")
        if "SIN(" in text:
          imports.add("sin")
        if "SQR(" in text:
          imports.add("sqrt")

  def _lower_nodes(self, nodes: tuple[Node, ...], clauses: list[str], indent: int):
    lines = []
    current_clauses = list(clauses)
    for node in nodes:
      if isinstance(node, Branch):
        branch_lines, current_clauses = self._lower_branch(node, current_clauses, indent)
        lines.extend(branch_lines)
        continue
      instruction_lines, current_clauses = self._lower_instruction(node, current_clauses, indent)
      lines.extend(instruction_lines)
    return lines, current_clauses

  def _lower_branch(self, branch: Branch, input_clauses: list[str], indent: int):
    local_branch_lines = []
    local_branch_vars = []
    full_branch_lines = []
    full_branch_vars = []
    all_local = True

    for branch_nodes in branch.branches:
      branch_lines, branch_clauses = self._lower_nodes(branch_nodes, list(input_clauses), indent)
      local_branch_lines.extend(branch_lines)
      full_branch_lines.extend(branch_lines)

      local_clauses = self._strip_prefix(input_clauses, branch_clauses)
      if local_clauses is None:
        all_local = False
      else:
        branch_var = self._next_temp("branch")
        local_branch_lines.append(
          self._indent(indent) + f"{branch_var} = bool({self._clauses_to_expr(local_clauses)})"
        )
        local_branch_vars.append(branch_var)

      full_branch_var = self._next_temp("branch")
      full_branch_lines.append(
        self._indent(indent) + f"{full_branch_var} = bool({self._clauses_to_expr(branch_clauses)})"
      )
      full_branch_vars.append(full_branch_var)

    branch_out = self._next_temp("branch")
    if all_local:
      local_branch_lines.append(
        self._indent(indent) + f"{branch_out} = {' or '.join(local_branch_vars) if local_branch_vars else 'False'}"
      )
      return local_branch_lines, input_clauses + [branch_out]

    full_branch_lines.append(
      self._indent(indent) + f"{branch_out} = {' or '.join(full_branch_vars) if full_branch_vars else 'False'}"
    )
    return full_branch_lines, [branch_out]

  def _strip_prefix(self, prefix: list[str], clauses: list[str]) -> list[str] | None:
    if len(clauses) < len(prefix):
      return None
    if clauses[:len(prefix)] != prefix:
      return None
    local = clauses[len(prefix):]
    return local or ["True"]

  def _lower_instruction(self, instruction: InstructionCall, clauses: list[str], indent: int):
    opcode = instruction.opcode
    operands = instruction.operands

    if opcode in {"AFI", "CMP", "EQU", "GEQ", "GRT", "LEQ", "LES", "LIM", "NEQ", "XIC", "XIO"}:
      return [], clauses + [self._render_predicate(opcode, operands)]

    if opcode == "OTE":
      return [self._indent(indent) + self._render_output_energize(operands[0], clauses)], clauses

    if opcode in {"ONS", "OSF", "OSR"}:
      pulse_name = self._next_temp("pulse")
      call_lines = self._render_call_lines(
        opcode,
        keyword_items=(
          ("storage_bit", self._render_value(operands[0])),
          *((("output_bit", self._render_value(operands[1])),) if len(operands) > 1 else ()),
          ("rung_in", self._clauses_to_expr(clauses)),
        ),
      )
      lines = [self._indent(indent) + f"{pulse_name} = {call_lines[0]}"]
      lines.extend(self._indent(indent) + line for line in call_lines[1:])
      return lines, [pulse_name]

    if opcode == "TON":
      call_lines = self._render_call_lines(
        opcode,
        keyword_items=(
          ("timer_tag", self._render_value(operands[0])),
          ("preset", self._render_value(operands[1])),
          ("accum", self._render_value(operands[2])),
          ("rung_in", self._clauses_to_expr(clauses)),
        ),
      )
      return [self._indent(indent) + line for line in call_lines], clauses

    body_lines = self._render_instruction_body(opcode, operands)
    return self._guard_block(clauses, body_lines, indent), clauses

  def _render_predicate(self, opcode: str, operands: tuple[str, ...]) -> str:
    if opcode == "AFI":
      return "False"
    if opcode == "XIC":
      return self._render_value(operands[0])
    if opcode == "XIO":
      return f"not {self._render_value(operands[0])}"
    if opcode == "CMP":
      return self._render_formula(operands[0])
    if opcode == "LIM":
      low = self._render_value(operands[0])
      test = self._render_value(operands[1])
      high = self._render_value(operands[2])
      return f"{low} <= {test} <= {high}"
    operator = PREDICATE_OPERATORS[opcode]
    left = self._render_value(operands[0])
    right = self._render_value(operands[1])
    return f"{left} {operator} {right}"

  def _render_instruction_body(self, opcode: str, operands: tuple[str, ...]):
    if opcode == "ADD":
      return [self._render_assignment(operands[2], f"{self._render_value(operands[0])} + {self._render_value(operands[1])}")]
    if opcode == "CPT":
      return [self._render_assignment(operands[0], self._render_formula(operands[1]))]
    if opcode == "MOD":
      return [self._render_assignment(operands[2], f"fmod({self._render_value(operands[0])}, {self._render_value(operands[1])})")]
    if opcode == "MOV":
      return [self._render_assignment(operands[1], self._render_value(operands[0]))]
    if opcode == "OTL":
      return [self._render_assignment(operands[0], "True")]
    if opcode == "OTU":
      return [self._render_assignment(operands[0], "False")]
    if opcode == "TRN":
      return [self._render_assignment(operands[1], f"trunc({self._render_value(operands[0])})")]
    if opcode == "JSR":
      return self._render_jsr(operands)
    if opcode in NAMED_ARGUMENTS:
      keyword_items = tuple(
        (name, self._render_value(value))
        for name, value in zip(NAMED_ARGUMENTS[opcode], operands)
      )
      return self._render_call_lines(opcode, keyword_items=keyword_items)
    if opcode in {"COP", "FFL", "FFU", "FLL", "PID", "RES", "SFX", "SLS"}:
      return self._render_call_lines(opcode, positional=tuple(self._render_value(operand) for operand in operands))
    if not operands:
      return [f"{opcode}()"]
    return self._render_call_lines(opcode, positional=tuple(self._render_value(operand) for operand in operands))

  def _render_jsr(self, operands: tuple[str, ...]):
    routine_name = str(operands[0])
    if len(operands) > 1 and operands[1] != "0":
      return self._render_call_lines(
        "JSR",
        keyword_items=(
          ("routine", self._render_value(routine_name)),
          ("parameter_block", self._render_value(operands[1])),
        ),
      )
    if self._is_valid_python_identifier(routine_name):
      return [f"{routine_name}()"]
    return self._render_call_lines("JSR", keyword_items=(("routine", self._render_value(routine_name)),))

  def _render_output_energize(self, target: str, clauses: list[str]) -> str:
    return self._render_assignment(target, f"bool({self._clauses_to_expr(clauses)})")

  def _render_assignment(self, target: str, value: str) -> str:
    if self._is_valid_python_path(target):
      return f"{target} = {value}"
    return f"set_tag({target!r}, {value})"

  def _guard_block(self, clauses: list[str], body_lines: list[str], indent: int):
    active_clauses = [clause for clause in clauses if clause != "True"]
    if not active_clauses:
      return [self._indent(indent) + line for line in body_lines]

    lines = []
    current_indent = indent
    for clause in active_clauses:
      lines.append(self._indent(current_indent) + f"if {clause}:")
      current_indent += 1
    for line in body_lines:
      lines.append(self._indent(current_indent) + line)
    return lines

  def _clauses_to_expr(self, clauses: list[str]) -> str:
    active_clauses = [clause for clause in clauses if clause != "True"]
    if not active_clauses:
      return "True"
    if len(active_clauses) == 1:
      return active_clauses[0]
    return " and ".join(f"({clause})" for clause in active_clauses)

  def _render_formula(self, expression: str) -> str:
    placeholders: list[str] = []

    def protect_string(match: re.Match[str]) -> str:
      placeholders.append(match.group(0))
      return f"\uFFF0{len(placeholders) - 1}\uFFF1"

    transformed = STRING_LITERAL_PATTERN.sub(protect_string, str(expression))
    transformed = re.sub(r"<>", "!=", transformed)
    transformed = re.sub(r"(?<![<>=!])=(?!=)", "==", transformed)

    for rockwell_name, python_name in FORMULA_NAME_MAP.items():
      transformed = re.sub(
        rf"\b{rockwell_name}\s*(?=\()",
        python_name,
        transformed,
      )

    transformed = IDENTIFIER_PATTERN.sub(
      lambda match: self._replace_formula_identifier(match, transformed),
      transformed,
    )

    for index, original in enumerate(placeholders):
      transformed = transformed.replace(
        f"\uFFF0{index}\uFFF1",
        repr(original[1:-1]),
      )
    return transformed

  def _replace_formula_identifier(self, match: re.Match[str], text: str) -> str:
    identifier = match.group(1)
    end = match.end(1)
    if end < len(text) and text[end] == "(" and identifier in FORMULA_NAME_MAP.values():
      return identifier
    if identifier in {"and", "or", "not", "True", "False"}:
      return identifier
    return self._render_value(identifier)

  def _render_value(self, token: str) -> str:
    text = str(token)
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
      return repr(text[1:-1])
    if NUMERIC_PATTERN.fullmatch(text):
      return text
    if text.lower() in {"true", "false"}:
      return "True" if text.lower() == "true" else "False"
    if ":" not in text and any(character in text for character in {" ", "-", "%"}):
      return repr(text)
    if self._is_valid_python_path(text):
      return text
    return f"tag({text!r})"

  def _render_call_lines(
    self,
    name: str,
    *,
    positional: tuple[str, ...] = (),
    keyword_items: tuple[tuple[str, str], ...] = (),
  ) -> list[str]:
    if keyword_items:
      lines = [f"{name}("]
      for key, value in keyword_items:
        lines.append(f"  {key}={value},")
      lines.append(")")
      return lines

    if not positional:
      return [f"{name}()"]

    joined = ", ".join(positional)
    if len(joined) <= 60 and len(positional) <= 2:
      return [f"{name}({joined})"]

    lines = [f"{name}("]
    for value in positional:
      lines.append(f"  {value},")
    lines.append(")")
    return lines

  def _next_temp(self, prefix: str) -> str:
    name = f"_{prefix}_{self._temp_counter}"
    self._temp_counter += 1
    return name

  def _indent(self, indent: int) -> str:
    return "  " * indent

  def _is_valid_python_identifier(self, text: str) -> bool:
    return text.isidentifier()

  def _is_valid_python_path(self, text: str) -> bool:
    return bool(VALID_PATH_PATTERN.fullmatch(str(text)))


def transpile_routine_to_python(routine: Routine) -> str:
  return PythonCodeGenerator().generate_routine(routine)


def transpile_routine_to_structured_python(routine: Routine) -> str:
  return StructuredPythonCodeGenerator().generate_routine(routine)


def load_generated_routine(source: str, *, symbol_name: str | None = None) -> Routine:
  return load_routine_from_source(source, symbol_name=symbol_name)
