import tempfile
import unittest
from pathlib import Path

from _template_gcode_test_support import MERGE, TOLERANT, coord
from dune_winder.recipes.v_template_gcode import (
    DEFAULT_V_TEMPLATE_ROW_COUNT,
    PRE_FINAL_WRAP_COUNT,
    SCRIPT_VARIANT_WRAPPING,
    VTemplateProgrammaticGenerator,
    WRAP_COUNT,
    WRAPPING_X_PULL_IN,
    WRAPPING_Y_PULL_IN,
    X_PULL_IN,
    Y_PULL_IN,
    get_v_template_named_inputs_snapshot,
    _normalize_pin_tokens,
    iter_v_wrap_primary_sites,
    render_default_v_template_text_lines,
    render_v_template_text_lines,
    write_v_template_text_file,
    write_v_template_file,
)


class VTemplateGCodeTests(unittest.TestCase):
    MERGE = MERGE
    TOLERANT = TOLERANT

    def _coord(self, axis, value):
        return coord(axis, value)

    def test_pb_pf_tokens_wrap_back_into_valid_pin_range(self):
        self.assertEqual(
            _normalize_pin_tokens("G103 PB2401 PA2402 PB0 PF-1 PA1 PBL PRT"),
            "G103 PB2 PA3 PB2399 PA2398 PA1 PBL PRT",
        )

    def test_default_render_matches_expected_spec_edges(self):
        lines = render_v_template_text_lines()

        self.assertEqual(len(lines), DEFAULT_V_TEMPLATE_ROW_COUNT)
        self.assertEqual(
            lines[:5],
            [
                "N0 ( V Layer )",
                "N1 " + self.MERGE + "(HEAD RESTART) X440 Y0",
                "N2 G206 P3",
                "N3 "
                + self.MERGE
                + "(0, ) F1000 G103 PB400 PB399 PXY G105 PY30 (board gap)",
                "N4 (1,1) (------------------STARTING LOOP 1------------------)",
            ],
        )
        tail_start = len(lines) - 9
        self.assertEqual(
            lines[-9:],
            [
                "N"
                + str(tail_start)
                + " "
                + self.TOLERANT
                + "(400,16) G109 PA400 PRT G103 PB2398 PB2399 PX (Top B corner - head end)",
                "N"
                + str(tail_start + 1)
                + " "
                + self.TOLERANT
                + "(400,17) G103 PB2398 PB2399 PY G105 "
                + self._coord("PY", -Y_PULL_IN),
                "N"
                + str(tail_start + 2)
                + " "
                + self.MERGE
                + "(400,18) G103 PB2398 PB2399 PY G105 PY0 G111",
                "N"
                + str(tail_start + 3)
                + " "
                + self.MERGE
                + "(400,19) X440 Y2250 F300",
                "N" + str(tail_start + 4) + " (400,20) G206 P0",
                "N" + str(tail_start + 5) + " " + self.MERGE + "(400,21) X440 Y2335",
                "N"
                + str(tail_start + 6)
                + " "
                + self.MERGE
                + "(400,22) X650 Y2335 G111",
                "N"
                + str(tail_start + 7)
                + " "
                + self.MERGE
                + "(400,23) X1200 Y2335 G111",
                "N" + str(tail_start + 8) + " " + self.MERGE + "(400,24) X440 Y2335",
            ],
        )

    def test_cached_reader_is_now_the_programmatic_default(self):
        self.assertEqual(
            render_default_v_template_text_lines(),
            render_v_template_text_lines(),
        )

    def test_named_inputs_and_special_aliases_remain_usable(self):
        lines = render_v_template_text_lines(
            named_inputs={
                "line 1 (Top B corner - foot end)": 2,
                "pause at combs": True,
            }
        )
        self.assertEqual(
            lines[5],
            "N5 "
            + self.MERGE
            + "(1,2) G109 PB400 PRT G103 PB1998 PB1999 PXY G105 PX2 G102 G108 (Top B corner - foot end)",
        )
        self.assertEqual(lines[7], "N7 (1,4) G206 P0")

        special_lines = render_v_template_text_lines(
            special_inputs={"head_a_offset": 7}
        )
        self.assertIn(
            "N23 "
            + self.TOLERANT
            + "(1,20) G109 PB399 PBR G103 PA1 PA2 PXY G105 PY7 (Head A corner)",
            special_lines,
        )

    def test_pull_in_overrides_update_generated_motion(self):
        lines = render_v_template_text_lines(
            special_inputs={
                "Y_PULL_IN": 82.5,
                "x_pull_in": 91.5,
            }
        )

        self.assertIn(
            "N8 "
            + self.TOLERANT
            + "(1,5) G103 PA800 PA799 PY G105 "
            + self._coord("PY", -82.5),
            lines,
        )
        self.assertIn(
            "N12 "
            + self.TOLERANT
            + "(1,9) G103 PB1200 PB1201 PX G105 "
            + self._coord("PX", -91.5),
            lines,
        )

    def test_xz_script_variant_uses_xz_base_script(self):
        lines = render_v_template_text_lines(script_variant="xz")

        self.assertEqual(
            lines[7],
            "N7 "
            + self.MERGE
            + "(1,4) G109 PB1999 PLT G103 PA800 PA799 Z0 PXZ (Top A corner - foot end)",
        )
        self.assertEqual(
            lines[8],
            "N8 "
            + self.TOLERANT
            + "(1,5) G103 PA800 PA799 PY G105 "
            + self._coord("PY", -Y_PULL_IN),
        )
        self.assertIn("ZEXTEND PXZ", "\n".join(lines))

    def test_offset_vector_maps_to_all_twelve_adjustment_sites(self):
        generator = VTemplateProgrammaticGenerator(
            special_inputs={"offsets": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13]}
        )
        lines = generator.render_lines()

        expected_first_wrap = [
            "N5 "
            + self.MERGE
            + "(1,2) G109 PB400 PRT G103 PB1998 PB1999 PXY G105 PX1 G102 G108 (Top B corner - foot end)",
            "N7 "
            + self.MERGE
            + "(1,4) G109 PB1999 PLT G103 PA800 PA799 PX G105 PX2 (Top A corner - foot end)",
            "N9 "
            + self.MERGE
            + "(1,6) G109 PA800 PRB G103 PA1600 PA1599 PXY G105 PY3 G102 G108 (Foot A corner)",
            "N11 "
            + self.MERGE
            + "(1,8) G109 PA1599 PBL G103 PB1200 PB1201 PY G105 PY4 (Foot B corner)",
            "N13 "
            + self.MERGE
            + "(1,10) G109 PB1200 PTR G103 PB1199 PB1198 PXY G105 PX5 G102 G108 (Bottom B corner - foot end)",
            "N15 "
            + self.MERGE
            + "(1,12) G109 PB1199 PBR G103 PA1599 PA1600 PX G105 PX6 (Bottom A corner - foot end)",
            "N17 "
            + self.MERGE
            + "(1,14) G109 PA1600 PLT G103 PA799 PA798 PXY G105 PX7 G102 G108 (Top A corner - head end)",
            "N19 "
            + self.TOLERANT
            + "(1,16) G109 PA799 PRT G103 PB1999 PB2000 PX G105 PX8 (Top B corner - head end)",
            "N21 "
            + self.MERGE
            + "(1,18) (HEAD RESTART) G109 PB2000 PLB G103 PB400 PB399 PXY G105 PY9 G102 G108 (Head B corner)",
            "N23 "
            + self.TOLERANT
            + "(1,20) G109 PB399 PBR G103 PA1 PA2 PXY G105 PY10 (Head A corner)",
            "N25 "
            + self.MERGE
            + "(1,22) G109 PA1 PTL G103 PA2398 PA2397 PXY G105 PX11 G102 G108 (Bottom A corner - head end)",
            "N27 "
            + self.MERGE
            + "(1,24) G109 PA2398 PBL G103 PB400 PB401 PX G105 PX13 (Bottom B corner - head end)",
        ]
        for expected_line in expected_first_wrap:
            self.assertIn(expected_line, lines)

        self.assertEqual(
            generator.get_value("AC", 24),
            "N23 "
            + self.TOLERANT
            + "(1,20) G109 PB399 PBR G103 PA1 PA2 PXY G105 PY10 (Head A corner)",
        )

    def test_transfer_pause_adds_all_optional_pause_lines(self):
        base_lines = render_v_template_text_lines()
        paused_lines = render_v_template_text_lines(
            special_inputs={"transferPause": True}
        )

        self.assertEqual(
            len(paused_lines) - len(base_lines), PRE_FINAL_WRAP_COUNT * 6 + 4
        )
        self.assertEqual(paused_lines[6], "N6 (1,3) G206 P2")
        self.assertEqual(paused_lines[11], "N11 (1,8) G206 P1")
        self.assertEqual(paused_lines[16], "N16 (1,13) G206 P2")

    def test_named_input_snapshot_and_file_writers(self):
        named_inputs = get_v_template_named_inputs_snapshot()
        self.assertFalse(named_inputs["transferPause"])
        self.assertFalse(named_inputs["addFootPauses"])
        self.assertEqual(named_inputs["line 10 (Head A corner)"], 0.0)
        self.assertEqual(named_inputs["Y_PULL_IN"], Y_PULL_IN)
        self.assertEqual(named_inputs["X_PULL_IN"], X_PULL_IN)

        with tempfile.TemporaryDirectory() as directory:
            plain_output = Path(directory) / "V_template.txt"
            recipe_output = Path(directory) / "V-layer.gc"

            write_v_template_text_file(
                plain_output, special_inputs={"head_a_offset": 7}
            )
            plain_lines = plain_output.read_text(encoding="utf-8").splitlines()
            self.assertIn(
                "N23 "
                + self.TOLERANT
                + "(1,20) G109 PB399 PBR G103 PA1 PA2 PXY G105 PY7 (Head A corner)",
                plain_lines,
            )

            recipe = write_v_template_file(
                recipe_output,
                special_inputs={
                    "head_a_offset": 7,
                    "transferPause": True,
                    "Y_PULL_IN": 82.5,
                    "X_PULL_IN": 91.5,
                },
            )
            recipe_lines = recipe_output.read_text(encoding="utf-8").splitlines()

        self.assertTrue(recipe_lines[0].startswith("( V-layer "))
        self.assertEqual(recipe_lines[1], "N0 ( V Layer )")
        self.assertTrue(recipe["transferPause"])
        self.assertEqual(recipe["fileName"], "V-layer.gc")
        self.assertEqual(recipe["pullIns"]["Y_PULL_IN"], 82.5)
        self.assertEqual(recipe["pullIns"]["X_PULL_IN"], 91.5)

    def test_add_foot_pauses_appends_g111_only_on_qualifying_lines(self):
        base_lines = render_v_template_text_lines()
        paused_lines = render_v_template_text_lines(add_foot_pauses=True)

        self.assertEqual(
            paused_lines[9],
            "N9 "
            + self.MERGE
            + "(1,6) G109 PA800 PRB G103 PA1600 PA1599 PXY G102 G108 G111 (board gap) (Foot A corner)",
        )
        self.assertEqual(
            paused_lines[16],
            "N16 "
            + self.TOLERANT
            + "(1,13) G103 PA1599 PA1600 PY G105 "
            + self._coord("PY", Y_PULL_IN)
            + " G111 (board gap)",
        )
        self.assertNotIn("G111", base_lines[9])
        self.assertNotIn("G111", base_lines[16])
        self.assertNotIn("G111", paused_lines[5])
        self.assertIn("foot", paused_lines[9].lower())
        self.assertNotIn("foot", paused_lines[16].lower())

    def test_add_foot_pauses_is_reported_in_recipe_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe = write_v_template_file(
                Path(directory) / "V-layer.gc",
                add_foot_pauses=True,
            )

        self.assertTrue(recipe["addFootPauses"])

    def test_xz_script_variant_is_reported_in_recipe_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe = write_v_template_file(
                Path(directory) / "V-layer.gc",
                script_variant="xz",
            )

        self.assertEqual(recipe["scriptVariant"], "xz")


