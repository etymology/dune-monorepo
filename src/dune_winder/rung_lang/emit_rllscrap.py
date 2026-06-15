"""Emit rung IR back to the paren dialect.

Used internally (equivalence checks, CI round-trips) and as L5X rung CDATA.
Studio's own clipboard output separates rungs with three spaces; we keep
that for byte-compatibility with checked-in ``studio_copy.rllscrap``.
"""

from __future__ import annotations

from .rung_ir import BranchIR, Node, RoutineIR, RungIR


def node_text(node: Node) -> str:
    if isinstance(node, BranchIR):
        return (
            "["
            + ",".join("".join(node_text(n) for n in leg) for leg in node.legs)
            + "]"
        )
    return node.text()


def rung_text(rung: RungIR) -> str:
    return "".join(node_text(node) for node in rung.nodes) + ";"


def routine_text(routine: RoutineIR) -> str:
    return "   ".join(rung_text(rung) for rung in routine.rungs) + "\n"
