###############################################################################
# Name: MachineCalibration.py
# Uses: Calibration for machine excluding APA.
# Date: 2016-03-23
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from dune_winder.library.serializable import Serializable
from dune_winder.library.serializable_location import SerializableLocation


class MachineCalibration(Serializable):
  # -------------------------------------------------------------------
  def __init__(self, outputFilePath=None, outputFileName=None):
    """
    Constructor.

    Args:
      outputFilePath - Path to save/load data.
      outputFileName - Name of data file.
    """

    Serializable.__init__(self, exclude=["_outputFilePath", "_outputFileName"])

    self._outputFilePath = outputFilePath
    self._outputFileName = outputFileName

    # Location of the park position.  Instance of Location.
    self.parkX = None
    self.parkY = None

    # Location for loading/unloading the spool.
    self.spoolLoadX = None
    self.spoolLoadY = None

    # Locations of the transfer areas.  Single number.
    # NOTE: The left/right transfer areas can transfer from the bottom and up
    # until some height not the top.  Hence a second number for this limit.
    self.transferLeft = None
    self.transferLeftTop = None
    self.transferTop = None
    self.transferRight = None
    self.transferRightTop = None
    self.transferBottom = None

    # Locations of the end-of-travels.  Single number.
    self.limitLeft = None
    self.limitTop = None
    self.limitRight = None
    self.limitBottom = None

    # Location of Z-axis when fully extended, and fully retracted.  Single number.
    self.zFront = None
    self.zBack = None

    # End-of-travels for Z-axis.  Single number.
    self.zLimitFront = None
    self.zLimitRear = None

    # Length of arm on winder head.
    self.headArmLength = None
    self.headRollerRadius = None
    self.headRollerGap = None

    # Diameter of U/V layer pin.
    self.pinDiameter = None

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
  def save(self):
    """
    Save data to disk.  Overloaded to correctly name class.
    """
    if self._outputFilePath and self._outputFileName:
      Serializable.save(
        self, self._outputFilePath, self._outputFileName, "MachineCalibration"
      )

  # ---------------------------------------------------------------------
  def load(self):
    """
    Load data from disk.  Overloaded to correctly name class.
    """
    if self._outputFilePath and self._outputFileName:
      Serializable.load(
        self, self._outputFilePath, self._outputFileName, "MachineCalibration"
      )


if __name__ == "__main__":
  machineCalibration = MachineCalibration()

  machineCalibration.park = SerializableLocation(1, 2)
  machineCalibration.spoolLoad = SerializableLocation(3, 4)
  machineCalibration.transferLeft = 1
  machineCalibration.transferLeftTop = 2
  machineCalibration.transferTop = 3
  machineCalibration.transferRight = 4
  machineCalibration.transferRightTop = 4
  machineCalibration.transferBottom = 5

  machineCalibration.limitLeft = 6
  machineCalibration.limitTop = 7
  machineCalibration.limitRight = 8
  machineCalibration.limitBottom = 9

  machineCalibration.zFront = 10
  machineCalibration.zBack = 11

  machineCalibration.zLimitFront = 12
  machineCalibration.zLimitRear = 13

  machineCalibration.save(".", "machineCalibrationTest.xml")

  machineCalibrationOut = MachineCalibration()
  machineCalibrationOut.load(".", "machineCalibrationTest.xml")

  assert machineCalibrationOut.park.x == machineCalibration.park.x
  assert machineCalibrationOut.park.y == machineCalibration.park.y
  assert machineCalibrationOut.park.z == machineCalibration.park.z
  assert machineCalibrationOut.spoolLoad.x == machineCalibration.spoolLoad.x
  assert machineCalibrationOut.spoolLoad.y == machineCalibration.spoolLoad.y
  assert machineCalibrationOut.spoolLoad.z == machineCalibration.spoolLoad.z

  assert machineCalibrationOut.transferLeft == machineCalibration.transferLeft
  assert machineCalibrationOut.transferLeftTop == machineCalibration.transferLeftTop
  assert machineCalibrationOut.transferTop == machineCalibration.transferTop
  assert machineCalibrationOut.transferRight == machineCalibration.transferRight
  assert machineCalibrationOut.transferRightTop == machineCalibration.transferRightTop
  assert machineCalibrationOut.transferBottom == machineCalibration.transferBottom

  assert machineCalibrationOut.limitLeft == machineCalibration.limitLeft
  assert machineCalibrationOut.limitTop == machineCalibration.limitTop
  assert machineCalibrationOut.limitRight == machineCalibration.limitRight
  assert machineCalibrationOut.limitBottom == machineCalibration.limitBottom

  assert machineCalibrationOut.zFront == machineCalibration.zFront
  assert machineCalibrationOut.zBack == machineCalibration.zBack

  assert machineCalibrationOut.zLimitFront == machineCalibration.zLimitFront
  assert machineCalibrationOut.zLimitRear == machineCalibration.zLimitRear
