###############################################################################
# Name: process_context.py
# Uses: Protocol defining the surface area that ManualCalibration and
#       TemplateRecipeBase require from the Process orchestrator.
###############################################################################

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
  from dune_winder.core.control_state_machine import ControlStateMachine
  from dune_winder.core.winder_workspace import WinderWorkspace
  from dune_winder.io.maps.base_io import BaseIO
  from dune_winder.library.app_config import AppConfig
  from dune_winder.library.log import Log
  from dune_winder.library.time_source import TimeSource


@runtime_checkable
class ProcessContext(Protocol):
  """Narrow interface consumed by ManualCalibration and TemplateRecipeBase.

  Process satisfies this protocol structurally — no explicit subclassing
  required.  The protocol documents exactly which members the satellite
  classes depend on, enabling future substitution for testing or further
  decomposition.
  """

  workspace: Optional[WinderWorkspace]
  controlStateMachine: ControlStateMachine
  _log: Log
  _io: BaseIO
  _systemTime: TimeSource
  _configuration: AppConfig
  _workspaceCalibrationDirectory: str

  def getRecipeLayer(self) -> Optional[str]:
    ...

  def manualSeekXY(
    self,
    xPosition: object = None,
    yPosition: object = None,
    velocity: object = None,
    acceleration: object = None,
    deceleration: object = None,
  ) -> bool:
    ...
