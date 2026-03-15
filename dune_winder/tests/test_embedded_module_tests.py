import math
import unittest

from dune_winder.gcode.handler_base import GCodeHandlerBase
from dune_winder.gcode.runtime import GCodeProgramExecutor
from dune_winder.library.Geometry.circle import Circle
from dune_winder.library.Geometry.location import Location
from dune_winder.library.math_extra import MathExtra
from dune_winder.machine.calibration.defaults import (
  DefaultLayerCalibration,
  DefaultMachineCalibration,
)
from dune_winder.machine.calibration.machine import MachineCalibration
from dune_winder.machine.head_compensation import HeadCompensation


class _GCodeHandlerBaseTestDouble(GCodeHandlerBase):
  def __init__(self):
    machineCalibration = DefaultMachineCalibration()
    layerCalibration = DefaultLayerCalibration(None, None, "V")
    headCompensation = HeadCompensation(machineCalibration)

    super().__init__(machineCalibration, headCompensation)
    self.useLayerCalibration(layerCalibration)
    self.layerCalibration = layerCalibration


class EmbeddedModuleTests(unittest.TestCase):
  def test_gcode_handler_base_main_block_cases(self):
    handler = _GCodeHandlerBaseTestDouble()
    gcode = GCodeProgramExecutor(
      [
        "X10 Y10 Z10",
        "G103 PF800 PF800 PXY",
        "G109 PF1200 PTR G103 PF1199 PF1198 PXY G102",
      ],
      handler._callbacks,
    )

    gcode.executeNextLine(0)
    self.assertEqual(Location(handler._x, handler._y, handler._z), Location(10, 10, 10))

    gcode.executeNextLine(1)
    pin_location = handler.layerCalibration.getPinLocation("F800")
    pin_location = pin_location.add(handler.layerCalibration.offset)
    pin_location.z = 0
    self.assertEqual(pin_location, Location(handler._x, handler._y))

    gcode.executeNextLine(2)
    self.assertTrue(MathExtra.isclose(handler._x, 6667.210624130574))
    self.assertTrue(MathExtra.isclose(handler._y, 4.0))

  def test_circle_tangent_point_main_block_cases(self):
    tests = [
      {
        "circle": Circle(Location(0, 0), 9),
        "position": Location(45, 45),
        "results": {
          "TR": None,
          "TL": None,
          "RB": None,
          "RT": Location(7.2, 5.4),
          "BL": Location(-5.4, -7.2),
          "BR": None,
          "LT": None,
          "LB": None,
        },
      },
      {
        "circle": Circle(Location(0, 0), 9),
        "position": Location(-45, 45),
        "results": {
          "TR": None,
          "TL": None,
          "RB": None,
          "RT": None,
          "BL": None,
          "BR": Location(5.4, -7.2),
          "LT": Location(-7.2, 5.4),
          "LB": None,
        },
      },
      {
        "circle": Circle(Location(0, 0), 9),
        "position": Location(-45, -45),
        "results": {
          "TR": Location(5.4, 7.2),
          "TL": None,
          "RB": None,
          "RT": None,
          "BL": None,
          "BR": None,
          "LT": None,
          "LB": Location(-7.2, -5.4),
        },
      },
      {
        "circle": Circle(Location(0, 0), 9),
        "position": Location(45, -45),
        "results": {
          "TR": None,
          "TL": Location(-5.4, 7.2),
          "RB": Location(7.2, -5.4),
          "RT": None,
          "BL": None,
          "BR": None,
          "LT": None,
          "LB": None,
        },
      },
      {
        "circle": Circle(Location(588.274, 170.594), 1.215),
        "position": Location(598.483, 166.131),
        "results": {
          "TR": None,
          "TL": Location(587.9116215645, 171.7537011984),
          "RB": Location(588.8791774069, 169.5404415981),
          "RT": None,
          "BL": None,
          "BR": None,
          "LT": None,
          "LB": None,
        },
      },
    ]

    for case in tests:
      for orientation, expected in case["results"].items():
        with self.subTest(position=case["position"], orientation=orientation):
          location = case["circle"].tangentPoint(orientation, case["position"])
          if expected is None:
            self.assertIsNone(location)
            continue

          self.assertTrue(MathExtra.isclose(location.x, expected.x))
          self.assertTrue(MathExtra.isclose(location.y, expected.y))

  def test_head_compensation_main_block_cases(self):
    machineCalibration = MachineCalibration()
    machineCalibration.headArmLength = 125
    machineCalibration.headRollerRadius = 6.35
    machineCalibration.headRollerGap = 1.27
    machineCalibration.pinDiameter = 2.43

    headCompensation = HeadCompensation(machineCalibration)

    anchorPoint = Location(6581.6559158273, 113.186368912, 174.15)
    machinePosition = Location(6363.6442868365, 4, 0)
    headCompensation.anchorPoint(anchorPoint)

    correctX = headCompensation.correctX(machinePosition)
    correctY = headCompensation.correctY(machinePosition)
    correctedPositionX = machinePosition.copy(x=correctX)
    correctedPositionY = machinePosition.copy(y=correctY)
    headAngleX = headCompensation.getHeadAngle(correctedPositionX)
    headAngleY = headCompensation.getHeadAngle(correctedPositionY)
    wireX = headCompensation.getActualLocation(correctedPositionX)

    self.assertTrue(MathExtra.isclose(6238.4109348003, correctX))
    self.assertTrue(MathExtra.isclose(66.7203926635, correctY))
    self.assertTrue(MathExtra.isclose(-116.9015774072 / 180 * math.pi, headAngleX))
    self.assertTrue(MathExtra.isclose(-128.6182306977 / 180 * math.pi, headAngleY))
    self.assertEqual(wireX, Location(6352.0774120067, 5.1306535219, 57.6702300097))

    anchorPoint = Location(588.274, 170.594)
    targetPosition = Location(598.483, 166.131)
    headCompensation.anchorPoint(anchorPoint)
    headCompensation.orientation("TR")

    newTarget = headCompensation.pinCompensation(targetPosition)
    self.assertIsNone(newTarget)


if __name__ == "__main__":
  unittest.main()
