###############################################################################
# Name: APA_Base.py
# Uses: Anode Plane Array (APA) base.
# Date: 2016-05-26
# Author(s):
#   Andrew Que <aque@bb7.com>
# Notes:
#   Contains just the data portion of the APA, but no process control.
###############################################################################

import json
import os
import os.path
import pathlib
import tempfile

from dune_winder.library.time_source import TimeSource
from typing import Optional


class APA_Base:
  # File name of the APA state (this object) on disk.
  FILE_NAME = "state.json"
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
    """Get the path for all files related to this APA."""
    return self._apaDirectory.rstrip("/\\") + "/"

  # ---------------------------------------------------------------------
  def getName(self):
    """Return the name of the APA."""
    return self._name

  # ---------------------------------------------------------------------
  def getLayer(self):
    """Return the current layer of the APA."""
    return self._layer

  # ---------------------------------------------------------------------
  def getStage(self):
    """Return the current stage of APA progress."""
    return self._stage

  # ---------------------------------------------------------------------
  def getRecipe(self):
    """Return the name of the loaded recipe (empty string if none)."""
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
    """Return class data as dictionary."""
    return {var: self.__dict__[var] for var in APA_Base.SERIALIZED_VARIABLES}

  # ---------------------------------------------------------------------
  def setLocation(self, x, y, headLocation):
    """
    Set the machine location.  Call before closing.

    Args:
      x: X location.
      y: Y location.
      headLocation: Position of the winder head (front/back).
    """
    self._x = x
    self._y = y
    self._headLocation = headLocation

  # ---------------------------------------------------------------------
  def load(self, nameOverride=None):
    """Load APA state from JSON.  Falls back to XML for first-run migration."""
    if self._systemTime:
      self._loadStart = self._systemTime.get()

    path = pathlib.Path(self.getPath()) / APA_Base.FILE_NAME
    if path.exists():
      with path.open() as f:
        data = json.load(f)
      for var in APA_Base.SERIALIZED_VARIABLES:
        if var in data:
          setattr(self, var, data[var])
    else:
      # Migration: try the legacy state.xml.
      xml_path = path.with_name("state.xml")
      if xml_path.exists():
        self._load_from_xml(xml_path)
        self.save()

  # ---------------------------------------------------------------------
  def save(self):
    """Save current APA state to JSON atomically."""
    if self._systemTime:
      now = self._systemTime.get()
      self._lastModifyDate = str(now)
      self._loadedTime += self._systemTime.getDelta(self._loadStart, now)

    data = {var: getattr(self, var) for var in APA_Base.SERIALIZED_VARIABLES}
    content = json.dumps(data, indent=2)

    path = pathlib.Path(self.getPath()) / APA_Base.FILE_NAME
    fd, tmp = tempfile.mkstemp(dir=str(path.parent))
    try:
      with os.fdopen(fd, "w") as f:
        f.write(content)
      os.replace(tmp, str(path))
    except Exception:
      try:
        os.unlink(tmp)
      except OSError:
        pass
      raise

  # ---------------------------------------------------------------------
  def _load_from_xml(self, xml_path: pathlib.Path) -> None:
    """Parse the legacy Serializable XML format into this instance."""
    import xml.dom.minidom

    doc = xml.dom.minidom.parse(str(xml_path))
    # The XML root element is the subclass name (e.g. AnodePlaneArray).
    root = doc.documentElement.firstChild
    while root and root.nodeType != root.ELEMENT_NODE:
      root = root.nextSibling
    if root is None:
      return

    for node in root.childNodes:
      if node.nodeType != node.ELEMENT_NODE:
        continue
      name = node.getAttribute("name")
      if name not in APA_Base.SERIALIZED_VARIABLES:
        continue
      tag = node.nodeName
      if tag == "NoneType" or not node.firstChild:
        setattr(self, name, None)
      elif tag == "float":
        setattr(self, name, float(node.firstChild.nodeValue))
      elif tag == "int":
        setattr(self, name, int(node.firstChild.nodeValue))
      elif tag == "str":
        setattr(self, name, str(node.firstChild.nodeValue))
      elif tag == "dict":
        d = {}
        for child in node.childNodes:
          if child.nodeType != child.ELEMENT_NODE:
            continue
          k = child.getAttribute("name")
          if child.firstChild:
            d[k] = child.firstChild.nodeValue
        setattr(self, name, d)


# end class
