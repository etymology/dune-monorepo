"""Expression AST shared by the Logix formula dialect and .rung surface.

One tree, two textual dialects:

- **formula** — what lives inside ``CMP(...)`` / ``CPT(dest, ...)`` operands
  in rung text: ``=``/``<>`` comparators, uppercase functions
  (``ABS``, ``SQR``), ``MOD`` as an infix keyword, no boolean operators.
- **surface** — what .rung files use: ``==``/``!=``, ``and``/``or``/``not``,
  lowercase functions, same arithmetic.

Both printers emit minimal parentheses from the same canonical precedence,
so parse -> print -> parse is a fixed point in either dialect (numeric
literals keep their original lexeme).
"""

from __future__ import annotations

from dataclasses import dataclass


class Expr:
    __slots__ = ()


@dataclass(frozen=True)
class Num(Expr):
    """Numeric literal; the lexeme is preserved verbatim."""

    text: str


@dataclass(frozen=True)
class Ref(Expr):
    """Tag reference path: ``name``, ``a.DN``, ``arr[3].member``."""

    text: str

    @property
    def base(self) -> str:
        cut = len(self.text)
        for sep in (".", "["):
            idx = self.text.find(sep)
            if idx != -1:
                cut = min(cut, idx)
        return self.text[:cut]

    @property
    def is_module(self) -> bool:
        """Module-qualified I/O path (``Local:1:I.Data``)."""
        return ":" in self.base


@dataclass(frozen=True)
class Call(Expr):
    """Function call (``ABS(x)``) or opaque boolean instruction atom
    (``LIM(a,b,c)``, ``ONS(bit)``, ``AFI()``). Func is stored uppercase."""

    func: str
    args: tuple[Expr, ...]


@dataclass(frozen=True)
class Una(Expr):
    """Unary operator: ``-`` (arithmetic) or ``not`` (boolean)."""

    op: str
    operand: Expr


@dataclass(frozen=True)
class Bin(Expr):
    """Binary operator. Canonical ops: ``+ - * / MOD``, comparators
    ``= <> < > <= >=``, boolean ``and``/``or``."""

    op: str
    lhs: Expr
    rhs: Expr


TRUE = Call("TRUE", ())  # internal "no condition" marker; never printed

COMPARATORS = {"=", "<>", "<", ">", "<=", ">="}
#: comparator -> its negation
COMPARATOR_NEGATION = {
    "=": "<>",
    "<>": "=",
    "<": ">=",
    ">=": "<",
    ">": "<=",
    "<=": ">",
}
#: comparator -> contact opcode for the plain two-operand form
COMPARATOR_OPCODE = {
    "=": "EQU",
    "<>": "NEQ",
    ">=": "GEQ",
    ">": "GRT",
    "<=": "LEQ",
    "<": "LES",
}
OPCODE_COMPARATOR = {v: k for k, v in COMPARATOR_OPCODE.items()}

_FORMULA_FUNCS = {
    "ABS",
    "SQR",
    "SIN",
    "COS",
    "ATN",
    "ASN",
    "ACS",
    "TAN",
    "LN",
    "LOG",
    "TRN",
    "DEG",
    "RAD",
    "FRD",
    "TOD",
    "XPY",
}

# precedence (higher binds tighter)
_PREC = {
    "or": 1,
    "and": 2,
    "not": 3,
    "=": 4,
    "<>": 4,
    "<": 4,
    ">": 4,
    "<=": 4,
    ">=": 4,
    "+": 5,
    "-": 5,
    "*": 6,
    "/": 6,
    "MOD": 6,
    "u-": 7,
}


class FormulaError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Tokenizer (shared; dialect differences are handled at the parser level)
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isdigit() or (ch == "." and i + 1 < n and text[i + 1].isdigit()):
            j = i
            while j < n and (
                text[j].isdigit()
                or text[j] in ".eE"
                or (text[j] in "+-" and j > i and text[j - 1] in "eE")
            ):
                j += 1
            tokens.append(text[i:j])
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i
            # ':' admits module-qualified I/O paths like Local:1:I.Data
            while j < n and (text[j].isalnum() or text[j] in "_.:"):
                j += 1
            # absorb [...] indexes (possibly followed by .member[...]...)
            while j < n and text[j] == "[":
                depth = 0
                while j < n:
                    if text[j] == "[":
                        depth += 1
                    elif text[j] == "]":
                        depth -= 1
                        if depth == 0:
                            j += 1
                            break
                    j += 1
                while j < n and (text[j].isalnum() or text[j] in "_."):
                    j += 1
            tokens.append(text[i:j])
            i = j
            continue
        for two in ("<=", ">=", "<>", "==", "!="):
            if text.startswith(two, i):
                tokens.append(two)
                i += 2
                break
        else:
            tokens.append(ch)
            i += 1
    return tokens


