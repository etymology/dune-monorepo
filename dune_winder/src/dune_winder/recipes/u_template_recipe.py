###############################################################################
# Name: UTemplateRecipe.py
# Uses: Manage U-layer template parameters and recipe generation.
# Date: 2026-03-04
###############################################################################

import datetime
import json
import os
import re

from dune_winder.recipes.u_template_gcode import (
  DEFAULT_U_TEMPLATE_ROW_COUNT,
  OFFSET_IDS,
  WRAP_COUNT,
  get_u_recipe_file_name,
  write_u_template_file,
)
from dune_winder.machine.Settings import Settings


OFFSET_LABELS = {
  "top_b_foot_end": "Top B / foot end",
  "top_a_foot_end": "Top A / foot end",
  "bottom_a_head_end": "Bottom A / head end",
  "bottom_b_head_end": "Bottom B / head end",
  "head_b_corner": "Head B",
  "head_a_corner": "Head A",
  "top_a_head_end": "Top A / head end",
  "top_b_head_end": "Top B / head end",
  "bottom_b_foot_end": "Bottom B / foot end",
  "bottom_a_foot_end": "Bottom A / foot end",
  "foot_a_corner": "Foot A",
  "foot_b_corner": "Foot B",
}

_HEADER_HASH_RE = re.compile(r"^\(\s*U-layer\s+([A-Z0-9-]+)\s*\)")


