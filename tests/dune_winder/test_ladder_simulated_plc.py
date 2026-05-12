from __future__ import annotations

import pytest
import unittest

from dune_winder.io.devices.ladder_simulated_plc import LadderSimulatedPLC
from dune_winder.queued_motion.segment_types import CIRCLE_TYPE_CENTER
from dune_winder.queued_motion.segment_types import MCCM_DIR_2D_CCW
from dune_winder.queued_motion.segment_types import SEG_TYPE_CIRCLE


@pytest.mark.ladder_sim
class LadderSimulatedPlcTests(unittest.TestCase):
    def _advance(self, plc: LadderSimulatedPLC, scans: int = 1):
        for _ in range(scans):
            plc.read("STATE")

    def _advance_until(self, plc: LadderSimulatedPLC, predicate, limit: int = 50):
        for _ in range(limit):
            plc.read("STATE")
            if predicate():
                return
        self.fail("Timed out waiting for ladder simulator condition.")

    def test_initial_state_uses_ladder_seeded_tags(self):
        plc = LadderSimulatedPLC("SIM")

        self.assertEqual(plc.get_status()["simEngine"], "LADDER")
        self.assertEqual(plc.get_tag("STATE"), plc.STATE_READY)
        self.assertEqual(plc.get_tag("ERROR_CODE"), 0)
        self.assertEqual(plc.get_tag("HEAD_POS"), 0)
        self.assertEqual(plc.get_tag("ACTUATOR_POS"), 1)
        self.assertTrue(plc.get_tag("MACHINE_SW_STAT[6]"))
        self.assertFalse(plc.get_tag("MACHINE_SW_STAT[7]"))
        self.assertEqual(plc.get_tag("QueueCtl.POS"), 0)

    def test_latch_home_and_unlock_stub_update_homed_status(self):
        plc = LadderSimulatedPLC("SIM")
        plc.set_tag("HEAD_POS", 3)
        plc.set_tag("ACTUATOR_POS", 2)
        plc.set_tag("LATCH_ACTUATOR_HOMED", False)

        plc.write(("MOVE_TYPE", plc.MOVE_LATCH_UNLOCK))
        self.assertEqual(plc.get_tag("STATE"), plc.STATE_LATCH_RELEASE)
        self._advance(plc)
        self.assertEqual(plc.get_tag("STATE"), plc.STATE_LATCH_RELEASE)
        self._advance_until(plc, lambda: plc.get_tag("STATE") == plc.STATE_READY)
        self.assertEqual(plc.get_tag("ACTUATOR_POS"), 2)
        self.assertFalse(plc.get_tag("LATCH_ACTUATOR_HOMED"))
        self.assertFalse(plc.get_tag("MACHINE_SW_STAT[0]"))

        plc.write(("MOVE_TYPE", plc.MOVE_HOME_LATCH))
        self.assertEqual(plc.get_tag("STATE"), plc.STATE_LATCH_HOMEING)
        self._advance(plc)
        self.assertEqual(plc.get_tag("STATE"), plc.STATE_LATCH_HOMEING)
        self._advance_until(plc, lambda: plc.get_tag("STATE") == plc.STATE_READY)
        self.assertEqual(plc.get_tag("ACTUATOR_POS"), 0)
        self.assertTrue(plc.get_tag("LATCH_ACTUATOR_HOMED"))
        self.assertTrue(plc.get_tag("MACHINE_SW_STAT[0]"))

    def test_queue_segment_enqueues_and_executes_via_motion_queue_routine(self):
        plc = LadderSimulatedPLC("SIM")
        plc.set_tag(
            "IncomingSeg",
            {
                "Valid": True,
                "SegType": 1,
                "XY": [125.0, 250.0],
                "Speed": 1000.0,
                "Accel": 2000.0,
                "Decel": 2000.0,
                "JerkAccel": 1500.0,
                "JerkDecel": 3000.0,
                "TermType": 3,
                "Seq": 1,
                "CircleType": 1,
                "ViaCenter": [0.0, 0.0],
                "Direction": 1,
            },
        )
        plc.set_tag("IncomingSegReqID", 1)

        self._advance_until(plc, lambda: plc.get_tag("QueueCount") == 1)

        self.assertEqual(plc.get_tag("IncomingSegAck"), 1)
        self.assertEqual(plc.get_tag("LastIncomingSegReqID"), 1)

        plc.set_tag("StartQueuedPath", 1)
        self._advance_until(
            plc,
            lambda: (
                plc.get_tag("STATE") == plc.STATE_READY
                and not plc.get_tag("CurIssued")
                and plc.get_tag("QueueCount") == 0
            ),
        )

        self.assertEqual(plc.get_tag("QueueCount"), 0)
        self.assertFalse(plc.get_tag("CurIssued"))
        self.assertAlmostEqual(plc.get_tag("X_axis.ActualPosition"), 125.0, places=6)
        self.assertAlmostEqual(plc.get_tag("Y_axis.ActualPosition"), 250.0, places=6)

    def test_hmi_stop_request_interrupts_xy_seek_and_returns_ready(self):
        plc = LadderSimulatedPLC("SIM")
        plc.write(("X_POSITION", 123.4))
        plc.write(("Y_POSITION", 456.7))
        plc.write(("XY_SPEED", 1000.0))
        plc.write(("XY_ACCELERATION", 1000.0))
        plc.write(("XY_DECELERATION", 1000.0))
        plc.write(("STATE_REQUEST", plc.STATE_XY_SEEK))
        self._advance(plc)

        plc.write(("STATE_REQUEST", plc.STATE_HMI_STOP))

        self._advance_until(plc, lambda: plc.get_tag("STATE") == plc.STATE_HMI_STOP)
        self._advance_until(plc, lambda: plc.get_tag("STATE") == plc.STATE_READY)

        self.assertEqual(plc.get_tag("STATE_REQUEST"), 0)
        self.assertTrue(plc.get_tag("hmi_xy_stop.DN"))
        self.assertTrue(plc.get_tag("hmi_x_axis_stop.DN"))
        self.assertTrue(plc.get_tag("hmi_y_axis_stop.DN"))
        self.assertTrue(plc.get_tag("hmi_z_axis_stop.DN"))

    def test_eot_state_request_enters_eot_recovery_state(self):
        plc = LadderSimulatedPLC("SIM")
        plc.set_tag("MINUS_X_EOT", False, override=True)
        plc.write(("STATE_REQUEST", plc.STATE_EOT))

        self._advance_until(plc, lambda: plc.get_tag("STATE") == plc.STATE_EOT)

        self.assertEqual(plc.get_tag("STATE"), plc.STATE_EOT)

    def test_queue_circle_segment_executes_via_motion_queue_routine(self):
        plc = LadderSimulatedPLC("SIM")
        plc.set_tag(
            "IncomingSeg",
            {
                "Valid": True,
                "SegType": SEG_TYPE_CIRCLE,
                "XY": [100.0, 100.0],
                "Speed": 800.0,
                "Accel": 1600.0,
                "Decel": 1600.0,
                "JerkAccel": 1500.0,
                "JerkDecel": 3000.0,
                "TermType": 3,
                "Seq": 2,
                "CircleType": CIRCLE_TYPE_CENTER,
                "ViaCenter": [0.0, 100.0],
                "Direction": MCCM_DIR_2D_CCW,
            },
        )
        plc.set_tag("IncomingSegReqID", 2)

        self._advance_until(plc, lambda: plc.get_tag("QueueCount") == 1)

        plc.set_tag("StartQueuedPath", 1)
        self._advance_until(
            plc,
            lambda: (
                plc.get_tag("STATE") == plc.STATE_READY
                and not plc.get_tag("CurIssued")
                and plc.get_tag("QueueCount") == 0
            ),
            limit=100,
        )

        self.assertEqual(plc.get_tag("IncomingSegAck"), 2)
        self.assertEqual(plc.get_tag("QueueCount"), 0)
        self.assertAlmostEqual(plc.get_tag("X_axis.ActualPosition"), 100.0, places=6)
        self.assertAlmostEqual(plc.get_tag("Y_axis.ActualPosition"), 100.0, places=6)


if __name__ == "__main__":
    unittest.main()
