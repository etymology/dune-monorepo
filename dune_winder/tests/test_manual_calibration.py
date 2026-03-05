import os
import tempfile
import unittest

from dune_winder.core.manual_calibration import (
  LAYER_METADATA,
  ManualCalibration,
  _apply_transform,
  build_nominal_calibration,
  build_transform,
)
from dune_winder.core.anode_plane_array import AnodePlaneArray
from dune_winder.library.configuration import Configuration
from dune_winder.library.serializable_location import SerializableLocation
from dune_winder.recipes.xg_template_gcode import WIRE_SPACING as GX_WIRE_SPACING
from dune_winder.machine.layer_calibration import LayerCalibration
from dune_winder.machine.settings import Settings


class FakeLog:
  def __init__(self):
    self.entries = []

  def add(self, *args):
    self.entries.append(args)


class FakeTimeSource:
  def __init__(self):
    self.value = 0

  def get(self):
    self.value += 1
    return self.value


class FakeControlStateMachine:
  def __init__(self, ready=True):
    self.ready = ready

  def isReadyForMovement(self):
    return self.ready


class FakeAxis:
  def __init__(self, position=0.0):
    self.position = position

  def getPosition(self):
    return self.position


class FakeIO:
  def __init__(self):
    self.xAxis = FakeAxis()
    self.yAxis = FakeAxis()


class FakeGCodeHandler:
  def __init__(self):
    self.currentCalibration = None

  def useLayerCalibration(self, calibration):
    self.currentCalibration = calibration

  def getLayerCalibration(self):
    return self.currentCalibration


class FakeAPA:
  def __init__(self, layer, path, calibrationDirectory, recipeDirectory, recipeArchiveDirectory):
    self._layer = layer
    self._path = path
    self._calibrationDirectory = calibrationDirectory
    self._recipeDirectory = recipeDirectory
    self._recipeArchiveDirectory = recipeArchiveDirectory
    self._calibration = None
    self._calibrationFile = None
    self._calibrationSignature = None
    self._recipeFile = None
    self._gCodeHandler = None
    self.loadReasons = []
    self.recipeRefreshCalls = 0

  def getLayer(self):
    return self._layer

  def getPath(self):
    return self._path

  def _useCalibration(self, calibration, calibrationFile=None):
    if calibrationFile is not None:
      self._calibrationFile = calibrationFile

    self._calibration = calibration
    self._calibrationSignature = "test-signature"
    if self._gCodeHandler is not None:
      self._gCodeHandler.useLayerCalibration(calibration)

  def _loadCalibrationFromDisk(self, reloadReason=None):
    calibration = LayerCalibration(layer=self._layer)
    calibration.load(
      self._calibrationDirectory,
      self._calibrationFile,
      exceptionForMismatch=False,
    )
    self.loadReasons.append(reloadReason)
    self._useCalibration(calibration, self._calibrationFile)

  def refreshRecipeIfChanged(self):
    self.recipeRefreshCalls += 1


def _create_stub_apa(calibrationDirectory, apaPath, calibrationFile):
  apa = object.__new__(AnodePlaneArray)
  apa._calibrationDirectory = calibrationDirectory
  apa._calibrationFile = calibrationFile
  apa._gCodeHandler = FakeGCodeHandler()
  apa._log = FakeLog()
  apa._apaDirectory = apaPath
  apa._calibration = None
  apa._calibrationSignature = None
  return apa


class FakeProcess:
  def __init__(
    self,
    layer,
    calibrationDirectory,
    configuration,
    apaPath,
    recipeDirectory,
    recipeArchiveDirectory,
  ):
    self._configuration = configuration
    self._apaCalibrationDirectory = calibrationDirectory
    self._systemTime = FakeTimeSource()
    self._log = FakeLog()
    self.controlStateMachine = FakeControlStateMachine(True)
    self._io = FakeIO()
    self.gCodeHandler = FakeGCodeHandler()
    self.apa = FakeAPA(layer, apaPath, calibrationDirectory, recipeDirectory, recipeArchiveDirectory)
    self.apa._gCodeHandler = self.gCodeHandler
    self.seekCalls = []

  def getRecipeLayer(self):
    return self.apa.getLayer()

  def manualSeekXY(self, xPosition=None, yPosition=None, velocity=None, acceleration=None, deceleration=None):
    self.seekCalls.append((xPosition, yPosition, velocity, acceleration, deceleration))
    return False


