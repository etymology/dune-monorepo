from __future__ import annotations

from .ast import Branch
from .ast import InstructionCall
from .ast import Node
from .ast import Rung
from .ast import Routine


class RllEmitter:
  def emit_routine(self, routine: Routine) -> str:
    return "\n".join(self.emit_rung(rung) for rung in routine.rungs) + "\n"

  def emit_rung(self, rung: Rung) -> str:
    return " ".join(self._emit_nodes(rung.nodes)) + " "

  def _emit_nodes(self, nodes: tuple[Node, ...]):
    emitted = []
    for node in nodes:
      if isinstance(node, InstructionCall):
        emitted.append(node.opcode)
        if node.opcode == "CMP":
          emitted.append(self._emit_cmp_operand(node.operands[0]))
        else:
          emitted.extend(node.operands)
        continue
      if isinstance(node, Branch):
        emitted.append("BST")
        for index, branch in enumerate(node.branches):
          if index:
            emitted.append("NXB")
          emitted.extend(self._emit_nodes(branch))
        emitted.append("BND")
        continue
      raise TypeError(f"Unsupported AST node: {type(node)!r}")
    return emitted

  def _emit_cmp_operand(self, operand: str) -> str:
    text = str(operand).strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
      text = text[1:-1]
    return '"' + "".join(text.split()) + '"'
