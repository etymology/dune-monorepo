"""Adapter that exposes any legacy PLC subclass to the new TagBus.

Bridge contract (matches Rust `PyCallbackDriver`):

    read(names: list[str]) -> dict[str, value]
    write(updates: list[(str, value)]) -> dict[str, bool]
    is_functional() -> bool

The legacy `PLC` base class returns `[[name, value], ...]` from `read` and
takes a single `(name, value)` tuple in `write`. This adapter normalizes both.
"""

from __future__ import annotations

from typing import Any, Iterable

from .plc import PLC


class LegacyPlcAdapter:
    """Bridge a legacy PLC instance to the TagBus driver protocol."""

    def __init__(self, plc: PLC) -> None:
        self._plc = plc

    @property
    def plc(self) -> PLC:
        return self._plc

    def is_functional(self) -> bool:
        return not self._plc.isNotFunctional()

    def read(self, names: Iterable[str]) -> dict[str, Any]:
        names_list = list(names)
        if not names_list:
            return {}
        result = self._plc.read(names_list)
        if result is None:
            return {}
        out: dict[str, Any] = {}
        for entry in result:
            name, value = entry[0], entry[1]
            out[str(name)] = value
        return out

    def write(self, updates: Iterable[tuple[str, Any]]) -> dict[str, bool]:
        out: dict[str, bool] = {}
        for name, value in updates:
            result = self._plc.write((str(name), value))
            out[str(name)] = result is not None
        return out
