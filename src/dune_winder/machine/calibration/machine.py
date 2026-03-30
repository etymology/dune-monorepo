###############################################################################
# Name: MachineCalibration.py
# Uses: Calibration for machine excluding APA.
# Date: 2016-03-23
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

import json
import os
import pathlib
import tempfile


# Fields persisted to disk, in declaration order.
_FIELDS = (
    "parkX",
    "parkY",
    "spoolLoadX",
    "spoolLoadY",
    "transferLeft",
    "transferLeftTop",
    "transferTop",
    "transferRight",
    "transferRightTop",
    "transferBottom",
    "transferLeftMargin",
    "transferYThreshold",
    "limitLeft",
    "limitTop",
    "limitRight",
    "limitBottom",
    "headwardPivotX",
    "headwardPivotY",
    "headwardPivotXTolerance",
    "headwardPivotYTolerance",
    "zFront",
    "zBack",
    "queuedMotionZCollisionThreshold",
    "arcMaxStepRad",
    "arcMaxChord",
    "apaCollisionBottomY",
    "apaCollisionTopY",
    "transferZoneHeadMinX",
    "transferZoneHeadMaxX",
    "transferZoneFootMinX",
    "transferZoneFootMaxX",
    "supportCollisionBottomMinY",
    "supportCollisionBottomMaxY",
    "supportCollisionMiddleMinY",
    "supportCollisionMiddleMaxY",
    "supportCollisionTopMinY",
    "supportCollisionTopMaxY",
    "geometryEpsilon",
    "zLimitFront",
    "zLimitRear",
    "headArmLength",
    "headRollerRadius",
    "headRollerGap",
    "pinDiameter",
    "v_x_max",
    "v_y_max",
)


class MachineCalibration:
  # -------------------------------------------------------------------
  def __init__(self, outputFilePath=None, outputFileName=None):
    """
    Constructor.

    Args:
      outputFilePath - Path to save/load data.
      outputFileName - Name of data file (JSON).
    """
    self._outputFilePath = outputFilePath
    self._outputFileName = outputFileName

    # Location of the park position.
    self.parkX = None
    self.parkY = None

    # Location for loading/unloading the spool.
    self.spoolLoadX = None
    self.spoolLoadY = None

    # Locations of the transfer areas.
    self.transferLeft = None
    self.transferLeftTop = None
    self.transferTop = None
    self.transferRight = None
    self.transferRightTop = None
    self.transferBottom = None
    self.transferLeftMargin = None
    self.transferYThreshold = None

    # Locations of the end-of-travels.
    self.limitLeft = None
    self.limitTop = None
    self.limitRight = None
    self.limitBottom = None

    # Keepout region around winding-head support arm pivot.
    self.headwardPivotX = None
    self.headwardPivotY = None
    self.headwardPivotXTolerance = None
    self.headwardPivotYTolerance = None

    # Location of Z-axis when fully extended, and fully retracted.
    self.zFront = None
    self.zBack = None
    self.queuedMotionZCollisionThreshold = None
    self.arcMaxStepRad = None
    self.arcMaxChord = None
    self.apaCollisionBottomY = None
    self.apaCollisionTopY = None
    self.transferZoneHeadMinX = None
    self.transferZoneHeadMaxX = None
    self.transferZoneFootMinX = None
    self.transferZoneFootMaxX = None
    self.supportCollisionBottomMinY = None
    self.supportCollisionBottomMaxY = None
    self.supportCollisionMiddleMinY = None
    self.supportCollisionMiddleMaxY = None
    self.supportCollisionTopMinY = None
    self.supportCollisionTopMaxY = None
    self.geometryEpsilon = None

    # End-of-travels for Z-axis.
    self.zLimitFront = None
    self.zLimitRear = None

    # Length of arm on winder head.
    self.headArmLength = None
    self.headRollerRadius = None
    self.headRollerGap = None

    # Diameter of U/V layer pin.
    self.pinDiameter = None

    # Maximum axis component velocities for queued motion (mm/min).
    self.v_x_max = None
    self.v_y_max = None

  # ---------------------------------------------------------------------
  def set(self, item, value):
    """
    Set a calibration item.

    Args:
      item: Name of item to set.
      value: Value of this item.
    """
    self.__dict__[item] = value

  # ---------------------------------------------------------------------
  def get(self, item):
    """
    Get a calibration item.

    Args:
      item: Name of item to get.

    Returns:
      Value of the requested item.
    """
    return self.__dict__[item]

  # ---------------------------------------------------------------------
  def _to_dict(self) -> dict:
    return {field: getattr(self, field) for field in _FIELDS}

  # ---------------------------------------------------------------------
  def _from_dict(self, data: dict) -> None:
    for field in _FIELDS:
      if field in data:
        setattr(self, field, data[field])

  # ---------------------------------------------------------------------
  def save(self):
    """Save calibration data to JSON atomically."""
    if not (self._outputFilePath and self._outputFileName):
      return

    path = pathlib.Path(self._outputFilePath) / self._outputFileName
    content = json.dumps(self._to_dict(), indent=2)

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
  def load(self):
    """Load calibration from JSON.  Falls back to XML on first migration."""
    if not (self._outputFilePath and self._outputFileName):
      return

    path = pathlib.Path(self._outputFilePath) / self._outputFileName
    if path.exists():
      with path.open() as f:
        self._from_dict(json.load(f))
    else:
      # Migration: try the legacy XML file.
      xml_path = path.with_suffix(".xml")
      if xml_path.exists():
        self._load_from_xml(xml_path)
        self.save()  # Persist as JSON.

  # ---------------------------------------------------------------------
  def _load_from_xml(self, xml_path: pathlib.Path) -> None:
    """Parse the legacy Serializable XML format into this instance."""
    import xml.dom.minidom

    doc = xml.dom.minidom.parse(str(xml_path))
    nodes = doc.getElementsByTagName("MachineCalibration")
    if not nodes:
      raise KeyError("MachineCalibration not found in XML file")

    for node in nodes[0].childNodes:
      if node.nodeType != node.ELEMENT_NODE:
        continue
      name = node.getAttribute("name")
      if not node.firstChild:
        continue
      if node.nodeName == "float":
        setattr(self, name, float(node.firstChild.nodeValue))
      elif node.nodeName == "int":
        setattr(self, name, int(node.firstChild.nodeValue))
