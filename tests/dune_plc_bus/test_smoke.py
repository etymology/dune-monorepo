"""Smoke test for the dune_plc_bus PyO3 binding.

Run with `uv run pytest tests/dune_plc_bus/test_smoke.py` after the wheel is
installed (via `uv sync` once the binding is in `tool.uv.sources`).
"""

from __future__ import annotations

import time

import pytest

dune_plc_bus = pytest.importorskip("dune_plc_bus")


def test_descriptors_include_state_handshake_tags():
    names = {t[0] for t in dune_plc_bus.all_tag_descriptors()}
    for required in (
        "STATE",
        "STATE_REQUEST",
        "STATE_REQUEST_ID",
        "STATE_REQUEST_ACK",
        "STATE_REQUEST_RESULT",
        "STATE_FAULT_FLAGS",
        "STATE_ENTRY_COUNTER",
        "LAST_STATE",
    ):
        assert required in names, f"missing {required}"


def test_round_trip_through_simulated_driver():
    bus, driver = dune_plc_bus.TagBus.simulated()
    driver.poke("STATE", 7)
    bus.start()
    try:
        snap = bus.read_fresh("STATE", within_ms=50, timeout_ms=500)
        assert snap.value == 7
        assert snap.source == "plc"

        bus.write("STATE_REQUEST", 3)
        snap = bus.snapshot("STATE_REQUEST")
        assert snap.value == 3
        assert snap.source == "write_echo"
        assert driver.peek("STATE_REQUEST") == 3
    finally:
        bus.stop()


def test_handshake_round_trip():
    """Mimics the Phase B handshake: write ID + REQUEST atomically, observe ACK."""
    bus, driver = dune_plc_bus.TagBus.simulated()
    driver.poke("STATE_REQUEST_ACK", 0)
    bus.start()
    try:
        bus.write_many({"STATE_REQUEST_ID": 42, "STATE_REQUEST": 5})
        # Simulate the PLC consuming the request and updating ACK.
        driver.poke("STATE_REQUEST_ACK", 42)
        driver.poke("STATE_REQUEST_RESULT", 1)  # accepted

        # within_ms=0 forces a driver round-trip past the poll-thread cache.
        ack = bus.read_fresh("STATE_REQUEST_ACK", within_ms=0, timeout_ms=500)
        result = bus.read_fresh("STATE_REQUEST_RESULT", within_ms=0, timeout_ms=500)
        assert ack.value == 42
        assert result.value == 1
    finally:
        bus.stop()


def test_unknown_tag_raises():
    bus, _drv = dune_plc_bus.TagBus.simulated()
    with pytest.raises(ValueError, match="unknown tag"):
        bus.snapshot("DOES_NOT_EXIST")


def test_metrics_increment():
    bus, driver = dune_plc_bus.TagBus.simulated()
    driver.poke("STATE", 1)
    bus.start()
    try:
        bus.read_fresh("STATE", within_ms=50, timeout_ms=500)
        bus.write("STATE_REQUEST", 2)
        m = bus.metrics()
        assert m["reads"] >= 1
        assert m["writes"] >= 1
    finally:
        bus.stop()
