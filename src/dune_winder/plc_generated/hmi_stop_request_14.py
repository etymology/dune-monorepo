from __future__ import annotations

from dune_winder.plc_ladder.ast import Routine
from dune_winder.plc_ladder.codegen_support import CMP
from dune_winder.plc_ladder.codegen_support import CPT
from dune_winder.plc_ladder.codegen_support import LEQ
from dune_winder.plc_ladder.codegen_support import MAS
from dune_winder.plc_ladder.codegen_support import MCS
from dune_winder.plc_ladder.codegen_support import OTE
from dune_winder.plc_ladder.codegen_support import OSR
from dune_winder.plc_ladder.codegen_support import ROUTINE
from dune_winder.plc_ladder.codegen_support import RUNG
from dune_winder.plc_ladder.codegen_support import XIC
from dune_winder.plc_ladder.codegen_support import XIO
from dune_winder.plc_ladder.emitter import RllEmitter


PROGRAM_NAME = "HMI_Stop_Request_14"
ROUTINE_NAME = "main"
ROUTINE_SYMBOL = "HMI_STOP_REQUEST_14_ROUTINE"

_DECEL = "1200"
_DECEL_UNITS = '"Units per sec2"'
_JERK = "1200"
_JERK_UNITS = '"Units per sec3"'


HMI_STOP_REQUEST_14_ROUTINE: Routine = ROUTINE(
  name=ROUTINE_NAME,
  program=PROGRAM_NAME,
  rungs=(
    RUNG(CMP("STATE=14"), OTE("STATE14_IND")),
    RUNG(XIC("STATE14_IND"), OSR("hmi_stop_entry_sb", "hmi_stop_entry_ob")),
    RUNG(
      XIC("hmi_stop_entry_ob"),
      MCS("X_Y", "hmi_xy_stop", "All", "Yes", _DECEL, _DECEL_UNITS, "Yes", _JERK, _JERK_UNITS),
    ),
    RUNG(
      XIC("hmi_stop_entry_ob"),
      MCS("xz", "hmi_xz_stop", "All", "Yes", _DECEL, _DECEL_UNITS, "Yes", _JERK, _JERK_UNITS),
    ),
    RUNG(
      XIC("hmi_stop_entry_ob"),
      MAS("X_axis", "hmi_x_axis_stop", "All", "Yes", _DECEL, _DECEL_UNITS, "Yes", _JERK, _JERK_UNITS),
    ),
    RUNG(
      XIC("hmi_stop_entry_ob"),
      MAS("Y_axis", "hmi_y_axis_stop", "All", "Yes", _DECEL, _DECEL_UNITS, "Yes", _JERK, _JERK_UNITS),
    ),
    RUNG(
      XIC("hmi_stop_entry_ob"),
      MAS("Z_axis", "hmi_z_axis_stop", "All", "Yes", _DECEL, _DECEL_UNITS, "Yes", _JERK, _JERK_UNITS),
    ),
    RUNG(XIC("STATE14_IND"), OTE("AbortQueue")),
    RUNG(XIC("STATE14_IND"), CPT("MOVE_TYPE", "0")),
    RUNG(
      XIC("STATE14_IND"),
      XIC("hmi_xy_stop.DN"),
      XIC("hmi_xz_stop.DN"),
      XIC("hmi_x_axis_stop.DN"),
      XIC("hmi_y_axis_stop.DN"),
      XIC("hmi_z_axis_stop.DN"),
      XIO("CurIssued"),
      XIO("NextIssued"),
      XIO("X_Y.MovePendingStatus"),
      LEQ("QueueCount", "0"),
      CPT("NEXTSTATE", "1"),
    ),
  ),
)


def emit_rll() -> str:
  return RllEmitter().emit_routine(HMI_STOP_REQUEST_14_ROUTINE)
