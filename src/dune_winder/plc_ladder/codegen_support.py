from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .ast import Branch
from .ast import InstructionCall
from .ast import Node
from .ast import Routine
from .ast import Rung
from .parser import OPERAND_COUNTS


def RUNG(*nodes: Node) -> Rung:
  return Rung(nodes=tuple(nodes))


def BRANCH(*branches: Iterable[Node]) -> Branch:
  return Branch(branches=tuple(tuple(branch) for branch in branches))


def ROUTINE(
  *,
  name: str,
  rungs: Iterable[Rung] = (),
  program: str | None = None,
  source_path: str | Path | None = None,
) -> Routine:
  return Routine(
    name=str(name),
    rungs=tuple(rungs),
    program=None if program is None else str(program),
    source_path=Path(source_path) if source_path is not None else None,
  )


def _instruction(opcode: str):
  def build_instruction(*operands) -> InstructionCall:
    return InstructionCall(
      opcode=opcode,
      operands=tuple(str(operand) for operand in operands),
    )

  build_instruction.__name__ = opcode
  return build_instruction


for _opcode in sorted(OPERAND_COUNTS):
  if _opcode in {"BND", "BST", "NXB"}:
    continue
  globals()[_opcode] = _instruction(_opcode)


def load_routine_from_source(source: str, *, symbol_name: str | None = None) -> Routine:
  namespace: dict[str, object] = {}
  exec(compile(source, "<plc_ladder_codegen>", "exec"), namespace)

  if symbol_name is not None:
    routine = namespace.get(symbol_name)
    if not isinstance(routine, Routine):
      raise ValueError(f"Routine symbol {symbol_name!r} not found in generated source")
    return routine

  routines = {
    name: value
    for name, value in namespace.items()
    if isinstance(value, Routine)
  }
  if not routines:
    raise ValueError("Generated source did not define a ladder routine")
  if len(routines) > 1:
    raise ValueError(
      "Generated source defined multiple ladder routines; pass symbol_name explicitly"
    )
  return next(iter(routines.values()))


__all__ = [
  "BRANCH",
  "ROUTINE",
  "RUNG",
  "load_routine_from_source",
  *sorted(opcode for opcode in OPERAND_COUNTS if opcode not in {"BND", "BST", "NXB"}),
]
