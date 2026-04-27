###############################################################################
# Name: recipe_service.py
# Uses: Recipe/workspace/editor helpers extracted from Process.
###############################################################################

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import TYPE_CHECKING, Callable, Optional

from dune_winder.core.winder_workspace import WinderWorkspace
from dune_winder.machine.settings import Settings

if TYPE_CHECKING:
    from dune_winder.gcode.handler import GCodeHandler
    from dune_winder.library.log import Log
    from dune_winder.library.time_source import TimeSource


class RecipeService:
    """Owns workspace lifecycle plus recipe/calibration file helpers."""

    def __init__(
        self,
        workspaceGetter: Callable[[], Optional[WinderWorkspace]],
        workspaceSetter: Callable[[Optional[WinderWorkspace]], None],
        workspaceDirectory: str,
        workspaceCalibrationDirectory: str,
        gCodeHandler: Optional[GCodeHandler] = None,
        log: Optional[Log] = None,
        systemTime: Optional[TimeSource] = None,
        controlStateMachine=None,
        resetWindTime: Optional[Callable[[], None]] = None,
        getWindTime: Optional[Callable[[], float]] = None,
    ):
        self._workspaceGetter = workspaceGetter
        self._workspaceSetter = workspaceSetter
        self._workspaceDirectory = workspaceDirectory
        self._workspaceCalibrationDirectory = workspaceCalibrationDirectory
        self._gCodeHandler = gCodeHandler
        self._log = log
        self._systemTime = systemTime
        self._controlStateMachine = controlStateMachine
        self._resetWindTime = resetWindTime
        self._getWindTime = getWindTime

    def getRecipes(self):
        recipeList = os.listdir(Settings.RECIPE_DIR)
        expression = re.compile(r"\.gc$")
        return [index for index in recipeList if expression.search(index)]

    def getRecipeName(self):
        workspace = self._workspaceGetter()
        if workspace:
            return workspace.getRecipe()
        return ""

    def getRecipeLayer(self):
        workspace = self._workspaceGetter()
        if workspace:
            return workspace.getLayer()
        return None

    def getRecipePeriod(self):
        workspace = self._workspaceGetter()
        if workspace:
            return workspace.getRecipePeriod()
        return None

    def getWrapSeekLine(self, wrap):
        workspace = self._workspaceGetter()
        if workspace:
            return workspace.getWrapSeekLine(wrap)
        return None

    def _openInEditor(self, filePath):
        try:
            editor = os.environ.get("WINDER_TEXT_EDITOR")
            if editor:
                subprocess.Popen([editor, filePath])
            elif os.name == "nt":
                os.startfile(filePath)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-t", filePath])
            else:
                subprocess.Popen(["xdg-open", filePath])
            return True
        except Exception:
            return False

    def openRecipeInEditor(self, recipeFile=None):
        if not recipeFile:
            recipeFile = self.getRecipeName()
        if not recipeFile:
            return "No G-Code file selected."

        recipeDirectory = os.path.abspath(Settings.RECIPE_DIR)
        filePath = os.path.abspath(os.path.join(recipeDirectory, recipeFile))
        if not filePath.startswith(recipeDirectory + os.sep):
            return "Invalid recipe path."
        if not os.path.isfile(filePath):
            return "G-Code file not found: " + filePath

        if self._openInEditor(filePath):
            if self._log is not None:
                self._log.add(
                    "Process", "OPEN", "Open G-Code file in editor.", [filePath]
                )
            return True

        return "Failed to open G-Code file."

    def openCalibrationInEditor(self):
        workspace = self._workspaceGetter()
        if not workspace:
            return "No workspace loaded."

        filePath = workspace.getCalibrationFullPath()
        if not filePath:
            return "No calibration file available."

        calibrationDirectory = os.path.abspath(self._workspaceCalibrationDirectory)
        filePath = os.path.abspath(filePath)
        if not filePath.startswith(calibrationDirectory + os.sep):
            return "Invalid calibration path."
        if not os.path.isfile(filePath):
            return "Calibration file not found: " + filePath

        if self._openInEditor(filePath):
            if self._log is not None:
                self._log.add(
                    "Process", "OPEN", "Open calibration file in editor.", [filePath]
                )
            return True

        return "Failed to open calibration file."

    def loadWorkspace(self):
        if self._gCodeHandler is None or self._log is None or self._systemTime is None:
            raise RuntimeError(
                "RecipeService is missing workspace lifecycle dependencies."
            )

        createNew = not os.path.isfile(
            os.path.join(self._workspaceDirectory, WinderWorkspace.FILE_NAME)
        )
        if self._resetWindTime is not None:
            self._resetWindTime()

        workspace = WinderWorkspace(
            self._gCodeHandler,
            self._workspaceDirectory,
            self._workspaceCalibrationDirectory,
            Settings.RECIPE_DIR,
            Settings.RECIPE_ARCHIVE_DIR,
            self._log,
            self._systemTime,
            controlStateMachine=self._controlStateMachine,
            createNew=createNew,
        )
        self._workspaceSetter(workspace)

    def closeWorkspace(self):
        workspace = self._workspaceGetter()
        if workspace:
            if self._getWindTime is not None:
                workspace.addWindTime(self._getWindTime())
            if self._resetWindTime is not None:
                self._resetWindTime()
            workspace.close()
            self._workspaceSetter(None)
