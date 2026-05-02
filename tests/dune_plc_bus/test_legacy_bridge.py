"""Run the new TagBus over the existing SimulatedPLC via LegacyPlcAdapter.

Confirms that the bridge driver lets us migrate consumers incrementally
without first porting all the simulator ladder semantics into Rust.
"""

from __future__ import annotations

import pytest

dune_plc_bus = pytest.importorskip("dune_plc_bus")

from dune_winder.io.devices.legacy_bus_adapter import LegacyPlcAdapter  # noqa: E402
from dune_winder.io.devices.simulated_plc import SimulatedPLC  # noqa: E402


@pytest.fixture()
def bus_over_legacy():
    plc = SimulatedPLC()
    plc.initialize()
    adapter = LegacyPlcAdapter(plc)
    bus = dune_plc_bus.TagBus.from_python(adapter)
    bus.start()
    try:
        yield bus, plc
    finally:
        bus.stop()


def test_state_read_through_bridge(bus_over_legacy):
    bus, _plc = bus_over_legacy
    snap = bus.read_fresh("STATE", within_ms=100, timeout_ms=1000)
    assert snap.source == "plc"
    assert isinstance(snap.value, int)


def test_state_request_write_lands_in_legacy_plc(bus_over_legacy):
    bus, plc = bus_over_legacy
    bus.write("STATE_REQUEST", SimulatedPLC.STATE_READY)
    # Read it back through the bus...
    snap = bus.read_fresh("STATE_REQUEST", within_ms=100, timeout_ms=1000)
    assert snap.value == SimulatedPLC.STATE_READY
    # ...and confirm the legacy PLC saw it.
    assert plc.get_tag("STATE_REQUEST") == SimulatedPLC.STATE_READY


def test_axis_position_round_trips(bus_over_legacy):
    bus, _plc = bus_over_legacy
    bus.write("X_POSITION", 12.5)
    snap = bus.read_fresh("X_POSITION", within_ms=100, timeout_ms=1000)
    assert snap.value == pytest.approx(12.5)
