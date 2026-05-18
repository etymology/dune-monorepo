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
_ANCHOR_OFFSET_RE = re.compile(
    r"offset=\(\s*(-?\d*\.?\d+)\s*,\s*(-?\d*\.?\d+)"
    r"(?:\s*,\s*(-?\d*\.?\d+))?\s*\)"
)


def _parse_rendered_anchor_offset(line_text):
    """Extract the (x, y, z) offset that was rendered into an ~anchorToTarget call.

    Accepts both legacy 2-tuple (x, y) and 3-tuple (x, y, z) forms; missing z is 0.
    """
    if line_text is None:
        return (0.0, 0.0, 0.0)
    match = _ANCHOR_OFFSET_RE.search(str(line_text))
    if match is None:
        return (0.0, 0.0, 0.0)
    z_group = match.group(3)
    return (
        float(match.group(1)),
        float(match.group(2)),
        float(z_group) if z_group is not None else 0.0,
    )


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


_LINE_NUMBER_PREFIX_RE = re.compile(r"^\s*N\d+\s+")
_WRAP_IDENTIFIER_RE = re.compile(r"\(\d+,\d+\)")
_ANCHOR_OFFSET_KEYWORD_RE = re.compile(
    r",\s*offset=\(\s*-?\d*\.?\d+\s*,\s*-?\d*\.?\d+"
    r"(?:\s*,\s*-?\d*\.?\d+)?\s*\)"
)


