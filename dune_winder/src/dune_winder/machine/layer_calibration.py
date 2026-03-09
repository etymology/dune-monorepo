###############################################################################
# Name: LayerCalibration.py
# Uses: Calibration adjustments for a layer.
# Date: 2016-03-23
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################
import json
import os
import os.path
import pathlib
import re
import shutil
import tempfile

from dune_winder.library.hash import Hash
from dune_winder.library.serializable_location import SerializableLocation
from dune_winder.library.Geometry.location import Location


def _loc_to_dict(loc: Location) -> dict:
  return {"x": loc.x, "y": loc.y, "z": loc.z}


def _dict_to_loc(d: dict) -> Location:
  return Location(d["x"], d["y"], d["z"])


class LayerCalibration:
  """
  Layer calibration is just a map that has an adjusted location for each
  pin on a layer.  The pins are addressed by side and pin number.  Each
  have a 2d location.

  When uncalibrated, the pin locations are the nominal locations.
  """

  # -------------------------------------------------------------------
  class Error(ValueError):
    """Exception raised on hash mismatch."""

    def __init__(self, message, data=None):
      super().__init__(message)
      self.data = data or []

  # -------------------------------------------------------------------
  def __init__(self, layer=None, filePath=None, fileName=None, archivePath=None):
    """
    Constructor.

    Args:
      layer: Name of layer.  (Optional)
      filePath: Directory of calibration file.  (Optional)
      fileName: File name.  (Optional)
      archivePath: Location to archive this data when changed.  (Optional)
    """
    self._layer = layer

    # Offset of 0,0 on the APA to machine offset.
    self.offset = SerializableLocation()

    # Z-positions to level with front/back of pins.
    self.zFront = None
    self.zBack = None

    # Look-up table that correlates pin names to their locations.
    self._locations: dict[str, Location] = {}

    self._filePath = filePath
    self._fileName = fileName
    self._archivePath = archivePath

    # Content hash — used for change detection and archive naming.
    self.hashValue = ""

  # -------------------------------------------------------------------
  def copy(self):
    """Return a duplicate of this calibration."""
    newLayer = LayerCalibration(self._layer)
    newLayer.offset = self.offset
    newLayer.zFront = self.zFront
    newLayer.zBack = self.zBack
    for pinName, location in self._locations.items():
      newLayer._locations[pinName] = location.copy()
    return newLayer

  # -------------------------------------------------------------------
  def setPinLocation(self, pin, location):
    """
    Set the calibrated location of the specified pin.

    Args:
      pin: Which pin.
      location: The location (relative to the APA) of this pin.
    """
    self._locations[pin] = SerializableLocation(location.x, location.y, location.z)

  # -------------------------------------------------------------------
  def getPinLocation(self, pin: str):
    """
    Get the calibrated location of the specified pin.

    Returns:
      Instance of Location with the position of this pin.
    """
    return self._locations[pin]

  # -------------------------------------------------------------------
  def getPinExists(self, pin):
    """Return True if a pin name exists in calibration."""
    return pin in self._locations

  # -------------------------------------------------------------------
  def getPinNames(self):
    """Return a list of pin names."""
    return list(self._locations.keys())

  # -------------------------------------------------------------------
  def getLayerNames(self):
    """Return name of layer (X/V/U/G)."""
    return self._layer

  # -------------------------------------------------------------------
  def getFullFileName(self) -> str:
    return str(pathlib.Path(self._filePath) / self._fileName)

  # -------------------------------------------------------------------
  def getFileName(self) -> str:
    return self._fileName

  # -------------------------------------------------------------------
  def getFilePath(self) -> str:
    return self._filePath

  # -------------------------------------------------------------------
  def _compute_hash(self, data: dict) -> str:
    """Compute MD5 hash of JSON content, excluding the hashValue field."""
    without_hash = {k: v for k, v in data.items() if k != "hashValue"}
    content = json.dumps(without_hash, sort_keys=True, separators=(",", ":"))
    return Hash.singleLine(content)

  # -------------------------------------------------------------------
  def _to_dict(self) -> dict:
    return {
      "layer": self._layer,
      "zFront": self.zFront,
      "zBack": self.zBack,
      "hashValue": self.hashValue,
      "offset": _loc_to_dict(self.offset),
      "locations": {pin: _loc_to_dict(loc) for pin, loc in self._locations.items()},
    }

  # -------------------------------------------------------------------
  def _from_dict(self, data: dict) -> None:
    self._layer = data.get("layer", self._layer)
    self.zFront = data.get("zFront")
    self.zBack = data.get("zBack")
    self.hashValue = data.get("hashValue", "")
    offset_d = data.get("offset", {"x": 0.0, "y": 0.0, "z": 0.0})
    self.offset = SerializableLocation(offset_d["x"], offset_d["y"], offset_d["z"])
    self._locations = {
      pin: Location(d["x"], d["y"], d["z"])
      for pin, d in data.get("locations", {}).items()
    }

  # -------------------------------------------------------------------
  def archive(self):
    """Archive this calibration file if the archive copy does not yet exist."""
    if not (self._archivePath and self.hashValue and self._filePath and self._fileName):
      return
    if not os.path.exists(self._archivePath):
      os.makedirs(self._archivePath)
    archive_file = os.path.join(self._archivePath, self.hashValue)
    source = self.getFullFileName()
    if os.path.isfile(source) and not os.path.isfile(archive_file):
      shutil.copy2(source, archive_file)

  # -------------------------------------------------------------------
  def _file_name_setup(self, filePath, fileName):
    if filePath is None and fileName is None:
      filePath = self._filePath
      fileName = self._fileName
    self._filePath = filePath
    self._fileName = fileName

  # -------------------------------------------------------------------
  def save(self, filePath=None, fileName=None, nameOverride=None):
    """
    Save calibration to JSON atomically.

    Args:
      filePath: Directory of file.  Omit to use the path specified on load.
      fileName: File name.  Omit to use the name specified on load.
      nameOverride: Ignored (kept for call-site compatibility).
    """
    self._file_name_setup(filePath, fileName)

    # Always persist to the .json file regardless of the stored name.
    self._fileName = pathlib.Path(self._fileName).with_suffix(".json").name

    data = self._to_dict()
    hash_val = self._compute_hash(data)
    data["hashValue"] = hash_val
    self.hashValue = hash_val

    content = json.dumps(data, indent=2)
    path = pathlib.Path(self._filePath) / self._fileName
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

    self.archive()

  # -------------------------------------------------------------------
  def load(
    self, filePath=None, fileName=None, nameOverride=None, exceptionForMismatch=True
  ):
    """
    Load calibration from JSON.  Falls back to XML for first-run migration.

    Args:
      filePath: Directory of file.
      fileName: File name.
      nameOverride: Ignored (kept for call-site compatibility).
      exceptionForMismatch: Raise LayerCalibration.Error on hash mismatch.

    Returns:
      True if there was a hash error, False otherwise.
    """
    self._file_name_setup(filePath, fileName)

    # Normalise to the JSON path regardless of whether the caller passed
    # a .xml or .json name (old APA state may still record .xml names).
    raw_path = pathlib.Path(self._filePath) / self._fileName
    json_path = raw_path.with_suffix(".json")
    xml_path = raw_path.with_suffix(".xml")

    # Update the stored name so subsequent save() writes the .json file.
    self._fileName = json_path.name

    if json_path.exists():
      with json_path.open() as f:
        data = json.load(f)
      stored_hash = data.get("hashValue", "")
      self._from_dict(data)
      computed_hash = self._compute_hash(data)
      self.hashValue = computed_hash
      if stored_hash and computed_hash != stored_hash and exceptionForMismatch:
        raise LayerCalibration.Error(
          f"{computed_hash!r} does not match {stored_hash!r}",
          [computed_hash, stored_hash],
        )
      is_error = bool(stored_hash and computed_hash != stored_hash)
    elif xml_path.exists():
      # Migration: read XML and immediately re-save as JSON.
      self._load_from_xml(xml_path, exceptionForMismatch)
      self.save(self._filePath, self._fileName)
      is_error = False
    else:
      raise FileNotFoundError(f"Calibration file not found: {json_path}")

    self.archive()
    return is_error

  # -------------------------------------------------------------------
  def _load_from_xml(self, xml_path: pathlib.Path, exceptionForMismatch=True) -> None:
    """Parse the legacy Serializable/HashedSerializable XML format."""
    import xml.dom.minidom

    doc = xml.dom.minidom.parse(str(xml_path))
    nodes = doc.getElementsByTagName("LayerCalibration")
    if not nodes:
      raise KeyError("LayerCalibration not found in XML file")
    root = nodes[0]

    self._layer = str(root.getAttribute("layer"))

    # Read scalar fields from typed element nodes.
    for node in root.childNodes:
      if node.nodeType != node.ELEMENT_NODE:
        continue
      name = node.getAttribute("name")
      if not node.firstChild:
        continue
      if node.nodeName == "float":
        if name == "zFront":
          self.zFront = float(node.firstChild.nodeValue)
        elif name == "zBack":
          self.zBack = float(node.firstChild.nodeValue)
      elif node.nodeName == "str":
        pass  # hashValue and _layer are handled elsewhere

    # Read SerializableLocation nodes.
    for node in root.getElementsByTagName("SerializableLocation"):
      loc = Location()
      for child in node.childNodes:
        if child.nodeType != child.ELEMENT_NODE:
          continue
        attr = child.getAttribute("name")
        if child.firstChild:
          val = float(child.firstChild.nodeValue)
          setattr(loc, attr, val)
      loc_name = node.getAttribute("name")
      if loc_name == "Offset":
        self.offset = SerializableLocation(loc.x, loc.y, loc.z)
      else:
        self._locations[loc_name] = loc

    # Hash validation on XML source.
    with xml_path.open() as f:
      raw = f.read()
    lines = re.sub(r"[\s]+", "", raw)
    lines = re.sub(
      r'(<strname="hashValue">' + Hash.HASH_PATTERN + r"?</str>)", "", lines
    )
    computed_hash = Hash.singleLine(lines)
    body = re.search(
      r'<str[\s]*?name="hashValue"[\s]*?>' + Hash.HASH_PATTERN + r"?</str>", raw
    )
    self.hashValue = computed_hash
    if body is not None:
      stored_hash = body.group(1)
      if computed_hash != stored_hash and exceptionForMismatch:
        raise LayerCalibration.Error(
          f"{computed_hash!r} does not match {stored_hash!r}",
          [computed_hash, stored_hash],
        )
