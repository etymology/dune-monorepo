"""PLC_Input on top of TagBus, against the legacy SimulatedPLC."""

from __future__ import annotations

import time

import pytest

pytest.importorskip("dune_plc_bus")

from dune_winder.io.devices.simulated_plc import SimulatedPLC
from dune_winder.io.primitives.plc_input import PLC_Input


@pytest.fixture()
def plc():
    p = SimulatedPLC()
    p.initialize()
    return p


def test_default_state_before_first_read(plc):
    inp = PLC_Input("estop", plc, "MACHINE_SW_STAT[23]", 0, defaultState=True)
    assert inp._doGet() is True


def test_slot_bit_zero_read_after_poll(plc):
    # SimulatedPLC coerces each MACHINE_SW_STAT[N] slot to a single bit in
    # bit 0. Asserting on bit 0 is the meaningful contract.
    from dune_winder.io.devices.tag_bus_registry import tag_bus_for

    plc.set_tag("MACHINE_SW_STAT[5]", 1)
    plc.set_tag("MACHINE_SW_STAT[6]", 0)
    high = PLC_Input("high", plc, "MACHINE_SW_STAT[5]", 0, defaultState=False)
    low = PLC_Input("low", plc, "MACHINE_SW_STAT[6]", 0, defaultState=False)
    bus = tag_bus_for(plc)
    bus.read_many_fresh(["MACHINE_SW_STAT[5]", "MACHINE_SW_STAT[6]"])
    assert high._doGet() is True
    assert low._doGet() is False


def test_returns_default_when_value_unreadable(plc):
    inp = PLC_Input("park", plc, "MACHINE_SW_STAT[24]", 0, defaultState=True)
    # Without a poll, snapshot is Default → fall back to defaultState.
    assert inp._doGet() is True
