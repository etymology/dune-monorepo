###############################################################################
# Name: AnodePlaneArray.py
# Uses: Anode Plane Array (APA) management.
# Date: 2016-03-01
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

import os
import re

from dune_winder.library.hash import Hash
from dune_winder.recipes.recipe import Recipe
from dune_winder.machine.settings import Settings
from dune_winder.machine.layer_calibration import LayerCalibration
from .apa_base import APA_Base
from dune_winder.library.time_source import TimeSource
from dune_winder.library.log import Log
from dune_winder.core.g_code_handler import G_CodeHandler


class AnodePlaneArray(APA_Base):
  # There can only be a single working instance of an APA, and it must be
  # saved before loading or starting a new one.
  activeAPA = None

  # ---------------------------------------------------------------------
  def __init__(
    self,
    gCodeHandler: G_CodeHandler,
    apaDirectory: str,
    calibrationDirectory: str,
    recipeDirectory: str,
    recipeArchiveDirectory: str,
    name: str,
    log: Log,
    systemTime: TimeSource,
    createNew=False,
  ):
    """
    Constructor.

    Args:
      gCodeHandler: Instance of G_CodeHandler.
      apaDirectory: Directory APA data is stored.
      calibrationDirectory: Directory user-provided layer calibration files are stored.
      recipeDirectory: Directory recipes are stored.
      recipeArchiveDirectory: Directory recipes are archived.
      name: Name/serial number of APA.
      log: Instance of system log file.
      systemTime: Instance of TimeSource.
      createNew: True if this APA should be created should it not already exist.
    """

    APA_Base.__init__(self, apaDirectory, name, systemTime)
    self._calibrationDirectory = calibrationDirectory

    # If there was an APA previously active, save it.
    if AnodePlaneArray.activeAPA:
      AnodePlaneArray.activeAPA.close()

    AnodePlaneArray.activeAPA = self

    self._recipeDirectory = recipeDirectory
    self._recipeArchiveDirectory = recipeArchiveDirectory
    self._log = log
    self._gCodeHandler = gCodeHandler
    self._systemTime = systemTime
    self._startTime = systemTime.get()

    # Uninitialized data.
    self._recipe = None
    self._recipeSignature = None
    self._recipePeriod = None
    self._calibration = None
    self._calibrationSignature = None

    self._log.attach(self.getPath() + AnodePlaneArray.LOG_FILE)

    if createNew:
      self.save()
    else:
      self.load()

  # ---------------------------------------------------------------------
  def _getG_CodeLogName(self, layer):
    """
    Get the name of the G-Code log for this layer.

    Args:
      layer: Name of the layer.
    """
    return self.getPath() + "/Layer" + layer + Settings.G_CODE_LOG_FILE

  # ---------------------------------------------------------------------
  def closeLoadedRecipe(self):
    """
    Close the open recipe and reset internals to blank APA.
    """
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

  # ---------------------------------------------------------------------
  def loadRecipe(self, layer=None, recipeFile=None, startingLine=-1):
    """
    Load a recipe file into G_CodeHandler.

    Args:
      layer: The current working layer.
      recipeFile: File name of recipe to load.
      startingLine: What line to start from in recipe.

    Returns:
      True if there was an error, False if not.
    """
    isError = False

    # If no explicit line given, restore the last saved line for this recipe.
    if startingLine == -1 and recipeFile is not None and recipeFile in self._lineHistory:
      startingLine = self._lineHistory[recipeFile]

    if layer is not None:
      self._layer = layer
    self._calibrationFile = self._layer + "_Calibration.xml"
    if self._lineNumber is not None:
      self._lineNumber = startingLine
    # If there is a calibration file, load it.
    if self._calibrationFile:
      self._loadCalibrationFromDisk()

    else:
      # If there is no calibration, use none.
      self._useCalibration(None)

    if recipeFile is not None:
      self._recipeFile = recipeFile

    if startingLine is not None:
      self._lineNumber = startingLine

    if self._lineNumber is None:
      self._lineNumber = -1

    if not isError and self._recipeFile is not None:
      self._recipe = Recipe(
        self._recipeDirectory + "/" + self._recipeFile, self._recipeArchiveDirectory
      )
      self._recipePeriod = self._recipe.getDetectedPeriod()
      self._gCodeHandler.loadG_Code(self._recipe.getLines(), self._calibration)
      self._recipeSignature = self._calculateRecipeSignature()

      # Assign a G-Code log.
      gCodeLogName = self._getG_CodeLogName(self._layer)
      self._gCodeHandler.setG_CodeLog(gCodeLogName)

    if not isError:
      isError |= self._gCodeHandler.setLine(self._lineNumber)
      if isError:
        error = "Invalid line number."

    if not isError:
      self._gCodeHandler.setLineChangeCallback(self.save)
      recipeFullPath = self._recipeDirectory + "/" + self._recipeFile
      self._log.add(
        self.__class__.__name__,
        "GCODE",
        "Loaded G-Code file "
        + recipeFullPath
        + ", active layer "
        + self._layer
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

  # ---------------------------------------------------------------------
  def load(self):
    """
    Load

    Returns:
      True if there was an error, False if not.
    """

    # Log message about AHA change.
    self._log.add(
      self.__class__.__name__, "LOAD", "Loaded APA called " + self._name, [self._name]
    )

    APA_Base.load(self)

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
      self.loadRecipe(self._layer, recipeFile, self._lineNumber)
      self._gCodeHandler.setInitialLocation(self._x, self._y, self._headLocation)

  # ---------------------------------------------------------------------
  def getCalibrationFile(self):
    """
    Get the file name of the calibration file currently in use.

    Returns:
      File name of the calibration file currently in use.  None if no calibration
      file has yet been assigned.
    """
    return self._calibrationFile

  # ---------------------------------------------------------------------
  def getRecipePeriod(self):
    """
    Get the cached repeating line period of the loaded recipe.

    Returns:
      Integer recipe period in lines, or None if no recipe is loaded or no
      stable repetition was detected when the recipe was loaded.
    """
    return getattr(self, "_recipePeriod", None)

  # ---------------------------------------------------------------------
  def getWrapSeekLine(self, wrap):
    """
    Get the line index to seek to for the requested wrap number.

    Wrap seeks are anchored to explicit wrap comments in the loaded recipe.
    For wrap ``n``, this finds the first line containing ``(n,1)`` and then
    jumps to the latest earlier line containing ``HEAD RESTART``. This matches
    the recipe's intended restart points more closely than period-based
    estimates. If wrap 1 has no prior restart anchor, the seek begins from the
    true start of the file so setup moves are replayed.

    Args:
      wrap: Requested wrap number (1-based).

    Returns:
      Zero-based G-Code seek line for Process.setG_CodeLine(), or None if the
      active recipe cannot provide a valid wrap-start target.
    """
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

  # ---------------------------------------------------------------------
  def _getWrapStartLine(self, wrap):
    """
    Find the first recipe line containing the explicit ``(wrap,1)`` marker.

    Args:
      wrap: Requested wrap number (1-based).

    Returns:
      1-based recipe line number, or None if the marker is not present.
    """
    if self._recipe is None:
      return None

    expression = re.compile(r"\(\s*" + str(int(wrap)) + r"\s*,\s*1\b", re.IGNORECASE)
    for index, line in enumerate(self._recipe.getLines(), start=1):
      if expression.search(line):
        return index

    return None

  # ---------------------------------------------------------------------
  def _getNearestPriorHeadRestartLine(self, targetLine):
    """
    Find the most recent HEAD RESTART line at or before the target.

    Args:
      targetLine: 1-based recipe line number target.

    Returns:
      1-based line number of the latest HEAD RESTART marker not after the
      target. Returns None if no such marker exists.
    """
    if self._recipe is None:
      return None

    priorLine = None
    for index, line in enumerate(self._recipe.getLines()):
      if 'HEAD RESTART' not in line.upper():
        continue

      lineNumber = index + 1
      if lineNumber <= targetLine:
        priorLine = lineNumber
      else:
        break

    return priorLine

  # ---------------------------------------------------------------------
  def _getCalibrationFullPath(self):
    """
    Get the full path to the active calibration XML file.

    Returns:
      Full path to calibration file, or None when no file is selected.
    """
    if not self._calibrationFile:
      return None

    return self._calibrationDirectory + "/" + self._calibrationFile

  # ---------------------------------------------------------------------
  def _getRecipeFullPath(self):
    """
    Get the full path to the active recipe file.

    Returns:
      Full path to recipe file, or None when no file is selected.
    """
    if not self._recipeFile:
      return None

    return self._recipeDirectory + "/" + self._recipeFile

  # ---------------------------------------------------------------------
  def _calculateRecipeSignature(self):
    """
    Calculate a file-content signature for the active recipe.

    Returns:
      Hash string of the file contents, or None if the file does not exist.
    """
    recipeFullPath = self._getRecipeFullPath()
    if recipeFullPath is None or not os.path.isfile(recipeFullPath):
      return None

    hashValue = Hash()
    with open(recipeFullPath, "rb") as inputFile:
      hashValue += inputFile.read()

    return str(hashValue)

  # ---------------------------------------------------------------------
  def _calculateCalibrationSignature(self):
    """
    Calculate a file-content signature for the active calibration XML.

    Returns:
      Hash string of the file contents, or None if the file does not exist.
    """
    calibFullPath = self._getCalibrationFullPath()
    if calibFullPath is None or not os.path.isfile(calibFullPath):
      return None

    with open(calibFullPath) as inputFile:
      lines = inputFile.read()

    calibration = self._calibration
    if calibration is None:
      calibration = LayerCalibration()

    return calibration._calculateStringHash(lines)

  # ---------------------------------------------------------------------
  def _useCalibration(self, calibration, calibrationFile=None):
    """
    Make the specified calibration the active runtime calibration.

    Args:
      calibration: Instance of LayerCalibration, or None.
      calibrationFile: Optional calibration file name override.
    """
    if calibrationFile is not None:
      self._calibrationFile = calibrationFile

    self._calibration = calibration
    self._gCodeHandler.useLayerCalibration(calibration)
    self._calibrationSignature = self._calculateCalibrationSignature()

  # ---------------------------------------------------------------------
  def _loadCalibrationFromDisk(self, reloadReason=None):
    """
    Load the current calibration file and apply it to runtime.

    Args:
      reloadReason: Optional human-readable reason for reload logging.
    """
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

  # ---------------------------------------------------------------------
  def refreshCalibrationIfChanged(self):
    """
    Reload calibration from disk when the XML file contents have changed.
    """
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
      self._loadCalibrationFromDisk("the calibration XML changed on disk")

  # ---------------------------------------------------------------------
  def refreshRecipeIfChanged(self):
    """
    Reload the active recipe from disk when the G-Code file contents change.
    """
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

  # ---------------------------------------------------------------------
  def setupBlankCalibration(self, layer, geometry):
    """
    Setup a blank calibration file for layer.
    """
    self._calibration = LayerCalibration()
    self._calibration.zFront = geometry.mostlyRetract
    self._calibration.zBack = geometry.mostlyExtend
    self._calibrationFile = layer + "_Calibration.xml"
    self._calibration.save(self._calibrationDirectory, self._calibrationFile)
    self._useCalibration(self._calibration)

  # ---------------------------------------------------------------------
  def setStage(self, stage, message="<unspecified>"):
    """
    Set the APA progress stage.

    Args:
      stage: Integer number (table in APA_Base.Stages) of APA progress.
      message: Message/reason for changing to new stage.
    """

    # Note in the log the stage change.
    self._log.add(
      self.__class__.__name__,
      "STAGE",
      "APA stage change from "
      + str(self._stage)
      + " to "
      + str(stage)
      + ".  Reason: "
      + message,
      [self._stage, stage, message],
    )
    self._stage = stage

  # ---------------------------------------------------------------------
  def save(self):
    """
    Save current APA state to file.
    """
    self._lineNumber = self._gCodeHandler.getLine()
    if self._recipeFile is not None and self._lineNumber is not None:
      self._lineHistory[self._recipeFile] = self._lineNumber
    APA_Base.save(self)

  # ---------------------------------------------------------------------
  def close(self):
    """
    Close an APA.  Call during shutdown sequence.  Called internally when new
    APA is loaded.
    """

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
      "Closing APA "
      + self._name
      + ", "
      + str(recipeFullPath)
      + ":"
      + str(self._lineNumber)
      + " after "
      + deltaString,
      [self._name, recipeFullPath, self._lineNumber, elapsedTime],
    )
    self._log.detach(self.getPath() + AnodePlaneArray.LOG_FILE)
    AnodePlaneArray.activeAPA = None


# end class


if __name__ == "__main__":
  from dune_winder.library.log import Log
  from dune_winder.library.system_time import SystemTime

  systemTime = SystemTime()
  log = Log(systemTime)
  log.add("Main", "START", "Control system starts.")

  from dune_winder.machine.g_code_handler_base import G_CodeHandlerBase

  gCodeHandler = G_CodeHandlerBase()

  apa = AnodePlaneArray(gCodeHandler, ".", ".", ".", ".", "TestAPA", log, True)

  apa.save()
  apa.load()
