from __future__ import annotations

import ast
from typing import Callable


def compile_legacy_tension_condition(expr: str) -> Callable[[float], bool]:
    """Compile a safe tension-only expression that references ``t``."""

    allowed_nodes = (
        ast.Expression,
        ast.BoolOp,
        ast.BinOp,
        ast.UnaryOp,
        ast.Compare,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.And,
        ast.Or,
        ast.Not,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Pow,
        ast.Mod,
        ast.USub,
        ast.UAdd,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
    )

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid syntax: {exc.msg}") from exc

    uses_t = False
    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            raise ValueError(f"disallowed expression node: {type(node).__name__}")
        if isinstance(node, ast.Name):
            if node.id != "t":
                raise ValueError(
                    "only the variable 't' is allowed in legacy tension conditions"
                )
            uses_t = True

    if not uses_t:
        raise ValueError("legacy tension conditions must reference the variable 't'")

    code = compile(tree, "<legacy-tension-condition>", "eval")

    def predicate(tension: float) -> bool:
        result = eval(code, {"__builtins__": {}}, {"t": float(tension)})
        return bool(result)

    return predicate


# Backwards-compatible private alias for the historical name.
_compile_legacy_tension_condition = compile_legacy_tension_condition
