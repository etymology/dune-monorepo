"""Lower the .rung AST to rung IR.

Canonical lowerings (the renderer recognises exactly these shapes, which
is what makes ``.rung -> rllscrap -> .rung`` a fixed point):

- guard expressions are normalised to NNF (De Morgan; comparator
  negation duals) and mapped structurally: ``and`` -> series contacts,
  ``or`` -> branch legs, literals -> XIC/XIO/comparator contacts; a
  comparison involving arithmetic becomes ``CMP(expr)``,
- assignment to a BOOL target -> RHS contacts + ``OTE`` (a coil drive,
  the inverse of how the renderer prints an ``OTE`` as ``coil = <enable>``);
  assignment of a number or tag to a numeric target -> ``MOV``; anything
  computed -> ``CPT``,
- ``when:`` blocks -> one rung with series outputs,
- ``on rising/falling/entry of`` -> an OSR/OSF rung plus one rung per
  action. The two bookkeeping bits are named as follows, in priority
  order: (1) an explicit ``using <storage>, <edge>`` clause is honoured
  verbatim — this is how the renderer round-trips hand-named bits so a
  recompile does not rename them; (2) otherwise, when the trigger is a
  single tag, informative names are derived from it
  (``<slug>_osr_sb``/``<slug>_rising`` for OSR, ``<slug>_osf_sb``/
  ``<slug>_falling`` for OSF) so the generated PLC stays readable;
  (3) otherwise (a multi-term trigger that cannot be slugged) we fall
  back to ``auto_edge_<k>_sb``/``auto_edge_<k>_ob``. The equivalence
  checker, not byte-diffing, is the correctness bar (plan §8),
- ``label x`` -> ``LBL(x)NOP();`` on its own rung.
"""

from __future__ import annotations

import re
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
# One-shot bookkeeping-bit naming
# ---------------------------------------------------------------------------


def edge_slug(expr: Expr) -> str | None:
    """A tag-derived slug for a single-tag trigger (``x_axis_msf.DN`` ->
    ``x_axis_msf_dn``), or None when the trigger is anything compound —
    such expressions have no readable short name, so the caller falls
    back to ``auto_edge_<k>``."""
    if not isinstance(expr, Ref):
        return None
    slug = re.sub(r"[^A-Za-z0-9]+", "_", expr.text).strip("_").lower()
    return slug or None


def auto_edge_names(kind: str, expr: Expr) -> tuple[str, str] | None:
    """The ``(storage, edge)`` bit names lowering invents for an ``on``
    block with no explicit ``using`` clause, or None when the trigger is
    not sluggable. ``entry`` is a rising edge, so it shares the OSR form.
    The renderer calls this to decide when a one-shot's actual bits match
    the auto scheme (clause stays implicit) versus need spelling out."""
    slug = edge_slug(expr)
    if slug is None:
        return None
    if kind == "falling":
        return f"{slug}_osf_sb", f"{slug}_falling"
    return f"{slug}_osr_sb", f"{slug}_rising"


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


def _bool_rhs(expr: Expr) -> bool:
    """The RHS of a BOOL-target assignment must be a contact network, not a
    value: a tag, a negation, an and/or/comparison, or a boolean call."""
    if isinstance(expr, Ref):
        return True
    if isinstance(expr, Una):
        return expr.op == "not"
    if isinstance(expr, Bin):
        return expr.op in ("and", "or") or expr.op in formula.COMPARATORS
    if isinstance(expr, Call):
        return expr.func in ("TRUE", "FALSE", "LIM", "AFI", "ONS")
    return False


def _coil_nodes(action: rast.Action, meta, program: str) -> list[Node] | None:
    """If ``action`` assigns a contact expression to a BOOL tag, return the
    RHS contacts followed by the driven ``OTE`` coil; otherwise None. MOV
    only accepts SINT/INT/DINT/REAL, so a BOOL destination *must* be a coil
    — emitting ``MOV`` there produces an illegal rung."""
    if (
        meta is None
        or not isinstance(action, rast.AssignAction)
        or not _bool_rhs(action.expr)
        or meta.data_type(program, Ref(action.target).base) != "BOOL"
    ):
        return None
    return guard_nodes(action.expr) + [Instr("OTE", (action.target,))]


