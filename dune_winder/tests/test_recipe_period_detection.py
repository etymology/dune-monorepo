import os
import tempfile
import unittest

from dune_winder.core.Process import Process
from dune_winder.recipes.recipe import Recipe


class FakeAPA:
  def __init__(self, period):
    self._period = period

  def getRecipePeriod(self):
    return self._period


class RecipePeriodDetectionTests(unittest.TestCase):
  def _writeRecipe(self, rootDirectory, fileName, lines):
    recipePath = os.path.join(rootDirectory, fileName)
    with open(recipePath, "w") as recipeFile:
      recipeFile.writelines(lines)
    return recipePath

  def test_detected_period_finds_repeated_body_with_header_and_footer(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      repeatedBody = []
      for index in range(1, 7):
        repeatedBody.extend(
          [
            "G0 X{0}.0 Y{1}.0\n".format(index, index + 10),
            "M98 P{0}\n".format(200 + index),
            "G1 Z-{0}.25 F{1}\n".format(index, 1000 + index),
          ]
        )

      recipePath = self._writeRecipe(
        rootDirectory,
        "periodic.gc",
        [
          "( Synthetic periodic recipe )\n",
          "; header comment 100\n",
        ]
        + repeatedBody
        + [
          "; footer comment 200\n",
          "M2\n",
        ],
      )

      recipe = Recipe(recipePath, None)

      self.assertEqual(recipe.getDetectedPeriod(), 3)

  def test_detected_period_returns_none_when_no_repeating_body_exists(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      recipePath = self._writeRecipe(
        rootDirectory,
        "non_periodic.gc",
        [
          "( Non-periodic recipe )\n",
          "G0 X1 Y2\n",
          "G1 X3 Y4 Z5\n",
          "M3 S1000\n",
          "G4 P0.5\n",
          "M5\n",
          "M2\n",
        ],
      )

      recipe = Recipe(recipePath, None)

      self.assertIsNone(recipe.getDetectedPeriod())

  def test_detected_period_prefers_wrap_start_spacing_when_wrap_comments_exist(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      recipePath = self._writeRecipe(
        rootDirectory,
        "wrap_comments.gc",
        [
          "( Wrap spacing recipe )\n",
          "N0 G0 X0\n",
          "N1 (1, 1) G1 X1\n",
          "N2 (1, 2 HEAD RESTART) G1 X2\n",
          "N3 (1, 3) G1 X3\n",
          "N4 (2, 1) G1 X4\n",
          "N5 (2, 2 HEAD RESTART) G1 X5\n",
          "N6 (2, 3) G1 X6\n",
          "N7 (3, 1) G1 X7\n",
          "N8 (3, 2 HEAD RESTART) G1 X8\n",
          "N9 (3, 3) G1 X9\n",
        ],
      )

      recipe = Recipe(recipePath, None)

      self.assertEqual(recipe.getDetectedPeriod(), 3)

  def test_detected_period_supports_legacy_wrap_comments(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      recipePath = self._writeRecipe(
        rootDirectory,
        "legacy_wraps.gc",
        [
          "( Legacy wrap spacing recipe )\n",
          "N0 (Wrap 1) G1 X1\n",
          "N1 G1 X2\n",
          "N2 G1 X3\n",
          "N3 (Wrap 2) G1 X4\n",
          "N4 G1 X5\n",
          "N5 G1 X6\n",
          "N6 (Wrap 3) G1 X7\n",
          "N7 G1 X8\n",
          "N8 G1 X9\n",
        ],
      )

      recipe = Recipe(recipePath, None)

      self.assertEqual(recipe.getDetectedPeriod(), 3)


class ProcessRecipePeriodTests(unittest.TestCase):
  def test_get_recipe_period_proxies_to_loaded_apa(self):
    process = object.__new__(Process)
    process.apa = FakeAPA(46)

    self.assertEqual(process.getRecipePeriod(), 46)

  def test_get_recipe_period_returns_none_without_loaded_apa(self):
    process = object.__new__(Process)
    process.apa = None

    self.assertIsNone(process.getRecipePeriod())


if __name__ == "__main__":
  unittest.main()
