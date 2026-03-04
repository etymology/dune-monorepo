###############################################################################
# Name: APA_Base.py
# Uses: Anode Plane Array (APA) base.
# Date: 2016-05-26
# Author(s):
#   Andrew Que <aque@bb7.com>
# Notes:
#   Contains just the data portion of the APA, but no process control.
###############################################################################

import os.path

from dune_winder.library.Serializable import Serializable
from dune_winder.library.TimeSource import TimeSource
from typing import Optional


class APA_Base(Serializable):
  # File name of the APA state (this object) on disk.
  FILE_NAME = "state.xml"
  LOG_FILE = "apa_history.csv"

  class Stages:
    # No actions have yet been done.
    UNINITIALIZED = 0

    # Stages for each half of each layer.
    LAYER_X_FIRST = 1
    LAYER_X_SECOND = 2
    LAYER_V_FIRST = 3
    LAYER_V_SECOND = 4
    LAYER_U_FIRST = 5
    LAYER_U_SECOND = 6
    LAYER_G_FIRST = 7
    LAYER_G_SECOND = 8

    # Stage needing sign-off.
    SIGN_OFF = 9

    # APA is complete.
    COMPLETE = 10

  # end class

  class Side:
    NONE = -1
    FRONT = 0
    BACK = 1

  # end class

  # Look-up table for what APA side faces the machine front.
  STAGE_SIDE = [
    Side.NONE,  # UNINITIALIZED
    Side.FRONT,  # LAYER_X_FIRST
    Side.BACK,  # LAYER_X_SECOND
    Side.FRONT,  # LAYER_V_FIRST
    Side.BACK,  # LAYER_V_SECOND
    Side.FRONT,  # LAYER_U_FIRST
    Side.BACK,  # LAYER_U_SECOND
    Side.FRONT,  # LAYER_G_FIRST
    Side.BACK,  # LAYER_G_SECOND
    Side.NONE,  # SIGN_OFF
    Side.NONE,  # COMPLETE
  ]

  # Items saved to disk.
  SERIALIZED_VARIABLES = [
    "_name",
    "_calibrationFile",
    "_recipeFile",
    "_lineNumber",
    "_lineHistory",
    "_layer",
    "_stage",
    "_creationDate",
    "_lastModifyDate",
    "_loadedTime",
    "_windTime",
    "_x",
    "_y",
    "_headLocation",
  ]

  # ---------------------------------------------------------------------
  @staticmethod
  def create(apaDirectory, name):
    """
    Create and return a new APA_Base instance.

    Args:
      apaDirectory: Directory APA data is stored.
      name: Name/serial number of APA.
    """

    # Create directory if it doesn't exist.
    if not os.path.exists(apaDirectory):
      os.makedirs(apaDirectory)

    # Create instance and save it.
    apa = APA_Base(apaDirectory, name)
    apa.save()

    return apa

  # ---------------------------------------------------------------------
  def __init__(
    self,
    apaDirectory=None,
    name: Optional[str] = None,
    systemTime: Optional[TimeSource] = None,
  ):
    """
    Constructor.

    Args:
      apaDirectory: Directory APA data is stored.
      name: Name/serial number of APA.
      systemTime: Instance of TimeSource.
    """

    Serializable.__init__(self, includeOnly=APA_Base.SERIALIZED_VARIABLES)

    self._apaDirectory = apaDirectory
    self._name = name

    # Tracking of what stage this APA is.
    self._stage = APA_Base.Stages.UNINITIALIZED

    # Uninitialized data.
    self._lineNumber = None
    self._lineHistory = {}
    self._recipeFile = None
    self._layer = None
    self._calibrationFile = None
    self._systemTime = systemTime
    self._x = None
    self._y = None
    self._z = None
    self._headLocation = None

    if self._systemTime:
      now = self._systemTime.get()
    else:
      now = 0

    self._creationDate = str(now)
    self._lastModifyDate = self._creationDate
    self._loadedTime = 0
    self._windTime = 0
    self._loadStart = now

  # ---------------------------------------------------------------------
  def getPath(self):
    """
    Get the path for all files related to this APA.
    """
    return self._apaDirectory.rstrip("/\\") + "/"

  # ---------------------------------------------------------------------
  def getName(self):
    """
    Return the name of the APA.

    Returns:
      String name of the APA.
    """
    return self._name

  # ---------------------------------------------------------------------
  def getLayer(self):
    """
    Return the current layer of the APA.

    Returns:
      String name of the current layer of the APA.
    """
    return self._layer

  # ---------------------------------------------------------------------
  def getStage(self):
    """
    Return the current stage of APA progress.

    Returns:
      Integer number (table in APA.Stages) of APA progress.
    """
    return self._stage

  # ---------------------------------------------------------------------
  def getRecipe(self):
    """
    Return the name of the loaded recipe.

    Returns:
      String name of the loaded recipe.  Empty string if no recipe loaded.
    """
    result = self._recipeFile
    if result is None:
      result = ""

    return result

  # ---------------------------------------------------------------------
  def addWindTime(self, time):
    """
    Account for time spent winding.

    Args:
      time - Additional amount of time (in seconds) spent winding.
    """
    self._windTime += time

  # ---------------------------------------------------------------------
  def toDictionary(self):
    """
    Return class data as dictionary.

    Returns:
      Dictionary object with all class data typically serialized.
    """
    result = {}
    for variable in APA_Base.SERIALIZED_VARIABLES:
      result[variable] = self.__dict__[variable]

    return result

  # ---------------------------------------------------------------------
  def setLocation(self, x, y, headLocation):
    """
    Set the machine location.  Call before closing.

    Args:
      x: X location.
      y: Y location.
      z: Z location.
      headLocation: Position of the winder head (front/back).
    """
    # print("$$$$$ APA_Base.setLocation SETTING X: %f Y: %f" %(self._x, self._y))
    self._x = x
    self._y = y
    self._headLocation = headLocation

  # ---------------------------------------------------------------------
  def load(self, nameOverride=None):
    """
    Load

    Returns:
      True if there was an error, False if not.
    """

    if self._systemTime:
      self._loadStart = self._systemTime.get()

    Serializable.load(self, self.getPath(), APA_Base.FILE_NAME, nameOverride)

  # ---------------------------------------------------------------------
  def save(self):
    """
    Save current APA state to file.
    """
    now = self._systemTime.get()
    self._lastModifyDate = str(now)

    # Count the amount of APA time loaded.
    self._loadedTime += self._systemTime.getDelta(self._loadStart, now)

    Serializable.save(self, self.getPath(), APA_Base.FILE_NAME)


# end class
