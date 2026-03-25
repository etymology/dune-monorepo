###############################################################################
# Name: SimulatedPLC.py
# Uses: In-memory PLC simulator backend.
###############################################################################

import re
import threading
from typing import Any

from .plc import PLC


class SimulatedPLC(PLC):
  STATE_INIT = 0
  STATE_READY = 1
  STATE_XY_JOG = 2
  STATE_XY_SEEK = 3
  STATE_Z_JOG = 4
  STATE_Z_SEEK = 5
  STATE_LATCHING = 6
  STATE_LATCH_HOMEING = 7
  STATE_LATCH_RELEASE = 8
  STATE_UNSERVO = 9
  STATE_ERROR = 10
  STATE_EOT = 11
  STATE_XZ_SEEK = 12
  STATE_QUEUED_MOTION = 13

  MOVE_RESET = 0
  MOVE_JOG_XY = 1
  MOVE_SEEK_XY = 2
  MOVE_JOG_Z = 3
  MOVE_SEEK_Z = 4
  MOVE_LATCH = 5
  MOVE_HOME_LATCH = 6
  MOVE_LATCH_UNLOCK = 7
  MOVE_UNSERVO = 8
  MOVE_PLC_INIT = 9
  MOVE_SEEK_XZ = 10

  _MACHINE_SW_PATTERN = re.compile(r"^MACHINE_SW_STAT\[(\d+)\]$")
  _XZ_TARGET_PATTERN = re.compile(r"^xz_position_target\[(\d+)\]$")

  _MACHINE_SW_ASSUMPTIONS = [
    "Z retract/extend sensors are derived from Z axis position and nominal front/back limits.",
    "Stage/fixed present sensors default true unless overridden; latched sensors are derived from HEAD_POS (-1/0/3).",
    "Actuator top/mid sensors are derived from ACTUATOR_POS (0/1/2).",
    "Transfer and end-of-travel sensors are derived from current X/Y positions and configured limits.",
    "Safety bits (Rotation_Lock_key, Light_Curtain) default to permissive values unless overridden.",
    "estop and park default to false unless overridden.",
    "Frame lock bits are mapped to the active side and ACTUATOR_POS.",
  ]

  _MOVE_TO_BUSY_STATE = {
    MOVE_JOG_XY: STATE_XY_JOG,
    MOVE_SEEK_XY: STATE_XY_SEEK,
    MOVE_JOG_Z: STATE_Z_JOG,
    MOVE_SEEK_Z: STATE_Z_SEEK,
    MOVE_LATCH: STATE_LATCHING,
    MOVE_HOME_LATCH: STATE_LATCH_HOMEING,
    MOVE_LATCH_UNLOCK: STATE_LATCH_RELEASE,
    MOVE_UNSERVO: STATE_UNSERVO,
    MOVE_PLC_INIT: STATE_INIT,
    MOVE_SEEK_XZ: STATE_XZ_SEEK,
  }

  def __init__(self, ipAddress="SIM"):
    self._ipAddress = ipAddress
    self._isFunctional = True
    self._lock = threading.Lock()
    self._cycle = 0
    self._pendingMoveType = None
    self._settleCyclesRemaining = 0
    self._incomingQueueSegment = None
    self._queuedSegments = []
    self._queuedMotionActive = False
    self._currentQueuedSegment = None
    self._currentQueueCyclesRemaining = 0

    self._limits = {
      "parkX": 0.0,
      "parkY": 0.0,
      "transferLeft": 440.0,
      "transferRight": 7174.0,
      "transferBottom": 0.0,
      "transferTop": 2683.0,
      "limitLeft": 0.0,
      "limitRight": 7179.0,
      "limitBottom": 0.0,
      "limitTop": 2688.0,
      "zFront": 0.0,
      "zBack": 417.7,
      "zLimitFront": 0.0,
      "zLimitRear": 425.0,
    }

    self._tagValues = {}
    self._overrides = {}
    self._seedDefaultTags()

  # ---------------------------------------------------------------------
  def initialize(self):
    self._isFunctional = True
    return self._isFunctional

  # ---------------------------------------------------------------------
  def isNotFunctional(self):
    return not self._isFunctional

  # ---------------------------------------------------------------------
  def read(self, tag):
    with self._lock:
      self._advanceCycle()

      if isinstance(tag, (list, tuple)):
        return [[str(name), self._readTagValue(str(name))] for name in tag]

      return [self._readTagValue(str(tag))]

  # ---------------------------------------------------------------------
  def write(self, tag, data=None, typeName=None):
    del typeName
    with self._lock:
      writes = self._normalizeWritePayload(tag, data)
      for name, value in writes:
        self._writeTag(name, value)
      return writes

  # ---------------------------------------------------------------------
  def get_status(self):
    with self._lock:
      return self._statusSnapshot()

  # ---------------------------------------------------------------------
  def get_tag(self, name: str):
    with self._lock:
      return self._readTagValue(str(name))

  # ---------------------------------------------------------------------
  def set_tag(self, name: str, value: Any, override=None):
    with self._lock:
      tagName = str(name)
      bitIndex = self._machineBitIndex(tagName)
      shouldOverride = override
      if shouldOverride is None:
        shouldOverride = bitIndex is not None
      shouldOverride = bool(shouldOverride)

      if bitIndex is not None:
        if shouldOverride:
          self._overrides[tagName] = self._coerceBit(value)
        else:
          self._overrides.pop(tagName, None)
        return self._readTagValue(tagName)

      if shouldOverride:
        self._overrides[tagName] = value
        return self._readTagValue(tagName)

      self._overrides.pop(tagName, None)
      self._writeTag(tagName, value)
      return self._readTagValue(tagName)

  # ---------------------------------------------------------------------
  def clear_override(self, name=None):
    with self._lock:
      if name is None:
        count = len(self._overrides)
        self._overrides.clear()
        return {"cleared": count}

      tagName = str(name)
      cleared = tagName in self._overrides
      self._overrides.pop(tagName, None)
      return {"cleared": 1 if cleared else 0, "name": tagName}

  # ---------------------------------------------------------------------
  def inject_error(self, code=3003, state=None):
    with self._lock:
      errorCode = int(code)
      errorState = self.STATE_ERROR if state is None else int(state)
      self._tagValues["ERROR_CODE"] = errorCode
      self._tagValues["STATE"] = errorState
      self._pendingMoveType = None
      self._settleCyclesRemaining = 0
      self._setAxisMovement(False)
      return self._statusSnapshot()

  # ---------------------------------------------------------------------
  def clear_error(self):
    with self._lock:
      self._clearErrorState()
      return self._statusSnapshot()

  # ---------------------------------------------------------------------
  def _normalizeWritePayload(self, tag, data):
    if data is not None:
      return [(str(tag), data)]

    if isinstance(tag, (list, tuple)):
      if len(tag) == 2 and not isinstance(tag[0], (list, tuple)):
        return [(str(tag[0]), tag[1])]

      writes = []
      for entry in tag:
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
          raise ValueError("PLC write requires (tag, value) pairs.")
        writes.append((str(entry[0]), entry[1]))
      return writes

    raise ValueError("PLC write requires a tag/value payload.")

  # ---------------------------------------------------------------------
  def _seedDefaultTags(self):
    self._tagValues["STATE"] = self.STATE_READY
    self._tagValues["ERROR_CODE"] = 0
    self._tagValues["MOVE_TYPE"] = self.MOVE_RESET
    self._tagValues["gui_latch_pulse"] = 0
    self._tagValues["HEAD_POS"] = 0
    self._tagValues["ACTUATOR_POS"] = 0

    self._tagValues["XY_SPEED"] = 0.0
    self._tagValues["XY_ACCELERATION"] = 0.0
    self._tagValues["XY_DECELERATION"] = 0.0
    self._tagValues["Z_SPEED"] = 0.0
    self._tagValues["Z_ACCELERATION"] = 0.0
    self._tagValues["Z_DECELLERATION"] = 0.0

    self._tagValues["X_POSITION"] = 0.0
    self._tagValues["Y_POSITION"] = 0.0
    self._tagValues["Z_POSITION"] = 0.0
    self._tagValues["X_SPEED"] = 0.0
    self._tagValues["Y_SPEED"] = 0.0
    self._tagValues["Z_SPEED"] = 0.0
    self._tagValues["X_DIR"] = 0
    self._tagValues["Y_DIR"] = 0
    self._tagValues["Z_DIR"] = 0

    self._tagValues["X_axis.ActualPosition"] = 0.0
    self._tagValues["Y_axis.ActualPosition"] = 0.0
    self._tagValues["Z_axis.ActualPosition"] = 0.0
    self._tagValues["X_axis.ActualVelocity"] = 0.0
    self._tagValues["Y_axis.ActualVelocity"] = 0.0
    self._tagValues["Z_axis.ActualVelocity"] = 0.0
    self._tagValues["X_axis.CommandAcceleration"] = 0.0
    self._tagValues["Y_axis.CommandAcceleration"] = 0.0
    self._tagValues["Z_axis.CommandAcceleration"] = 0.0
    self._tagValues["X_axis.CoordinatedMotionStatus"] = 0
    self._tagValues["Y_axis.CoordinatedMotionStatus"] = 0
    self._tagValues["Z_axis.CoordinatedMotionStatus"] = 0
    self._tagValues["X_axis.ModuleFault"] = 0
    self._tagValues["Y_axis.ModuleFault"] = 0
    self._tagValues["Z_axis.ModuleFault"] = 0

    self._tagValues["CAM_F_TRIGGER"] = 0
    self._tagValues["CAM_F_EN"] = 0
    self._tagValues["EN_POS_TRIGGERS"] = 0
    self._tagValues["X_DELTA"] = 0.0
    self._tagValues["Y_DELTA"] = 0.0
    self._tagValues["READ_FIFOS"] = 0
    self._tagValues["FIFO_Data[0]"] = 0.0
    self._tagValues["FIFO_Data[1]"] = 0.0
    self._tagValues["FIFO_Data[2]"] = 0.0
    self._tagValues["FIFO_Data[3]"] = 0.0
    self._tagValues["FIFO_Data[4]"] = 0.0
    self._tagValues["FIFO_Data[5]"] = 0.0

    self._tagValues["tension"] = 0.0
    self._tagValues["v_xyz"] = 0.0
    self._tagValues["tension_motor_cv"] = 0.0
    self._tagValues["xz_position_target"] = [0.0, 0.0]

    self._tagValues["MORE_STATS_S[0]"] = 1
    self._tagValues["IncomingSeg"] = {}
    self._tagValues["IncomingSegReqID"] = 0
    self._tagValues["LastIncomingSegReqID"] = 0
    self._tagValues["IncomingSegAck"] = 0
    self._tagValues["AbortQueue"] = 0
    self._tagValues["StartQueuedPath"] = 0
    self._tagValues["QueueStopRequest"] = 0
    self._tagValues["MotionFault"] = 0
    self._tagValues["CurIssued"] = 0
    self._tagValues["NextIssued"] = 0
    self._tagValues["ActiveSeq"] = 0
    self._tagValues["PendingSeq"] = 0
    self._tagValues["QueueFault"] = 0
    self._tagValues["MoveA.ER"] = 0
    self._tagValues["MoveB.ER"] = 0
    self._tagValues["QueueCount"] = 0
    self._tagValues["UseAasCurrent"] = 1
    self._tagValues["X_Y.MovePendingStatus"] = 0
    self._tagValues["FaultCode"] = 0

  # ---------------------------------------------------------------------
  def _writeTag(self, tagName, value):
    bitIndex = self._machineBitIndex(tagName)
    if bitIndex is not None:
      self._overrides[tagName] = self._coerceBit(value)
      return

    if tagName == "MOVE_TYPE":
      self._setMoveType(int(value))
      return

    if tagName == "IncomingSeg":
      self._incomingQueueSegment = dict(value)
      self._tagValues[tagName] = dict(value)
      return

    if tagName == "IncomingSegReqID":
      reqId = int(value)
      self._tagValues[tagName] = reqId
      self._acceptIncomingQueueSegment(reqId)
      return

    if tagName == "AbortQueue":
      enabled = self._coerceBit(value)
      self._tagValues[tagName] = enabled
      if enabled:
        self._abortQueuedMotion()
      return

    if tagName == "StartQueuedPath":
      enabled = self._coerceBit(value)
      self._tagValues[tagName] = enabled
      if enabled:
        self._startQueuedMotion()
      return

    if tagName == "QueueStopRequest":
      enabled = self._coerceBit(value)
      self._tagValues[tagName] = enabled
      if enabled:
        self._abortQueuedMotion()
      return

    if tagName == "gui_latch_pulse":
      enabled = self._coerceBit(value)
      self._tagValues[tagName] = enabled
      if enabled:
        if bool(self._readTagValue("MACHINE_SW_STAT[9]")) and bool(
          self._readTagValue("MACHINE_SW_STAT[10]")
        ):
          self._advanceLatch()
        self._tagValues[tagName] = 0
      return

    if tagName == "HEAD_POS":
      intValue = int(value)
      if intValue not in (-1, 0, 3):
        raise ValueError("HEAD_POS must be one of -1, 0, or 3.")
      self._tagValues[tagName] = intValue
      return

    if tagName == "ACTUATOR_POS":
      intValue = int(value)
      if intValue not in (0, 1, 2):
        raise ValueError("ACTUATOR_POS must be one of 0, 1, or 2.")
      self._tagValues[tagName] = intValue
      return

    if tagName == "xz_position_target":
      if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("xz_position_target must be a two-element sequence.")
      self._tagValues[tagName] = [float(value[0]), float(value[1])]
      return

    if tagName in ("STATE", "ERROR_CODE"):
      self._tagValues[tagName] = int(value)
      return

    self._tagValues[tagName] = value

  # ---------------------------------------------------------------------
  def _setMoveType(self, moveType: int):
    self._tagValues["MOVE_TYPE"] = int(moveType)

    if moveType == self.MOVE_RESET:
      self._clearErrorState()
      return

    if self._tagValues.get("STATE", self.STATE_READY) == self.STATE_ERROR:
      return

    busyState = self._MOVE_TO_BUSY_STATE.get(moveType)
    if busyState is None:
      return

    self._tagValues["STATE"] = busyState
    self._pendingMoveType = moveType
    self._settleCyclesRemaining = 1
    self._setAxisMovement(True)

  # ---------------------------------------------------------------------
  def _advanceCycle(self):
    self._cycle += 1
    self._advanceQueuedMotion()

    if self._settleCyclesRemaining <= 0:
      return

    self._settleCyclesRemaining -= 1
    if self._settleCyclesRemaining == 0 and self._pendingMoveType is not None:
      self._completePendingMove(self._pendingMoveType)

  # ---------------------------------------------------------------------
  def _completePendingMove(self, moveType: int):
    self._pendingMoveType = None
    self._setAxisMovement(False)

    if moveType == self.MOVE_SEEK_XZ:
      xTarget, zTarget = self._tagValues.get("xz_position_target", [0.0, 0.0])
      xTarget = float(xTarget)
      zTarget = float(zTarget)
      if self._isXYLimitViolation(xTarget, float(self._tagValues["Y_axis.ActualPosition"])):
        self._setError(3003)
        return
      if self._isZLimitViolation(zTarget):
        self._setError(5003)
        return
      if not bool(self._readTagValue("Y_XFER_OK")):
        self._setError(5003)
        return
      self._tagValues["X_axis.ActualPosition"] = xTarget
      self._tagValues["Z_axis.ActualPosition"] = zTarget

    elif moveType == self.MOVE_SEEK_XY:
      xTarget = float(self._tagValues.get("X_POSITION", self._tagValues["X_axis.ActualPosition"]))
      yTarget = float(self._tagValues.get("Y_POSITION", self._tagValues["Y_axis.ActualPosition"]))
      if self._isXYLimitViolation(xTarget, yTarget):
        self._setError(3003)
        return
      self._tagValues["X_axis.ActualPosition"] = xTarget
      self._tagValues["Y_axis.ActualPosition"] = yTarget

    elif moveType == self.MOVE_JOG_XY:
      xTarget = float(self._tagValues["X_axis.ActualPosition"]) + self._signedSpeed("X_SPEED", "X_DIR") * 0.1
      yTarget = float(self._tagValues["Y_axis.ActualPosition"]) + self._signedSpeed("Y_SPEED", "Y_DIR") * 0.1
      if self._isXYLimitViolation(xTarget, yTarget):
        self._setError(3003)
        return
      self._tagValues["X_axis.ActualPosition"] = xTarget
      self._tagValues["Y_axis.ActualPosition"] = yTarget

    elif moveType == self.MOVE_SEEK_Z:
      zTarget = float(self._tagValues.get("Z_POSITION", self._tagValues["Z_axis.ActualPosition"]))
      if self._isZLimitViolation(zTarget):
        self._setError(5003)
        return
      self._tagValues["Z_axis.ActualPosition"] = zTarget

    elif moveType == self.MOVE_JOG_Z:
      zTarget = float(self._tagValues["Z_axis.ActualPosition"]) + self._signedSpeed("Z_SPEED", "Z_DIR") * 0.1
      if self._isZLimitViolation(zTarget):
        self._setError(5003)
        return
      self._tagValues["Z_axis.ActualPosition"] = zTarget

    elif moveType == self.MOVE_LATCH:
      self._advanceLatch()

    elif moveType == self.MOVE_HOME_LATCH:
      self._tagValues["ACTUATOR_POS"] = 0
      if self._tagValues.get("HEAD_POS") == -1:
        self._tagValues["HEAD_POS"] = 0

    elif moveType == self.MOVE_LATCH_UNLOCK:
      self._tagValues["ACTUATOR_POS"] = 2

    if self._tagValues.get("STATE") != self.STATE_ERROR:
      self._tagValues["ERROR_CODE"] = 0
      self._tagValues["STATE"] = self.STATE_READY

  # ---------------------------------------------------------------------
  def _advanceLatch(self):
    actuator = int(self._tagValues.get("ACTUATOR_POS", 0))
    actuator = (actuator + 1) % 3
    self._tagValues["ACTUATOR_POS"] = actuator

    headPos = int(self._tagValues.get("HEAD_POS", 0))
    if actuator == 2 and headPos in (0, 3):
      self._tagValues["HEAD_POS"] = 3 if headPos == 0 else 0

  # ---------------------------------------------------------------------
  def _setAxisMovement(self, isMoving: bool):
    moving = 1 if isMoving else 0
    self._tagValues["X_axis.CoordinatedMotionStatus"] = moving
    self._tagValues["Y_axis.CoordinatedMotionStatus"] = moving
    self._tagValues["Z_axis.CoordinatedMotionStatus"] = moving

    if isMoving and self._pendingMoveType in (self.MOVE_JOG_XY, self.MOVE_SEEK_XY):
      self._tagValues["X_axis.ActualVelocity"] = self._signedSpeed("X_SPEED", "X_DIR")
      self._tagValues["Y_axis.ActualVelocity"] = self._signedSpeed("Y_SPEED", "Y_DIR")
      self._tagValues["Z_axis.ActualVelocity"] = 0.0
    elif isMoving and self._pendingMoveType == self.MOVE_SEEK_XZ:
      self._tagValues["X_axis.ActualVelocity"] = 1.0
      self._tagValues["Y_axis.ActualVelocity"] = 0.0
      self._tagValues["Z_axis.ActualVelocity"] = 1.0
    elif isMoving and self._pendingMoveType in (self.MOVE_JOG_Z, self.MOVE_SEEK_Z):
      self._tagValues["X_axis.ActualVelocity"] = 0.0
      self._tagValues["Y_axis.ActualVelocity"] = 0.0
      self._tagValues["Z_axis.ActualVelocity"] = self._signedSpeed("Z_SPEED", "Z_DIR")
    else:
      self._tagValues["X_axis.ActualVelocity"] = 0.0
      self._tagValues["Y_axis.ActualVelocity"] = 0.0
      self._tagValues["Z_axis.ActualVelocity"] = 0.0

  # ---------------------------------------------------------------------
  def _clearErrorState(self):
    self._pendingMoveType = None
    self._settleCyclesRemaining = 0
    self._tagValues["ERROR_CODE"] = 0
    self._tagValues["STATE"] = self.STATE_READY
    self._tagValues["MOVE_TYPE"] = self.MOVE_RESET
    self._setAxisMovement(False)
    self._abortQueuedMotion()

  # ---------------------------------------------------------------------
  def _setError(self, code: int):
    self._pendingMoveType = None
    self._settleCyclesRemaining = 0
    self._tagValues["ERROR_CODE"] = int(code)
    self._tagValues["STATE"] = self.STATE_ERROR
    self._setAxisMovement(False)
    self._abortQueuedMotion()

  # ---------------------------------------------------------------------
  def _acceptIncomingQueueSegment(self, reqId: int):
    if reqId == int(self._tagValues.get("LastIncomingSegReqID", 0)):
      return
    segment = dict(self._incomingQueueSegment or {})
    if not segment.get("Valid"):
      self._tagValues["LastIncomingSegReqID"] = reqId
      return
    self._queuedSegments.append(segment)
    self._tagValues["IncomingSegAck"] = int(segment.get("Seq", 0))
    self._tagValues["LastIncomingSegReqID"] = reqId
    self._syncQueueTags()

  # ---------------------------------------------------------------------
  def _syncQueueTags(self):
    self._tagValues["QueueCount"] = len(self._queuedSegments)
    if self._queuedSegments:
      self._tagValues["PendingSeq"] = int(self._queuedSegments[0].get("Seq", 0))
      self._tagValues["NextIssued"] = 1 if len(self._queuedSegments) > 1 else 0
    else:
      self._tagValues["PendingSeq"] = 0
      self._tagValues["NextIssued"] = 0

  # ---------------------------------------------------------------------
  def _abortQueuedMotion(self, clearFaults: bool = True):
    self._queuedSegments = []
    self._queuedMotionActive = False
    self._currentQueuedSegment = None
    self._currentQueueCyclesRemaining = 0
    self._tagValues["CurIssued"] = 0
    self._tagValues["NextIssued"] = 0
    self._tagValues["ActiveSeq"] = 0
    self._tagValues["PendingSeq"] = 0
    self._tagValues["QueueCount"] = 0
    if self._tagValues.get("STATE") == self.STATE_QUEUED_MOTION:
      self._tagValues["STATE"] = self.STATE_READY
    if clearFaults:
      self._tagValues["QueueFault"] = 0
      self._tagValues["MotionFault"] = 0
      self._tagValues["FaultCode"] = 0

  # ---------------------------------------------------------------------
  def _startQueuedMotion(self):
    if self._queuedMotionActive or not self._queuedSegments:
      return
    self._queuedMotionActive = True
    self._currentQueueCyclesRemaining = 0
    if self._tagValues.get("STATE") != self.STATE_ERROR:
      self._tagValues["STATE"] = self.STATE_QUEUED_MOTION

  # ---------------------------------------------------------------------
  def _completeQueuedSegment(self, segment):
    target = segment.get("XY") or (0.0, 0.0)
    xTarget = float(target[0])
    yTarget = float(target[1])
    if self._isXYLimitViolation(xTarget, yTarget):
      self._tagValues["MotionFault"] = 1
      self._tagValues["FaultCode"] = 3003
      self._abortQueuedMotion(clearFaults=False)
      return
    self._tagValues["X_axis.ActualPosition"] = xTarget
    self._tagValues["Y_axis.ActualPosition"] = yTarget

  # ---------------------------------------------------------------------
  def _advanceQueuedMotion(self):
    if not self._queuedMotionActive:
      return
    if self._currentQueuedSegment is None:
      if not self._queuedSegments:
        self._abortQueuedMotion()
        return
      self._currentQueuedSegment = self._queuedSegments.pop(0)
      self._currentQueueCyclesRemaining = 1
      self._tagValues["CurIssued"] = 1
      self._tagValues["ActiveSeq"] = int(self._currentQueuedSegment.get("Seq", 0))
      self._syncQueueTags()
      return

    if self._currentQueueCyclesRemaining > 0:
      self._currentQueueCyclesRemaining -= 1
      return

    self._completeQueuedSegment(self._currentQueuedSegment)
    self._currentQueuedSegment = None
    if not self._queuedSegments:
      self._queuedMotionActive = False
      self._tagValues["CurIssued"] = 0
      self._tagValues["ActiveSeq"] = 0
      if self._tagValues.get("STATE") != self.STATE_ERROR:
        self._tagValues["STATE"] = self.STATE_READY
      self._syncQueueTags()
      return
    self._tagValues["CurIssued"] = 0
    self._tagValues["ActiveSeq"] = 0
    self._syncQueueTags()

  # ---------------------------------------------------------------------
  def _signedSpeed(self, speedTag: str, directionTag: str) -> float:
    speed = float(self._tagValues.get(speedTag, 0.0))
    direction = int(self._tagValues.get(directionTag, 0))
    if direction == 0:
      return abs(speed)
    return -abs(speed)

  # ---------------------------------------------------------------------
  def _isXYLimitViolation(self, x: float, y: float) -> bool:
    return (
      x < self._limits["limitLeft"]
      or x > self._limits["limitRight"]
      or y < self._limits["limitBottom"]
      or y > self._limits["limitTop"]
    )

  # ---------------------------------------------------------------------
  def _isZLimitViolation(self, z: float) -> bool:
    return z < self._limits["zLimitFront"] or z > self._limits["zLimitRear"]

  # ---------------------------------------------------------------------
  def _machineBitIndex(self, tagName):
    match = self._MACHINE_SW_PATTERN.match(tagName)
    if match is None:
      return None
    return int(match.group(1))

  # ---------------------------------------------------------------------
  def _coerceBit(self, value):
    if isinstance(value, bool):
      return 1 if value else 0

    if isinstance(value, (int, float)):
      return 1 if int(value) != 0 else 0

    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
      return 1
    if text in ("0", "false", "no", "off"):
      return 0
    raise ValueError("Bit override must be boolean-like.")

  # ---------------------------------------------------------------------
  def _readTagValue(self, tagName):
    if tagName in self._overrides:
      return self._overrides[tagName]

    if tagName in self._tagValues:
      return self._tagValues[tagName]

    if tagName.startswith("SegQueue[") and "]." in tagName:
      index_text, field_name = tagName[len("SegQueue[") :].split("].", 1)
      try:
        index = int(index_text)
      except ValueError:
        index = -1
      if 0 <= index < len(self._queuedSegments):
        segment = self._queuedSegments[index]
        return segment.get(field_name, 0)

    if tagName == "Y_XFER_OK":
      return self._readTagValue("MACHINE_SW_STAT[17]")

    xzTargetIndex = self._xzTargetIndex(tagName)
    if xzTargetIndex is not None:
      return self._tagValues.get("xz_position_target", [0.0, 0.0])[xzTargetIndex]

    bitIndex = self._machineBitIndex(tagName)
    if bitIndex is not None:
      return self._deriveMachineSwitchBit(bitIndex)

    return 0

  # ---------------------------------------------------------------------
  def _xzTargetIndex(self, tagName):
    match = self._XZ_TARGET_PATTERN.match(tagName)
    if match is None:
      return None
    index = int(match.group(1))
    if index not in (0, 1):
      raise ValueError("xz_position_target index must be 0 or 1.")
    return index

  # ---------------------------------------------------------------------
  def _deriveMachineSwitchBit(self, bitIndex: int):
    x = float(self._tagValues.get("X_axis.ActualPosition", 0.0))
    y = float(self._tagValues.get("Y_axis.ActualPosition", 0.0))
    z = float(self._tagValues.get("Z_axis.ActualPosition", 0.0))
    headPos = int(self._tagValues.get("HEAD_POS", 0))
    actuatorPos = int(self._tagValues.get("ACTUATOR_POS", 0))

    zRetracted = z <= (self._limits["zFront"] + 1.0)
    zExtended = z >= (self._limits["zBack"] - 1.0)
    xPark = abs(x - self._limits["parkX"]) <= 1.0
    xTransfer = self._limits["transferLeft"] <= x <= self._limits["transferRight"]
    yTransfer = self._limits["transferBottom"] <= y <= self._limits["transferTop"]

    baseBits = {
      0: actuatorPos == 0,
      1: zRetracted,
      2: zRetracted,
      3: zRetracted,
      4: zRetracted,
      5: zExtended,
      6: headPos == 0,
      7: headPos == 3,
      8: z <= self._limits["zLimitFront"] or z >= self._limits["zLimitRear"],
      9: True,
      10: True,
      11: zExtended,
      12: actuatorPos == 0,
      13: actuatorPos == 1,
      14: xPark,
      15: xTransfer,
      16: yTransfer,
      17: yTransfer,
      18: y >= self._limits["limitTop"],
      19: y <= self._limits["limitBottom"],
      20: x >= self._limits["limitRight"],
      21: x <= self._limits["limitLeft"],
      22: True,
      23: False,
      24: False,
      25: True,
      26: headPos == 0 and actuatorPos == 0,
      27: headPos == 0 and actuatorPos == 1,
      28: headPos == 0 and actuatorPos == 2,
      29: headPos == 3 and actuatorPos == 0,
      30: headPos == 3 and actuatorPos == 1,
      31: headPos == 3 and actuatorPos == 2,
    }

    return 1 if baseBits.get(bitIndex, False) else 0

  # ---------------------------------------------------------------------
  def _statusSnapshot(self):
    return {
      "mode": "SIM",
      "functional": self._isFunctional,
      "cycle": self._cycle,
      "state": int(self._tagValues.get("STATE", self.STATE_READY)),
      "moveType": int(self._tagValues.get("MOVE_TYPE", self.MOVE_RESET)),
      "errorCode": int(self._tagValues.get("ERROR_CODE", 0)),
      "headPos": int(self._tagValues.get("HEAD_POS", 0)),
      "actuatorPos": int(self._tagValues.get("ACTUATOR_POS", 0)),
      "pendingMoveType": self._pendingMoveType,
      "pendingSettleCycles": self._settleCyclesRemaining,
      "overrides": sorted(self._overrides.keys()),
      "limits": dict(self._limits),
      "assumptions": list(self._MACHINE_SW_ASSUMPTIONS),
    }
