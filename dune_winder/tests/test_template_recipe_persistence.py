import os
import tempfile
import unittest

from dune_winder.recipes.u_template_recipe import UTemplateRecipe
from dune_winder.recipes.v_template_recipe import VTemplateRecipe
from dune_winder.library.app_config import AppConfig
from dune_winder.machine.settings import Settings


class FakeLog:
  def __init__(self):
    self.entries = []

  def add(self, *args):
    self.entries.append(args)


class FakeTimeSource:
  def __init__(self):
    self.value = 0

  def get(self):
    self.value += 1
    return self.value


class FakeControlStateMachine:
  def __init__(self, ready=True):
    self.ready = ready

  def isReadyForMovement(self):
    return self.ready


class FakeWorkspace:
  def __init__(self, layer, path, recipeDirectory, recipeArchiveDirectory):
    self._layer = layer
    self._path = path
    self._recipeDirectory = recipeDirectory
    self._recipeArchiveDirectory = recipeArchiveDirectory
    self._recipeFile = None

  def getLayer(self):
    return self._layer

  def getPath(self):
    return self._path


class FakeProcess:
  def __init__(self, layer, rootDirectory):
    self._configuration = _build_configuration(rootDirectory)
    self._workspaceCalibrationDirectory = os.path.join(rootDirectory, "config", "APA")
    self._systemTime = FakeTimeSource()
    self._log = FakeLog()
    self.controlStateMachine = FakeControlStateMachine(True)

    recipeDirectory = os.path.join(rootDirectory, "gc_files")
    recipeArchiveDirectory = os.path.join(rootDirectory, "cache", "Recipes")
    workspacePath = os.path.join(rootDirectory, "cache", "APA")
    os.makedirs(self._workspaceCalibrationDirectory, exist_ok=True)
    os.makedirs(recipeDirectory, exist_ok=True)
    os.makedirs(recipeArchiveDirectory, exist_ok=True)
    os.makedirs(workspacePath, exist_ok=True)
    self.workspace = FakeWorkspace(layer, workspacePath, recipeDirectory, recipeArchiveDirectory)

  def getRecipeLayer(self):
    return self.workspace.getLayer()


def _build_configuration(rootDirectory):
  import pathlib
  configuration = AppConfig.load(pathlib.Path(rootDirectory) / "configuration.toml")
  configuration.save()
  return configuration


class TemplateRecipePersistenceTests(unittest.TestCase):
  def test_u_recipe_draft_persists_after_service_restart(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      process = FakeProcess("U", rootDirectory)
      service = UTemplateRecipe(process)

      result = service.setOffset("head_a_corner", 1.25)
      self.assertTrue(result["ok"])
      result = service.setTransferPause(False)
      self.assertTrue(result["ok"])
      result = service.setPullIn("Y_PULL_IN", 212.5)
      self.assertTrue(result["ok"])
      result = service.setPullIn("X_PULL_IN", 187.5)
      self.assertTrue(result["ok"])

      draftPath = os.path.join(process.workspace.getPath(), "TemplateRecipe", "U_Draft.json")
      self.assertTrue(os.path.isfile(draftPath))

      restarted = UTemplateRecipe(process)
      state = restarted.getState()
      self.assertAlmostEqual(state["offsets"]["head_a_corner"], 1.25, places=6)
      self.assertFalse(state["transferPause"])
      self.assertAlmostEqual(state["pullIns"]["Y_PULL_IN"], 212.5, places=6)
      self.assertAlmostEqual(state["pullIns"]["X_PULL_IN"], 187.5, places=6)
      self.assertTrue(state["dirty"])

  def test_v_recipe_draft_persists_after_service_restart(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      process = FakeProcess("V", rootDirectory)
      service = VTemplateRecipe(process)

      result = service.setOffset("head_a_corner", -2.5)
      self.assertTrue(result["ok"])
      result = service.setTransferPause(False)
      self.assertTrue(result["ok"])

      draftPath = os.path.join(process.workspace.getPath(), "TemplateRecipe", "V_Draft.json")
      self.assertTrue(os.path.isfile(draftPath))

      restarted = VTemplateRecipe(process)
      state = restarted.getState()
      self.assertAlmostEqual(state["offsets"]["head_a_corner"], -2.5, places=6)
      self.assertFalse(state["transferPause"])
      self.assertTrue(state["dirty"])

  def test_u_and_v_drafts_use_separate_files(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      uProcess = FakeProcess("U", rootDirectory)
      vProcess = FakeProcess("V", rootDirectory)
      uService = UTemplateRecipe(uProcess)
      vService = VTemplateRecipe(vProcess)

      self.assertTrue(uService.setOffset("head_a_corner", 3.0)["ok"])
      self.assertTrue(vService.setOffset("head_a_corner", -4.0)["ok"])

      reloadedU = UTemplateRecipe(uProcess).getState()
      reloadedV = VTemplateRecipe(vProcess).getState()
      self.assertAlmostEqual(reloadedU["offsets"]["head_a_corner"], 3.0, places=6)
      self.assertAlmostEqual(reloadedV["offsets"]["head_a_corner"], -4.0, places=6)


if __name__ == "__main__":
  unittest.main()
