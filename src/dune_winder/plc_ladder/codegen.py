from __future__ import annotations

import re

from .ast import Branch
from .ast import InstructionCall
from .ast import Node
from .ast import Rung
from .ast import Routine
from .codegen_support import load_routine_from_source
from .emitter import RllEmitter
from .imperative import load_imperative_routine_from_source


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

REFERENCE_ARGUMENT_NAMES = {
  "accum",
  "active_limit",
  "active_status",
  "alarm_disable",
  "array",
  "axis",
  "control_block",
  "control_tag",
  "control_variable",
  "coordinate_system",
  "dest",
  "fault_bit",
  "fault_status",
  "feedback_position",
  "feedback_tag",
  "feedback_velocity",
  "feedforward",
  "hold",
  "home_trigger",
  "homed_status",
  "limit_status",
  "mode_a",
  "mode_b",
  "motion_control",
  "output_bit",
  "process_variable",
  "request_bit",
  "reset",
  "reset_bit",
  "source",
  "speed_limit",
  "storage_bit",
  "tieback",
  "timer_tag",
  "valid_bit",
}

LITERAL_ARGUMENT_NAMES = {
  "accel_enable",
  "accel_jerk_enable",
  "accel_units",
  "apply_to",
  "change_decel",
  "change_jerk",
  "decel_enable",
  "decel_jerk_enable",
  "decel_units",
  "jerk_units",
  "lock_direction",
  "merge",
  "merge_speed",
  "profile",
  "scope",
  "speed_enable",
  "speed_units",
  "stop_type",
  "time_units",
}

RUNG_IN_ARGUMENT_NAMES = {
  "FFL",
  "FFU",
  "MAM",
  "MCCM",
  "MCLM",
}

CANONICAL_LITERAL_ARGUMENT_VALUES = {
  "calculated_data": 0,
  "event_distance": 0,
  "lock_direction": "None",
  "lock_position": 0,
  "merge": None,
  "profile": None,
  "speed_units": "Units per sec",
  "accel_units": "Units per sec2",
  "decel_units": "Units per sec2",
  "jerk_units": "Units per sec3",
}

CANONICAL_PROFILE_VALUES = {
  "s-curve": "S-Curve",
  "scurve": "S-Curve",
  "trapezoidal": "Trapezoidal",
}

CANONICAL_MERGE_VALUES = {
  "disabled": "Disabled",
  "all": "All",
  "coordinated motion": "Coordinated motion",
}

