import tempfile
import unittest
from pathlib import Path

from dune_winder.recipes.u_template_gcode import (
  DEFAULT_U_TEMPLATE_ROW_COUNT,
  WRAP_COUNT,
  UTemplateProgrammaticGenerator,
  get_u_template_named_inputs_snapshot,
  _normalize_pin_tokens,
  render_default_u_template_text_lines,
  render_u_template_text_lines,
  write_u_template_text_file,
  write_u_template_file,
)


class UTemplateGCodeTests(unittest.TestCase):
  def test_pb_pf_tokens_wrap_back_into_valid_pin_range(self):
    self.assertEqual(
      _normalize_pin_tokens("G103 PB2401 PF2402 PB0 PF-1 PF-2 PF1 PBL PRT"),
      "G103 PB2401 PF1 PB2401 PF2400 PF2399 PF1 PBL PRT",
    )

  def test_default_render_matches_expected_spec_edges(self):
    lines = render_u_template_text_lines()

    self.assertEqual(len(lines), DEFAULT_U_TEMPLATE_ROW_COUNT)
    self.assertEqual(
      lines[:6],
      [
        "N0 ( U Layer )",
        "N1 X7174 Y60 F300 (load new calibration file)",
        "N2 F300 G106 P3",
        "N3 (0, ) F300 G103 PB1201 PB1200 PXY G105 PX-50",
        "N4 (1,1) (------------------STARTING LOOP 1------------------)",
        "N5 (1,2) G109 PB1201 PBR G103 PB2001 PB2002 PXY G102 G108 (Top B corner - foot end)",
      ],
    )
    self.assertEqual(
      lines[-4:],
      [
        "N10077 (400,22) G109 PF2001 PRT G103 PF1201 PF1200 PXY G102 G108 (Foot A corner)",
        "N10078 (400,23) G106 P3",
        "N10079 (400,24) G109 PF1201 PRT G103 PB1601 PB1600 PXY (Foot B corner, rewind)",
        "N10080 (400,25) G103 PB1601 PB1600 PX G105 PX-70",
      ],
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
      "N5 (1,2) G109 PB1201 PBR G103 PB2001 PB2002 PXY G105 PX2 G102 G108 (Top B corner - foot end)",
    )
    self.assertEqual(lines[7], "N7 (1,4) G106 P0")

    special_lines = render_u_template_text_lines(special_inputs={"head_a_offset": 7})
    self.assertIn(
      "N15 (1,12) G109 PB400 PLT G103 PF1 PF2401 PXY G105 PY7 (Head A corner, rewind)",
      special_lines,
    )

  def test_offset_vector_maps_to_all_twelve_adjustment_sites(self):
    generator = UTemplateProgrammaticGenerator(
      special_inputs={"offsets": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13]}
    )
    lines = generator.render_lines()

    expected_first_wrap = [
      "N5 (1,2) G109 PB1201 PBR G103 PB2001 PB2002 PXY G105 PX1 G102 G108 (Top B corner - foot end)",
      "N7 (1,4) G109 PB1201 PLT G103 PB2001 PB2002 PXY G105 PX14 (Top A corner - foot end)",
      "N9 (1,6) G109 PF801 PLB G103 PF2401 PF1 PXY G105 PY3 G102 G108 (Bottom A corner - head end)",
      "N11 (1,8) G109 PF2401 PBR G103 PB401 PB402 PXY G105 PY4 (Bottom B corner - head end, rewind)",
      "N13 (1,10) (HEAD RESTART) G109 PB401 PLT G103 PB400 PB399 PXY G105 PY5 G102 G108 (Head B corner)",
      "N15 (1,12) G109 PB400 PLT G103 PF1 PF2401 PXY G105 PY6 (Head A corner, rewind)",
      "N17 (1,14) G109 PF2 PRT G103 PF799 PF798 PXY G105 PX7 G102 G108 (Top A corner - head end)",
      "N19 (1,16) G109 PF799 PRT G103 PB2003 PB2004 PXY G105 PX-4 (Top B corner - head end)",
      "N21 (1,18) G109 PB2002 PRB G103 PB1200 PB1201 PXY G105 PY9 G102 G108 (Bottom B corner - foot end)",
      "N23 (1,20) G109 PB1200 PBL G103 PF1602 PF1603 PXY G105 PY10 (Bottom A corner - foot end, rewind)",
      "N25 (1,22) G109 PF1602 PRT G103 PF1600 PF1599 PXY G105 PY11 G102 G108 (Foot A corner)",
      "N27 (1,24) G109 PF1600 PRT G103 PB1202 PB1201 PXY G105 PY13 (Foot B corner, rewind)",
    ]
    for expected_line in expected_first_wrap:
      self.assertIn(expected_line, lines)

    self.assertEqual(
      generator.get_value("AC", 16),
      "N15 (1,12) G109 PB400 PLT G103 PF1 PF2401 PXY G105 PY6 (Head A corner, rewind)",
    )

  def test_transfer_pause_adds_all_optional_pause_lines(self):
    base_lines = render_u_template_text_lines()
    paused_lines = render_u_template_text_lines(special_inputs={"transferPause": True})

    self.assertEqual(len(paused_lines) - len(base_lines), WRAP_COUNT * 6)
    self.assertEqual(paused_lines[6], "N6 (1,3) G106 P2")
    self.assertEqual(paused_lines[11], "N11 (1,8) G106 P1")
    self.assertEqual(paused_lines[16], "N16 (1,13) G106 P2")

  def test_named_input_snapshot_and_file_writers(self):
    named_inputs = get_u_template_named_inputs_snapshot()
    self.assertFalse(named_inputs["transferPause"])
    self.assertEqual(named_inputs["line 6 (Head A corner)"], 0.0)

    with tempfile.TemporaryDirectory() as directory:
      plain_output = Path(directory) / "U_template.txt"
      recipe_output = Path(directory) / "U-layer.gc"

      write_u_template_text_file(plain_output, special_inputs={"head_a_offset": 7})
      plain_lines = plain_output.read_text(encoding="utf-8").splitlines()
      self.assertIn(
        "N15 (1,12) G109 PB400 PLT G103 PF1 PF2401 PXY G105 PY7 (Head A corner, rewind)",
        plain_lines,
      )

      recipe = write_u_template_file(
        recipe_output,
        special_inputs={"head_a_offset": 7, "transferPause": True},
      )
      recipe_lines = recipe_output.read_text(encoding="utf-8").splitlines()

    self.assertTrue(recipe_lines[0].startswith("( U-layer "))
    self.assertEqual(recipe_lines[1], "N0 ( U Layer )")
    self.assertTrue(recipe["transferPause"])
    self.assertEqual(recipe["fileName"], "U-layer.gc")


if __name__ == "__main__":
  unittest.main()
