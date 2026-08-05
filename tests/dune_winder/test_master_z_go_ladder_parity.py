"""The Python MASTER_Z_GO mirror must agree with the real ladder.

`dune_winder.core.master_z_go` re-implements
winder/plc/state_5_move_z/main/main.rung:13-19 in Python so the G-code
interpreter can explain a blocked head transfer before it commands one.  That
duplication is only safe if it stays in step with the rung, so these tests drive
LadderSimulatedPLC (which executes the exported ladder) and compare its
MASTER_Z_GO against the mirror over the same inputs.

The geometry bands are read back out of the ladder rather than from
machineCalibration.json, so this file tests the *logic*.  Constant drift between
the two sources is a separate concern -- see
ConstantSourceTests.test_documents_known_band_drift below.
"""

from __future__ import annotations

import unittest

from dune_winder.core.master_z_go import evaluate_master_z_go, master_z_go_is_ready
from dune_winder.io.devices.ladder_simulated_plc import LadderSimulatedPLC
from dune_winder.io.devices.plc import PLC
from dune_winder.queued_motion.safety import (
    MotionSafetyLimits,
    QueuedMotionCollisionState,
    load_motion_safety_limits,
)


# MACHINE_SW_STAT bit -> frame lock, per LadderSimulatedPLC._MACHINE_BIT_ALIASES.
_FRAME_LOCK_BITS = {
    "frame_lock_head_top": 26,
    "frame_lock_head_mid": 27,
    "frame_lock_head_btm": 28,
    "frame_lock_foot_top": 29,
    "frame_lock_foot_mid": 30,
    "frame_lock_foot_btm": 31,
}


class _Case:
    """One machine state, expressed the same way for the ladder and the mirror."""

    def __init__(
        self,
        name,
        *,
        fixed_latched=False,
        actuator_pos=1,
        x_transfer_ok=True,
        y_transfer_ok=True,
        x_position=450.0,
        y_position=800.0,
        frame_locks=(),
    ):
        self.name = name
        self.fixed_latched = fixed_latched
        self.actuator_pos = actuator_pos
        self.x_transfer_ok = x_transfer_ok
        self.y_transfer_ok = y_transfer_ok
        self.x_position = x_position
        self.y_position = y_position
        self.frame_locks = frozenset(frame_locks)

    def collision_state(self):
        return QueuedMotionCollisionState(
            **{name: (name in self.frame_locks) for name in _FRAME_LOCK_BITS}
        )

    def transfer_state(self):
        return {
            "stagePresent": True,
            "fixedPresent": True,
            "stageLatched": not self.fixed_latched,
            "fixedLatched": self.fixed_latched,
            "zExtended": False,
            "enableActuator": False,
            "actuatorPos": self.actuator_pos,
            "zPosition": 0.0,
        }


# Y bands used below (from the ladder): bottom 80-450, middle 1050-1515,
# top 2200-2650.  X bands: head 400-500, foot 7100-7200.
_CASES = (
    _Case("clean state"),
    _Case("fixed latched at mid engagement", fixed_latched=True, actuator_pos=2),
    _Case("fixed latched at rocker_at_fixed", fixed_latched=True, actuator_pos=3),
    _Case("fixed latched at transition", fixed_latched=True, actuator_pos=0),
    _Case("no transfer window", x_transfer_ok=False, y_transfer_ok=False),
    _Case("x window only", x_transfer_ok=True, y_transfer_ok=False),
    _Case("y window only", x_transfer_ok=False, y_transfer_ok=True),
    _Case(
        "head band, middle support, matching lock",
        y_transfer_ok=False,
        x_position=450.0,
        y_position=1300.0,
        frame_locks=("frame_lock_head_mid",),
    ),
    _Case(
        "head band, middle support, other row locked",
        y_transfer_ok=False,
        x_position=450.0,
        y_position=1300.0,
        frame_locks=("frame_lock_head_top",),
    ),
    _Case(
        "head band, middle support, foot lock is irrelevant",
        y_transfer_ok=False,
        x_position=450.0,
        y_position=1300.0,
        frame_locks=("frame_lock_foot_mid",),
    ),
    _Case(
        "foot band, bottom support, matching lock",
        y_transfer_ok=False,
        x_position=7150.0,
        y_position=300.0,
        frame_locks=("frame_lock_foot_btm",),
    ),
    _Case(
        "foot band, bottom support, head lock is irrelevant",
        y_transfer_ok=False,
        x_position=7150.0,
        y_position=300.0,
        frame_locks=("frame_lock_head_btm",),
    ),
    _Case(
        "outside both X bands, inside a support band",
        y_transfer_ok=False,
        x_position=3000.0,
        y_position=1300.0,
    ),
    _Case(
        "outside both X bands, clear of every support band",
        y_transfer_ok=False,
        x_position=3000.0,
        y_position=800.0,
    ),
    _Case(
        "top support band, matching lock",
        y_transfer_ok=False,
        x_position=450.0,
        y_position=2400.0,
        frame_locks=("frame_lock_head_top",),
    ),
    _Case(
        "every frame lock asserted inside a support band",
        y_transfer_ok=False,
        x_position=450.0,
        y_position=300.0,
        frame_locks=tuple(_FRAME_LOCK_BITS),
    ),
    _Case(
        "latch conflict and support conflict together",
        fixed_latched=True,
        actuator_pos=3,
        y_transfer_ok=False,
        x_position=450.0,
        y_position=1300.0,
        frame_locks=("frame_lock_head_mid",),
    ),
)


