"""Lower the .rung AST to rung IR.

Canonical lowerings (the renderer recognises exactly these shapes, which
is what makes ``.rung -> rllscrap -> .rung`` a fixed point):

- guard expressions are normalised to NNF (De Morgan; comparator
  negation duals) and mapped structurally: ``and`` -> series contacts,
  ``or`` -> branch legs, literals -> XIC/XIO/comparator contacts; a
  comparison involving arithmetic becomes ``CMP(expr)``,
- assignment of a number or tag -> ``MOV``; anything computed -> ``CPT``,
- ``when:`` blocks -> one rung with series outputs,
- ``on rising/falling/entry of`` -> an OSR/OSF rung plus one rung per
  action, with deterministically named bookkeeping bits
  (``auto_edge_<k>_sb`` / ``auto_edge_<k>_ob``, k = block index in source
  order); the historical hand-allocated storage-array names are *not*
  reproduced — the equivalence checker, not byte-diffing, is the
  correctness bar (plan §8),
- ``label x`` -> ``LBL(x)NOP();`` on its own rung.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import ast as rast
from . import formula
from .formula import Bin, Call, Expr, Num, Ref, Una
from .parse_rllscrap import parse_rung_text
from .rung_ir import BranchIR, Instr, Node, RoutineIR, RungIR
from .schema import SERVO_KEYWORDS, surface_to_operands


class LowerError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Boolean guard -> contact network
# ---------------------------------------------------------------------------


def nnf(expr: Expr) -> Expr:
    if isinstance(expr, Una) and expr.op == "not":
        inner = expr.operand
        if isinstance(inner, Una) and inner.op == "not":
            return nnf(inner.operand)
        if isinstance(inner, Bin) and inner.op == "and":
            return Bin("or", nnf(Una("not", inner.lhs)), nnf(Una("not", inner.rhs)))
        if isinstance(inner, Bin) and inner.op == "or":
            return Bin("and", nnf(Una("not", inner.lhs)), nnf(Una("not", inner.rhs)))
        if isinstance(inner, Bin) and inner.op in formula.COMPARATORS:
            return Bin(formula.COMPARATOR_NEGATION[inner.op], inner.lhs, inner.rhs)
        if isinstance(inner, Ref):
            return expr
        if isinstance(inner, Call) and inner.func == "TRUE":
            return Call("FALSE", ())
        if isinstance(inner, Call) and inner.func == "FALSE":
            return Call("TRUE", ())
        raise LowerError(
            f"cannot negate {formula.print_surface(inner)!r}; rewrite without 'not'"
        )
    if isinstance(expr, Bin) and expr.op in ("and", "or"):
        return Bin(expr.op, nnf(expr.lhs), nnf(expr.rhs))
    return expr


def _plain(expr: Expr) -> str | None:
    """Operand text when the expr is a bare number/tag (contact-eligible)."""
    if isinstance(expr, Num) or isinstance(expr, Ref):
        return formula.print_formula(expr)
    if isinstance(expr, Una) and expr.op == "-" and isinstance(expr.operand, Num):
        return formula.print_formula(expr)
    return None


def guard_nodes(expr: Expr) -> list[Node]:
    """NNF boolean expression -> contact network (series of nodes)."""
    expr = nnf(expr)
    return _nodes(expr)


def _nodes(expr: Expr) -> list[Node]:
    if isinstance(expr, Bin) and expr.op == "and":
        return [n for term in formula.flatten(expr, "and") for n in _nodes(term)]
    if isinstance(expr, Bin) and expr.op == "or":
        legs = tuple(tuple(_nodes(term)) for term in formula.flatten(expr, "or"))
        return [BranchIR(legs)]
    if isinstance(expr, Ref):
        return [Instr("XIC", (expr.text,))]
    if isinstance(expr, Una) and expr.op == "not" and isinstance(expr.operand, Ref):
        return [Instr("XIO", (expr.operand.text,))]
    if isinstance(expr, Bin) and expr.op in formula.COMPARATORS:
        lhs = _plain(expr.lhs)
        rhs = _plain(expr.rhs)
        if lhs is not None and rhs is not None:
            return [Instr(formula.COMPARATOR_OPCODE[expr.op], (lhs, rhs))]
        return [Instr("CMP", (formula.print_formula(expr),))]
    if isinstance(expr, Call):
        if expr.func == "TRUE":
            return []
        if expr.func == "FALSE":
            return [Instr("AFI", ())]
        operands = []
        for arg in expr.args:
            text = _plain(arg)
            if text is None:
                raise LowerError(f"{expr.func} arguments must be plain tags or numbers")
            operands.append(text)
        return [Instr(expr.func, tuple(operands))]
    raise LowerError(f"expression {formula.print_surface(expr)!r} is not boolean")


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def action_instr(action: rast.Action) -> Instr:
    if isinstance(action, rast.AssignAction):
        plain = _plain(action.expr)
        if isinstance(action.expr, Una) and isinstance(action.expr.operand, Ref):
            plain = None  # MOV cannot negate a tag; use CPT
        if plain is not None:
            return Instr("MOV", (plain, action.target))
        return Instr("CPT", (action.target, formula.print_formula(action.expr)))
    if isinstance(action, rast.GenericAction):
        return Instr(action.opcode, action.operands)
    if isinstance(action, rast.ServoAction):
        return Instr(SERVO_KEYWORDS[action.keyword], (action.axis, action.control))
    if isinstance(action, rast.MotionAction):
        opcode, operands = surface_to_operands(
            action.keyword, action.target, action.control, list(action.pairs)
        )
        return Instr(opcode, operands)
    if isinstance(action, rast.TimerAction):
        if action.keyword == "start_timer":
            return Instr("TON", (action.tag, "?", "?"))
        if action.keyword == "count_up":
            return Instr("CTU", (action.tag, "?", "?"))
        return Instr("RES", (action.tag,))
    if isinstance(action, rast.CallAction):
        return Instr("JSR", (action.routine, "0"))
    if isinstance(action, rast.LatchAction):
        return Instr("OTL" if action.keyword == "latch" else "OTU", (action.target,))
    raise LowerError(f"unknown action {action!r}")


# ---------------------------------------------------------------------------
# Statements -> rungs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Lowered:
    routine: RoutineIR
    #: BOOL bookkeeping tags this lowering invented (storage + edge bits)
    auto_tags: tuple[str, ...]


def lower_routine(routine_ast: rast.RoutineAST) -> Lowered:
    rungs: list[RungIR] = []
    auto_tags: list[str] = []
    edge_index = 0

    for stmt in routine_ast.statements:
        if isinstance(stmt, rast.RawStmt):
            for text in stmt.text.split(";"):
                text = text.strip()
                if text:
                    rungs.append(parse_rung_text(text, "e" if stmt.pending else "N"))
            continue
        if isinstance(stmt, rast.LabelStmt):
            rungs.append(RungIR((Instr("LBL", (stmt.name,)), Instr("NOP", ()))))
            continue
        if isinstance(stmt, rast.BoolAssignStmt):
            nodes = guard_nodes(stmt.expr) + [Instr("OTE", (stmt.target,))]
            rungs.append(RungIR(tuple(nodes)))
            continue
        if isinstance(stmt, rast.GuardedStmt):
            nodes = guard_nodes(stmt.guard) if stmt.guard is not None else []
            rungs.append(RungIR(tuple(nodes + [action_instr(stmt.action)])))
            continue
        if isinstance(stmt, rast.WhenBlock):
            nodes = guard_nodes(stmt.guard) if stmt.guard is not None else []
            outputs = [action_instr(a) for a in stmt.actions]
            rungs.append(RungIR(tuple(nodes + outputs)))
            continue
        if isinstance(stmt, rast.OnBlock):
            storage = f"auto_edge_{edge_index}_sb"
            edge = f"auto_edge_{edge_index}_ob"
            edge_index += 1
            auto_tags.extend((storage, edge))
            shot = "OSF" if stmt.kind == "falling" else "OSR"
            trigger_nodes = guard_nodes(stmt.expr)
            rungs.append(RungIR(tuple(trigger_nodes + [Instr(shot, (storage, edge))])))
            if stmt.kind == "entry":
                if not isinstance(stmt.expr, Ref):
                    raise LowerError("'on entry of' takes a single bool tag")
                gate: list[Node] = [
                    Instr("XIC", (stmt.expr.text,)),
                    Instr("XIC", (edge,)),
                ]
            else:
                gate = [Instr("XIC", (edge,))]
            for action in stmt.actions:
                rungs.append(RungIR(tuple(gate + [action_instr(action)])))
            continue
        raise LowerError(f"unknown statement {stmt!r}")

    return Lowered(
        RoutineIR(routine_ast.program, routine_ast.routine, tuple(rungs)),
        tuple(auto_tags),
    )
