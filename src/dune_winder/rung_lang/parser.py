"""Hand-written parser for the .rung surface language.

Line-oriented with indentation blocks (4 spaces per level). A physical
line continues the previous one while parentheses are unbalanced, or when
a deeper-indented line follows a statement line that does not open a
block (no trailing ``:``). ``#`` starts a comment; a comment containing
``PENDING EDIT`` marks the following statement as a pending Studio edit
(``rung-compile`` refuses those routines).
"""

from __future__ import annotations

import re

from . import ast as rast
from . import formula
from .formula import parse_surface_expr
from .schema import MOTION_KEYWORDS, SERVO_KEYWORDS, unquote_operand

LOCAL_TYPES = {"bool", "int", "dint", "real", "motion", "timer", "counter"}
PENDING_MARK = "PENDING EDIT"

_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_NAME_RE = re.compile(_NAME + r"\Z")
#: a uses entry may be a module-qualified base like ``Local:1:I``
_USES_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_:]*\Z")
_DECL_RE = re.compile(rf"({_NAME})(?:\[(\d+)\])?\Z")
_GENERIC_RE = re.compile(r"([A-Z][A-Z0-9_]*)\((.*)\)\Z", re.DOTALL)


class RungSyntaxError(ValueError):
    def __init__(self, message: str, line_no: int | None = None):
        prefix = f"line {line_no}: " if line_no else ""
        super().__init__(prefix + message)
        self.line_no = line_no


def _strip_comment(text: str) -> tuple[str, str | None]:
    """Remove a trailing comment, respecting quotes and raw backticks."""
    in_quote = False
    in_tick = False
    for i, ch in enumerate(text):
        if ch == '"' and not in_tick:
            in_quote = not in_quote
        elif ch == "`" and not in_quote:
            in_tick = not in_tick
        elif ch == "#" and not in_quote and not in_tick:
            return text[:i].rstrip(), text[i + 1 :].strip()
    return text.rstrip(), None


def _paren_balance(text: str) -> int:
    depth = 0
    in_quote = False
    for ch in text:
        if ch == '"':
            in_quote = not in_quote
        elif not in_quote and ch in "([":
            depth += 1
        elif not in_quote and ch in ")]":
            depth -= 1
    return depth


def _split_top_level(text: str, sep: str) -> list[str]:
    """Split on a separator word/char at paren depth 0, outside quotes."""
    parts: list[str] = []
    depth = 0
    in_quote = False
    i = 0
    start = 0
    is_word = sep.isalpha()
    while i < len(text):
        ch = text[i]
        if ch == '"':
            in_quote = not in_quote
        elif not in_quote and ch in "([":
            depth += 1
        elif not in_quote and ch in ")]":
            depth -= 1
        elif not in_quote and depth == 0:
            if is_word:
                if (
                    text.startswith(sep, i)
                    and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] == "_"))
                    and not (
                        i + len(sep) < len(text)
                        and (text[i + len(sep)].isalnum() or text[i + len(sep)] == "_")
                    )
                ):
                    parts.append(text[start:i])
                    start = i + len(sep)
                    i += len(sep)
                    continue
            elif ch == sep:
                parts.append(text[start:i])
                start = i + 1
        i += 1
    parts.append(text[start:])
    return parts


def _split_operands(text: str) -> tuple[str, ...]:
    if not text.strip():
        return ()
    return tuple(unquote_operand(p) for p in _split_top_level(text, ","))


class _Line:
    __slots__ = ("indent", "text", "no", "pending")

    def __init__(self, indent: int, text: str, no: int, pending: bool):
        self.indent = indent
        self.text = text
        self.no = no
        self.pending = pending


def _logical_lines(source: str) -> list[_Line]:
    physical: list[tuple[int, str, int, str | None]] = []
    for no, raw in enumerate(source.splitlines(), start=1):
        code, comment = _strip_comment(raw)
        if not code.strip():
            if comment is not None:
                physical.append((0, "", no, comment))
            continue
        indent = len(code) - len(code.lstrip(" "))
        physical.append((indent, code.strip(), no, comment))

    lines: list[_Line] = []
    pending_next = False
    i = 0
    while i < len(physical):
        indent, text, no, comment = physical[i]
        if comment is not None and PENDING_MARK in comment:
            pending_next = True
        if not text:
            i += 1
            continue
        # join continuations
        while i + 1 < len(physical):
            n_indent, n_text, _n_no, n_comment = physical[i + 1]
            if not n_text:
                break
            if _paren_balance(text) > 0 or (
                n_indent > indent and not text.endswith(":")
            ):
                text = text + " " + n_text
                if n_comment is not None and PENDING_MARK in n_comment:
                    pending_next = True
                i += 1
                continue
            break
        lines.append(_Line(indent, text, no, pending_next))
        pending_next = False
        i += 1
    return lines