class MasterZGoLadderParityTests(unittest.TestCase):
    def setUp(self):
        self._saved_tag_instances = list(PLC.Tag.instances)
        self._saved_tag_lookup = dict(PLC.Tag.tag_lookup_table)
        PLC.Tag.instances = []
        PLC.Tag.tag_lookup_table = {}

    def tearDown(self):
        PLC.Tag.instances = self._saved_tag_instances
        PLC.Tag.tag_lookup_table = self._saved_tag_lookup

    def _ladder_limits(self, plc) -> MotionSafetyLimits:
        """Geometry bands as the ladder itself sees them."""
        return MotionSafetyLimits(
            limit_left=0.0,
            limit_right=7500.0,
            limit_bottom=0.0,
            limit_top=2700.0,
            transfer_left=0.0,
            transfer_zone_head_min_x=400.0,
            transfer_zone_head_max_x=500.0,
            transfer_zone_foot_min_x=7100.0,
            transfer_zone_foot_max_x=7200.0,
            support_collision_bottom_min_y=float(
                plc.get_tag("btm_support_collision_ymin")
            ),
            support_collision_bottom_max_y=float(
                plc.get_tag("btm_support_collision_ymax")
            ),
            support_collision_middle_min_y=float(
                plc.get_tag("mid_support_collision_ymin")
            ),
            support_collision_middle_max_y=float(
                plc.get_tag("mid_support_collision_ymax")
            ),
            support_collision_top_min_y=float(
                plc.get_tag("top_support_collision_ymin")
            ),
            support_collision_top_max_y=float(
                plc.get_tag("top_support_collision_ymax")
            ),
        )

    def _drive_ladder(self, case: _Case):
        plc = LadderSimulatedPLC("SIM")

        # MACHINE_SW_STAT bits are re-derived from Local IO on every scan, so
        # they must be pinned with override=True.
        #
        # Everything else must be written with override=False:
        # LadderSimulatedPLC._apply_logic_overrides only re-applies overrides
        # for machine-status bits, their aliases, and "Local:" points.  An
        # override on ACTUATOR_POS or an axis position lands in the override
        # map -- so get_tag() reports it back -- but never reaches the scan
        # context, leaving the rung to evaluate the untouched underlying value.
        plc.set_tag("MACHINE_SW_STAT[7]", 1 if case.fixed_latched else 0, override=True)
        plc.set_tag(
            "MACHINE_SW_STAT[15]", 1 if case.x_transfer_ok else 0, override=True
        )
        plc.set_tag(
            "MACHINE_SW_STAT[17]", 1 if case.y_transfer_ok else 0, override=True
        )
        for name, bit in _FRAME_LOCK_BITS.items():
            plc.set_tag(
                "MACHINE_SW_STAT[" + str(bit) + "]",
                1 if name in case.frame_locks else 0,
                override=True,
            )

        plc.set_tag("ACTUATOR_POS", int(case.actuator_pos), override=False)
        plc.set_tag("X_axis.ActualPosition", float(case.x_position), override=False)
        plc.set_tag("Y_axis.ActualPosition", float(case.y_position), override=False)

        for _ in range(3):
            plc.read("STATE")

        return plc

    def test_mirror_matches_ladder_for_every_case(self):
        for case in _CASES:
            with self.subTest(case=case.name):
                plc = self._drive_ladder(case)

                ladder_ready = bool(plc.get_tag("MASTER_Z_GO"))
                terms = evaluate_master_z_go(
                    transfer_state=case.transfer_state(),
                    x_transfer_ok=case.x_transfer_ok,
                    y_transfer_ok=case.y_transfer_ok,
                    x_position=case.x_position,
                    y_position=case.y_position,
                    limits=self._ladder_limits(plc),
                    collision_state=case.collision_state(),
                )

                self.assertEqual(
                    master_z_go_is_ready(terms),
                    ladder_ready,
                    "MASTER_Z_GO disagreement for " + case.name,
                )

    def test_each_named_term_matches_the_ladder_coil(self):
        ladder_names = {
            "no_latch_collision": "no_latch_collision",
            "no_apa_collision": "no_apa_collision",
            "no_supports_collision": "no_supports_collision",
        }

        for case in _CASES:
            plc = self._drive_ladder(case)
            terms = evaluate_master_z_go(
                transfer_state=case.transfer_state(),
                x_transfer_ok=case.x_transfer_ok,
                y_transfer_ok=case.y_transfer_ok,
                x_position=case.x_position,
                y_position=case.y_position,
                limits=self._ladder_limits(plc),
                collision_state=case.collision_state(),
            )

            for term in terms:
                with self.subTest(case=case.name, term=term.name):
                    self.assertEqual(
                        term.ok,
                        bool(plc.get_tag(ladder_names[term.name])),
                        term.name + " disagreement for " + case.name,
                    )

    def test_blocked_latch_case_reaches_plc_error_5001(self):
        # Ties the mirror back to the operator-facing consequence: the same
        # state the preflight refuses is the one the PLC faults on.
        plc = LadderSimulatedPLC("SIM")
        plc.set_tag("MACHINE_SW_STAT[7]", 1, override=True)
        plc.set_tag("ACTUATOR_POS", 3, override=False)
        plc.write(("Z_POSITION", 43.0))
        plc.write(("Z_SPEED", 100.0))
        plc.write(("STATE_REQUEST", plc.STATE_Z_SEEK))

        for _ in range(3):
            plc.read("STATE")

        self.assertFalse(plc.get_tag("no_latch_collision"))
        self.assertFalse(plc.get_tag("MASTER_Z_GO"))
        self.assertEqual(plc.get_tag("STATE"), plc.STATE_ERROR)
        self.assertIn(plc.get_tag("ERROR_CODE"), (5001, 5004))
        self.assertAlmostEqual(plc.get_tag("Z_axis.ActualPosition"), 0.0, places=6)