class _Parser:
    """Pratt-style parser over the token list; dialect-parameterised."""

    def __init__(self, tokens: list[str], surface: bool):
        self.tokens = tokens
        self.pos = 0
        self.surface = surface

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def next(self) -> str:
        tok = self.peek()
        if tok is None:
            raise FormulaError("unexpected end of expression")
        self.pos += 1
        return tok

    def expect(self, tok: str) -> None:
        got = self.next()
        if got != tok:
            raise FormulaError(f"expected {tok!r}, got {got!r}")

    # grammar: or_ > and_ > not_ > comparison > add > mul > unary > atom
    def parse(self) -> Expr:
        expr = self.parse_or()
        if self.peek() is not None:
            raise FormulaError(f"unexpected trailing token {self.peek()!r}")
        return expr

    def parse_or(self) -> Expr:
        expr = self.parse_and()
        while self._is_kw("or"):
            self.next()
            expr = Bin("or", expr, self.parse_and())
        return expr

    def parse_and(self) -> Expr:
        expr = self.parse_not()
        while self._is_kw("and"):
            self.next()
            expr = Bin("and", expr, self.parse_not())
        return expr

    def parse_not(self) -> Expr:
        if self._is_kw("not"):
            self.next()
            return Una("not", self.parse_not())
        return self.parse_comparison()

    def parse_comparison(self) -> Expr:
        expr = self.parse_add()
        tok = self.peek()
        op = self._comparator(tok)
        if op is not None:
            self.next()
            expr = Bin(op, expr, self.parse_add())
        return expr

    def _comparator(self, tok: str | None) -> str | None:
        if tok is None:
            return None
        if self.surface:
            mapping = {
                "==": "=",
                "!=": "<>",
                "<": "<",
                ">": ">",
                "<=": "<=",
                ">=": ">=",
            }
        else:
            mapping = {"=": "=", "<>": "<>", "<": "<", ">": ">", "<=": "<=", ">=": ">="}
        return mapping.get(tok)

    def parse_add(self) -> Expr:
        expr = self.parse_mul()
        while self.peek() in ("+", "-"):
            op = self.next()
            expr = Bin(op, expr, self.parse_mul())
        return expr

    def parse_mul(self) -> Expr:
        expr = self.parse_unary()
        while True:
            tok = self.peek()
            if tok in ("*", "/"):
                self.next()
                expr = Bin(tok, expr, self.parse_unary())
            elif tok is not None and tok.upper() == "MOD":
                self.next()
                expr = Bin("MOD", expr, self.parse_unary())
            else:
                return expr

    def parse_unary(self) -> Expr:
        if self.peek() == "-":
            self.next()
            return Una("-", self.parse_unary())
        return self.parse_atom()

    def parse_atom(self) -> Expr:
        tok = self.next()
        if tok == "(":
            expr = self.parse_or()
            self.expect(")")
            return expr
        first = tok[0]
        if first.isdigit() or first == ".":
            return Num(tok)
        if first.isalpha() or first == "_":
            if self.peek() == "(":
                self.next()
                args: list[Expr] = []
                if self.peek() != ")":
                    args.append(self.parse_or())
                    while self.peek() == ",":
                        self.next()
                        args.append(self.parse_or())
                self.expect(")")
                return Call(tok.upper(), tuple(args))
            if self.surface and tok in ("on", "off"):
                # boolean literals (rare; unconditional OTE rungs)
                return Call("TRUE" if tok == "on" else "FALSE", ())
            return Ref(tok)
        raise FormulaError(f"unexpected token {tok!r}")

    def _is_kw(self, kw: str) -> bool:
        tok = self.peek()
        if tok is None:
            return False
        if self.surface:
            return tok == kw
        return tok.upper() == kw.upper() and tok.upper() in ("AND", "OR", "NOT")


def parse_formula(text: str) -> Expr:
    """Parse a Logix formula operand (CMP/CPT expression)."""
    return _Parser(_tokenize(text), surface=False).parse()


