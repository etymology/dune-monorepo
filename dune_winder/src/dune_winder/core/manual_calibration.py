###############################################################################
# Name: ManualCalibration.py
# Uses: Manual calibration workflow for U/V layers.
# Date: 2026-03-02
###############################################################################

import math
import os
import json

from dune_winder.library.Geometry.location import Location
from dune_winder.library.serializable_location import SerializableLocation
from dune_winder.recipes.xg_template_gcode import (
  WIRE_SPACING as GX_WIRE_SPACING,
  WRAP_COUNTS as GX_WRAP_COUNTS,
  get_xg_recipe_file_name,
  write_xg_template_file,
)
from dune_winder.machine.geometry.factory import create_layer_geometry
from dune_winder.machine.calibration.layer import LayerCalibration
from dune_winder.machine.geometry.layer_functions import LayerFunctions
from dune_winder.machine.settings import Settings


UV_LAYERS = ("U", "V")
GX_LAYERS = ("X", "G")
SUPPORTED_LAYERS = UV_LAYERS + GX_LAYERS
SIDE_ORDER = ("head", "bottom", "foot", "top")
EPSILON = 1e-9

CAMERA_OFFSET_DEFAULTS = {
  "U": (65.0, -108.2),
  "V": (65.0, -108.2),
  "X": (65.0, -108.2),
  "G": (65.0, -108.2),
}

GX_REFERENCE_IDS = ("head", "foot")
GX_REFERENCE_LABELS = {
  "head": "B960 (head)",
  "foot": "B1 (foot)",
}
GX_REFERENCE_PIN_NAMES = {
  "head": "B960",
  "foot": "B1",
}
GX_REFERENCE_DEFAULT_WIRE_POSITIONS = {
  "head": (570.0, 170.0),
  "foot": (6970.0, 170.0),
}
GX_OFFSET_IDS = ("headA", "headB", "footA", "footB")

SIDE_RANGES = {
  "U": {
    "head": (1, 400),
    "bottom": (401, 1200),
    "foot": (1201, 1601),
    "top": (1602, 2401),
  },
  "V": {
    "head": (1, 399),
    "bottom": (400, 1199),
    "foot": (1200, 1599),
    "top": (1600, 2399),
  },
}

LAYER_ENDPOINTS = {
  "U": (
    1, 40, 41, 80, 81, 120, 121, 160, 161, 200, 201, 240, 241, 280, 281, 320,
    321, 360, 361, 400, 401, 424, 425, 449, 450, 473, 474, 510, 511, 547, 548,
    584, 585, 621, 622, 658, 659, 695, 696, 732, 733, 769, 770, 806,
    807, 843, 844, 880, 881, 917, 918, 954, 955, 991, 992, 1028, 1029, 1065,
    1066, 1102, 1103, 1139, 1140, 1176, 1177, 1200, 1201, 1240, 1241, 1280,
    1281, 1320, 1321, 1360, 1361, 1400, 1401, 1440, 1441, 1480, 1481, 1520,
    1521, 1560, 1561, 1601, 1602, 1625, 1626, 1662, 1663, 1699, 1700, 1736,
    1737, 1773, 1774, 1810, 1811, 1847, 1848, 1884, 1885, 1921, 1922, 1958,
    1959, 1995, 1996, 2032, 2033, 2069, 2070, 2106, 2107, 2143,
    2144, 2180, 2181, 2217, 2218, 2254, 2255, 2291, 2292, 2328, 2329, 2352,
    2353, 2377, 2378, 2401,
  ),
  "V": (
    1, 39, 40, 79, 80, 119, 120, 159, 160, 199, 200, 239, 240, 279, 280, 319,
    320, 359, 360, 399, 400, 423, 424, 448, 449, 472, 473, 509, 510, 546, 547,
    583, 584, 620, 621, 657, 658, 694, 695, 731, 732, 768, 769, 805,
    806, 842, 843, 879, 880, 916, 917, 953, 954, 990, 991, 1027, 1028, 1064,
    1065, 1101, 1102, 1138, 1139, 1175, 1176, 1199, 1200, 1239, 1240, 1279,
    1280, 1319, 1320, 1359, 1360, 1399, 1400, 1439, 1440, 1479, 1480, 1519,
    1520, 1559, 1560, 1599, 1600, 1623, 1624, 1660, 1661, 1697, 1698, 1734,
    1735, 1771, 1772, 1808, 1809, 1845, 1846, 1882, 1883, 1919, 1920, 1956,
    1957, 1993, 1994, 2030, 2031, 2067, 2068, 2104, 2105, 2141,
    2142, 2178, 2179, 2215, 2216, 2252, 2253, 2289, 2290, 2326, 2327, 2350,
    2351, 2375, 2376, 2399,
  ),
}


def _pairwise(values):
  pairs = []
  for index in range(0, len(values), 2):
    pairs.append((values[index], values[index + 1]))
  return pairs


def _layer_offset_key(layer, axis):
  return "manualCalibrationOffset" + layer + axis


def _mode_for_layer(layer):
  if layer in UV_LAYERS:
    return "uv"
  if layer in GX_LAYERS:
    return "gx"
  return None


def _safe_float(value, defaultValue):
  try:
    return float(value)
  except (TypeError, ValueError):
    return float(defaultValue)


def _normalize_pin(pin):
  if isinstance(pin, str):
    pin = pin.strip().upper()
    if pin.startswith("B") or pin.startswith("F"):
      pin = pin[1:]
    pin = int(float(pin))
  else:
    pin = int(pin)

  return pin


def _apply_transform(transform, xValue, yValue):
  return (
    transform["a"] * xValue + transform["b"] * yValue + transform["c"],
    transform["d"] * xValue + transform["e"] * yValue + transform["f"],
  )


def _solve_linear_system(matrix, vector):
  size = len(vector)
  augmented = []
  for rowIndex in range(size):
    row = list(matrix[rowIndex])
    row.append(vector[rowIndex])
    augmented.append(row)

  for column in range(size):
    pivotRow = max(range(column, size), key=lambda rowIndex: abs(augmented[rowIndex][column]))
    pivotValue = augmented[pivotRow][column]
    if abs(pivotValue) < EPSILON:
      return None

    if pivotRow != column:
      augmented[column], augmented[pivotRow] = augmented[pivotRow], augmented[column]

    pivotValue = augmented[column][column]
    for rowIndex in range(column + 1, size):
      scale = augmented[rowIndex][column] / pivotValue
      for valueIndex in range(column, size + 1):
        augmented[rowIndex][valueIndex] -= scale * augmented[column][valueIndex]

  result = [0.0] * size
  for rowIndex in range(size - 1, -1, -1):
    value = augmented[rowIndex][size]
    for column in range(rowIndex + 1, size):
      value -= augmented[rowIndex][column] * result[column]

    pivotValue = augmented[rowIndex][rowIndex]
    if abs(pivotValue) < EPSILON:
      return None

    result[rowIndex] = value / pivotValue

  return result


def _translation_transform(pair):
  sourceX, sourceY, targetX, targetY = pair
  return {
    "a": 1.0,
    "b": 0.0,
    "c": targetX - sourceX,
    "d": 0.0,
    "e": 1.0,
    "f": targetY - sourceY,
  }


def _similarity_transform(firstPair, secondPair):
  sourceAX, sourceAY, targetAX, targetAY = firstPair
  sourceBX, sourceBY, targetBX, targetBY = secondPair

  deltaSourceX = sourceBX - sourceAX
  deltaSourceY = sourceBY - sourceAY
  deltaTargetX = targetBX - targetAX
  deltaTargetY = targetBY - targetAY

  sourceLength = math.hypot(deltaSourceX, deltaSourceY)
  targetLength = math.hypot(deltaTargetX, deltaTargetY)
  if sourceLength < EPSILON or targetLength < EPSILON:
    return _translation_transform(firstPair)

  scale = targetLength / sourceLength
  rotation = math.atan2(deltaTargetY, deltaTargetX) - math.atan2(deltaSourceY, deltaSourceX)

  cosine = math.cos(rotation) * scale
  sine = math.sin(rotation) * scale

  return {
    "a": cosine,
    "b": -sine,
    "c": targetAX - cosine * sourceAX + sine * sourceAY,
    "d": sine,
    "e": cosine,
    "f": targetAY - sine * sourceAX - cosine * sourceAY,
  }


