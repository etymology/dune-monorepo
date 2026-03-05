###############################################################################
# Name: LayerCalibration.py
# Uses: Calibration adjustments for a layer.
# Date: 2016-03-23
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################
import os.path
import shutil

from dune_winder.library.hashed_serializable import HashedSerializable
from dune_winder.library.serializable_location import SerializableLocation
from dune_winder.library.Geometry.location import Location


class LayerCalibration(HashedSerializable):
  """
  Layer calibration is just a map that has an adjusted location for each
  pin on a layer.  The pins are addressed by side and pin number.  Each
  have a 2d location.

  When uncalibrated, the pin locations are the nominal locations.
  """

  # -------------------------------------------------------------------
  def __init__(self, layer=None, filePath=None, fileName=None, archivePath=None):
    """
    Constructor.

    Args:
      layer: Name of layer.  (Optional)
      archivePath: Location to archive this data when changed.  (Optional)
    """

    # Include only is just for the automatic serialized objects.
    # Missing keys are ignored by the base class because we deal with them
    # specifically with this class.
    includeOnly = ["zFront", "zBack", "_layer"]
    HashedSerializable.__init__(self, includeOnly=includeOnly, ignoreMissing=True)

    # Name of layer this calibration file applies.
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

  # -------------------------------------------------------------------
  def copy(self):
    """
    Duplicate calibration.

    Returns:
      New instance of LayerCalibration with identical values.
    """
    newLayer = LayerCalibration(self._layer)
    newLayer.offset = self.offset
    newLayer.zFront = self.zFront
    newLayer.zBack = self.zBack
    for pinName in self._locations:
      location = self._locations[pinName]
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
    newLocation = SerializableLocation(location.x, location.y, location.z)
    self._locations[pin] = newLocation

  # -------------------------------------------------------------------
  def getPinLocation(self, pin: str):
    """
    Get the calibrated location of the specified pin.

    Args:
      pin: Which pin.

    Returns:
      Instance of SerializableLocation with the position of this pin.
    """

    return self._locations[pin]

  # ---------------------------------------------------------------------
  def getPinExists(self, pin):
    """
    Check to see if a pin name exists in calibration.

    Returns:
      True if pin exists, False if not.
    """
    return pin in self._locations

  # ---------------------------------------------------------------------
  def getPinNames(self):
    """
    Return a list of pin names.

    Returns:
      List of pin names.
    """
    return list(self._locations.keys())

  # ---------------------------------------------------------------------
  def getLayerNames(self):
    """
    Return name of layer.

    Returns:
      Name of layer (X/V/U/G).
    """
    return self._layer

  # -------------------------------------------------------------------
  def archive(self):
    """
    Archive this calibration data if archive does not already exist.
    """

    if self._archivePath:
      # Create directory if it doesn't exist.
      if not os.path.exists(self._archivePath):
        os.makedirs(self._archivePath)

      # If this file does not exist in the archive, copy it there.
      archiveFile = self._archivePath + "/" + self.hashValue
      fileName = self.getFullFileName()
      if not os.path.isfile(archiveFile):
        # Make an archive copy of the file.
        shutil.copy2(fileName, archiveFile)

  # -------------------------------------------------------------------
  def _fileNameSetup(self, filePath, fileName):
    """
    Setup path and file name if override is given.

    Args:
      filePath: Override file path.
      fileName: Override file name.
    """
    if filePath is None and fileName is None:
      filePath = self._filePath
      fileName = self._fileName

    self._filePath = filePath
    self._fileName = fileName

  # -------------------------------------------------------------------
  def load(
    self, filePath=None, fileName=None, nameOverride=None, exceptionForMismatch=True
  ):
    """
    Load an XML file and return instance.

    Args:
      filePath: Directory of file.
      fileName: File name to load.
      nameOverride: Top-level XML name.
      exceptionForMismatch: True to raise an exception if the hash does not
        match.  Default is True.

    Returns:
      True if there was an error, False if not.

    Throws:
      HashedSerializable.Error if hashes do not match (only when
      exceptionForMismatch is True).
    """
    self._fileNameSetup(filePath, fileName)
    HashedSerializable.load(
      self, filePath, fileName, nameOverride, exceptionForMismatch
    )
    self.archive()

  # -------------------------------------------------------------------
  def save(self, filePath=None, fileName=None, nameOverride=None):
    """
    Save data to disk.

    Args:
      filePath: Directory of file.  Omit to use the path specified loading.
      fileName: File name to save in.  Omit to use the name specified loading.
      nameOverride: Top-level XML name.
    """
    self._fileNameSetup(filePath, fileName)
    HashedSerializable.save(self, filePath, fileName, nameOverride)
    self.archive()

  # ---------------------------------------------------------------------
  def serialize(self, xmlDocument, nameOverride=None):
    """
    Turn this object into an XML node.

    Args:
      xmlDocument: Instance of xml.dom.minidom.Document.

    Returns:
      Must return an XML node with the data from this object.
    """

    node = HashedSerializable.serialize(self, xmlDocument, nameOverride)

    node.setAttribute("layer", str(self._layer))

    offsetNode = self.serializeObject(xmlDocument, "Offset", self.offset)
    node.appendChild(offsetNode)

    for pin in self._locations:
      location = self._locations[pin]
      pinNode = self.serializeObject(xmlDocument, pin, location)
      node.appendChild(pinNode)

    return node

  # ---------------------------------------------------------------------
  def unserialize(self, node):
    """
    Take an XML node and load values into this object.

    Args:
      node: Instance of xml.dom.minidom.Node.

    Returns:
      True if there was an error, False if not.
    """

    HashedSerializable.unserialize(self, node)

    self._layer = str(node.getAttribute("layer"))

    nodes = node.getElementsByTagName("SerializableLocation")
    for node in nodes:
      location = SerializableLocation()
      location.unserialize(node)

      name = node.getAttribute("name")
      if "Offset" == name:
        self.offset = location
      else:
        self._locations[name] = location


