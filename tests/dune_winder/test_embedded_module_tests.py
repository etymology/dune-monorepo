import json
import math
import os
import tempfile
import unittest

import dune_winder.gcode.handler_base as handler_base_module
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
from dune_winder.machine.head_compensation import WirePathModel


class _GCodeHandlerBaseTestDouble(GCodeHandlerBase):
  def __init__(self):
    machineCalibration = DefaultMachineCalibration()
    layerCalibration = DefaultLayerCalibration(None, None, "V")
    headCompensation = WirePathModel(machineCalibration)

    super().__init__(machineCalibration, headCompensation)
    self.useLayerCalibration(layerCalibration)
    self.layerCalibration = layerCalibration


class EmbeddedModuleTests(unittest.TestCase):
  def test_default_layer_calibration_uses_layer_specific_z_defaults(self):
    calibration = DefaultLayerCalibration(None, None, "V")

    self.assertEqual(calibration.zFront, 150.0)
    self.assertEqual(calibration.zBack, 265.0)
    self.assertEqual(calibration.getPinLocation("A1").z, 150.0)
    self.assertEqual(calibration.getPinLocation("B1").z, 265.0)

  def test_gcode_handler_base_main_block_cases(self):
    handler = _GCodeHandlerBaseTestDouble()
    gcode = GCodeProgramExecutor(
      [
        "X10 Y10 Z10",
        "G103 PA800 PA800 PXY",
        "G109 PA1200 PTR G103 PA1199 PA1198 PXY G102",
      ],
      handler._callbacks,
    )

    gcode.executeNextLine(0)
    self.assertEqual(Location(handler._x, handler._y, handler._z), Location(10, 10, 10))

    gcode.executeNextLine(1)
    pin_location = handler.layerCalibration.getPinLocation("A800")
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

    headCompensation = WirePathModel(machineCalibration)

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

  def test_g109_g103_lines_emit_motion_trace_logging(self):
    handler = _GCodeHandlerBaseTestDouble()
    handler._x = 0.0
    handler._y = 0.0
    handler._z = 0.0
    handler._headPosition = 1
    line = "G109 PA1200 PTR G103 PA1199 PA1198 PXY G105 PX5"

    with self.assertLogs("dune_winder.gcode.handler_base", level="INFO") as captured:
      GCodeProgramExecutor([line], handler._callbacks).executeNextLine(0)

    payload = json.loads(captured.output[0].split("GCODE_MOTION_TRACE ", 1)[1])

    anchor = next(pin for pin in payload["pins"] if pin["role"] == "anchor")
    pin_a = next(pin for pin in payload["pins"] if pin["role"] == "pinA")
    pin_b = next(pin for pin in payload["pins"] if pin["role"] == "pinB")

    expected_anchor = handler.layerCalibration.getPinLocation("A1200")
    expected_pin_a = handler.layerCalibration.getPinLocation("A1199")
    expected_pin_b = handler.layerCalibration.getPinLocation("A1198")
    expected_center = expected_pin_a.center(expected_pin_b).add(handler.layerCalibration.offset)

    self.assertEqual(payload["line"], line)
    self.assertEqual(payload["anchorOrientation"], "TR")
    self.assertEqual(anchor["pin"], "A1200")
    self.assertEqual(anchor["orientation"], "TR")
    self.assertAlmostEqual(anchor["calibrationSpace"]["x"], expected_anchor.x, places=6)
    self.assertAlmostEqual(
      anchor["wireSpace"]["x"],
      expected_anchor.x + handler.layerCalibration.offset.x,
      places=6,
    )
    self.assertAlmostEqual(pin_a["calibrationSpace"]["x"], expected_pin_a.x, places=6)
    self.assertAlmostEqual(pin_b["calibrationSpace"]["x"], expected_pin_b.x, places=6)
    self.assertEqual(payload["pinCenter"]["axes"], "XY")
    self.assertAlmostEqual(payload["pinCenter"]["wireSpace"]["x"], expected_center.x, places=6)
    self.assertAlmostEqual(payload["resultingTarget"]["x"], expected_center.x + 5.0, places=6)
    self.assertAlmostEqual(payload["resultingTarget"]["y"], expected_center.y, places=6)
    self.assertIsNotNone(payload["resultingWireTarget"])

  def test_g109_g103_motion_trace_is_written_to_log_file(self):
    handler = _GCodeHandlerBaseTestDouble()
    handler._x = 0.0
    handler._y = 0.0
    handler._z = 0.0
    handler._headPosition = 1
    line = "G109 PA1200 PTR G103 PA1199 PA1198 PXY"

    with tempfile.TemporaryDirectory() as temp_directory:
      log_path = os.path.join(temp_directory, "gcode_motion_trace.log")
      previous_env = os.environ.get(handler_base_module._MOTION_TRACE_LOG_ENV)
      previous_handler = handler_base_module._MOTION_TRACE_FILE_HANDLER
      previous_file_path = handler_base_module._MOTION_TRACE_FILE_PATH

      if previous_handler is not None:
        handler_base_module.LOGGER.removeHandler(previous_handler)
        previous_handler.close()
      handler_base_module._MOTION_TRACE_FILE_HANDLER = None
      handler_base_module._MOTION_TRACE_FILE_PATH = None
      os.environ[handler_base_module._MOTION_TRACE_LOG_ENV] = log_path

      try:
        GCodeProgramExecutor([line], handler._callbacks).executeNextLine(0)
      finally:
        active_handler = handler_base_module._MOTION_TRACE_FILE_HANDLER
        if active_handler is not None:
          active_handler.flush()
          handler_base_module.LOGGER.removeHandler(active_handler)
          active_handler.close()
        handler_base_module._MOTION_TRACE_FILE_HANDLER = None
        handler_base_module._MOTION_TRACE_FILE_PATH = None
        if previous_env is None:
          os.environ.pop(handler_base_module._MOTION_TRACE_LOG_ENV, None)
        else:
          os.environ[handler_base_module._MOTION_TRACE_LOG_ENV] = previous_env
        if previous_handler is not None:
          handler_base_module.LOGGER.addHandler(previous_handler)
          handler_base_module._MOTION_TRACE_FILE_HANDLER = previous_handler
          handler_base_module._MOTION_TRACE_FILE_PATH = previous_file_path

      with open(log_path, encoding="utf-8") as input_file:
        lines = [entry.strip() for entry in input_file.readlines() if entry.strip()]

    self.assertEqual(len(lines), 1)
    self.assertIn("GCODE_MOTION_TRACE", lines[0])
    payload = json.loads(lines[0].split("GCODE_MOTION_TRACE ", 1)[1])
    self.assertEqual(payload["line"], line)

  def test_g109_g103_motion_trace_callback_receives_payload(self):
    handler = _GCodeHandlerBaseTestDouble()
    handler._x = 0.0
    handler._y = 0.0
    handler._z = 0.0
    handler._headPosition = 1
    seen = []
    handler.setInstructionTraceCallback(lambda payload: seen.append(payload))

    GCodeProgramExecutor(
      ["G109 PA1200 PTR G103 PA1199 PA1198 PXY"],
      handler._callbacks,
    ).executeNextLine(0)

    self.assertEqual(len(seen), 1)
    self.assertEqual(seen[0]["line"], "G109 PA1200 PTR G103 PA1199 PA1198 PXY")
    self.assertEqual(seen[0]["anchorOrientation"], "TR")


if __name__ == "__main__":
  unittest.main()
