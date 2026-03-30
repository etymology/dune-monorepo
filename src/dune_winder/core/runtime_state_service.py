###############################################################################
# Name: runtime_state_service.py
# Uses: UI/runtime state helpers extracted from Process.
###############################################################################

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

from dune_winder.io.primitives.digital_input import DigitalInput
from dune_winder.library.Geometry.location import Location

if TYPE_CHECKING:
  from dune_winder.core.winder_workspace import WinderWorkspace
  from dune_winder.io.maps.base_io import BaseIO
  from dune_winder.machine.head_compensation import WirePathModel


class RuntimeStateService:
  """Collects UI-facing runtime state and persisted workspace state."""

  def __init__(
    self,
    io: BaseIO,
    headCompensation: WirePathModel,
    workspaceGetter: Callable[[], Optional[WinderWorkspace]],
    workspaceStateReader: Callable[[], dict],
  ):
    self._io = io
    self._headCompensation = headCompensation
    self._workspaceGetter = workspaceGetter
    self._workspaceStateReader = workspaceStateReader

  def _getUiAxisSnapshot(self, axis):
    return {
      "functional": axis.isFunctional(),
      "moving": axis.isSeeking(),
      "desiredPosition": axis.getDesiredPosition(),
      "position": axis.getPosition(),
      "velocity": axis.getVelocity(),
      "acceleration": axis.getAcceleration(),
      "seekStartPosition": axis.getSeekStartPosition(),
    }

  def _getUiInputSnapshot(self):
    inputs = {}
    for ioPoint in DigitalInput.digital_input_instances:
      inputs[ioPoint.getName()] = ioPoint.get()

    return inputs

  def _getUiHeadSide(self):
    headSide = 0
    if self._io.Z_Stage_Present.get():
      headSide += 1

    if self._io.Z_Fixed_Present.get():
      headSide += 2

    return headSide

  def getUiSnapshot(self):
    xAxis = self._getUiAxisSnapshot(self._io.xAxis)
    yAxis = self._getUiAxisSnapshot(self._io.yAxis)
    zAxis = self._getUiAxisSnapshot(self._io.zAxis)

    headAngle = 0
    if self._io.isFunctional():
      location = Location(
        xAxis["position"],
        yAxis["position"],
        zAxis["position"],
      )
      headAngle = self._headCompensation.getHeadAngle(location)

    return {
      "axes": {
        "x": xAxis,
        "y": yAxis,
        "z": zAxis,
      },
      "headAngle": headAngle,
      "headSide": self._getUiHeadSide(),
      "inputs": self._getUiInputSnapshot(),
      "plcNotFunctional": self._io.plc.isNotFunctional(),
    }

  def getWorkspaceState(self):
    workspace = self._workspaceGetter()
    if workspace is not None:
      return workspace.toDictionary()

    return self._workspaceStateReader()