class UTemplateRecipe:
  def __init__(self, process):
    self._process = process
    self._offsets = {}
    self._transferPause = True
    self._includeLeadMode = False
    self._dirty = False
    self._generated = {"hashValue": None, "updatedAt": None}
    self._loadedDraftPath = None
    self._resetState(markDirty=False)

  # -------------------------------------------------------------------
  def _getActiveLayer(self):
    layer = self._process.getRecipeLayer()
    if layer != "U":
      if layer is None:
        return (None, "Load a U recipe to use the U recipe generator.")
      return (None, "This page is only available when the active layer is U.")

    return (layer, None)

  # -------------------------------------------------------------------
  def _mutationGuard(self):
    if not self._process.controlStateMachine.isReadyForMovement():
      return self._errorResult("Machine is not ready to generate the U recipe.")

    return None

  # -------------------------------------------------------------------
  def _recipeDirectory(self):
    if self._process.apa is not None and hasattr(self._process.apa, "_recipeDirectory"):
      return self._process.apa._recipeDirectory
    return Settings.RECIPE_DIR

  # -------------------------------------------------------------------
  def _recipeArchiveDirectory(self):
    if self._process.apa is not None and hasattr(self._process.apa, "_recipeArchiveDirectory"):
      return self._process.apa._recipeArchiveDirectory
    return None

  # -------------------------------------------------------------------
  def _liveFileName(self):
    return get_u_recipe_file_name()

  # -------------------------------------------------------------------
  def _liveFilePath(self):
    return os.path.join(self._recipeDirectory(), self._liveFileName())

  # -------------------------------------------------------------------
  def _draftDirectory(self):
    if self._process.apa is not None and hasattr(self._process.apa, "getPath"):
      return os.path.join(self._process.apa.getPath(), "TemplateRecipe")
    return os.path.join(self._process._apaCalibrationDirectory, "TemplateRecipe")

  # -------------------------------------------------------------------
  def _draftFileName(self):
    return "U_Draft.json"

  # -------------------------------------------------------------------
  def _draftFilePath(self):
    return os.path.join(self._draftDirectory(), self._draftFileName())

  # -------------------------------------------------------------------
  def _normalizeOffsetId(self, offsetId):
    offsetId = str(offsetId).strip()
    if offsetId not in OFFSET_IDS:
      raise ValueError("Unknown U offset: " + repr(offsetId))
    return offsetId

  # -------------------------------------------------------------------
  def _readExistingHash(self, filePath):
    if not os.path.isfile(filePath):
      return None

    try:
      with open(filePath, encoding="utf-8") as inputFile:
        match = _HEADER_HASH_RE.search(inputFile.readline().strip())
        if match:
          return match.group(1)
    except OSError:
      return None

    return None

  # -------------------------------------------------------------------
  def _formatTimestamp(self, timestamp):
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

  # -------------------------------------------------------------------
  def _getGeneratedState(self, filePath):
    generated = dict(self._generated)
    if generated["hashValue"] is None:
      generated["hashValue"] = self._readExistingHash(filePath)

    if generated["updatedAt"] is None and os.path.isfile(filePath):
      generated["updatedAt"] = self._formatTimestamp(os.path.getmtime(filePath))

    return generated

  # -------------------------------------------------------------------
  def _okResult(self, data=None):
    result = {"ok": True}
    if data is not None:
      result["data"] = data
    return result

  # -------------------------------------------------------------------
  def _errorResult(self, message):
    return {"ok": False, "error": message}

  # -------------------------------------------------------------------
  def _resetState(self, markDirty):
    self._offsets = {offsetId: 0.0 for offsetId in OFFSET_IDS}
    self._transferPause = True
    self._includeLeadMode = False
    self._dirty = bool(markDirty)

  # -------------------------------------------------------------------
  def _loadStateData(self, data):
    offsets = data.get("offsets", {})
    for offsetId in OFFSET_IDS:
      if offsetId in offsets:
        self._offsets[offsetId] = float(offsets[offsetId])

    self._transferPause = bool(data.get("transferPause", self._transferPause))
    self._includeLeadMode = bool(data.get("includeLeadMode", self._includeLeadMode))
    self._dirty = bool(data.get("dirty", self._dirty))
    generated = data.get("generated", {})
    if isinstance(generated, dict):
      self._generated = {
        "hashValue": generated.get("hashValue"),
        "updatedAt": generated.get("updatedAt"),
      }

  # -------------------------------------------------------------------
  def _loadPersistedState(self, draftPath):
    if not os.path.isfile(draftPath):
      return False

    try:
      with open(draftPath, "r", encoding="utf-8") as inputFile:
        data = json.load(inputFile)
      self._loadStateData(data)
      return True
    except (OSError, ValueError, TypeError) as exception:
      self._process._log.add(
        "UTemplateRecipe",
        "DRAFT_LOAD",
        "Failed to load U template draft state.",
        [draftPath, exception],
      )
      return False

  # -------------------------------------------------------------------
  def _persistState(self):
    draftPath = self._draftFilePath()
    try:
      draftDirectory = self._draftDirectory()
      if not os.path.isdir(draftDirectory):
        os.makedirs(draftDirectory)

      data = {
        "offsets": dict(self._offsets),
        "transferPause": self._transferPause,
        "includeLeadMode": self._includeLeadMode,
        "dirty": self._dirty,
        "generated": dict(self._generated),
      }
      temporaryPath = draftPath + ".tmp"
      with open(temporaryPath, "w", encoding="utf-8") as outputFile:
        json.dump(data, outputFile, indent=2, sort_keys=True)
      os.replace(temporaryPath, draftPath)
      return True
    except Exception as exception:
      self._process._log.add(
        "UTemplateRecipe",
        "DRAFT_SAVE",
        "Failed to save U template draft state.",
        [draftPath, exception],
      )
      return False

  # -------------------------------------------------------------------
  def _ensureDraftStateLoaded(self):
    draftPath = self._draftFilePath()
    if self._loadedDraftPath == draftPath:
      return

    self._resetState(markDirty=False)
    self._generated = {"hashValue": None, "updatedAt": None}
    self._loadPersistedState(draftPath)
    self._loadedDraftPath = draftPath

  # -------------------------------------------------------------------
  def getState(self):
    self._ensureDraftStateLoaded()

    layer = self._process.getRecipeLayer()
    enabled = layer == "U"
    disabledReason = ""
    if layer is None:
      disabledReason = "Load a U recipe to use the U recipe generator."
    elif not enabled:
      disabledReason = "This page is only available when the active layer is U."

    liveFile = self._liveFilePath()
    return {
      "layer": layer,
      "enabled": enabled,
      "movementReady": self._process.controlStateMachine.isReadyForMovement(),
      "disabledReason": disabledReason,
      "dirty": self._dirty,
      "liveFile": liveFile,
      "outputExists": os.path.isfile(liveFile),
      "transferPause": self._transferPause,
      "includeLeadMode": self._includeLeadMode,
      "offsets": dict(self._offsets),
      "offsetOrder": list(OFFSET_IDS),
      "offsetLabels": dict(OFFSET_LABELS),
      "wrapCount": WRAP_COUNT,
      "lineCount": DEFAULT_U_TEMPLATE_ROW_COUNT,
      "generated": self._getGeneratedState(liveFile),
    }

  # -------------------------------------------------------------------
  def setOffset(self, offsetId, value):
    self._ensureDraftStateLoaded()

    layer, error = self._getActiveLayer()
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    try:
      offsetId = self._normalizeOffsetId(offsetId)
    except ValueError as exception:
      return self._errorResult(str(exception))

    self._offsets[offsetId] = float(value)
    self._dirty = True
    self._persistState()
    return self._okResult({"layer": layer, "offsetId": offsetId, "value": self._offsets[offsetId]})

  # -------------------------------------------------------------------
  def setTransferPause(self, enabled):
    self._ensureDraftStateLoaded()

    _, error = self._getActiveLayer()
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    self._transferPause = bool(enabled)
    self._dirty = True
    self._persistState()
    return self._okResult({"transferPause": self._transferPause})

  # -------------------------------------------------------------------
  def setIncludeLeadMode(self, enabled):
    self._ensureDraftStateLoaded()

    _, error = self._getActiveLayer()
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    self._includeLeadMode = bool(enabled)
    self._dirty = True
    self._persistState()
    return self._okResult({"includeLeadMode": self._includeLeadMode})

  # -------------------------------------------------------------------
  def resetDraft(self, markDirty=True):
    self._ensureDraftStateLoaded()

    _, error = self._getActiveLayer()
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    self._resetState(markDirty=markDirty)
    self._persistState()
    return self._okResult(
      {
        "offsets": dict(self._offsets),
        "transferPause": self._transferPause,
        "includeLeadMode": self._includeLeadMode,
      }
    )

  # -------------------------------------------------------------------
  def generateRecipeFile(self):
    self._ensureDraftStateLoaded()

    layer, error = self._getActiveLayer()
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    outputDirectory = self._recipeDirectory()
    if not os.path.isdir(outputDirectory):
      os.makedirs(outputDirectory)

    outputPath = self._liveFilePath()
    generation = write_u_template_file(
      outputPath,
      offsets=[self._offsets[offsetId] for offsetId in OFFSET_IDS],
      transfer_pause=self._transferPause,
      include_lead_mode=self._includeLeadMode,
      archive_directory=self._recipeArchiveDirectory(),
    )

    updatedAt = str(self._process._systemTime.get())
    self._generated = {
      "hashValue": generation["hashValue"],
      "updatedAt": updatedAt,
    }
    self._dirty = False
    self._persistState()

    recipeWasRefreshed = False
    if (
      self._process.apa is not None
      and getattr(self._process.apa, "_recipeFile", None) == self._liveFileName()
      and hasattr(self._process.apa, "refreshRecipeIfChanged")
    ):
      self._process.apa.refreshRecipeIfChanged()
      recipeWasRefreshed = True

    self._process._log.add(
      "UTemplateRecipe",
      "GENERATE",
      "Generated U recipe file.",
      [
        layer,
        outputPath,
        generation["hashValue"],
        generation["wrapCount"],
        self._transferPause,
        self._includeLeadMode,
      ],
    )
    return self._okResult(
      {
        "liveFile": outputPath,
        "hashValue": generation["hashValue"],
        "wrapCount": generation["wrapCount"],
        "lineCount": len(generation["lines"]),
        "recipeReloaded": recipeWasRefreshed,
      }
    )
