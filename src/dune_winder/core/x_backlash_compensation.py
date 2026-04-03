###############################################################################
# Name: x_backlash_compensation.py
# Uses: Convert between raw X-axis positions and effective real-space X.
###############################################################################

from __future__ import annotations


class XBacklashCompensation:
  _EPSILON = 1e-9

  def __init__(self, backlashMm: float = 0.0):
    self._backlashMm = 0.0
    self._direction = 0
    self.setBacklashMm(backlashMm)

  def setBacklashMm(self, backlashMm: float):
    backlash = float(backlashMm)
    if backlash < 0.0:
      backlash = 0.0
    self._backlashMm = backlash

  def getBacklashMm(self) -> float:
    return self._backlashMm

  def reset(self):
    self._direction = 0

  def getDirection(self) -> int:
    return self._direction

  def getEffectiveX(self, rawX: float) -> float:
    raw = float(rawX)
    if self._direction > 0:
      return raw - self._backlashMm
    return raw

  def getCommandedRawX(self, currentRawX: float, targetEffectiveX: float) -> float:
    currentEffective = self.getEffectiveX(currentRawX)
    targetEffective = float(targetEffectiveX)
    delta = targetEffective - currentEffective
    if delta > self._EPSILON:
      return targetEffective + self._backlashMm
    if delta < -self._EPSILON:
      return targetEffective
    return float(currentRawX)

  def noteCommand(self, currentRawX: float, targetEffectiveX: float):
    currentEffective = self.getEffectiveX(currentRawX)
    targetEffective = float(targetEffectiveX)
    delta = targetEffective - currentEffective
    if delta > self._EPSILON:
      self._direction = 1
    elif delta < -self._EPSILON:
      self._direction = -1

