from __future__ import annotations

import unittest
from unittest.mock import patch

from dune_winder.gcode.handler import GCodeHandler
from dune_winder.geometry.primitives.location import Location
from dune_winder.io.controllers.head import Head
from dune_winder.machine.calibration.layer import LayerCalibration
from dune_winder.machine.calibration.machine import MachineCalibration
from dune_winder.machine.calibration.pin_resolution import wire_space_pin_location
from dune_winder.machine.geometry.uv_wrap_geometry import (
    Point2D,
    Point3D,
    RectBounds,
    alternating_side_hover_y_offset,
    plan_wrap_transition,
)
from dune_winder.machine.head_compensation import WirePathModel
from dune_winder.paths import REPO_ROOT


# Sentinel for _expected_explicit_wrap_plan: derive roller offsets from the
# loaded calibration unless the caller passes an explicit, test-controlled value.
_USE_CALIBRATION_ROLLER_OFFSETS = object()


class _Axis:
    def __init__(self, position):
        self._position = float(position)

    def getPosition(self):
        return float(self._position)

    def setPosition(self, position):
        self._position = float(position)


class _Input:
    def __init__(self, value=False):
        self._value = bool(value)

    def get(self):
        return self._value


class _PLCLogic:
    def __init__(self, x_axis, y_axis, z_axis):
        self._x_axis = x_axis
        self._y_axis = y_axis
        self._z_axis = z_axis
        self.xy_moves = []
        # Parallel to xy_moves: the per-move accel-jerk override, None when the
        # caller did not supply one.
        self.xy_jerks = []
        self.z_moves = []
        self.xz_moves = []
        self.latch_moves = 0

    def isReady(self):
        return True

    def setXY_Position(
        self,
        x,
        y,
        velocity=None,
        acceleration=None,
        deceleration=None,
        accelJerk=None,
    ):
        self.xy_moves.append((float(x), float(y), velocity, acceleration, deceleration))
        self.xy_jerks.append(accelJerk)
        self._x_axis.setPosition(x)
        self._y_axis.setPosition(y)

    def setZ_Position(self, z, velocity=None):
        self.z_moves.append((float(z), velocity))
        self._z_axis.setPosition(z)

    def setXZ_Position(self, x, z, velocity=None):
        self.xz_moves.append((float(x), float(z), velocity))
        self._x_axis.setPosition(x)
        self._z_axis.setPosition(z)

    def move_latch(self):
        self.latch_moves += 1


class _Head:
    def __init__(self):
        self.moves = []
        self.transfer_moves = []
        self.front_back = None
        self.position = 0
        # Mirrors the real Head: derived from `position` unless a test pins it.
        # Set to Head.TRANSFER_BLOCKED to exercise the latch-conflict preflight.
        self.availability = None
        self.transfer_state = {
            "stagePresent": False,
            "fixedPresent": True,
            "stageLatched": False,
            "fixedLatched": True,
            "zExtended": False,
            "enableActuator": False,
            "actuatorPos": 3,
            "zPosition": 0.0,
        }
        self.latch_conflict = (
            "fixed-latched, ACTUATOR_POS=3 (needs 2, mid_engagement, before the "
            "arm can extend)"
        )

    def getTransferAvailability(self):
        if self.availability is not None:
            return (self.availability, dict(self.transfer_state))
        if int(self.position) == Head.HEAD_ABSENT:
            return (Head.TRANSFER_ABSENT, dict(self.transfer_state))
        return (Head.TRANSFER_READY, dict(self.transfer_state))

    def describeLatchConflict(self, state):
        del state
        return self.latch_conflict

    def _formatTransferState(self, state):
        return "actuatorPos=" + str(int(state["actuatorPos"]))

    def isReady(self):
        return True

    def hasError(self):
        return False

    def getLastError(self):
        return ""

    def consumeLastError(self):
        return ""

    def readCurrentPosition(self):
        return int(self.position)

    def setHeadPosition(self, position, velocity=None):
        self.moves.append((int(position), velocity))
        self.position = int(position)
        return None

    def setTransferPosition(self, position, velocity=None):
        self.transfer_moves.append((int(position), velocity))
        self.position = int(position)
        return None

    def stop(self):
        return None

    def getTargetAxisPosition(self):
        return 0.0

    def setFrontAndBack(self, front, back):
        self.front_back = (float(front), float(back))

    def clearQueuedTransfer(self):
        return None


class _IO:
    def __init__(self, x, y, z=0.0):
        self.xAxis = _Axis(x)
        self.yAxis = _Axis(y)
        self.zAxis = _Axis(z)
        self.plcLogic = _PLCLogic(self.xAxis, self.yAxis, self.zAxis)
        self.head = _Head()
        self.Y_Transfer_OK = _Input(True)
        self.FrameLockHeadTop = _Input(False)
        self.FrameLockHeadMid = _Input(False)
        self.FrameLockHeadBtm = _Input(False)
        self.FrameLockFootTop = _Input(False)
        self.FrameLockFootMid = _Input(False)
        self.FrameLockFootBtm = _Input(False)