def _strip_anchor_offset(line_text):
    """Strip ~anchorToTarget offset= keyword and runner-added prefixes.

    Removes the leading ``Nxx`` line number, any ``(wrap,line)`` wrap
    identifier, and the ``,offset=(...)`` keyword inside any
    ``~anchorToTarget(...)`` call.  Trailing labels like
    ``(Top A corner)`` are preserved for operator readability.
    """
    text = str(line_text)
    text = _LINE_NUMBER_PREFIX_RE.sub("", text)
    text = _WRAP_IDENTIFIER_RE.sub("", text, count=1)
    text = _ANCHOR_OFFSET_KEYWORD_RE.sub("", text)
    return " ".join(text.split())


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
    def setLineOffsetOverride(self, lineKey, xValue, yValue, zValue=0.0, extra=None):
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
        entry["z"] = float(zValue)
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
    def _readActualPosition(self):
        """Sample current motor XYZ position from IO.

        The Z axis motor position is reported even when the head is in the
        fixed-present mode -- the operator may still be jogging the Z
        gantry, and the static `extended_z_position` configuration value
        is not a useful proxy for "where the wire is right now."
        """
        process = self._process
        io = process._io
        x_pos = float(io.xAxis.getPosition()) if hasattr(io, "xAxis") else 0.0
        y_pos = float(io.yAxis.getPosition()) if hasattr(io, "yAxis") else 0.0
        z_pos = float(io.zAxis.getPosition()) if hasattr(io, "zAxis") else 0.0
        return {"x": x_pos, "y": y_pos, "z": z_pos}

    # -------------------------------------------------------------------
    def _collectJogCalibrationSnapshot(self):
        """Read live jog-calibration inputs without mutating state.

        Safe to call at any time, including during G-code execution.  The
        frontend polls this for the auto-updating "last labeled line"
        panel and expects the call to *always* succeed -- a top-level
        `available` field flags whether a calibratable line is currently
        in view.  Mutation guards for actually applying the offset live
        in `applyJogCalibration`.
        """
        self._ensureDraftStateLoaded()

        actual = self._readActualPosition()

        layer, layer_error = self._getActiveLayer()
        if layer_error is not None:
            return {
                "available": False,
                "reason": layer_error,
                "actual": actual,
            }

        process = self._process
        trace = getattr(process, "getLastInstructionTrace", lambda: None)()
        if not isinstance(trace, dict) or not trace.get("line"):
            return {
                "available": False,
                "reason": "No g-code line has been executed yet.",
                "layer": layer,
                "actual": actual,
            }

        line_text = trace["line"]
        label = _parse_trailing_label(line_text)
        if label is None or label not in self.LABEL_TO_OFFSET_ID:
            return {
                "available": False,
                "reason": (
                    "Last executed line has no calibratable label "
                    "(parsed: " + repr(label) + ")."
                ),
                "layer": layer,
                "lineText": line_text,
                "actual": actual,
            }

        handler = getattr(process, "gCodeHandler", None)
        line_index = handler.getLine() if handler is not None else None
        if line_index is None or line_index < 0:
            line_index = None

        offset_id = self.LABEL_TO_OFFSET_ID[label]
        resulting_target = trace.get("resultingTarget") or {}
        commanded = {
            "x": float(resulting_target.get("x") or 0.0),
            "y": float(resulting_target.get("y") or 0.0),
            "z": float(
                resulting_target.get("pinZ")
                if resulting_target.get("pinZ") is not None
                else resulting_target.get("headZ") or 0.0
            ),
        }
        rendered_offset_x, rendered_offset_y, rendered_offset_z = (
            _parse_rendered_anchor_offset(line_text)
        )
        rendered_offset = {
            "x": rendered_offset_x,
            "y": rendered_offset_y,
            "z": rendered_offset_z,
        }
        base = {
            "x": commanded["x"] - rendered_offset_x,
            "y": commanded["y"] - rendered_offset_y,
            "z": commanded["z"] - rendered_offset_z,
        }
        delta = {axis: actual[axis] - commanded[axis] for axis in _OFFSET_AXES}
        current_offset = dict(self._offsets.get(offset_id, _zero_offset_3d()))
        new_offset = {axis: actual[axis] - base[axis] for axis in _OFFSET_AXES}

        # Alternating-side wires cross the frame at a fixed clearance Z
        # (z_extended for A targets, z_back for B targets); the operator cannot
        # meaningfully jog the head in Z, so the Z component of the offset is
        # not applied to the rendered anchor call.  We still report observed
        # actual.z and delta.z so the geometry solver can ignore them.
        same_side = trace.get("sameSide")
        if same_side is False:
            new_offset["z"] = 0.0

        return {
            "available": True,
            "layer": layer,
            "lineIndex": line_index,
            "lineText": line_text,
            "label": label,
            "offsetId": offset_id,
            "sameSide": same_side,
            "commanded": commanded,
            "actual": actual,
            "delta": delta,
            "currentOffset": current_offset,
            "newOffset": new_offset,
            "renderedOffset": rendered_offset,
        }

    # -------------------------------------------------------------------
    def previewJogCalibration(self):
        """Return the current jog-calibration snapshot.

        Always reports ok=true: an inner `available` field flags whether
        the snapshot is calibratable (V layer loaded, labeled line in the
        trace, etc).  When unavailable, the `reason` field tells the
        operator what's missing.  Keeping a uniformly-successful envelope
        lets the frontend poll this continuously without the periodic
        callback infrastructure swallowing the response.
        """
        return self._okResult(self._collectJogCalibrationSnapshot())

    # -------------------------------------------------------------------
    def applyJogCalibration(self):
        """Apply the jog-derived offset to the matching machine-geometry offset.

        The new offset is `actual − base` where `base` is the position that
        `~anchorToTarget` would have commanded with no offset (recovered by
        subtracting the offset baked into the executed line).  Persists, regenerates
        the recipe, and records a `kind="jog_calibration"` measurement in the
        machine-geometry calibration store.
        """
        process = self._process
        is_gcode_active = (
            bool(process.isGCodeExecutionActive())
            if hasattr(process, "isGCodeExecutionActive")
            else False
        )
        if is_gcode_active:
            return self._errorResult(
                "Stop G-code execution before applying jog calibration."
            )

        snapshot = self._collectJogCalibrationSnapshot()
        if not snapshot.get("available"):
            return self._errorResult(
                snapshot.get("reason", "No calibratable line is currently in view.")
            )

        blocked = self._mutationGuard()
        if blocked is not None:
            return blocked

        data = snapshot
        offset_id = data["offsetId"]
        current_offset = data["currentOffset"]
        new_offset = {axis: float(data["newOffset"][axis]) for axis in _OFFSET_AXES}
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
                delta=data["delta"],
                previous_offset=current_offset,
                new_offset=new_offset,
                same_side=data.get("sameSide"),
            )
        except Exception as exception:
            self._process._log.add(
                self._serviceName(),
                "JOG_CAL_LOG_FAIL",
                "Failed to record jog calibration measurement.",
                [str(exception)],
            )

        regen_result = self.generateRecipeFile(scriptVariant="wrapping")
        regen_ok = bool(regen_result.get("ok"))

        result = dict(data)
        result["newOffset"] = new_offset
        result["regenerated"] = regen_ok
        if not regen_ok:
            result["regenerationError"] = regen_result.get("error")
        return self._okResult(result)

    # -------------------------------------------------------------------
    def runBareJogCalibrationLine(self):
        """Re-execute the last labeled line with all offsets stripped.

        Lets the operator land at the bare anchor-to-target position so
        they can jog from there to align the wire by eye.  Strips both
        the rendered ``offset=(x,y[,z])`` keyword from the anchor call
        and any leading line-number / wrap-identifier annotations that
        the recipe runner adds, then dispatches the result through the
        normal manual G-Code path.
        """
        snapshot = self._collectJogCalibrationSnapshot()
        if not snapshot.get("available"):
            return self._errorResult(
                snapshot.get("reason", "No calibratable line is currently in view.")
            )

        bare_line = _strip_anchor_offset(str(snapshot["lineText"]))
        if not bare_line.strip():
            return self._errorResult(
                "Could not derive a bare g-code line from the last trace."
            )

        process = self._process
        execute_fn = getattr(process, "executeG_CodeLine", None)
        if execute_fn is None:
            return self._errorResult(
                "Manual G-Code execution is not available on this process."
            )

        try:
            error = execute_fn(bare_line)
        except Exception as exception:
            return self._errorResult(
                "Failed to execute bare line: " + str(exception)
            )

        if error:
            return self._errorResult("Failed to execute bare line: " + str(error))

        return self._okResult(
            {
                "lineText": snapshot["lineText"],
                "bareLine": bare_line,
                "label": snapshot.get("label"),
                "offsetId": snapshot.get("offsetId"),
            }
        )