class VTemplateWrappingVariantTests(unittest.TestCase):
    def _coord(self, axis, value):
        return coord(axis, value)

    def test_preamble_and_first_wrap_anchor_to_target(self):
        lines = render_v_template_text_lines(script_variant=SCRIPT_VARIANT_WRAPPING)

        self.assertEqual(
            lines[:7],
            [
                "N0 ( V Layer )",
                "N1 ~goto(440,0)",
                "N2 G206 P3",
                "N3 (1,1) ~anchorToTarget(A2399,B400) (Bottom B corner - head end)",
                "N4 (1,2) ~increment(0,50)",
                "N5 (1,3) ~anchorToTarget(B400,B1999) (Top B corner - foot end)",
                "N6 (1,4) ~anchorToTarget(B1999,A800) (Top A corner - foot end)",
            ],
        )

    def test_no_g_codes_in_wrapping_output(self):
        lines = render_v_template_text_lines(script_variant=SCRIPT_VARIANT_WRAPPING)

        for line in lines:
            self.assertNotIn(" G109 ", " " + line + " ")
            self.assertNotIn(" G103 ", " " + line + " ")
            self.assertNotIn(" G113 ", " " + line + " ")
            self.assertNotIn("transfer", line)

    def test_twelve_anchor_to_targets_per_normal_wrap_and_eleven_for_final(self):
        lines = render_v_template_text_lines(script_variant=SCRIPT_VARIANT_WRAPPING)
        at_count = sum(1 for line in lines if "~anchorToTarget(" in line)
        self.assertEqual(at_count, 12 * (WRAP_COUNT - 1) + 11)

    def test_normal_wrap_emits_pull_in_and_bottom_a_head_end(self):
        lines = render_v_template_text_lines(script_variant=SCRIPT_VARIANT_WRAPPING)
        bodies = [line.split(" ", 2)[-1] for line in lines]
        head_a_idx = bodies.index("~anchorToTarget(B399,A1) (Head A corner)")
        self.assertEqual(
            bodies[head_a_idx + 1],
            "~increment(" + str(int(WRAPPING_X_PULL_IN)) + ",0)",
        )
        self.assertEqual(
            bodies[head_a_idx + 2],
            "~anchorToTarget(A1,A2398) (Bottom A corner - head end)",
        )
        self.assertEqual(
            bodies[head_a_idx + 3],
            "~anchorToTarget(A2398,B401) (Bottom B corner - head end)",
        )

    def test_bottom_a_head_end_offset_renders_with_offset_keyword(self):
        lines = render_v_template_text_lines(
            script_variant=SCRIPT_VARIANT_WRAPPING,
            named_inputs={"line 11 (Bottom A corner - head end)": 2.25},
        )
        self.assertTrue(
            any(
                "~anchorToTarget(A1,A2398,offset=(2.25,0)) (Bottom A corner - head end)"
                in line
                for line in lines
            )
        )

    def test_pull_in_defaults_use_wrapping_values(self):
        self.assertEqual(WRAPPING_Y_PULL_IN, 50.0)
        self.assertEqual(WRAPPING_X_PULL_IN, 70.0)

        lines = render_v_template_text_lines(script_variant=SCRIPT_VARIANT_WRAPPING)
        self.assertIn("N4 (1,2) ~increment(0,50)", lines)
        # −X pull-in between Foot B corner and Bottom B corner - foot end in wrap 1
        self.assertTrue(any("~increment(-70,0)" in line for line in lines))

    def test_named_pull_in_overrides_wrapping_defaults(self):
        lines = render_v_template_text_lines(
            script_variant=SCRIPT_VARIANT_WRAPPING,
            named_inputs={"X_PULL_IN": 100, "Y_PULL_IN": 33},
        )
        self.assertTrue(any("~increment(0,33)" in line for line in lines))
        self.assertTrue(any("~increment(-100,0)" in line for line in lines))
        self.assertFalse(any("~increment(0,50)" in line for line in lines))
        self.assertFalse(any("~increment(-70,0)" in line for line in lines))

    def test_offset_keyword_appears_when_offset_non_zero(self):
        lines = render_v_template_text_lines(
            script_variant=SCRIPT_VARIANT_WRAPPING,
            named_inputs={"line 1 (Top B corner - foot end)": 2.0},
        )
        self.assertIn(
            "N5 (1,3) ~anchorToTarget(B400,B1999,offset=(2,0)) (Top B corner - foot end)",
            lines,
        )

    def test_offset_keyword_appears_for_bottom_b_head_end(self):
        lines = render_v_template_text_lines(
            script_variant=SCRIPT_VARIANT_WRAPPING,
            named_inputs={"line 12 (Bottom B corner - head end)": 1.5},
        )
        self.assertIn(
            "N3 (1,1) ~anchorToTarget(A2399,B400,offset=(1.5,0)) (Bottom B corner - head end)",
            lines,
        )

    def test_offset_keyword_uses_y_axis_for_corner_offsets(self):
        lines = render_v_template_text_lines(
            script_variant=SCRIPT_VARIANT_WRAPPING,
            special_inputs={"foot_a_offset": 3.5},
        )
        # foot_a_offset → offsets[2] → AT 3→4 of wrap 1 = BtoA(1999)→BtoA(1200) = A800→A1599
        self.assertTrue(
            any("~anchorToTarget(A800,A1599,offset=(0,3.5))" in line for line in lines)
        )

    def test_final_wrap_last_anchor_to_target(self):
        lines = render_v_template_text_lines(script_variant=SCRIPT_VARIANT_WRAPPING)
        # wrap 400 deviates after step 8 (Top A corner - head end at A1999→A400) into a
        # custom tail: A400→B2398, increment(0,-y_pull_in), B2398→B1, B1→A399, increment(500,0).
        tail = [line.split(" ", 2)[-1] for line in lines[-5:]]
        self.assertEqual(
            tail,
            [
                "~anchorToTarget(A400,B2398) (Wrap 400 tail A400 to B2398)",
                "~increment(0,-50)",
                "~anchorToTarget(B2398,B1) (Wrap 400 tail B2398 to B1)",
                "~anchorToTarget(B1,A399) (Wrap 400 tail B1 to A399)",
                "~increment(500,0)",
            ],
        )

    def test_iter_primary_sites_returns_empty_for_wrapping(self):
        self.assertEqual(
            iter_v_wrap_primary_sites(script_variant=SCRIPT_VARIANT_WRAPPING),
            (),
        )

    def test_write_v_template_file_supports_wrapping_variant(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe = write_v_template_file(
                Path(directory) / "V-layer.gc",
                script_variant=SCRIPT_VARIANT_WRAPPING,
            )

        self.assertEqual(recipe["scriptVariant"], SCRIPT_VARIANT_WRAPPING)
        self.assertEqual(recipe["pullIns"]["Y_PULL_IN"], WRAPPING_Y_PULL_IN)
        self.assertEqual(recipe["pullIns"]["X_PULL_IN"], WRAPPING_X_PULL_IN)


if __name__ == "__main__":
    unittest.main()
