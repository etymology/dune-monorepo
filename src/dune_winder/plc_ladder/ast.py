from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias


@dataclass(frozen=True)
class InstructionCall:
  opcode: str
  operands: tuple[str, ...] = ()


@dataclass(frozen=True)
class Branch:
  branches: tuple[tuple["Node", ...], ...]


Node: TypeAlias = InstructionCall | Branch


@dataclass(frozen=True)
class Rung:
  nodes: tuple[Node, ...]


@dataclass(frozen=True)
class Routine:
  name: str
  rungs: tuple[Rung, ...]
  program: str | None = None
  source_path: Path | None = None
