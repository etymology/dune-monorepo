"""AST for the .rung surface language."""

from __future__ import annotations

from dataclasses import dataclass, field

from .formula import Expr


@dataclass(frozen=True)
class TagDecl:
    """``local <type> <name>[dims] [preset Nms]`` or a ``uses`` entry."""

    name: str
    type: str | None = None  # bool|int|dint|real|motion|timer|counter (local only)
    dims: int | None = None
    preset_ms: int | None = None


class Action:
    __slots__ = ()


@dataclass(frozen=True)
class AssignAction(Action):
    """``target = expr`` as a value write (MOV/CPT)."""

    target: str
    expr: Expr


@dataclass(frozen=True)
class GenericAction(Action):
    """Verbatim instruction call: ``MCS(X_Y, ctl, "All", ...)``."""

    opcode: str
    operands: tuple[str, ...]


@dataclass(frozen=True)
class ServoAction(Action):
    keyword: str  # servo_on | servo_off | fault_reset
    axis: str
    control: str


@dataclass(frozen=True)
class MotionAction(Action):
    keyword: str  # move_axis | coordinated_move
    target: str
    control: str
    pairs: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class TimerAction(Action):
    keyword: str  # start_timer | count_up | reset
    tag: str


@dataclass(frozen=True)
class CallAction(Action):
    routine: str


@dataclass(frozen=True)
class LatchAction(Action):
    keyword: str  # latch | unlatch
    target: str


class Stmt:
    __slots__ = ()


@dataclass(frozen=True)
class LetStmt(Stmt):
    name: str
    expr: Expr


@dataclass(frozen=True)
class BoolAssignStmt(Stmt):
    """``target = <bool-expr>`` -> contacts + OTE (one rung)."""

    target: str
    expr: Expr


@dataclass(frozen=True)
class GuardedStmt(Stmt):
    """``<action> when <expr>`` / bare action; guard None = unconditional."""

    action: Action
    guard: Expr | None


@dataclass(frozen=True)
class WhenBlock(Stmt):
    """``when <expr>:`` / ``always:`` with several actions -> one rung."""

    guard: Expr | None
    actions: tuple[Action, ...]


@dataclass(frozen=True)
class OnBlock(Stmt):
    """``on rising/falling <expr>:`` / ``on entry of <tag>:``.

    An optional ``using <storage>, <edge>`` clause pins the one-shot's
    bookkeeping bits to specific names (the renderer emits it to preserve
    hand-named bits through a recompile); when absent, lowering invents
    informative names from the trigger.
    """

    kind: str  # rising | falling | entry
    expr: Expr
    actions: tuple[Action, ...]
    storage: str | None = None  # OSR/OSF storage bit (internal one-shot state)
    edge: str | None = None  # the output bit that pulses for one scan


@dataclass(frozen=True)
class RawStmt(Stmt):
    text: str
    pending: bool = False


@dataclass(frozen=True)
class LabelStmt(Stmt):
    name: str


@dataclass(frozen=True)
class RoutineAST:
    program: str
    routine: str
    uses: tuple[TagDecl, ...] = ()
    locals: tuple[TagDecl, ...] = ()
    statements: tuple[Stmt, ...] = ()
    unresolved_uses: tuple[str, ...] = field(default=())
