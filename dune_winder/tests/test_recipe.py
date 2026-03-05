import os
import re
import tempfile
import unittest

from dune_winder.library.hash import Hash
from dune_winder.recipes.recipe import Recipe


class RecipeTests(unittest.TestCase):
  def test_missing_heading_uses_filename_and_preserves_gcode(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      recipePath = os.path.join(rootDirectory, "sample-recipe.gc")
      originalLines = ["G0 X1 Y2\n", "M2\n"]

      with open(recipePath, "w") as recipeFile:
        recipeFile.writelines(originalLines)

      recipe = Recipe(recipePath, None)

      self.assertEqual(recipe.getDescription(), "sample-recipe")
      self.assertEqual(recipe.getLines(), originalLines)
      self.assertRegex(recipe.getID(), "^" + Hash.HASH_PATTERN + "$")

      with open(recipePath) as recipeFile:
        rewrittenLines = recipeFile.readlines()

      self.assertRegex(
        rewrittenLines[0],
        r"^\( sample-recipe " + Hash.HASH_PATTERN + r" \)\n$",
      )
      self.assertEqual(rewrittenLines[1:], originalLines)

  def test_write_generated_file_writes_hash_header_and_round_trips_without_mutation(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      recipePath = os.path.join(rootDirectory, "X-layer.gc")
      archivePath = os.path.join(rootDirectory, "archive")
      bodyLines = ["X440 Y100", "G106 P0\n", "X635 Y200"]

      hashValue = Recipe.writeGeneratedFile(
        recipePath,
        "X-layer",
        bodyLines,
        archiveDirectory=archivePath,
      )

      with open(recipePath) as recipeFile:
        savedLines = recipeFile.readlines()

      self.assertRegex(savedLines[0], r"^\( X-layer " + Hash.HASH_PATTERN + r" \)\n$")
      self.assertEqual(savedLines[1:], ["X440 Y100\n", "G106 P0\n", "X635 Y200\n"])
      self.assertTrue(os.path.isfile(os.path.join(archivePath, hashValue)))

      recipe = Recipe(recipePath, archivePath)

      with open(recipePath) as recipeFile:
        reloadedLines = recipeFile.readlines()

      self.assertEqual(recipe.getDescription(), "X-layer")
      self.assertEqual(recipe.getID(), hashValue)
      self.assertEqual(recipe.getLines(), savedLines[1:])
      self.assertEqual(reloadedLines, savedLines)
