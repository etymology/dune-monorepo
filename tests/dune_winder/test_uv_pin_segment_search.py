import unittest

from dune_winder.core.manual_calibration import LAYER_METADATA
from dune_winder.core.winder_workspace import WinderWorkspace
from dune_winder.recipes.u_template_gcode import render_u_template_lines
from dune_winder.recipes.v_template_gcode import render_v_template_lines


class FakeRecipe:
    def __init__(self, lines):
        self._lines = lines

    def getLines(self):
        return list(self._lines)


class FakeGCodeHandler:
    def __init__(self):
        self.lines = []
        self.lastSetLine = None

    def setLine(self, line):
        self.lastSetLine = line
        return False


class UvPinSegmentSearchTests(unittest.TestCase):
    def _workspace(self, layer, lines):
        workspace = object.__new__(WinderWorkspace)
        workspace._layer = layer
        workspace._recipe = FakeRecipe(lines)
        workspace._gCodeHandler = FakeGCodeHandler()
        return workspace

    def _expected_u_a_pin(self, bPin):
        return WinderWorkspace._getOppositeFamilyPinMap("U")[bPin]

    def test_v_board_pin_resolution_matches_requested_examples(self):
        workspace = self._workspace("V", render_v_template_lines())

        self.assertEqual(
            workspace._resolveUvBoardPin("B", "head", 1, 40)["pinName"], "PB40"
        )
        self.assertEqual(
            workspace._resolveUvBoardPin("B", "head", 10, 39)["pinName"], "PB399"
        )
        self.assertEqual(
            workspace._resolveUvBoardPin("A", "head", 10, 39)["pinName"], "PA1"
        )
        self.assertEqual(
            workspace._resolveUvBoardPin("B", "bottom", 1, 1)["pinName"], "PB400"
        )
        self.assertEqual(
            workspace._resolveUvBoardPin("A", "bottom", 1, 1)["pinName"], "PA2399"
        )

    def test_u_board_pin_resolution_uses_active_layer_mapping(self):
        workspace = self._workspace("U", render_u_template_lines())

        self.assertEqual(
            workspace._resolveUvBoardPin("B", "head", 1, 40)["pinName"], "PB40"
        )
        self.assertEqual(
            workspace._resolveUvBoardPin("B", "head", 10, 39)["pinName"], "PB399"
        )
        self.assertEqual(
            workspace._resolveUvBoardPin("A", "head", 10, 39)["pinName"],
            "PA" + str(self._expected_u_a_pin(399)),
        )
        self.assertEqual(
            workspace._resolveUvBoardPin("B", "bottom", 1, 1)["pinName"], "PB401"
        )
        self.assertEqual(
            workspace._resolveUvBoardPin("A", "bottom", 1, 1)["pinName"],
            "PA" + str(self._expected_u_a_pin(401)),
        )

    def test_find_v_pin_segment_reports_preamble_segment(self):
        workspace = self._workspace("V", render_v_template_lines())

        result = workspace.findUvPinSegment("B", "bottom", 1, 1)

        self.assertEqual(result["pinName"], "PB400")
        self.assertEqual(result["segmentStartLine"], 3)
        self.assertEqual(result["segmentStartLineNumber"], 4)
        self.assertEqual(result["matchedLine"], 3)
        self.assertEqual(result["segmentEndLine"], 3)
        self.assertEqual(result["pinRole"], "start")
        self.assertEqual(result["segmentLines"], 1)

    def test_find_v_pin_segment_reports_end_role(self):
        workspace = self._workspace("V", render_v_template_lines())

        result = workspace.findUvPinSegment("B", "head", 1, 40)

        self.assertEqual(result["pinName"], "PB40")
        self.assertEqual(result["pinRole"], "end")
        self.assertEqual(result["segmentSide"], "B")
        self.assertEqual(result["segmentStartLine"], 9032)
        self.assertEqual(result["matchedLine"], 9032)
        self.assertEqual(result["segmentEndLine"], 9032)

    def test_find_v_pin_segment_reports_interior_role_for_b_family(self):
        workspace = self._workspace("V", render_v_template_lines())

        result = workspace.findUvPinSegment("B", "foot", 1, 2)

        self.assertEqual(result["pinRole"], "interior")
        self.assertEqual(result["pinName"], "PB1201")
        self.assertEqual(result["segmentSide"], "B")
        self.assertEqual(result["segmentStartLine"], 11)
        self.assertEqual(result["matchedLine"], 11)
        self.assertEqual(result["segmentEndLine"], 13)

    def test_find_u_pin_segment_respects_transfer_boundaries_with_same_family_lines(
        self,
    ):
        workspace = self._workspace("U", render_u_template_lines())

        result = workspace.findUvPinSegment("B", "foot", 1, 2)

        self.assertEqual(result["pinName"], "PB1202")
        self.assertEqual(result["pinRole"], "start")
        self.assertEqual(result["segmentStartLine"], 27)
        self.assertEqual(result["segmentEndLine"], 28)
        self.assertEqual(result["segmentLines"], 2)

    def test_jump_to_uv_pin_segment_moves_to_segment_start(self):
        workspace = self._workspace("V", render_v_template_lines())

        result = workspace.jumpToUvPinSegment("B", "head", 1, 40)

        self.assertEqual(result["jumpedToLine"], result["segmentStartLine"])
        self.assertEqual(
            workspace._gCodeHandler.lastSetLine, result["segmentStartLine"]
        )

    def test_find_uv_pin_segment_rejects_invalid_inputs(self):
        workspace = self._workspace("V", render_v_template_lines())

        with self.assertRaisesRegex(ValueError, "Side must be 'A' or 'B'"):
            workspace.findUvPinSegment("C", "head", 1, 1)
        with self.assertRaisesRegex(ValueError, "Board side must be one of"):
            workspace.findUvPinSegment("B", "left", 1, 1)
        with self.assertRaisesRegex(ValueError, "board_number 999 is outside"):
            workspace.findUvPinSegment("B", "head", 999, 1)
        with self.assertRaisesRegex(ValueError, "pin_number 999 is outside"):
            workspace.findUvPinSegment("B", "head", 1, 999)

    def test_find_uv_pin_segment_rejects_non_uv_layers(self):
        workspace = self._workspace("X", ["N0 X0 Y0"])

        with self.assertRaisesRegex(
            ValueError, "only available for the U and V layers"
        ):
            workspace.findUvPinSegment("B", "head", 1, 1)

    def test_find_uv_pin_segment_rejects_missing_recipe(self):
        workspace = object.__new__(WinderWorkspace)
        workspace._layer = "V"
        workspace._recipe = None
        workspace._gCodeHandler = FakeGCodeHandler()

        with self.assertRaisesRegex(ValueError, "No recipe is loaded"):
            workspace.findUvPinSegment("B", "head", 1, 1)

    def test_find_uv_pin_segment_rejects_when_resolved_pin_is_absent(self):
        workspace = self._workspace("V", ["N0 ( V Layer )", "N1 G103 PB1 PB2 PXY"])

        with self.assertRaisesRegex(
            ValueError, "does not appear in any same-side segment"
        ):
            workspace.findUvPinSegment("B", "head", 1, 40)

    def test_u_mapping_uses_metadata_board_counts(self):
        workspace = self._workspace("U", render_u_template_lines())
        metadata = LAYER_METADATA["U"]
        sideBoards = [
            board for board in metadata["boards"] if board["side"] == "bottom"
        ]

        result = workspace._resolveUvBoardPin("B", "bottom", len(sideBoards), 1)

        self.assertEqual(result["boardNumber"], len(sideBoards))
        self.assertEqual(result["pin"], sideBoards[-1]["startPin"])


if __name__ == "__main__":
    unittest.main()