def _affine_transform(pairs):
  if len(pairs) < 3:
    return None

  sumXX = 0.0
  sumXY = 0.0
  sumYY = 0.0
  sumX = 0.0
  sumY = 0.0
  count = 0.0

  sumTargetXX = 0.0
  sumTargetYX = 0.0
  sumTargetX = 0.0
  sumTargetXY = 0.0
  sumTargetYY = 0.0
  sumTargetY = 0.0

  for sourceX, sourceY, targetX, targetY in pairs:
    sumXX += sourceX * sourceX
    sumXY += sourceX * sourceY
    sumYY += sourceY * sourceY
    sumX += sourceX
    sumY += sourceY
    count += 1.0

    sumTargetXX += sourceX * targetX
    sumTargetYX += sourceY * targetX
    sumTargetX += targetX

    sumTargetXY += sourceX * targetY
    sumTargetYY += sourceY * targetY
    sumTargetY += targetY

  matrix = [
    [sumXX, sumXY, sumX],
    [sumXY, sumYY, sumY],
    [sumX, sumY, count],
  ]

  xSolution = _solve_linear_system(matrix, [sumTargetXX, sumTargetYX, sumTargetX])
  ySolution = _solve_linear_system(matrix, [sumTargetXY, sumTargetYY, sumTargetY])
  if xSolution is None or ySolution is None:
    return None

  return {
    "a": xSolution[0],
    "b": xSolution[1],
    "c": xSolution[2],
    "d": ySolution[0],
    "e": ySolution[1],
    "f": ySolution[2],
  }


def _farthest_pair(pairs):
  farthest = None
  farthestDistance = -1.0
  for firstIndex in range(len(pairs)):
    sourceAX = pairs[firstIndex][0]
    sourceAY = pairs[firstIndex][1]
    for secondIndex in range(firstIndex + 1, len(pairs)):
      sourceBX = pairs[secondIndex][0]
      sourceBY = pairs[secondIndex][1]
      distance = (sourceBX - sourceAX) ** 2 + (sourceBY - sourceAY) ** 2
      if distance > farthestDistance:
        farthestDistance = distance
        farthest = (pairs[firstIndex], pairs[secondIndex])

  return farthest


def build_transform(pairs):
  if len(pairs) == 0:
    return (
      {"a": 1.0, "b": 0.0, "c": 0.0, "d": 0.0, "e": 1.0, "f": 0.0},
      "identity",
    )

  if len(pairs) == 1:
    return (_translation_transform(pairs[0]), "translation")

  if len(pairs) == 2:
    return (_similarity_transform(pairs[0], pairs[1]), "similarity")

  transform = _affine_transform(pairs)
  if transform is not None:
    return (transform, "affine")

  farthest = _farthest_pair(pairs)
  if farthest is not None:
    return (_similarity_transform(farthest[0], farthest[1]), "similarity")

  return (_translation_transform(pairs[0]), "translation")


def _cyclic_pin_distance(pinA, pinB, pinMax):
  delta = abs(pinA - pinB)
  return min(delta, pinMax - delta)


def _interpolate_residual(pinA, residualA, pinB, residualB, pinValue):
  if pinA == pinB:
    return residualA

  fraction = float(pinValue - pinA) / float(pinB - pinA)
  return (
    residualA[0] + (residualB[0] - residualA[0]) * fraction,
    residualA[1] + (residualB[1] - residualA[1]) * fraction,
  )


def _absolute_location(calibration, pinName):
  location = calibration.getPinLocation(pinName)
  offset = calibration.offset
  if offset is None:
    offset = SerializableLocation()

  return Location(location.x + offset.x, location.y + offset.y, location.z + offset.z)


def normalize_calibration(calibration, layer):
  normalized = LayerCalibration(layer=layer)
  normalized.zFront = calibration.zFront
  normalized.zBack = calibration.zBack
  normalized.offset = SerializableLocation(0.0, 0.0, 0.0)

  for pinName in calibration.getPinNames():
    location = _absolute_location(calibration, pinName)
    normalized.setPinLocation(pinName, location)

  return normalized


