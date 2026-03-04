###############################################################################
# Name: VTemplateRecipe.py
# Uses: Manage V-layer template parameters and recipe generation.
# Date: 2026-03-03
###############################################################################

import datetime
import os
import re

from dune_winder.library.VTemplateGCode import (
  DEFAULT_V_TEMPLATE_ROW_COUNT,
  OFFSET_IDS,
  WRAP_COUNT,
  get_v_recipe_file_name,
  write_v_template_file,
)
from dune_winder.machine.Settings import Settings


OFFSET_LABELS = {
  "top_b_foot_end": "Top B / foot end",
  "top_a_foot_end": "Top A / foot end",
  "foot_a_corner": "Foot A",
  "foot_b_corner": "Foot B",
  "bottom_b_foot_end": "Bottom B / foot end",
  "bottom_a_foot_end": "Bottom A / foot end",
  "top_a_head_end": "Top A / head end",
  "top_b_head_end": "Top B / head end",
  "head_b_corner": "Head B",
  "head_a_corner": "Head A",
  "bottom_a_head_end": "Bottom A / head end",
  "bottom_b_head_end": "Bottom B / head end",
}

_HEADER_HASH_RE = re.compile(r"^\(\s*V-layer\s+([A-Z0-9-]+)\s*\)")


class VTemplateRecipe:
  def __init__(self, process):
    self._process = process
    self._offsets = {}
    self._transferPause = False
    self._dirty = False
    self._generated = {"hashValue": None, "updatedAt": None}
    self._resetState(markDirty=False)

  # -------------------------------------------------------------------
  def _getActiveLayer(self):
    layer = self._process.getRecipeLayer()
    if layer != "V":
      if layer is None:
        return (None, "Load a V recipe to use the V recipe generator.")
      return (None, "This page is only available when the active layer is V.")

    return (layer, None)

  # -------------------------------------------------------------------
  def _mutationGuard(self):
    if not self._process.controlStateMachine.isReadyForMovement():
      return self._errorResult("Machine is not ready to generate the V recipe.")

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
    return get_v_recipe_file_name()

  # -------------------------------------------------------------------
  def _liveFilePath(self):
    return os.path.join(self._recipeDirectory(), self._liveFileName())

  # -------------------------------------------------------------------
  def _normalizeOffsetId(self, offsetId):
    offsetId = str(offsetId).strip()
    if offsetId not in OFFSET_IDS:
      raise ValueError("Unknown V offset: " + repr(offsetId))
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
    self._transferPause = False
    self._dirty = bool(markDirty)

  # -------------------------------------------------------------------
  def getState(self):
    layer = self._process.getRecipeLayer()
    enabled = layer == "V"
    disabledReason = ""
    if layer is None:
      disabledReason = "Load a V recipe to use the V recipe generator."
    elif not enabled:
      disabledReason = "This page is only available when the active layer is V."

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
      "offsets": dict(self._offsets),
      "offsetOrder": list(OFFSET_IDS),
      "offsetLabels": dict(OFFSET_LABELS),
      "wrapCount": WRAP_COUNT,
      "lineCount": DEFAULT_V_TEMPLATE_ROW_COUNT,
      "generated": self._getGeneratedState(liveFile),
    }

  # -------------------------------------------------------------------
  def setOffset(self, offsetId, value):
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
    return self._okResult({"layer": layer, "offsetId": offsetId, "value": self._offsets[offsetId]})

  # -------------------------------------------------------------------
  def setTransferPause(self, enabled):
    _, error = self._getActiveLayer()
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    self._transferPause = bool(enabled)
    self._dirty = True
    return self._okResult({"transferPause": self._transferPause})

  # -------------------------------------------------------------------
  def resetDraft(self, markDirty=True):
    _, error = self._getActiveLayer()
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    self._resetState(markDirty=markDirty)
    return self._okResult(
      {
        "offsets": dict(self._offsets),
        "transferPause": self._transferPause,
      }
    )

  # -------------------------------------------------------------------
  def generateRecipeFile(self):
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
    generation = write_v_template_file(
      outputPath,
      offsets=[self._offsets[offsetId] for offsetId in OFFSET_IDS],
      transfer_pause=self._transferPause,
      archive_directory=self._recipeArchiveDirectory(),
    )

    updatedAt = str(self._process._systemTime.get())
    self._generated = {
      "hashValue": generation["hashValue"],
      "updatedAt": updatedAt,
    }
    self._dirty = False

    recipeWasRefreshed = False
    if (
      self._process.apa is not None
      and getattr(self._process.apa, "_recipeFile", None) == self._liveFileName()
      and hasattr(self._process.apa, "refreshRecipeIfChanged")
    ):
      self._process.apa.refreshRecipeIfChanged()
      recipeWasRefreshed = True

    self._process._log.add(
      "VTemplateRecipe",
      "GENERATE",
      "Generated V recipe file.",
      [
        layer,
        outputPath,
        generation["hashValue"],
        generation["wrapCount"],
        self._transferPause,
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
