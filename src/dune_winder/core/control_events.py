###############################################################################
# Name: control_events.py
# Uses: Typed events dispatched to the control state machine.
###############################################################################

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class StartWindEvent:
  pass


@dataclass(frozen=True)
class StopMotionEvent:
  pass


@dataclass(frozen=True)
class SetLoopModeEvent:
  enabled: bool


@dataclass(frozen=True)
class ManualModeEvent:
  seekX: Optional[float] = None
  seekY: Optional[float] = None
  seekZ: Optional[float] = None
  velocity: Optional[float] = None
  acceleration: Optional[float] = None
  deceleration: Optional[float] = None
  setHeadPosition: Optional[int] = None
  idleServos: bool = False
  executeGCode: bool = False
  isJogging: bool = False


@dataclass(frozen=True)
class SetManualJoggingEvent:
  isJogging: bool


@dataclass(frozen=True)
class CalibrationModeEvent:
  seekX: Optional[float] = None
  seekY: Optional[float] = None
  velocity: Optional[float] = None
  acceleration: Optional[float] = None
  deceleration: Optional[float] = None