# Unit test.
if __name__ == "__main__":

  def compare(a, b):
    return (a.x == b.x) and (a.y == b.y) and (a.z == b.z)

  layerCalibration = LayerCalibration("V")
  layerCalibration.offset = SerializableLocation(1, 2)
  layerCalibration.zFront = 10
  layerCalibration.zBack = 20
  layerCalibration.setPinLocation("F1", SerializableLocation(0, 0, 0))
  layerCalibration.setPinLocation("F2", SerializableLocation(1, 0, 0))
  layerCalibration.setPinLocation("F3", SerializableLocation(1, 1, 0))
  layerCalibration.setPinLocation("F4", SerializableLocation(0, 1, 0))
  layerCalibration.setPinLocation("B1", SerializableLocation(0, 0, 1))
  layerCalibration.setPinLocation("B2", SerializableLocation(1, 0, 1))
  layerCalibration.setPinLocation("B3", SerializableLocation(1, 1, 1))
  layerCalibration.setPinLocation("B4", SerializableLocation(0, 1, 1))
  layerCalibration.save(".", "layerCalibrationTest.xml")

  layerCopy = LayerCalibration("V")
  layerCopy.load(".", "layerCalibrationTest.xml")

  assert layerCopy._layer == layerCalibration._layer
  assert layerCopy.zFront == layerCalibration.zFront
  assert layerCopy.zBack == layerCalibration.zBack
  assert compare(layerCopy.offset, layerCalibration.offset)
  assert compare(layerCopy._locations["F1"], layerCalibration._locations["F1"])
  assert compare(layerCopy._locations["F2"], layerCalibration._locations["F2"])
  assert compare(layerCopy._locations["F3"], layerCalibration._locations["F3"])
  assert compare(layerCopy._locations["F4"], layerCalibration._locations["F4"])
  assert compare(layerCopy._locations["B1"], layerCalibration._locations["B1"])
  assert compare(layerCopy._locations["B2"], layerCalibration._locations["B2"])
  assert compare(layerCopy._locations["B3"], layerCalibration._locations["B3"])
  assert compare(layerCopy._locations["B4"], layerCalibration._locations["B4"])
