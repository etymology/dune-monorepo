from __future__ import annotations

import os
import tempfile
import unittest

from dune_winder.recipes.template_recipe_base import _strip_anchor_offset
from dune_winder.recipes.v_template_recipe import VTemplateRecipe

from test_template_recipe_persistence import FakeProcess


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


class _Axis:
    def __init__(self, position):
        self._position = float(position)

    def getPosition(self):
        return float(self._position)


class _IO:
    def __init__(self, x, y, z):
        self.xAxis = _Axis(x)
        self.yAxis = _Axis(y)
        self.zAxis = _Axis(z)


class _Handler:
    def __init__(self, line_number):
        self._line = int(line_number)

    def getLine(self):
        return self._line


class _CalibrationProcess(FakeProcess):
    def __init__(self, layer, root, *, trace, position, line_number):
        super().__init__(layer, root)
        self._io = _IO(*position)
        self._last_trace = trace
        self.gCodeHandler = _Handler(line_number)
        self.machineGeometryCalibration = None

    def getLastInstructionTrace(self):
        return self._last_trace

    def isGCodeExecutionActive(self):
        return False


def _trace(line, *, same_side=True, x=0.0, y=0.0, head_z=418.0):
    return {
        "line": line,
        "sameSide": same_side,
        "resultingTarget": {
            "x": float(x),
            "y": float(y),
            "pinZ": float(head_z),
            "headZ": float(head_z),
        },
    }


class JogCalibrationSnapshotTests(unittest.TestCase):
    def test_canonical_corner_label_uses_corner_offset(self):
        with tempfile.TemporaryDirectory() as root:
            trace = _trace(
                "N5 (1,3) ~anchorToTarget(B400,B1999) (Top B corner - foot end)",
                x=10.0,
                y=20.0,
            )
            process = _CalibrationProcess(
                "V", root, trace=trace, position=(10.5, 20.5, 150.0), line_number=5
            )
            service = VTemplateRecipe(process)

            snapshot = service._collectJogCalibrationSnapshot()

            self.assertTrue(snapshot["available"])
            self.assertEqual(snapshot["overrideKind"], "corner")
            self.assertEqual(snapshot["offsetId"], "top_b_foot_end")
            self.assertEqual(snapshot["lineKey"], "(1,3)")
            self.assertAlmostEqual(snapshot["actual"]["z"], 150.0, places=6)

    def test_unlabeled_anchor_falls_back_to_line_override(self):
        with tempfile.TemporaryDirectory() as root:
            # Final-wrap tail line: real anchorToTarget call but its label is
            # not in LABEL_TO_OFFSET_ID.
            trace = _trace(
                "N99 (400,8) ~anchorToTarget(A400,B2398) "
                "(Wrap 400 tail A400 to B2398)",
                x=50.0,
                y=60.0,
            )
            process = _CalibrationProcess(
                "V", root, trace=trace, position=(51.0, 60.0, 150.0), line_number=99
            )
            service = VTemplateRecipe(process)

            snapshot = service._collectJogCalibrationSnapshot()

            self.assertTrue(snapshot["available"])
            self.assertEqual(snapshot["overrideKind"], "line")
            self.assertIsNone(snapshot["offsetId"])
            self.assertEqual(snapshot["lineKey"], "(400,8)")
            self.assertAlmostEqual(snapshot["delta"]["x"], 1.0, places=6)

    def test_non_anchor_line_is_not_calibratable(self):
        with tempfile.TemporaryDirectory() as root:
            trace = _trace("N7 (1,5) G103 PB400 PB399 PXY")
            process = _CalibrationProcess(
                "V", root, trace=trace, position=(0.0, 0.0, 150.0), line_number=7
            )
            service = VTemplateRecipe(process)

            snapshot = service._collectJogCalibrationSnapshot()

            self.assertFalse(snapshot["available"])
            self.assertIn("anchorToTarget", snapshot["reason"])

    def test_actual_z_reads_motor_position(self):
        # Even with head extended at 418, jogging the Z motor down to 147.3
        # must be reported, not the static extended_z_position constant.
        with tempfile.TemporaryDirectory() as root:
            trace = _trace(
                "N5 (1,3) ~anchorToTarget(B400,B1999) (Top B corner - foot end)",
            )
            process = _CalibrationProcess(
                "V", root, trace=trace, position=(0.0, 0.0, 147.3), line_number=5
            )
            service = VTemplateRecipe(process)

            snapshot = service._collectJogCalibrationSnapshot()

            self.assertAlmostEqual(snapshot["actual"]["z"], 147.3, places=6)


if __name__ == "__main__":
    unittest.main()
