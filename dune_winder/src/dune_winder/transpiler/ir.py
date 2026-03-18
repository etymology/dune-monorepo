"""Intermediate representation (IR) for the Python→Ladder Logic transpiler.

All expression nodes carry an optional `typ` (PLCType) filled in by py_to_ir.
All statement nodes have a `reg_map` available from the enclosing Routine scope.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Union
from .types import PLCType, Reg, SegField

# ---------------------------------------------------------------------------
# Expression nodes
# ---------------------------------------------------------------------------

@dataclass
class Const:
    """Numeric or bool literal."""
    value: float | int | bool
    typ: PLCType = PLCType.REAL

    def __str__(self) -> str:
        if self.typ == PLCType.BOOL:
            return "1" if self.value else "0"
        if self.typ == PLCType.DINT:
            return str(int(self.value))
        # REAL
        v = float(self.value)
        if v == float("inf"):
            return "3.4028235E+38"
        if v == float("-inf"):
            return "-3.4028235E+38"
        return repr(v)


@dataclass
class RegExpr:
    """A register reference used as an expression."""
    reg: Reg
    typ: PLCType = field(init=False)

    def __post_init__(self) -> None:
        self.typ = self.reg.typ

    def __str__(self) -> str:
        return str(self.reg)


@dataclass
class SegFieldExpr:
    """SegQueue[reg].Field used as an expression."""
    sf: SegField
    typ: PLCType = PLCType.REAL

    def __str__(self) -> str:
        return str(self.sf)


@dataclass
class BinOp:
    left: "Expr"
    op: str   # "+", "-", "*", "/", "%", "**"
    right: "Expr"
    typ: PLCType = PLCType.REAL

    def __str__(self) -> str:
        return f"{self.left}{self.op}{self.right}"


@dataclass
class UnaryOp:
    op: str   # "-", "not"
    operand: "Expr"
    typ: PLCType = PLCType.REAL

    def __str__(self) -> str:
        if self.op == "-":
            return f"-{self.operand}"
        return f"NOT({self.operand})"


@dataclass
class CptCall:
    """A builtin that maps directly to a single CPT function: ABS, SQR, SIN, COS, ATN, TRUNC."""
    func: str
    args: list["Expr"]
    typ: PLCType = PLCType.REAL

    def __str__(self) -> str:
        args_str = ",".join(str(a) for a in self.args)
        if self.func == "SQR_HYPOT":
            # math.hypot(a, b) → SQR(a*a+b*b)
            a, b = self.args
            return f"SQR({a}*{a}+{b}*{b})"
        return f"{self.func}({args_str})"


# Expr is a union of all expression types
Expr = Union[Const, RegExpr, SegFieldExpr, BinOp, UnaryOp, CptCall]

# ---------------------------------------------------------------------------
# Condition nodes  (used as contacts on rungs)
# ---------------------------------------------------------------------------

@dataclass
class Cmp:
    """EQU/NEQ/LES/LEQ/GRT/GEQ a b"""
    op: str   # "==", "!=", "<", "<=", ">", ">="
    left: Expr
    right: Expr

    @property
    def instr(self) -> str:
        return {"==": "EQU", "!=": "NEQ", "<": "LES", "<=": "LEQ",
                ">": "GRT", ">=": "GEQ"}[self.op]

    def negated(self) -> "Cmp":
        inv = {"==": "!=", "!=": "==", "<": ">=", "<=": ">", ">": "<=", ">=": "<"}
        return Cmp(inv[self.op], self.left, self.right)

    def __str__(self) -> str:
        return f"{self.instr} {self.left} {self.right}"


@dataclass
class XicCond:
    """XIC bit — examine if closed."""
    reg: Reg | SegField

    def __str__(self) -> str:
        return f"XIC {self.reg}"

    def negated(self) -> "XioCond":
        return XioCond(self.reg)


@dataclass
class XioCond:
    """XIO bit — examine if open."""
    reg: Reg | SegField

    def __str__(self) -> str:
        return f"XIO {self.reg}"

    def negated(self) -> XicCond:
        return XicCond(self.reg)


@dataclass
class AndCond:
    """Series (AND) of conditions — all must be true."""
    parts: list["Condition"]

    def negated(self) -> "OrCond":
        return OrCond([p.negated() for p in self.parts])


@dataclass
class OrCond:
    """Parallel (OR) of conditions — at least one must be true.
    Emitted as BST ... NXB ... BND OTL BOOLS[k]."""
    parts: list["Condition"]

    def negated(self) -> AndCond:
        return AndCond([p.negated() for p in self.parts])


@dataclass
class IsInf:
    """math.isinf(x) — GEQ ABS(x) 3.4028235E+38"""
    expr: Expr

    def negated(self) -> "IsNotInf":
        return IsNotInf(self.expr)


@dataclass
class IsNotInf:
    expr: Expr

    def negated(self) -> IsInf:
        return IsInf(self.expr)


Condition = Union[Cmp, XicCond, XioCond, AndCond, OrCond, IsInf, IsNotInf]

# ---------------------------------------------------------------------------
# Statement (IR node) types
# ---------------------------------------------------------------------------

@dataclass
class Assign:
    """dest = expr  →  MOV or CPT rung."""
    dest: Reg | SegField
    expr: Expr


@dataclass
class SetBool:
    """OTL / OTU a BOOL register."""
    reg: Reg
    value: bool   # True = OTL, False = OTU


@dataclass
class If:
    cond: Condition
    then_body: list["IRNode"]
    else_body: list["IRNode"] = field(default_factory=list)


@dataclass
class Loop:
    """Counted loop: MOV 0 counter; LBL; GEQ counter limit JMP end; body; ADD 1; JMP; LBL."""
    counter: Reg                    # DINTS[n]
    limit: "Reg | Const | RegExpr"  # exclusive upper bound
    body: list["IRNode"]


@dataclass
class JSRCall:
    """Jump to subroutine: pre-load args → JSR → read return regs."""
    routine: str
    # Each item: (dest_reg_in_callee, value_expr_from_caller)
    in_args: list[tuple[Reg, Expr]]
    # Each item: (src_reg_in_callee, dest_reg_in_caller)
    out_args: list[tuple[Reg, Reg]]


@dataclass
class Return:
    """Non-tail return: write value to output register, jump to routine end."""
    value: Expr | None
    out_reg: Reg | None         # where to write the value
    end_label: str


@dataclass
class Fault:
    """raise ValueError(...) → OTL fault_bool, JMP end."""
    fault_reg: Reg
    end_label: str


@dataclass
class Comment:
    text: str


IRNode = Union[Assign, SetBool, If, Loop, JSRCall, Return, Fault, Comment]


@dataclass
class Routine:
    name: str
    # input parameter regs (for JSR calling convention documentation)
    in_params: list[tuple[str, Reg]]
    # output return regs
    out_params: list[tuple[str, Reg]]
    body: list[IRNode]
    # human-readable register allocation summary lines
    alloc_comments: list[str] = field(default_factory=list)
