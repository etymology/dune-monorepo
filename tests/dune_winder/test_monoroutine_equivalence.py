"""Equivalence tests: MonoroutineLadderSimulatedPLC vs LadderSimulatedPLC ensemble.

Both simulators are driven with identical inputs and their observable outputs are
compared after each step.  The monoroutine is a self-contained routine that should
produce the same externally-visible behaviour as the full ensemble.

Timer / counter note: unregistered timer and counter tags default to PRE=10 so
timing-related transitions behave deterministically across both simulators.
"""

from __future__ import annotations

import pytest
import unittest

from dune_winder.io.devices.ladder_simulated_plc import LadderSimulatedPLC
from dune_winder.io.devices.monoroutine_simulated_plc import (
    MonoroutineLadderSimulatedPLC,
)
from dune_winder.queued_motion.segment_types import MotionSegment

# ---------------------------------------------------------------------------
# Tags compared after each step
# ---------------------------------------------------------------------------
COMPARE_TAGS = [
    "STATE",
    "NEXTSTATE",
    "ERROR_CODE",
    "MOVE_TYPE",
    "STATE_REQUEST",
    "QueueCount",
    "CurIssued",
    "NextIssued",
    "IncomingSegAck",
    "ActiveSeq",
    "PendingSeq",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ensemble() -> LadderSimulatedPLC:
    return LadderSimulatedPLC("SIM")


def _make_mono() -> MonoroutineLadderSimulatedPLC:
    return MonoroutineLadderSimulatedPLC("SIM")


def _advance(plc, scans: int = 1):
    for _ in range(scans):
        plc.read("STATE")


def _advance_until(plc, predicate, limit: int = 100):
    for _ in range(limit):
        plc.read("STATE")
        if predicate():
            return True
    return False


def _advance_both(ensemble, mono, scans: int = 1):
    _advance(ensemble, scans)
    _advance(mono, scans)


def _advance_both_until(ensemble, mono, predicate_e, predicate_m, limit: int = 100):
    for _ in range(limit):
        _advance_both(ensemble, mono)
        if predicate_e() and predicate_m():
            return True
    return False


def _enqueue_segment(plc, req_id: int, segment: MotionSegment, limit: int = 100):
    plc.set_tag(
        "IncomingSeg",
        {
            "Valid": True,
            "SegType": segment.seg_type,
            "XY": [segment.x, segment.y],
            "Speed": segment.speed,
            "Accel": segment.accel,
            "Decel": segment.decel,
            "JerkAccel": segment.jerk_accel,
            "JerkDecel": segment.jerk_decel,
            "TermType": segment.term_type,
            "Seq": segment.seq,
            "CircleType": segment.circle_type,
            "ViaCenter": [segment.via_center_x, segment.via_center_y],
            "Direction": segment.direction,
        },
    )
    plc.set_tag("IncomingSegReqID", req_id)
    return _advance_until(plc, lambda: plc.get_tag("IncomingSegAck") == req_id, limit)


def _enqueue_both(
    ensemble, mono, req_id: int, segment: MotionSegment, limit: int = 100
):
    ok_e = _enqueue_segment(ensemble, req_id, segment, limit)
    ok_m = _enqueue_segment(mono, req_id, segment, limit)
    return ok_e, ok_m


def _assert_tags_equal(
    tc: unittest.TestCase, ensemble, mono, tags=COMPARE_TAGS, msg_prefix=""
):
    for tag in tags:
        e_val = ensemble.get_tag(tag)
        m_val = mono.get_tag(tag)
        tc.assertEqual(
            e_val,
            m_val,
            f"{msg_prefix}Mismatch on {tag!r}: ensemble={e_val!r} mono={m_val!r}",
        )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


@pytest.mark.ladder_sim
class MonoroutineEquivalenceTests(unittest.TestCase):
    # ------------------------------------------------------------------
    # Startup / initial state
    # ------------------------------------------------------------------

    def test_initial_state_both_ready(self):
        ensemble = _make_ensemble()
        mono = _make_mono()
        _assert_tags_equal(self, ensemble, mono)

    def test_initial_state_error_code_zero(self):
        ensemble = _make_ensemble()
        mono = _make_mono()
        self.assertEqual(ensemble.get_tag("ERROR_CODE"), 0)
        self.assertEqual(mono.get_tag("ERROR_CODE"), 0)

    def test_initial_queue_empty(self):
        ensemble = _make_ensemble()
        mono = _make_mono()
        self.assertEqual(ensemble.get_tag("QueueCount"), 0)
        self.assertEqual(mono.get_tag("QueueCount"), 0)
        self.assertFalse(ensemble.get_tag("CurIssued"))
        self.assertFalse(mono.get_tag("CurIssued"))

    # ------------------------------------------------------------------
    # MOVE_TYPE state transitions
    # ------------------------------------------------------------------

    def test_xy_jog_state_transition(self):
        ensemble = _make_ensemble()
        mono = _make_mono()
        ensemble.write(("MOVE_TYPE", ensemble.MOVE_JOG_XY))
        mono.write(("MOVE_TYPE", mono.MOVE_JOG_XY))
        _advance_both(ensemble, mono, 3)
        _assert_tags_equal(self, ensemble, mono, ["STATE", "MOVE_TYPE"])

    def test_z_seek_state_transition(self):
        ensemble = _make_ensemble()
        mono = _make_mono()
        ensemble.write(("STATE_REQUEST", ensemble.STATE_Z_SEEK))
        mono.write(("STATE_REQUEST", mono.STATE_Z_SEEK))
        _advance_both(ensemble, mono, 2)
        _assert_tags_equal(self, ensemble, mono, ["STATE"])

    def test_unservo_state_transition(self):
        ensemble = _make_ensemble()
        mono = _make_mono()
        ensemble.write(("STATE_REQUEST", ensemble.STATE_UNSERVO))
        mono.write(("STATE_REQUEST", mono.STATE_UNSERVO))
        _advance_both(ensemble, mono, 3)
        _assert_tags_equal(self, ensemble, mono, ["STATE"])

    def test_hmi_stop_state_transition(self):
        ensemble = _make_ensemble()
        mono = _make_mono()
        # First trigger a seek so HMI stop has something to interrupt
        for plc in (ensemble, mono):
            plc.write(("X_POSITION", 500.0))
            plc.write(("Y_POSITION", 500.0))
            plc.write(("XY_SPEED", 1000.0))
            plc.write(("XY_ACCELERATION", 1000.0))
            plc.write(("XY_DECELERATION", 1000.0))
            plc.write(("STATE_REQUEST", plc.STATE_XY_SEEK))
        _advance_both(ensemble, mono)
        ensemble.write(("STATE_REQUEST", ensemble.STATE_HMI_STOP))
        mono.write(("STATE_REQUEST", mono.STATE_HMI_STOP))
        self.assertTrue(
            _advance_both_until(
                ensemble,
                mono,
                lambda: ensemble.get_tag("STATE") == ensemble.STATE_HMI_STOP,
                lambda: mono.get_tag("STATE") == mono.STATE_HMI_STOP,
            ),
            "Both simulators did not reach HMI_STOP",
        )
        _assert_tags_equal(self, ensemble, mono, ["STATE"])

    def test_queue_stop_request_drains_gracefully(self):
        ensemble = _make_ensemble()
        mono = _make_mono()
        for i in range(1, 4):
            seg = MotionSegment(seq=i, x=float(i * 150), y=0.0)
            _enqueue_both(ensemble, mono, req_id=i, segment=seg)
        ensemble.set_tag("StartQueuedPath", True)
        mono.set_tag("StartQueuedPath", True)
        _advance_both(ensemble, mono, 5)
        ensemble.set_tag("QueueStopRequest", True)
        mono.set_tag("QueueStopRequest", True)
        self.assertTrue(
            _advance_both_until(
                ensemble,
                mono,
                lambda: ensemble.get_tag("STATE") == ensemble.STATE_READY,
                lambda: mono.get_tag("STATE") == mono.STATE_READY,
                limit=200,
            ),
            "Both simulators did not reach READY after QueueStopRequest",
        )
        _assert_tags_equal(self, ensemble, mono, ["STATE", "CurIssued", "QueueCount"])


if __name__ == "__main__":
    unittest.main()