def _create_process(layer, rootDirectory):
  calibrationDirectory = os.path.join(rootDirectory, "config", "APA")
  apaPath = os.path.join(rootDirectory, "cache", "APA")
  recipeDirectory = os.path.join(rootDirectory, "gc_files")
  recipeArchiveDirectory = os.path.join(rootDirectory, "cache", "Recipes")
  os.makedirs(calibrationDirectory, exist_ok=True)
  os.makedirs(apaPath, exist_ok=True)
  os.makedirs(recipeDirectory, exist_ok=True)
  os.makedirs(recipeArchiveDirectory, exist_ok=True)

  configurationPath = os.path.join(rootDirectory, "configuration.xml")
  configuration = Configuration(configurationPath)
  Settings.defaultConfig(configuration)
  configuration.save()

  if layer in ("U", "V"):
    liveCalibration = build_nominal_calibration(layer)
    liveCalibration.save(calibrationDirectory, layer + "_Calibration.xml", "LayerCalibration")

  return FakeProcess(
    layer,
    calibrationDirectory,
    configuration,
    apaPath,
    recipeDirectory,
    recipeArchiveDirectory,
  )


class ManualCalibrationTests(unittest.TestCase):
  def assertPointAlmostEqual(self, pointA, pointB):
    self.assertAlmostEqual(pointA[0], pointB[0], places=6)
    self.assertAlmostEqual(pointA[1], pointB[1], places=6)

  def test_layer_metadata_uses_expected_pin_counts_and_bootstrap(self):
    self.assertEqual(LAYER_METADATA["U"]["pinMax"], 2401)
    self.assertEqual(LAYER_METADATA["V"]["pinMax"], 2399)
    self.assertEqual(
      LAYER_METADATA["U"]["bootstrapPins"],
      [1, 200, 400, 401, 806, 1200, 1201, 1400, 1601, 1602, 1995, 2401],
    )
    self.assertEqual(
      LAYER_METADATA["V"]["bootstrapPins"],
      [1, 199, 399, 400, 805, 1199, 1200, 1399, 1599, 1600, 1993, 2399],
    )

    for layer in ("U", "V"):
      metadata = LAYER_METADATA[layer]
      for sideIndex, side in enumerate(("head", "bottom", "foot", "top")):
        sideBoards = [board for board in metadata["boards"] if board["side"] == side]
        sideMidpoint = (sideBoards[0]["startPin"] + sideBoards[-1]["endPin"]) / 2.0
        candidatePins = [board["endPin"] for board in sideBoards]

        bootstrapPin = metadata["bootstrapPins"][sideIndex * 3 + 1]
        self.assertEqual(
          bootstrapPin,
          min(candidatePins, key=lambda pin: (abs(pin - sideMidpoint), pin)),
        )

  def test_build_transform_covers_translation_similarity_and_affine(self):
    transform, mode = build_transform([(0.0, 0.0, 10.0, 5.0)])
    self.assertEqual(mode, "translation")
    self.assertPointAlmostEqual(_apply_transform(transform, 2.0, 3.0), (12.0, 8.0))

    transform, mode = build_transform([(0.0, 0.0, 1.0, 1.0), (1.0, 0.0, 1.0, 3.0)])
    self.assertEqual(mode, "similarity")
    self.assertPointAlmostEqual(_apply_transform(transform, 0.0, 1.0), (-1.0, 1.0))

    affinePairs = [
      (0.0, 0.0, 3.0, 4.0),
      (1.0, 0.0, 4.0, 3.0),
      (0.0, 1.0, 5.0, 5.0),
    ]
    transform, mode = build_transform(affinePairs)
    self.assertEqual(mode, "affine")
    self.assertPointAlmostEqual(_apply_transform(transform, 2.0, 3.0), (11.0, 5.0))

  def test_nominal_calibration_assigns_back_labels_to_back_side_geometry(self):
    for layer in ("U", "V"):
      calibration = build_nominal_calibration(layer)
      frontPin = calibration.getPinLocation("F1")
      backPin = calibration.getPinLocation("B1")
      self.assertGreater(backPin.y, frontPin.y)
      self.assertAlmostEqual(backPin.x, frontPin.x, places=6)

  def test_default_session_starts_nominal_and_recalibration_uses_live_geometry(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      process = _create_process("U", rootDirectory)
      liveCalibration = build_nominal_calibration("U")
      livePin = liveCalibration.getPinLocation("B1")
      liveCalibration.setPinLocation(
        "B1",
        SerializableLocation(livePin.x + 50.0, livePin.y - 25.0, livePin.z),
      )
      liveCalibration.save(process._apaCalibrationDirectory, "U_Calibration.xml", "LayerCalibration")

      service = ManualCalibration(process)
      nominalPin = build_nominal_calibration("U").getPinLocation("B1")

      state = service.getState()
      prediction = service.predictPin(1)

      self.assertEqual(state["baselineSource"], "nominal")
      self.assertAlmostEqual(prediction["wireX"], nominalPin.x, places=6)
      self.assertAlmostEqual(prediction["wireY"], nominalPin.y, places=6)

      loadResult = service.loadPrevious()
      self.assertTrue(loadResult["ok"])
      prediction = service.predictPin(1)

      self.assertEqual(service.getState()["baselineSource"], "live")
      self.assertAlmostEqual(prediction["wireX"], livePin.x + 50.0, places=6)
      self.assertAlmostEqual(prediction["wireY"], livePin.y - 25.0, places=6)

  def test_default_session_uses_loaded_runtime_calibration_when_present(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      process = _create_process("U", rootDirectory)
      calibration = build_nominal_calibration("U")
      baselineBack = calibration.getPinLocation("B1")
      calibration.setPinLocation(
        "B1",
        SerializableLocation(baselineBack.x + 25.0, baselineBack.y - 12.0, baselineBack.z),
      )
      process.apa._useCalibration(calibration, "U_Custom_Calibration.xml")

      service = ManualCalibration(process)
      state = service.getState()
      prediction = service.predictPin(1)

      self.assertEqual(state["baselineSource"], "loaded")
      self.assertAlmostEqual(prediction["wireX"], baselineBack.x + 25.0, places=6)
      self.assertAlmostEqual(prediction["wireY"], baselineBack.y - 12.0, places=6)
      self.assertFalse(state["dirty"])

  def test_capture_uses_camera_offset_and_goto_uses_camera_target(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      process = _create_process("U", rootDirectory)
      service = ManualCalibration(process)

      service.startNew()
      service.setCameraOffset(10.0, -5.0)
      process._io.xAxis.position = 100.0
      process._io.yAxis.position = 200.0

      captureResult = service.captureCurrentPin(1)
      self.assertTrue(captureResult["ok"])
      session = service._getSession("U")
      self.assertAlmostEqual(session.measuredPins[1]["wireX"], 110.0)
      self.assertAlmostEqual(session.measuredPins[1]["wireY"], 195.0)

      gotoResult = service.gotoPin(1, 25.0)
      self.assertTrue(gotoResult["ok"])
      self.assertEqual(len(process.seekCalls), 1)
      self.assertAlmostEqual(process.seekCalls[0][0], 100.0)
      self.assertAlmostEqual(process.seekCalls[0][1], 200.0)
      self.assertAlmostEqual(process.seekCalls[0][2], 25.0)

  def test_front_pin_prediction_uses_mapped_back_pin_correction(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      process = _create_process("U", rootDirectory)
      service = ManualCalibration(process)

      service.startNew()
      session = service._getSession("U")
      baselineBack = session.baselineCalibration.getPinLocation("B1")
      baselineFront = session.baselineCalibration.getPinLocation("F400")

      service.updateMeasuredPin(1, baselineBack.x + 10.0, baselineBack.y + 5.0)
      context = service._buildPredictionContext(session)
      predictedFront = service._predictFrontPin(session, context, 400)

      self.assertAlmostEqual(predictedFront[0], baselineFront.x + 10.0, places=6)
      self.assertAlmostEqual(predictedFront[1], baselineFront.y + 5.0, places=6)

  def test_save_live_writes_offset_zero_file_and_reloads_runtime_calibration(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      process = _create_process("U", rootDirectory)
      service = ManualCalibration(process)

      service.startNew()
      session = service._getSession("U")
      baselineBack = session.baselineCalibration.getPinLocation("B1")
      service.updateMeasuredPin(1, baselineBack.x + 7.0, baselineBack.y - 3.0)

      saveResult = service.saveLive()
      self.assertTrue(saveResult["ok"])

      savedPath = os.path.join(process._apaCalibrationDirectory, "U_Calibration.xml")
      self.assertTrue(os.path.isfile(savedPath))
      self.assertIsNotNone(process.gCodeHandler.currentCalibration)
      self.assertEqual(process.apa._calibrationFile, "U_Calibration.xml")
      self.assertEqual(process.apa.loadReasons, ["manual calibration save"])

      savedCalibration = LayerCalibration(layer="U")
      savedCalibration.load(process._apaCalibrationDirectory, "U_Calibration.xml")
      self.assertAlmostEqual(savedCalibration.offset.x, 0.0)
      self.assertAlmostEqual(savedCalibration.offset.y, 0.0)
      self.assertAlmostEqual(savedCalibration.getPinLocation("B1").x, baselineBack.x + 7.0, places=6)
      self.assertAlmostEqual(savedCalibration.getPinLocation("B1").y, baselineBack.y - 3.0, places=6)
      self.assertFalse(service.getState()["dirty"])

  def test_draft_persists_without_overwriting_live_calibration(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      process = _create_process("U", rootDirectory)
      service = ManualCalibration(process)

      service.startNew()
      session = service._getSession("U")
      baselineBack = session.baselineCalibration.getPinLocation("B1")

      service.setCameraOffset(12.5, -7.5)
      service.updateMeasuredPin(1, baselineBack.x + 4.0, baselineBack.y - 2.0)

      draftDirectory = os.path.join(process.apa.getPath(), "ManualCalibration")
      self.assertTrue(os.path.isfile(os.path.join(draftDirectory, "U_Draft.json")))
      self.assertTrue(os.path.isfile(os.path.join(draftDirectory, "U_DraftBaseline.xml")))

      liveCalibration = LayerCalibration(layer="U")
      liveCalibration.load(process._apaCalibrationDirectory, "U_Calibration.xml")
      self.assertAlmostEqual(liveCalibration.getPinLocation("B1").x, baselineBack.x, places=6)
      self.assertAlmostEqual(liveCalibration.getPinLocation("B1").y, baselineBack.y, places=6)

      reloadedService = ManualCalibration(process)
      state = reloadedService.getState()
      prediction = reloadedService.predictPin(1)

      self.assertTrue(state["dirty"])
      self.assertEqual(state["counts"]["measuredPins"], 1)
      self.assertAlmostEqual(state["cameraOffsetX"], 12.5, places=6)
      self.assertAlmostEqual(state["cameraOffsetY"], -7.5, places=6)
      self.assertAlmostEqual(prediction["wireX"], baselineBack.x + 4.0, places=6)
      self.assertAlmostEqual(prediction["wireY"], baselineBack.y - 2.0, places=6)

  def test_xg_layer_reports_enabled_state_and_capture_uses_camera_offset(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      process = _create_process("X", rootDirectory)
      service = ManualCalibration(process)

      state = service.getState()
      self.assertTrue(state["enabled"])
      self.assertEqual(state["mode"], "gx")
      self.assertEqual(state["outputKind"], "gc")
      self.assertEqual(state["counts"]["referencePointsRecorded"], 0)
      self.assertEqual(state["counts"]["referencePointsTotal"], 2)
      self.assertEqual(state["wrapCount"], 480)
      self.assertAlmostEqual(state["wireSpacing"], GX_WIRE_SPACING, places=6)
      self.assertTrue(state["transferPause"])
      self.assertAlmostEqual(state["references"]["head"]["wireX"], 570.0)
      self.assertAlmostEqual(state["references"]["head"]["wireY"], 170.0)
      self.assertAlmostEqual(state["references"]["foot"]["wireX"], 6970.0)
      self.assertAlmostEqual(state["references"]["foot"]["wireY"], 170.0)

      service.setCameraOffset(10.0, -5.0)
      process._io.xAxis.position = 100.0
      process._io.yAxis.position = 200.0

      captureResult = service.captureCurrentReference("head")
      self.assertTrue(captureResult["ok"])

      state = service.getState()
      head = state["references"]["head"]
      self.assertAlmostEqual(head["rawCameraX"], 100.0)
      self.assertAlmostEqual(head["rawCameraY"], 200.0)
      self.assertAlmostEqual(head["wireX"], 110.0)
      self.assertAlmostEqual(head["wireY"], 195.0)
      self.assertEqual(head["source"], "capture")

  def test_xg_state_uses_loaded_runtime_calibration_references_when_present(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      process = _create_process("X", rootDirectory)
      calibration = LayerCalibration(layer="X")
      calibration.offset = SerializableLocation(0.0, 0.0, 0.0)
      calibration.zFront = 0.0
      calibration.zBack = 0.0
      calibration.setPinLocation("B960", SerializableLocation(612.5, 182.25, 0.0))
      calibration.setPinLocation("B1", SerializableLocation(7012.0, 184.75, 0.0))
      process.apa._useCalibration(calibration, "X_Custom_Calibration.xml")

      service = ManualCalibration(process)
      state = service.getState()

      self.assertEqual(state["references"]["head"]["source"], "loaded")
      self.assertEqual(state["references"]["foot"]["source"], "loaded")
      self.assertAlmostEqual(state["references"]["head"]["wireX"], 612.5, places=6)
      self.assertAlmostEqual(state["references"]["head"]["wireY"], 182.25, places=6)
      self.assertAlmostEqual(state["references"]["foot"]["wireX"], 7012.0, places=6)
      self.assertAlmostEqual(state["references"]["foot"]["wireY"], 184.75, places=6)
      self.assertEqual(state["counts"]["referencePointsRecorded"], 2)
      self.assertFalse(state["readyToGenerate"])

  def test_xg_goto_reference_uses_selected_reference_target(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      process = _create_process("X", rootDirectory)
      service = ManualCalibration(process)

      service.setCameraOffset(10.0, -5.0)

      defaultMove = service.gotoReference("head", 321.0)
      self.assertTrue(defaultMove["ok"])
      self.assertEqual(
        process.seekCalls[-1],
        (560.0, 175.0, 321.0, None, None),
      )
      self.assertEqual(defaultMove["data"]["pinName"], "B960")
      self.assertAlmostEqual(defaultMove["data"]["cameraX"], 560.0, places=6)
      self.assertAlmostEqual(defaultMove["data"]["cameraY"], 175.0, places=6)

      process._io.xAxis.position = 100.0
      process._io.yAxis.position = 200.0
      service.captureCurrentReference("head")

      capturedMove = service.gotoReference("head", 654.0)
      self.assertTrue(capturedMove["ok"])
      self.assertEqual(
        process.seekCalls[-1],
        (100.0, 200.0, 654.0, None, None),
      )
      self.assertAlmostEqual(capturedMove["data"]["wireX"], 110.0, places=6)
      self.assertAlmostEqual(capturedMove["data"]["wireY"], 195.0, places=6)

  def test_xg_generate_writes_live_gcode_and_refreshes_active_recipe(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      process = _create_process("X", rootDirectory)
      process.apa._recipeFile = "X-layer.gc"
      service = ManualCalibration(process)

      service.setCameraOffset(10.0, -5.0)
      process._io.xAxis.position = 100.0
      process._io.yAxis.position = 200.0
      service.captureCurrentReference("head")
      process._io.xAxis.position = 300.0
      process._io.yAxis.position = 400.0
      service.captureCurrentReference("foot")

      service.setCornerOffset("headA", 1.0)
      service.setCornerOffset("headB", 2.0)
      service.setCornerOffset("footA", 3.0)
      service.setCornerOffset("footB", 4.0)
      service.setTransferPause(False)

      generateResult = service.generateRecipeFile()
      self.assertTrue(generateResult["ok"])

      outputPath = os.path.join(process.apa._recipeDirectory, "X-layer.gc")
      self.assertTrue(os.path.isfile(outputPath))
      self.assertEqual(process.apa.recipeRefreshCalls, 1)

      with open(outputPath) as inputFile:
        lines = inputFile.readlines()

      self.assertTrue(lines[0].startswith("( X-layer "))
      self.assertEqual(lines[1], "N0 X440.0 Y196.0\n")
      self.assertEqual(lines[2], "N1 G106 P0\n")
      self.assertEqual(lines[3], "N2 (1,1) X635.0 Y196.0\n")
      self.assertEqual(lines[4], "N3 (1,2) X7165.0 Y398.0\n")
      self.assertEqual(lines[5], "N4 (1,3) G106 P0\n")
      self.assertEqual(lines[6], "N5 (1,4) G106 P3\n")
      self.assertEqual(lines[7], "N6 (1,5) X7016.0 Y399.0\n")
      self.assertEqual(lines[-1], "N3842 X635.0 Y2496.0\n")

      state = service.getState()
      self.assertFalse(state["dirty"])
      self.assertTrue(state["readyToGenerate"])
      self.assertEqual(state["generated"]["filePath"], outputPath)
      self.assertEqual(state["generated"]["wrapCount"], 480)
      self.assertIsNotNone(state["generated"]["hashValue"])

  def test_xg_draft_persists_without_writing_live_recipe(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      process = _create_process("G", rootDirectory)
      service = ManualCalibration(process)

      service.setCameraOffset(12.5, -7.5)
      process._io.xAxis.position = 10.0
      process._io.yAxis.position = 20.0
      service.captureCurrentReference("head")
      process._io.xAxis.position = 30.0
      process._io.yAxis.position = 40.0
      service.captureCurrentReference("foot")
      service.setCornerOffset("headA", 0.1)
      service.setCornerOffset("headB", 0.2)
      service.setCornerOffset("footA", 0.3)
      service.setCornerOffset("footB", 0.4)

      draftDirectory = os.path.join(process.apa.getPath(), "ManualCalibration")
      self.assertTrue(os.path.isfile(os.path.join(draftDirectory, "G_Draft.json")))
      self.assertFalse(os.path.isfile(os.path.join(process.apa._recipeDirectory, "G-layer.gc")))

      reloadedService = ManualCalibration(process)
      state = reloadedService.getState()

      self.assertTrue(state["dirty"])
      self.assertEqual(state["mode"], "gx")
      self.assertEqual(state["counts"]["referencePointsRecorded"], 2)
      self.assertAlmostEqual(state["cameraOffsetX"], 12.5, places=6)
      self.assertAlmostEqual(state["cameraOffsetY"], -7.5, places=6)
      self.assertAlmostEqual(state["references"]["head"]["wireX"], 22.5, places=6)
      self.assertAlmostEqual(state["references"]["head"]["wireY"], 12.5, places=6)
      self.assertEqual(state["offsets"]["footB"], 0.4)

  def test_unsupported_layer_reports_disabled_state(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      process = _create_process("Z", rootDirectory)
      service = ManualCalibration(process)

      state = service.getState()
      self.assertFalse(state["enabled"])
      self.assertIn("only available", state["disabledReason"])

  def test_hashless_calibration_refreshes_runtime_calibration_when_file_changes(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      calibrationDirectory = os.path.join(rootDirectory, "config", "APA")
      apaPath = os.path.join(rootDirectory, "cache", "APA")
      os.makedirs(calibrationDirectory, exist_ok=True)
      os.makedirs(apaPath, exist_ok=True)

      calibration = build_nominal_calibration("U")
      baselineBack = calibration.getPinLocation("B1")
      calibration.save(calibrationDirectory, "U_Calibration.xml", "LayerCalibration")

      apa = _create_stub_apa(calibrationDirectory, apaPath, "U_Calibration.xml")
      apa._loadCalibrationFromDisk()

      loadedBack = apa._gCodeHandler.currentCalibration.getPinLocation("B1")
      self.assertAlmostEqual(loadedBack.x, baselineBack.x, places=6)
      self.assertAlmostEqual(loadedBack.y, baselineBack.y, places=6)
      self.assertIsNotNone(apa._calibrationSignature)
      self.assertFalse(
        any("Invalid calibration hash" in entry[2] for entry in apa._log.entries)
      )

      updated = build_nominal_calibration("U")
      updated.setPinLocation(
        "B1",
        SerializableLocation(baselineBack.x + 12.0, baselineBack.y - 4.0, baselineBack.z),
      )
      updated.save(calibrationDirectory, "U_Calibration.xml", "LayerCalibration")

      previousSignature = apa._calibrationSignature
      apa.refreshCalibrationIfChanged()

      refreshedBack = apa._gCodeHandler.currentCalibration.getPinLocation("B1")
      self.assertAlmostEqual(refreshedBack.x, baselineBack.x + 12.0, places=6)
      self.assertAlmostEqual(refreshedBack.y, baselineBack.y - 4.0, places=6)
      self.assertNotEqual(apa._calibrationSignature, previousSignature)
      self.assertTrue(
        any("Detected calibration file change" in entry[2] for entry in apa._log.entries)
      )
      self.assertTrue(
        any("Reloaded calibration file" in entry[2] for entry in apa._log.entries)
      )


if __name__ == "__main__":
  unittest.main()