VALID_TERMINATION_TYPES = frozenset(range(7))


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
    self._structured = StructuredPythonCodeGenerator()
    self._temp_counter = 0

  def generate_routine(self, routine: Routine) -> str:
    self._assert_supported(routine)
    self._temp_counter = 0

    lines = [
      "from dune_winder.plc_ladder.imperative import bind_scan_context",
    ]
    imports = self._math_imports_for(routine)
    if imports:
      lines.append("")
      lines.append(f"from math import {', '.join(imports)}")
    lines.append("")
    lines.extend(self._render_routine_metadata(routine))
    lines.append("")

    routine_name = self._structured._python_name(routine)
    lines.append(f"def {routine_name}(ctx):")
    lines.append("  api = bind_scan_context(ctx)")
    lines.append("  tag = api.tag")
    lines.append("  set_tag = api.set_tag")
    lines.append("  formula = api.formula")
    for helper_name in self._runtime_helpers_for(routine):
      lines.append(f"  {helper_name} = api.{helper_name}")
    if len(lines) > 0 and lines[-1] != "":
      lines.append("")

    for index, rung in enumerate(routine.rungs):
      lines.append(f"  # rung {index}")
      lines.append(f"  # {self._emitter.emit_rung(rung).strip()}")
      rung_lines, _ = self._lower_nodes(rung.nodes, [], 1)
      if rung_lines:
        lines.extend(rung_lines)
      else:
        lines.append("  pass")
      if index != len(routine.rungs) - 1:
        lines.append("")

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

  def _render_routine_metadata(self, routine: Routine) -> list[str]:
    structured_name = self._structured._python_name(routine)
    metadata_source = self._structured.generate_routine(routine)
    metadata_source = metadata_source.replace(
      f"{structured_name} = ROUTINE(",
      "__ladder_routine__ = ROUTINE(",
      1,
    )
    return metadata_source.rstrip().splitlines()

  def _runtime_helpers_for(self, routine: Routine) -> tuple[str, ...]:
    helpers = set()
    for rung in routine.rungs:
      self._collect_runtime_helpers(rung.nodes, helpers)
    return tuple(sorted(helpers))

  def _collect_runtime_helpers(self, nodes: tuple[Node, ...], helpers: set[str]):
    for node in nodes:
      if isinstance(node, Branch):
        for branch in node.branches:
          self._collect_runtime_helpers(branch, helpers)
        continue
      if node.opcode in {"AFI", "CMP", "EQU", "GEQ", "GRT", "LEQ", "LES", "LIM", "NEQ", "OTE", "XIC", "XIO"}:
        continue
      helpers.add(node.opcode)

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
          ("storage_bit", self._render_path_argument(operands[0])),
          *((("output_bit", self._render_path_argument(operands[1])),) if len(operands) > 1 else ()),
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
          ("timer_tag", self._render_path_argument(operands[0])),
          ("preset", self._render_literal(operands[1])),
          ("accum", self._render_literal(operands[2])),
          ("rung_in", self._clauses_to_expr(clauses)),
        ),
      )
      return [self._indent(indent) + line for line in call_lines], clauses

    if opcode in RUNG_IN_ARGUMENT_NAMES:
      body_lines = self._render_instruction_body(opcode, operands, rung_in=self._clauses_to_expr(clauses))
      return [self._indent(indent) + line for line in body_lines], clauses

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
      return f"formula({operands[0]!r})"
    if opcode == "LIM":
      low = self._render_value(operands[0])
      test = self._render_value(operands[1])
      high = self._render_value(operands[2])
      return f"{low} <= {test} <= {high}"
    operator = PREDICATE_OPERATORS[opcode]
    left = self._render_value(operands[0])
    right = self._render_value(operands[1])
    return f"{left} {operator} {right}"

  def _render_instruction_body(self, opcode: str, operands: tuple[str, ...], rung_in: str | None = None):
    if opcode == "ADD":
      return [self._render_assignment(operands[2], f"{self._render_value(operands[0])} + {self._render_value(operands[1])}")]
    if opcode == "CPT":
      return [self._render_assignment(operands[0], f"formula({operands[1]!r})")]
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
      keyword_items = [
        (name, self._render_named_argument(name, value))
        for name, value in zip(NAMED_ARGUMENTS[opcode], operands)
      ]
      if rung_in is not None and opcode in RUNG_IN_ARGUMENT_NAMES:
        keyword_items.append(("rung_in", rung_in))
      return self._render_call_lines(opcode, keyword_items=tuple(keyword_items))
    if opcode == "RES":
      return self._render_call_lines(opcode, positional=(self._render_path_argument(operands[0]),))
    if opcode == "COP":
      return self._render_call_lines(
        opcode,
        keyword_items=(
          ("source", self._render_path_argument(operands[0])),
          ("dest", self._render_path_argument(operands[1])),
          ("length", self._render_runtime_token(operands[2])),
        ),
      )
    if opcode == "FLL":
      return self._render_call_lines(
        opcode,
        keyword_items=(
          ("value", self._render_runtime_token(operands[0])),
          ("dest", self._render_path_argument(operands[1])),
          ("length", self._render_runtime_token(operands[2])),
        ),
      )
    if opcode == "FFL":
      keyword_items = [
        ("source", self._render_path_argument(operands[0])),
        ("array", self._render_path_argument(operands[1])),
        ("control", self._render_path_argument(operands[2])),
        ("length", self._render_literal(operands[3])),
        ("position", self._render_literal(operands[4])),
      ]
      if rung_in is not None:
        keyword_items.append(("rung_in", rung_in))
      return self._render_call_lines(
        opcode,
        keyword_items=tuple(keyword_items),
      )
    if opcode == "FFU":
      keyword_items = [
        ("array", self._render_path_argument(operands[0])),
        ("dest", self._render_path_argument(operands[1])),
        ("control", self._render_path_argument(operands[2])),
        ("length", self._render_literal(operands[3])),
        ("position", self._render_literal(operands[4])),
      ]
      if rung_in is not None:
        keyword_items.append(("rung_in", rung_in))
      return self._render_call_lines(
        opcode,
        keyword_items=tuple(keyword_items),
      )
    if opcode in {"PID", "SFX", "SLS"}:
      return self._render_call_lines(opcode, positional=tuple(self._render_literal(operand) for operand in operands))
    if not operands:
      return [f"{opcode}()"]
    return self._render_call_lines(opcode, positional=tuple(self._render_value(operand) for operand in operands))

  def _render_jsr(self, operands: tuple[str, ...]):
    routine_name = str(operands[0])
    keyword_items: list[tuple[str, str]] = [("routine", self._render_literal(routine_name))]
    if len(operands) > 1 and operands[1] != "0":
      keyword_items.append(("parameter_block", self._render_runtime_token(operands[1])))
    return self._render_call_lines("JSR", keyword_items=tuple(keyword_items))

  def _render_output_energize(self, target: str, clauses: list[str]) -> str:
    return self._render_assignment(target, f"bool({self._clauses_to_expr(clauses)})")

  def _render_assignment(self, target: str, value: str) -> str:
    if str(target).startswith("_"):
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
    if text == "?":
      return "None"
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
      return repr(text[1:-1])
    if NUMERIC_PATTERN.fullmatch(text):
      return text
    if text.lower() in {"true", "false"}:
      return "True" if text.lower() == "true" else "False"
    if text.startswith("_"):
      return text
    if ":" not in text and any(character in text for character in {" ", "-", "%"}):
      return repr(text)
    return f"tag({text!r})"

  def _render_named_argument(self, name: str, value: str) -> str:
    if name in REFERENCE_ARGUMENT_NAMES:
      return self._render_path_argument(value)
    if name == "profile":
      return repr(self._canonicalize_profile(value))
    if name == "merge":
      return repr(self._canonicalize_merge(value))
    if name == "termination_type":
      return self._render_termination_type(value)
    if name in CANONICAL_LITERAL_ARGUMENT_VALUES:
      return repr(CANONICAL_LITERAL_ARGUMENT_VALUES[name]) if isinstance(CANONICAL_LITERAL_ARGUMENT_VALUES[name], str) else str(CANONICAL_LITERAL_ARGUMENT_VALUES[name])
    if name in LITERAL_ARGUMENT_NAMES:
      return self._render_literal(value)
    return self._render_runtime_token(value)

  def _render_path_argument(self, token: str) -> str:
    return repr(str(token))

  def _render_runtime_token(self, token: str) -> str:
    return self._render_literal(token)

  def _canonicalize_profile(self, token: str) -> str:
    text = str(token).strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
      text = text[1:-1]
    normalized = text.lower()
    return CANONICAL_PROFILE_VALUES.get(normalized, text)

  def _canonicalize_merge(self, token: str) -> str:
    text = str(token).strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
      text = text[1:-1]
    normalized = text.lower()
    return CANONICAL_MERGE_VALUES.get(normalized, text)

  def _render_termination_type(self, token: str) -> str:
    text = str(token).strip()
    if NUMERIC_PATTERN.fullmatch(text):
      value = int(float(text))
      if value in VALID_TERMINATION_TYPES:
        return str(value)
    return self._render_runtime_token(token)

  def _render_literal(self, token: str) -> str:
    text = str(token)
    if text == "?":
      return "None"
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
      return repr(text[1:-1])
    if NUMERIC_PATTERN.fullmatch(text):
      return text
    if text.lower() in {"true", "false"}:
      return "True" if text.lower() == "true" else "False"
    return repr(text)

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


def load_executable_generated_routine(
  source: str,
  *,
  symbol_name: str | None = None,
):
  return load_imperative_routine_from_source(source, symbol_name=symbol_name)