def parse_rung_source(source: str) -> rast.RoutineAST:
    lines = _logical_lines(source)
    if not lines or not lines[0].text.startswith("routine "):
        raise RungSyntaxError("file must start with 'routine <program>/<routine>'")
    head = lines[0].text[len("routine ") :].strip()
    if "/" not in head:
        raise RungSyntaxError("routine header must be <program>/<routine>", lines[0].no)
    program, routine = (part.strip() for part in head.split("/", 1))

    uses: list[rast.TagDecl] = []
    locals_: list[rast.TagDecl] = []
    statements: list[rast.Stmt] = []
    lets: dict[str, formula.Expr] = {}

    pos = 1
    while pos < len(lines):
        line = lines[pos]
        if line.indent != 0:
            raise RungSyntaxError(f"unexpected indent for {line.text!r}", line.no)
        first = line.text.split(None, 1)[0]
        if first == "uses":
            uses.extend(_parse_uses(line))
            pos += 1
        elif first == "local":
            locals_.extend(_parse_local(line))
            pos += 1
        elif first == "let":
            name, expr = _parse_let(line, lets)
            lets[name] = expr
            pos += 1
        else:
            stmt, pos = _parse_statement(lines, pos, lets)
            statements.append(stmt)

    return rast.RoutineAST(
        program=program,
        routine=routine,
        uses=tuple(uses),
        locals=tuple(locals_),
        statements=tuple(statements),
    )


def _parse_uses(line: _Line) -> list[rast.TagDecl]:
    body = line.text[len("uses") :].strip()
    decls = []
    for name in body.split(","):
        name = name.strip()
        if not _USES_RE.match(name):
            raise RungSyntaxError(f"bad tag name {name!r} in uses", line.no)
        decls.append(rast.TagDecl(name))
    return decls


def _parse_local(line: _Line) -> list[rast.TagDecl]:
    parts = line.text.split(None, 2)
    if len(parts) < 3 or parts[1] not in LOCAL_TYPES:
        raise RungSyntaxError(
            f"expected 'local <{'|'.join(sorted(LOCAL_TYPES))}> <name>...'", line.no
        )
    type_ = parts[1]
    rest = parts[2]
    preset: int | None = None
    match = re.search(r"\bpreset\s+(\d+)\s*ms\Z", rest)
    if match:
        preset = int(match.group(1))
        rest = rest[: match.start()].rstrip().rstrip(",")
    decls = []
    for item in rest.split(","):
        item = item.strip()
        m = _DECL_RE.match(item)
        if not m:
            raise RungSyntaxError(f"bad local declaration {item!r}", line.no)
        decls.append(
            rast.TagDecl(
                m.group(1),
                type=type_,
                dims=int(m.group(2)) if m.group(2) else None,
                preset_ms=preset,
            )
        )
    if preset is not None and type_ not in ("timer", "counter"):
        raise RungSyntaxError("preset only applies to timer/counter locals", line.no)
    return decls


def _parse_let(line: _Line, lets: dict[str, formula.Expr]) -> tuple[str, formula.Expr]:
    body = line.text[len("let") :].strip()
    if "=" not in body:
        raise RungSyntaxError("expected 'let <name> = <expr>'", line.no)
    name, expr_text = body.split("=", 1)
    name = name.strip()
    if not _NAME_RE.match(name):
        raise RungSyntaxError(f"bad let name {name!r}", line.no)
    expr = _substitute(parse_surface_expr(expr_text.strip()), lets)
    return name, expr


def _substitute(expr: formula.Expr, lets: dict[str, formula.Expr]) -> formula.Expr:
    if not lets:
        return expr
    if isinstance(expr, formula.Ref) and expr.text in lets:
        return lets[expr.text]
    if isinstance(expr, formula.Una):
        return formula.Una(expr.op, _substitute(expr.operand, lets))
    if isinstance(expr, formula.Bin):
        return formula.Bin(
            expr.op, _substitute(expr.lhs, lets), _substitute(expr.rhs, lets)
        )
    if isinstance(expr, formula.Call):
        return formula.Call(expr.func, tuple(_substitute(a, lets) for a in expr.args))
    return expr


