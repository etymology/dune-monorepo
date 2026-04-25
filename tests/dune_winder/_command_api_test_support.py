from dune_winder.api.commands import build_command_registry
import hashlib


class DummyLog:
    def __init__(self):
        self.entries = []

    def add(self, *args):
        self.entries.append(args)

    def getAll(self, numberOfLines=-1):
        return (
            ["entry-a", "entry-b"][: max(0, numberOfLines)]
            if numberOfLines >= 0
            else ["entry-a", "entry-b"]
        )


class DummyControlState:
    def __init__(self):
        class StopMode:
            pass

        self.state = StopMode()

    def isReadyForMovement(self):
        return True


class DummyGCodeHandler:
    def __init__(self):
        self._line = 12
        self._total = 99
        self._velocityScale = 1.0

    def isG_CodeLoaded(self):
        return True

    def getLine(self):
        return self._line

    def getTotalLines(self):
        return self._total

    def getVelocityScale(self):
        return self._velocityScale


class DummyTemplateRecipe:
    def __init__(self):
        self.lastPullIn = None

    def getState(self):
        return {"layer": "V"}

    def setOffset(self, offsetId, value):
        return {"ok": True, "data": {"offsetId": offsetId, "value": value}}

    def setPullIn(self, pullInId, value):
        self.lastPullIn = (pullInId, value)
        return {"ok": True, "data": {"pullInId": pullInId, "value": value}}

    def setTransferPause(self, enabled):
        return {"ok": True, "data": {"enabled": enabled}}

    def setAddFootPauses(self, enabled):
        return {"ok": True, "data": {"enabled": enabled}}

    def setIncludeLeadMode(self, enabled):
        return {"ok": True, "data": {"enabled": enabled}}

    def resetDraft(self, markDirty=True):
        return {"ok": True, "data": {"markDirty": markDirty}}

    def generateRecipeFile(self, scriptVariant=None):
        return {"ok": True, "data": {"generated": True, "scriptVariant": scriptVariant}}


class DummyMachineGeometryCalibration:
    def __init__(self):
        self.measurements = []
        self.lastSetLineOffset = None
        self.lastDeletedLineOffset = None

    def getState(self):
        return {
            "enabled": True,
            "activeLayer": "V",
            "measurements": list(self.measurements),
            "machine": {
                "live": {
                    "cameraWireOffsetX": 0.0,
                    "cameraWireOffsetY": 0.0,
                    "rollerYCals": [1.0, 1.0, 1.0, 1.0],
                }
            },
            "layerState": {"layer": "V", "currentLineOffsetOverrides": {}},
        }

    def recordMeasurement(self, *, layer=None, capture_xy=True, capture_z=False):
        measurement = {
            "id": f"m{len(self.measurements) + 1}",
            "layer": layer or "V",
            "captureXY": bool(capture_xy),
            "captureZ": bool(capture_z),
        }
        self.measurements.append(measurement)
        return measurement

    def deleteMeasurement(self, measurement_id):
        self.measurements = [
            measurement
            for measurement in self.measurements
            if measurement["id"] != measurement_id
        ]
        return {"measurementId": measurement_id}

    def solveLayerZ(self, layer=None):
        return {"layer": layer or "V", "coefficients": [0.0, 0.0, 1.0]}

    def applyLayerZ(self, layer=None):
        return {"layer": layer or "V", "applied": True}

    def solveMachineXY(self, layer=None):
        return {"layer": layer or "V", "fitError": None}

    def cancelMachineXY(self, layer=None):
        return {"layer": layer or "V", "canceled": True}

    def killMachineXY(self, layer=None):
        return {"layer": layer or "V", "killed": True}

    def applyMachineXY(self, layer=None):
        return {"layer": layer or "V", "applied": True}

    def setLineOffsetOverride(self, layer, line_key, x_value, y_value):
        self.lastSetLineOffset = (layer, line_key, x_value, y_value)
        return {
            "ok": True,
            "data": {"layer": layer, "lineKey": line_key, "x": x_value, "y": y_value},
        }

    def deleteLineOffsetOverride(self, layer, line_key):
        self.lastDeletedLineOffset = (layer, line_key)
        return {"ok": True, "data": {"layer": layer, "lineKey": line_key}}


class DummyManualCalibration:
    def getState(self):
        return {"mode": "gx"}

    def setXBacklashCompensation(self, value):
        return {"ok": True, "data": {"xBacklashCompensationMm": value}}

    def setCornerOffset(self, offsetId, value):
        return {"ok": True, "data": {"offsetId": offsetId, "value": value}}

    def setTransferPause(self, enabled):
        return {"ok": True, "data": {"enabled": enabled}}

    def setIncludeLeadMode(self, enabled):
        return {"ok": True, "data": {"enabled": enabled}}

    def clearGXDraft(self):
        return {"ok": True}

    def generateRecipeFile(self):
        return {"ok": True, "data": {"generated": True}}


