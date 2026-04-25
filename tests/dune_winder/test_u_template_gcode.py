import tempfile
import unittest
from pathlib import Path

from dune_winder.recipes.u_template_gcode import (
    DEFAULT_U_TEMPLATE_ROW_COUNT,
    SCRIPT_VARIANT_WRAPPING,
    WRAP_COUNT,
    UTemplateProgrammaticGenerator,
    X_PULL_IN,
    Y_PULL_IN,
    get_u_template_named_inputs_snapshot,
    _normalize_pin_tokens,
    render_default_u_template_text_lines,
    render_u_template_text_lines,
    write_u_template_text_file,
    write_u_template_file,
)


class UTemplateGCodeTests(unittest.TestCase):
    MERGE = "G113 PPRECISE "
    TOLERANT = "G113 PTOLERANT "

    def _coord(self, axis, value):
        text = "{0:.6f}".format(float(value)).rstrip("0").rstrip(".")
        if text in ("", "-0"):
            text = "0"
        return axis + text

    def test_pb_pf_tokens_wrap_back_into_valid_pin_range(self):
        self.assertEqual(
            _normalize_pin_tokens("G103 PB2401 PA2402 PB0 PF-1 PF-2 PA1 PBL PRT"),
            "G103 PB2401 PA1 PB2401 PA2400 PA2399 PA1 PBL PRT",
        )

    def test_default_render_matches_expected_spec_edges(self):
        lines = render_u_template_text_lines()

        self.assertEqual(len(lines), DEFAULT_U_TEMPLATE_ROW_COUNT)
        self.assertEqual(
            lines[:6],
            [
                "N0 ( U Layer )",
                "N1 " + self.MERGE + "X7174 Y60 F300 (load new calibration file)",
                "N2 F300 G206 P3",
                "N3 " + self.MERGE + "(0, ) F300 G103 PB1201 PB1200 PXY G105 PX-50",
                "N4 (1,1) (------------------STARTING LOOP 1------------------)",
                "N5 "
                + self.MERGE
                + "(1,2) G109 PB1201 PBR G103 PB2001 PB2002 PXY G102 G108 (Top B corner - foot end)",
            ],
        )

    def test_wrapping_variant_emits_parallel_wrap_commands(self):
        lines = render_u_template_text_lines(script_variant=SCRIPT_VARIANT_WRAPPING)

        self.assertEqual(
            lines[:5],
            [
                "N0 ( U Layer )",
                "N1 ~goto(7174,0)",
                "N2 (1,1) ~anchorToTarget(A1601,B1201) (Foot B corner)",
                "N3 (1,2) ~increment(-200,0)",
                "N4 (1,3) ~anchorToTarget(B1201,B2001) (Top B corner - foot end)",
            ],
        )
        self.assertIn("~anchorToTarget(B2001,A801,hover=True)", lines[5])
        self.assertTrue(lines[-2].endswith("~anchorToTarget(A1201,B1601)"))
        self.assertTrue(lines[-1].endswith("~increment(200,0)"))
        self.assertTrue(all("G103" not in line and "G11" not in line for line in lines))
        self.assertEqual(
            lines[-4:],
            [
                "N7248 (400,17) ~increment(0,200)",
                "N7249 (400,18) ~anchorToTarget(A2001,A1201) (Foot A corner)",
                "N7250 ~anchorToTarget(A1201,B1601)",
                "N7251 ~increment(200,0)",
            ],
        )

    def test_wrapping_variant_includes_offset_keyword_when_offset_is_non_zero(self):
        lines = render_u_template_text_lines(
            script_variant=SCRIPT_VARIANT_WRAPPING,
            named_inputs={"line 1 (Top B corner - foot end)": 2.0},
        )

        self.assertIn(
            "~anchorToTarget(B1201,B2001,offset=(2,0))",
            lines[4],
        )

    def test_wrapping_variant_combines_offset_and_hover_on_alternating_calls(self):
        lines = render_u_template_text_lines(
            script_variant=SCRIPT_VARIANT_WRAPPING,
            named_inputs={"line 2 (Top A corner - foot end)": 2.0},
        )

        self.assertIn(
            "~anchorToTarget(B2001,A801,offset=(2,0),hover=True)",
            lines[5],
        )

    def test_wrapping_variant_includes_foot_b_offset_keyword_when_non_zero(self):
        lines = render_u_template_text_lines(
            script_variant=SCRIPT_VARIANT_WRAPPING,
            named_inputs={"line 12 (Foot B corner)": 3.5},
        )

        self.assertTrue(
            any("~anchorToTarget(A1601,B1201,offset=(0,3.5))" in line for line in lines)
        )

    def test_cached_reader_is_now_the_programmatic_default(self):
        self.assertEqual(
            render_default_u_template_text_lines(),
            render_u_template_text_lines(),
        )

    def test_named_inputs_and_special_aliases_remain_usable(self):
        lines = render_u_template_text_lines(
            named_inputs={
                "line 1 (Top B corner - foot end)": 2,
                "pause at combs": True,
            }
        )
        self.assertEqual(
            lines[5],
            "N5 "
            + self.MERGE
            + "(1,2) G109 PB1201 PBR G103 PB2001 PB2002 PXY G105 PX2 G102 G108 (Top B corner - foot end)",
        )
        self.assertEqual(lines[7], "N7 (1,4) G206 P0")

        special_lines = render_u_template_text_lines(
            special_inputs={"head_a_offset": 7}
        )
        self.assertIn(
            "N15 "
            + self.TOLERANT
            + "(1,12) G109 PB400 PLT G103 PA1 PA2401 PXY G105 PY7 (Head A corner, rewind)",
            special_lines,
        )

    def test_pull_in_overrides_update_generated_motion(self):
        lines = render_u_template_text_lines(
            special_inputs={
                "Y_PULL_IN": 212.5,
                "x_pull_in": 187.5,
            }
        )

        self.assertIn(
            "N8 "
            + self.TOLERANT
            + "(1,5) G103 PA801 PA802 PY G105 "
            + self._coord("PY", -212.5),
            lines,
        )
        self.assertIn(
            "N16 "
            + self.TOLERANT
            + "(1,13) G103 PA2 PA1 PX G105 "
            + self._coord("PX", 187.5),
            lines,
        )

    def test_offset_vector_maps_to_all_twelve_adjustment_sites(self):
        generator = UTemplateProgrammaticGenerator(
            special_inputs={"offsets": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13]}
        )
        lines = generator.render_lines()

        expected_first_wrap = [
            "N5 "
            + self.MERGE
            + "(1,2) G109 PB1201 PBR G103 PB2001 PB2002 PXY G105 PX1 G102 G108 (Top B corner - foot end)",
            "N7 "
            + self.MERGE
            + "(1,4) G109 PB2001 PLT G103 PA801 PA802 PXY G105 PY5 G105 PX2 (Top A corner - foot end)",
            "N9 "
            + self.MERGE
            + "(1,6) G109 PA801 PLB G103 PA2401 PA1 PXY G105 PX3 G102 G108 (Bottom A corner - head end)",
            "N11 "
            + self.MERGE
            + "(1,8) G109 PA2401 PBR G103 PB401 PB402 PXY G105 PY-5 G105 PX4 (Bottom B corner - head end, rewind)",
            "N13 "
            + self.MERGE
            + "(1,10) (HEAD RESTART) G109 PB401 PLT G103 PB400 PB399 PXY G105 PY5 G102 G108 (Head B corner)",
            "N15 "
            + self.TOLERANT
            + "(1,12) G109 PB400 PLT G103 PA1 PA2401 PXY G105 PY6 (Head A corner, rewind)",
            "N17 "
            + self.MERGE
            + "(1,14) G109 PA2 PRT G103 PA799 PA798 PXY G105 PX7 G102 G108 (Top A corner - head end)",
            "N19 "
            + self.MERGE
            + "(1,16) G109 PA799 PRT G103 PB2003 PB2004 PXY G105 PY5 G105 PX8 (Top B corner - head end)",
            "N21 "
            + self.MERGE
            + "(1,18) G109 PB2002 PRB G103 PB1200 PB1201 PXY G105 PX9 G102 G108 (Bottom B corner - foot end)",
            "N23 "
            + self.MERGE
            + "(1,20) G109 PB1200 PBL G103 PA1602 PA1603 PXY G105 PY-5 G105 PX10 (Bottom A corner - foot end, rewind)",
            "N25 "
            + self.MERGE
            + "(1,22) G109 PA1602 PRT G103 PA1600 PA1599 PXY G105 PY11 G102 G108 (Foot A corner)",
            "N27 "
            + self.MERGE
            + "(1,24) G109 PA1600 PRT G103 PB1202 PB1201 PXY G105 PY13 (Foot B corner, rewind)",
        ]
        for expected_line in expected_first_wrap:
            self.assertIn(expected_line, lines)

        self.assertEqual(
            generator.get_value("AC", 16),
            "N15 "
            + self.TOLERANT
            + "(1,12) G109 PB400 PLT G103 PA1 PA2401 PXY G105 PY6 (Head A corner, rewind)",
        )

    def test_transfer_pause_adds_all_optional_pause_lines(self):
        base_lines = render_u_template_text_lines()
        paused_lines = render_u_template_text_lines(
            special_inputs={"transferPause": True}
        )

        self.assertEqual(len(paused_lines) - len(base_lines), WRAP_COUNT * 6)
        self.assertEqual(paused_lines[6], "N6 (1,3) G206 P2")
        self.assertEqual(paused_lines[11], "N11 (1,8) G206 P1")
        self.assertEqual(paused_lines[16], "N16 (1,13) G206 P2")

    def test_named_input_snapshot_and_file_writers(self):
        named_inputs = get_u_template_named_inputs_snapshot()
        self.assertFalse(named_inputs["transferPause"])
        self.assertFalse(named_inputs["addFootPauses"])
        self.assertEqual(named_inputs["line 6 (Head A corner)"], 0.0)
        self.assertEqual(named_inputs["Y_PULL_IN"], Y_PULL_IN)
        self.assertEqual(named_inputs["X_PULL_IN"], X_PULL_IN)

        with tempfile.TemporaryDirectory() as directory:
            plain_output = Path(directory) / "U_template.txt"
            recipe_output = Path(directory) / "U-layer.gc"

            write_u_template_text_file(
                plain_output, special_inputs={"head_a_offset": 7}
            )
            plain_lines = plain_output.read_text(encoding="utf-8").splitlines()
            self.assertIn(
                "N15 "
                + self.TOLERANT
                + "(1,12) G109 PB400 PLT G103 PA1 PA2401 PXY G105 PY7 (Head A corner, rewind)",
                plain_lines,
            )

            recipe = write_u_template_file(
                recipe_output,
                special_inputs={
                    "head_a_offset": 7,
                    "transferPause": True,
                    "Y_PULL_IN": 212.5,
                    "X_PULL_IN": 187.5,
                },
            )
            recipe_lines = recipe_output.read_text(encoding="utf-8").splitlines()

        self.assertTrue(recipe_lines[0].startswith("( U-layer "))
        self.assertEqual(recipe_lines[1], "N0 ( U Layer )")
        self.assertTrue(recipe["transferPause"])
        self.assertEqual(recipe["fileName"], "U-layer.gc")
        self.assertEqual(recipe["pullIns"]["Y_PULL_IN"], 212.5)
        self.assertEqual(recipe["pullIns"]["X_PULL_IN"], 187.5)

    def test_write_u_template_file_supports_wrapping_variant(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe = write_u_template_file(
                Path(directory) / "U-layer.gc",
                script_variant=SCRIPT_VARIANT_WRAPPING,
            )

        self.assertEqual(recipe["scriptVariant"], SCRIPT_VARIANT_WRAPPING)
        self.assertTrue(any(line.endswith("~goto(7174,0)") for line in recipe["lines"]))
        self.assertTrue(any("~anchorToTarget(" in line for line in recipe["lines"]))

    def test_add_foot_pauses_appends_g111_only_on_qualifying_lines(self):
        base_lines = render_u_template_text_lines()
        paused_lines = render_u_template_text_lines(add_foot_pauses=True)

        self.assertEqual(
            paused_lines[3],
            "N3 "
            + self.MERGE
            + "(0, ) F300 G103 PB1201 PB1200 PXY G105 PX-50 G111 (board gap)",
        )
        self.assertEqual(
            paused_lines[21],
            "N21 "
            + self.MERGE
            + "(1,18) G109 PB2002 PRB G103 PB1200 PB1201 PXY G102 G108 G111 (board gap) (Bottom B corner - foot end)",
        )
        self.assertNotIn("G111", base_lines[3])
        self.assertNotIn("G111", base_lines[21])
        self.assertNotIn("G111", paused_lines[5])
        self.assertIn("foot", paused_lines[21].lower())
        self.assertIn(
            "N975 "
            + self.MERGE
            + "(39,22) G109 PA1640 PRT G103 PA1562 PA1561 PXY G102 G108 G111 (board gap) (Foot A corner)",
            paused_lines,
        )
        self.assertIn(
            "N1000 "
            + self.MERGE
            + "(40,22) G109 PA1641 PRT G103 PA1561 PA1560 PXY G102 G108 (Foot A corner)",
            paused_lines,
        )

    def test_add_foot_pauses_shifts_all_u_front_foot_gaps_one_wrap_earlier(self):
        paused_lines = render_u_template_text_lines(add_foot_pauses=True)
        foot_a_gap_lines = [
            line
            for line in paused_lines
            if "(Foot A corner)" in line and "G111 (board gap)" in line
        ]

        expected_pairs = [
            "PA1562 PA1561",
            "PA1522 PA1521",
            "PA1482 PA1481",
            "PA1442 PA1441",
            "PA1402 PA1401",
            "PA1362 PA1361",
            "PA1322 PA1321",
            "PA1282 PA1281",
            "PA1242 PA1241",
            "PA1202 PA1201",
            "PA1201 PA1200",
        ]

        self.assertEqual(len(foot_a_gap_lines), len(expected_pairs))
        for pin_pair in expected_pairs:
            self.assertTrue(
                any(pin_pair in line for line in foot_a_gap_lines),
                msg="Missing shifted Foot A gap pause for " + pin_pair,
            )

        self.assertFalse(
            any(
                "PA1561 PA1560" in line and "G111 (board gap)" in line
                for line in paused_lines
            )
        )
        self.assertFalse(
            any(
                "PA1521 PA1520" in line and "G111 (board gap)" in line
                for line in paused_lines
            )
        )

    def test_add_foot_pauses_is_reported_in_recipe_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe = write_u_template_file(
                Path(directory) / "U-layer.gc",
                add_foot_pauses=True,
            )

        self.assertTrue(recipe["addFootPauses"])


if __name__ == "__main__":
    unittest.main()
