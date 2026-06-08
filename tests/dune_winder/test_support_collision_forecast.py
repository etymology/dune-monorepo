import unittest

from dune_winder.core.support_collision_forecast import (
    SUPPORT_COLLISION_KEYS,
    compute_support_collision_forecast,
    current_wrap_number,
    empty_forecast,
    _iter_anchor_to_target_commands,
)


# Head transfer zone X 400-500, foot 7100-7200; support bands bottom 80-450,
# middle 1050-1550, top 2200-2650.
TRANSFER_ZONES = {"head": (400.0, 500.0), "foot": (7100.0, 7200.0)}
SUPPORT_BANDS = {
    "Btm": (80.0, 450.0),
    "Mid": (1050.0, 1550.0),
    "Top": (2200.0, 2650.0),
}


class CurrentWrapNumberTests(unittest.TestCase):
    def test_reads_label_on_current_line(self):
        lines = ["N1 setup\n", "N2 (3,1) move\n", "N3 (3,2) move\n"]
        self.assertEqual(current_wrap_number(lines, 1), 3)

    def test_walks_back_to_most_recent_label(self):
        lines = ["N1 (4,1) start\n", "N2 ~increment(0,-50)\n", "N3 plain\n"]
        self.assertEqual(current_wrap_number(lines, 2), 4)

    def test_ignores_offset_parenthesis_as_label(self):
        lines = ["N1 move ~anchorToTarget(A1,A2,offset=(1,0))\n"]
        self.assertIsNone(current_wrap_number(lines, 0))

    def test_ignores_increment_negative_value(self):
        lines = ["N1 ~increment(0,-50)\n"]
        self.assertIsNone(current_wrap_number(lines, 0))

    def test_scans_forward_when_before_first_label(self):
        lines = ["N1 preamble\n", "N2 (1,1) start\n"]
        self.assertEqual(current_wrap_number(lines, -1), 1)


class IterAnchorCommandsTests(unittest.TestCase):
    def test_extracts_balanced_command_with_offset(self):
        line = "N5 (5,2) ~anchorToTarget(A12,A34,offset=(1,0)) trailing\n"
        results = list(_iter_anchor_to_target_commands(line))
        self.assertEqual(len(results), 1)
        command, anchor, target = results[0]
        self.assertEqual(command, "~anchorToTarget(A12,A34,offset=(1,0))")
        self.assertEqual(anchor, "A12")
        self.assertEqual(target, "A34")

    def test_extracts_multiple_commands(self):
        line = "~anchorToTarget(B1,B2) ~anchorToTarget(A3,B4)\n"
        results = list(_iter_anchor_to_target_commands(line))
        self.assertEqual([r[1:] for r in results], [("B1", "B2"), ("A3", "B4")])


class ForecastTests(unittest.TestCase):
    def _flags(self, lines, current_line, head_points):
        def head_point_fn(command_text):
            return head_points.get(command_text)

        return compute_support_collision_forecast(
            lines,
            current_line,
            head_point_fn=head_point_fn,
            transfer_zones=TRANSFER_ZONES,
            support_bands=SUPPORT_BANDS,
            wraps_ahead=1,
        )

    def test_same_side_head_transfer_into_top_band_blinks_head_top(self):
        lines = [
            "N1 (5,1) ~anchorToTarget(A1,A2)\n",
            "N2 (5,2) ~anchorToTarget(B3,B4)\n",
        ]
        # A1->A2 same side, ends in head transfer zone at a top-band Y.
        flags = self._flags(
            lines,
            0,
            {
                "~anchorToTarget(A1,A2)": (450.0, 2400.0),
                "~anchorToTarget(B3,B4)": (450.0, 2400.0),
            },
        )
        self.assertTrue(flags["headTop"])
        # B3->B4 also same-side and lands in the same box.
        self.assertEqual(
            {k for k, v in flags.items() if v},
            {"headTop"},
        )

    def test_alternating_side_command_is_ignored(self):
        lines = ["N1 (2,1) ~anchorToTarget(A1,B2)\n"]
        flags = self._flags(lines, 0, {"~anchorToTarget(A1,B2)": (7150.0, 1300.0)})
        self.assertFalse(any(flags.values()))

    def test_includes_next_wrap(self):
        lines = [
            "N1 (5,1) ~anchorToTarget(A1,A2)\n",
            "N2 (6,1) ~anchorToTarget(B7,B8)\n",
        ]
        flags = self._flags(
            lines,
            0,
            {
                "~anchorToTarget(A1,A2)": (450.0, 300.0),  # head bottom
                "~anchorToTarget(B7,B8)": (7150.0, 1300.0),  # foot middle (wrap 6)
            },
        )
        self.assertTrue(flags["headBtm"])
        self.assertTrue(flags["footMid"])

    def test_endpoint_outside_any_box_does_not_blink(self):
        lines = ["N1 (3,1) ~anchorToTarget(B1,B2)\n"]
        # X inside no transfer zone.
        flags = self._flags(lines, 0, {"~anchorToTarget(B1,B2)": (3000.0, 1300.0)})
        self.assertFalse(any(flags.values()))

    def test_no_wrap_label_returns_empty(self):
        flags = self._flags(["N1 plain move\n"], 0, {})
        self.assertEqual(flags, empty_forecast())
        self.assertEqual(set(flags), set(SUPPORT_COLLISION_KEYS))


if __name__ == "__main__":
    unittest.main()
