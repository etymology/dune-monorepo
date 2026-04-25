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
        self._workspaceCalibrationDirectory = os.path.join(
            rootDirectory, "config", "APA"
        )
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
        self.workspace = FakeWorkspace(
            layer, workspacePath, recipeDirectory, recipeArchiveDirectory
        )

    def getRecipeLayer(self):
        return self.workspace.getLayer()


def _build_configuration(rootDirectory):
    import pathlib

    configuration = AppConfig.load(pathlib.Path(rootDirectory) / "configuration.toml")
    configuration.save()
    return configuration


class TemplateRecipePersistenceTests(unittest.TestCase):
    def test_v_recipe_generation_is_allowed_while_machine_is_busy(self):
        with tempfile.TemporaryDirectory() as rootDirectory:
            process = FakeProcess("V", rootDirectory)
            process.controlStateMachine = FakeControlStateMachine(False)
            service = VTemplateRecipe(process)

            result = service.generateRecipeFile()

            self.assertTrue(result["ok"])
            self.assertTrue(
                os.path.isfile(
                    os.path.join(process.workspace._recipeDirectory, "V-layer.gc")
                )
            )

    def test_v_recipe_generation_supports_xz_script_variant(self):
        with tempfile.TemporaryDirectory() as rootDirectory:
            process = FakeProcess("V", rootDirectory)
            service = VTemplateRecipe(process)

            result = service.generateRecipeFile(scriptVariant="xz")

            self.assertTrue(result["ok"])
            recipePath = os.path.join(process.workspace._recipeDirectory, "V-layer.gc")
            self.assertTrue(os.path.isfile(recipePath))
            with open(recipePath, encoding="utf-8") as handle:
                recipeText = handle.read()
            self.assertIn("PXZ", recipeText)

    def test_u_recipe_generation_is_allowed_while_machine_is_busy(self):
        with tempfile.TemporaryDirectory() as rootDirectory:
            process = FakeProcess("U", rootDirectory)
            process.controlStateMachine = FakeControlStateMachine(False)
            service = UTemplateRecipe(process)

            result = service.generateRecipeFile()

            self.assertTrue(result["ok"])
            self.assertTrue(
                os.path.isfile(
                    os.path.join(process.workspace._recipeDirectory, "U-layer.gc")
                )
            )

    def test_u_recipe_generation_supports_wrapping_script_variant(self):
        with tempfile.TemporaryDirectory() as rootDirectory:
            process = FakeProcess("U", rootDirectory)
            service = UTemplateRecipe(process)

            result = service.generateRecipeFile(scriptVariant="wrapping")

            self.assertTrue(result["ok"])
            recipePath = os.path.join(process.workspace._recipeDirectory, "U-layer.gc")
            self.assertTrue(os.path.isfile(recipePath))
            with open(recipePath, encoding="utf-8") as handle:
                recipeText = handle.read()
            self.assertIn("~goto(7174,0)", recipeText)
            self.assertIn("~anchorToTarget(B2001,A801,hover=True)", recipeText)
            self.assertNotIn("~increment(0,5)", recipeText)

    def test_u_recipe_generation_applies_line_offset_overrides_to_wrapping_output(self):
        with tempfile.TemporaryDirectory() as rootDirectory:
            process = FakeProcess("U", rootDirectory)
            service = UTemplateRecipe(process)

            result = service.setLineOffsetOverride("(1,1)", 1.25, -2.5)
            self.assertTrue(result["ok"])
            result = service.generateRecipeFile(scriptVariant="wrapping")

            self.assertTrue(result["ok"])
            recipePath = os.path.join(process.workspace._recipeDirectory, "U-layer.gc")
            with open(recipePath, encoding="utf-8") as handle:
                recipeText = handle.read()
            self.assertIn("offset=(1.25,-2.5)", recipeText)

    def test_v_recipe_generation_applies_line_offset_overrides_to_raw_output(self):
        with tempfile.TemporaryDirectory() as rootDirectory:
            process = FakeProcess("V", rootDirectory)
            service = VTemplateRecipe(process)

            result = service.setLineOffsetOverride("(1,1)", 1.25, -2.5)
            self.assertTrue(result["ok"])
            result = service.generateRecipeFile()

            self.assertTrue(result["ok"])
            recipePath = os.path.join(process.workspace._recipeDirectory, "V-layer.gc")
            with open(recipePath, encoding="utf-8") as handle:
                recipeText = handle.read()
            self.assertIn("G105 PX1.25 G105 PY-2.5", recipeText)

    def test_u_recipe_draft_persists_after_service_restart(self):
        with tempfile.TemporaryDirectory() as rootDirectory:
            process = FakeProcess("U", rootDirectory)
            service = UTemplateRecipe(process)

            result = service.setOffset("head_a_corner", 1.25)
            self.assertTrue(result["ok"])
            result = service.setTransferPause(False)
            self.assertTrue(result["ok"])
            result = service.setAddFootPauses(True)
            self.assertTrue(result["ok"])
            result = service.setPullIn("Y_PULL_IN", 212.5)
            self.assertTrue(result["ok"])
            result = service.setPullIn("X_PULL_IN", 187.5)
            self.assertTrue(result["ok"])
            result = service.setPullIn("Y_HOVER", 0.0)
            self.assertTrue(result["ok"])

            draftPath = os.path.join(
                process.workspace.getPath(), "TemplateRecipe", "U_Draft.json"
            )
            self.assertTrue(os.path.isfile(draftPath))

            restarted = UTemplateRecipe(process)
            state = restarted.getState()
            self.assertAlmostEqual(state["offsets"]["head_a_corner"], 1.25, places=6)
            self.assertFalse(state["transferPause"])
            self.assertTrue(state["addFootPauses"])
            self.assertAlmostEqual(state["pullIns"]["Y_PULL_IN"], 212.5, places=6)
            self.assertAlmostEqual(state["pullIns"]["X_PULL_IN"], 187.5, places=6)
            self.assertAlmostEqual(state["pullIns"]["Y_HOVER"], 0.0, places=6)
            self.assertTrue(state["dirty"])

    def test_v_recipe_draft_persists_after_service_restart(self):
        with tempfile.TemporaryDirectory() as rootDirectory:
            process = FakeProcess("V", rootDirectory)
            service = VTemplateRecipe(process)

            result = service.setOffset("head_a_corner", -2.5)
            self.assertTrue(result["ok"])
            result = service.setTransferPause(False)
            self.assertTrue(result["ok"])
            result = service.setAddFootPauses(True)
            self.assertTrue(result["ok"])
            result = service.setPullIn("Y_PULL_IN", 82.5)
            self.assertTrue(result["ok"])
            result = service.setPullIn("X_PULL_IN", 91.5)
            self.assertTrue(result["ok"])

            draftPath = os.path.join(
                process.workspace.getPath(), "TemplateRecipe", "V_Draft.json"
            )
            self.assertTrue(os.path.isfile(draftPath))

            restarted = VTemplateRecipe(process)
            state = restarted.getState()
            self.assertAlmostEqual(state["offsets"]["head_a_corner"], -2.5, places=6)
            self.assertFalse(state["transferPause"])
            self.assertTrue(state["addFootPauses"])
            self.assertAlmostEqual(state["pullIns"]["Y_PULL_IN"], 82.5, places=6)
            self.assertAlmostEqual(state["pullIns"]["X_PULL_IN"], 91.5, places=6)
            self.assertTrue(state["dirty"])

    def test_u_recipe_draft_persists_line_offset_overrides_and_last_variant(self):
        with tempfile.TemporaryDirectory() as rootDirectory:
            process = FakeProcess("U", rootDirectory)
            service = UTemplateRecipe(process)

            self.assertTrue(service.setLineOffsetOverride("(4,2)", 0.75, -1.5)["ok"])
            self.assertTrue(service.generateRecipeFile(scriptVariant="wrapping")["ok"])

            restarted = UTemplateRecipe(process)
            state = restarted.getState()
            self.assertEqual(state["lastGeneratedScriptVariant"], "wrapping")
            self.assertEqual(list(state["lineOffsetOverrides"].keys()), ["(4,2)"])
            self.assertAlmostEqual(
                state["lineOffsetOverrides"]["(4,2)"]["x"], 0.75, places=6
            )
            self.assertAlmostEqual(
                state["lineOffsetOverrides"]["(4,2)"]["y"], -1.5, places=6
            )

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
            self.assertAlmostEqual(
                reloadedV["offsets"]["head_a_corner"], -4.0, places=6
            )


if __name__ == "__main__":
    unittest.main()
