import unittest

from dune_winder.recipes.offset_axis_policy import (
    enforce_offset_axes,
    enforce_offset_dict,
    enforce_offset_natural_axis,
    natural_axis_for_pin,
    round_to_tenth,
)


class RoundToTenthTests(unittest.TestCase):
    def test_sub_tenth_magnitudes_are_zero(self):
        # The deadband is 0.1 mm: anything smaller in magnitude is treated as
        # zero, including values that would otherwise round up to 0.1.
        for value in (0.0, 0.04, 0.05, 0.09, -0.099):
            self.assertEqual(round_to_tenth(value), 0.0)

    def test_quantises_to_nearest_tenth(self):
        self.assertEqual(round_to_tenth(0.1), 0.1)
        self.assertEqual(round_to_tenth(0.94), 0.9)
        self.assertEqual(round_to_tenth(4.737), 4.7)
        self.assertEqual(round_to_tenth(-2.394), -2.4)
        self.assertEqual(round_to_tenth(-1.0004), -1.0)


class EnforceAxesTests(unittest.TestCase):
    def test_off_axis_component_is_zeroed(self):
        self.assertEqual(enforce_offset_axes(2.39, 1.5, "x"), (2.4, 0.0))
        self.assertEqual(enforce_offset_axes(2.39, 1.5, "y"), (0.0, 1.5))

    def test_unknown_axis_zeroes_both(self):
        self.assertEqual(enforce_offset_axes(2.0, 3.0, None), (0.0, 0.0))

    def test_enforce_dict_accepts_scalar_on_natural_axis(self):
        self.assertEqual(enforce_offset_dict(1.5, "y"), {"x": 0.0, "y": 1.5})
        self.assertEqual(enforce_offset_dict(1.5, "x"), {"x": 1.5, "y": 0.0})

    def test_enforce_dict_drops_off_axis(self):
        self.assertEqual(
            enforce_offset_dict({"x": 0.18, "y": 0.0}, "y"), {"x": 0.0, "y": 0.0}
        )


class NaturalAxisForPinTests(unittest.TestCase):
    def test_v_faces_map_to_expected_axis(self):
        self.assertEqual(natural_axis_for_pin("V", "A1"), "y")  # head
        self.assertEqual(natural_axis_for_pin("V", "B399"), "y")  # head
        self.assertEqual(natural_axis_for_pin("V", "B400"), "x")  # bottom
        self.assertEqual(natural_axis_for_pin("V", "B2000"), "x")  # top

    def test_unrecognised_pin_is_none(self):
        self.assertIsNone(natural_axis_for_pin("V", "nope"))


class EnforceNaturalAxisInLinesTests(unittest.TestCase):
    def test_off_axis_component_dropped_keeps_trailing_kwargs(self):
        line = (
            "N3 (1,1) ~anchorToTarget(A2399,B400,offset=(0.5,-2.39),inTwoMoves=True)"
            " (Bottom B corner - head end)"
        )
        # B400 is on the bottom face (X-natural): the Y component is dropped and
        # the X component quantised; inTwoMoves and the label are preserved.
        (out,) = enforce_offset_natural_axis([line], layer="V")
        self.assertEqual(
            out,
            "N3 (1,1) ~anchorToTarget(A2399,B400,offset=(0.5,0),inTwoMoves=True)"
            " (Bottom B corner - head end)",
        )

    def test_both_components_zero_drops_offset_entirely(self):
        line = "N18 (1,16) ~anchorToTarget(B399,A1,offset=(0.177843,0)) (Head A corner)"
        # A1 is on the head face (Y-natural): the X-only offset collapses to zero
        # and the offset keyword is removed rather than rendered as offset=(0,0).
        (out,) = enforce_offset_natural_axis([line], layer="V")
        self.assertEqual(
            out, "N18 (1,16) ~anchorToTarget(B399,A1) (Head A corner)"
        )

    def test_on_axis_value_is_quantised(self):
        line = "N1 ~anchorToTarget(A1,A2398,offset=(4.73765,0)) (Top B corner - foot end)"
        (out,) = enforce_offset_natural_axis([line], layer="V")
        self.assertIn("offset=(4.7,0)", out)

    def test_non_anchor_lines_pass_through(self):
        line = "N4 (1,2) ~increment(0,50)"
        self.assertEqual(enforce_offset_natural_axis([line], layer="V"), [line])


if __name__ == "__main__":
    unittest.main()
