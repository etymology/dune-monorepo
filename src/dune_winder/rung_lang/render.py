"""Render rung IR as .rung source — the projection LLMs read and edit.

Invariants:

- **No-fail:** every rung of every routine renders; anything the surface
  syntax can't express comes out as ``raw `...```.
- **Determinism:** output is a pure function of the IR plus the tag
  JSONs; no timestamps, no ambient state.
- **Fixed point:** compiling rendered output and re-rendering reproduces
  the text byte-for-byte. Every recognition rule below therefore only
  fires on shapes whose canonical lowering re-renders identically (a
  construct may *normalise once* — e.g. a packed multi-output branch rung
  splits into one statement per output — and is stable afterwards).

The distribution pass walks a rung computing each output's symbolic
enable condition, then groups consecutive outputs with the same enable
into one statement. A rung where an output writes a tag that a later
condition in the same rung reads cannot be split safely and falls back
to ``raw`` (the equivalence checker would catch a mistake here too).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import formula
from .formula import Bin, Call, Expr, Ref, Una
from .rung_ir import (
    CONDITION_OPCODES,
    BranchIR,
    Instr,
    Node,
    RoutineIR,
    RungIR,
    all_instructions,
    operand_is_ref,
    referenced_tag_bases,
)
from .schema import SERVO_OPCODES, instr_to_surface, quote_operand

INDENT = "    "


class Unrenderable(Exception):
    """Internal: this rung needs the raw fallback."""


@dataclass
class RenderResult:
    text: str
    raw_rungs: int
    total_rungs: int
    #: subset of raw_rungs that are raw because Studio holds pending edits
    #: for them (not a renderer limitation)
    pending_rungs: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def raw_density(self) -> float:
        return self.raw_rungs / self.total_rungs if self.total_rungs else 0.0


# ---------------------------------------------------------------------------
# Condition nodes -> Expr
# ---------------------------------------------------------------------------


def _instr_expr(instr: Instr) -> Expr:
    op = instr.opcode
    if op == "XIC":
        return Ref(instr.operands[0])
    if op == "XIO":
        return Una("not", Ref(instr.operands[0]))
    if op == "CMP":
        return formula.parse_formula(instr.operands[0])
    if op in formula.OPCODE_COMPARATOR:
        return Bin(
            formula.OPCODE_COMPARATOR[op],
            formula.parse_operand(instr.operands[0]),
            formula.parse_operand(instr.operands[1]),
        )
    if op in ("LIM", "AFI", "ONS"):
        return Call(op, tuple(formula.parse_operand(o) for o in instr.operands))
    raise Unrenderable(f"condition opcode {op}")


def simplify(expr: Expr) -> Expr:
    """Light, deterministic boolean cleanup: drop ``x or not x`` branch
    tautologies and absorb TRUE in conjunctions. Runs bottom-up to a
    fixed point so rendered expressions are stable under re-rendering."""
    if isinstance(expr, Una):
        return Una(expr.op, simplify(expr.operand))
    if isinstance(expr, Call):
        return Call(expr.func, tuple(simplify(a) for a in expr.args))
    if not isinstance(expr, Bin):
        return expr
    if expr.op == "or":
        terms = [simplify(t) for t in formula.flatten(expr, "or")]
        if any(formula.is_true(t) for t in terms):
            return formula.TRUE
        for i, a in enumerate(terms):
            for b in terms[i + 1 :]:
                if formula.complements(a, b):
                    return formula.TRUE
        return formula.join(terms, "or")
    if expr.op == "and":
        terms = [
            t
            for t in (simplify(t) for t in formula.flatten(expr, "and"))
            if not formula.is_true(t)
        ]
        return formula.join(terms, "and")
    return Bin(expr.op, simplify(expr.lhs), simplify(expr.rhs))


# ---------------------------------------------------------------------------
# Distribution: rung -> [(enable, output instruction)]
# ---------------------------------------------------------------------------


@dataclass
class _Emission:
    enable: Expr
    instr: Instr


def _written_paths(instr: Instr) -> set[str]:
    from .rung_ir import _WRITER_DEST  # shared table

    dest = _WRITER_DEST.get(instr.opcode)
    paths: set[str] = set()
    if dest is not None and dest < len(instr.operands):
        paths.add(instr.operands[dest].strip())
    if instr.opcode in ("OSR", "OSF"):
        paths.update(o.strip() for o in instr.operands)
    return paths


def _paths_overlap(p: str, q: str) -> bool:
    """Member-level aliasing: a write to ``x`` clobbers ``x.DN`` and vice
    versa, but ``x.FLAGS`` and ``x.DN`` are independent (and ``a[1]`` is
    not a prefix of ``a[17]``)."""
    if p == q:
        return True
    for a, b in ((p, q), (q, p)):
        if b.startswith(a) and len(b) > len(a) and b[len(a)] in ".[":
            return True
    return False


def _refs_paths(expr: Expr) -> set[str]:
    return {node.text for node in formula.walk(expr) if isinstance(node, Ref)}


def _distribute(rung: RungIR) -> list[_Emission]:
    """Distribute a rung into (enable, output) emissions.

    Splitting re-evaluates each output's full condition path right before
    the output runs, i.e. *after* the writes of earlier outputs from the
    same rung. That is only safe when no condition term captured before a
    write reads a path that write touched — otherwise the rung stays raw.
    Term/write ordering is tracked with a step counter; a term composed
    from branch legs carries the smallest step of its constituents.
    """
    emissions: list[_Emission] = []
    #: (path set, step) per write, in execution order
    writes: list[tuple[set[str], int]] = []
    step = 0

    def check_terms(terms: list[tuple[Expr, int]]) -> None:
        for expr, term_step in terms:
            refs = _refs_paths(expr)
            for paths, write_step in writes:
                if term_step < write_step and any(
                    _paths_overlap(r, w) for r in refs for w in paths
                ):
                    raise Unrenderable(
                        "a condition captured before a write in the same rung"
                        " reads what the write changes"
                    )

    def walk(
        nodes: tuple[Node, ...], outer: list[tuple[Expr, int]]
    ) -> list[tuple[Expr, int]]:
        nonlocal step
        added: list[tuple[Expr, int]] = []
        for node in nodes:
            if isinstance(node, BranchIR):
                leg_ends: list[Expr] = []
                min_step = step
                for leg in node.legs:
                    leg_added = walk(leg, outer + added)
                    if leg_added:
                        min_step = min(min_step, min(s for _, s in leg_added))
                    leg_ends.append(
                        formula.join([expr for expr, _ in leg_added], "and")
                    )
                or_term = simplify(formula.join(leg_ends, "or"))
                if not formula.is_true(or_term):
                    added.append((or_term, min_step))
                continue
            if node.opcode in CONDITION_OPCODES:
                if node.opcode == "LBL":
                    raise Unrenderable("LBL not at rung start")
                added.append((_instr_expr(node), step))
                step += 1
                continue
            # output instruction
            terms = outer + added
            check_terms(terms)
            enable = simplify(formula.join([expr for expr, _ in terms], "and"))
            emissions.append(_Emission(enable, node))
            paths = _written_paths(node)
            if paths:
                writes.append((paths, step))
            step += 1
        return added

    walk(rung.nodes, [])
    # ONS is stateful: splitting its rung would duplicate the storage
    # update across statements, changing edge behaviour.
    if any(i.opcode == "ONS" for i in all_instructions(rung)):
        if len({_expr_key(e.enable) for e in emissions}) > 1:
            raise Unrenderable("ONS in a rung that splits into several statements")
    return emissions


def _expr_key(expr: Expr) -> str:
    return formula.print_surface(expr)


# ---------------------------------------------------------------------------
# Action surface text
# ---------------------------------------------------------------------------


@dataclass
class _ActionText:
    lines: list[str]  # first line may be a block header; rest pre-indented one level
    inline: bool  # can take a trailing `when`/be used on a guard suffix line
    comment: str = ""  # informational suffix, appended after any guard


def _operand_surface(text: str) -> str:
    return formula.print_surface(formula.parse_operand(text))


def _generic_text(instr: Instr) -> str:
    return f"{instr.opcode}({', '.join(quote_operand(o) for o in instr.operands)})"


def _action_text(instr: Instr, meta, program: str) -> _ActionText:
    op = instr.opcode
    a = instr.operands
    if op == "MOV":
        return _ActionText([f"{a[1]} = {_operand_surface(a[0])}"], True)
    if op == "CPT":
        expr = formula.parse_formula(a[1])
        return _ActionText([f"{a[0]} = {formula.print_surface(expr)}"], True)
    if op in ("ADD", "SUB", "MUL", "DIV", "MOD"):
        sym = {"ADD": "+", "SUB": "-", "MUL": "*", "DIV": "/", "MOD": "mod"}[op]
        lhs = _operand_surface(a[0])
        rhs = _operand_surface(a[1])
        return _ActionText([f"{a[2]} = {lhs} {sym} {rhs}"], True)
    if op == "OTL":
        return _ActionText([f"latch {a[0]}"], True)
    if op == "OTU":
        return _ActionText([f"unlatch {a[0]}"], True)
    if op == "TON" and len(a) == 3:
        preset = meta.preset_ms(program, Ref(a[0]).base) if meta else None
        comment = f"  # preset {preset} ms" if preset is not None else ""
        return _ActionText([f"start_timer {a[0]}"], True, comment)
    if op == "CTU" and len(a) == 3:
        preset = meta.preset_ms(program, Ref(a[0]).base) if meta else None
        comment = f"  # preset {preset}" if preset is not None else ""
        return _ActionText([f"count_up {a[0]}"], True, comment)
    if op == "RES":
        return _ActionText([f"reset {a[0]}"], True)
    if op == "JSR" and len(a) == 2 and a[1] == "0":
        return _ActionText([f"call {a[0]}"], True)
    if op in SERVO_OPCODES and len(a) == 2:
        return _ActionText([f"{SERVO_OPCODES[op]} {a[0]} using {a[1]}"], True)
    motion = instr_to_surface(op, a)
    if motion is not None:
        keyword, header, pairs = motion
        width = max(len(k) for k, _ in pairs)
        lines = [f"{keyword} {header}:"]
        lines += [f"{INDENT}{k:<{width}} = {v}" for k, v in pairs]
        return _ActionText(lines, False)
    return _ActionText([_generic_text(instr)], True)


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------


@dataclass
class _Stmt:
    lines: list[str]
    refs: set[str] = field(default_factory=set)
    is_raw: bool = False
    rung_count: int = 1


def _refs_of_instrs(instrs: list[Instr]) -> set[str]:
    return referenced_tag_bases(RungIR(tuple(instrs)))


def _raw_stmt(rung: RungIR, pending: bool = False) -> _Stmt:
    from .emit_rllscrap import rung_text

    text = rung_text(rung)[:-1]  # drop the trailing ';'
    lines = []
    if pending:
        lines.append("# PENDING EDIT in Studio")
    lines.append(f"raw `{text}`")
    return _Stmt(lines, refs=referenced_tag_bases(rung), is_raw=True)


def _guard_suffix(enable: Expr) -> str:
    return "" if formula.is_true(enable) else f" when {formula.print_surface(enable)}"


def _statements_for_rung(rung: RungIR, meta, program: str) -> list[_Stmt]:
    stmts: list[_Stmt] = []
    nodes = rung.nodes

    # `label x` prefix
    while nodes and isinstance(nodes[0], Instr) and nodes[0].opcode == "LBL":
        stmts.append(_Stmt([f"label {nodes[0].operands[0]}"], rung_count=0))
        nodes = nodes[1:]
        if len(nodes) == 1 and isinstance(nodes[0], Instr) and nodes[0].opcode == "NOP":
            nodes = ()
    if not nodes:
        if stmts:
            stmts[-1].rung_count = 1
        return stmts

    emissions = _distribute(RungIR(nodes, rung.rung_type))
    if not emissions:
        raise Unrenderable("rung has no output instruction")

    # group consecutive emissions sharing an enable
    groups: list[tuple[Expr, list[Instr]]] = []
    for emission in emissions:
        if groups and _expr_key(groups[-1][0]) == _expr_key(emission.enable):
            groups[-1][1].append(emission.instr)
        else:
            groups.append((emission.enable, [emission.instr]))

    for enable, instrs in groups:
        # OTE renders as an assignment statement and stands alone
        chunk: list[Instr] = []
        for instr in instrs:
            if instr.opcode == "OTE":
                if chunk:
                    stmts.append(_group_stmt(enable, chunk, meta, program))
                    chunk = []
                expr_text = (
                    "on" if formula.is_true(enable) else formula.print_surface(enable)
                )
                stmts.append(
                    _Stmt(
                        [f"{instr.operands[0]} = {expr_text}"],
                        refs=formula.referenced_bases(enable)
                        | {Ref(instr.operands[0]).base},
                    )
                )
            else:
                chunk.append(instr)
        if chunk:
            stmts.append(_group_stmt(enable, chunk, meta, program))
    return stmts


def _group_stmt(enable: Expr, instrs: list[Instr], meta, program: str) -> _Stmt:
    refs = formula.referenced_bases(enable) | _refs_of_instrs(instrs)
    actions = [_action_text(i, meta, program) for i in instrs]
    if len(actions) == 1 and actions[0].inline:
        only = actions[0]
        return _Stmt([only.lines[0] + _guard_suffix(enable) + only.comment], refs=refs)
    header = (
        "always:"
        if formula.is_true(enable)
        else f"when {formula.print_surface(enable)}:"
    )
    lines = [header]
    for action in actions:
        lines += [INDENT + line for line in action.lines[:1]]
        lines[-1] += action.comment
        lines += [INDENT + line for line in action.lines[1:]]
    return _Stmt(lines, refs=refs)


# ---------------------------------------------------------------------------
# One-shot idiom recognition (on rising / on falling / on entry of)
# ---------------------------------------------------------------------------


def _sole_one_shot(rung: RungIR) -> tuple[str, str, str, list[Instr]] | None:
    """If the rung is `contacts... OSR/OSF(sb,ob)` with the one-shot as the
    only output: (opcode, sb, ob, condition instrs). Branches disqualify."""
    conditions: list[Instr] = []
    for i, node in enumerate(rung.nodes):
        if isinstance(node, BranchIR):
            return None
        if node.opcode in ("OSR", "OSF"):
            if i != len(rung.nodes) - 1 or len(node.operands) != 2:
                return None
            return node.opcode, node.operands[0], node.operands[1], conditions
        if node.opcode not in CONDITION_OPCODES or node.opcode in ("ONS", "LBL"):
            return None
        conditions.append(node)
    return None


def _gated_outputs(rung: RungIR, gate: list[str]) -> list[Instr] | None:
    """Outputs of a rung whose condition is exactly XIC(gate0) XIC(gate1)...
    followed only by plain output instructions."""
    nodes = rung.nodes
    if len(nodes) < len(gate) + 1:
        return None
    for i, tag in enumerate(gate):
        node = nodes[i]
        if (
            isinstance(node, BranchIR)
            or node.opcode != "XIC"
            or node.operands != (tag,)
        ):
            return None
    outputs: list[Instr] = []
    for node in nodes[len(gate) :]:
        if isinstance(node, BranchIR) or node.opcode in CONDITION_OPCODES:
            return None
        if node.opcode == "OTE":
            return None  # OTE has its own statement form; keep explicit
        outputs.append(node)
    return outputs or None


def _bit_references(routine: RoutineIR, name: str) -> int:
    count = 0
    for rung in routine.rungs:
        if name in referenced_tag_bases(rung):
            count += 1
    return count


@dataclass
class _OnItem:
    kind: str  # rising | falling | entry
    expr: Expr
    action_rungs: list[list[Instr]]
    span: int  # how many source rungs the idiom covers


def _recognize_on_block(routine: RoutineIR, index: int) -> _OnItem | None:
    rung = routine.rungs[index]
    if rung.rung_type != "N":
        return None
    shot = _sole_one_shot(rung)
    if shot is None:
        return None
    opcode, storage, edge, conditions = shot
    if not conditions:
        return None

    entry_tag = (
        conditions[0].operands[0]
        if len(conditions) == 1 and conditions[0].opcode == "XIC"
        else None
    )

    for kind, gate in (
        ("entry", [entry_tag, edge] if entry_tag else None),
        ("rising" if opcode == "OSR" else "falling", [edge]),
    ):
        if gate is None:
            continue
        action_rungs: list[list[Instr]] = []
        j = index + 1
        while j < len(routine.rungs) and routine.rungs[j].rung_type == "N":
            outputs = _gated_outputs(routine.rungs[j], [g for g in gate if g])
            if outputs is None:
                break
            action_rungs.append(outputs)
            j += 1
        if not action_rungs:
            continue
        # the bookkeeping bits may not appear anywhere outside the idiom
        span = j - index
        rest = RoutineIR(
            routine.program,
            routine.name,
            routine.rungs[:index] + routine.rungs[j:],
        )
        if _bit_references(rest, edge) or _bit_references(rest, storage):
            continue
        if any({edge, storage} & _refs_of_instrs(outs) for outs in action_rungs):
            continue
        if kind == "entry":
            expr: Expr = Ref(entry_tag)
        else:
            expr = simplify(formula.join([_instr_expr(c) for c in conditions], "and"))
        return _OnItem(kind, expr, action_rungs, span)
    return None


def _on_block_stmt(item: _OnItem, meta, program: str) -> _Stmt:
    if item.kind == "entry":
        header = f"on entry of {formula.print_surface(item.expr)}:"
    else:
        header = f"on {item.kind} {formula.print_surface(item.expr)}:"
    lines = [header]
    refs = formula.referenced_bases(item.expr)
    for outputs in item.action_rungs:
        refs |= _refs_of_instrs(outputs)
        for instr in outputs:
            action = _action_text(instr, meta, program)
            lines += [INDENT + line for line in action.lines[:1]]
            lines[-1] += action.comment
            lines += [INDENT + line for line in action.lines[1:]]
    return _Stmt(lines, refs=refs, rung_count=item.span)


# ---------------------------------------------------------------------------
# Routine rendering
# ---------------------------------------------------------------------------


def _uses_lines(refs: set[str], meta, program: str, warnings: list[str]) -> list[str]:
    controller: list[str] = []
    program_scope: list[str] = []
    module_io: list[str] = []
    unresolved: list[str] = []
    for base in sorted(refs, key=str.lower):
        if ":" in base:
            module_io.append(base)
            continue
        scope = meta.scope(program, base) if meta else None
        if scope == "program":
            program_scope.append(base)
        elif scope == "controller":
            controller.append(base)
        else:
            unresolved.append(base)

    lines: list[str] = []

    def emit(names: list[str], comment: str) -> None:
        out: list[str] = []
        for name in names:
            candidate = out + [name]
            if len("uses " + ", ".join(candidate)) > 96 and out:
                lines.append("uses " + ", ".join(out) + f"  # {comment}")
                out = [name]
            else:
                out = candidate
        if out:
            lines.append("uses " + ", ".join(out) + f"  # {comment}")

    if controller:
        emit(controller, "controller scope")
    if program_scope:
        emit(program_scope, "program scope")
    if module_io:
        emit(module_io, "module I/O")
    if unresolved:
        emit(unresolved, "UNRESOLVED: not in the tag JSON exports")
        warnings.append(f"{program}: unresolved tag(s) {', '.join(unresolved)}")
    return lines


def render_routine(routine: RoutineIR, meta=None) -> RenderResult:
    warnings: list[str] = []
    stmts: list[_Stmt] = []
    raw_rungs = 0
    pending_rungs = 0

    index = 0
    while index < len(routine.rungs):
        item = _recognize_on_block(routine, index)
        if item is not None:
            stmts.append(_on_block_stmt(item, meta, routine.program))
            index += item.span
            continue
        rung = routine.rungs[index]
        if rung.rung_type == "e":
            stmts.append(_raw_stmt(rung, pending=True))
            raw_rungs += 1
            pending_rungs += 1
            index += 1
            continue
        try:
            stmts.extend(_statements_for_rung(rung, meta, routine.program))
        except (Unrenderable, formula.FormulaError):
            stmts.append(_raw_stmt(rung))
            raw_rungs += 1
        index += 1

    refs: set[str] = set()
    for stmt in stmts:
        refs |= stmt.refs

    lines = [f"routine {routine.program}/{routine.name}", ""]
    uses = _uses_lines(refs, meta, routine.program, warnings)
    if uses:
        lines += uses
        lines.append("")
    if not stmts:
        lines.append("# (empty routine)")
    for i, stmt in enumerate(stmts):
        if i:
            lines.append("")
        lines += stmt.lines

    return RenderResult(
        text="\n".join(lines) + "\n",
        raw_rungs=raw_rungs,
        total_rungs=len(routine.rungs),
        pending_rungs=pending_rungs,
        warnings=warnings,
    )
