from __future__ import annotations

import unittest

from dune_winder.recipes.line_offset_overrides import (
    apply_line_offset_overrides,
    normalize_line_offset_overrides,
)
from dune_winder.uv_head_target_parts.anchor_to_target import (
    parse_anchor_to_target_command,
)


def _identity(text):
    return " ".join(str(text).split())


class LineOffsetOverridesTests(unittest.TestCase):
    def test_normalize_assigns_zero_z_when_missing(self):
        normalized = normalize_line_offset_overrides({"(1,1)": {"x": 1.0, "y": -2.0}})
        self.assertEqual(normalized["(1,1)"]["x"], 1.0)
        self.assertEqual(normalized["(1,1)"]["y"], -2.0)
        self.assertEqual(normalized["(1,1)"]["z"], 0.0)

    def test_apply_anchor_xy_only_keeps_two_tuple_form(self):
        line = "(1,1) ~anchorToTarget(B400,B1999) (Top B corner)"
        result = apply_line_offset_overrides(
            [line],
            {"(1,1)": {"x": 1.5, "y": -2.25}},
            normalize_line_text_fn=_identity,
        )
        self.assertEqual(
            result, ["(1,1) ~anchorToTarget(B400,B1999,offset=(1.5,-2.25)) (Top B corner)"]
        )

    def test_apply_anchor_xyz_emits_three_tuple(self):
        line = "(1,1) ~anchorToTarget(B400,B1999) (Top B corner)"
        result = apply_line_offset_overrides(
            [line],
            {"(1,1)": {"x": 1.5, "y": -2.25, "z": 0.75}},
            normalize_line_text_fn=_identity,
        )
        self.assertEqual(
            result,
            [
                "(1,1) ~anchorToTarget(B400,B1999,offset=(1.5,-2.25,0.75)) "
                "(Top B corner)"
            ],
        )

    def test_apply_anchor_combines_existing_3tuple_offset(self):
        line = (
            "(1,1) ~anchorToTarget(B400,B1999,offset=(1,2,3)) (Top B corner)"
        )
        result = apply_line_offset_overrides(
            [line],
            {"(1,1)": {"x": 0.5, "y": 0.5, "z": -1.0}},
            normalize_line_text_fn=_identity,
        )
        self.assertEqual(
            result,
            [
                "(1,1) ~anchorToTarget(B400,B1999,offset=(1.5,2.5,2)) "
                "(Top B corner)"
            ],
        )

    def test_apply_non_anchor_line_appends_pz_when_z_present(self):
        line = "(2,3) G103 PB400 PB399 PXY"
        result = apply_line_offset_overrides(
            [line],
            {"(2,3)": {"x": 0.0, "y": 0.0, "z": 1.25}},
            normalize_line_text_fn=_identity,
        )
        self.assertEqual(result, ["(2,3) G103 PB400 PB399 PXY G105 PZ1.25"])

    def test_apply_non_anchor_line_appends_all_axes(self):
        line = "(2,3) G103 PB400 PB399 PXY"
        result = apply_line_offset_overrides(
            [line],
            {"(2,3)": {"x": 1.0, "y": -2.0, "z": 0.5}},
            normalize_line_text_fn=_identity,
        )
        self.assertEqual(
            result,
            ["(2,3) G103 PB400 PB399 PXY G105 PX1 G105 PY-2 G105 PZ0.5"],
        )

    def test_zero_override_leaves_line_unchanged(self):
        line = "(2,3) G103 PB400 PB399 PXY"
        result = apply_line_offset_overrides(
            [line],
            {"(2,3)": {"x": 0.0, "y": 0.0, "z": 0.0}},
            normalize_line_text_fn=_identity,
        )
        self.assertEqual(result, [line])


class AnchorToTargetCommandParseTests(unittest.TestCase):
    def test_parse_no_offset_yields_none(self):
        command = parse_anchor_to_target_command("~anchorToTarget(B400,B1999)")
        self.assertIsNone(command.target_offset)

    def test_parse_xy_offset_promoted_to_3tuple(self):
        command = parse_anchor_to_target_command(
            "~anchorToTarget(B400,B1999,offset=(1.5,-2.25))"
        )
        self.assertEqual(command.target_offset, (1.5, -2.25, 0.0))

    def test_parse_xyz_offset_round_trips(self):
        command = parse_anchor_to_target_command(
            "~anchorToTarget(B400,B1999,offset=(1.5,-2.25,0.75))"
        )
        self.assertEqual(command.target_offset, (1.5, -2.25, 0.75))

    def test_parse_four_element_offset_raises(self):
        with self.assertRaises(Exception):
            parse_anchor_to_target_command(
                "~anchorToTarget(B400,B1999,offset=(1,2,3,4))"
            )


if __name__ == "__main__":
    unittest.main()
