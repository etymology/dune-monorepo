###############################################################################
# Name: template_recipe_base.py
# Uses: Shared state/persistence behavior for template recipe services.
# Date: 2026-03-05
###############################################################################

import datetime
import json
import os
import re

from dune_winder.machine.settings import Settings
from dune_winder.recipes.line_offset_overrides import (
    line_offset_override_items,
    normalize_line_key,
    normalize_line_offset_overrides,
)
from dune_winder.recipes.template_gcode_common import normalize_offset_value

from dune_winder.core.process_context import ProcessContext


_OFFSET_AXES = ("x", "y", "z")
_TRAILING_LABEL_RE = re.compile(r"\(([^()]*)\)\s*$")


def _zero_offset_3d():
    return {"x": 0.0, "y": 0.0, "z": 0.0}


def _parse_trailing_label(line_text):
    """Return the trailing parenthesised label of a gcode line (or None)."""
    if line_text is None:
        return None
    match = _TRAILING_LABEL_RE.search(str(line_text).rstrip())
    if match is None:
        return None
    label = match.group(1).strip()
    return label or None


class TemplateRecipeBase:
    LAYER = None
    SERVICE_NAME = None
    OFFSET_IDS = ()
    OFFSET_LABELS = {}
    OFFSET_NATURAL_AXIS = {}
    LABEL_TO_OFFSET_ID = {}
    WRAP_COUNT = 0
    DEFAULT_ROW_COUNT = 0
    HEADER_HASH_RE = None
    DRAFT_FILE_NAME = None

    # -------------------------------------------------------------------
    def _naturalAxis(self, offsetId):
        return self.OFFSET_NATURAL_AXIS.get(offsetId, "x")

    @staticmethod
    def get_recipe_file_name():
        raise NotImplementedError("get_recipe_file_name() must be implemented.")

    @staticmethod
    def write_template_file(
        output_path,
        *,
        offsets=None,
        transfer_pause=False,
        add_foot_pauses=False,
        include_lead_mode=False,
        strip_g113_params=False,
        spool_change_pause=False,
        named_inputs=None,
        special_inputs=None,
        archive_directory=None,
        parent_hash=None,
    ):
        _ = (
            output_path,
            offsets,
            transfer_pause,
            add_foot_pauses,
            include_lead_mode,
            spool_change_pause,
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
    def __init__(self, process: ProcessContext):
        self._process = process
        self._offsets = {}
        self._lineOffsetOverrides = {}
        self._transferPause = True
        self._addFootPauses = False
        self._includeLeadMode = False
        self._stripG113Params = False
        self._spoolChangePause = False
        self._dirty = False
        self._generated = {"hashValue": None, "updatedAt": None}
        self._lastGeneratedScriptVariant = None
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
                "This page is only available when the active layer is "
                + expectedLayer
                + ".",
            )

        return (layer, None)

    # -------------------------------------------------------------------
    def _mutationGuard(self):
        return None

    # -------------------------------------------------------------------
    def _recipeDirectory(self):
        if self._process.workspace is not None and hasattr(
            self._process.workspace, "_recipeDirectory"
        ):
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
        if self._process.workspace is not None and hasattr(
            self._process.workspace, "getPath"
        ):
            return os.path.join(self._process.workspace.getPath(), "TemplateRecipe")
        return os.path.join(
            self._process._workspaceCalibrationDirectory, "TemplateRecipe"
        )

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
                header_hash_re = self.HEADER_HASH_RE
                if header_hash_re is None:
                    return None
                match = header_hash_re.search(inputFile.readline().strip())
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
        self._offsets = {offsetId: _zero_offset_3d() for offsetId in self.OFFSET_IDS}
        self._lineOffsetOverrides = {}
        self._transferPause = True
        self._addFootPauses = False
        self._includeLeadMode = False
        self._stripG113Params = False
        self._spoolChangePause = False
        self._resetExtraState()
        self._dirty = bool(markDirty)

    # -------------------------------------------------------------------
    def _loadStateData(self, data):
        offsets = data.get("offsets", {})
        for offsetId in self.OFFSET_IDS:
            if offsetId in offsets:
                self._offsets[offsetId] = normalize_offset_value(
                    offsets[offsetId],
                    natural_axis=self._naturalAxis(offsetId),
                )

        self._lineOffsetOverrides = normalize_line_offset_overrides(
            data.get("lineOffsetOverrides", {})
        )
        self._transferPause = bool(data.get("transferPause", self._transferPause))
        self._addFootPauses = bool(data.get("addFootPauses", self._addFootPauses))
        self._includeLeadMode = bool(data.get("includeLeadMode", self._includeLeadMode))
        self._stripG113Params = bool(data.get("stripG113Params", self._stripG113Params))
        self._spoolChangePause = bool(
            data.get("spoolChangePause", self._spoolChangePause)
        )
        self._lastGeneratedScriptVariant = data.get("lastGeneratedScriptVariant")
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
                "lineOffsetOverrides": dict(self._lineOffsetOverrides),
                "transferPause": self._transferPause,
                "addFootPauses": self._addFootPauses,
                "includeLeadMode": self._includeLeadMode,
                "stripG113Params": self._stripG113Params,
                "spoolChangePause": self._spoolChangePause,
                "lastGeneratedScriptVariant": self._lastGeneratedScriptVariant,
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
                "Load a "
                + expectedLayer
                + " recipe to use the "
                + expectedLayer
                + " recipe generator."
            )
        elif not enabled:
            disabledReason = (
                "This page is only available when the active layer is "
                + expectedLayer
                + "."
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
            "addFootPauses": self._addFootPauses,
            "includeLeadMode": self._includeLeadMode,
            "stripG113Params": self._stripG113Params,
            "spoolChangePause": self._spoolChangePause,
            "offsets": dict(self._offsets),
            "lineOffsetOverrides": dict(self._lineOffsetOverrides),
            "lineOffsetOverrideItems": line_offset_override_items(
                self._lineOffsetOverrides
            ),
            "offsetOrder": list(self.OFFSET_IDS),
            "offsetLabels": dict(self.OFFSET_LABELS),
            "offsetNaturalAxis": dict(self.OFFSET_NATURAL_AXIS),
            "wrapCount": self.WRAP_COUNT,
            "lineCount": self.DEFAULT_ROW_COUNT,
            "generated": self._getGeneratedState(liveFile),
            "lastGeneratedScriptVariant": self._lastGeneratedScriptVariant,
        }
        state.update(self._extraPublicState())
        return state

    # -------------------------------------------------------------------
    def setOffset(self, offsetId, value=None, *, x=None, y=None, z=None):
        """Set a 3D offset for `offsetId`.

        Accepts either a 3D dict via `value`, a legacy scalar via `value`
        (placed on the natural axis), or per-axis keyword arguments. Any
        axis omitted in keyword form preserves the existing value.
        """
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

        if value is not None:
            if isinstance(value, dict):
                self._offsets[offsetId] = normalize_offset_value(
                    value, natural_axis=self._naturalAxis(offsetId)
                )
            else:
                # Legacy scalar: only the natural axis is touched; preserve any
                # off-axis calibration the operator may have set via jog calibration.
                current = dict(self._offsets.get(offsetId, _zero_offset_3d()))
                current[self._naturalAxis(offsetId)] = float(value)
                self._offsets[offsetId] = current
        else:
            current = dict(self._offsets.get(offsetId, _zero_offset_3d()))
            for axis_key, axis_value in (("x", x), ("y", y), ("z", z)):
                if axis_value is not None:
                    current[axis_key] = float(axis_value)
            self._offsets[offsetId] = current

        self._dirty = True
        self._persistState()
        return self._okResult(
            {"layer": layer, "offsetId": offsetId, "value": dict(self._offsets[offsetId])}
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
    def setLineOffsetOverride(self, lineKey, xValue, yValue, extra=None):
        self._ensureDraftStateLoaded()

        _, error = self._getActiveLayer()
        if error is not None:
            return self._errorResult(error)

        blocked = self._mutationGuard()
        if blocked is not None:
            return blocked

        entry = dict(extra or {})
        entry["x"] = float(xValue)
        entry["y"] = float(yValue)
        lineKey = normalize_line_key(lineKey)
        self._lineOffsetOverrides[lineKey] = entry
        self._dirty = True
        self._persistState()
        return self._okResult({"lineKey": lineKey, **entry})

    # -------------------------------------------------------------------
    def deleteLineOffsetOverride(self, lineKey):
        self._ensureDraftStateLoaded()

        _, error = self._getActiveLayer()
        if error is not None:
            return self._errorResult(error)

        blocked = self._mutationGuard()
        if blocked is not None:
            return blocked

        lineKey = normalize_line_key(lineKey)
        if lineKey in self._lineOffsetOverrides:
            del self._lineOffsetOverrides[lineKey]
            self._dirty = True
            self._persistState()
        return self._okResult({"lineKey": lineKey})

    # -------------------------------------------------------------------
    def replaceLineOffsetOverrides(self, overrides):
        self._ensureDraftStateLoaded()

        _, error = self._getActiveLayer()
        if error is not None:
            return self._errorResult(error)

        blocked = self._mutationGuard()
        if blocked is not None:
            return blocked

        self._lineOffsetOverrides = normalize_line_offset_overrides(overrides)
        self._dirty = True
        self._persistState()
        return self._okResult(
            {
                "lineOffsetOverrides": dict(self._lineOffsetOverrides),
                "lineOffsetOverrideItems": line_offset_override_items(
                    self._lineOffsetOverrides
                ),
            }
        )

    # -------------------------------------------------------------------
    def setAddFootPauses(self, enabled):
        self._ensureDraftStateLoaded()

        _, error = self._getActiveLayer()
        if error is not None:
            return self._errorResult(error)

        blocked = self._mutationGuard()
        if blocked is not None:
            return blocked

        self._addFootPauses = bool(enabled)
        self._dirty = True
        self._persistState()
        return self._okResult({"addFootPauses": self._addFootPauses})

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
    def setSpoolChangePause(self, enabled):
        self._ensureDraftStateLoaded()

        _, error = self._getActiveLayer()
        if error is not None:
            return self._errorResult(error)

        blocked = self._mutationGuard()
        if blocked is not None:
            return blocked

        self._spoolChangePause = bool(enabled)
        self._dirty = True
        self._persistState()
        return self._okResult({"spoolChangePause": self._spoolChangePause})

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
                "addFootPauses": self._addFootPauses,
                "includeLeadMode": self._includeLeadMode,
                "stripG113Params": self._stripG113Params,
                "spoolChangePause": self._spoolChangePause,
                "lineOffsetOverrides": dict(self._lineOffsetOverrides),
                **self._extraPublicState(),
            }
        )

    # -------------------------------------------------------------------
    def generateRecipeFile(self, scriptVariant=None):
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
        generation_kwargs = {
            "offsets": [self._offsets[offsetId] for offsetId in self.OFFSET_IDS],
            "transfer_pause": self._transferPause,
            "add_foot_pauses": self._addFootPauses,
            "include_lead_mode": self._includeLeadMode,
            "strip_g113_params": self._stripG113Params,
            "spool_change_pause": self._spoolChangePause,
            "line_offset_overrides": dict(self._lineOffsetOverrides),
            "archive_directory": self._recipeArchiveDirectory(),
            **self._generationKwargs(),
        }
        if scriptVariant is not None:
            generation_kwargs["script_variant"] = scriptVariant

        generation = self.write_template_file(outputPath, **generation_kwargs)

        updatedAt = str(self._process._systemTime.get())
        self._generated = {
            "hashValue": generation["hashValue"],
            "updatedAt": updatedAt,
        }
        self._lastGeneratedScriptVariant = generation.get("scriptVariant")
        self._dirty = False
        self._persistState()

        recipeWasRefreshed = False
        if (
            self._process.workspace is not None
            and getattr(self._process.workspace, "_recipeFile", None)
            == self._liveFileName()
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
                generation.get("scriptVariant"),
                self._transferPause,
                self._addFootPauses,
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

    # -------------------------------------------------------------------
    def _collectJogCalibrationSnapshot(self):
        """Read live jog-calibration inputs without mutating state.

        Returns `{"ok": True, "data": {...}}` on success or
        `{"ok": False, "error": "..."}` on failure.
        """
        self._ensureDraftStateLoaded()

        layer, error = self._getActiveLayer()
        if error is not None:
            return {"ok": False, "error": error}

        process = self._process
        if not process.controlStateMachine.isStopped():
            return {
                "ok": False,
                "error": "Machine must be in STOP state to apply jog calibration.",
            }

        handler = getattr(process, "gCodeHandler", None)
        line_index = handler.getLine() if handler is not None else None
        if line_index is None or line_index < 0:
            return {
                "ok": False,
                "error": "No g-code line has been executed yet.",
            }

        gCode = getattr(handler, "_gCode", None)
        if gCode is None or line_index >= gCode.getLineCount():
            return {
                "ok": False,
                "error": "Last g-code line is no longer available.",
            }

        line_text = gCode.lines[line_index]
        label = _parse_trailing_label(line_text)
        if label is None or label not in self.LABEL_TO_OFFSET_ID:
            return {
                "ok": False,
                "error": (
                    "Last executed line has no calibratable label "
                    "(parsed: " + repr(label) + ")."
                ),
            }

        offset_id = self.LABEL_TO_OFFSET_ID[label]
        commanded = {
            "x": float(getattr(handler, "_x", 0.0) or 0.0),
            "y": float(getattr(handler, "_y", 0.0) or 0.0),
            "z": float(getattr(handler, "_z", 0.0) or 0.0),
        }
        io = process._io
        actual = {
            "x": float(io.xAxis.getPosition()),
            "y": float(io.yAxis.getPosition()),
            "z": float(io.zAxis.getPosition()) if hasattr(io, "zAxis") else 0.0,
        }
        delta = {axis: actual[axis] - commanded[axis] for axis in _OFFSET_AXES}
        current_offset = dict(self._offsets.get(offset_id, _zero_offset_3d()))
        new_offset = {axis: current_offset[axis] + delta[axis] for axis in _OFFSET_AXES}

        return {
            "ok": True,
            "data": {
                "layer": layer,
                "lineIndex": line_index,
                "lineText": line_text,
                "label": label,
                "offsetId": offset_id,
                "commanded": commanded,
                "actual": actual,
                "delta": delta,
                "currentOffset": current_offset,
                "newOffset": new_offset,
            },
        }

    # -------------------------------------------------------------------
    def previewJogCalibration(self):
        """Compute the delta that *would* be applied without mutating state."""
        snapshot = self._collectJogCalibrationSnapshot()
        if not snapshot["ok"]:
            return self._errorResult(snapshot["error"])
        return self._okResult(snapshot["data"])

    # -------------------------------------------------------------------
    def applyJogCalibration(self):
        """Apply the jog-derived delta to the matching machine-geometry offset.

        Adds `actual − commanded` to `_offsets[offset_id]`, persists, regenerates
        the recipe, and records a `kind="jog_calibration"` measurement in the
        machine-geometry calibration store.
        """
        snapshot = self._collectJogCalibrationSnapshot()
        if not snapshot["ok"]:
            return self._errorResult(snapshot["error"])

        blocked = self._mutationGuard()
        if blocked is not None:
            return blocked

        data = snapshot["data"]
        offset_id = data["offsetId"]
        delta = data["delta"]
        current_offset = data["currentOffset"]
        new_offset = {
            axis: float(current_offset[axis]) + float(delta[axis])
            for axis in _OFFSET_AXES
        }
        self._offsets[offset_id] = new_offset
        self._dirty = True
        self._persistState()

        try:
            self._process.machineGeometryCalibration.recordJogMeasurement(
                layer=self._layerName(),
                line_index=data["lineIndex"],
                gcode_line=data["lineText"],
                label=data["label"],
                offset_id=offset_id,
                commanded=data["commanded"],
                actual=data["actual"],
                delta=delta,
                previous_offset=current_offset,
                new_offset=new_offset,
            )
        except Exception as exception:
            self._process._log.add(
                self._serviceName(),
                "JOG_CAL_LOG_FAIL",
                "Failed to record jog calibration measurement.",
                [str(exception)],
            )

        regen_result = self.generateRecipeFile()
        regen_ok = bool(regen_result.get("ok"))

        result = dict(data)
        result["newOffset"] = new_offset
        result["regenerated"] = regen_ok
        if not regen_ok:
            result["regenerationError"] = regen_result.get("error")
        return self._okResult(result)
