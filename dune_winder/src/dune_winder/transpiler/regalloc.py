"""Global register allocator.

Assigns non-overlapping slices of REALS[*], DINTS[*], BOOLS[*] to variables
across all routines, so that nested JSR calls cannot clobber each other.
"""
from __future__ import annotations
from .types import PLCType, Reg


class RegisterAllocator:
    def __init__(self) -> None:
        self._next: dict[PLCType, int] = {
            PLCType.REAL: 0,
            PLCType.DINT: 0,
            PLCType.BOOL: 0,
        }
        # name → Reg, for comment generation
        self._log: list[tuple[str, Reg]] = []

    def alloc(self, typ: PLCType, name: str = "") -> Reg:
        idx = self._next[typ]
        self._next[typ] += 1
        reg = Reg(typ, idx)
        if name:
            self._log.append((name, reg))
        return reg

    def alloc_temp(self, typ: PLCType) -> Reg:
        return self.alloc(typ, "")

    def alloc_routine(
        self,
        vars_: list[tuple[str, PLCType]],
    ) -> dict[str, Reg]:
        """Allocate a named set of variables for one routine, returning name→Reg map."""
        result: dict[str, Reg] = {}
        for name, typ in vars_:
            result[name] = self.alloc(typ, name)
        return result

    def summary_comments(self) -> list[str]:
        """Return comment lines listing every allocation made so far."""
        lines = ["; Register allocation:"]
        for name, reg in self._log:
            lines.append(f";   {reg} = {name}")
        return lines

    def snapshot(self) -> dict[PLCType, int]:
        return dict(self._next)

    def restore(self, snap: dict[PLCType, int]) -> None:
        self._next = dict(snap)
