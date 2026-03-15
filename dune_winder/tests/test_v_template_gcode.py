import tempfile
import unittest
from pathlib import Path

from dune_winder.recipes.v_template_gcode import (
  DEFAULT_V_TEMPLATE_ROW_COUNT,
  PRE_FINAL_WRAP_COUNT,
  VTemplateProgrammaticGenerator,
  get_v_template_named_inputs_snapshot,
  _normalize_pin_tokens,
  render_default_v_template_text_lines,
  render_v_template_text_lines,
  write_v_template_text_file,
  write_v_template_file,
)


class VTemplateGCodeTests(unittest.TestCase):
  MERGE = "G113 PPRECISE "

  def test_pb_pf_tokens_wrap_back_into_valid_pin_range(self):
    self.assertEqual(
      _normalize_pin_tokens("G103 PB2401 PF2402 PB0 PF-1 PF1 PBL PRT"),
      "G103 PB1 PF2 PB2400 PF2400 PF1 PBL PRT",
    )

  def test_default_render_matches_expected_spec_edges(self):
    lines = render_v_template_text_lines()

    self.assertEqual(len(lines), DEFAULT_V_TEMPLATE_ROW_COUNT)
    self.assertEqual(
      lines[:5],
      [
        "N0 ( V Layer )",
        "N1 " + self.MERGE + "(HEAD RESTART) X440 Y0",
        "N2 G106 P3",
        "N3 " + self.MERGE + "(0, ) F1000 G103 PB400 PB399 PXY G105 PY30 ( BOARD GAP )",
        "N4 (1,1) (------------------STARTING LOOP 1------------------)",
      ],
    )
    tail_start = len(lines) - 8
    self.assertEqual(
      lines[-8:],
      [
        "N" + str(tail_start) + " " + self.MERGE + "(400,16) G109 PF400 PRT G103 PB2398 PB2399 PX (Top B corner - head end)",
        "N" + str(tail_start + 1) + " " + self.MERGE + "(400,17) G103 PB2398 PB2399 PY G105 PY-60",
        "N" + str(tail_start + 2) + " " + self.MERGE + "(400,18) G103 PB2398 PB2399 PY G105 PY0 G111",
        "N" + str(tail_start + 3) + " " + self.MERGE + "(400,19) X440 Y2315 F300",
        "N" + str(tail_start + 4) + " (400,20) G106 P0",
        "N" + str(tail_start + 5) + " " + self.MERGE + "(400,21) X440 Y2335",
        "N" + str(tail_start + 6) + " " + self.MERGE + "(400,22) X650 Y2335 G111",
        "N" + str(tail_start + 7) + " " + self.MERGE + "(400,23) X440 Y2335",
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
      "N5 " + self.MERGE + "(1,2) G109 PB400 PRT G103 PB1998 PB1999 PXY G105 PX2 G102 G108 (Top B corner - foot end)",
    )
    self.assertEqual(lines[7], "N7 (1,4) G106 P0")

    special_lines = render_v_template_text_lines(special_inputs={"head_a_offset": 7})
    self.assertIn(
      "N23 " + self.MERGE + "(1,20) G109 PB399 PBR G103 PF1 PF2 PY G105 PY7 (Head A corner)",
      special_lines,
    )

  def test_offset_vector_maps_to_all_twelve_adjustment_sites(self):
    generator = VTemplateProgrammaticGenerator(
      special_inputs={"offsets": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13]}
    )
    lines = generator.render_lines()

    expected_first_wrap = [
      "N5 " + self.MERGE + "(1,2) G109 PB400 PRT G103 PB1998 PB1999 PXY G105 PX1 G102 G108 (Top B corner - foot end)",
      "N7 " + self.MERGE + "(1,4) G109 PB1999 PLT G103 PF800 PF799 PX G105 PX2 (Top A corner - foot end)",
      "N9 " + self.MERGE + "(1,6) G109 PF800 PRB G103 PF1600 PF1599 PXY G105 PY3 G102 G108 ( BOARD GAP ) (Foot A corner)",
      "N11 " + self.MERGE + "(1,8) G109 PF1599 PBL G103 PB1200 PB1201 PY G105 PY4 (Foot B corner)",
      "N13 " + self.MERGE + "(1,10) G109 PB1200 PTR G103 PB1199 PB1198 PXY G105 PX5 G102 G108 (Bottom B corner - foot end)",
      "N15 " + self.MERGE + "(1,12) G109 PB1199 PBR G103 PF1599 PF1600 PX G105 PX6 (Bottom A corner - foot end)",
      "N17 " + self.MERGE + "(1,14) G109 PF1600 PLT G103 PF799 PF798 PXY G105 PX7 G102 G108 (Top A corner - head end)",
      "N19 " + self.MERGE + "(1,16) G109 PF799 PRT G103 PB1999 PB2000 PX G105 PX8 (Top B corner - head end)",
      "N21 " + self.MERGE + "(1,18) (HEAD RESTART) G109 PB2000 PLB G103 PB400 PB399 PXY G105 PY9 G102 G108 ( BOARD GAP )",
      "N23 " + self.MERGE + "(1,20) G109 PB399 PBR G103 PF1 PF2 PY G105 PY10 (Head A corner)",
      "N25 " + self.MERGE + "(1,22) G109 PF1 PTL G103 PF2398 PF2397 PXY G105 PX11 G102 G108 (Bottom A corner - head end)",
      "N27 " + self.MERGE + "(1,24) G109 PF2398 PBL G103 PB400 PB401 G105 PX13 PX12 (Bottom B corner - head end)",
    ]
    for expected_line in expected_first_wrap:
      self.assertIn(expected_line, lines)

    self.assertEqual(
      generator.get_value("AC", 24),
      "N23 " + self.MERGE + "(1,20) G109 PB399 PBR G103 PF1 PF2 PY G105 PY10 (Head A corner)",
    )

  def test_transfer_pause_adds_all_optional_pause_lines(self):
    base_lines = render_v_template_text_lines()
    paused_lines = render_v_template_text_lines(special_inputs={"transferPause": True})

    self.assertEqual(len(paused_lines) - len(base_lines), PRE_FINAL_WRAP_COUNT * 6 + 4)
    self.assertEqual(paused_lines[6], "N6 (1,3) G106 P2")
    self.assertEqual(paused_lines[11], "N11 (1,8) G106 P1")
    self.assertEqual(paused_lines[16], "N16 (1,13) G106 P2")

  def test_named_input_snapshot_and_file_writers(self):
    named_inputs = get_v_template_named_inputs_snapshot()
    self.assertFalse(named_inputs["transferPause"])
    self.assertEqual(named_inputs["line 10 (Head A corner)"], 0.0)

    with tempfile.TemporaryDirectory() as directory:
      plain_output = Path(directory) / "V_template.txt"
      recipe_output = Path(directory) / "V-layer.gc"

      write_v_template_text_file(plain_output, special_inputs={"head_a_offset": 7})
      plain_lines = plain_output.read_text(encoding="utf-8").splitlines()
      self.assertIn(
        "N23 " + self.MERGE + "(1,20) G109 PB399 PBR G103 PF1 PF2 PY G105 PY7 (Head A corner)",
        plain_lines,
      )

      recipe = write_v_template_file(
        recipe_output,
        special_inputs={"head_a_offset": 7, "transferPause": True},
      )
      recipe_lines = recipe_output.read_text(encoding="utf-8").splitlines()

    self.assertTrue(recipe_lines[0].startswith("( V-layer "))
    self.assertEqual(recipe_lines[1], "N0 ( V Layer )")
    self.assertTrue(recipe["transferPause"])
    self.assertEqual(recipe["fileName"], "V-layer.gc")


if __name__ == "__main__":
  unittest.main()