def parse_surface_expr(text: str) -> Expr:
    """Parse a .rung surface expression."""
    return _Parser(_tokenize(text), surface=True).parse()


def parse_operand(text: str) -> Expr:
    """Parse a plain instruction operand: a number or a tag path."""
    text = text.strip()
    if not text:
        raise FormulaError("empty operand")
    first = text[0]
    if first.isdigit() or first == "." or (first == "-" and len(text) > 1):
        if first == "-":
            return Una("-", parse_operand(text[1:]))
        return Num(text)
    if first.isalpha() or first == "_":
        return Ref(text)
    raise FormulaError(f"operand {text!r} is not a number or tag path")


# ---------------------------------------------------------------------------
# Printers
# ---------------------------------------------------------------------------


def _print(expr: Expr, surface: bool, parent_prec: int) -> str:
    if isinstance(expr, Num):
        return expr.text
    if isinstance(expr, Ref):
        return expr.text
    if isinstance(expr, Call):
        if expr.func == "TRUE":
            return "on" if surface else "1"
        if expr.func == "FALSE":
            return "off" if surface else "0"
        name = (
            expr.func.lower() if surface and expr.func in _FORMULA_FUNCS else expr.func
        )
        args = (
            ", ".join(_print(a, surface, 0) for a in expr.args)
            if surface
            else ",".join(_print(a, surface, 0) for a in expr.args)
        )
        return f"{name}({args})"
    if isinstance(expr, Una):
        if expr.op == "not":
            inner = _print(expr.operand, surface, _PREC["not"])
            text = f"not {inner}"
            return f"({text})" if parent_prec > _PREC["not"] else text
        inner = _print(expr.operand, surface, _PREC["u-"])
        text = f"-{inner}"
        return f"({text})" if parent_prec > _PREC["u-"] else text
    if isinstance(expr, Bin):
        prec = _PREC[expr.op]
        lhs = _print(expr.lhs, surface, prec)
        # right side of a same-precedence non-associative chain needs parens
        rhs = _print(expr.rhs, surface, prec + 1)
        if surface:
            op = {"=": "==", "<>": "!=", "MOD": "mod"}.get(expr.op, expr.op)
            text = f"{lhs} {op} {rhs}"
        else:
            op = expr.op
            text = f"{lhs} {op} {rhs}" if op == "MOD" else f"{lhs}{op}{rhs}"
        return f"({text})" if parent_prec > prec else text
    raise TypeError(f"unknown expr node {expr!r}")


def print_formula(expr: Expr) -> str:
    """Emit the Logix formula dialect (for CMP/CPT operands)."""
    return _print(expr, surface=False, parent_prec=0)


def print_surface(expr: Expr) -> str:
    """Emit the .rung surface dialect."""
    return _print(expr, surface=True, parent_prec=0)


# ---------------------------------------------------------------------------
# Tree helpers
# ---------------------------------------------------------------------------


def walk(expr: Expr):
    yield expr
    if isinstance(expr, Call):
        for arg in expr.args:
            yield from walk(arg)
    elif isinstance(expr, Una):
        yield from walk(expr.operand)
    elif isinstance(expr, Bin):
        yield from walk(expr.lhs)
        yield from walk(expr.rhs)


def referenced_bases(expr: Expr) -> set[str]:
    return {node.base for node in walk(expr) if isinstance(node, Ref)}


def flatten(expr: Expr, op: str) -> list[Expr]:
    """Flatten an associative and/or chain into its operand list."""
    if isinstance(expr, Bin) and expr.op == op:
        return flatten(expr.lhs, op) + flatten(expr.rhs, op)
    return [expr]


def join(terms: list[Expr], op: str) -> Expr:
    if not terms:
        return TRUE
    expr = terms[0]
    for term in terms[1:]:
        expr = Bin(op, expr, term)
    return expr


def is_true(expr: Expr) -> bool:
    return isinstance(expr, Call) and expr.func == "TRUE"


def complements(a: Expr, b: Expr) -> bool:
    """True when one expr is exactly ``not`` of the other (literal level)."""
    if isinstance(a, Una) and a.op == "not" and a.operand == b:
        return True
    if isinstance(b, Una) and b.op == "not" and b.operand == a:
        return True
    if isinstance(a, Bin) and isinstance(b, Bin) and a.lhs == b.lhs and a.rhs == b.rhs:
        return COMPARATOR_NEGATION.get(a.op) == b.op
    return False
