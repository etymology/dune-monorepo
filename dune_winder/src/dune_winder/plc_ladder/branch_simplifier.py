from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .ast import Branch
from .ast import InstructionCall
from .ast import Node
from .ast import Routine
from .ast import Rung
from .emitter import RllEmitter
from .parser import RllParser


CONDITION_OPCODES = frozenset({
  "AFI",
  "CMP",
  "EQU",
  "GEQ",
  "GRT",
  "LEQ",
  "LES",
  "LIM",
  "NEQ",
  "XIC",
  "XIO",
})
SAFE_DUPLICATE_OPCODES = CONDITION_OPCODES | frozenset({
  "CPT",
  "MOV",
  "NOP",
  "OTL",
  "OTU",
})
FORMULA_FUNCTIONS = frozenset({
  "ABS",
  "ATN",
  "COS",
  "MOD",
  "SIN",
  "SQR",
})
STRING_LITERAL_PATTERN = re.compile(r'"[^"]*"')
IDENTIFIER_PATTERN = re.compile(
  r"(?<![A-Za-z0-9_.])"
  r"([A-Za-z_][A-Za-z0-9_:]*(?:\[[^\]]+\])*(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]+\])*)*)"
)


@dataclass(frozen=True)
class SimplificationIssue:
  rung_number: int
  reason: str
  source_rung: str


@dataclass(frozen=True)
class RoutineSimplificationResult:
  routine: Routine
  changed: bool
  original_rung_count: int
  emitted_rung_count: int
  helper_tags: tuple[str, ...]
  issues: tuple[SimplificationIssue, ...]


@dataclass(frozen=True)
class FileSimplificationResult:
  path: Path
  changed: bool
  original_rung_count: int
  emitted_rung_count: int
  helper_tags: tuple[str, ...]
  issues: tuple[SimplificationIssue, ...]


@dataclass(frozen=True)
class HelperLoweringPlan:
  prefix: tuple[InstructionCall, ...]
  branch_paths: tuple[tuple[InstructionCall, ...], ...]
  suffix: tuple[InstructionCall, ...]


def iter_pasteable_files(root: Path):
  yield from sorted(root.rglob("pasteable.rll"))


def infer_program_name(path: Path) -> str | None:
  if len(path.parts) < 3:
    return None
  return path.parent.parent.name


def simplify_text(
  text: str,
  *,
  routine_name: str = "main",
  program: str | None = None,
  source_path: str | Path | None = None,
) -> RoutineSimplificationResult:
  routine = RllParser().parse_routine_text(
    routine_name,
    text,
    program=program,
    source_path=source_path,
  )
  return simplify_routine(routine)


def simplify_routine(routine: Routine) -> RoutineSimplificationResult:
  emitter = RllEmitter()
  issues: list[SimplificationIssue] = []
  helper_tags: list[str] = []
  new_rungs: list[Rung] = []
  changed = False
  helper_index = 1

  for rung_number, rung in enumerate(routine.rungs, start=1):
    if not _contains_branch(rung.nodes):
      new_rungs.append(rung)
      continue

    branch_side_effect_opcode = _first_branch_side_effect_opcode(rung.nodes)
    if branch_side_effect_opcode is not None:
      new_rungs.append(rung)
      issues.append(
        SimplificationIssue(
          rung_number=rung_number,
          reason=f"branch path contains side-effect opcode {branch_side_effect_opcode}",
          source_rung=emitter.emit_rung(rung).strip(),
        )
      )
      continue

    duplicate_reason = _duplicate_blocker_reason(rung.nodes)
    if duplicate_reason is None:
      expanded = _expand_nodes(rung.nodes)
      changed = changed or len(expanded) != 1 or expanded[0] != rung.nodes
      new_rungs.extend(Rung(nodes=nodes) for nodes in expanded)
      continue

    helper_plan = _helper_lowering_plan(rung.nodes)
    if helper_plan is not None:
      helper_name = _make_helper_name(routine.name, helper_index)
      helper_index += 1
      helper_tags.append(helper_name)
      new_rungs.extend(_lower_with_helper(helper_plan, helper_name))
      changed = True
      continue

    new_rungs.append(rung)
    issues.append(
      SimplificationIssue(
        rung_number=rung_number,
        reason=duplicate_reason,
        source_rung=emitter.emit_rung(rung).strip(),
      )
    )

  return RoutineSimplificationResult(
    routine=Routine(
      name=routine.name,
      rungs=tuple(new_rungs),
      program=routine.program,
      source_path=routine.source_path,
    ),
    changed=changed,
    original_rung_count=len(routine.rungs),
    emitted_rung_count=len(new_rungs),
    helper_tags=tuple(helper_tags),
    issues=tuple(issues),
  )


