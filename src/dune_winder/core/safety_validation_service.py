###############################################################################
# Name: safety_validation_service.py
# Uses: Safety validation and motion limit management extracted from Process.
###############################################################################

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from dune_winder.queued_motion.safety import (
  MotionSafetyLimits,
  validate_xy_move_within_safety_limits,
)

if TYPE_CHECKING:
  from dune_winder.core.control_state_machine import ControlStateMachine
  from dune_winder.io.maps.base_io import BaseIO
  from dune_winder.machine.calibration.machine import MachineCalibration


def _calibration_float(calibration: MachineCalibration, key: str, default: float) -> float:
  value = None
  try:
    value = calibration.get(key)
  except Exception:
    value = None

  if value is None:
    calibration.set(key, default)
    value = default

  return float(value)


class SafetyValidationService:
  """Owns machine safety limits and validates motion targets."""

  def __init__(
    self,
    machineCalibration: MachineCalibration,
    io: BaseIO,
    controlStateMachine: ControlStateMachine,
    maxVelocity: float,
    maxSlowVelocity: float,
  ):
    self._io = io
    self._controlStateMachine = controlStateMachine
    self._maxVelocity = maxVelocity
    self._maxSlowVelocity = maxSlowVelocity

    cal = machineCalibration
    self._transferLeft = _calibration_float(cal, "transferLeft", 0.0)
    self._transferRight = _calibration_float(cal, "transferRight", 0.0)
    self._transferLeftMargin = _calibration_float(cal, "transferLeftMargin", 10.0)
    self._transferYThreshold = _calibration_float(cal, "transferYThreshold", 1000.0)
    self._limitLeft = _calibration_float(cal, "limitLeft", 0.0)
    self._limitRight = _calibration_float(cal, "limitRight", 0.0)
    self._limitTop = _calibration_float(cal, "limitTop", 0.0)
    self._limitBottom = _calibration_float(cal, "limitBottom", 0.0)
    self._zlimitFront = _calibration_float(cal, "zLimitFront", 0.0)
    self._zlimitRear = _calibration_float(cal, "zLimitRear", 0.0)
    self._queuedMotionZCollisionThreshold = _calibration_float(
      cal, "queuedMotionZCollisionThreshold", _calibration_float(cal, "zBack", 0.0)
    )
    self._arcMaxStepRad = _calibration_float(cal, "arcMaxStepRad", math.radians(3.0))
    self._arcMaxChord = _calibration_float(cal, "arcMaxChord", 5.0)
    self._apaCollisionBottomY = _calibration_float(cal, "apaCollisionBottomY", 50.0)
    self._apaCollisionTopY = _calibration_float(cal, "apaCollisionTopY", 2250.0)
    self._transferZoneHeadMinX = _calibration_float(cal, "transferZoneHeadMinX", 400.0)
    self._transferZoneHeadMaxX = _calibration_float(cal, "transferZoneHeadMaxX", 500.0)
    self._transferZoneFootMinX = _calibration_float(cal, "transferZoneFootMinX", 7100.0)
    self._transferZoneFootMaxX = _calibration_float(cal, "transferZoneFootMaxX", 7200.0)
    self._supportCollisionBottomMinY = _calibration_float(
      cal, "supportCollisionBottomMinY", 80.0
    )
    self._supportCollisionBottomMaxY = _calibration_float(
      cal, "supportCollisionBottomMaxY", 450.0
    )
    self._supportCollisionMiddleMinY = _calibration_float(
      cal, "supportCollisionMiddleMinY", 1050.0
    )
    self._supportCollisionMiddleMaxY = _calibration_float(
      cal, "supportCollisionMiddleMaxY", 1550.0
    )
    self._supportCollisionTopMinY = _calibration_float(
      cal, "supportCollisionTopMinY", 2200.0
    )
    self._supportCollisionTopMaxY = _calibration_float(
      cal, "supportCollisionTopMaxY", 2650.0
    )
    self._geometryEpsilon = _calibration_float(cal, "geometryEpsilon", 1e-9)
    self._headwardPivotX = _calibration_float(cal, "headwardPivotX", 150.0)
    self._headwardPivotY = _calibration_float(cal, "headwardPivotY", 1400.0)
    self._headwardPivotXTolerance = _calibration_float(
      cal, "headwardPivotXTolerance", 150.0
    )
    self._headwardPivotYTolerance = _calibration_float(
      cal, "headwardPivotYTolerance", 300.0
    )

  # -- public properties ---------------------------------------------------

  @property
  def max_velocity(self) -> float:
    return self._maxVelocity

  @max_velocity.setter
  def max_velocity(self, value: float) -> None:
    self._maxVelocity = value

  @property
  def max_slow_velocity(self) -> float:
    return self._maxSlowVelocity

  @property
  def transfer_left(self) -> float:
    return self._transferLeft

  @property
  def transfer_right(self) -> float:
    return self._transferRight

  @property
  def limit_left(self) -> float:
    return self._limitLeft

  @property
  def limit_right(self) -> float:
    return self._limitRight

  @property
  def zlimit_front(self) -> float:
    return self._zlimitFront

  @property
  def zlimit_rear(self) -> float:
    return self._zlimitRear

  # -- validation ----------------------------------------------------------

  def current_motion_safety_limits(self) -> MotionSafetyLimits:
    return MotionSafetyLimits(
      limit_left=float(self._limitLeft),
      limit_right=float(self._limitRight),
      limit_bottom=float(self._limitBottom),
      limit_top=float(self._limitTop),
      transfer_left=float(self._transferLeft),
      transfer_right=float(self._transferRight),
      transfer_left_margin=float(self._transferLeftMargin),
      transfer_y_threshold=float(self._transferYThreshold),
      headward_pivot_x=float(self._headwardPivotX),
      headward_pivot_y=float(self._headwardPivotY),
      headward_pivot_x_tolerance=float(self._headwardPivotXTolerance),
      headward_pivot_y_tolerance=float(self._headwardPivotYTolerance),
      queued_motion_z_collision_threshold=float(self._queuedMotionZCollisionThreshold),
      arc_max_step_rad=float(self._arcMaxStepRad),
      arc_max_chord=float(self._arcMaxChord),
      apa_collision_bottom_y=float(self._apaCollisionBottomY),
      apa_collision_top_y=float(self._apaCollisionTopY),
      transfer_zone_head_min_x=float(self._transferZoneHeadMinX),
      transfer_zone_head_max_x=float(self._transferZoneHeadMaxX),
      transfer_zone_foot_min_x=float(self._transferZoneFootMinX),
      transfer_zone_foot_max_x=float(self._transferZoneFootMaxX),
      support_collision_bottom_min_y=float(self._supportCollisionBottomMinY),
      support_collision_bottom_max_y=float(self._supportCollisionBottomMaxY),
      support_collision_middle_min_y=float(self._supportCollisionMiddleMinY),
      support_collision_middle_max_y=float(self._supportCollisionMiddleMaxY),
      support_collision_top_min_y=float(self._supportCollisionTopMinY),
      support_collision_top_max_y=float(self._supportCollisionTopMaxY),
      geometry_epsilon=float(self._geometryEpsilon),
    )

  def validate_xy_move_target(
    self,
    startX: float,
    startY: float,
    targetX: float,
    targetY: float,
  ) -> Optional[str]:
    try:
      validate_xy_move_within_safety_limits(
        (float(startX), float(startY)),
        (float(targetX), float(targetY)),
        self.current_motion_safety_limits(),
      )
    except ValueError as exception:
      return str(exception)
    return None

  # -- blocker diagnostics -------------------------------------------------

  @staticmethod
  def _stateObjectName(stateObject: object) -> str:
    if stateObject is None:
      return "<None>"
    return stateObject.__class__.__name__

  @staticmethod
  def _formatBlockerDict(blocker: dict) -> str:
    parts = []

    state = blocker.get("state")
    if state:
      parts.append(str(state))

    moveType = blocker.get("moveType")
    if moveType:
      parts.append("move=" + str(moveType))

    errorCode = blocker.get("errorCode")
    if errorCode:
      message = blocker.get("errorMessage")
      if message:
        parts.append("error=" + str(errorCode) + ":" + str(message))
      else:
        parts.append("error=" + str(errorCode))

    if blocker.get("queuedSafeZMove") is not None:
      parts.append("queued_safe_z")

    positionTarget = blocker.get("positionTarget")
    if positionTarget is not None:
      parts.append("target=" + str(positionTarget))

    latchTarget = blocker.get("latchTarget")
    if latchTarget is not None:
      parts.append("latch_target=" + str(latchTarget))

    zTarget = blocker.get("zTarget")
    if zTarget is not None:
      parts.append("z_target=" + str(zTarget))

    transfer = blocker.get("transfer")
    if isinstance(transfer, dict):
      parts.append(
        "transfer="
        + ",".join(
          [
            "stagePresent=" + str(bool(transfer.get("stagePresent"))),
            "fixedPresent=" + str(bool(transfer.get("fixedPresent"))),
            "stageLatched=" + str(bool(transfer.get("stageLatched"))),
            "fixedLatched=" + str(bool(transfer.get("fixedLatched"))),
            "actuatorPos=" + str(transfer.get("actuatorPos")),
          ]
        )
      )

    errorMessage = blocker.get("errorMessage")
    if errorMessage and not errorCode:
      parts.append("error=" + str(errorMessage))

    return ",".join(parts)

  def manual_movement_blocker_message(self) -> str:
    blockers = []

    blockers.append(
      "control="
      + self._stateObjectName(getattr(self._controlStateMachine, "state", None))
    )

    stopMode = getattr(self._controlStateMachine, "stopMode", None)
    stopStateMachine = getattr(stopMode, "stopStateMachine", None)
    stopStateName = self._stateObjectName(getattr(stopStateMachine, "state", None))
    if stopStateName != "<None>":
      blockers.append("stop=" + stopStateName)

    plcLogic = getattr(self._io, "plcLogic", None)
    if plcLogic is not None:
      plcBlocker = None
      if hasattr(plcLogic, "getReadinessBlocker"):
        plcBlocker = plcLogic.getReadinessBlocker()
      elif hasattr(plcLogic, "isReady") and not plcLogic.isReady():
        plcBlocker = {"state": "not-ready"}
      if plcBlocker is not None:
        blockers.append("plc=" + self._formatBlockerDict(plcBlocker))

    head = getattr(self._io, "head", None)
    if head is not None:
      headBlocker = None
      if hasattr(head, "getReadinessBlocker"):
        headBlocker = head.getReadinessBlocker()
      elif hasattr(head, "isReady") and not head.isReady():
        headBlocker = {"state": "not-ready"}
      if headBlocker is not None:
        blockers.append("head=" + self._formatBlockerDict(headBlocker))

    return "Machine not ready: " + "; ".join(blockers) + "."
