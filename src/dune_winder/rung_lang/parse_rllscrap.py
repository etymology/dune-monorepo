"""Parser for Studio's clipboard paren dialect (.rllscrap / L5X rung CDATA).

Grammar (see winder/plc/RLL_FORMAT.md):

    routine := rung (';' rung)*
    rung    := element*
    element := NAME '(' operands ')' | '[' rung (',' rung)* ']'

Operands split on commas at parenthesis depth 0, so commas inside CMP/CPT
formula sub-calls survive. Whitespace between elements and around branch
commas is insignificant. This is a fresh implementation (the plc_ladder
package parses the space-token paste dialect, a different format).
"""

from __future__ import annotations

from .rung_ir import BranchIR, Instr, Node, RoutineIR, RungIR


class RllscrapError(ValueError):
    pass


def _split_rungs(text: str) -> list[str]:
    """Split routine text into rung texts at top-level semicolons."""
    rungs: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == ";" and depth == 0:
            rungs.append("".join(current))
            current = []
        else:
            current.append(ch)
    tail = "".join(current).strip()
    if tail:
        rungs.append(tail)
    return [r for r in (r.strip() for r in rungs) if r]


def _split_operands(text: str) -> tuple[str, ...]:
    if text.strip() == "":
        return ()
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    parts.append("".join(current).strip())
    return tuple(parts)


class _RungParser:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    def _skip_ws(self) -> None:
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def at_end(self) -> bool:
        self._skip_ws()
        return self.pos >= len(self.text)

    def peek(self) -> str:
        self._skip_ws()
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def parse_elements(self, stop: str = "") -> tuple[Node, ...]:
        nodes: list[Node] = []
        while not self.at_end():
            ch = self.peek()
            if stop and ch in stop:
                break
            if ch == "[":
                nodes.append(self.parse_branch())
            elif ch.isalpha() or ch == "_":
                nodes.append(self.parse_instruction())
            else:
                raise RllscrapError(
                    f"unexpected character {ch!r} at offset {self.pos} in rung {self.text!r}"
                )
        return tuple(nodes)

    def parse_branch(self) -> BranchIR:
        self._skip_ws()
        assert self.text[self.pos] == "["
        self.pos += 1
        legs: list[tuple[Node, ...]] = []
        while True:
            legs.append(self.parse_elements(stop=",]"))
            self._skip_ws()
            if self.pos >= len(self.text):
                raise RllscrapError(f"unterminated branch in rung {self.text!r}")
            ch = self.text[self.pos]
            self.pos += 1
            if ch == "]":
                return BranchIR(tuple(legs))
            if ch != ",":
                raise RllscrapError(f"unexpected {ch!r} in branch")

    def parse_instruction(self) -> Instr:
        self._skip_ws()
        start = self.pos
        while self.pos < len(self.text) and (
            self.text[self.pos].isalnum() or self.text[self.pos] == "_"
        ):
            self.pos += 1
        opcode = self.text[start : self.pos]
        self._skip_ws()
        if self.pos >= len(self.text) or self.text[self.pos] != "(":
            raise RllscrapError(f"expected '(' after {opcode!r} in rung {self.text!r}")
        depth = 0
        arg_start = self.pos + 1
        while self.pos < len(self.text):
            ch = self.text[self.pos]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    operands = _split_operands(self.text[arg_start : self.pos])
                    self.pos += 1
                    return Instr(opcode, operands)
            self.pos += 1
        raise RllscrapError(f"unterminated operand list for {opcode!r}")


def parse_rung_text(text: str, rung_type: str = "N") -> RungIR:
    parser = _RungParser(text)
    nodes = parser.parse_elements()
    return RungIR(nodes, rung_type)


def parse_rllscrap_text(
    text: str,
    *,
    program: str,
    routine: str,
    pending_rungs: frozenset[int] = frozenset(),
) -> RoutineIR:
    """Parse a whole routine's rllscrap text.

    ``pending_rungs`` marks rung indexes that the ACD flags as pending
    edits (rllscrap text itself carries no marker; callers harvest the
    indexes from the routine L5X's ``Type="e"`` attributes).
    """
    rungs = [
        parse_rung_text(rung_text, "e" if i in pending_rungs else "N")
        for i, rung_text in enumerate(_split_rungs(text))
    ]
    return RoutineIR(program, routine, tuple(rungs))
