from __future__ import annotations

from .ast import Branch
from .ast import InstructionCall
from .ast import Node
from .ast import Rung
from .ast import Routine
from .codegen_support import load_routine_from_source


class PythonCodeGenerator:
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


def transpile_routine_to_python(routine: Routine) -> str:
  return PythonCodeGenerator().generate_routine(routine)


def load_generated_routine(source: str, *, symbol_name: str | None = None) -> Routine:
  return load_routine_from_source(source, symbol_name=symbol_name)
