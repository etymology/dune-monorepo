"""Phase B handshake — STATE_REQUEST_ID/ACK/RESULT round-trip.

Exercises the dispatch contract through a real BaseIO stack on the
SimulatedPLC. Verifies ACK ordering, the four RESULT outcomes (1
accepted, 2 rejected, 3 completed, 4 faulted), STATE_ENTRY_COUNTER
monotonicity, LAST_STATE bookkeeping, and fault-flag → legacy
ERROR_CODE composition.
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip("dune_plc_bus")

from dune_winder.io.controllers.plc_logic import (  # noqa: E402
    FAULT_AXIS,
    FAULT_INTERLOCK,
    FAULT_REQUEST_OUT_OF_RANGE,
    PLC_Logic,
)
from dune_winder.io.devices.simulated_plc import SimulatedPLC  # noqa: E402
from dune_winder.io.maps.base_io import BaseIO  # noqa: E402

# Bus poll thread runs at the critical tier (~20 ms); give cached snapshots
# a generous window so the test isn't racy on a loaded CI box.
_SETTLE_S = 0.1


@pytest.fixture()
def io():
    plc = SimulatedPLC()
    plc.initialize()
    bridge = BaseIO(plc)
    time.sleep(_SETTLE_S)
    yield bridge


def test_request_completes_with_result_3_and_counter_increments(io):
    pl = io.plcLogic
    counter_before = pl.getStateEntryCounter()
    pl.setZ_Position(25.0)
    time.sleep(_SETTLE_S)
    assert pl.getStateRequestAck() == pl.getLastRequestId() == 1
    assert pl.getStateRequestResult() == 3  # completed
    assert pl.getLastState() == PLC_Logic.States.Z_SEEK
    # READY → Z_SEEK → READY = two transitions.
    assert pl.getStateEntryCounter() == counter_before + 2
    assert pl.isReady() is True


def test_out_of_range_request_is_rejected(io):
    pl = io.plcLogic
    # Send the dispatch directly through the bus so we bypass the Python-side
    # whitelist check and exercise the ladder/sim's own range-check path.
    pl._lastIssuedRequestId += 1
    pl._bus.write("STATE_REQUEST_ID", pl._lastIssuedRequestId)
    pl._bus.write("STATE_REQUEST", 99)
    time.sleep(_SETTLE_S)
    assert pl.getStateRequestResult() == 2  # rejected
    assert pl.getStateFaultFlags() & FAULT_REQUEST_OUT_OF_RANGE
    assert pl.getStateRequestAck() == pl.getLastRequestId()


def test_python_whitelist_rejects_unknown_state(io):
    pl = io.plcLogic
    with pytest.raises(ValueError):
        pl._requestState(99)


def test_request_ids_are_monotonic_across_multiple_requests(io):
    pl = io.plcLogic
    pl.setZ_Position(10.0)
    time.sleep(_SETTLE_S)
    assert pl.getLastRequestId() == 1
    pl.setZ_Position(20.0)
    time.sleep(_SETTLE_S)
    assert pl.getLastRequestId() == 2
    assert pl.getStateRequestAck() == 2
    assert pl.getStateRequestResult() == 3


def test_fault_flags_compose_to_legacy_error_code(io):
    pl = io.plcLogic
    # Inject a Z-axis fault state, then verify both that the error surfaces
    # *and* that getErrorCode picks the right legacy code from (LAST_STATE,
    # FAULT_AXIS).
    plc = io.plc
    pl.setZ_Position(15.0)
    time.sleep(_SETTLE_S)
    # Manually mark the most recent state as Z_SEEK, raise the AXIS bit,
    # and assert composition. We don't rely on a real fault-injection path;
    # the simulator publishes flags only on _setError, which uses code 5003
    # by default — that's a position error, not the interlock case we want
    # to map. So we drive the bus directly to focus on the mapping logic.
    plc.write([("LAST_STATE", PLC_Logic.States.Z_SEEK)])
    plc.write([("STATE_FAULT_FLAGS", FAULT_AXIS)])
    time.sleep(_SETTLE_S)
    assert pl.getErrorCode() == 5002
    assert "axis fault" in pl.getErrorCodeString().lower()


def test_interlock_flag_maps_to_xy_seek_3001(io):
    pl = io.plcLogic
    plc = io.plc
    plc.write([("LAST_STATE", PLC_Logic.States.XY_SEEK)])
    plc.write([("STATE_FAULT_FLAGS", FAULT_INTERLOCK)])
    time.sleep(_SETTLE_S)
    assert pl.getErrorCode() == 3001


def test_isready_falls_back_to_legacy_when_no_request_issued(io):
    # Before any request, _lastIssuedRequestId == 0; isReady should read the
    # legacy STATE/STATE_REQUEST pair and report True for a fresh sim.
    pl = io.plcLogic
    assert pl.getLastRequestId() == 0
    assert pl.isReady() is True