def _parse_expr(text: str, lets: dict[str, formula.Expr], line: _Line) -> formula.Expr:
    try:
        return _substitute(parse_surface_expr(text), lets)
    except formula.FormulaError as exc:
        raise RungSyntaxError(str(exc), line.no) from exc


def _parse_statement(
    lines: list[_Line], pos: int, lets: dict[str, formula.Expr]
) -> tuple[rast.Stmt, int]:
    line = lines[pos]
    text = line.text
    first = text.split(None, 1)[0]

    if first == "raw":
        body = text[len("raw") :].strip()
        if len(body) < 2 or body[0] != "`" or body[-1] != "`":
            raise RungSyntaxError("raw statement must be raw `...`", line.no)
        return rast.RawStmt(body[1:-1].strip(), pending=line.pending), pos + 1

    if first == "label":
        name = text[len("label") :].strip()
        if not _NAME_RE.match(name):
            raise RungSyntaxError(f"bad label name {name!r}", line.no)
        return rast.LabelStmt(name), pos + 1

    if first == "always:" or (first == "always" and text.rstrip().endswith(":")):
        actions, pos = _parse_action_block(lines, pos, lets)
        return rast.WhenBlock(None, actions), pos

    if first == "when":
        header = text[len("when") :].strip()
        if not header.endswith(":"):
            raise RungSyntaxError("when block header must end with ':'", line.no)
        guard = _parse_expr(header[:-1].strip(), lets, line)
        actions, pos = _parse_action_block(lines, pos, lets)
        return rast.WhenBlock(guard, actions), pos

    if first == "on":
        rest = text[len("on") :].strip()
        if not rest.endswith(":"):
            raise RungSyntaxError("on block header must end with ':'", line.no)
        rest = rest[:-1].strip()
        if rest.startswith("entry of "):
            kind, expr_text = "entry", rest[len("entry of ") :]
            if not _NAME_RE.match(expr_text.strip()):
                raise RungSyntaxError("'on entry of' takes a single bool tag", line.no)
        elif rest.startswith("rising "):
            kind, expr_text = "rising", rest[len("rising ") :]
        elif rest.startswith("falling "):
            kind, expr_text = "falling", rest[len("falling ") :]
        else:
            raise RungSyntaxError("expected 'on rising/falling/entry of'", line.no)
        expr = _parse_expr(expr_text.strip(), lets, line)
        actions, pos = _parse_action_block(lines, pos, lets)
        return rast.OnBlock(kind, expr, actions), pos

    # single statement: action [when guard] | target = expr [when guard]
    parts = _split_top_level(text, "when")
    guard: formula.Expr | None = None
    body = parts[0].strip()
    if len(parts) == 2:
        guard = _parse_expr(parts[1].strip(), lets, line)
    elif len(parts) > 2:
        raise RungSyntaxError("more than one 'when' in statement", line.no)

    action, opened_block = _parse_action(
        body, line, lets, allow_block_header=guard is None
    )
    if opened_block:
        # motion action with a key block, optionally `... when guard` is not
        # supported on block actions; the guard belongs in a when block.
        pairs, pos = _parse_key_block(lines, pos)
        assert isinstance(action, rast.MotionAction)
        action = rast.MotionAction(action.keyword, action.target, action.control, pairs)
        return rast.GuardedStmt(action, None), pos

    if (
        guard is None
        and isinstance(action, rast.AssignAction)
        and _is_boolean_expr(action.expr)
    ):
        return rast.BoolAssignStmt(action.target, action.expr), pos + 1
    return rast.GuardedStmt(action, guard), pos + 1


def _is_boolean_expr(expr: formula.Expr) -> bool:
    if isinstance(expr, formula.Bin):
        return expr.op in ("and", "or") or expr.op in formula.COMPARATORS
    if isinstance(expr, formula.Una):
        return expr.op == "not"
    if isinstance(expr, formula.Call):
        return expr.func in ("TRUE", "FALSE", "LIM", "AFI", "ONS")
    return False