class DummySpool:
    def __init__(self):
        self.lastWire = None

    def setWire(self, value):
        self.lastWire = value
        return False


class DummyWorkspace:
    def __init__(self):
        self._gCodeHandler = type(
            "GCodeVars", (), {"transferLeft": 100.0, "transferRight": 200.0}
        )()
        self._calibrationFile = "V_Calibration.json"
        self.lastFindUvPinSegment = None
        self.lastJumpUvPinSegment = None

    def loadRecipe(self, layer, recipe, line):
        return {"layer": layer, "recipe": recipe, "line": line}

    def getCalibrationFile(self):
        return self._calibrationFile

    def getCalibrationFullPath(self):
        return None

    def findUvPinSegment(self, side, boardSide, boardNumber, pinNumber):
        self.lastFindUvPinSegment = (side, boardSide, boardNumber, pinNumber)
        return {
            "layer": "V",
            "side": side,
            "boardSide": boardSide,
            "boardNumber": boardNumber,
            "pinNumberOnBoard": pinNumber,
            "pinFamily": "PB",
            "pin": 40,
            "pinName": "PB40",
            "segmentSide": "B",
            "segmentStartLine": 12,
            "segmentStartLineNumber": 13,
            "matchedLine": 14,
            "matchedLineNumber": 15,
            "segmentEndLine": 16,
            "segmentEndLineNumber": 17,
            "pinRole": "start",
            "segmentLines": 3,
        }

    def jumpToUvPinSegment(self, side, boardSide, boardNumber, pinNumber):
        self.lastJumpUvPinSegment = (side, boardSide, boardNumber, pinNumber)
        result = self.findUvPinSegment(side, boardSide, boardNumber, pinNumber)
        result["jumpedToLine"] = result["segmentStartLine"]
        return result


class DummyProcess:
    def __init__(self):
        self.started = False
        self.stopped = False
        self.lastLine = None
        self.lastExecuted = None
        self.lastSeek = None
        self.lastVelocityScale = None
        self.lastAnchor = None
        self.queuedPreview = {"previewId": 7, "kind": "single"}
        self.queuedMotionUseMaxSpeed = False
        self.queuedPreviewContinued = False
        self.queuedPreviewCancelled = False
        self.controlStateMachine = DummyControlState()
        self.gCodeHandler = DummyGCodeHandler()
        self.vTemplateRecipe = DummyTemplateRecipe()
        self.uTemplateRecipe = DummyTemplateRecipe()
        self.manualCalibration = DummyManualCalibration()
        self.machineGeometryCalibration = DummyMachineGeometryCalibration()
        self.spool = DummySpool()
        self.workspace = DummyWorkspace()

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def step(self):
        return None

    def stopNextLine(self):
        return None

    def setG_CodeLine(self, line):
        self.lastLine = line
        return False

    def executeG_CodeLine(self, line):
        self.lastExecuted = line
        return None

    def jogXY(self, xVelocity, yVelocity, acceleration=None, deceleration=None):
        self.lastSeek = ("jogXY", xVelocity, yVelocity, acceleration, deceleration)
        return False

    def jogZ(self, velocity):
        self.lastSeek = ("jogZ", velocity)
        return False

    def manualSeekXY(
        self,
        xPosition=None,
        yPosition=None,
        velocity=None,
        acceleration=None,
        deceleration=None,
    ):
        self.lastSeek = (
            "seekXY",
            xPosition,
            yPosition,
            velocity,
            acceleration,
            deceleration,
        )
        return False

    def getRealXPosition(self):
        return 123.4

    def manualSeekZ(self, position, velocity=None):
        self.lastSeek = ("seekZ", position, velocity)
        return False

    def manualHeadPosition(self, position, velocity):
        self.lastSeek = ("head", position, velocity)
        return False

    def seekPin(self, pin, velocity):
        self.lastSeek = ("pin", pin, velocity)
        return False

    def setAnchorPoint(self, pinA, pinB=None):
        self.lastAnchor = (pinA, pinB)
        return False

    def acknowledgeError(self):
        return None

    def servoDisable(self):
        return None

    def eotRecover(self):
        return None

    def getRecipes(self):
        return ["V-layer.gc"]

    def getRecipeName(self):
        return "V-layer.gc"

    def getRecipeLayer(self):
        return "V"

    def getLayerCalibration(self, layer):
        return {
            "layer": str(layer).upper(),
            "activeLayer": "V",
            "calibrationFile": "V_Calibration.json",
            "source": "workspace",
            "pinDiameterMm": 1.0,
            "locations": {"B400": {"x": 1.0, "y": 2.0, "z": 3.0}},
        }

    def getLayerCalibrationJson(self, layer):
        content = '{\n  "layer": "V"\n}'
        return {
            "layer": str(layer).upper(),
            "activeLayer": "V",
            "calibrationFile": "V_Calibration.json",
            "source": "workspace",
            "contentHash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "content": content,
        }

    def getRecipePeriod(self):
        return 32

    def getWrapSeekLine(self, wrap):
        return wrap * 10

    def openRecipeInEditor(self, recipeFile=None):
        return recipeFile

    def openCalibrationInEditor(self):
        return "ok"

    def getWorkspaceState(self):
        return {"layer": "V", "recipe": "V-layer.gc"}

    def setG_CodeRunToLine(self, line):
        return line

    def setG_CodeVelocityScale(self, scaleFactor=1.0):
        self.lastVelocityScale = scaleFactor
        return scaleFactor

    def getQueuedMotionPreview(self):
        return self.queuedPreview

    def getQueuedMotionUseMaxSpeed(self):
        return self.queuedMotionUseMaxSpeed

    def setQueuedMotionUseMaxSpeed(self, enabled):
        self.queuedMotionUseMaxSpeed = bool(enabled)
        return self.queuedMotionUseMaxSpeed

    def continueQueuedMotionPreview(self):
        self.queuedPreviewContinued = True
        return True

    def cancelQueuedMotionPreview(self):
        self.queuedPreviewCancelled = True
        return True


