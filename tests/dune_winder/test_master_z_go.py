"""Unit tests for the Python mirror of the PLC MASTER_Z_GO rung.

Source of truth: winder/plc/state_5_move_z/main/main.rung:13-19

    no_latch_collision    = Z_FIXED_LATCHED and ACTUATOR_POS == 2
                            or not Z_FIXED_LATCHED
    no_apa_collision      = X_XFER_OK or Y_XFER_OK
    no_supports_collision = X_XFER_OK and ( ... ) or Y_XFER_OK
"""

from __future__ import annotations

import unittest

from dune_winder.core.master_z_go import (
    MASTER_Z_GO_ERROR_CODE,
    TERM_NO_APA_COLLISION,
    TERM_NO_LATCH_COLLISION,
    TERM_NO_SUPPORTS_COLLISION,
    evaluate_master_z_go,
    format_master_z_go_message,
    master_z_go_is_ready,
)
from dune_winder.queued_motion.safety import (
    MotionSafetyLimits,
    QueuedMotionCollisionState,
)


def _limits(**overrides) -> MotionSafetyLimits:
    base = dict(
        limit_left=0.0,
        limit_right=7500.0,
        limit_bottom=0.0,
        limit_top=2700.0,
        transfer_left=0.0,
    )
    base.update(overrides)
    return MotionSafetyLimits(**base)


def _transfer_state(**overrides):
    state = {
        "stagePresent": True,
        "fixedPresent": False,
        "stageLatched": True,
        "fixedLatched": False,
        "zExtended": False,
        "enableActuator": False,
        "actuatorPos": 1,
        "zPosition": 0.0,
    }
    state.update(overrides)
    return state


def _evaluate(**overrides):
    kwargs = dict(
        transfer_state=_transfer_state(),
        x_transfer_ok=True,
        y_transfer_ok=True,
        # Y clear of every support band (bottom 80-450, middle 1050-1550,
        # top 2200-2650), X inside the head transfer band 400-500.
        x_position=450.0,
        y_position=800.0,
        limits=_limits(),
        collision_state=QueuedMotionCollisionState(),
    )
    kwargs.update(overrides)
    return evaluate_master_z_go(**kwargs)


def _term(terms, name):
    return next(term for term in terms if term.name == name)


class MasterZGoReadyTests(unittest.TestCase):
    def test_all_terms_hold_in_a_clean_state(self):
        terms = _evaluate()

        self.assertTrue(master_z_go_is_ready(terms))
        self.assertEqual(
            [term.name for term in terms],
            [
                TERM_NO_LATCH_COLLISION,
                TERM_NO_APA_COLLISION,
                TERM_NO_SUPPORTS_COLLISION,
            ],
        )


class NoLatchCollisionTests(unittest.TestCase):
    def test_holds_when_not_fixed_latched(self):
        terms = _evaluate(
            transfer_state=_transfer_state(fixedLatched=False, actuatorPos=3)
        )

        self.assertTrue(_term(terms, TERM_NO_LATCH_COLLISION).ok)

    def test_holds_when_fixed_latched_at_mid_engagement(self):
        terms = _evaluate(
            transfer_state=_transfer_state(fixedLatched=True, actuatorPos=2)
        )

        self.assertTrue(_term(terms, TERM_NO_LATCH_COLLISION).ok)

    def test_fails_when_fixed_latched_at_rocker_at_fixed(self):
        terms = _evaluate(
            transfer_state=_transfer_state(fixedLatched=True, actuatorPos=3)
        )

        term = _term(terms, TERM_NO_LATCH_COLLISION)
        self.assertFalse(term.ok)
        self.assertIn("ACTUATOR_POS=3", term.detail)
        # The other two terms are unaffected.
        self.assertTrue(_term(terms, TERM_NO_APA_COLLISION).ok)
        self.assertTrue(_term(terms, TERM_NO_SUPPORTS_COLLISION).ok)

    def test_supplied_latch_detail_wins(self):
        terms = _evaluate(
            transfer_state=_transfer_state(fixedLatched=True, actuatorPos=0),
            latch_detail="custom explanation from the head controller",
        )

        self.assertEqual(
            _term(terms, TERM_NO_LATCH_COLLISION).detail,
            "custom explanation from the head controller",
        )


class NoApaCollisionTests(unittest.TestCase):
    def test_holds_when_either_transfer_window_is_true(self):
        self.assertTrue(
            _term(
                _evaluate(x_transfer_ok=True, y_transfer_ok=False),
                TERM_NO_APA_COLLISION,
            ).ok
        )
        self.assertTrue(
            _term(
                _evaluate(x_transfer_ok=False, y_transfer_ok=True),
                TERM_NO_APA_COLLISION,
            ).ok
        )

    def test_fails_when_neither_transfer_window_is_true(self):
        terms = _evaluate(x_transfer_ok=False, y_transfer_ok=False)

        term = _term(terms, TERM_NO_APA_COLLISION)
        self.assertFalse(term.ok)
        self.assertIn("X_XFER_OK=0", term.detail)
        self.assertIn("Y_XFER_OK=0", term.detail)
        self.assertFalse(master_z_go_is_ready(terms))