def _gated_rungs(
    gate: list[Node], actions, meta, program: str, group_by_type: bool = False
) -> list[RungIR]:
    """Lower a block's actions behind ``gate``. Non-coil outputs pack into a
    single gated rung (series outputs); each BOOL coil gets its own rung so
    its RHS contacts don't gate the outputs that follow it.

    With ``group_by_type``, a run of non-coil outputs is further split at
    each change of opcode, so consecutive same-instruction outputs land
    together but distinct kinds do not (MOV MOV …, then MCS MCS …, then MAS
    MAS …, one rung each) — the conventional ladder shape. Only ``on`` blocks
    use this: their actions are re-gated across several rungs that the
    renderer collects back into one block, whereas a plain ``when:`` block is
    a single rung and must stay one rung to round-trip."""
    rungs: list[RungIR] = []
    packed: list[Instr] = []

    def flush() -> None:
        nonlocal packed
        if packed:
            rungs.append(RungIR(tuple(gate + packed)))
            packed = []

    for action in actions:
        coil = _coil_nodes(action, meta, program)
        if coil is None:
            instr = action_instr(action)
            if group_by_type and packed and packed[-1].opcode != instr.opcode:
                flush()
            packed.append(instr)
            continue
        flush()
        rungs.append(RungIR(tuple(gate + coil)))
    if packed:
        flush()
    elif not rungs:
        rungs.append(RungIR(tuple(gate)))
    return rungs


def lower_routine(routine_ast: rast.RoutineAST, meta=None) -> Lowered:
    rungs: list[RungIR] = []
    auto_tags: list[str] = []
    edge_index = 0
    used_edge_bits: set[str] = set()
    program = routine_ast.program

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
            gate = guard_nodes(stmt.guard) if stmt.guard is not None else []
            rungs.extend(_gated_rungs(gate, [stmt.action], meta, program))
            continue
        if isinstance(stmt, rast.WhenBlock):
            gate = guard_nodes(stmt.guard) if stmt.guard is not None else []
            rungs.extend(_gated_rungs(gate, stmt.actions, meta, program))
            continue
        if isinstance(stmt, rast.OnBlock):
            if stmt.storage is not None and stmt.edge is not None:
                # explicit `using` clause: honour it verbatim. These bits
                # are existing program tags (or human-declared locals), so
                # they are *not* auto-synthesized — they resolve like any
                # other referenced tag.
                storage, edge = stmt.storage, stmt.edge
            else:
                named = auto_edge_names(stmt.kind, stmt.expr)
                if named is None:
                    storage = f"auto_edge_{edge_index}_sb"
                    edge = f"auto_edge_{edge_index}_ob"
                    edge_index += 1
                else:
                    storage, edge = named
                    # two identical triggers would collide; disambiguate.
                    n = 2
                    while storage in used_edge_bits or edge in used_edge_bits:
                        storage, edge = f"{named[0]}_{n}", f"{named[1]}_{n}"
                        n += 1
                auto_tags.extend((storage, edge))
            used_edge_bits.update((storage, edge))
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
            # Re-gate the actions behind the edge bit, grouping consecutive
            # outputs of the same opcode onto one rung (MOV MOV …, MCS MCS …,
            # MAS MAS …). Every output is gated by the same edge bit, which no
            # action writes, so this is behaviourally identical to one rung
            # per action while keeping rungs to the conventional one-kind
            # shape. The renderer's `_gated_outputs` reads any number of
            # outputs off each rung and `_recognize_on_block` collects the run
            # of gated rungs back into one block, so this round-trips.
            rungs.extend(
                _gated_rungs(gate, stmt.actions, meta, program, group_by_type=True)
            )
            continue
        raise LowerError(f"unknown statement {stmt!r}")

    return Lowered(
        RoutineIR(routine_ast.program, routine_ast.routine, tuple(rungs)),
        tuple(auto_tags),
    )
