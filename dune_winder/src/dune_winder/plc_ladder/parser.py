from __future__ import annotations

import re
from pathlib import Path

from .ast import Branch
from .ast import InstructionCall
from .ast import Node
from .ast import Rung
from .ast import Routine


TOKEN_PATTERN = re.compile(r'"[^"]*"|\S+')
PROTECTED_SPACE = "\uFFF0"
SEGQUEUE_PATH_PATTERN = re.compile(
  r"SegQueueBST\s+"
  r"([A-Za-z_][A-Za-z0-9_]*)\s+"
  r"BND\s+"
  r"(\.[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]+\])*(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]+\])*)*)"
)

OPERAND_COUNTS = {
  "ADD": 3,
  "AFI": 0,
  "BND": 0,
  "BST": 0,
  "CMP": 1,
  "COP": 3,
  "CPT": 2,
  "CTU": 3,
  "EQU": 2,
  "FFL": 5,
  "FFU": 5,
  "FLL": 3,
  "GEQ": 2,
  "GRT": 2,
  "JMP": 1,
  "JSR": 2,
  "LBL": 1,
  "LEQ": 2,
  "LES": 2,
  "LIM": 3,
  "MAFR": 2,
  "MAM": 20,
  "MAS": 9,
  "MCCM": 25,
  "MCCD": 18,
  "MCLM": 22,
  "MCS": 9,
  "MOD": 3,
  "MOV": 2,
  "MSF": 2,
  "MSO": 2,
  "NEQ": 2,
  "NOP": 0,
  "NXB": 0,
  "ONS": 1,
  "OSF": 2,
  "OSR": 2,
  "OTE": 1,
  "OTL": 1,
  "OTU": 1,
  "PID": 7,
  "RES": 1,
  "SFX": 14,
  "SLS": 11,
  "TON": 3,
  "TRN": 2,
  "XIC": 1,
  "XIO": 1,
}


class RllParser:
  def parse_routine_text(
    self,
    routine_name: str,
    text: str,
    *,
    program: str | None = None,
    source_path: str | Path | None = None,
  ) -> Routine:
    rungs = []
    for line in text.splitlines():
      stripped = line.strip()
      if not stripped or stripped.startswith(";"):
        continue
      rungs.append(self.parse_rung(stripped))
    return Routine(
      name=routine_name,
      rungs=tuple(rungs),
      program=program,
      source_path=Path(source_path) if source_path is not None else None,
    )

  def parse_routine_path(
    self,
    routine_path: str | Path,
    *,
    routine_name: str | None = None,
    program: str | None = None,
  ) -> Routine:
    path = Path(routine_path)
    inferred_name = routine_name or path.parent.name
    return self.parse_routine_text(
      inferred_name,
      path.read_text(encoding="utf-8"),
      program=program,
      source_path=path,
    )

  def parse_rung(self, line: str) -> Rung:
    tokens = tuple(TOKEN_PATTERN.findall(self._protect_special_operands(line)))
    nodes, index = self._parse_nodes(tokens, 0, stop_tokens=frozenset())
    if index != len(tokens):
      raise ValueError(f"Unexpected trailing tokens in rung: {tokens[index:]!r}")
    return Rung(nodes=tuple(nodes))

  def _parse_nodes(self, tokens, index: int, stop_tokens: frozenset[str]):
    nodes: list[Node] = []
    while index < len(tokens):
      opcode = tokens[index]
      if opcode in stop_tokens:
        break
      if opcode == "BST":
        branch, index = self._parse_branch(tokens, index + 1)
        nodes.append(branch)
        continue
      if opcode in {"NXB", "BND"}:
        raise ValueError(f"Unexpected branch token {opcode!r}")
      instruction, index = self._parse_instruction(tokens, index)
      nodes.append(instruction)
    return nodes, index

  def _parse_branch(self, tokens, index: int):
    branches = []
    while True:
      branch_nodes, index = self._parse_nodes(tokens, index, stop_tokens=frozenset({"NXB", "BND"}))
      branches.append(tuple(branch_nodes))
      if index >= len(tokens):
        raise ValueError("Unclosed BST/NXB/BND branch group")
      if tokens[index] == "BND":
        return Branch(branches=tuple(branches)), index + 1
      index += 1

  def _parse_instruction(self, tokens, index: int):
    opcode = tokens[index]
    if opcode not in OPERAND_COUNTS:
      raise ValueError(f"Unsupported opcode {opcode!r}")
    if opcode == "CMP":
      operands, end = self._collect_formula_operands(tokens, index + 1, required_prefix=0)
      return InstructionCall(opcode=opcode, operands=operands), end
    if opcode == "CPT":
      operands, end = self._collect_formula_operands(tokens, index + 1, required_prefix=1)
      return InstructionCall(opcode=opcode, operands=operands), end
    operand_count = OPERAND_COUNTS[opcode]
    start = index + 1
    end = start + operand_count
    operands = tuple(self._restore_token(token) for token in tokens[start:end])
    if len(operands) != operand_count:
      raise ValueError(f"Opcode {opcode!r} expects {operand_count} operands")
    return InstructionCall(opcode=opcode, operands=operands), end

  def _collect_formula_operands(self, tokens, index: int, required_prefix: int):
    prefix = [
      self._restore_token(token)
      for token in tokens[index:index + required_prefix]
    ]
    if len(prefix) != required_prefix:
      raise ValueError("Missing formula operands")

    cursor = index + required_prefix
    formula_tokens = []
    while cursor < len(tokens) and not self._is_boundary_token(tokens[cursor]):
      formula_tokens.append(tokens[cursor])
      cursor += 1

    if not formula_tokens:
      raise ValueError("Missing formula expression")

    return tuple(prefix + [self._restore_token(" ".join(formula_tokens))]), cursor

  def _is_boundary_token(self, token: str) -> bool:
    return token in OPERAND_COUNTS or token in {"BST", "NXB", "BND"}

  def _protect_special_operands(self, line: str) -> str:
    return SEGQUEUE_PATH_PATTERN.sub(self._replace_segqueue_path, line)

  def _replace_segqueue_path(self, match: re.Match[str]) -> str:
    protected = [
      "SegQueueBST",
      match.group(1),
      "BND",
      match.group(2),
    ]
    return PROTECTED_SPACE.join(protected)

  def _restore_token(self, token: str) -> str:
    return str(token).replace(PROTECTED_SPACE, " ")