def _load_machine_calibration() -> MachineCalibration:
    calibration = MachineCalibration(
        str(REPO_ROOT / "config"), "machineCalibration.json"
    )
    calibration.load()
    return calibration


def _load_layer_calibration(layer: str) -> LayerCalibration:
    path = REPO_ROOT / "config" / "APA" / f"{str(layer).upper()}_Calibration.json"
    calibration = LayerCalibration(layer)
    calibration.load(str(path.parent), path.name, exceptionForMismatch=False)
    return calibration


class WrapRuntimeTests(unittest.TestCase):
    def _build_handler(self, start_x, start_y):
        machine_calibration = _load_machine_calibration()
        layer_calibration = _load_layer_calibration("U")
        io = _IO(start_x, start_y, z=0.0)
        handler = GCodeHandler(
            io, machine_calibration, WirePathModel(machine_calibration)
        )
        handler.useLayerCalibration(layer_calibration)
        handler._x = float(start_x)
        handler._y = float(start_y)
        handler._z = 0.0
        return handler, io, machine_calibration, layer_calibration

    def _seed_position(self, handler, io, x, y):
        """Place both the interpreter and the mock axes at (x, y)."""
        handler._x = float(x)
        handler._y = float(y)
        io.xAxis.setPosition(float(x))
        io.yAxis.setPosition(float(y))

    def _expected_explicit_wrap_plan(
        self,
        *,
        layer_calibration,
        machine_calibration,
        anchor_pin,
        target_pin,
        offset_x=0.0,
        offset_y=0.0,
        start_x=None,
        start_y=None,
        use_fitted_roller_offsets=True,
        roller_arm_y_offsets=_USE_CALIBRATION_ROLLER_OFFSETS,
    ):
        anchor_location = wire_space_pin_location(
            layer_calibration, machine_calibration, anchor_pin
        )
        target_location = wire_space_pin_location(
            layer_calibration, machine_calibration, target_pin
        )
        target_location = Location(
            float(target_location.x) + float(offset_x),
            float(target_location.y) + float(offset_y),
            float(target_location.z),
        )
        current_xy = None
        if start_x is not None and start_y is not None:
            current_xy = Point2D(float(start_x), float(start_y))
        if roller_arm_y_offsets is _USE_CALIBRATION_ROLLER_OFFSETS:
            roller_arm_y_offsets = (
                machine_calibration.rollerArmCalibration.fitted_y_cals
                if use_fitted_roller_offsets
                and machine_calibration.rollerArmCalibration is not None
                else None
            )
        return plan_wrap_transition(
            layer=layer_calibration.getLayerNames(),
            anchor_pin=anchor_pin,
            target_pin=target_pin,
            anchor_pin_point=Point3D(
                float(anchor_location.x),
                float(anchor_location.y),
                float(anchor_location.z),
            ),
            target_pin_point=Point3D(
                float(target_location.x),
                float(target_location.y),
                float(target_location.z),
            ),
            transfer_bounds=RectBounds(
                left=float(machine_calibration.transferLeft),
                top=float(machine_calibration.transferTop),
                right=float(machine_calibration.transferRight),
                bottom=float(machine_calibration.transferBottom),
            ),
            z_front=float(machine_calibration.zFront),
            z_back=float(machine_calibration.zBack),
            pin_radius=float(machine_calibration.pinDiameter) / 2.0,
            head_arm_length=float(machine_calibration.headArmLength),
            head_roller_radius=float(machine_calibration.headRollerRadius),
            head_roller_gap=float(machine_calibration.headRollerGap),
            roller_arm_y_offsets=roller_arm_y_offsets,
            current_xy=current_xy,
        )

    def _expected_explicit_wrap_final_xy(
        self,
        *,
        layer_calibration,
        machine_calibration,
        anchor_pin,
        target_pin,
        offset_x=0.0,
        offset_y=0.0,
        hover=False,
    ):
        plan = self._expected_explicit_wrap_plan(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin=anchor_pin,
            target_pin=target_pin,
            offset_x=offset_x,
            offset_y=offset_y,
        )
        final_xy = Point2D(float(plan.final_xy.x), float(plan.final_xy.y))
        if hover and not plan.same_side:
            self.assertIsNotNone(plan.face)
            final_xy = Point2D(
                float(final_xy.x),
                float(final_xy.y + alternating_side_hover_y_offset(plan.face)),
            )
        return final_xy, plan

    def test_tilde_goto_and_increment_move_xy_without_wrap_state(self):
        handler, io, _machine_calibration, _layer_calibration = self._build_handler(
            500.0, 500.0
        )

        error = handler.executeG_CodeLine("~goto(7174,0)")

        self.assertIsNone(error)
        self.assertEqual(
            io.plcLogic.xy_moves, [(7174.0, 0.0, float("inf"), None, None)]
        )

        error = handler.executeG_CodeLine("~increment(-200,0)")
        self.assertIsNone(error)
        self.assertEqual(io.plcLogic.xy_moves[-1][:2], (6974.0, 0.0))

    def test_tilde_increment_reads_live_xy_before_applying_offset(self):
        handler, io, _machine_calibration, _layer_calibration = self._build_handler(
            500.0, 500.0
        )

        error = handler.executeG_CodeLine("~goto(7174,0)")
        self.assertIsNone(error)
        io.xAxis.setPosition(7300.0)
        io.yAxis.setPosition(10.0)
        handler._x = 7174.0
        handler._y = 0.0

        error = handler.executeG_CodeLine("~increment(-200,0)")

        self.assertIsNone(error)
        self.assertEqual(io.plcLogic.xy_moves[-1][:2], (7100.0, 10.0))

    def test_anchor_to_target_applies_offset_keyword_to_target_pin(self):
        handler, io, machine_calibration, layer_calibration = self._build_handler(
            500.0, 500.0
        )
        anchor_pin = "B1201"
        target_pin = "B2001"

        plan = self._expected_explicit_wrap_plan(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin=anchor_pin,
            target_pin=target_pin,
            offset_x=12.5,
            offset_y=-3.0,
            start_x=500.0,
            start_y=500.0,
        )

        error = handler.executeG_CodeLine(
            "~anchorToTarget(B1201,B2001,offset=(12.5,-3.0))"
        )

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        self.assertGreaterEqual(len(io.plcLogic.xy_moves), 1)
        self.assertAlmostEqual(
            io.plcLogic.xy_moves[-1][0], float(plan.final_xy.x), places=3
        )
        self.assertAlmostEqual(
            io.plcLogic.xy_moves[-1][1], float(plan.final_xy.y), places=3
        )

    def test_plain_anchor_to_target_remains_unmodified_without_offset_macro(self):
        handler, io, machine_calibration, layer_calibration = self._build_handler(
            500.0, 500.0
        )
        anchor_pin = "B1201"
        target_pin = "B2001"

        plan = self._expected_explicit_wrap_plan(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin=anchor_pin,
            target_pin=target_pin,
            start_x=500.0,
            start_y=500.0,
        )

        error = handler.executeG_CodeLine("~anchorToTarget(B1201,B2001)")

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        self.assertGreaterEqual(len(io.plcLogic.xy_moves), 1)
        self.assertAlmostEqual(
            io.plcLogic.xy_moves[-1][0], float(plan.final_xy.x), places=3
        )
        self.assertAlmostEqual(
            io.plcLogic.xy_moves[-1][1], float(plan.final_xy.y), places=3
        )

    def test_anchor_to_target_hover_keyword_offsets_alternating_side_final_y(self):
        handler, io, machine_calibration, layer_calibration = self._build_handler(
            500.0, 500.0
        )
        anchor_pin = "B2001"
        target_pin = "A800"

        final_xy, plan = self._expected_explicit_wrap_final_xy(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin=anchor_pin,
            target_pin=target_pin,
            hover=True,
        )
        self.assertEqual(plan.face, "top")

        error = handler.executeG_CodeLine("~anchorToTarget(B2001,A800,hover=True)")

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        self.assertGreaterEqual(len(io.plcLogic.xy_moves), 1)
        self.assertAlmostEqual(io.plcLogic.xy_moves[-1][0], float(final_xy.x), places=3)
        self.assertAlmostEqual(io.plcLogic.xy_moves[-1][1], float(final_xy.y), places=3)

    def test_anchor_to_target_hover_keyword_offsets_bottom_alternating_side_final_y(
        self,
    ):
        handler, io, machine_calibration, layer_calibration = self._build_handler(
            500.0, 500.0
        )
        anchor_pin = "A2401"
        target_pin = "B401"

        final_xy, plan = self._expected_explicit_wrap_final_xy(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin=anchor_pin,
            target_pin=target_pin,
            hover=True,
        )
        self.assertEqual(plan.face, "bottom")

        error = handler.executeG_CodeLine("~anchorToTarget(A2401,B401,hover=True)")

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        self.assertGreaterEqual(len(io.plcLogic.xy_moves), 1)
        self.assertAlmostEqual(io.plcLogic.xy_moves[-1][0], float(final_xy.x), places=3)
        self.assertAlmostEqual(io.plcLogic.xy_moves[-1][1], float(final_xy.y), places=3)

    def test_anchor_to_target_hover_keyword_does_not_change_same_side_final_xy(self):
        handler, io, machine_calibration, layer_calibration = self._build_handler(
            500.0, 500.0
        )
        anchor_pin = "B1201"
        target_pin = "B2001"

        final_xy, plan = self._expected_explicit_wrap_final_xy(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin=anchor_pin,
            target_pin=target_pin,
            hover=True,
        )
        self.assertTrue(plan.same_side)

        error = handler.executeG_CodeLine("~anchorToTarget(B1201,B2001,hover=True)")

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        self.assertGreaterEqual(len(io.plcLogic.xy_moves), 1)
        self.assertAlmostEqual(io.plcLogic.xy_moves[-1][0], float(final_xy.x), places=3)
        self.assertAlmostEqual(io.plcLogic.xy_moves[-1][1], float(final_xy.y), places=3)

    def test_anchor_to_target_in_two_moves_splits_top_cross_side(self):
        start_y = 500.0
        handler, io, machine_calibration, layer_calibration = self._build_handler(
            500.0, start_y
        )
        anchor_pin = "B2001"
        target_pin = "A800"

        final_xy, plan = self._expected_explicit_wrap_final_xy(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin=anchor_pin,
            target_pin=target_pin,
        )
        self.assertFalse(plan.same_side)
        self.assertEqual(plan.face, "top")

        baseline_moves = len(io.plcLogic.xy_moves)
        error = handler.executeG_CodeLine("~anchorToTarget(B2001,A800,inTwoMoves=True)")

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        emitted = io.plcLogic.xy_moves[baseline_moves:]
        self.assertEqual(len(emitted), 2)
        self.assertAlmostEqual(emitted[0][0], float(final_xy.x), places=3)
        self.assertAlmostEqual(emitted[0][1], float(start_y), places=3)
        self.assertAlmostEqual(emitted[1][0], float(final_xy.x), places=3)
        self.assertAlmostEqual(emitted[1][1], float(final_xy.y), places=3)

    def test_anchor_to_target_in_two_moves_splits_bottom_cross_side(self):
        start_y = 500.0
        handler, io, machine_calibration, layer_calibration = self._build_handler(
            500.0, start_y
        )
        anchor_pin = "A2401"
        target_pin = "B401"

        final_xy, plan = self._expected_explicit_wrap_final_xy(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin=anchor_pin,
            target_pin=target_pin,
        )
        self.assertFalse(plan.same_side)
        self.assertEqual(plan.face, "bottom")

        baseline_moves = len(io.plcLogic.xy_moves)
        error = handler.executeG_CodeLine("~anchorToTarget(A2401,B401,inTwoMoves=True)")

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        emitted = io.plcLogic.xy_moves[baseline_moves:]
        self.assertEqual(len(emitted), 2)
        self.assertAlmostEqual(emitted[0][0], float(final_xy.x), places=3)
        self.assertAlmostEqual(emitted[0][1], float(start_y), places=3)
        self.assertAlmostEqual(emitted[1][0], float(final_xy.x), places=3)
        self.assertAlmostEqual(emitted[1][1], float(final_xy.y), places=3)

    def test_anchor_to_target_in_two_moves_no_op_on_same_side(self):
        handler, io, machine_calibration, layer_calibration = self._build_handler(
            500.0, 500.0
        )
        anchor_pin = "B1201"
        target_pin = "B2001"

        final_xy, plan = self._expected_explicit_wrap_final_xy(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin=anchor_pin,
            target_pin=target_pin,
        )
        self.assertTrue(plan.same_side)

        baseline_moves = len(io.plcLogic.xy_moves)
        error = handler.executeG_CodeLine(
            "~anchorToTarget(B1201,B2001,inTwoMoves=True)"
        )

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        emitted = io.plcLogic.xy_moves[baseline_moves:]
        self.assertEqual(len(emitted), 1)
        self.assertAlmostEqual(emitted[-1][0], float(final_xy.x), places=3)
        self.assertAlmostEqual(emitted[-1][1], float(final_xy.y), places=3)

    def test_anchor_to_target_in_two_moves_combines_with_hover(self):
        start_y = 500.0
        handler, io, machine_calibration, layer_calibration = self._build_handler(
            500.0, start_y
        )
        anchor_pin = "B2001"
        target_pin = "A800"

        final_xy, plan = self._expected_explicit_wrap_final_xy(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin=anchor_pin,
            target_pin=target_pin,
            hover=True,
        )
        self.assertFalse(plan.same_side)
        self.assertEqual(plan.face, "top")

        baseline_moves = len(io.plcLogic.xy_moves)
        error = handler.executeG_CodeLine(
            "~anchorToTarget(B2001,A800,hover=True,inTwoMoves=True)"
        )

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        emitted = io.plcLogic.xy_moves[baseline_moves:]
        self.assertEqual(len(emitted), 2)
        self.assertAlmostEqual(emitted[0][0], float(final_xy.x), places=3)
        self.assertAlmostEqual(emitted[0][1], float(start_y), places=3)
        self.assertAlmostEqual(emitted[1][0], float(final_xy.x), places=3)
        self.assertAlmostEqual(emitted[1][1], float(final_xy.y), places=3)

    def test_plan_wrap_transition_uses_fitted_roller_offsets_for_same_side_final_xy(
        self,
    ):
        _handler, _io, machine_calibration, layer_calibration = self._build_handler(
            500.0, 500.0
        )

        # Inject explicit, test-controlled roller offsets rather than reading
        # them from machineCalibration.json, so this test does not depend on the
        # calibration file's specific (and possibly uniform) fitted values.
        fitted_plan = self._expected_explicit_wrap_plan(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin="A388",
            target_pin="A413",
            offset_x=1.0,
            roller_arm_y_offsets=(0.0, 5.0, -5.0, 10.0),
        )
        nominal_plan = self._expected_explicit_wrap_plan(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin="A388",
            target_pin="A413",
            offset_x=1.0,
            roller_arm_y_offsets=None,
        )

        # Roller offsets must actually shift the same-side final X versus the
        # no-offset computation. Assert the relationship, not a calibration-
        # specific coordinate.
        self.assertGreater(
            abs(float(fitted_plan.final_xy.x) - float(nominal_plan.final_xy.x)), 1.0
        )
        # The same-side A-pin transition clamps the outbound intercept to the top
        # transfer edge; derive it from calibration rather than hard-coding it.
        self.assertAlmostEqual(
            float(fitted_plan.final_xy.y),
            float(machine_calibration.transferTop),
            places=3,
        )

    def test_anchor_to_target_uses_reverse_vector_roller_selection_for_same_side_runtime(
        self,
    ):
        handler, io, machine_calibration, layer_calibration = self._build_handler(
            500.0, 500.0
        )

        plan = self._expected_explicit_wrap_plan(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin="B2391",
            target_pin="B812",
            start_x=500.0,
            start_y=500.0,
        )

        error = handler.executeG_CodeLine("~anchorToTarget(B2391,B812)")

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        self.assertGreaterEqual(len(io.plcLogic.xy_moves), 1)
        # The same-side B-pin transition clamps the outbound intercept to the
        # bottom transfer edge; derive it from calibration rather than a literal.
        self.assertAlmostEqual(
            float(plan.final_xy.y),
            float(machine_calibration.transferBottom),
            places=3,
        )
        # The runtime dispatch must reproduce the planner's final XY exactly.
        self.assertAlmostEqual(
            io.plcLogic.xy_moves[-1][0], float(plan.final_xy.x), places=3
        )
        self.assertAlmostEqual(
            io.plcLogic.xy_moves[-1][1], float(plan.final_xy.y), places=3
        )

    def test_plan_wrap_transition_uses_transfer_line_intercept_for_alternating_final_xy(
        self,
    ):
        _handler, _io, machine_calibration, layer_calibration = self._build_handler(
            500.0, 500.0
        )

        plan = self._expected_explicit_wrap_plan(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin="B1201",
            target_pin="A1201",
        )

        self.assertFalse(plan.same_side)
        self.assertEqual(plan.plane, "yz")
        self.assertEqual(plan.face, "foot")
        # The alternating final XY is the transfer-line intercept projected past
        # the transfer zone, beyond the tangent contact. Assert the geometric
        # relationships rather than calibration-specific coordinates.
        self.assertGreater(
            float(plan.final_xy.y), float(machine_calibration.transferTop)
        )
        self.assertLess(float(plan.target_tangent_point.y), float(plan.final_xy.y))

    def test_anchor_to_target_rejects_mixed_face_alternating_pair(self):
        handler, _io, _machine_calibration, _layer_calibration = self._build_handler(
            500.0, 500.0
        )

        error = handler.executeG_CodeLine("~anchorToTarget(B1201,A2001)")

        self.assertIsNotNone(error)
        self.assertIn(
            "same face after converting the A pin to the B side", error["message"]
        )

    def test_anchor_to_target_runtime_does_not_use_legacy_uv_head_target_probe(self):
        handler, io, machine_calibration, layer_calibration = self._build_handler(
            500.0, 500.0
        )

        plan = self._expected_explicit_wrap_plan(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin="B1201",
            target_pin="B2001",
            start_x=500.0,
            start_y=500.0,
        )

        with patch(
            "dune_winder.uv_head_target._execute_line",
            side_effect=AssertionError("legacy comparison path invoked"),
        ):
            error = handler.executeG_CodeLine("~anchorToTarget(B1201,B2001)")

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        self.assertGreaterEqual(len(io.plcLogic.xy_moves), 1)
        self.assertAlmostEqual(
            io.plcLogic.xy_moves[-1][0], float(plan.final_xy.x), places=3
        )
        self.assertAlmostEqual(
            io.plcLogic.xy_moves[-1][1], float(plan.final_xy.y), places=3
        )

    def test_anchor_to_target_skips_head_motion_when_head_absent_same_side(self):
        handler, io, machine_calibration, layer_calibration = self._build_handler(
            500.0, 500.0
        )
        io.head.position = -1

        plan = self._expected_explicit_wrap_plan(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin="B1201",
            target_pin="B2001",
            start_x=500.0,
            start_y=500.0,
        )
        self.assertTrue(plan.same_side)
        initial_z = handler._z
        initial_head_position = handler._headPosition

        error = handler.executeG_CodeLine("~anchorToTarget(B1201,B2001)")

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        self.assertEqual(io.head.transfer_moves, [])
        self.assertEqual(io.head.moves, [])
        self.assertGreaterEqual(len(io.plcLogic.xy_moves), 1)
        self.assertAlmostEqual(
            io.plcLogic.xy_moves[-1][0], float(plan.final_xy.x), places=3
        )
        self.assertAlmostEqual(
            io.plcLogic.xy_moves[-1][1], float(plan.final_xy.y), places=3
        )
        self.assertEqual(handler._z, initial_z)
        self.assertEqual(handler._headPosition, initial_head_position)

    def test_anchor_to_target_skips_head_motion_when_head_absent_alternating(self):
        handler, io, machine_calibration, layer_calibration = self._build_handler(
            500.0, 500.0
        )
        io.head.position = -1

        final_xy, plan = self._expected_explicit_wrap_final_xy(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin="B2001",
            target_pin="A800",
            hover=True,
        )
        self.assertFalse(plan.same_side)

        error = handler.executeG_CodeLine("~anchorToTarget(B2001,A800,hover=True)")

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        self.assertEqual(io.head.transfer_moves, [])
        self.assertEqual(io.head.moves, [])
        self.assertGreaterEqual(len(io.plcLogic.xy_moves), 1)
        self.assertAlmostEqual(io.plcLogic.xy_moves[-1][0], float(final_xy.x), places=3)
        self.assertAlmostEqual(io.plcLogic.xy_moves[-1][1], float(final_xy.y), places=3)

    def test_same_side_prep_transfer_fires_for_b_in_zone_near_target(self):
        handler, io, machine_calibration, layer_calibration = self._build_handler(
            0.0, 0.0
        )
        plan = self._expected_explicit_wrap_plan(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin="B2391",
            target_pin="B812",
        )
        self.assertTrue(plan.same_side)
        # Start exactly at the planned target: inside the transfer zone and within
        # tolerance, regardless of the calibration's specific coordinates.
        self._seed_position(handler, io, plan.final_xy.x, plan.final_xy.y)

        error = handler.executeG_CodeLine("~anchorToTarget(B2391,B812)")

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        transfer_positions = [move[0] for move in io.head.transfer_moves]
        # Fixed-side clearance (3) prep transfer, then the working extend (2).
        self.assertEqual(transfer_positions, [3, 2])

    def test_same_side_prep_transfer_fires_for_a_in_zone_near_target(self):
        handler, io, machine_calibration, layer_calibration = self._build_handler(
            0.0, 0.0
        )
        plan = self._expected_explicit_wrap_plan(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin="A388",
            target_pin="A413",
        )
        self.assertTrue(plan.same_side)
        self._seed_position(handler, io, plan.final_xy.x, plan.final_xy.y)

        error = handler.executeG_CodeLine("~anchorToTarget(A388,A413)")

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        transfer_positions = [move[0] for move in io.head.transfer_moves]
        # Stage-side clearance (0) prep transfer, then the working extend (1).
        self.assertEqual(transfer_positions, [0, 1])

    def test_same_side_prep_transfer_skipped_when_far_from_target(self):
        handler, io, machine_calibration, layer_calibration = self._build_handler(
            0.0, 0.0
        )
        plan = self._expected_explicit_wrap_plan(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin="B2391",
            target_pin="B812",
        )
        # In the transfer zone, but more than the per-axis tolerance away in Y.
        far_y = float(plan.final_xy.y) + 30.0
        if far_y > float(machine_calibration.transferTop):
            far_y = float(plan.final_xy.y) - 30.0
        self.assertGreaterEqual(far_y, float(machine_calibration.transferBottom))
        self._seed_position(handler, io, plan.final_xy.x, far_y)

        error = handler.executeG_CodeLine("~anchorToTarget(B2391,B812)")

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        transfer_positions = [move[0] for move in io.head.transfer_moves]
        self.assertEqual(transfer_positions, [2])

    def test_same_side_prep_transfer_skipped_when_outside_transfer_zone(self):
        handler, io, machine_calibration, layer_calibration = self._build_handler(
            0.0, 0.0
        )
        plan = self._expected_explicit_wrap_plan(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin="B2391",
            target_pin="B812",
        )
        # Near the target in XY but just below the bottom transfer edge, i.e.
        # outside the transfer zone. This isolates the in-transfer-zone gate.
        outside_y = float(machine_calibration.transferBottom) - 10.0
        self.assertLessEqual(abs(outside_y - float(plan.final_xy.y)), 25.0)
        self._seed_position(handler, io, plan.final_xy.x, outside_y)

        error = handler.executeG_CodeLine("~anchorToTarget(B2391,B812)")

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        transfer_positions = [move[0] for move in io.head.transfer_moves]
        self.assertEqual(transfer_positions, [2])

    def test_alternating_move_does_not_get_prep_transfer_near_target(self):
        handler, io, machine_calibration, layer_calibration = self._build_handler(
            500.0, 500.0
        )

        final_xy, plan = self._expected_explicit_wrap_final_xy(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin="B2001",
            target_pin="A800",
        )
        self.assertFalse(plan.same_side)

        # Seed the interpreter at the final XY target so the same-side trigger
        # condition would be met if it (incorrectly) applied to alternating moves.
        handler._x = float(final_xy.x)
        handler._y = float(final_xy.y)
        io.xAxis.setPosition(float(final_xy.x))
        io.yAxis.setPosition(float(final_xy.y))

        error = handler.executeG_CodeLine("~anchorToTarget(B2001,A800)")

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        transfer_positions = [move[0] for move in io.head.transfer_moves]
        # Alternating same-as-before: a single clearance transfer (position 0 for
        # an A target), no extra preparatory transfer.
        self.assertEqual(transfer_positions, [0])

    def test_anchor_to_target_jerk_keyword_overrides_the_xy_move_jerk(self):
        handler, io, _machine_calibration, _layer_calibration = self._build_handler(
            500.0, 500.0
        )

        baseline_moves = len(io.plcLogic.xy_moves)
        error = handler.executeG_CodeLine("~anchorToTarget(B1201,B2001,jerk=gentle)")

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        emitted = io.plcLogic.xy_jerks[baseline_moves:]
        self.assertTrue(emitted)
        self.assertTrue(all(jerk == 1000.0 for jerk in emitted))

    def test_anchor_to_target_jerky_keyword_selects_the_jerky_profile(self):
        handler, io, _machine_calibration, _layer_calibration = self._build_handler(
            500.0, 500.0
        )

        baseline_moves = len(io.plcLogic.xy_moves)
        error = handler.executeG_CodeLine("~anchorToTarget(B1201,B2001,jerk=jerky)")

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        emitted = io.plcLogic.xy_jerks[baseline_moves:]
        self.assertTrue(emitted)
        self.assertTrue(all(jerk == 2000.0 for jerk in emitted))

    def test_anchor_to_target_without_jerk_keyword_leaves_the_override_unset(self):
        handler, io, _machine_calibration, _layer_calibration = self._build_handler(
            500.0, 500.0
        )

        baseline_moves = len(io.plcLogic.xy_moves)
        error = handler.executeG_CodeLine("~anchorToTarget(B1201,B2001)")

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        emitted = io.plcLogic.xy_jerks[baseline_moves:]
        self.assertTrue(emitted)
        # None leaves the PLC facade free to apply its configured default.
        self.assertTrue(all(jerk is None for jerk in emitted))

    def test_anchor_to_target_jerk_reads_live_configuration(self):
        handler, io, _machine_calibration, _layer_calibration = self._build_handler(
            500.0, 500.0
        )

        class _Configuration:
            xyRegulatedAccelJerkDefault = 1500.0
            xyRegulatedAccelJerkGentle = 750.0
            xyRegulatedAccelJerkJerky = 2000.0

        handler._configuration = _Configuration()

        baseline_moves = len(io.plcLogic.xy_moves)
        error = handler.executeG_CodeLine("~anchorToTarget(B1201,B2001,jerk=gentle)")

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        emitted = io.plcLogic.xy_jerks[baseline_moves:]
        self.assertTrue(emitted)
        self.assertTrue(all(jerk == 750.0 for jerk in emitted))

    def test_anchor_to_target_jerk_applies_to_both_halves_of_a_split_move(self):
        handler, io, machine_calibration, layer_calibration = self._build_handler(
            500.0, 500.0
        )

        _final_xy, plan = self._expected_explicit_wrap_final_xy(
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            anchor_pin="B2001",
            target_pin="A800",
        )
        self.assertFalse(plan.same_side)
        self.assertEqual(plan.face, "top")

        baseline_moves = len(io.plcLogic.xy_moves)
        error = handler.executeG_CodeLine(
            "~anchorToTarget(B2001,A800,inTwoMoves=True,jerk=gentle)"
        )

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        self.assertEqual(len(io.plcLogic.xy_moves[baseline_moves:]), 2)
        self.assertEqual(io.plcLogic.xy_jerks[baseline_moves:], [1000.0, 1000.0])

    def test_anchor_to_target_rejects_an_unknown_jerk_keyword(self):
        handler, io, _machine_calibration, _layer_calibration = self._build_handler(
            500.0, 500.0
        )

        error = handler.executeG_CodeLine("~anchorToTarget(B1201,B2001,jerk=snappy)")

        self.assertIsNotNone(error)
        self.assertIn("jerk must be one of", error["message"])
        self.assertEqual(io.plcLogic.xy_moves, [])

    def test_g206_silently_skips_head_transfer_when_head_absent(self):
        handler, io, _machine_calibration, _layer_calibration = self._build_handler(
            500.0, 500.0
        )
        io.head.position = -1
        initial_head_position = handler._headPosition

        error = handler.executeG_CodeLine("G206 P3")

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        self.assertEqual(io.head.transfer_moves, [])
        self.assertEqual(io.head.moves, [])
        self.assertEqual(handler._headPosition, initial_head_position)
        self.assertFalse(handler.isG_CodeError())


