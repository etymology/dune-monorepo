"""Contact-network IR shared by both directions, plus a scan evaluator.

The IR mirrors rung text structure exactly: a rung is a sequence of
instructions and branch groups; a branch group is a list of parallel legs,
each itself a sequence. Nothing here knows about the .rung surface.

The evaluator executes one scan over a mutable tag valuation and records
the externally visible effects (used by ``equiv``):

- every store write (OTE/OTL/OTU/MOV/CPT/ADD/MOD/...),
- every *enabled* fire of an effectful instruction that the evaluator does
  not model as a store write (motion instructions, JSR, TON, PID, ...).

Approximations, shared by both sides of any comparison so they cancel out:

- ``JMP`` records a fire event but does not transfer control,
- ``TON``/``CTU`` record fires; timer/counter members are plain valuation
  entries (never advanced),
- type information is ignored; values are Python floats/ints keyed by the
  full operand path string (``x_axis_msf.DN`` is independent of
  ``x_axis_msf``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import formula
from .formula import Bin, Call, Expr, Num, Ref, Una

# ---------------------------------------------------------------------------
# IR nodes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Instr:
    opcode: str
    operands: tuple[str, ...]

    def text(self) -> str:
        return f"{self.opcode}({','.join(self.operands)})"


@dataclass(frozen=True)
class BranchIR:
    legs: tuple[tuple["Node", ...], ...]


Node = Instr | BranchIR


@dataclass(frozen=True)
class RungIR:
    nodes: tuple[Node, ...]
    rung_type: str = "N"  # "N" normal, "e" pending edit (Studio)


@dataclass(frozen=True)
class RoutineIR:
    program: str
    name: str
    rungs: tuple[RungIR, ...]


# ---------------------------------------------------------------------------
# Instruction classification
# ---------------------------------------------------------------------------

#: instructions that examine state and AND into the rung condition
CONDITION_OPCODES = {
    "XIC",
    "XIO",
    "CMP",
    "EQU",
    "NEQ",
    "GEQ",
    "GRT",
    "LEQ",
    "LES",
    "LIM",
    "AFI",
    "ONS",
    "LBL",  # passes condition through; only valid at rung start
}

#: comparator contacts (subset of the above)
COMPARE_OPCODES = set(formula.OPCODE_COMPARATOR)

#: output instructions the evaluator models as direct store writes
_WRITER_DEST = {
    "OTE": 0,
    "OTL": 0,
    "OTU": 0,
    "MOV": 1,
    "CPT": 0,
    "ADD": 2,
    "SUB": 2,
    "MUL": 2,
    "DIV": 2,
    "MOD": 2,
    "TRN": 1,
}

#: operand kinds per opcode, for tag extraction. kinds:
#:   ref    - always a tag path
#:   val    - tag path unless it parses as a number / '?' placeholder
#:   enum   - vendor enum/unit string, never a tag
#:   label  - JMP/LBL label or JSR routine name, never a tag
#:   expr   - Logix formula text
#: a trailing "*" repeats the last kind.
OPERAND_KINDS: dict[str, tuple[str, ...]] = {
    "XIC": ("ref",),
    "XIO": ("ref",),
    "OTE": ("ref",),
    "OTL": ("ref",),
    "OTU": ("ref",),
    "CMP": ("expr",),
    "CPT": ("ref", "expr"),
    "MOV": ("val", "ref"),
    "EQU": ("val", "val"),
    "NEQ": ("val", "val"),
    "GEQ": ("val", "val"),
    "GRT": ("val", "val"),
    "LEQ": ("val", "val"),
    "LES": ("val", "val"),
    "LIM": ("val", "val", "val"),
    "ADD": ("val", "val", "ref"),
    "SUB": ("val", "val", "ref"),
    "MUL": ("val", "val", "ref"),
    "DIV": ("val", "val", "ref"),
    "MOD": ("val", "val", "ref"),
    "TRN": ("val", "ref"),
    "ONS": ("ref",),
    "OSR": ("ref", "ref"),
    "OSF": ("ref", "ref"),
    "TON": ("ref", "val", "val"),
    "TOF": ("ref", "val", "val"),
    "RTO": ("ref", "val", "val"),
    "CTU": ("ref", "val", "val"),
    "CTD": ("ref", "val", "val"),
    "RES": ("ref",),
    "JSR": ("label", "val"),
    "JMP": ("label",),
    "LBL": ("label",),
    "NOP": (),
    "AFI": (),
    "MSO": ("ref", "ref"),
    "MSF": ("ref", "ref"),
    "MAFR": ("ref", "ref"),
    "MAS": ("ref", "ref", "enum", "enum", "val", "enum", "enum", "val", "enum"),
    "MAM": (
        "ref",
        "ref",
        "val",
        "val",
        "val",
        "enum",
        "val",
        "enum",
        "val",
        "enum",
        "enum",
        "val",
        "val",
        "enum",
        "val",
        "val",
        "val",
        "val",
        "val",
        "val",
    ),
    "MAJ": (
        "ref",
        "ref",
        "val",
        "val",
        "enum",
        "val",
        "enum",
        "val",
        "enum",
        "enum",
        "val",
        "val",
        "enum",
        "val",
        "val",
        "val",
        "val",
    ),
    "MAR": ("ref", "ref", "enum", "enum", "val", "val", "val"),
    "MRP": ("ref", "ref", "enum", "enum", "val"),
    "MCS": ("ref", "ref", "enum", "enum", "val", "enum", "enum", "val", "enum"),
    "MCLM": (
        "ref",
        "ref",
        "val",
        "val",
        "val",
        "enum",
        "val",
        "enum",
        "val",
        "enum",
        "enum",
        "val",
        "val",
        "enum",
        "val",
        "enum",
        "enum",
        "val",
        "val",
        "enum",
        "val",
        "val",
    ),
    "MCCM": (
        "ref",
        "ref",
        "val",
        "val",
        "val",
        "val",
        "val",
        "val",
        "enum",
        "val",
        "enum",
        "val",
        "enum",
        "enum",
        "val",
        "val",
        "enum",
        "val",
        "enum",
        "enum",
        "val",
        "val",
        "enum",
        "val",
        "val",
    ),
    "MCCD": (
        "ref",
        "ref",
        "enum",
        "enum",
        "val",
        "enum",
        "enum",
        "val",
        "enum",
        "enum",
        "val",
        "enum",
        "enum",
        "val",
        "enum",
        "val",
        "enum",
        "enum",
    ),
    "PID": ("ref", "val", "val", "val", "val", "val", "val"),
    "COP": ("ref", "ref", "val"),
    "FLL": ("val", "ref", "val"),
    "FFL": ("val", "ref", "ref", "val", "val"),
    "FFU": ("ref", "ref", "ref", "val", "val"),
    "SFX": ("ref", "enum", "val*"),
    "SLS": ("ref", "enum", "enum", "val*"),
}

#: vendor enum/unit literals that look like identifiers
ENUM_WORDS = {
    "Yes",
    "No",
    "All",
    "None",
    "Disabled",
    "Enabled",
    "Programmed",
    "Current",
    "Forward",
    "Reverse",
    "Jog",
    "Move",
    "Time",
    "Seconds",
    "Immediate",
}


def operand_kinds(opcode: str, count: int) -> tuple[str, ...]:
    kinds = OPERAND_KINDS.get(opcode)
    if kinds is None:
        return ("val",) * count
    if kinds and kinds[-1].endswith("*"):
        base = kinds[:-1] + (kinds[-1][:-1],) * max(0, count - len(kinds) + 1)
        return base[:count]
    return kinds[:count] + ("val",) * max(0, count - len(kinds))


def _looks_numeric(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def operand_is_ref(opcode: str, index: int, operand: str, count: int) -> bool:
    """Is this operand a tag reference (for scope checks / uses lines)?"""
    operand = operand.strip()
    if not operand or operand == "?" or operand.startswith('"'):
        return False
    kind = operand_kinds(opcode, count)[index] if index < count else "val"
    if kind in ("enum", "label"):
        return False
    if kind == "expr":
        return False  # handled by formula parsing
    if kind == "ref":
        return True
    # val: tag path unless numeric or a known enum word / spaced string
    if _looks_numeric(operand) or " " in operand or operand in ENUM_WORDS:
        return False
    return operand[0].isalpha() or operand[0] == "_"


def referenced_tag_bases(rung: RungIR) -> set[str]:
    """All tag base names a rung references (conditions, formulas, operands)."""
    bases: set[str] = set()

    def visit(nodes: tuple[Node, ...]) -> None:
        for node in nodes:
            if isinstance(node, BranchIR):
                for leg in node.legs:
                    visit(leg)
                continue
            count = len(node.operands)
            kinds = operand_kinds(node.opcode, count)
            for i, op in enumerate(node.operands):
                if i < len(kinds) and kinds[i] == "expr":
                    bases.update(formula.referenced_bases(formula.parse_formula(op)))
                elif operand_is_ref(node.opcode, i, op, count):
                    bases.add(Ref(op.strip()).base)

    visit(rung.nodes)
    return bases


# ---------------------------------------------------------------------------
# Scan evaluator
# ---------------------------------------------------------------------------


@dataclass
class ScanResult:
    store: dict[str, float]
    fires: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)


class EvalError(ValueError):
    pass


class Evaluator:
    """Executes one scan of a routine over a mutable valuation."""

    def __init__(self, store: dict[str, float]):
        self.store = store
        self.fires: list[tuple[str, tuple[str, ...]]] = []
        self.writes: set[str] = set()

    # -- value access -------------------------------------------------------

    def _read(self, path: str) -> float:
        return self.store.get(path.strip(), 0.0)

    def _write(self, path: str, value: float) -> None:
        path = path.strip()
        self.writes.add(path)
        self.store[path] = value

    def _value(self, expr: Expr) -> float:
        if isinstance(expr, Num):
            return float(expr.text)
        if isinstance(expr, Ref):
            return self._read(expr.text)
        if isinstance(expr, Una):
            if expr.op == "-":
                return -self._value(expr.operand)
            return 0.0 if self._truth(expr) else 1.0  # not
        if isinstance(expr, Bin):
            if expr.op in formula.COMPARATORS or expr.op in ("and", "or"):
                return 1.0 if self._truth(expr) else 0.0
            lhs = self._value(expr.lhs)
            rhs = self._value(expr.rhs)
            if expr.op == "+":
                return lhs + rhs
            if expr.op == "-":
                return lhs - rhs
            if expr.op == "*":
                return lhs * rhs
            if expr.op == "/":
                return lhs / rhs if rhs != 0 else 0.0
            if expr.op == "MOD":
                return lhs % rhs if rhs != 0 else 0.0
            raise EvalError(f"operator {expr.op!r}")
        if isinstance(expr, Call):
            import math

            args = [self._value(a) for a in expr.args]
            table = {
                "ABS": lambda: abs(args[0]),
                "SQR": lambda: math.sqrt(abs(args[0])),
                "SIN": lambda: math.sin(args[0]),
                "COS": lambda: math.cos(args[0]),
                "TAN": lambda: math.tan(args[0]),
                "ATN": lambda: math.atan(args[0]),
                "ASN": lambda: math.asin(max(-1.0, min(1.0, args[0]))),
                "ACS": lambda: math.acos(max(-1.0, min(1.0, args[0]))),
                "LN": lambda: math.log(args[0]) if args[0] > 0 else 0.0,
                "LOG": lambda: math.log10(args[0]) if args[0] > 0 else 0.0,
                "TRN": lambda: float(int(args[0])),
                "TRUE": lambda: 1.0,
                "FALSE": lambda: 0.0,
            }
            fn = table.get(expr.func)
            if fn is None:
                raise EvalError(f"function {expr.func!r}")
            return fn()
        raise EvalError(f"expr node {expr!r}")

    def _truth(self, expr: Expr) -> bool:
        if isinstance(expr, Bin) and expr.op in formula.COMPARATORS:
            lhs = self._value(expr.lhs)
            rhs = self._value(expr.rhs)
            return {
                "=": lhs == rhs,
                "<>": lhs != rhs,
                "<": lhs < rhs,
                ">": lhs > rhs,
                "<=": lhs <= rhs,
                ">=": lhs >= rhs,
            }[expr.op]
        if isinstance(expr, Bin) and expr.op == "and":
            lhs = self._truth(expr.lhs)
            rhs = self._truth(expr.rhs)
            return lhs and rhs
        if isinstance(expr, Bin) and expr.op == "or":
            lhs = self._truth(expr.lhs)
            rhs = self._truth(expr.rhs)
            return lhs or rhs
        if isinstance(expr, Una) and expr.op == "not":
            return not self._truth(expr.operand)
        return self._value(expr) != 0

    # -- instruction execution ----------------------------------------------

    def _exec_instr(self, instr: Instr, cond: bool) -> bool:
        """Execute one instruction; returns the rung condition after it."""
        op = instr.opcode
        a = instr.operands

        if op == "XIC":
            return cond and self._read(a[0]) != 0
        if op == "XIO":
            return cond and self._read(a[0]) == 0
        if op == "CMP":
            return cond and self._truth(formula.parse_formula(a[0]))
        if op in COMPARE_OPCODES:
            comparator = formula.OPCODE_COMPARATOR[op]
            expr = Bin(
                comparator, formula.parse_operand(a[0]), formula.parse_operand(a[1])
            )
            return cond and self._truth(expr)
        if op == "LIM":
            low = self._value(formula.parse_operand(a[0]))
            test = self._value(formula.parse_operand(a[1]))
            high = self._value(formula.parse_operand(a[2]))
            if low <= high:
                ok = low <= test <= high
            else:
                ok = test >= low or test <= high
            return cond and ok
        if op == "AFI":
            return False
        if op == "LBL":
            return cond
        if op == "ONS":
            prev = self._read(a[0])
            self._write(a[0], 1.0 if cond else 0.0)
            return cond and prev == 0

        # outputs ------------------------------------------------------------
        if op == "OTE":
            self._write(a[0], 1.0 if cond else 0.0)
            return cond
        if op == "OTL":
            if cond:
                self._write(a[0], 1.0)
            return cond
        if op == "OTU":
            if cond:
                self._write(a[0], 0.0)
            return cond
        if op == "OSR":
            prev = self._read(a[0])
            self._write(a[1], 1.0 if cond and prev == 0 else 0.0)
            self._write(a[0], 1.0 if cond else 0.0)
            return cond
        if op == "OSF":
            prev = self._read(a[0])
            self._write(a[1], 1.0 if not cond and prev != 0 else 0.0)
            self._write(a[0], 1.0 if cond else 0.0)
            return cond
        if op == "MOV":
            if cond:
                self._write(a[1], self._value(formula.parse_operand(a[0])))
            return cond
        if op == "CPT":
            if cond:
                self._write(a[0], self._value(formula.parse_formula(a[1])))
            return cond
        if op in ("ADD", "SUB", "MUL", "DIV", "MOD"):
            if cond:
                lhs = self._value(formula.parse_operand(a[0]))
                rhs = self._value(formula.parse_operand(a[1]))
                value = {
                    "ADD": lhs + rhs,
                    "SUB": lhs - rhs,
                    "MUL": lhs * rhs,
                    "DIV": lhs / rhs if rhs != 0 else 0.0,
                    "MOD": lhs % rhs if rhs != 0 else 0.0,
                }[op]
                self._write(a[2], value)
            return cond
        if op == "TRN":
            if cond:
                self._write(a[1], float(int(self._value(formula.parse_operand(a[0])))))
            return cond
        if op == "NOP":
            return cond

        # everything else: record an enabled fire, leave condition unchanged
        if cond:
            self.fires.append((op, instr.operands))
        return cond

    def _exec_nodes(self, nodes: tuple[Node, ...], cond: bool) -> bool:
        for node in nodes:
            if isinstance(node, BranchIR):
                out = False
                for leg in node.legs:
                    out = self._exec_nodes(leg, cond) or out
                cond = out
            else:
                cond = self._exec_instr(node, cond)
        return cond

    def scan(self, routine: RoutineIR) -> None:
        for rung in routine.rungs:
            self._exec_nodes(rung.nodes, True)


def all_instructions(rung: RungIR):
    def visit(nodes: tuple[Node, ...]):
        for node in nodes:
            if isinstance(node, BranchIR):
                for leg in node.legs:
                    yield from visit(leg)
            else:
                yield node

    yield from visit(rung.nodes)
