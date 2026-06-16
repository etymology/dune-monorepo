"""Resolve timer/counter instruction PRE and ACC operands from tag metadata."""

from __future__ import annotations

from .formula import Ref
from .rung_ir import BranchIR, Instr, Node, RoutineIR, RungIR

TIMER_COUNTER_OPCODES = {"TON", "TOF", "RTO", "CTU", "CTD"}


def resolve_timer_counter_args(routine: RoutineIR, meta) -> RoutineIR:
    if meta is None:
        return routine
    return RoutineIR(
        routine.program,
        routine.name,
        tuple(_resolve_rung(rung, meta, routine.program) for rung in routine.rungs),
    )


def _resolve_rung(rung: RungIR, meta, program: str) -> RungIR:
    return RungIR(
        tuple(_resolve_node(node, meta, program) for node in rung.nodes),
        rung.rung_type,
    )


def _resolve_node(node: Node, meta, program: str) -> Node:
    if isinstance(node, BranchIR):
        return BranchIR(
            tuple(
                tuple(_resolve_node(child, meta, program) for child in leg)
                for leg in node.legs
            )
        )
    if node.opcode not in TIMER_COUNTER_OPCODES or len(node.operands) < 3:
        return node
    pre, acc = node.operands[1], node.operands[2]
    if pre != "?" and acc != "?":
        return node
    values = meta.timer_counter_values(program, Ref(node.operands[0]).base)
    if values is None:
        return node
    resolved_pre = values[0] if pre == "?" else pre
    resolved_acc = values[1] if acc == "?" else acc
    return Instr(
        node.opcode, (node.operands[0], resolved_pre, resolved_acc) + node.operands[3:]
    )