class HeadTransferBlockedTests(unittest.TestCase):
    """
    A head that is mounted but sits in a conflicting latch position must fault
    loudly rather than degrade to a bare XY move.  This is the case the PLC
    would refuse with MASTER_Z_GO / ERROR_CODE 5001.
    """

    def _build_handler(self, start_x, start_y):
        machine_calibration = _load_machine_calibration()
        layer_calibration = _load_layer_calibration("U")
        io = _IO(start_x, start_y, z=0.0)
        handler = GCodeHandler(
            io, machine_calibration, WirePathModel(machine_calibration)
        )
        handler.useLayerCalibration(layer_calibration)
        handler._x = float(start_x)
        handler._y = float(start_y)
        handler._z = 0.0
        return handler, io, machine_calibration, layer_calibration

    def _blocked_handler(self, start_x=500.0, start_y=500.0):
        handler, io, machine_calibration, layer_calibration = self._build_handler(
            start_x, start_y
        )
        io.head.availability = Head.TRANSFER_BLOCKED
        return handler, io, machine_calibration, layer_calibration

    def _assert_lockout_error(self, error):
        self.assertIsNotNone(error)
        message = error["message"]
        self.assertIn("MASTER_Z_GO", message)
        self.assertIn("no_latch_collision", message)
        self.assertIn("ACTUATOR_POS=3", message)
        self.assertIn("ERROR_CODE 5001", message)

    def test_anchor_to_target_errors_when_head_blocked_same_side(self):
        handler, io, _machine_calibration, _layer_calibration = self._blocked_handler()

        error = handler.executeG_CodeLine("~anchorToTarget(B1201,B2001)")

        self._assert_lockout_error(error)
        # Nothing may move: not the head, and not a consolation XY move.
        self.assertEqual(io.head.transfer_moves, [])
        self.assertEqual(io.head.moves, [])
        self.assertEqual(io.plcLogic.xy_moves, [])

    def test_anchor_to_target_errors_when_head_blocked_alternating(self):
        handler, io, _machine_calibration, _layer_calibration = self._blocked_handler()

        error = handler.executeG_CodeLine("~anchorToTarget(B2001,A800,hover=True)")

        self._assert_lockout_error(error)
        self.assertEqual(io.head.transfer_moves, [])
        self.assertEqual(io.plcLogic.xy_moves, [])

    def test_g206_errors_when_head_blocked(self):
        handler, io, _machine_calibration, _layer_calibration = self._blocked_handler()
        initial_head_position = handler._headPosition

        error = handler.executeG_CodeLine("G206 P3")

        self._assert_lockout_error(error)
        self.assertEqual(io.head.transfer_moves, [])
        self.assertEqual(handler._headPosition, initial_head_position)

    def test_message_reports_every_blocking_term(self):
        handler, io, _machine_calibration, _layer_calibration = self._blocked_handler()
        # Drop both transfer windows so no_apa_collision fails as well.
        io.Y_Transfer_OK = _Input(False)

        error = handler.executeG_CodeLine("G206 P3")

        self.assertIsNotNone(error)
        message = error["message"]
        self.assertIn("no_latch_collision", message)
        self.assertIn("no_apa_collision", message)
        self.assertIn("X_XFER_OK=0", message)
        self.assertIn("no_supports_collision", message)

    def test_head_state_summary_is_appended(self):
        handler, _io, _machine_calibration, _layer_calibration = self._blocked_handler()

        error = handler.executeG_CodeLine("G206 P3")

        self.assertIsNotNone(error)
        self.assertIn("actuatorPos=3", error["message"])

    def test_error_data_carries_the_pins(self):
        handler, _io, _machine_calibration, _layer_calibration = self._blocked_handler()

        error = handler.executeG_CodeLine("~anchorToTarget(B1201,B2001)")

        self.assertIsNotNone(error)
        self.assertIn("B1201", error["data"])
        self.assertIn("B2001", error["data"])

    def test_latch_conflict_that_does_not_trip_master_z_go(self):
        # Stage-latched at the wrong ACTUATOR_POS leaves the head on no known
        # side, but every MASTER_Z_GO conjunct still holds (no_latch_collision
        # only constrains the *fixed* latch).  Naming MASTER_Z_GO would be
        # misleading, so the message reports the latch conflict alone.
        handler, io, _machine_calibration, _layer_calibration = self._blocked_handler()
        io.head.transfer_state = {
            "stagePresent": True,
            "fixedPresent": False,
            "stageLatched": True,
            "fixedLatched": False,
            "zExtended": False,
            "enableActuator": False,
            "actuatorPos": 3,
            "zPosition": 0.0,
        }
        io.head.latch_conflict = "stage-latched, ACTUATOR_POS=3 (needs 1)"

        error = handler.executeG_CodeLine("G206 P3")

        self.assertIsNotNone(error)
        message = error["message"]
        self.assertIn("not resting on a known transfer side", message)
        self.assertIn("stage-latched, ACTUATOR_POS=3", message)
        self.assertNotIn("MASTER_Z_GO", message)
        self.assertEqual(io.head.transfer_moves, [])

    def test_absent_head_still_skips_silently(self):
        # Regression guard for the behaviour we deliberately kept: with neither
        # presence sensor asserted there is no head to transfer, so the XY move
        # proceeds without an error.
        handler, io, _machine_calibration, _layer_calibration = self._build_handler(
            500.0, 500.0
        )
        io.head.position = -1
        io.head.availability = Head.TRANSFER_ABSENT

        error = handler.executeG_CodeLine("~anchorToTarget(B1201,B2001)")

        self.assertIsNone(error)
        while handler._dispatch_pending_actions(safety_label="manual"):
            pass
        self.assertEqual(io.head.transfer_moves, [])
        self.assertGreaterEqual(len(io.plcLogic.xy_moves), 1)


if __name__ == "__main__":
    unittest.main()
