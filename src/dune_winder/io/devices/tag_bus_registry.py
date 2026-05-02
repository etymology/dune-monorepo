"""Acquire a TagBus for either a legacy PLC or an existing bus.

Used during migration so consumers (`PLC_Motor`, `PLC_Input`, ...) can be
flipped to the bus API one at a time. The registry guarantees one TagBus per
underlying legacy PLC instance, so a winder with several motors does not spin
up several poll threads.
"""

from __future__ import annotations

import weakref
from typing import Any

from .legacy_bus_adapter import LegacyPlcAdapter
from .plc import PLC


def _is_bus(obj: Any) -> bool:
    return all(
        hasattr(obj, attr) for attr in ("read_fresh", "write", "snapshot", "start")
    )


# PyO3 classes can't be weakref targets, so we hold buses by strong ref keyed
# off the (weakly-held) legacy PLC. When the PLC is collected, the entry
# disappears and the bus drops with it.
_OWNERSHIP: "weakref.WeakKeyDictionary[Any, Any]" = weakref.WeakKeyDictionary()


def tag_bus_for(plc_or_bus: Any) -> Any:
    """Return a TagBus for the given PLC or bus.

    - If passed a TagBus already, returns it as-is.
    - If passed a legacy PLC, returns a cached TagBus wired through the
      bridge driver. The bus is started lazily on first acquisition.
    """
    if _is_bus(plc_or_bus):
        return plc_or_bus

    if not isinstance(plc_or_bus, PLC):
        raise TypeError(f"expected PLC or TagBus, got {type(plc_or_bus).__name__}")

    cached = _OWNERSHIP.get(plc_or_bus)
    if cached is not None:
        return cached

    import dune_plc_bus  # late import: optional during transition

    adapter = LegacyPlcAdapter(plc_or_bus)
    bus = dune_plc_bus.TagBus.from_python(adapter)  # type: ignore[attr-defined]
    # Bus is *not* auto-started; production wiring (e.g. base_io) calls
    # `start_bus_for(plc)` once after construction. Tests can leave it stopped
    # to keep the read pattern deterministic, since `read_fresh` and `write`
    # work without the poll thread (one-shot reads bypass it).
    _OWNERSHIP[plc_or_bus] = bus
    return bus


def start_bus_for(plc_or_bus: Any) -> Any:
    """Acquire the bus for a PLC/bus and ensure its poll thread is running."""
    bus = tag_bus_for(plc_or_bus)
    bus.start()
    return bus
