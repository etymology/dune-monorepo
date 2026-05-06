"""PyO3 surface tests for the Phase D wire/anchor-to-target types in
dune_geometry.

Covers AnchorToTargetRequest, AnchorToTargetSolution, and the
`solve_anchor_to_target` function. The function currently performs steps
1-3 of the spec obligation (raw-coordinate lookup + per-pose
camera-wire-offset + arm correction); the wire-tangent refinement step
is still owned by the legacy Python solver and lands here in a follow-up
commit.
"""

from __future__ import annotations

import pytest

dune_geometry = pytest.importorskip("dune_geometry")


def _ua(n: int) -> "dune_geometry.Pin":
    return dune_geometry.Pin("U", "A", n)


def _ub(n: int) -> "dune_geometry.Pin":
    return dune_geometry.Pin("U", "B", n)


def _vb(n: int) -> "dune_geometry.Pin":
    return dune_geometry.Pin("V", "B", n)


def _model_with(
    *,
    base_stage=(0.0, 0.0, 0.0),
    base_fixed=(0.0, 0.0, 0.0),
    arm=(0.0, 0.0, 0.0),
    per_pin=(),
):
    return dune_geometry.MachineCalibrationModel(
        base_camera_wire_offset_stage=dune_geometry.Vec3(*base_stage),
        base_camera_wire_offset_fixed=dune_geometry.Vec3(*base_fixed),
        per_pin_camera_wire_offset=[
            dune_geometry.PerPinOffset(p, dune_geometry.Vec3(*v)) for p, v in per_pin
        ],
        arm_correction=dune_geometry.Vec3(*arm),
    )


def test_request_surface_round_trip() -> None:
    req = dune_geometry.AnchorToTargetRequest(
        anchor_pin=_ua(1),
        anchor_xyz=dune_geometry.Vec3(1.0, 2.0, 3.0),
        target_pin=_ub(2),
        target_xyz=dune_geometry.Vec3(10.0, 20.0, 30.0),
        head_side="stage",
        target_offset=(0.5, -0.5),
        hover=True,
    )
    assert req.anchor_pin == _ua(1)
    assert req.target_pin == _ub(2)
    assert req.head_side == "stage"
    assert req.target_offset == (0.5, -0.5)
    assert req.hover is True
    assert req.target_xyz.as_tuple() == (10.0, 20.0, 30.0)


def test_solve_applies_offset_and_arm_correction() -> None:
    model = _model_with(
        base_stage=(1.0, 2.0, 0.0),
        base_fixed=(0.0, 0.0, 0.0),
        arm=(0.5, 0.0, -0.25),
    )
    req = dune_geometry.AnchorToTargetRequest(
        anchor_pin=_ua(1),
        anchor_xyz=dune_geometry.Vec3(100.0, 100.0, 50.0),
        target_pin=_ub(2),
        target_xyz=dune_geometry.Vec3(200.0, 200.0, 60.0),
        head_side="stage",
    )
    sol = dune_geometry.solve_anchor_to_target(req, model)
    assert sol.effective_camera_wire_offset.as_tuple() == (1.0, 2.0, 0.0)
    assert sol.effective_arm_correction.as_tuple() == (0.5, 0.0, -0.25)
    assert sol.commanded_head_xyz.as_tuple() == (201.5, 202.0, 59.75)


def test_solve_per_pin_override_wins() -> None:
    model = _model_with(
        base_stage=(1.0, 1.0, 1.0),
        base_fixed=(2.0, 2.0, 2.0),
        per_pin=[(_ub(2), (7.0, 8.0, 9.0))],
    )
    req = dune_geometry.AnchorToTargetRequest(
        anchor_pin=_ua(1),
        anchor_xyz=dune_geometry.Vec3(0.0, 0.0, 0.0),
        target_pin=_ub(2),
        target_xyz=dune_geometry.Vec3(0.0, 0.0, 0.0),
        head_side="stage",
    )
    sol = dune_geometry.solve_anchor_to_target(req, model)
    assert sol.commanded_head_xyz.as_tuple() == (7.0, 8.0, 9.0)


def test_solve_target_offset_applied_in_xy_only() -> None:
    model = _model_with(base_fixed=(10.0, 20.0, 0.0), arm=(0.0, 0.0, 5.0))
    req = dune_geometry.AnchorToTargetRequest(
        anchor_pin=_ua(1),
        anchor_xyz=dune_geometry.Vec3(0.0, 0.0, 0.0),
        target_pin=_ub(2),
        target_xyz=dune_geometry.Vec3(100.0, 100.0, 100.0),
        head_side="fixed",
        target_offset=(1.0, 2.0),
    )
    sol = dune_geometry.solve_anchor_to_target(req, model)
    # Z is untouched by the (dx, dy) target_offset; effective offset and arm
    # correction stack on top.
    assert sol.commanded_head_xyz.as_tuple() == (111.0, 122.0, 105.0)


def test_solve_rejects_layer_mismatch() -> None:
    model = _model_with()
    req = dune_geometry.AnchorToTargetRequest(
        anchor_pin=_ua(1),
        anchor_xyz=dune_geometry.Vec3(0.0, 0.0, 0.0),
        target_pin=_vb(2),
        target_xyz=dune_geometry.Vec3(0.0, 0.0, 0.0),
        head_side="stage",
    )
    with pytest.raises(ValueError, match="layer"):
        dune_geometry.solve_anchor_to_target(req, model)


def test_solve_rejects_unknown_head_side() -> None:
    with pytest.raises(ValueError):
        dune_geometry.AnchorToTargetRequest(
            anchor_pin=_ua(1),
            anchor_xyz=dune_geometry.Vec3(0.0, 0.0, 0.0),
            target_pin=_ub(2),
            target_xyz=dune_geometry.Vec3(0.0, 0.0, 0.0),
            head_side="left",
        )


def test_solve_consumes_pin_calibration_file_effective_coords() -> None:
    """End-to-end: build a PinCalibrationFile, read off effective coords,
    feed into solve_anchor_to_target."""
    file = dune_geometry.PinCalibrationFile("apa-stand-01")
    file.append_snapshot(
        dune_geometry.PinCalibrationSnapshot(
            taken_at="2026-05-01T00:00:00Z",
            calibration_camera_id="cam",
            pins=[
                dune_geometry.PinCoordinate(_ua(1), dune_geometry.Vec3(1.0, 2.0, 3.0)),
                dune_geometry.PinCoordinate(
                    _ub(2), dune_geometry.Vec3(50.0, 60.0, 70.0)
                ),
            ],
        )
    )
    eff = dict(file.effective_pin_coords())
    model = _model_with(base_stage=(0.1, 0.2, 0.3), arm=(0.01, 0.02, 0.03))
    req = dune_geometry.AnchorToTargetRequest(
        anchor_pin=_ua(1),
        anchor_xyz=eff[_ua(1)],
        target_pin=_ub(2),
        target_xyz=eff[_ub(2)],
        head_side="stage",
    )
    sol = dune_geometry.solve_anchor_to_target(req, model)
    # 50 + 0.1 + 0.01, 60 + 0.2 + 0.02, 70 + 0.3 + 0.03
    cx, cy, cz = sol.commanded_head_xyz.as_tuple()
    assert cx == pytest.approx(50.11)
    assert cy == pytest.approx(60.22)
    assert cz == pytest.approx(70.33)