def simplify_file(path: str | Path, *, write_changes: bool = False) -> FileSimplificationResult:
  source_path = Path(path)
  text = source_path.read_text(encoding="utf-8")
  result = simplify_text(
    text,
    routine_name=source_path.parent.name,
    program=infer_program_name(source_path),
    source_path=source_path,
  )
  if write_changes and result.changed:
    emitted = RllEmitter().emit_routine(result.routine)
    source_path.write_text(emitted, encoding="utf-8")
  return FileSimplificationResult(
    path=source_path,
    changed=result.changed,
    original_rung_count=result.original_rung_count,
    emitted_rung_count=result.emitted_rung_count,
    helper_tags=result.helper_tags,
    issues=result.issues,
  )


def _contains_branch(nodes: tuple[Node, ...]) -> bool:
  for node in nodes:
    if isinstance(node, Branch):
      return True
  return False


def _duplicate_blocker_reason(nodes: tuple[Node, ...]) -> str | None:
  unsupported_opcode = _first_unsupported_opcode(nodes)
  if unsupported_opcode is not None:
    return f"rung contains opcode {unsupported_opcode} that is not safe to duplicate"

  reads, writes = _collect_reads_and_writes(nodes)
  overlap = sorted(reads & writes)
  if overlap:
    return "rung reads and writes the same tag(s): " + ", ".join(overlap)

  return None


def _first_branch_side_effect_opcode(nodes: tuple[Node, ...]) -> str | None:
  for node in nodes:
    if not isinstance(node, Branch):
      continue
    for branch_nodes in node.branches:
      opcode = _first_non_condition_opcode(branch_nodes)
      if opcode is not None:
        return opcode
  return None


def _helper_lowering_plan(nodes: tuple[Node, ...]) -> HelperLoweringPlan | None:
  branch_indexes = [index for index, node in enumerate(nodes) if isinstance(node, Branch)]
  if len(branch_indexes) != 1:
    return None

  branch_index = branch_indexes[0]
  prefix_nodes = nodes[:branch_index]
  branch_node = nodes[branch_index]
  suffix_nodes = nodes[branch_index + 1:]

  if not isinstance(branch_node, Branch):
    return None
  if not suffix_nodes:
    return None
  if any(not isinstance(node, InstructionCall) or node.opcode not in CONDITION_OPCODES for node in prefix_nodes):
    return None
  if any(not isinstance(node, InstructionCall) for node in suffix_nodes):
    return None

  branch_paths: list[tuple[InstructionCall, ...]] = []
  for branch_nodes in branch_node.branches:
    for expanded_path in _expand_nodes(branch_nodes):
      if any(not isinstance(node, InstructionCall) or node.opcode not in CONDITION_OPCODES for node in expanded_path):
        return None
      branch_paths.append(tuple(expanded_path))

  if not branch_paths:
    return None

  return HelperLoweringPlan(
    prefix=tuple(prefix_nodes),
    branch_paths=tuple(branch_paths),
    suffix=tuple(suffix_nodes),
  )


def _make_helper_name(routine_name: str, index: int) -> str:
  sanitized = re.sub(r"[^A-Za-z0-9_]+", "_", routine_name).strip("_")
  if not sanitized:
    sanitized = "routine"
  return f"auto_{sanitized}_branch_{index:03d}"


def _lower_with_helper(plan: HelperLoweringPlan, helper_name: str) -> list[Rung]:
  lowered = [Rung(nodes=(InstructionCall(opcode="OTU", operands=(helper_name,)),))]
  for branch_path in plan.branch_paths:
    lowered.append(
      Rung(
        nodes=tuple(plan.prefix + branch_path + (InstructionCall(opcode="OTL", operands=(helper_name,)),))
      )
    )
  lowered.append(
    Rung(
      nodes=(InstructionCall(opcode="XIC", operands=(helper_name,)),) + plan.suffix
    )
  )
  return lowered