def build_nominal_calibration(layer):
  geometry = create_layer_geometry(layer)
  calibration = LayerCalibration(layer=layer)
  calibration.zFront = geometry.mostlyRetract
  calibration.zBack = geometry.mostlyExtend
  calibration.offset = SerializableLocation(0.0, 0.0, 0.0)

  origin = geometry.apaLocation.add(geometry.apaOffset)
  grids = [
    ("F", geometry.gridBack, geometry.mostlyRetract, geometry.startPinBack, geometry.directionBack),
    ("B", geometry.gridFront, geometry.mostlyExtend, geometry.startPinFront, geometry.directionFront),
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
          side + str(pinNumber),
          Location(round(xValue, 5) + origin.x, round(yValue, 5) + origin.y, depth),
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

  return calibration


def _side_for_pin(layer, pin):
  for side in SIDE_ORDER:
    startPin, endPin = SIDE_RANGES[layer][side]
    if startPin <= pin <= endPin:
      return side

  raise ValueError("Pin " + str(pin) + " is outside " + str(layer) + " metadata.")


def _bootstrap_pins_for_side(sideBoards):
  if 0 == len(sideBoards):
    return []

  firstPin = sideBoards[0]["startPin"]
  lastPin = sideBoards[-1]["endPin"]
  midpoint = (firstPin + lastPin) / 2.0
  candidatePins = [board["endPin"] for board in sideBoards]

  middlePin = min(candidatePins, key=lambda pin: (abs(pin - midpoint), pin))
  return [firstPin, middlePin, lastPin]


def _build_layer_metadata(layer):
  geometry = create_layer_geometry(layer)
  pinMax = int(geometry.pins)
  endpoints = LAYER_ENDPOINTS[layer]
  if endpoints[-1] != pinMax:
    raise ValueError("Endpoint metadata does not match geometry for layer " + layer + ".")

  boards = []
  endpointInfo = {}
  pinToBoard = {}
  sideBoardCounts = {}
  sideBoards = {}
  for side in SIDE_ORDER:
    sideBoardCounts[side] = 0
    sideBoards[side] = []

  for boardIndex, (startPin, endPin) in enumerate(_pairwise(endpoints), start=1):
    side = _side_for_pin(layer, startPin)
    sideBoardCounts[side] += 1
    sideIndex = sideBoardCounts[side]

    board = {
      "boardIndex": boardIndex,
      "side": side,
      "sideIndex": sideIndex,
      "startPin": startPin,
      "endPin": endPin,
    }
    boards.append(board)
    sideBoards[side].append(board)

    endpointInfo[startPin] = {
      "pin": startPin,
      "boardIndex": boardIndex,
      "side": side,
      "sideIndex": sideIndex,
      "endpoint": "start",
    }
    endpointInfo[endPin] = {
      "pin": endPin,
      "boardIndex": boardIndex,
      "side": side,
      "sideIndex": sideIndex,
      "endpoint": "end",
    }

    for pin in range(startPin, endPin + 1):
      pinToBoard[pin] = board

  bootstrapPins = []
  for side in SIDE_ORDER:
    bootstrapPins.extend(_bootstrap_pins_for_side(sideBoards[side]))

  return {
    "layer": layer,
    "pinMax": pinMax,
    "geometry": geometry,
    "boards": boards,
    "endpointInfo": endpointInfo,
    "endpointPins": list(endpoints),
    "pinToBoard": pinToBoard,
    "bootstrapPins": bootstrapPins,
    "bootstrapSet": set(bootstrapPins),
    "sideRanges": SIDE_RANGES[layer],
  }


LAYER_METADATA = {}
for _layerName in UV_LAYERS:
  LAYER_METADATA[_layerName] = _build_layer_metadata(_layerName)


class _ManualCalibrationSession:
  def __init__(self, layer, cameraOffsetX, cameraOffsetY):
    self.mode = "uv"
    self.initialized = False
    self.layer = layer
    self.cameraOffsetX = cameraOffsetX
    self.cameraOffsetY = cameraOffsetY
    self.baselineSource = None
    self.baselineCalibration = None
    self.measuredPins = {}
    self.boardChecks = {}
    self.dirty = False


class _ManualCalibrationGXSession:
  def __init__(self, layer, cameraOffsetX, cameraOffsetY):
    self.mode = "gx"
    self.initialized = False
    self.layer = layer
    self.cameraOffsetX = cameraOffsetX
    self.cameraOffsetY = cameraOffsetY
    self.references = {}
    self.offsets = {}
    self.transferPause = True
    self.includeLeadMode = True
    self.generated = {}
    self.dirty = False


class ManualCalibration:
  def __init__(self, process):
    self._process = process
    self._sessions = {}

  # -------------------------------------------------------------------
  def _sessionKey(self, layer):
    return (self._draftDirectory(), layer)

  # -------------------------------------------------------------------
  def _draftDirectory(self):
    if self._process.workspace is not None:
      return os.path.join(self._process.workspace.getPath(), "ManualCalibration")

    return os.path.join(self._process._workspaceCalibrationDirectory, "ManualCalibration")

  # -------------------------------------------------------------------
  def _draftFileName(self, layer):
    return layer + "_Draft.json"

  # -------------------------------------------------------------------
  def _draftFilePath(self, layer):
    return os.path.join(self._draftDirectory(), self._draftFileName(layer))

  # -------------------------------------------------------------------
  def _draftBaselineFileName(self, layer):
    return layer + "_DraftBaseline.json"

  # -------------------------------------------------------------------
  def _draftBaselinePath(self, layer):
    return os.path.join(self._draftDirectory(), self._draftBaselineFileName(layer))

  # -------------------------------------------------------------------
  def _optionalFloat(self, value):
    if value is None or "" == value:
      return None

    return float(value)

  # -------------------------------------------------------------------
  def _loadDraftBaseline(self, session, baselineSource):
    baselinePath = self._draftBaselinePath(session.layer)
    if os.path.isfile(baselinePath):
      calibration = LayerCalibration(layer=session.layer)
      calibration.load(
        self._draftDirectory(),
        self._draftBaselineFileName(session.layer),
        exceptionForMismatch=False,
      )
      session.baselineCalibration = normalize_calibration(calibration, session.layer)
      session.baselineSource = baselineSource
      return True

    if "live" == baselineSource:
      error = self._resetToLive(session, allowFallback=True)
      return error is None

    self._resetToNominal(session)
    return True

  # -------------------------------------------------------------------
  def _emptyGXReference(self, referenceId):
    defaultWireX, defaultWireY = GX_REFERENCE_DEFAULT_WIRE_POSITIONS[referenceId]
    return {
      "id": referenceId,
      "label": GX_REFERENCE_LABELS[referenceId],
      "pinName": GX_REFERENCE_PIN_NAMES[referenceId],
      "rawCameraX": None,
      "rawCameraY": None,
      "offsetX": None,
      "offsetY": None,
      "wireX": defaultWireX,
      "wireY": defaultWireY,
      "updatedAt": "",
      "source": None,
    }

  # -------------------------------------------------------------------
  def _emptyGXGenerated(self, session):
    return {
      "filePath": self._liveFilePath(session.layer),
      "hashValue": None,
      "updatedAt": None,
      "wrapCount": GX_WRAP_COUNTS[session.layer],
    }

  # -------------------------------------------------------------------
  def _loadPersistedGXSession(self, session, data):
    session.cameraOffsetX = float(data.get("cameraOffsetX", session.cameraOffsetX))
    session.cameraOffsetY = float(data.get("cameraOffsetY", session.cameraOffsetY))

    references = {}
    storedReferences = data.get("references", {})
    for referenceId in GX_REFERENCE_IDS:
      reference = self._emptyGXReference(referenceId)
      storedReference = storedReferences.get(referenceId)
      if storedReference is not None:
        reference["rawCameraX"] = self._optionalFloat(storedReference.get("rawCameraX"))
        reference["rawCameraY"] = self._optionalFloat(storedReference.get("rawCameraY"))
        reference["offsetX"] = self._optionalFloat(storedReference.get("offsetX"))
        reference["offsetY"] = self._optionalFloat(storedReference.get("offsetY"))
        reference["wireX"] = self._optionalFloat(storedReference.get("wireX"))
        reference["wireY"] = self._optionalFloat(storedReference.get("wireY"))
        reference["updatedAt"] = str(storedReference.get("updatedAt", ""))
        source = storedReference.get("source")
        reference["source"] = None if source is None else str(source)
      references[referenceId] = reference
    session.references = references

    offsets = {}
    storedOffsets = data.get("offsets", {})
    for offsetId in GX_OFFSET_IDS:
      offsets[offsetId] = self._optionalFloat(storedOffsets.get(offsetId))
    session.offsets = offsets

    session.transferPause = bool(data.get("transferPause", True))
    session.includeLeadMode = bool(data.get("includeLeadMode", True))
    session.generated = self._emptyGXGenerated(session)
    generated = data.get("generated", {})
    if generated is not None:
      filePath = generated.get("filePath", session.generated["filePath"])
      if filePath is not None:
        session.generated["filePath"] = str(filePath)
      session.generated["hashValue"] = generated.get("hashValue")
      session.generated["updatedAt"] = generated.get("updatedAt")
      wrapCount = generated.get("wrapCount", session.generated["wrapCount"])
      if wrapCount is not None:
        session.generated["wrapCount"] = int(wrapCount)

    session.dirty = bool(data.get("dirty", False))
    session.initialized = True

  # -------------------------------------------------------------------
  def _persistGXSession(self, session):
    try:
      draftDirectory = self._draftDirectory()
      if not os.path.isdir(draftDirectory):
        os.makedirs(draftDirectory)

      data = {
        "layer": session.layer,
        "cameraOffsetX": session.cameraOffsetX,
        "cameraOffsetY": session.cameraOffsetY,
        "dirty": session.dirty,
        "transferPause": session.transferPause,
        "includeLeadMode": session.includeLeadMode,
        "references": {},
        "offsets": {},
        "generated": dict(session.generated),
      }

      for referenceId in GX_REFERENCE_IDS:
        data["references"][referenceId] = dict(session.references[referenceId])

      for offsetId in GX_OFFSET_IDS:
        data["offsets"][offsetId] = session.offsets[offsetId]

      temporaryPath = self._draftFilePath(session.layer) + ".tmp"
      with open(temporaryPath, "w", encoding="utf-8") as outputFile:
        json.dump(data, outputFile, indent=2, sort_keys=True)
      os.replace(temporaryPath, self._draftFilePath(session.layer))
    except Exception as exception:
      self._process._log.add(
        "ManualCalibration",
        "DRAFT_SAVE",
        "Failed to save manual calibration draft for layer " + session.layer + ".",
        [self._draftFilePath(session.layer), exception],
      )
      return False

    return True

  # -------------------------------------------------------------------
  def _loadPersistedSession(self, session):
    draftPath = self._draftFilePath(session.layer)
    if not os.path.isfile(draftPath):
      return False

    try:
      with open(draftPath, "r", encoding="utf-8") as inputFile:
        data = json.load(inputFile)
    except (OSError, ValueError) as exception:
      self._process._log.add(
        "ManualCalibration",
        "DRAFT_LOAD",
        "Failed to load manual calibration draft for layer " + session.layer + ".",
        [draftPath, exception],
      )
      return False

    try:
      if session.mode == "gx":
        self._loadPersistedGXSession(session, data)
      else:
        baselineSource = str(data.get("baselineSource", "nominal")).lower()
        if baselineSource not in ("nominal", "live", "loaded"):
          baselineSource = "nominal"

        self._loadDraftBaseline(session, baselineSource)
        session.cameraOffsetX = float(data.get("cameraOffsetX", session.cameraOffsetX))
        session.cameraOffsetY = float(data.get("cameraOffsetY", session.cameraOffsetY))

        measuredPins = {}
        for pinValue, measurement in data.get("measuredPins", {}).items():
          pin = _normalize_pin(pinValue)
          measuredPins[pin] = {
            "pin": pin,
            "rawCameraX": self._optionalFloat(measurement.get("rawCameraX")),
            "rawCameraY": self._optionalFloat(measurement.get("rawCameraY")),
            "offsetX": float(measurement.get("offsetX", session.cameraOffsetX)),
            "offsetY": float(measurement.get("offsetY", session.cameraOffsetY)),
            "wireX": float(measurement["wireX"]),
            "wireY": float(measurement["wireY"]),
            "updatedAt": str(measurement.get("updatedAt", "")),
            "source": str(measurement.get("source", "manual")),
          }
        session.measuredPins = measuredPins

        boardChecks = {}
        for pinValue, boardCheck in data.get("boardChecks", {}).items():
          pin = _normalize_pin(pinValue)
          boardChecks[pin] = {
            "pin": pin,
            "boardIndex": int(boardCheck["boardIndex"]),
            "status": str(boardCheck.get("status", "ok")),
            "wireX": float(boardCheck["wireX"]),
            "wireY": float(boardCheck["wireY"]),
            "cameraX": float(boardCheck["cameraX"]),
            "cameraY": float(boardCheck["cameraY"]),
            "updatedAt": str(boardCheck.get("updatedAt", "")),
          }
        session.boardChecks = boardChecks
        session.dirty = bool(data.get("dirty", False))
        session.initialized = True
    except Exception as exception:
      self._process._log.add(
        "ManualCalibration",
        "DRAFT_LOAD",
        "Failed to restore manual calibration draft for layer " + session.layer + ".",
        [draftPath, exception],
      )
      return False

    self._process._log.add(
      "ManualCalibration",
      "DRAFT_LOAD",
      "Loaded manual calibration draft for layer " + session.layer + ".",
      [
        session.layer,
        draftPath,
        session.baselineSource if session.mode == "uv" else "gx",
        len(session.measuredPins) if session.mode == "uv" else len(session.references),
        session.dirty,
      ],
    )
    return True

  # -------------------------------------------------------------------
  def _persistSession(self, session, persistBaseline=False):
    if session.mode == "gx":
      return self._persistGXSession(session)

    if session.baselineCalibration is None:
      return False

    try:
      draftDirectory = self._draftDirectory()
      if not os.path.isdir(draftDirectory):
        os.makedirs(draftDirectory)

      if persistBaseline or not os.path.isfile(self._draftBaselinePath(session.layer)):
        baselineCalibration = LayerCalibration(layer=session.layer)
        baselineCalibration.zFront = session.baselineCalibration.zFront
        baselineCalibration.zBack = session.baselineCalibration.zBack
        baselineCalibration.offset = SerializableLocation(
          session.baselineCalibration.offset.x,
          session.baselineCalibration.offset.y,
          session.baselineCalibration.offset.z,
        )
        for pinName in session.baselineCalibration.getPinNames():
          baselineLocation = session.baselineCalibration.getPinLocation(pinName)
          baselineCalibration.setPinLocation(
            pinName,
            Location(baselineLocation.x, baselineLocation.y, baselineLocation.z),
          )

        baselineCalibration.save(
          draftDirectory,
          self._draftBaselineFileName(session.layer),
          "LayerCalibration",
        )

      data = {
        "layer": session.layer,
        "baselineSource": session.baselineSource,
        "cameraOffsetX": session.cameraOffsetX,
        "cameraOffsetY": session.cameraOffsetY,
        "dirty": session.dirty,
        "measuredPins": {},
        "boardChecks": {},
      }

      for pin in sorted(session.measuredPins):
        data["measuredPins"][str(pin)] = dict(session.measuredPins[pin])

      for pin in sorted(session.boardChecks):
        data["boardChecks"][str(pin)] = dict(session.boardChecks[pin])

      temporaryPath = self._draftFilePath(session.layer) + ".tmp"
      with open(temporaryPath, "w", encoding="utf-8") as outputFile:
        json.dump(data, outputFile, indent=2, sort_keys=True)
      os.replace(temporaryPath, self._draftFilePath(session.layer))
    except Exception as exception:
      self._process._log.add(
        "ManualCalibration",
        "DRAFT_SAVE",
        "Failed to save manual calibration draft for layer " + session.layer + ".",
        [self._draftFilePath(session.layer), exception],
      )
      return False

    return True

  # -------------------------------------------------------------------
  def _getActiveLayer(self):
    layer = self._process.getRecipeLayer()
    if _mode_for_layer(layer) is None:
      if layer is None:
        return (None, "Load a U, V, X, or G recipe to use manual calibration.")
      return (None, "Manual calibration is only available for the U, V, X, and G layers.")

    return (layer, None)

  # -------------------------------------------------------------------
  def _getActiveLayerForMode(self, expectedMode):
    layer, error = self._getActiveLayer()
    if error is not None:
      return (None, error)

    if _mode_for_layer(layer) != expectedMode:
      if expectedMode == "uv":
        return (None, "This action is only available for the U and V layers.")
      return (None, "This action is only available for the X and G layers.")

    return (layer, None)

  # -------------------------------------------------------------------
  def _mutationGuard(self):
    if not self._process.controlStateMachine.isReadyForMovement():
      return self._errorResult("Machine is not ready for manual calibration moves.")

    return None

  # -------------------------------------------------------------------
  def _okResult(self, data=None):
    result = {"ok": True}
    if data is not None:
      result["data"] = data
    return result

  # -------------------------------------------------------------------
  def _errorResult(self, message):
    return {"ok": False, "error": message}

  # -------------------------------------------------------------------
  def _liveFileName(self, layer):
    if _mode_for_layer(layer) == "gx":
      return get_xg_recipe_file_name(layer)
    return layer + "_Calibration.json"

  # -------------------------------------------------------------------
  def _liveFilePath(self, layer):
    if _mode_for_layer(layer) == "gx":
      return os.path.join(self._recipeDirectory(), self._liveFileName(layer))
    return os.path.join(self._process._workspaceCalibrationDirectory, self._liveFileName(layer))

  # -------------------------------------------------------------------
  def _archivePath(self):
    if self._process.workspace is None:
      return None
    return os.path.join(self._process.workspace.getPath(), "Calibration")

  # -------------------------------------------------------------------
  def _recipeDirectory(self):
    if self._process.workspace is not None and hasattr(self._process.workspace, "_recipeDirectory"):
      return self._process.workspace._recipeDirectory
    return Settings.RECIPE_DIR

  # -------------------------------------------------------------------
  def _recipeArchiveDirectory(self):
    if self._process.workspace is not None and hasattr(self._process.workspace, "_recipeArchiveDirectory"):
      return self._process.workspace._recipeArchiveDirectory
    return None

  # -------------------------------------------------------------------
  def _getLoadedCalibration(self, layer):
    calibration = None
    if self._process.workspace is not None:
      calibration = getattr(self._process.workspace, "_calibration", None)

    if calibration is None:
      gCodeHandler = getattr(self._process, "gCodeHandler", None)
      if gCodeHandler is not None:
        if hasattr(gCodeHandler, "getLayerCalibration"):
          calibration = gCodeHandler.getLayerCalibration()
        else:
          calibration = getattr(gCodeHandler, "currentCalibration", None)

    if calibration is None:
      return None

    calibrationLayer = getattr(calibration, "layer", None)
    if calibrationLayer not in (None, "", layer):
      return None

    return calibration

  # -------------------------------------------------------------------
  def _resetToLoadedCalibration(self, session):
    calibration = self._getLoadedCalibration(session.layer)
    if calibration is None:
      return False

    if session.mode == "gx":
      self._resetGXSession(session)
      for referenceId in GX_REFERENCE_IDS:
        reference = self._emptyGXReference(referenceId)
        pinName = reference["pinName"]
        if not calibration.getPinExists(pinName):
          session.references[referenceId] = reference
          continue

        location = calibration.getPinLocation(pinName)
        reference["offsetX"] = session.cameraOffsetX
        reference["offsetY"] = session.cameraOffsetY
        reference["wireX"] = float(location.x)
        reference["wireY"] = float(location.y)
        reference["updatedAt"] = str(self._process._systemTime.get())
        reference["source"] = "loaded"
        session.references[referenceId] = reference

      return True

    session.baselineCalibration = normalize_calibration(calibration, session.layer)
    session.baselineSource = "loaded"
    session.measuredPins = {}
    session.boardChecks = {}
    session.dirty = False
    session.initialized = True
    return True

  # -------------------------------------------------------------------
  def _createSession(self, layer):
    configuration = self._process._configuration
    defaultX, defaultY = CAMERA_OFFSET_DEFAULTS[layer]
    offsetX = _safe_float(configuration.get(_layer_offset_key(layer, "X")), defaultX)
    offsetY = _safe_float(configuration.get(_layer_offset_key(layer, "Y")), defaultY)
    if _mode_for_layer(layer) == "gx":
      return _ManualCalibrationGXSession(layer, offsetX, offsetY)
    return _ManualCalibrationSession(layer, offsetX, offsetY)

  # -------------------------------------------------------------------
  def _getSession(self, layer):
    sessionKey = self._sessionKey(layer)
    if sessionKey not in self._sessions:
      self._sessions[sessionKey] = self._createSession(layer)

    session = self._sessions[sessionKey]
    if not session.initialized:
      if not self._loadPersistedSession(session):
        if not self._resetToLoadedCalibration(session):
          if session.mode == "gx":
            self._resetGXSession(session)
          else:
            self._resetToNominal(session)

    return session

  # -------------------------------------------------------------------
  def _resetToNominal(self, session):
    session.baselineCalibration = build_nominal_calibration(session.layer)
    session.baselineSource = "nominal"
    session.measuredPins = {}
    session.boardChecks = {}
    session.dirty = False
    session.initialized = True

  # -------------------------------------------------------------------
  def _resetToLive(self, session, allowFallback=False):
    filePath = self._liveFilePath(session.layer)
    if not os.path.isfile(filePath):
      if allowFallback:
        self._resetToNominal(session)
        return None
      return "Calibration file not found: " + filePath

    calibration = LayerCalibration(layer=session.layer)
    try:
      calibration.load(
        self._process._workspaceCalibrationDirectory,
        self._liveFileName(session.layer),
        exceptionForMismatch=False,
      )
    except Exception as exception:
      if allowFallback:
        self._resetToNominal(session)
        return None
      return "Failed to load calibration file: " + str(exception)

    session.baselineCalibration = normalize_calibration(calibration, session.layer)
    session.baselineSource = "live"
    session.measuredPins = {}
    session.boardChecks = {}
    session.dirty = False
    session.initialized = True
    return None

  # -------------------------------------------------------------------
  def _resetGXSession(self, session):
    session.references = {}
    for referenceId in GX_REFERENCE_IDS:
      session.references[referenceId] = self._emptyGXReference(referenceId)

    session.offsets = {}
    for offsetId in GX_OFFSET_IDS:
      session.offsets[offsetId] = None

    session.transferPause = True
    session.includeLeadMode = True
    session.generated = self._emptyGXGenerated(session)
    session.dirty = False
    session.initialized = True

  # -------------------------------------------------------------------
  def _getBaselineLocation(self, session, side, pin):
    return session.baselineCalibration.getPinLocation(side + str(pin))

  # -------------------------------------------------------------------
  def _buildPredictionContext(self, session):
    metadata = LAYER_METADATA[session.layer]
    transformPairs = []
    for pin in sorted(session.measuredPins):
      baseline = self._getBaselineLocation(session, "B", pin)
      measurement = session.measuredPins[pin]
      transformPairs.append((baseline.x, baseline.y, measurement["wireX"], measurement["wireY"]))

    transform, transformMode = build_transform(transformPairs)

    exactPins = {}
    residuals = {}
    for pin in sorted(session.measuredPins):
      baseline = self._getBaselineLocation(session, "B", pin)
      transformedX, transformedY = _apply_transform(transform, baseline.x, baseline.y)
      measurement = session.measuredPins[pin]
      exactPins[pin] = {
        "wireX": measurement["wireX"],
        "wireY": measurement["wireY"],
        "predictionMode": "measured",
      }
      residuals[pin] = (
        measurement["wireX"] - transformedX,
        measurement["wireY"] - transformedY,
      )

    for pin in sorted(session.boardChecks):
      if pin in exactPins:
        continue

      baseline = self._getBaselineLocation(session, "B", pin)
      transformedX, transformedY = _apply_transform(transform, baseline.x, baseline.y)
      boardCheck = session.boardChecks[pin]
      exactPins[pin] = {
        "wireX": boardCheck["wireX"],
        "wireY": boardCheck["wireY"],
        "predictionMode": "accepted",
      }
      residuals[pin] = (
        boardCheck["wireX"] - transformedX,
        boardCheck["wireY"] - transformedY,
      )

    sideAnchors = {}
    for side in SIDE_ORDER:
      sideAnchors[side] = []

    globalAnchors = []
    for pin in sorted(residuals):
      board = metadata["pinToBoard"][pin]
      anchor = (pin, residuals[pin])
      sideAnchors[board["side"]].append(anchor)
      globalAnchors.append(anchor)

    return {
      "metadata": metadata,
      "geometry": metadata["geometry"],
      "transform": transform,
      "transformMode": transformMode,
      "exactPins": exactPins,
      "residuals": residuals,
      "sideAnchors": sideAnchors,
      "globalAnchors": globalAnchors,
    }

  # -------------------------------------------------------------------
  def _interpolateSideResidual(self, context, pin):
    metadata = context["metadata"]
    board = metadata["pinToBoard"][pin]
    anchors = context["sideAnchors"][board["side"]]
    if len(anchors) == 0:
      if len(context["globalAnchors"]) == 0:
        return ((0.0, 0.0), "none")

      nearest = min(
        context["globalAnchors"],
        key=lambda anchor: _cyclic_pin_distance(pin, anchor[0], metadata["pinMax"]),
      )
      return (nearest[1], "nearest")

    if len(anchors) == 1:
      return (anchors[0][1], "nearest")

    if pin <= anchors[0][0]:
      return (anchors[0][1], "side")

    for index in range(len(anchors) - 1):
      leftPin, leftResidual = anchors[index]
      rightPin, rightResidual = anchors[index + 1]
      if leftPin <= pin <= rightPin:
        return (_interpolate_residual(leftPin, leftResidual, rightPin, rightResidual, pin), "side")

    return (anchors[-1][1], "side")

  # -------------------------------------------------------------------
  def _predictBackPin(self, session, context, pin):
    if pin in context["exactPins"]:
      exact = context["exactPins"][pin]
      return (exact["wireX"], exact["wireY"], exact["predictionMode"])

    baseline = self._getBaselineLocation(session, "B", pin)
    transformedX, transformedY = _apply_transform(context["transform"], baseline.x, baseline.y)

    board = context["metadata"]["pinToBoard"][pin]
    startPin = board["startPin"]
    endPin = board["endPin"]
    if startPin in context["residuals"] and endPin in context["residuals"]:
      residual = _interpolate_residual(
        startPin,
        context["residuals"][startPin],
        endPin,
        context["residuals"][endPin],
        pin,
      )
      modeSuffix = "board"
    else:
      residual, modeSuffix = self._interpolateSideResidual(context, pin)

    predictionMode = context["transformMode"]
    if modeSuffix != "none":
      predictionMode += "+" + modeSuffix

    return (
      transformedX + residual[0],
      transformedY + residual[1],
      predictionMode,
    )

  # -------------------------------------------------------------------
  def _predictFrontPin(self, session, context, pin):
    baselineFront = self._getBaselineLocation(session, "F", pin)
    transformedFrontX, transformedFrontY = _apply_transform(
      context["transform"], baselineFront.x, baselineFront.y
    )

    backPin = int(LayerFunctions.translateFrontBack(context["geometry"], pin))
    predictedBackX, predictedBackY, predictionMode = self._predictBackPin(session, context, backPin)

    baselineBack = self._getBaselineLocation(session, "B", backPin)
    transformedBackX, transformedBackY = _apply_transform(
      context["transform"], baselineBack.x, baselineBack.y
    )

    correctionX = predictedBackX - transformedBackX
    correctionY = predictedBackY - transformedBackY
    return (
      transformedFrontX + correctionX,
      transformedFrontY + correctionY,
      predictionMode,
    )

  # -------------------------------------------------------------------
  def _boardStatus(self, session, pin):
    if pin in session.boardChecks:
      return session.boardChecks[pin]["status"]
    return "pending"

  # -------------------------------------------------------------------
  def _predictionState(self, session, context, pin):
    metadata = context["metadata"]
    board = metadata["pinToBoard"][pin]
    wireX, wireY, predictionMode = self._predictBackPin(session, context, pin)
    return {
      "pin": pin,
      "wireX": wireX,
      "wireY": wireY,
      "cameraCheckX": wireX - session.cameraOffsetX,
      "cameraCheckY": wireY - session.cameraOffsetY,
      "isMeasured": pin in session.measuredPins,
      "predictionMode": predictionMode,
      "boardIndex": board["boardIndex"],
      "side": board["side"],
      "status": self._boardStatus(session, pin),
      "isBoardEndpoint": pin in metadata["endpointInfo"],
      "isBootstrapPin": pin in metadata["bootstrapSet"],
    }

  # -------------------------------------------------------------------
  def _boardCheckEntry(self, session, pin, status, wireX, wireY):
    endpointInfo = LAYER_METADATA[session.layer]["endpointInfo"][pin]
    return {
      "pin": pin,
      "boardIndex": endpointInfo["boardIndex"],
      "status": status,
      "wireX": wireX,
      "wireY": wireY,
      "cameraX": wireX - session.cameraOffsetX,
      "cameraY": wireY - session.cameraOffsetY,
      "updatedAt": str(self._process._systemTime.get()),
    }

  # -------------------------------------------------------------------
  def _setBoardCheck(self, session, pin, status, wireX, wireY):
    session.boardChecks[pin] = self._boardCheckEntry(session, pin, status, wireX, wireY)

  # -------------------------------------------------------------------
  def _gxReferenceRecorded(self, reference):
    return (
      reference.get("wireX") is not None
      and reference.get("wireY") is not None
      and reference.get("offsetX") is not None
      and reference.get("offsetY") is not None
    )

  # -------------------------------------------------------------------
  def _gxReferenceCount(self, session):
    return len(
      [
        referenceId for referenceId in GX_REFERENCE_IDS
        if self._gxReferenceRecorded(session.references[referenceId])
      ]
    )

  # -------------------------------------------------------------------
  def _gxReadyToGenerate(self, session):
    if self._gxReferenceCount(session) != len(GX_REFERENCE_IDS):
      return False

    for offsetId in GX_OFFSET_IDS:
      if session.offsets[offsetId] is None:
        return False

    return True

  # -------------------------------------------------------------------
  def _normalizeGXReferenceId(self, referenceId):
    referenceId = str(referenceId).strip().lower()
    if referenceId not in GX_REFERENCE_IDS:
      raise ValueError("Reference must be 'head' or 'foot'.")
    return referenceId

  # -------------------------------------------------------------------
  def _normalizeGXOffsetId(self, offsetId):
    offsetId = str(offsetId).strip()
    if offsetId not in GX_OFFSET_IDS:
      raise ValueError("Offset must be one of " + ", ".join(GX_OFFSET_IDS) + ".")
    return offsetId

  # -------------------------------------------------------------------
  def getState(self):
    layer = self._process.getRecipeLayer()
    movementReady = self._process.controlStateMachine.isReadyForMovement()
    mode = _mode_for_layer(layer)
    enabled = mode is not None
    disabledReason = None
    if not enabled:
      if layer is None:
        disabledReason = "Load a U, V, X, or G recipe to use manual calibration."
      else:
        disabledReason = "Manual calibration is only available for the U, V, X, and G layers."

      return {
        "enabled": False,
        "disabledReason": disabledReason,
        "layer": layer,
        "mode": None,
        "outputKind": None,
        "pinMax": None,
        "baselineSource": None,
        "liveFile": None,
        "dirty": False,
        "cameraOffsetX": None,
        "cameraOffsetY": None,
        "measuredPins": [],
        "bootstrapPins": [],
        "boardChecks": [],
        "suggestedPin": None,
        "counts": {
          "measuredPins": 0,
          "acceptedPins": 0,
          "bootstrapDone": 0,
          "bootstrapTotal": 0,
          "bootstrapComplete": False,
          "boardCheckDone": 0,
          "boardCheckTotal": 0,
        },
        "movementReady": movementReady,
      }

    session = self._getSession(layer)
    if mode == "gx":
      references = {}
      for referenceId in GX_REFERENCE_IDS:
        references[referenceId] = dict(session.references[referenceId])

      offsets = {}
      for offsetId in GX_OFFSET_IDS:
        offsets[offsetId] = session.offsets[offsetId]

      return {
        "enabled": True,
        "disabledReason": None,
        "layer": layer,
        "mode": "gx",
        "outputKind": "gc",
        "pinMax": None,
        "baselineSource": None,
        "liveFile": self._liveFilePath(layer),
        "dirty": session.dirty,
        "cameraOffsetX": session.cameraOffsetX,
        "cameraOffsetY": session.cameraOffsetY,
        "references": references,
        "offsets": offsets,
        "transferPause": session.transferPause,
        "includeLeadMode": session.includeLeadMode,
        "wrapCount": GX_WRAP_COUNTS[layer],
        "wireSpacing": GX_WIRE_SPACING,
        "counts": {
          "referencePointsRecorded": self._gxReferenceCount(session),
          "referencePointsTotal": len(GX_REFERENCE_IDS),
        },
        "readyToGenerate": self._gxReadyToGenerate(session),
        "generated": dict(session.generated),
        "movementReady": movementReady,
      }

    context = self._buildPredictionContext(session)
    metadata = context["metadata"]

    measuredPins = []
    for pin in sorted(session.measuredPins):
      measurement = session.measuredPins[pin]
      board = metadata["pinToBoard"][pin]
      measuredPins.append(
        {
          "pin": pin,
          "rawCameraX": measurement["rawCameraX"],
          "rawCameraY": measurement["rawCameraY"],
          "offsetX": measurement["offsetX"],
          "offsetY": measurement["offsetY"],
          "wireX": measurement["wireX"],
          "wireY": measurement["wireY"],
          "updatedAt": measurement["updatedAt"],
          "source": measurement["source"],
          "boardIndex": board["boardIndex"],
          "side": board["side"],
          "status": self._boardStatus(session, pin),
        }
      )

    boardChecks = []
    for pin in metadata["endpointPins"]:
      prediction = self._predictionState(session, context, pin)
      boardChecks.append(
        {
          "pin": pin,
          "boardIndex": prediction["boardIndex"],
          "status": prediction["status"],
          "predictedWireX": prediction["wireX"],
          "predictedWireY": prediction["wireY"],
          "predictedCameraX": prediction["cameraCheckX"],
          "predictedCameraY": prediction["cameraCheckY"],
          "side": prediction["side"],
          "isBootstrapPin": prediction["isBootstrapPin"],
        }
      )

    bootstrapPins = []
    for pin in metadata["bootstrapPins"]:
      prediction = self._predictionState(session, context, pin)
      bootstrapPins.append(
        {
          "pin": pin,
          "boardIndex": prediction["boardIndex"],
          "status": prediction["status"],
          "predictedWireX": prediction["wireX"],
          "predictedWireY": prediction["wireY"],
          "predictedCameraX": prediction["cameraCheckX"],
          "predictedCameraY": prediction["cameraCheckY"],
          "side": prediction["side"],
        }
      )

    bootstrapDone = len([item for item in bootstrapPins if item["status"] != "pending"])
    boardCheckDone = len([item for item in boardChecks if item["status"] != "pending"])

    suggestedPin = None
    for item in bootstrapPins:
      if item["status"] == "pending":
        suggestedPin = item["pin"]
        break

    if suggestedPin is None and bootstrapDone == len(bootstrapPins):
      for item in boardChecks:
        if item["status"] == "pending":
          suggestedPin = item["pin"]
          break

    return {
      "enabled": True,
      "disabledReason": None,
      "layer": layer,
      "mode": "uv",
      "outputKind": "xml",
      "pinMax": metadata["pinMax"],
      "baselineSource": session.baselineSource,
      "liveFile": self._liveFilePath(layer),
      "dirty": session.dirty,
      "cameraOffsetX": session.cameraOffsetX,
      "cameraOffsetY": session.cameraOffsetY,
      "measuredPins": measuredPins,
      "bootstrapPins": bootstrapPins,
      "boardChecks": boardChecks,
      "suggestedPin": suggestedPin,
      "counts": {
        "measuredPins": len(session.measuredPins),
        "acceptedPins": len(context["residuals"]),
        "bootstrapDone": bootstrapDone,
        "bootstrapTotal": len(bootstrapPins),
        "bootstrapComplete": bootstrapDone == len(bootstrapPins),
        "boardCheckDone": boardCheckDone,
        "boardCheckTotal": len(boardChecks),
      },
      "movementReady": movementReady,
    }

  # -------------------------------------------------------------------
  def startNew(self):
    layer, error = self._getActiveLayerForMode("uv")
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    session = self._getSession(layer)
    self._resetToNominal(session)
    self._persistSession(session, persistBaseline=True)
    self._process._log.add(
      "ManualCalibration",
      "RESET",
      "Manual calibration reset to nominal geometry for layer " + layer + ".",
      [layer],
    )
    return self._okResult({"baselineSource": session.baselineSource})

  # -------------------------------------------------------------------
  def loadPrevious(self):
    layer, error = self._getActiveLayerForMode("uv")
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    session = self._getSession(layer)
    error = self._resetToLive(session)
    if error is not None:
      return self._errorResult(error)

    self._persistSession(session, persistBaseline=True)
    self._process._log.add(
      "ManualCalibration",
      "RESET",
      "Manual calibration loaded live baseline for layer " + layer + ".",
      [layer, self._liveFilePath(layer)],
    )
    return self._okResult({"baselineSource": session.baselineSource})

  # -------------------------------------------------------------------
  def setCameraOffset(self, xValue, yValue):
    layer, error = self._getActiveLayer()
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    session = self._getSession(layer)
    session.cameraOffsetX = float(xValue)
    session.cameraOffsetY = float(yValue)
    if session.mode == "gx":
      for referenceId in GX_REFERENCE_IDS:
        reference = session.references[referenceId]
        if (
          reference.get("source") == "capture"
          and reference.get("rawCameraX") is not None
          and reference.get("rawCameraY") is not None
        ):
          reference["offsetX"] = session.cameraOffsetX
          reference["offsetY"] = session.cameraOffsetY
          reference["wireX"] = reference["rawCameraX"] + session.cameraOffsetX
          reference["wireY"] = reference["rawCameraY"] + session.cameraOffsetY
    session.dirty = True
    self._persistSession(session)
    return self._okResult({"cameraOffsetX": session.cameraOffsetX, "cameraOffsetY": session.cameraOffsetY})

  # -------------------------------------------------------------------
  def captureCurrentReference(self, referenceId):
    layer, error = self._getActiveLayerForMode("gx")
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    try:
      referenceId = self._normalizeGXReferenceId(referenceId)
    except ValueError as exception:
      return self._errorResult(str(exception))

    session = self._getSession(layer)
    rawCameraX = self._process._io.xAxis.getPosition()
    rawCameraY = self._process._io.yAxis.getPosition()
    session.references[referenceId] = {
      "id": referenceId,
      "label": GX_REFERENCE_LABELS[referenceId],
      "pinName": GX_REFERENCE_PIN_NAMES[referenceId],
      "rawCameraX": rawCameraX,
      "rawCameraY": rawCameraY,
      "offsetX": session.cameraOffsetX,
      "offsetY": session.cameraOffsetY,
      "wireX": rawCameraX + session.cameraOffsetX,
      "wireY": rawCameraY + session.cameraOffsetY,
      "updatedAt": str(self._process._systemTime.get()),
      "source": "capture",
    }
    session.dirty = True
    self._persistSession(session)
    return self._okResult(dict(session.references[referenceId]))

  # -------------------------------------------------------------------
  def updateReferencePoint(self, referenceId, wireX, wireY):
    layer, error = self._getActiveLayerForMode("gx")
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    try:
      referenceId = self._normalizeGXReferenceId(referenceId)
    except ValueError as exception:
      return self._errorResult(str(exception))

    session = self._getSession(layer)
    previous = session.references.get(referenceId, self._emptyGXReference(referenceId))
    offsetX = previous.get("offsetX")
    offsetY = previous.get("offsetY")
    if offsetX is None:
      offsetX = session.cameraOffsetX
    if offsetY is None:
      offsetY = session.cameraOffsetY
    session.references[referenceId] = {
      "id": referenceId,
      "label": GX_REFERENCE_LABELS[referenceId],
      "pinName": GX_REFERENCE_PIN_NAMES[referenceId],
      "rawCameraX": previous.get("rawCameraX"),
      "rawCameraY": previous.get("rawCameraY"),
      "offsetX": offsetX,
      "offsetY": offsetY,
      "wireX": float(wireX),
      "wireY": float(wireY),
      "updatedAt": str(self._process._systemTime.get()),
      "source": "manual",
    }
    session.dirty = True
    self._persistSession(session)
    return self._okResult(dict(session.references[referenceId]))

  # -------------------------------------------------------------------
  def gotoReference(self, referenceId, velocity=None):
    layer, error = self._getActiveLayerForMode("gx")
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    try:
      referenceId = self._normalizeGXReferenceId(referenceId)
    except ValueError as exception:
      return self._errorResult(str(exception))

    session = self._getSession(layer)
    reference = session.references.get(referenceId, self._emptyGXReference(referenceId))
    wireX = reference.get("wireX")
    wireY = reference.get("wireY")
    if wireX is None or wireY is None:
      return self._errorResult(
        "No wire-space target is available for " + GX_REFERENCE_LABELS[referenceId] + "."
      )

    velocityValue = None
    if velocity is not None:
      velocityValue = float(velocity)

    cameraX = float(wireX) - session.cameraOffsetX
    cameraY = float(wireY) - session.cameraOffsetY
    isError = self._process.manualSeekXY(cameraX, cameraY, velocityValue)
    if isError:
      return self._errorResult("Move request was rejected.")

    result = {
      "referenceId": referenceId,
      "pinName": GX_REFERENCE_PIN_NAMES[referenceId],
      "wireX": float(wireX),
      "wireY": float(wireY),
      "cameraX": cameraX,
      "cameraY": cameraY,
      "velocity": velocityValue,
    }
    self._process._log.add(
      "ManualCalibration",
      "GOTO",
      "Seek X/G reference " + GX_REFERENCE_PIN_NAMES[referenceId] + ".",
      [
        referenceId,
        GX_REFERENCE_PIN_NAMES[referenceId],
        wireX,
        wireY,
        cameraX,
        cameraY,
        velocityValue,
      ],
    )
    return self._okResult(result)

  # -------------------------------------------------------------------
  def setCornerOffset(self, offsetId, value):
    layer, error = self._getActiveLayerForMode("gx")
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    try:
      offsetId = self._normalizeGXOffsetId(offsetId)
    except ValueError as exception:
      return self._errorResult(str(exception))

    session = self._getSession(layer)
    session.offsets[offsetId] = float(value)
    session.dirty = True
    self._persistSession(session)
    return self._okResult({"offsetId": offsetId, "value": session.offsets[offsetId]})

  # -------------------------------------------------------------------
  def setTransferPause(self, enabled):
    layer, error = self._getActiveLayerForMode("gx")
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    session = self._getSession(layer)
    session.transferPause = bool(enabled)
    session.dirty = True
    self._persistSession(session)
    return self._okResult({"transferPause": session.transferPause})

  # -------------------------------------------------------------------
  def setIncludeLeadMode(self, enabled):
    layer, error = self._getActiveLayerForMode("gx")
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    session = self._getSession(layer)
    session.includeLeadMode = bool(enabled)
    session.dirty = True
    self._persistSession(session)
    return self._okResult({"includeLeadMode": session.includeLeadMode})

  # -------------------------------------------------------------------
  def clearGXDraft(self):
    layer, error = self._getActiveLayerForMode("gx")
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    session = self._getSession(layer)
    self._resetGXSession(session)
    session.dirty = False
    self._persistSession(session)
    self._process._log.add(
      "ManualCalibration",
      "RESET",
      "Cleared X/G manual calibration draft for layer " + layer + ".",
      [layer],
    )
    return self._okResult({"layer": layer})

  # -------------------------------------------------------------------
  def generateRecipeFile(self):
    layer, error = self._getActiveLayerForMode("gx")
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    session = self._getSession(layer)
    if self._gxReferenceCount(session) != len(GX_REFERENCE_IDS):
      return self._errorResult("Record both the head and foot reference points first.")

    for offsetId in GX_OFFSET_IDS:
      if session.offsets[offsetId] is None:
        return self._errorResult("Enter all four corner offsets before generating the recipe.")

    outputDirectory = self._recipeDirectory()
    if not os.path.isdir(outputDirectory):
      os.makedirs(outputDirectory)

    outputPath = self._liveFilePath(layer)
    generation = write_xg_template_file(
      layer,
      output_path=outputPath,
      special_inputs={
        "references": session.references,
        "offsets": session.offsets,
        "transferPause": session.transferPause,
        "includeLeadMode": session.includeLeadMode,
      },
      archive_directory=self._recipeArchiveDirectory(),
    )

    updatedAt = str(self._process._systemTime.get())
    session.generated = {
      "filePath": outputPath,
      "hashValue": generation["hashValue"],
      "updatedAt": updatedAt,
      "wrapCount": generation["wrapCount"],
    }
    session.dirty = False
    self._persistSession(session)

    recipeWasRefreshed = False
    if (
      self._process.workspace is not None
      and getattr(self._process.workspace, "_recipeFile", None) == self._liveFileName(layer)
      and hasattr(self._process.workspace, "refreshRecipeIfChanged")
    ):
      self._process.workspace.refreshRecipeIfChanged()
      recipeWasRefreshed = True

    self._process._log.add(
      "ManualCalibration",
      "GENERATE",
      "Generated X/G recipe file for layer " + layer + ".",
      [
        layer,
        outputPath,
        generation["hashValue"],
        generation["wrapCount"],
        session.transferPause,
        session.includeLeadMode,
      ],
    )
    return self._okResult(
      {
        "liveFile": outputPath,
        "hashValue": generation["hashValue"],
        "wrapCount": generation["wrapCount"],
        "recipeReloaded": recipeWasRefreshed,
      }
    )

  # -------------------------------------------------------------------
  def predictPin(self, pin):
    layer, error = self._getActiveLayerForMode("uv")
    if error is not None:
      return {"ok": False, "error": error}

    session = self._getSession(layer)
    pin = _normalize_pin(pin)
    if pin < 1 or pin > LAYER_METADATA[layer]["pinMax"]:
      return {"ok": False, "error": "Pin " + str(pin) + " is outside the " + layer + " layer."}

    context = self._buildPredictionContext(session)
    prediction = self._predictionState(session, context, pin)
    prediction["ok"] = True
    return prediction

  # -------------------------------------------------------------------
  def gotoPin(self, pin, velocity=None):
    layer, error = self._getActiveLayerForMode("uv")
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    prediction = self.predictPin(pin)
    if not prediction.get("ok", False):
      return prediction

    velocityValue = None
    if velocity is not None:
      velocityValue = float(velocity)

    isError = self._process.manualSeekXY(
      prediction["cameraCheckX"], prediction["cameraCheckY"], velocityValue
    )
    if isError:
      return self._errorResult("Move request was rejected.")

    self._process._log.add(
      "ManualCalibration",
      "GOTO",
      "Seek manual calibration pin " + str(prediction["pin"]) + ".",
      [
        prediction["pin"],
        prediction["wireX"],
        prediction["wireY"],
        prediction["cameraCheckX"],
        prediction["cameraCheckY"],
        velocityValue,
      ],
    )
    return self._okResult(prediction)

  # -------------------------------------------------------------------
  def captureCurrentPin(self, pin):
    layer, error = self._getActiveLayerForMode("uv")
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    session = self._getSession(layer)
    pin = _normalize_pin(pin)
    if pin < 1 or pin > LAYER_METADATA[layer]["pinMax"]:
      return self._errorResult("Pin " + str(pin) + " is outside the " + layer + " layer.")

    rawCameraX = self._process._io.xAxis.getPosition()
    rawCameraY = self._process._io.yAxis.getPosition()
    wireX = rawCameraX + session.cameraOffsetX
    wireY = rawCameraY + session.cameraOffsetY

    session.measuredPins[pin] = {
      "pin": pin,
      "rawCameraX": rawCameraX,
      "rawCameraY": rawCameraY,
      "offsetX": session.cameraOffsetX,
      "offsetY": session.cameraOffsetY,
      "wireX": wireX,
      "wireY": wireY,
      "updatedAt": str(self._process._systemTime.get()),
      "source": "capture",
    }

    if pin in LAYER_METADATA[layer]["endpointInfo"]:
      self._setBoardCheck(session, pin, "adjusted", wireX, wireY)

    session.dirty = True
    self._persistSession(session)
    return self._okResult(self.predictPin(pin))

  # -------------------------------------------------------------------
  def updateMeasuredPin(self, pin, wireX, wireY):
    layer, error = self._getActiveLayerForMode("uv")
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    session = self._getSession(layer)
    pin = _normalize_pin(pin)
    if pin < 1 or pin > LAYER_METADATA[layer]["pinMax"]:
      return self._errorResult("Pin " + str(pin) + " is outside the " + layer + " layer.")

    previous = session.measuredPins.get(pin, {})
    session.measuredPins[pin] = {
      "pin": pin,
      "rawCameraX": previous.get("rawCameraX"),
      "rawCameraY": previous.get("rawCameraY"),
      "offsetX": previous.get("offsetX", session.cameraOffsetX),
      "offsetY": previous.get("offsetY", session.cameraOffsetY),
      "wireX": float(wireX),
      "wireY": float(wireY),
      "updatedAt": str(self._process._systemTime.get()),
      "source": "manual",
    }

    if pin in LAYER_METADATA[layer]["endpointInfo"]:
      self._setBoardCheck(session, pin, "adjusted", float(wireX), float(wireY))

    session.dirty = True
    self._persistSession(session)
    return self._okResult(self.predictPin(pin))

  # -------------------------------------------------------------------
  def deleteMeasuredPin(self, pin):
    layer, error = self._getActiveLayerForMode("uv")
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    session = self._getSession(layer)
    pin = _normalize_pin(pin)
    if pin not in session.measuredPins:
      return self._errorResult("Pin " + str(pin) + " does not have a measurement.")

    del session.measuredPins[pin]
    if pin in session.boardChecks and session.boardChecks[pin]["status"] == "adjusted":
      del session.boardChecks[pin]

    session.dirty = True
    self._persistSession(session)
    return self._okResult({"pin": pin})

  # -------------------------------------------------------------------
  def markBoardCheck(self, pin, status):
    layer, error = self._getActiveLayerForMode("uv")
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    session = self._getSession(layer)
    pin = _normalize_pin(pin)
    status = str(status).lower()
    if pin not in LAYER_METADATA[layer]["endpointInfo"]:
      return self._errorResult("Pin " + str(pin) + " is not a board endpoint.")

    if status not in ("ok", "adjusted"):
      return self._errorResult("Board check status must be 'ok' or 'adjusted'.")

    if pin in session.measuredPins:
      measurement = session.measuredPins[pin]
      self._setBoardCheck(session, pin, "adjusted", measurement["wireX"], measurement["wireY"])
    elif status == "adjusted":
      return self._errorResult("Adjusted status requires a measured pin.")
    else:
      prediction = self.predictPin(pin)
      if not prediction.get("ok", False):
        return prediction
      self._setBoardCheck(session, pin, "ok", prediction["wireX"], prediction["wireY"])

    session.dirty = True
    self._persistSession(session)
    return self._okResult(self.predictPin(pin))

  # -------------------------------------------------------------------
  def saveLive(self):
    layer, error = self._getActiveLayerForMode("uv")
    if error is not None:
      return self._errorResult(error)

    blocked = self._mutationGuard()
    if blocked is not None:
      return blocked

    if self._process.workspace is None:
      return self._errorResult("No workspace is loaded.")

    session = self._getSession(layer)
    context = self._buildPredictionContext(session)
    calibrationDirectory = self._process._workspaceCalibrationDirectory
    if not os.path.isdir(calibrationDirectory):
      os.makedirs(calibrationDirectory)

    calibration = LayerCalibration(layer=layer, archivePath=self._archivePath())
    calibration.zFront = session.baselineCalibration.zFront
    calibration.zBack = session.baselineCalibration.zBack
    calibration.offset = SerializableLocation(0.0, 0.0, 0.0)

    for pinName in session.baselineCalibration.getPinNames():
      baselineLocation = session.baselineCalibration.getPinLocation(pinName)
      if pinName.startswith("B"):
        pin = int(pinName[1:])
        wireX, wireY, _ = self._predictBackPin(session, context, pin)
        calibration.setPinLocation(pinName, Location(wireX, wireY, baselineLocation.z))
      elif pinName.startswith("F"):
        pin = int(pinName[1:])
        wireX, wireY, _ = self._predictFrontPin(session, context, pin)
        calibration.setPinLocation(pinName, Location(wireX, wireY, baselineLocation.z))
      else:
        calibration.setPinLocation(
          pinName, Location(baselineLocation.x, baselineLocation.y, baselineLocation.z)
        )

    savedFromSource = session.baselineSource
    fileName = self._liveFileName(layer)
    calibration.save(calibrationDirectory, fileName, "LayerCalibration")

    configuration = self._process._configuration
    configuration.set(_layer_offset_key(layer, "X"), session.cameraOffsetX)
    configuration.set(_layer_offset_key(layer, "Y"), session.cameraOffsetY)

    self._process.workspace._calibrationFile = fileName
    self._process.workspace._loadCalibrationFromDisk("manual calibration save")
    calibration = self._process.workspace._calibration

    session.baselineCalibration = normalize_calibration(calibration, layer)
    session.baselineSource = "live"
    session.dirty = False
    self._persistSession(session, persistBaseline=True)

    self._process._log.add(
      "ManualCalibration",
      "SAVE",
      "Saved manual calibration for layer " + layer + ".",
      [
        layer,
        self._liveFilePath(layer),
        calibration.hashValue,
        savedFromSource,
        len(session.measuredPins),
        session.cameraOffsetX,
        session.cameraOffsetY,
      ],
    )

    return self._okResult(
      {
        "liveFile": self._liveFilePath(layer),
        "hashValue": calibration.hashValue,
      }
    )
