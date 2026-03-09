###############################################################################
# Name: DefaultCalibration.py
# Uses: Generate a default calibration file for layer based on nominal geometry.
# Date: 2016-04-15
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################
import os

from dune_winder.library.Geometry.location import Location
from dune_winder.library.serializable_location import SerializableLocation

from dune_winder.machine.geometry_selection import create_layer_geometry
from dune_winder.machine.layer_calibration import LayerCalibration
from dune_winder.machine.machine_calibration import MachineCalibration
from dune_winder.machine.uv_layer_geometry import UV_LayerGeometry


def _populate_nominal_locations(calibration, geometry):
  """
  Populate the calibration map with nominal pin locations from geometry.

  Args:
    calibration: Instance of LayerCalibration to fill.
    geometry: Instance of LayerGeometry for the target layer.
  """
  grids = [
    (
      "F",
      geometry.gridFront,
      geometry.mostlyExtend,
      geometry.startPinFront,
      geometry.directionFront,
    ),
    (
      "B",
      geometry.gridBack,
      geometry.mostlyRetract,
      geometry.startPinBack,
      geometry.directionBack,
    ),
  ]

  for side, grid, depth, startPin, direction in grids:
    xValue = 0.0
    yValue = 0.0
    pinNumber = int(startPin)

    for parameter in grid:
      count = int(parameter[0])
      xIncrement = parameter[1]
      yIncrement = parameter[2]
      xValue += parameter[3]
      yValue += parameter[4]

      for _ in range(count):
        calibration.setPinLocation(
          side + str(pinNumber), Location(round(xValue, 5), round(yValue, 5), depth)
        )

        pinNumber += int(direction)

        if 0 == pinNumber:
          pinNumber = int(geometry.pins)
        elif pinNumber > int(geometry.pins):
          pinNumber = 1

        xValue += xIncrement
        yValue += yIncrement

      xValue -= xIncrement
      yValue -= yIncrement


class DefaultMachineCalibration(MachineCalibration):
  # ---------------------------------------------------------------------
  def __init__(self, outputFilePath=None, outputFileName=None):
    """
    Constructor.

    Args:
      outputFilePath - Path to save/load data.
      outputFileName - Name of data file.
    """
    MachineCalibration.__init__(self, outputFilePath, outputFileName)
    geometry = UV_LayerGeometry()

    # Location of the park position.
    self.parkX = 0
    self.parkY = 0

    # Location for loading/unloading the spool.
    self.spoolLoadX = 0
    self.spoolLoadY = 0

    self.transferLeft = geometry.left
    self.transferLeftTop = geometry.top / 2
    self.transferTop = geometry.top
    self.transferRight = geometry.right
    self.transferRightTop = geometry.top / 2
    self.transferBottom = geometry.bottom

    self.limitLeft = geometry.limitLeft
    self.limitTop = geometry.limitTop
    self.limitRight = geometry.limitRight
    self.limitBottom = geometry.limitBottom
    self.zFront = 0
    self.zBack = geometry.zTravel
    self.zLimitFront = geometry.limitRetracted
    self.zLimitRear = geometry.limitExtended
    self.headArmLength = geometry.headArmLength
    self.headRollerRadius = geometry.headRollerRadius
    self.headRollerGap = geometry.headRollerGap
    self.pinDiameter = geometry.pinDiameter

    if outputFilePath and outputFileName:
      import pathlib
      json_path = pathlib.Path(outputFilePath) / outputFileName
      xml_path = json_path.with_suffix(".xml")
      if json_path.exists() or xml_path.exists():
        # load() handles XML → JSON migration automatically.
        self.load()
      else:
        self.save()


class DefaultLayerCalibration(LayerCalibration):
  # ---------------------------------------------------------------------
  def __init__(self, outputFilePath, outputFileName, layerName):
    """
    Export node list to calibration file.  Debug function.

    Args:
      outputFileName: File name to create.
      layerName: Name of recipe.
    """

    geometry = create_layer_geometry(layerName)

    LayerCalibration.__init__(self, layerName)
    self.offset = geometry.apaLocation.add(geometry.apaOffset)
    self.offset = SerializableLocation.fromLocation(self.offset)
    self.zFront = geometry.mostlyRetract
    self.zBack = geometry.mostlyExtend

    _populate_nominal_locations(self, geometry)

    if outputFilePath and outputFileName:
      self.save(outputFilePath, outputFileName, "LayerCalibration")


# end class

if __name__ == "__main__":
  DefaultMachineCalibration(".", "MachineCalibration.json")
  DefaultLayerCalibration(".", "V_Calibration.json", "V")
  DefaultLayerCalibration(".", "U_Calibration.json", "U")