class NoSupportsCollisionTests(unittest.TestCase):
    def test_y_transfer_ok_short_circuits_the_whole_term(self):
        # Y_XFER_OK is the trailing OR of the rung, so even a fully blocked
        # support band cannot fail the term.
        terms = _evaluate(
            x_transfer_ok=False,
            y_transfer_ok=True,
            x_position=3000.0,
            y_position=1300.0,
            collision_state=QueuedMotionCollisionState(frame_lock_head_mid=True),
        )

        self.assertTrue(_term(terms, TERM_NO_SUPPORTS_COLLISION).ok)

    def test_holds_when_y_is_outside_every_support_band(self):
        terms = _evaluate(x_transfer_ok=True, y_transfer_ok=False, y_position=800.0)

        self.assertTrue(_term(terms, TERM_NO_SUPPORTS_COLLISION).ok)

    def test_fails_when_matching_head_frame_lock_is_asserted(self):
        # Y in the middle support band (1050-1550), X in the head band
        # (400-500), FRAME_LOC_HD_MID asserted.
        terms = _evaluate(
            x_transfer_ok=True,
            y_transfer_ok=False,
            x_position=450.0,
            y_position=1300.0,
            collision_state=QueuedMotionCollisionState(frame_lock_head_mid=True),
        )

        term = _term(terms, TERM_NO_SUPPORTS_COLLISION)
        self.assertFalse(term.ok)
        self.assertIn("middle", term.detail)
        self.assertIn("FRAME_LOC_HD_MID", term.detail)

    def test_holds_when_a_different_row_frame_lock_is_asserted(self):
        terms = _evaluate(
            x_transfer_ok=True,
            y_transfer_ok=False,
            x_position=450.0,
            y_position=1300.0,
            collision_state=QueuedMotionCollisionState(frame_lock_head_top=True),
        )

        self.assertTrue(_term(terms, TERM_NO_SUPPORTS_COLLISION).ok)

    def test_foot_band_uses_the_foot_frame_locks(self):
        blocked = _evaluate(
            x_transfer_ok=True,
            y_transfer_ok=False,
            x_position=7150.0,
            y_position=300.0,
            collision_state=QueuedMotionCollisionState(frame_lock_foot_btm=True),
        )
        self.assertFalse(_term(blocked, TERM_NO_SUPPORTS_COLLISION).ok)

        # The head-side lock is irrelevant when X sits in the foot band.
        clear = _evaluate(
            x_transfer_ok=True,
            y_transfer_ok=False,
            x_position=7150.0,
            y_position=300.0,
            collision_state=QueuedMotionCollisionState(frame_lock_head_btm=True),
        )
        self.assertTrue(_term(clear, TERM_NO_SUPPORTS_COLLISION).ok)

    def test_fails_when_x_is_in_neither_transfer_band(self):
        terms = _evaluate(
            x_transfer_ok=True,
            y_transfer_ok=False,
            x_position=3000.0,
            y_position=1300.0,
        )

        term = _term(terms, TERM_NO_SUPPORTS_COLLISION)
        self.assertFalse(term.ok)
        self.assertIn("neither the head band", term.detail)

    def test_support_bands_are_inclusive_like_ladder_lim(self):
        on_edge = _evaluate(
            x_transfer_ok=True,
            y_transfer_ok=False,
            x_position=450.0,
            y_position=1050.0,
            collision_state=QueuedMotionCollisionState(frame_lock_head_mid=True),
        )

        self.assertFalse(_term(on_edge, TERM_NO_SUPPORTS_COLLISION).ok)


class MessageFormattingTests(unittest.TestCase):
    def test_message_names_each_term_and_the_plc_error_code(self):
        terms = _evaluate(
            transfer_state=_transfer_state(fixedLatched=True, actuatorPos=3),
            x_transfer_ok=False,
            y_transfer_ok=False,
        )

        message = format_master_z_go_message(terms, state_summary="actuatorPos=3")

        self.assertIn("MASTER_Z_GO transfer lockout is not ready", message)
        self.assertIn(TERM_NO_LATCH_COLLISION, message)
        self.assertIn(TERM_NO_APA_COLLISION, message)
        self.assertIn(TERM_NO_SUPPORTS_COLLISION, message)
        self.assertIn("ERROR_CODE " + str(MASTER_Z_GO_ERROR_CODE), message)
        self.assertIn("actuatorPos=3", message)

    def test_passing_terms_render_as_ok(self):
        terms = _evaluate(
            transfer_state=_transfer_state(fixedLatched=True, actuatorPos=3)
        )

        message = format_master_z_go_message(terms)

        self.assertIn(TERM_NO_SUPPORTS_COLLISION + ": OK", message)


if __name__ == "__main__":
    unittest.main()