def _first_non_condition_opcode(nodes: tuple[Node, ...]) -> str | None:
  for node in nodes:
    if isinstance(node, Branch):
      for branch_nodes in node.branches:
        opcode = _first_non_condition_opcode(branch_nodes)
        if opcode is not None:
          return opcode
      continue
    if node.opcode not in CONDITION_OPCODES:
      return node.opcode
  return None


def _first_unsupported_opcode(nodes: tuple[Node, ...]) -> str | None:
  for node in nodes:
    if isinstance(node, Branch):
      opcode = _first_unsupported_opcode_in_branches(node)
      if opcode is not None:
        return opcode
      continue
    if node.opcode not in SAFE_DUPLICATE_OPCODES:
      return node.opcode
  return None


def _first_unsupported_opcode_in_branches(branch: Branch) -> str | None:
  for branch_nodes in branch.branches:
    opcode = _first_unsupported_opcode(branch_nodes)
    if opcode is not None:
      return opcode
  return None


def _collect_reads_and_writes(nodes: tuple[Node, ...]) -> tuple[set[str], set[str]]:
  reads: set[str] = set()
  writes: set[str] = set()
  for node in nodes:
    if isinstance(node, Branch):
      branch_reads, branch_writes = _collect_reads_and_writes_for_branches(node)
      reads.update(branch_reads)
      writes.update(branch_writes)
      continue
    node_reads, node_writes = _instruction_reads_and_writes(node)
    reads.update(node_reads)
    writes.update(node_writes)
  return reads, writes


def _collect_reads_and_writes_for_branches(branch: Branch) -> tuple[set[str], set[str]]:
  reads: set[str] = set()
  writes: set[str] = set()
  for branch_nodes in branch.branches:
    branch_reads, branch_writes = _collect_reads_and_writes(branch_nodes)
    reads.update(branch_reads)
    writes.update(branch_writes)
  return reads, writes


def _instruction_reads_and_writes(instruction: InstructionCall) -> tuple[set[str], set[str]]:
  opcode = instruction.opcode
  operands = instruction.operands
  if opcode in {"AFI", "NOP"}:
    return set(), set()
  if opcode in {"XIC", "XIO", "OTL", "OTU"}:
    reads = _extract_tag_references(operands[0]) if opcode in {"XIC", "XIO"} else set()
    writes = {operands[0]} if opcode in {"OTL", "OTU"} else set()
    return reads, writes
  if opcode == "CMP":
    return _extract_tag_references(operands[0]), set()
  if opcode in {"EQU", "GEQ", "GRT", "LEQ", "LES", "NEQ"}:
    return _extract_tag_references(operands[0]) | _extract_tag_references(operands[1]), set()
  if opcode == "LIM":
    return (
      _extract_tag_references(operands[0])
      | _extract_tag_references(operands[1])
      | _extract_tag_references(operands[2]),
      set(),
    )
  if opcode == "MOV":
    return _extract_tag_references(operands[0]), {operands[1]}
  if opcode == "CPT":
    return _extract_tag_references(operands[1]), {operands[0]}
  return set(), set()


def _extract_tag_references(text: str) -> set[str]:
  scrubbed = STRING_LITERAL_PATTERN.sub(" ", str(text))
  references: set[str] = set()
  for match in IDENTIFIER_PATTERN.finditer(scrubbed):
    name = match.group(1)
    if name.lower() in {"false", "true"}:
      continue
    end = match.end(1)
    if end < len(scrubbed) and scrubbed[end] == "(" and name.upper() in FORMULA_FUNCTIONS:
      continue
    references.add(name)
  return references


def _expand_nodes(nodes: tuple[Node, ...]) -> tuple[tuple[Node, ...], ...]:
  expanded: list[tuple[Node, ...]] = [tuple()]
  for node in nodes:
    if isinstance(node, Branch):
      branch_expansions: list[tuple[Node, ...]] = []
      for branch_nodes in node.branches:
        branch_expansions.extend(_expand_nodes(branch_nodes))
      expanded = [
        left + right
        for left in expanded
        for right in branch_expansions
      ]
      continue
    expanded = [nodes_so_far + (node,) for nodes_so_far in expanded]
  return tuple(expanded)
