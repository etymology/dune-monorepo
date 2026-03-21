from __future__ import annotations

from .ast import Branch
from .ast import InstructionCall
from .ast import Node
from .ast import Rung
from .ast import Routine


class PythonCodeGenerator:
  def generate_routine(self, routine: Routine) -> str:
    lines = [
      "from dune_winder.plc_ladder.codegen_support import BRANCH, RUNG",
      "",
      "",
      f"def {self._python_name(routine)}(ctx):",
    ]
    if not routine.rungs:
      lines.append("  return")
      return "\n".join(lines) + "\n"

    for rung in routine.rungs:
      lines.append("  RUNG(")
      for rendered in self._render_rung_nodes(rung):
        lines.append("    " + rendered)
      lines.append("  )")
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
