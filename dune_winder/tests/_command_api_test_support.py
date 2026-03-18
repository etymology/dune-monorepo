from dune_winder.api.commands import build_command_registry


class DummyLog:
  def __init__(self):
    self.entries = []

  def add(self, *args):
    self.entries.append(args)

  def getAll(self, numberOfLines=-1):
    return ["entry-a", "entry-b"][: max(0, numberOfLines)] if numberOfLines >= 0 else ["entry-a", "entry-b"]


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
  def getState(self):
    return {"layer": "V"}

  def setOffset(self, offsetId, value):
    return {"ok": True, "data": {"offsetId": offsetId, "value": value}}

  def setTransferPause(self, enabled):
    return {"ok": True, "data": {"enabled": enabled}}

  def setIncludeLeadMode(self, enabled):
    return {"ok": True, "data": {"enabled": enabled}}

  def resetDraft(self, markDirty=True):
    return {"ok": True, "data": {"markDirty": markDirty}}

  def generateRecipeFile(self):
    return {"ok": True, "data": {"generated": True}}


class DummyManualCalibration:
  def getState(self):
    return {"mode": "gx"}

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
    self._gCodeHandler = type("GCodeVars", (), {"transferLeft": 100.0, "transferRight": 200.0})()

  def loadRecipe(self, layer, recipe, line):
    return {"layer": layer, "recipe": recipe, "line": line}


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

  def manualSeekXY(self, xPosition=None, yPosition=None, velocity=None, acceleration=None, deceleration=None):
    self.lastSeek = ("seekXY", xPosition, yPosition, velocity, acceleration, deceleration)
    return False

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

  def getCameraImageURL(self):
    return "/camera_image"

  def acknowledgeError(self):
    return None

  def servoDisable(self):
    return None

  def getRecipes(self):
    return ["V-layer.gc"]

  def getRecipeName(self):
    return "V-layer.gc"

  def getRecipeLayer(self):
    return "V"

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
  zBack = 123.45


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

