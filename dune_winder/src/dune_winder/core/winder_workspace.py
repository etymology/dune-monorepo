###############################################################################
# Name: winder_workspace.py
# Uses: Active runtime workspace for the winder interface.
# Date: 2026-03-14
###############################################################################

import json
import os
import pathlib
import re
import tempfile
from typing import Optional

from dune_winder.gcode.handler import GCodeHandler
from dune_winder.library.hash import Hash
from dune_winder.library.log import Log
from dune_winder.library.time_source import TimeSource
from dune_winder.machine.calibration.layer import LayerCalibration
from dune_winder.machine.settings import Settings
from dune_winder.recipes.recipe import Recipe
from dune_winder.recipes.u_template_gcode import write_u_template_file
from dune_winder.recipes.v_template_gcode import write_v_template_file
from dune_winder.recipes.xg_template_gcode import write_xg_template_file


class WinderWorkspace:
  FILE_NAME = "state.json"
  LOG_FILE = "workspace_history.csv"
  SERIALIZED_VARIABLES = [
    "_calibrationFile",
    "_recipeFile",
    "_lineNumber",
    "_lineHistory",
    "_layer",
    "_creationDate",
    "_lastModifyDate",
    "_loadedTime",
    "_windTime",
    "_x",
    "_y",
    "_headLocation",
  ]

  activeWorkspace = None

  @classmethod
  def _defaultState(cls):
    return {
      "_calibrationFile": None,
      "_recipeFile": None,
      "_lineNumber": None,
      "_lineHistory": {},
      "_layer": None,
      "_creationDate": "0",
      "_lastModifyDate": "0",
      "_loadedTime": 0,
      "_windTime": 0,
      "_x": None,
      "_y": None,
      "_headLocation": None,
    }

  @classmethod
  def _readXmlState(cls, xmlPath: pathlib.Path):
    import xml.dom.minidom

    state = cls._defaultState()
    doc = xml.dom.minidom.parse(str(xmlPath))
    root = doc.documentElement.firstChild
    while root and root.nodeType != root.ELEMENT_NODE:
      root = root.nextSibling
    if root is None:
      return state

    for node in root.childNodes:
      if node.nodeType != node.ELEMENT_NODE:
        continue
      name = node.getAttribute("name")
      if name not in cls.SERIALIZED_VARIABLES:
        continue
      tag = node.nodeName
      if tag == "NoneType" or not node.firstChild:
        state[name] = None
      elif tag == "float":
        state[name] = float(node.firstChild.nodeValue)
      elif tag == "int":
        state[name] = int(node.firstChild.nodeValue)
      elif tag == "str":
        state[name] = str(node.firstChild.nodeValue)
      elif tag == "dict":
        value = {}
        for child in node.childNodes:
          if child.nodeType != child.ELEMENT_NODE:
            continue
          key = child.getAttribute("name")
          if child.firstChild:
            value[key] = child.firstChild.nodeValue
        state[name] = value

    return state

  @classmethod
  def readState(cls, workspaceDirectory: str):
    state = cls._defaultState()
    path = pathlib.Path(workspaceDirectory.rstrip("/\\")) / cls.FILE_NAME
    if path.exists():
      with path.open() as inputFile:
        loaded = json.load(inputFile)
      for var in cls.SERIALIZED_VARIABLES:
        if var in loaded:
          state[var] = loaded[var]
      return state

    xmlPath = path.with_name("state.xml")
    if xmlPath.exists():
      return cls._readXmlState(xmlPath)

    return state

  def __init__(
    self,
    gCodeHandler: GCodeHandler,
    workspaceDirectory: str,
    calibrationDirectory: str,
    recipeDirectory: str,
    recipeArchiveDirectory: str,
    log: Log,
    systemTime: TimeSource,
    createNew=False,
  ):
    self._workspaceDirectory = workspaceDirectory
    self._calibrationDirectory = calibrationDirectory
    self._recipeDirectory = recipeDirectory
    self._recipeArchiveDirectory = recipeArchiveDirectory
    self._log = log
    self._gCodeHandler = gCodeHandler
    self._systemTime = systemTime
    self._startTime = systemTime.get()

    self._recipe = None
    self._recipeSignature = None
    self._recipePeriod = None
    self._calibration = None
    self._calibrationSignature = None
    self._z = None

    for var, value in self._defaultState().items():
      setattr(self, var, value)

    now = self._systemTime.get() if self._systemTime else 0
    self._creationDate = str(now)
    self._lastModifyDate = self._creationDate
    self._loadStart = now

    if WinderWorkspace.activeWorkspace:
      WinderWorkspace.activeWorkspace.close()
    WinderWorkspace.activeWorkspace = self

    self._log.attach(self.getPath() + WinderWorkspace.LOG_FILE)

    if createNew:
      self._saveState()
    else:
      self.load()

  def getPath(self):
    return self._workspaceDirectory.rstrip("/\\") + "/"

  def getLayer(self):
    return self._layer

  def getRecipe(self):
    return self._recipeFile or ""

  def addWindTime(self, elapsedTime):
    self._windTime += elapsedTime

  def toDictionary(self):
    return {var: getattr(self, var) for var in self.SERIALIZED_VARIABLES}

  def setLocation(self, x, y, headLocation):
    self._x = x
    self._y = y
    self._headLocation = headLocation

  def _loadState(self):
    if self._systemTime:
      self._loadStart = self._systemTime.get()

    path = pathlib.Path(self.getPath()) / self.FILE_NAME
    jsonExists = path.exists()
    state = self.readState(self.getPath())
    for var in self.SERIALIZED_VARIABLES:
      setattr(self, var, state[var])

    if not jsonExists and path.with_name("state.xml").exists():
      self._saveState()

  def _saveState(self):
    if self._systemTime:
      now = self._systemTime.get()
      self._lastModifyDate = str(now)
      self._loadedTime += self._systemTime.getDelta(self._loadStart, now)

    data = {var: getattr(self, var) for var in self.SERIALIZED_VARIABLES}
    content = json.dumps(data, indent=2)

    path = pathlib.Path(self.getPath()) / self.FILE_NAME
    fd, tmp = tempfile.mkstemp(dir=str(path.parent))
    try:
      with os.fdopen(fd, "w") as outputFile:
        outputFile.write(content)
      os.replace(tmp, str(path))
    except Exception:
      try:
        os.unlink(tmp)
      except OSError:
        pass
      raise

  def _getG_CodeLogName(self, layer):
    if layer is None:
      return None
    return self.getPath() + "/Layer" + layer + Settings.G_CODE_LOG_FILE

  def _inferLayerFromRecipeFile(self, recipeFile):
    if not recipeFile:
      return None

    match = re.match(r"^\s*([A-Za-z])(?:[-_]|$)", recipeFile)
    if not match:
      return None

    return match.group(1).upper()

  def closeLoadedRecipe(self):
    if self._calibrationFile:
      self._calibrationFile = None
      self._calibration = None
      self._calibrationSignature = None
      self._gCodeHandler.useLayerCalibration(None)

    if self._recipeFile:
      self._recipeFile = None
      self._recipe = None
      self._recipeSignature = None
      self._recipePeriod = None
      self._gCodeHandler.closeG_Code()

    self._layer = None
    self._lineNumber = None

  _LAYER_FILE_WRITERS = {
    "V": lambda path, archive: write_v_template_file(path, archive_directory=archive),
    "U": lambda path, archive: write_u_template_file(path, archive_directory=archive),
    "X": lambda path, archive: write_xg_template_file("X", output_path=path, archive_directory=archive),
    "G": lambda path, archive: write_xg_template_file("G", output_path=path, archive_directory=archive),
  }

  def _generateDefaultRecipeIfMissing(self, recipeFile):
    """Generate a default recipe file with zero offsets if it doesn't exist."""
    filePath = self._recipeDirectory + "/" + recipeFile
    if os.path.isfile(filePath):
      return

    match = re.match(r"^([A-Za-z])-layer\.gc$", recipeFile, re.IGNORECASE)
    if not match:
      return

    layer = match.group(1).upper()
    writer = self._LAYER_FILE_WRITERS.get(layer)
    if writer is None:
      return

    os.makedirs(self._recipeDirectory, exist_ok=True)
    writer(filePath, self._recipeArchiveDirectory)
    self._log.add(
      self.__class__.__name__,
      "GCODE",
      "Generated default recipe file " + filePath,
      [layer, filePath],
    )

  def loadRecipe(self, layer=None, recipeFile=None, startingLine=-1):
    isError = False

    if startingLine == -1 and recipeFile is not None and recipeFile in self._lineHistory:
      startingLine = self._lineHistory[recipeFile]

    if layer is not None:
      self._layer = layer
    self._calibrationFile = self._layer + "_Calibration.json" if self._layer is not None else None
    if self._lineNumber is not None:
      self._lineNumber = startingLine
    if self._calibrationFile:
      self._loadCalibrationFromDisk()
    else:
      self._useCalibration(None)

    if recipeFile is not None:
      self._recipeFile = recipeFile

    if startingLine is not None:
      self._lineNumber = startingLine

    if self._lineNumber is None:
      self._lineNumber = -1

    if not isError and self._recipeFile is not None:
      self._generateDefaultRecipeIfMissing(self._recipeFile)
      self._recipe = Recipe(
        self._recipeDirectory + "/" + self._recipeFile, self._recipeArchiveDirectory
      )
      self._recipePeriod = self._recipe.getDetectedPeriod()
      self._gCodeHandler.loadG_Code(self._recipe.getLines(), self._calibration)
      self._recipeSignature = self._calculateRecipeSignature()

      gCodeLogName = self._getG_CodeLogName(self._layer)
      self._gCodeHandler.setG_CodeLog(gCodeLogName)

    if not isError:
      isError |= self._gCodeHandler.setLine(self._lineNumber)
      if isError:
        error = "Invalid line number."

    if not isError:
      self._gCodeHandler.setLineChangeCallback(self.save)
      recipeFullPath = self._recipeDirectory + "/" + self._recipeFile
      activeLayer = self._layer if self._layer is not None else "<unset>"
      self._log.add(
        self.__class__.__name__,
        "GCODE",
        "Loaded G-Code file "
        + recipeFullPath
        + ", active layer "
        + activeLayer
        + ", starting at line "
        + str(self._lineNumber),
        [
          recipeFullPath,
          self._layer,
          self._lineNumber,
          self._recipe.getDescription(),
          self._recipe.getID(),
        ],
      )
    else:
      self._log.add(
        self.__class__.__name__,
        "GCODE",
        "Failed to loaded G-Code file "
        + self._recipeDirectory + "/" + self._recipeFile
        + ", starting at line "
        + str(self._lineNumber),
        [error, self._recipeDirectory + "/" + self._recipeFile, self._lineNumber],
      )

    return isError

  def load(self):
    self._log.add(self.__class__.__name__, "LOAD", "Loaded winder workspace.", [])

    self._loadState()

    recipeFile = self._recipeFile
    if recipeFile is None or not os.path.isfile(self._recipeDirectory + "/" + recipeFile):
      gcFiles = sorted(f for f in os.listdir(self._recipeDirectory) if f.endswith(".gc"))
      recipeFile = gcFiles[0] if gcFiles else None
      if recipeFile:
        self._log.add(
          self.__class__.__name__,
          "LOAD",
          "Recipe file missing or not set; defaulting to " + self._recipeDirectory + "/" + recipeFile,
          [self._recipeFile, self._recipeDirectory + "/" + recipeFile],
        )

    if recipeFile is not None:
      if self._layer is None:
        self._layer = self._inferLayerFromRecipeFile(recipeFile)
      self.loadRecipe(self._layer, recipeFile, self._lineNumber)
      self._gCodeHandler.setInitialLocation(self._x, self._y, self._headLocation)

  def getCalibrationFile(self):
    return self._calibrationFile

  def getCalibrationFullPath(self):
    return self._getCalibrationFullPath()

  def getRecipePeriod(self):
    return getattr(self, "_recipePeriod", None)

  def getWrapSeekLine(self, wrap):
    if self._recipe is None:
      return None

    try:
      wrap = int(wrap)
    except (TypeError, ValueError):
      return None

    if wrap < 1:
      return None

    lines = self._recipe.getLines()
    if len(lines) == 0:
      return None

    wrapStartLine = self._getWrapStartLine(wrap)
    if wrapStartLine is None:
      return None

    targetLine = self._getNearestPriorHeadRestartLine(wrapStartLine - 1)
    if targetLine is None:
      if wrap == 1:
        return -1
      targetLine = wrapStartLine

    targetLine = max(1, min(targetLine, len(lines)))
    return targetLine - 2

  def _getWrapStartLine(self, wrap):
    if self._recipe is None:
      return None

    expression = re.compile(r"\(\s*" + str(int(wrap)) + r"\s*,\s*1\b", re.IGNORECASE)
    for index, line in enumerate(self._recipe.getLines(), start=1):
      if expression.search(line):
        return index

    return None

  def _getNearestPriorHeadRestartLine(self, targetLine):
    if self._recipe is None:
      return None

    priorLine = None
    for index, line in enumerate(self._recipe.getLines()):
      if "HEAD RESTART" not in line.upper():
        continue

      lineNumber = index + 1
      if lineNumber <= targetLine:
        priorLine = lineNumber
      else:
        break

    return priorLine

  def _getCalibrationFullPath(self):
    if not self._calibrationFile:
      return None

    jsonName = pathlib.Path(self._calibrationFile).with_suffix(".json").name
    jsonPath = os.path.join(self._calibrationDirectory, jsonName)
    if os.path.isfile(jsonPath):
      return jsonPath

    return os.path.join(self._calibrationDirectory, self._calibrationFile)

  def _getRecipeFullPath(self):
    if not self._recipeFile:
      return None

    return self._recipeDirectory + "/" + self._recipeFile

  def _calculateRecipeSignature(self):
    recipeFullPath = self._getRecipeFullPath()
    if recipeFullPath is None or not os.path.isfile(recipeFullPath):
      return None

    hashValue = Hash()
    with open(recipeFullPath, "rb") as inputFile:
      hashValue += inputFile.read()

    return str(hashValue)

  def _calculateCalibrationSignature(self):
    calibFullPath = self._getCalibrationFullPath()
    if calibFullPath is None or not os.path.isfile(calibFullPath):
      return None

    with open(calibFullPath) as inputFile:
      content = inputFile.read()

    try:
      data = json.loads(content)
      data.pop("hashValue", None)
      canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    except json.JSONDecodeError:
      canonical = content

    return Hash.singleLine(canonical)

  def _useCalibration(self, calibration, calibrationFile=None):
    if calibrationFile is not None:
      self._calibrationFile = calibrationFile

    self._calibration = calibration
    self._gCodeHandler.useLayerCalibration(calibration)
    self._calibrationSignature = self._calculateCalibrationSignature()

  def _loadCalibrationFromDisk(self, reloadReason=None):
    archivePath = self.getPath() + "/Calibration"
    calibration = LayerCalibration(archivePath=archivePath)
    calibFullPath = self._getCalibrationFullPath()

    try:
      calibration.load(self._calibrationDirectory, self._calibrationFile)
    except LayerCalibration.Error as exception:
      errorString = (
        "Invalid calibration hash for "
        + calibFullPath
        + " because "
        + str(exception)
        + "."
      )
      errorData = [calibFullPath] + exception.data

      self._log.add(
        self.__class__.__name__, "LOAD", errorString + " Reloading.", errorData
      )

      calibration.load(
        self._calibrationDirectory, self._calibrationFile, exceptionForMismatch=False
      )

    self._useCalibration(calibration)

    message = "Loaded calibration file " + calibFullPath + "."
    if reloadReason is not None:
      message = "Reloaded calibration file " + calibFullPath + " because " + reloadReason + "."

    self._log.add(
      self.__class__.__name__,
      "LOAD",
      message,
      [calibFullPath, self._calibration.hashValue, self._calibrationSignature],
    )

  def refreshCalibrationIfChanged(self):
    if not self._calibrationFile:
      return

    currentSignature = self._calculateCalibrationSignature()
    if currentSignature is None:
      return

    if self._calibration is None:
      self._loadCalibrationFromDisk("no calibration was active in the G-Code system")
      return

    if self._calibrationSignature != currentSignature:
      calibFullPath = self._getCalibrationFullPath()
      self._log.add(
        self.__class__.__name__,
        "CALIBRATION_CHANGE",
        "Detected calibration file change for " + calibFullPath + ".",
        [calibFullPath, self._calibrationSignature, currentSignature],
      )
      self._loadCalibrationFromDisk("the calibration JSON changed on disk")

  def refreshRecipeIfChanged(self):
    if not self._recipeFile:
      return

    recipeFullPath = self._getRecipeFullPath()
    currentSignature = self._calculateRecipeSignature()
    if currentSignature is None:
      raise Exception("Active G-Code file is missing: " + str(recipeFullPath))

    if self._recipe is None:
      self._recipe = Recipe(recipeFullPath, self._recipeArchiveDirectory)
      self._recipePeriod = self._recipe.getDetectedPeriod()
      self._gCodeHandler.reloadG_Code(self._recipe.getLines())
      self._recipeSignature = self._calculateRecipeSignature()
      return

    if self._recipeSignature != currentSignature:
      self._log.add(
        self.__class__.__name__,
        "GCODE_CHANGE",
        "Detected G-Code file change for " + recipeFullPath + ".",
        [recipeFullPath, self._recipeSignature, currentSignature],
      )

      reloadedRecipe = Recipe(recipeFullPath, self._recipeArchiveDirectory)
      try:
        self._gCodeHandler.reloadG_Code(reloadedRecipe.getLines())
      except ValueError as exception:
        raise Exception(
          "Updated G-Code file no longer contains the active execution line."
        ) from exception

      self._recipe = reloadedRecipe
      self._recipePeriod = self._recipe.getDetectedPeriod()
      self._recipeSignature = self._calculateRecipeSignature()

      self._log.add(
        self.__class__.__name__,
        "GCODE_RELOAD",
        "Reloaded G-Code file " + recipeFullPath + " because the file changed on disk.",
        [recipeFullPath, self._recipe.getID(), self._recipeSignature],
      )

  def setupBlankCalibration(self, layer, geometry):
    self._calibration = LayerCalibration()
    self._calibration.zFront = geometry.mostlyRetract
    self._calibration.zBack = geometry.mostlyExtend
    self._calibrationFile = layer + "_Calibration.json"
    self._calibration.save(self._calibrationDirectory, self._calibrationFile)
    self._useCalibration(self._calibration)

  def save(self):
    self._lineNumber = self._gCodeHandler.getLine()
    if self._recipeFile is not None and self._lineNumber is not None:
      self._lineHistory[self._recipeFile] = self._lineNumber
    self._saveState()

  def close(self):
    self.setLocation(
      self._gCodeHandler._x, self._gCodeHandler._y, self._gCodeHandler._headPosition
    )

    self._gCodeHandler.setLineChangeCallback(None)
    self._gCodeHandler.closeG_CodeLog()
    self.save()

    elapsedTime = self._systemTime.getDelta(self._startTime)
    deltaString = self._systemTime.getElapsedString(elapsedTime)

    recipeFullPath = (self._recipeDirectory + "/" + self._recipeFile) if self._recipeFile else None
    self._log.add(
      self.__class__.__name__,
      "CLOSE",
      "Closing workspace "
      + str(recipeFullPath)
      + ":"
      + str(self._lineNumber)
      + " after "
      + deltaString,
      [recipeFullPath, self._lineNumber, elapsedTime],
    )
    self._log.detach(self.getPath() + WinderWorkspace.LOG_FILE)
    WinderWorkspace.activeWorkspace = None
