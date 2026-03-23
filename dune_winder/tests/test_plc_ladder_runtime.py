from __future__ import annotations

from pathlib import Path
import unittest

from dune_winder.io.devices.plc import PLC
from dune_winder.plc_ladder import JSRRegistry
from dune_winder.plc_ladder import PythonCodeGenerator
from dune_winder.plc_ladder import RllParser
from dune_winder.plc_ladder import RoutineExecutor
from dune_winder.plc_ladder import RuntimeState
from dune_winder.plc_ladder import ScanContext
from dune_winder.plc_ladder import TagStore
from dune_winder.plc_ladder import load_imperative_routine_from_source
from dune_winder.plc_ladder import load_plc_metadata


class PlcLadderRuntimeTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.metadata = load_plc_metadata("plc")

  def setUp(self):
    self.tag_store = TagStore(self.metadata, use_exported_values=True)
    self.ctx = ScanContext(
      tag_store=self.tag_store,
      jsr_registry=JSRRegistry(),
      runtime_state=RuntimeState(scan_time_ms=100),
    )
    self.executor = RoutineExecutor()
    self.parser = RllParser()

  def _make_ctx(self) -> ScanContext:
    return ScanContext(
      tag_store=TagStore(self.metadata, use_exported_values=True),
      jsr_registry=JSRRegistry(),
      runtime_state=RuntimeState(scan_time_ms=100),
    )

  def _assert_contexts_match(self, expected: ScanContext, actual: ScanContext, *, program: str | None):
    self.assertEqual(expected.tag_store.snapshot(), actual.tag_store.snapshot())
    if program is not None:
      self.assertEqual(expected.tag_store.snapshot(program), actual.tag_store.snapshot(program))
    self.assertEqual(expected.builtin_values, actual.builtin_values)
    self.assertEqual(expected.runtime_state.axis_moves, actual.runtime_state.axis_moves)
    self.assertEqual(expected.runtime_state.coordinate_moves, actual.runtime_state.coordinate_moves)
    self.assertEqual(expected.runtime_state.coordinate_pending_moves, actual.runtime_state.coordinate_pending_moves)
    self.assertEqual(expected.scan_count, actual.scan_count)

  def _assert_ast_and_generated_match(
    self,
    routine,
    *,
    setup=None,
    scans: int = 1,
    advance_runtime_scans: int = 0,
  ):
    source = PythonCodeGenerator().generate_routine(routine)
    generated = load_imperative_routine_from_source(source)
    ast_ctx = self._make_ctx()
    py_ctx = self._make_ctx()

    if setup is not None:
      setup(ast_ctx)
      setup(py_ctx)

    for _ in range(scans):
      self.executor.execute_routine(routine, ast_ctx)
      generated(py_ctx)
      self._assert_contexts_match(ast_ctx, py_ctx, program=routine.program)
      for _ in range(advance_runtime_scans):
        self.executor.advance_runtime(ast_ctx)
        self.executor.advance_runtime(py_ctx)
        self._assert_contexts_match(ast_ctx, py_ctx, program=routine.program)

  def test_branch_math_and_expression_execution(self):
    routine = self.parser.parse_routine_text(
      "main",
      "\n".join(
        [
          "XIC trigger MOV 3 source_a MOV 4 source_b",
          "XIC trigger ADD source_a source_b sum",
          "XIC trigger CPT hyp SQR(sum*sum)",
          "XIC trigger BST GRT sum 10 MOV 1 branch_hit NXB LEQ sum 10 MOV 2 branch_hit BND",
        ]
      ),
      program="MoveXY_State_2_3",
    )

    self.ctx.set_value("trigger", True)
    self.executor.execute_routine(routine, self.ctx)

    self.assertEqual(self.ctx.get_value("sum"), 7)
    self.assertEqual(self.ctx.get_value("hyp"), 7.0)
    self.assertEqual(self.ctx.get_value("branch_hit"), 2)

  def test_generated_python_matches_ast_for_branch_math_and_expression_execution(self):
    routine = self.parser.parse_routine_text(
      "main",
      "\n".join(
        [
          "XIC trigger MOV 3 source_a MOV 4 source_b",
          "XIC trigger ADD source_a source_b sum",
          "XIC trigger CPT hyp SQR(sum*sum)",
          "XIC trigger BST GRT sum 10 MOV 1 branch_hit NXB LEQ sum 10 MOV 2 branch_hit BND",
        ]
      ),
      program="MoveXY_State_2_3",
    )

    def setup(ctx: ScanContext):
      ctx.set_value("trigger", True)

    self._assert_ast_and_generated_match(routine, setup=setup)

  def test_osr_and_ons_only_pulse_on_rising_edge(self):
    routine = self.parser.parse_routine_text(
      "main",
      "\n".join(
        [
          "XIC trigger OSR storage pulse",
          "XIC trigger ONS oneshot_storage OTL oneshot_latched",
        ]
      ),
      program="Ready_State_1",
    )

    self.ctx.set_value("trigger", True)
    self.executor.execute_routine(routine, self.ctx)
    self.assertTrue(self.ctx.get_value("pulse"))
    self.assertTrue(self.ctx.get_value("oneshot_latched"))

    self.ctx.set_value("pulse", False)
    self.ctx.set_value("oneshot_latched", False)
    self.executor.execute_routine(routine, self.ctx)
    self.assertFalse(self.ctx.get_value("pulse"))
    self.assertFalse(self.ctx.get_value("oneshot_latched"))

    self.ctx.set_value("trigger", False)
    self.executor.execute_routine(routine, self.ctx)
    self.ctx.set_value("trigger", True)
    self.executor.execute_routine(routine, self.ctx)
    self.assertTrue(self.ctx.get_value("pulse"))
    self.assertTrue(self.ctx.get_value("oneshot_latched"))

  def test_ffl_and_ffu_update_queue_control_and_payload(self):
    routine = self.parser.parse_routine_text(
      "main",
      "\n".join(
        [
          "XIC load FFL IncomingSeg SegQueue[0] QueueCtl ? ?",
          "XIC unload FFU SegQueue[0] CurSeg QueueCtl ? ?",
        ]
      ),
      program="motionQueue",
    )

    self.ctx.set_value("IncomingSeg.Valid", True)
    self.ctx.set_value("IncomingSeg.Seq", 99)
    self.ctx.set_value("load", True)
    self.executor.execute_routine(routine, self.ctx)

    self.assertEqual(self.ctx.get_value("QueueCtl.POS"), 1)
    self.assertEqual(self.ctx.get_value("SegQueue[0].Seq"), 99)

    self.ctx.set_value("load", False)
    self.ctx.set_value("unload", True)
    self.executor.execute_routine(routine, self.ctx)

    self.assertEqual(self.ctx.get_value("QueueCtl.POS"), 0)
    self.assertEqual(self.ctx.get_value("CurSeg.Seq"), 99)
    self.assertFalse(self.ctx.get_value("SegQueue[0].Valid"))

  def test_generated_python_matches_ast_for_ffl_and_ffu(self):
    routine = self.parser.parse_routine_text(
      "main",
      "\n".join(
        [
          "XIC load FFL IncomingSeg SegQueue[0] QueueCtl ? ?",
          "XIC unload FFU SegQueue[0] CurSeg QueueCtl ? ?",
        ]
      ),
      program="motionQueue",
    )

    def setup(ctx: ScanContext):
      ctx.set_value("IncomingSeg.Valid", True)
      ctx.set_value("IncomingSeg.Seq", 99)
      ctx.set_value("load", True)

    self._assert_ast_and_generated_match(routine, setup=setup)

    def second_scan(ctx: ScanContext):
      ctx.set_value("IncomingSeg.Valid", True)
      ctx.set_value("IncomingSeg.Seq", 99)
      ctx.set_value("load", True)

    source = PythonCodeGenerator().generate_routine(routine)
    generated = load_imperative_routine_from_source(source)
    ast_ctx = self._make_ctx()
    py_ctx = self._make_ctx()
    second_scan(ast_ctx)
    second_scan(py_ctx)
    self.executor.execute_routine(routine, ast_ctx)
    generated(py_ctx)
    ast_ctx.set_value("load", False)
    py_ctx.set_value("load", False)
    ast_ctx.set_value("unload", True)
    py_ctx.set_value("unload", True)
    self.executor.execute_routine(routine, ast_ctx)
    generated(py_ctx)
    self._assert_contexts_match(ast_ctx, py_ctx, program="motionQueue")

  def test_coordinate_motion_tracks_pending_status_scan_by_scan(self):
    start_routine = self.parser.parse_routine_text(
      "main",
      "\n".join(
        [
          "XIC issue_a MCLM X_Y MoveA 0 CmdA_XY[0] CmdA_Speed \"Units per sec\" CmdA_Accel \"Units per sec2\" CmdA_Decel \"Units per sec2\" S-Curve CmdA_JerkAccel CmdA_JerkDecel \"Units per sec3\" CmdA_TermType Disabled Programmed CmdTolerance 0 None 0 0",
          "XIC issue_b MCLM X_Y MoveB 0 CmdB_XY[0] CmdB_Speed \"Units per sec\" CmdB_Accel \"Units per sec2\" CmdB_Decel \"Units per sec2\" S-Curve CmdB_JerkAccel CmdB_JerkDecel \"Units per sec3\" CmdB_TermType Disabled Programmed CmdTolerance 0 None 0 0",
        ]
      ),
      program="motionQueue",
    )

    self.ctx.set_value("CmdA_XY[0]", 100.0)
    self.ctx.set_value("CmdA_XY[1]", 50.0)
    self.ctx.set_value("CmdA_Speed", 500.0)
    self.ctx.set_value("CmdA_Accel", 1000.0)
    self.ctx.set_value("CmdA_Decel", 1000.0)
    self.ctx.set_value("CmdB_XY[0]", 200.0)
    self.ctx.set_value("CmdB_XY[1]", 75.0)
    self.ctx.set_value("CmdB_Speed", 500.0)
    self.ctx.set_value("CmdB_Accel", 1000.0)
    self.ctx.set_value("CmdB_Decel", 1000.0)
    self.ctx.set_value("issue_a", True)
    self.ctx.set_value("issue_b", True)

    self.executor.execute_routine(start_routine, self.ctx)

    self.assertTrue(self.ctx.get_value("MoveA.IP"))
    self.assertTrue(self.ctx.get_value("MoveB.IP"))
    self.assertTrue(self.ctx.get_value("X_Y.MovePendingStatus"))

    while self.ctx.get_value("X_Y.MovePendingStatus"):
      self.executor.advance_runtime(self.ctx)

    self.assertTrue(self.ctx.get_value("MoveA.PC"))
    self.assertTrue(self.ctx.get_value("MoveB.IP"))
    self.assertFalse(self.ctx.get_value("X_Y.MovePendingStatus"))

    while self.ctx.get_value("MoveB.IP"):
      self.executor.advance_runtime(self.ctx)

    self.assertAlmostEqual(self.ctx.get_value("X_axis.ActualPosition"), 200.0, places=6)
    self.assertAlmostEqual(self.ctx.get_value("Y_axis.ActualPosition"), 75.0, places=6)
    self.assertTrue(self.ctx.get_value("MoveB.PC"))

  def test_mccm_uses_arc_speed_and_accel_operands(self):
    routine = self.parser.parse_routine_text(
      "main",
      "\n".join(
        [
          "XIC issue MCCM X_Y MoveA 0 CmdA_XY[0] CmdA_CircleType CmdA_ViaCenter[0] CmdA_Direction CmdA_Speed \"Units per sec\" CmdA_Accel \"Units per sec2\" CmdA_Decel \"Units per sec2\" S-Curve CmdA_JerkAccel CmdA_JerkDecel \"Units per sec3\" CmdA_TermType Disabled Programmed CmdTolerance 0 None 0 0",
        ]
      ),
      program="motionQueue",
    )

    self.ctx.set_value("CmdA_XY[0]", 100.0)
    self.ctx.set_value("CmdA_XY[1]", 100.0)
    self.ctx.set_value("CmdA_CircleType", 1)
    self.ctx.set_value("CmdA_ViaCenter[0]", 0.0)
    self.ctx.set_value("CmdA_ViaCenter[1]", 100.0)
    self.ctx.set_value("CmdA_Direction", 1)
    self.ctx.set_value("CmdA_Speed", 321.0)
    self.ctx.set_value("CmdA_Accel", 654.0)
    self.ctx.set_value("CmdA_Decel", 654.0)
    self.ctx.set_value("CmdA_JerkAccel", 1000.0)
    self.ctx.set_value("CmdA_JerkDecel", 1000.0)
    self.ctx.set_value("CmdA_TermType", 3)
    self.ctx.set_value("issue", True)

    self.executor.execute_routine(routine, self.ctx)

    motion = self.ctx.runtime_state.coordinate_moves["X_Y"]
    self.assertEqual(motion.command_name, "MCCM")
    self.assertEqual(motion.direction, 1)
    self.assertAlmostEqual(motion.speed, 321.0, places=6)
    self.assertAlmostEqual(motion.acceleration, 654.0, places=6)
    self.assertTrue(self.ctx.get_value("MoveA.IP"))

  def test_generated_python_matches_ast_execution_for_movexy_main(self):
    path = Path("plc/MoveXY_State_2_3/main/pasteable.rll")
    routine = self.parser.parse_routine_path(
      path,
      routine_name="main",
      program="MoveXY_State_2_3",
    )
    def setup(ctx: ScanContext):
      ctx.set_value("STATE", 3)
      ctx.set_value("APA_IS_VERTICAL", True)
      ctx.set_value("Z_RETRACTED", True)
      ctx.set_value("X_axis.DriveEnableStatus", True)
      ctx.set_value("Y_axis.DriveEnableStatus", True)
      ctx.set_value("X_POSITION", 100.0)
      ctx.set_value("Y_POSITION", 50.0)
      ctx.set_value("XY_SPEED", 500.0)
      ctx.set_value("XY_ACCELERATION", 1000.0)
      ctx.set_value("XY_DECELERATION", 1000.0)
      ctx.set_value("v_x_max", 1000.0)
      ctx.set_value("v_y_max", 1000.0)
      ctx.set_value("speed_regulator_switch", False)
      ctx.set_value("TENSION_CONTROL_OK", False)

    self._assert_ast_and_generated_match(routine, setup=setup)

  def test_generated_python_matches_ast_execution_for_movez_main(self):
    path = Path("plc/MoveZ_State_4_5/main/pasteable.rll")
    routine = self.parser.parse_routine_path(
      path,
      routine_name="main",
      program="MoveZ_State_4_5",
    )

    def setup(ctx: ScanContext):
      ctx.set_value("STATE", 5)
      ctx.set_value("STATE5_IND", True)
      ctx.set_value("prepare_to_move", True)
      ctx.set_value("trigger_z_move", True)
      ctx.set_value("APA_IS_VERTICAL", True)
      ctx.set_value("Z_axis.DriveEnableStatus", True)
      ctx.set_value("Z_axis.PhysicalAxisFault", False)
      ctx.set_value("Z_FIXED_LATCHED", False)
      ctx.set_value("Z_POSITION", 12.5)
      ctx.set_value("Z_SPEED", 100.0)
      ctx.set_value("Z_ACCELERATION", 200.0)
      ctx.set_value("Z_DECELLERATION", 200.0)
      ctx.set_value("z_accel_jerk", 300.0)
      ctx.set_value("z_decel_jerk", 300.0)
      ctx.set_value("ALL_EOT_GOOD", True)

    self._assert_ast_and_generated_match(routine, setup=setup)

  def test_generated_python_matches_ast_for_coordinate_motion_scan_by_scan(self):
    routine = self.parser.parse_routine_text(
      "main",
      "\n".join(
        [
          "XIC issue_a MCLM X_Y MoveA 0 CmdA_XY[0] CmdA_Speed \"Units per sec\" CmdA_Accel \"Units per sec2\" CmdA_Decel \"Units per sec2\" S-Curve CmdA_JerkAccel CmdA_JerkDecel \"Units per sec3\" CmdA_TermType Disabled Programmed CmdTolerance 0 None 0 0",
          "XIC issue_b MCLM X_Y MoveB 0 CmdB_XY[0] CmdB_Speed \"Units per sec\" CmdB_Accel \"Units per sec2\" CmdB_Decel \"Units per sec2\" S-Curve CmdB_JerkAccel CmdB_JerkDecel \"Units per sec3\" CmdB_TermType Disabled Programmed CmdTolerance 0 None 0 0",
        ]
      ),
      program="motionQueue",
    )

    def setup(ctx: ScanContext):
      ctx.set_value("CmdA_XY[0]", 100.0)
      ctx.set_value("CmdA_XY[1]", 50.0)
      ctx.set_value("CmdA_Speed", 500.0)
      ctx.set_value("CmdA_Accel", 1000.0)
      ctx.set_value("CmdA_Decel", 1000.0)
      ctx.set_value("CmdA_TermType", 3)
      ctx.set_value("CmdB_XY[0]", 200.0)
      ctx.set_value("CmdB_XY[1]", 75.0)
      ctx.set_value("CmdB_Speed", 500.0)
      ctx.set_value("CmdB_Accel", 1000.0)
      ctx.set_value("CmdB_Decel", 1000.0)
      ctx.set_value("CmdB_TermType", 3)
      ctx.set_value("issue_a", True)
      ctx.set_value("issue_b", True)

    self._assert_ast_and_generated_match(routine, setup=setup, advance_runtime_scans=10)


class PlcPollHookTests(unittest.TestCase):
  def test_poll_all_wraps_reads_in_scan_cycle_hooks(self):
    class _PollingPLC:
      def __init__(self):
        self.events = []

      def begin_scan_cycle(self):
        self.events.append("begin")

      def end_scan_cycle(self):
        self.events.append("end")

      def isNotFunctional(self):
        return False

      def read(self, tags):
        self.events.append(tuple(tags))
        return [[name, 1] for name in tags]

    class _PolledTag(PLC.Tag):
      class Attributes(PLC.Tag.Attributes):
        isPolled = True

    try:
      PLC.Tag.instances = []
      PLC.Tag.tag_lookup_table = {}
      plc = _PollingPLC()
      _PolledTag(plc, "STATE", _PolledTag.Attributes())
      _PolledTag(plc, "ERROR_CODE", _PolledTag.Attributes())

      PLC.Tag.pollAll(plc)

      self.assertEqual(plc.events[0], "begin")
      self.assertEqual(plc.events[-1], "end")
      self.assertEqual(plc.events[1], ("STATE", "ERROR_CODE"))
    finally:
      PLC.Tag.instances = []
      PLC.Tag.tag_lookup_table = {}


if __name__ == "__main__":
  unittest.main()
