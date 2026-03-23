"""Ladder-backed in-memory PLC simulator."""

from __future__ import annotations

import copy
import threading
from pathlib import Path
from typing import Any

from dune_winder.plc_ladder import JSRRegistry
from dune_winder.plc_ladder import RllParser
from dune_winder.plc_ladder import RoutineExecutor
from dune_winder.plc_ladder import RuntimeState
from dune_winder.plc_ladder import ScanContext
from dune_winder.plc_ladder import TagStore
from dune_winder.plc_ladder import load_imperative_routine_from_source
from dune_winder.plc_ladder import load_plc_metadata
from dune_winder.plc_ladder import transpile_routine_to_python
from dune_winder.queued_motion.segment_patterns import cap_segments_speed_by_axis_velocity
from dune_winder.queued_motion.segment_types import MotionSegment

from .simulated_plc import SimulatedPLC


class LadderSimulatedPLC(SimulatedPLC):
  _PLC_ROOT = Path(__file__).resolve().parents[4] / "plc"
  _LATCH_PROGRAM = "Latch_UnLatch_State_6_7_8"

  _SCAN_ORDER = (
    ("MainProgram", "main"),
    ("Initialize", "main"),
    ("Ready_State_1", "main"),
    ("MoveXY_State_2_3", "main"),
    ("MoveZ_State_4_5", "main"),
    ("xz_move", "xz_move"),
    ("Error_State_10", "main"),
    ("motionQueue", "main"),
  )
  _ROUTINES_TO_LOAD = _SCAN_ORDER + (
    ("MoveXY_State_2_3", "xy_speed_regulator"),
  )

  _MOVE_TO_STATE = {
    SimulatedPLC.MOVE_JOG_XY: SimulatedPLC.STATE_XY_JOG,
    SimulatedPLC.MOVE_SEEK_XY: SimulatedPLC.STATE_XY_SEEK,
    SimulatedPLC.MOVE_JOG_Z: SimulatedPLC.STATE_Z_JOG,
    SimulatedPLC.MOVE_SEEK_Z: SimulatedPLC.STATE_Z_SEEK,
    SimulatedPLC.MOVE_LATCH: SimulatedPLC.STATE_LATCHING,
    SimulatedPLC.MOVE_HOME_LATCH: SimulatedPLC.STATE_LATCH_HOMEING,
    SimulatedPLC.MOVE_LATCH_UNLOCK: SimulatedPLC.STATE_LATCH_RELEASE,
    SimulatedPLC.MOVE_UNSERVO: SimulatedPLC.STATE_UNSERVO,
    SimulatedPLC.MOVE_PLC_INIT: SimulatedPLC.STATE_INIT,
    SimulatedPLC.MOVE_SEEK_XZ: SimulatedPLC.STATE_XZ_SEEK,
  }
  _LATCH_STUB_MOVE_TYPES = {
    SimulatedPLC.MOVE_LATCH,
    SimulatedPLC.MOVE_HOME_LATCH,
    SimulatedPLC.MOVE_LATCH_UNLOCK,
  }

  _MACHINE_BIT_ALIASES = {
    1: ("Z_RETRACTED_1A",),
    2: ("Z_RETRACTED_1B",),
    3: ("Z_RETRACTED_2A",),
    4: ("Z_RETRACTED_2B",),
    5: ("Z_EXTENDED",),
    6: ("Z_STAGE_LATCHED",),
    7: ("Z_FIXED_LATCHED",),
    8: ("Z_EOT",),
    9: ("Z_STAGE_PRESENT",),
    10: ("Z_FIXED_PRESENT",),
    14: ("X_PARKED",),
    15: ("X_XFER_OK",),
    16: ("Y_MOUNT_XFER_OK",),
    17: ("Y_XFER_OK",),
    18: ("PLUS_Y_EOT",),
    19: ("MINUS_Y_EOT",),
    20: ("PLUS_X_EOT",),
    21: ("MINUS_X_EOT",),
    22: ("APA_IS_VERTICAL",),
    23: (),
    25: (),
    26: ("FRAME_LOC_HD_TOP",),
    27: ("FRAME_LOC_HD_MID",),
    28: ("FRAME_LOC_HD_BTM",),
    29: ("FRAME_LOC_FT_TOP",),
    30: ("FRAME_LOC_FT_MID",),
    31: ("FRAME_LOC_FT_BTM",),
  }
  _ALIASES_TO_MACHINE_BITS = {
    alias: bit
    for bit, aliases in _MACHINE_BIT_ALIASES.items()
    for alias in aliases
  }

  def __init__(self, ipAddress="SIM", routine_backend: str = "ast"):
    super().__init__(ipAddress)

    self._metadata = load_plc_metadata(self._PLC_ROOT)
    self._tag_store = TagStore(self._metadata, use_exported_values=True)
    self._jsr_registry = JSRRegistry()
    self._executor = RoutineExecutor()
    self._routine_backend = str(routine_backend)
    self._ctx = ScanContext(
      tag_store=self._tag_store,
      jsr_registry=self._jsr_registry,
      runtime_state=RuntimeState(scan_time_ms=100),
    )
    self._routines = {}
    self._scan_cycle_active = False

    self._load_routines()
    self._register_jsr_targets()
    self._bootstrap_tags()
    self._apply_scan(advance_runtime=False)

  # ---------------------------------------------------------------------
  def initialize(self):
    self._isFunctional = True
    return self._isFunctional

  # ---------------------------------------------------------------------
  def isNotFunctional(self):
    return not self._isFunctional

  # ---------------------------------------------------------------------
  def begin_scan_cycle(self):
    with self._lock:
      if self._scan_cycle_active:
        return
      self._scan_cycle_active = True
      self._apply_scan()

  # ---------------------------------------------------------------------
  def end_scan_cycle(self):
    with self._lock:
      self._scan_cycle_active = False

  # ---------------------------------------------------------------------
  def read(self, tag):
    with self._lock:
      if not self._scan_cycle_active:
        self._apply_scan()

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
      shouldOverride = override
      if shouldOverride is None:
        shouldOverride = (
          self._machineBitIndex(tagName) is not None
          or tagName in self._ALIASES_TO_MACHINE_BITS
          or ":" in tagName
        )
      shouldOverride = bool(shouldOverride)

      if shouldOverride:
        self._overrides[tagName] = self._coerceBit(value) if self._machineBitIndex(tagName) is not None else value
        self._apply_logic_overrides()
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
        self._refresh_io_state()
        return {"cleared": count}

      tagName = str(name)
      cleared = tagName in self._overrides
      self._overrides.pop(tagName, None)
      if cleared:
        self._refresh_io_state()
      return {"cleared": 1 if cleared else 0, "name": tagName}

  # ---------------------------------------------------------------------
  def inject_error(self, code=3003, state=None):
    with self._lock:
      errorState = self.STATE_ERROR if state is None else int(state)
      self._abort_active_motion()
      self._ctx.set_value("ERROR_CODE", int(code))
      self._ctx.set_value("STATE", errorState)
      self._ctx.set_value("NEXTSTATE", errorState)
      self._ctx.set_value("MOVE_TYPE", self.MOVE_RESET)
      return self._statusSnapshot()

  # ---------------------------------------------------------------------
  def clear_error(self):
    with self._lock:
      self._abort_active_motion()
      self._ctx.set_value("ERROR_CODE", 0)
      self._ctx.set_value("MOVE_TYPE", self.MOVE_RESET)
      self._ctx.set_value("STATE", self.STATE_READY)
      self._ctx.set_value("NEXTSTATE", self.STATE_READY)
      return self._statusSnapshot()

  # ---------------------------------------------------------------------
  def _load_routines(self):
    parser = RllParser()
    for programName, routineName in self._ROUTINES_TO_LOAD:
      program = self._metadata.programs[programName]
      routine_dir = routineName
      if routineName == program.main_routine_name and (self._PLC_ROOT / programName / "main" / "pasteable.rll").exists():
        routine_dir = "main"
      routine_path = self._PLC_ROOT / programName / routine_dir / "pasteable.rll"
      if not routine_path.exists():
        continue
      routine = parser.parse_routine_text(
        routineName,
        routine_path.read_text(encoding="utf-8"),
        program=programName,
        source_path=routine_path,
      )
      loaded = routine
      if self._routine_backend == "imperative":
        loaded = load_imperative_routine_from_source(transpile_routine_to_python(routine))
      self._routines[(programName, routineName)] = loaded

  # ---------------------------------------------------------------------
  def _register_jsr_targets(self):
    for (programName, routineName), routine in self._routines.items():
      if routineName == "main":
        continue
      self._jsr_registry.register(
        f"{programName}:{routineName}",
        lambda ctx, loaded=routine: self._execute_loaded_callable(loaded, ctx),
      )
      if routineName not in {"CapSegSpeed"}:
        self._jsr_registry.register(
          routineName,
          lambda ctx, loaded=routine: self._execute_loaded_callable(loaded, ctx),
        )

    self._jsr_registry.register("motionQueue:CapSegSpeed", self._cap_seg_speed_jsr)
    self._jsr_registry.register("CapSegSpeed", self._cap_seg_speed_jsr)

  # ---------------------------------------------------------------------
  def _bootstrap_tags(self):
    self._reset_runtime_structures()
    self._ctx.set_value("STATE", self.STATE_READY)
    self._ctx.set_value("NEXTSTATE", self.STATE_READY)
    self._ctx.set_value("MOVE_TYPE", self.MOVE_RESET)
    self._ctx.set_value("ERROR_CODE", 0)
    self._ctx.set_value("INIT_DONE", True)
    self._ctx.set_value("HEAD_POS", 0)
    self._ctx.set_value("ACTUATOR_POS", 0)
    self._ctx.set_value("LATCH_ACTUATOR_HOMED", True)
    self._ctx.set_value("MACHINE_SW_STAT[0]", True)
    self._ctx.set_value("UseAasCurrent", True)
    self._ctx.set_value("QueueCtl.POS", 0, program="motionQueue")
    self._ctx.set_value("QueueCtl.EM", True, program="motionQueue")
    self._ctx.set_value("QueueCtl.DN", False, program="motionQueue")

    for axis in ("X_axis", "Y_axis", "Z_axis"):
      self._ctx.set_value(f"{axis}.ActualPosition", 0.0)
      self._ctx.set_value(f"{axis}.ActualVelocity", 0.0)
      self._ctx.set_value(f"{axis}.CommandAcceleration", 0.0)
      self._ctx.set_value(f"{axis}.DriveEnableStatus", False)
      self._ctx.set_value(f"{axis}.PhysicalAxisFault", False)
      self._ctx.set_value(f"{axis}.ModuleFault", False)
      self._ctx.set_value(f"{axis}.SafeTorqueOffInhibit", False)
      self._ctx.set_value(f"{axis}.CoordinatedMotionStatus", False)

    self._ctx.set_value("X_Y.PhysicalAxisFault", False)
    self._ctx.set_value("X_Y.MovePendingStatus", False)
    self._ctx.set_value("X_Y.MovePendingQueueFullStatus", False)
    self._ctx.set_value("xz.PhysicalAxisFault", False)
    self._ctx.set_value("xz.MovePendingStatus", False)
    self._ctx.set_value("xz.MovePendingQueueFullStatus", False)

  # ---------------------------------------------------------------------
  def _reset_runtime_structures(self):
    for definition in self._metadata.controller_tags.values():
      self._reset_tag_definition(definition.name, definition.program, definition.data_type_name)
    for program in self._metadata.programs.values():
      for definition in program.tags.values():
        self._reset_tag_definition(definition.name, program.name, definition.data_type_name)

  # ---------------------------------------------------------------------
  def _reset_tag_definition(self, name: str, program: str | None, dataTypeName: str | None):
    if dataTypeName not in {"MOTION_INSTRUCTION", "TIMER", "CONTROL"}:
      return

    value = self._ctx.get_value(name, program=program)
    if isinstance(value, list):
      reset = [self._reset_structure_value(item, dataTypeName) for item in value]
    else:
      reset = self._reset_structure_value(value, dataTypeName)
    self._ctx.set_value(name, reset, program=program)

  # ---------------------------------------------------------------------
  def _reset_structure_value(self, value, dataTypeName: str):
    struct = copy.deepcopy(value)
    if dataTypeName == "MOTION_INSTRUCTION":
      flags = struct.get("FLAGS", 0)
      for key in list(struct):
        struct[key] = False if isinstance(struct[key], bool) else 0
      struct["FLAGS"] = flags
      return struct
    if dataTypeName == "TIMER":
      struct["ACC"] = 0
      struct["EN"] = False
      struct["TT"] = False
      struct["DN"] = False
      return struct
    if dataTypeName == "CONTROL":
      struct["POS"] = 0
      struct["EN"] = False
      struct["EU"] = False
      struct["DN"] = False
      struct["EM"] = True
      struct["ER"] = False
      struct["UL"] = False
      struct["IN"] = False
      struct["FD"] = False
      return struct
    return struct

  # ---------------------------------------------------------------------
  def _apply_scan(self, advance_runtime: bool = True):
    if advance_runtime:
      self._executor.advance_runtime(self._ctx)
      self._cycle = self._ctx.scan_count

    self._sync_builtin_inputs()
    self._execute_loaded_routine("MainProgram", "main")
    self._apply_logic_overrides()
    for programName, routineName in self._SCAN_ORDER[1:]:
      self._execute_loaded_routine(programName, routineName)
    self._apply_logic_overrides()
    self._apply_latch_stub()
    self._apply_compatibility_state()

  # ---------------------------------------------------------------------
  def _refresh_io_state(self):
    self._sync_builtin_inputs()
    self._execute_loaded_routine("MainProgram", "main")
    self._apply_logic_overrides()

  # ---------------------------------------------------------------------
  def _execute_loaded_routine(self, programName: str, routineName: str):
    if programName == "Initialize" and routineName == "main":
      if (
        int(self._ctx.get_value("STATE")) != self.STATE_INIT
        and int(self._ctx.get_value("MOVE_TYPE")) != self.MOVE_PLC_INIT
        and bool(self._ctx.get_value("INIT_DONE"))
      ):
        return
    routine = self._routines.get((programName, routineName))
    if routine is not None:
      self._execute_loaded_callable(routine, self._ctx)

  # ---------------------------------------------------------------------
  def _execute_loaded_callable(self, routine, ctx: ScanContext):
    if callable(routine):
      routine(ctx)
      return
    self._executor.execute_routine(routine, ctx)

  # ---------------------------------------------------------------------
  def _sync_builtin_inputs(self):
    x = float(self._ctx.get_value("X_axis.ActualPosition"))
    y = float(self._ctx.get_value("Y_axis.ActualPosition"))
    z = float(self._ctx.get_value("Z_axis.ActualPosition"))
    headPos = int(self._ctx.get_value("HEAD_POS"))
    actuatorPos = int(self._ctx.get_value("ACTUATOR_POS"))

    zRetracted = z <= (self._limits["zFront"] + 1.0)
    zExtended = z >= (self._limits["zBack"] - 1.0)
    xTransfer = self._limits["transferLeft"] <= x <= self._limits["transferRight"]
    yTransfer = self._limits["transferBottom"] <= y <= self._limits["transferTop"]
    xPark = abs(x - self._limits["parkX"]) <= 1.0
    plusYEot = True
    minusYEot = True
    plusXEot = True
    minusXEot = True
    zEot = True

    inputs = {
      "Local:1:I.Pt00.Data": zRetracted,
      "Local:1:I.Pt01.Data": not zRetracted,
      "Local:1:I.Pt02.Data": zRetracted,
      "Local:1:I.Pt03.Data": not zRetracted,
      "Local:1:I.Pt04.Data": zExtended,
      "Local:1:I.Pt06.Data": plusYEot,
      "Local:1:I.Pt07.Data": zEot,
      "Local:1:I.Pt10.Data": not (headPos == 0),
      "Local:1:I.Pt11.Data": headPos == 0,
      "Local:1:I.Pt12.Data": yTransfer,
      "Local:1:I.Pt13.Data": yTransfer,
      "Local:1:I.Pt15.Data": False,
      "Local:2:I.Pt00.Data": xTransfer,
      "Local:2:I.Pt01.Data": headPos == 3,
      "Local:2:I.Pt02.Data": not (headPos == 3),
      "Local:2:I.Pt04.Data": xPark,
      "Local:2:I.Pt06.Data": False,
      "Local:2:I.Pt08.Data": plusXEot,
      "Local:2:I.Pt10.Data": minusXEot,
      "Local:2:I.Pt12.Data": minusYEot,
      "Local:2:I.Pt13.Data": False,
      "Local:2:I.Pt14.Data": True,
      "Local:6:I.Pt00.Data": headPos == 0 and actuatorPos == 0,
      "Local:6:I.Pt01.Data": headPos == 0 and actuatorPos == 1,
      "Local:6:I.Pt02.Data": headPos == 0 and actuatorPos == 2,
      "Local:6:I.Pt03.Data": headPos == 3 and actuatorPos == 0,
      "Local:6:I.Pt04.Data": headPos == 3 and actuatorPos == 1,
      "Local:6:I.Pt05.Data": headPos == 3 and actuatorPos == 2,
      "DUNEW2PLC2:1:I.Pt00Data": True,
      "DUNEW2PLC2:1:I.Pt01Data": True,
      "DUNEW2PLC2:1:I.Pt02Data": True,
      "DUNEW2PLC2:1:I.Pt03Data": True,
      "DUNEW2PLC2:1:I.Pt04Data": True,
      "DUNEW2PLC2:1:I.Pt06Data": False,
    }

    for name, value in inputs.items():
      resolved = self._overrides.get(name, value)
      if self._ctx.exists(name):
        self._ctx.set_value(name, resolved)
      else:
        self._ctx.builtin_values[name] = resolved

  # ---------------------------------------------------------------------
  def _apply_logic_overrides(self):
    for name, value in self._overrides.items():
      bitIndex = self._machineBitIndex(name)
      if bitIndex is not None:
        self._ctx.set_value(name, bool(value))
        for alias in self._MACHINE_BIT_ALIASES.get(bitIndex, ()):
          self._ctx.set_value(alias, bool(value))
        continue

      bitIndex = self._ALIASES_TO_MACHINE_BITS.get(name)
      if bitIndex is not None:
        self._ctx.set_value(name, bool(value))
        self._ctx.set_value(f"MACHINE_SW_STAT[{bitIndex}]", bool(value))
        continue

      if ":" in name:
        if self._ctx.exists(name):
          self._ctx.set_value(name, value)
        else:
          self._ctx.builtin_values[name] = value

  # ---------------------------------------------------------------------
  def _apply_compatibility_state(self):
    queueActive = bool(self._ctx.get_value("CurIssued")) or bool(self._ctx.get_value("NextIssued"))
    queueActive = queueActive or bool(self._ctx.get_value("X_Y.MovePendingStatus"))
    state = int(self._ctx.get_value("STATE"))
    if queueActive and state not in {self.STATE_ERROR, self.STATE_EOT}:
      self._ctx.set_value("STATE", self.STATE_QUEUED_MOTION)
      self._ctx.set_value("NEXTSTATE", self.STATE_QUEUED_MOTION)
      return
    if state == self.STATE_QUEUED_MOTION and not queueActive:
      self._ctx.set_value("STATE", self.STATE_READY)
      self._ctx.set_value("NEXTSTATE", self.STATE_READY)

  # ---------------------------------------------------------------------
  def _apply_latch_stub(self) -> bool:
    moveType = int(self._ctx.get_value("MOVE_TYPE"))
    state = int(self._ctx.get_value("STATE"))
    if moveType not in self._LATCH_STUB_MOVE_TYPES and state not in {
      self.STATE_LATCHING,
      self.STATE_LATCH_HOMEING,
      self.STATE_LATCH_RELEASE,
    }:
      return False

    if moveType == self.MOVE_RESET and state not in {
      self.STATE_LATCHING,
      self.STATE_LATCH_HOMEING,
      self.STATE_LATCH_RELEASE,
    }:
      return False
    if moveType == self.MOVE_RESET and int(self._ctx.get_value("NEXTSTATE")) == self.STATE_READY:
      return False

    if moveType == self.MOVE_HOME_LATCH or state == self.STATE_LATCH_HOMEING:
      self._ctx.set_value("ACTUATOR_POS", 0)
      if int(self._ctx.get_value("HEAD_POS")) == -1:
        self._ctx.set_value("HEAD_POS", 0)
      self._ctx.set_value("LATCH_ACTUATOR_HOMED", True)
      self._ctx.set_value("MACHINE_SW_STAT[0]", True)
    elif moveType == self.MOVE_LATCH_UNLOCK or state == self.STATE_LATCH_RELEASE:
      self._ctx.set_value("ACTUATOR_POS", 2)
      self._ctx.set_value("LATCH_ACTUATOR_HOMED", False)
      self._ctx.set_value("MACHINE_SW_STAT[0]", False)
    else:
      self._ctx.set_value(
        "PREV_ACT_POS",
        int(self._ctx.get_value("ACTUATOR_POS")),
        program=self._LATCH_PROGRAM,
      )
      self._advance_latch_stub()
      self._ctx.set_value("MACHINE_SW_STAT[0]", bool(self._ctx.get_value("LATCH_ACTUATOR_HOMED")))

    self._ctx.set_value("ERROR_CODE", 0)
    self._ctx.set_value("MOVE_TYPE", self.MOVE_RESET)
    self._ctx.set_value("NEXTSTATE", self.STATE_READY)
    return True

  # ---------------------------------------------------------------------
  def _advance_latch_stub(self):
    actuator = int(self._ctx.get_value("ACTUATOR_POS"))
    actuator = (actuator + 1) % 3
    self._ctx.set_value("ACTUATOR_POS", actuator)

    headPos = int(self._ctx.get_value("HEAD_POS"))
    if actuator == 2 and headPos in (0, 3):
      self._ctx.set_value("HEAD_POS", 3 if headPos == 0 else 0)

  # ---------------------------------------------------------------------
  def _cap_seg_speed_jsr(self, ctx: ScanContext):
    queueCount = int(ctx.get_value("QueueCtl.POS", program="motionQueue"))
    if queueCount <= 0:
      return

    segments = []
    for index in range(queueCount):
      raw = ctx.get_value(f"SegQueue[{index}]")
      segments.append(
        MotionSegment(
          seq=int(raw.get("Seq", index + 1)),
          x=float(raw.get("XY", [0.0, 0.0])[0]),
          y=float(raw.get("XY", [0.0, 0.0])[1]),
          speed=float(raw.get("Speed", 0.0)),
          accel=float(raw.get("Accel", 0.0)),
          decel=float(raw.get("Decel", 0.0)),
          jerk_accel=float(raw.get("JerkAccel", 0.0)),
          jerk_decel=float(raw.get("JerkDecel", 0.0)),
          term_type=int(raw.get("TermType", 0)),
          seg_type=int(raw.get("SegType", 1)),
          circle_type=int(raw.get("CircleType", 0)),
          via_center_x=float(raw.get("ViaCenter", [0.0, 0.0])[0]),
          via_center_y=float(raw.get("ViaCenter", [0.0, 0.0])[1]),
          direction=int(raw.get("Direction", 0)),
        )
      )

    try:
      capped = cap_segments_speed_by_axis_velocity(
        segments,
        v_x_max=float(ctx.get_value("v_x_max")),
        v_y_max=float(ctx.get_value("v_y_max")),
        start_xy=(
          float(ctx.get_value("X_axis.ActualPosition")),
          float(ctx.get_value("Y_axis.ActualPosition")),
        ),
      )
    except ValueError:
      ctx.set_value("FaultCode", 9)
      ctx.set_value("QueueFault", True)
      return

    for index, segment in enumerate(capped):
      ctx.set_value(f"SegQueue[{index}].Speed", float(segment.speed))

  # ---------------------------------------------------------------------
  def _abort_active_motion(self):
    self._ctx.runtime_state.axis_moves.clear()
    self._ctx.runtime_state.coordinate_moves.clear()
    self._ctx.runtime_state.coordinate_pending_moves.clear()
    for axis in ("X_axis", "Y_axis", "Z_axis"):
      self._ctx.set_value(f"{axis}.ActualVelocity", 0.0)
      self._ctx.set_value(f"{axis}.CommandAcceleration", 0.0)
      self._ctx.set_value(f"{axis}.CoordinatedMotionStatus", False)

  # ---------------------------------------------------------------------
  def _writeTag(self, tagName, value):
    bitIndex = self._machineBitIndex(tagName)
    if bitIndex is not None:
      self._overrides[tagName] = self._coerceBit(value)
      self._apply_logic_overrides()
      return

    if tagName in self._ALIASES_TO_MACHINE_BITS:
      self._overrides[tagName] = self._coerceBit(value)
      self._apply_logic_overrides()
      return

    if tagName == "MOVE_TYPE":
      moveType = int(value)
      self._ctx.set_value(tagName, moveType)
      nextState = self._MOVE_TO_STATE.get(moveType)
      if nextState is not None:
        self._ctx.set_value("NEXTSTATE", nextState)
        self._ctx.set_value("STATE", nextState)
      elif moveType == self.MOVE_RESET and int(self._ctx.get_value("STATE")) == self.STATE_ERROR:
        self._ctx.set_value("NEXTSTATE", self.STATE_READY)
      return

    if tagName in ("STATE", "NEXTSTATE", "ERROR_CODE", "HEAD_POS", "ACTUATOR_POS"):
      self._ctx.set_value(tagName, int(value))
      return

    if tagName == "xz_position_target":
      if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("xz_position_target must be a two-element sequence.")
      self._ctx.set_value(tagName, [float(value[0]), float(value[1])])
      return

    self._ctx.set_value(tagName, value)

  # ---------------------------------------------------------------------
  def _readTagValue(self, tagName):
    if tagName in self._overrides:
      return copy.deepcopy(self._overrides[tagName])
    return copy.deepcopy(self._ctx.get_value(tagName))

  # ---------------------------------------------------------------------
  def _statusSnapshot(self):
    return {
      "mode": "SIM",
      "simEngine": "LADDER",
      "functional": self._isFunctional,
      "cycle": self._cycle,
      "scanCount": self._ctx.scan_count,
      "state": int(self._ctx.get_value("STATE")),
      "moveType": int(self._ctx.get_value("MOVE_TYPE")),
      "errorCode": int(self._ctx.get_value("ERROR_CODE")),
      "headPos": int(self._ctx.get_value("HEAD_POS")),
      "actuatorPos": int(self._ctx.get_value("ACTUATOR_POS")),
      "queueCount": int(self._ctx.get_value("QueueCount")),
      "curIssued": int(bool(self._ctx.get_value("CurIssued"))),
      "nextIssued": int(bool(self._ctx.get_value("NextIssued"))),
      "movePending": int(bool(self._ctx.get_value("X_Y.MovePendingStatus"))),
      "overrides": sorted(self._overrides.keys()),
      "limits": dict(self._limits),
      "assumptions": list(self._MACHINE_SW_ASSUMPTIONS),
    }