class DummyPLCLogic:
    def move_latch(self):
        return None

    def latch(self):
        return None

    def latchHome(self):
        return None

    def latchUnlock(self):
        return None


class DummyRealPLC:
    pass


class DummySimPLC:
    def __init__(self):
        self.tags = {"STATE": 1, "MACHINE_SW_STAT[6]": 1}
        self.overrides = {}
        self.errorCode = 0

    def get_status(self):
        return {
            "mode": "SIM",
            "state": self.tags.get("STATE", 1),
            "errorCode": self.errorCode,
            "overrides": sorted(self.overrides.keys()),
        }

    def get_tag(self, name):
        return self.tags.get(name, 0)

    def set_tag(self, name, value, override=None):
        if override:
            self.overrides[name] = value
        else:
            self.overrides.pop(name, None)
            self.tags[name] = value
        return self.get_tag(name)

    def clear_override(self, name=None):
        if name is None:
            count = len(self.overrides)
            self.overrides = {}
            return {"cleared": count}

        cleared = 1 if name in self.overrides else 0
        self.overrides.pop(name, None)
        return {"cleared": cleared, "name": name}

    def inject_error(self, code=3003, state=None):
        self.errorCode = code
        self.tags["STATE"] = 10 if state is None else state
        return self.get_status()

    def clear_error(self):
        self.errorCode = 0
        self.tags["STATE"] = 1
        return self.get_status()


class DummyIO:
    def __init__(self, plc=None):
        self.plcLogic = DummyPLCLogic()
        self.plc = plc if plc is not None else DummyRealPLC()


class DummyConfiguration:
    def get(self, key):
        values = {
            "maxVelocity": "100",
            "maxAcceleration": "200",
            "maxDeceleration": "300",
        }
        return values.get(key, "")

    def set(self, key, value):
        pass

    def save(self):
        pass


class DummyLowLevelIO:
    @staticmethod
    def getTags():
        return ["tagA", "tagB"]


class DummyMachineCalibration:
    def __init__(self):
        self.zBack = 123.45
        self.headArmLength = 80.0
        self.headRollerRadius = 9.0
        self.headRollerGap = 24.0
        self.cameraWireOffsetX = 0.0
        self.cameraWireOffsetY = 0.0
        self.rollerArmCalibration = None

    def set(self, key, value):
        setattr(self, str(key), value)
        return {"key": key, "value": value}

    def save(self):
        return None


def build_registry_fixture(sim_plc=False):
    process = DummyProcess()
    io = DummyIO(plc=DummySimPLC() if sim_plc else DummyRealPLC())
    configuration = DummyConfiguration()
    log = DummyLog()
    machineCalibration = DummyMachineCalibration()
    registry = build_command_registry(
        process,
        io,
        configuration,
        DummyLowLevelIO,
        log,
        machineCalibration,
    )
    return registry, process, io, configuration, log, machineCalibration
