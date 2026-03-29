###############################################################################
# Name: template_recipe_base.py
# Uses: Shared state/persistence behavior for template recipe services.
# Date: 2026-03-05
###############################################################################

import datetime
import json
import os

from dune_winder.machine.settings import Settings


class TemplateRecipeBase:
  LAYER = None
  SERVICE_NAME = None
  OFFSET_IDS = ()
  OFFSET_LABELS = {}
  WRAP_COUNT = 0
  DEFAULT_ROW_COUNT = 0
  HEADER_HASH_RE = None
  DRAFT_FILE_NAME = None

  @staticmethod
  def get_recipe_file_name():
    raise NotImplementedError("get_recipe_file_name() must be implemented.")

  @staticmethod
  def write_template_file(
    output_path,
    *,
    offsets=None,
    transfer_pause=False,
    include_lead_mode=False,
    strip_g113_params=False,
    named_inputs=None,
    special_inputs=None,
    archive_directory=None,
    parent_hash=None,
  ):
    _ = (
      output_path,
      offsets,
      transfer_pause,
      include_lead_mode,
      named_inputs,
      special_inputs,
      archive_directory,
      parent_hash,
    )
    raise NotImplementedError("write_template_file() must be implemented.")

  # -------------------------------------------------------------------
  def _resetExtraState(self):
    return None

  # -------------------------------------------------------------------
  def _loadExtraStateData(self, data):
    _ = data
    return None

  # -------------------------------------------------------------------
  def _extraDraftState(self):
    return {}

  # -------------------------------------------------------------------
  def _extraPublicState(self):
    return {}

  # -------------------------------------------------------------------
  def _generationKwargs(self):
    return {}

  # -------------------------------------------------------------------
  def __init__(self, process):
    self._process = process
    self._offsets = {}
    self._transferPause = True
    self._includeLeadMode = False
    self._stripG113Params = False
    self._dirty = False
    self._generated = {"hashValue": None, "updatedAt": None}
    self._loadedDraftPath = None
    self._resetState(markDirty=False)

  # -------------------------------------------------------------------
  def _layerName(self):
    return str(self.LAYER)

  # -------------------------------------------------------------------
  def _serviceName(self):
    if self.SERVICE_NAME is not None:
      return str(self.SERVICE_NAME)
    return self.__class__.__name__

  # -------------------------------------------------------------------
  def _getActiveLayer(self):
    layer = self._process.getRecipeLayer()
    expectedLayer = self._layerName()
    if layer != expectedLayer:
      if layer is None:
        return (
          None,
          "Load a "
          + expectedLayer
          + " recipe to use the "
          + expectedLayer
          + " recipe generator.",
        )
      return (
        None,
        "This page is only available when the active layer is " + expectedLayer + ".",
      )

    return (layer, None)

  # -------------------------------------------------------------------
  def _mutationGuard(self):
    if not self._process.controlStateMachine.isReadyForMovement():
      return self._errorResult(
        "Machine is not ready to generate the " + self._layerName() + " recipe."
      )

    return None

  # -------------------------------------------------------------------
  def _recipeDirectory(self):
    if self._process.workspace is not None and hasattr(self._process.workspace, "_recipeDirectory"):
      return self._process.workspace._recipeDirectory
    return Settings.RECIPE_DIR

  # -------------------------------------------------------------------
  def _recipeArchiveDirectory(self):
    if self._process.workspace is not None and hasattr(
      self._process.workspace,
      "_recipeArchiveDirectory",
    ):
      return self._process.workspace._recipeArchiveDirectory
    return None

  # -------------------------------------------------------------------
  def _liveFileName(self):
    return self.get_recipe_file_name()

  # -------------------------------------------------------------------
  def _liveFilePath(self):
    return os.path.join(self._recipeDirectory(), self._liveFileName())

  # -------------------------------------------------------------------
  def _draftDirectory(self):
    if self._process.workspace is not None and hasattr(self._process.workspace, "getPath"):
      return os.path.join(self._process.workspace.getPath(), "TemplateRecipe")
    return os.path.join(self._process._workspaceCalibrationDirectory, "TemplateRecipe")

  # -------------------------------------------------------------------
  def _draftFileName(self):
    return str(self.DRAFT_FILE_NAME)

  # -------------------------------------------------------------------
  def _draftFilePath(self):
    return os.path.join(self._draftDirectory(), self._draftFileName())

  # -------------------------------------------------------------------
  def _normalizeOffsetId(self, offsetId):
    offsetId = str(offsetId).strip()
    if offsetId not in self.OFFSET_IDS:
      raise ValueError(
        "Unknown " + self._layerName() + " offset: " + repr(offsetId)
      )
    return offsetId

  # -------------------------------------------------------------------
  def _readExistingHash(self, filePath):
    if not os.path.isfile(filePath):
      return None

    try:
      with open(filePath, encoding="utf-8") as inputFile:
        match = self.HEADER_HASH_RE.search(inputFile.readline().strip())
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
    self._offsets = {offsetId: 0.0 for offsetId in self.OFFSET_IDS}
    self._transferPause = True
    self._includeLeadMode = False
    self._stripG113Params = False
    self._resetExtraState()
    self._dirty = bool(markDirty)

  # -------------------------------------------------------------------
  def _loadStateData(self, data):
    offsets = data.get("offsets", {})
    for offsetId in self.OFFSET_IDS:
      if offsetId in offsets:
        self._offsets[offsetId] = float(offsets[offsetId])

    self._transferPause = bool(data.get("transferPause", self._transferPause))
    self._includeLeadMode = bool(data.get("includeLeadMode", self._includeLeadMode))
    self._stripG113Params = bool(data.get("stripG113Params", self._stripG113Params))
    self._dirty = bool(data.get("dirty", self._dirty))
    generated = data.get("generated", {})
    if isinstance(generated, dict):
      self._generated = {
        "hashValue": generated.get("hashValue"),
        "updatedAt": generated.get("updatedAt"),
      }
    self._loadExtraStateData(data)

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
        self._serviceName(),
        "DRAFT_LOAD",
        "Failed to load " + self._layerName() + " template draft state.",
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
        "stripG113Params": self._stripG113Params,
        "dirty": self._dirty,
        "generated": dict(self._generated),
      }
      data.update(self._extraDraftState())
      temporaryPath = draftPath + ".tmp"
      with open(temporaryPath, "w", encoding="utf-8") as outputFile:
        json.dump(data, outputFile, indent=2, sort_keys=True)
      os.replace(temporaryPath, draftPath)
      return True
    except Exception as exception:
      self._process._log.add(
        self._serviceName(),
        "DRAFT_SAVE",
        "Failed to save " + self._layerName() + " template draft state.",
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
    expectedLayer = self._layerName()
    enabled = layer == expectedLayer
    disabledReason = ""
    if layer is None:
      disabledReason = (
        "Load a " + expectedLayer + " recipe to use the " + expectedLayer + " recipe generator."
      )
    elif not enabled:
      disabledReason = (
        "This page is only available when the active layer is " + expectedLayer + "."
      )

    liveFile = self._liveFilePath()
    state = {
      "layer": layer,
      "enabled": enabled,
      "movementReady": self._process.controlStateMachine.isReadyForMovement(),
      "disabledReason": disabledReason,
      "dirty": self._dirty,
      "liveFile": liveFile,
      "outputExists": os.path.isfile(liveFile),
      "transferPause": self._transferPause,
      "includeLeadMode": self._includeLeadMode,
      "stripG113Params": self._stripG113Params,
      "offsets": dict(self._offsets),
      "offsetOrder": list(self.OFFSET_IDS),
      "offsetLabels": dict(self.OFFSET_LABELS),
      "wrapCount": self.WRAP_COUNT,
      "lineCount": self.DEFAULT_ROW_COUNT,
      "generated": self._getGeneratedState(liveFile),
    }
    state.update(self._extraPublicState())
    return state

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
    return self._okResult(
      {"layer": layer, "offsetId": offsetId, "value": self._offsets[offsetId]}
    )

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
  def setStripG113Params(self, enabled):
    self._ensureDraftStateLoaded()

    _, error = self._getActiveLayer()
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    self._stripG113Params = bool(enabled)
    self._dirty = True
    self._persistState()
    return self._okResult({"stripG113Params": self._stripG113Params})

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
        "stripG113Params": self._stripG113Params,
        **self._extraPublicState(),
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
    generation = self.write_template_file(
      outputPath,
      offsets=[self._offsets[offsetId] for offsetId in self.OFFSET_IDS],
      transfer_pause=self._transferPause,
      include_lead_mode=self._includeLeadMode,
      strip_g113_params=self._stripG113Params,
      archive_directory=self._recipeArchiveDirectory(),
      **self._generationKwargs(),
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
      self._process.workspace is not None
      and getattr(self._process.workspace, "_recipeFile", None) == self._liveFileName()
      and hasattr(self._process.workspace, "refreshRecipeIfChanged")
    ):
      self._process.workspace.refreshRecipeIfChanged()
      recipeWasRefreshed = True

    self._process._log.add(
      self._serviceName(),
      "GENERATE",
      "Generated " + self._layerName() + " recipe file.",
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
