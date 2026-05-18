from __future__ import annotations

import unittest

from dune_winder.recipes.template_recipe_base import _strip_anchor_offset


class StripAnchorOffsetTests(unittest.TestCase):
    def test_strips_line_number_and_wrap_id(self):
        text = "N12 (1,3) ~anchorToTarget(B400,B1999) (Top B corner - foot end)"
        self.assertEqual(
            _strip_anchor_offset(text),
            "~anchorToTarget(B400,B1999) (Top B corner - foot end)",
        )

    def test_strips_xy_offset_keyword(self):
        text = (
            "N5 (1,3) ~anchorToTarget(B400,B1999,offset=(1.5,-2.25)) "
            "(Top B corner - foot end)"
        )
        self.assertEqual(
            _strip_anchor_offset(text),
            "~anchorToTarget(B400,B1999) (Top B corner - foot end)",
        )

    def test_strips_xyz_offset_keyword(self):
        text = (
            "N5 (1,3) ~anchorToTarget(B400,B1999,offset=(1.5,-2.25,0.75)) "
            "(Top B corner - foot end)"
        )
        self.assertEqual(
            _strip_anchor_offset(text),
            "~anchorToTarget(B400,B1999) (Top B corner - foot end)",
        )

    def test_preserves_hover_keyword(self):
        text = (
            "N1 (1,1) ~anchorToTarget(B400,B1999,offset=(1,2,3),hover=True) "
            "(Head A corner)"
        )
        self.assertEqual(
            _strip_anchor_offset(text),
            "~anchorToTarget(B400,B1999,hover=True) (Head A corner)",
        )

    def test_idempotent_on_already_bare_line(self):
        text = "~anchorToTarget(B400,B1999) (Top B corner - foot end)"
        self.assertEqual(_strip_anchor_offset(text), text)


if __name__ == "__main__":
    unittest.main()