def _parse_action_block(
    lines: list[_Line], pos: int, lets: dict[str, formula.Expr]
) -> tuple[tuple[rast.Action, ...], int]:
    header = lines[pos]
    body_indent: int | None = None
    actions: list[rast.Action] = []
    pos += 1
    while pos < len(lines):
        line = lines[pos]
        if line.indent <= header.indent:
            break
        if body_indent is None:
            body_indent = line.indent
        if line.indent < body_indent:
            break
        if line.indent > body_indent:
            raise RungSyntaxError("unexpected indent inside block", line.no)
        action, opened_block = _parse_action(
            line.text, line, lets, allow_block_header=True
        )
        if opened_block:
            pairs, pos = _parse_key_block(lines, pos)
            assert isinstance(action, rast.MotionAction)
            action = rast.MotionAction(
                action.keyword, action.target, action.control, pairs
            )
        else:
            pos += 1
        actions.append(action)
    if not actions:
        raise RungSyntaxError("empty block", header.no)
    return tuple(actions), pos


def _parse_key_block(
    lines: list[_Line], pos: int
) -> tuple[tuple[tuple[str, str], ...], int]:
    header = lines[pos]
    pairs: list[tuple[str, str]] = []
    body_indent: int | None = None
    pos += 1
    while pos < len(lines):
        line = lines[pos]
        if line.indent <= header.indent:
            break
        if body_indent is None:
            body_indent = line.indent
        if line.indent != body_indent:
            break
        if "=" not in line.text:
            raise RungSyntaxError(
                "expected '<key> = <value>' inside motion block", line.no
            )
        key, value = line.text.split("=", 1)
        key = key.strip()
        if not _NAME_RE.match(key):
            raise RungSyntaxError(f"bad motion key {key!r}", line.no)
        pairs.append((key, value.strip()))
        pos += 1
    if not pairs:
        raise RungSyntaxError("empty motion block", header.no)
    return tuple(pairs), pos


_ASSIGN_RE = re.compile(r"(?<![<>=!])=(?!=)")


def _parse_action(
    text: str, line: _Line, lets: dict[str, formula.Expr], allow_block_header: bool
) -> tuple[rast.Action, bool]:
    """Parse one action; returns (action, opens_key_block)."""
    first = text.split(None, 1)[0]

    if first in SERVO_KEYWORDS:
        rest = text[len(first) :].strip()
        match = re.match(rf"({_NAME})\s+using\s+({_NAME})\Z", rest)
        if not match:
            raise RungSyntaxError(f"expected '{first} <axis> using <control>'", line.no)
        return rast.ServoAction(first, match.group(1), match.group(2)), False

    if first in MOTION_KEYWORDS:
        rest = text[len(first) :].strip()
        if not rest.endswith(":"):
            raise RungSyntaxError(
                f"'{first}' action must open a key block with ':'", line.no
            )
        if not allow_block_header:
            raise RungSyntaxError(
                f"'{first}' block cannot take a 'when' suffix; wrap it in a when block",
                line.no,
            )
        match = re.match(rf"({_NAME})\s+using\s+({_NAME})\Z", rest[:-1].strip())
        if not match:
            raise RungSyntaxError(
                f"expected '{first} <target> using <control>:'", line.no
            )
        return rast.MotionAction(first, match.group(1), match.group(2), ()), True

    if first in ("start_timer", "count_up", "reset"):
        tag = text[len(first) :].strip()
        if not re.match(rf"{_NAME}(\[[0-9]+\])?\Z", tag):
            raise RungSyntaxError(f"expected '{first} <tag>'", line.no)
        return rast.TimerAction(first, tag), False

    if first == "call":
        name = text[len("call") :].strip()
        if not _NAME_RE.match(name):
            raise RungSyntaxError("expected 'call <routine>'", line.no)
        return rast.CallAction(name), False

    if first in ("latch", "unlatch"):
        target = text[len(first) :].strip()
        return rast.LatchAction(first, target), False

    generic = _GENERIC_RE.match(text)
    if generic:
        return (
            rast.GenericAction(generic.group(1), _split_operands(generic.group(2))),
            False,
        )

    match = _ASSIGN_RE.search(text)
    if match:
        target = text[: match.start()].strip()
        expr_text = text[match.end() :].strip()
        if not re.match(r"[A-Za-z_][A-Za-z0-9_:]*([.\[][^=\s]*)?\Z", target):
            raise RungSyntaxError(f"bad assignment target {target!r}", line.no)
        return rast.AssignAction(target, _parse_expr(expr_text, lets, line)), False

    raise RungSyntaxError(f"cannot parse statement {text!r}", line.no)