class ConstantSourceTests(unittest.TestCase):
    def setUp(self):
        self._saved_tag_instances = list(PLC.Tag.instances)
        self._saved_tag_lookup = dict(PLC.Tag.tag_lookup_table)
        PLC.Tag.instances = []
        PLC.Tag.tag_lookup_table = {}

    def tearDown(self):
        PLC.Tag.instances = self._saved_tag_instances
        PLC.Tag.tag_lookup_table = self._saved_tag_lookup

    def test_documents_known_band_drift(self):
        """
        machineCalibration.json and the ladder disagree on the middle support
        band's upper edge: 1550 vs 1515.

        This is pre-existing -- the same calibration feeds the queued-motion
        keepout boxes in queued_motion/safety.py -- and deciding which value is
        physically right is a machine question, not a code one.  This test pins
        the current values so the discrepancy is visible and so that whoever
        reconciles them has to come here and say so.
        """
        plc = LadderSimulatedPLC("SIM")
        limits = load_motion_safety_limits()

        # Bands that already agree.
        self.assertEqual(
            float(plc.get_tag("btm_support_collision_ymin")),
            limits.support_collision_bottom_min_y,
        )
        self.assertEqual(
            float(plc.get_tag("btm_support_collision_ymax")),
            limits.support_collision_bottom_max_y,
        )
        self.assertEqual(
            float(plc.get_tag("mid_support_collision_ymin")),
            limits.support_collision_middle_min_y,
        )
        self.assertEqual(
            float(plc.get_tag("top_support_collision_ymin")),
            limits.support_collision_top_min_y,
        )
        self.assertEqual(
            float(plc.get_tag("top_support_collision_ymax")),
            limits.support_collision_top_max_y,
        )

        # The one that does not.
        self.assertEqual(float(plc.get_tag("mid_support_collision_ymax")), 1515.0)
        self.assertEqual(limits.support_collision_middle_max_y, 1550.0)


if __name__ == "__main__":
    unittest.main()
