import os
import tempfile
import unittest

from dune_winder.recipes.recipe import Recipe
from dune_winder.recipes.xg_template_gcode import (
  WIRE_SPACING,
  render_xg_template_lines,
  write_xg_template_file,
)


class XGTemplateGCodeTests(unittest.TestCase):
  def _special_inputs(self, transferPause=False):
    return {
      "references": {
        "head": {
          "wireX": 100.0,
          "wireY": 200.0,
        },
        "foot": {
          "wireX": 300.0,
          "wireY": 400.0,
        },
      },
      "offsets": {
        "headA": 1.5,
        "headB": 2.5,
        "footA": -0.5,
        "footB": -1.5,
      },
      "transferPause": transferPause,
    }

  def test_render_x_layer_matches_programmatic_description(self):
    lines = render_xg_template_lines("X", self._special_inputs())

    self.assertEqual(lines[0], "N0 X440.0 Y201.5\n")
    self.assertEqual(lines[1], "N1 G106 P0\n")
    self.assertEqual(lines[2], "N2 (1,1) X635.0 Y201.5\n")
    self.assertEqual(lines[3], "N3 (1,2) X7165.0 Y399.5\n")
    self.assertEqual(lines[4], "N4 (1,3) G106 P0\n")
    self.assertEqual(lines[5], "N5 (1,4) G106 P3\n")
    self.assertEqual(lines[6], "N6 (1,5) X7016.0 Y398.5\n")
    self.assertEqual(lines[7], "N7 (1,6 HEAD RESTART) X440.0 Y202.5\n")
    self.assertEqual(lines[8], "N8 (1,7) G106 P3\n")
    self.assertEqual(lines[9], "N9 (1,8) G106 P0\n")
    self.assertEqual(lines[10], "N10 (2,1) X635.0 Y209.3\n")
    self.assertEqual(lines[-1], "N3842 X635.0 Y2501.5\n")
    self.assertEqual(len(lines), 3843)

  def test_render_g_layer_uses_481_wraps_and_optional_transfer_pause(self):
    lines = render_xg_template_lines("G", self._special_inputs(transferPause=True))

    self.assertEqual(lines[0], "N0 X440.0 Y201.5\n")
    self.assertEqual(lines[1], "N1 G106 P0\n")
    self.assertEqual(lines[2], "N2 (1,1) X635.0 Y201.5\n")
    self.assertEqual(lines[6], "N6 (1,5) G106 P3\n")
    self.assertEqual(lines[7], "N7 (1,6) X7016.0 Y398.5\n")
    self.assertEqual(lines[10], "N10 (1,9) G106 P2\n")
    self.assertEqual(lines[11], "N11 (1,10) G106 P0\n")
    self.assertEqual(lines[-2], "N4811 (481,10) G106 P0\n")
    self.assertEqual(lines[-1], "N4812 X635.0 Y2501.5\n")
    self.assertEqual(len(lines), 4813)

  def test_write_xg_template_file_writes_recipe_header_and_body(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      outputPath = os.path.join(rootDirectory, "X-layer.gc")

      result = write_xg_template_file("X", outputPath, specialInputs=self._special_inputs())

      recipe = Recipe(outputPath, None)

      self.assertEqual(result["description"], "X-layer")
      self.assertEqual(result["wrapCount"], 480)
      self.assertEqual(result["wireSpacing"], WIRE_SPACING)
      self.assertEqual(recipe.getDescription(), "X-layer")
      self.assertEqual(recipe.getID(), result["hashValue"])
      self.assertEqual(recipe.getLines()[0], "N0 X440.0 Y201.5\n")
      self.assertEqual(recipe.getLines()[1], "N1 G106 P0\n")
      self.assertEqual(recipe.getLines()[2], "N2 (1,1) X635.0 Y201.5\n")

  def test_write_xg_template_file_accepts_snake_case_aliases(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      outputPath = os.path.join(rootDirectory, "G-layer.gc")
      archiveDirectory = os.path.join(rootDirectory, "Archive")

      result = write_xg_template_file(
        "G",
        output_path=outputPath,
        special_inputs=self._special_inputs(transferPause=True),
        archive_directory=archiveDirectory,
      )

      recipe = Recipe(outputPath, None)
      self.assertEqual(result["description"], "G-layer")
      self.assertEqual(recipe.getDescription(), "G-layer")
      self.assertEqual(recipe.getID(), result["hashValue"])


if __name__ == "__main__":
  unittest.main()
