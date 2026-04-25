from __future__ import annotations

import math
import shutil
from types import SimpleNamespace

import pytest

from _command_api_test_support import (
    DummyConfiguration,
    DummyIO,
    DummyLog,
    DummyLowLevelIO,
    DummyProcess,
)
from dune_winder.api.commands import build_command_registry
from dune_winder.machine.calibration.layer import LayerCalibration
from dune_winder.machine.calibration.machine import MachineCalibration
from dune_winder.machine.calibration.z_plane import (
    LayerZPlaneMeasurement,
    LayerZPlaneObservation,
)
import dune_winder.machine.calibration.z_plane_solver as z_plane_solver_module
from dune_winder.machine.calibration.z_plane_solver import (
    BOARD_WIDTH_MM,
    apply_layer_z_plane_calibration,
    build_layer_z_plane_observation,
    evaluate_plane_z,
    fit_layer_z_plane,
    fit_layer_z_plane_from_observations,
)
from dune_winder.paths import REPO_ROOT


_U_SAMPLE_MEASUREMENTS = [
    LayerZPlaneMeasurement(
        gcode_line="~anchorToTarget(A1010,A2192)",
        layer="U",
        actual_x=0.0,
        actual_y=0.0,
        actual_z=143.0,
    ),
    LayerZPlaneMeasurement(
        gcode_line="~anchorToTarget(B610,B191,offset=(0,1))",
        layer="U",
        actual_x=0.0,
        actual_y=0.0,
        actual_z=276.0,
    ),
    LayerZPlaneMeasurement(
        gcode_line="~anchorToTarget(A210,A591)",
        layer="U",
        actual_x=0.0,
        actual_y=0.0,
        actual_z=149.0,
    ),
    LayerZPlaneMeasurement(
        gcode_line="~anchorToTarget(B2212,B991)",
        layer="U",
        actual_x=0.0,
        actual_y=0.0,
        actual_z=270.0,
    ),
    LayerZPlaneMeasurement(
        gcode_line="~anchorToTarget(B1411,B1791)",
        layer="U",
        actual_x=0.0,
        actual_y=0.0,
        actual_z=280.0,
    ),
]


def _load_machine_calibration() -> MachineCalibration:
    calibration = MachineCalibration(
        str(REPO_ROOT / "dune_winder" / "config"),
        "machineCalibration.json",
    )
    calibration.load()
    return calibration


def _copied_layer_calibration(tmp_path, layer: str = "U") -> LayerCalibration:
    source = (
        REPO_ROOT
        / "dune_winder"
        / "config"
        / "APA"
        / f"{layer.upper()}_Calibration.json"
    )
    target = tmp_path / source.name
    shutil.copy2(source, target)
    calibration = LayerCalibration(layer.upper())
    calibration.load(str(tmp_path), target.name, exceptionForMismatch=False)
    return calibration


class _CalibrationHandler:
    def __init__(self, calibration: LayerCalibration):
        self._calibration = calibration
        self.sync_calls = []

    def getLayerCalibration(self):
        return self._calibration

    def useLayerCalibration(self, calibration):
        self._calibration = calibration
        self.sync_calls.append((float(calibration.zFront), float(calibration.zBack)))


class _CalibrationProcess(DummyProcess):
    def __init__(self, calibration: LayerCalibration):
        super().__init__()
        self._active_calibration = calibration
        self.gCodeHandler = _CalibrationHandler(calibration)

    def _getActiveLayerCalibration(self, layer):
        normalized = str(layer).strip().upper()
        if normalized != str(self._active_calibration.getLayerNames()).strip().upper():
            raise ValueError(
                "No layer calibration is loaded for active layer " + normalized + "."
            )
        return self._active_calibration

    def getRecipeLayer(self):
        return self._active_calibration.getLayerNames()


def test_solver_ignores_existing_pin_z_values(tmp_path):
    calibration = _copied_layer_calibration(tmp_path, "U")
    baseline = fit_layer_z_plane(
        _U_SAMPLE_MEASUREMENTS,
        layer_calibration_path=calibration.getFullFileName(),
    )

    for pin_name in calibration.getPinNames():
        location = calibration.getPinLocation(pin_name)
        offset = 500.0 if pin_name.startswith("A") else -500.0
        calibration.setPinLocation(
            pin_name,
            location.copy(z=float(location.z) + offset),
        )
    calibration.save()

    perturbed = fit_layer_z_plane(
        _U_SAMPLE_MEASUREMENTS,
        layer_calibration_path=calibration.getFullFileName(),
    )

    assert baseline.coefficients is not None
    assert perturbed.coefficients is not None
    assert baseline.coefficients == pytest.approx(perturbed.coefficients, abs=1e-9)
    assert [
        (observation.effective_x, observation.effective_y)
        for observation in baseline.observations
    ] == pytest.approx(
        [
            (observation.effective_x, observation.effective_y)
            for observation in perturbed.observations
        ],
        abs=1e-9,
    )


def test_observation_uses_roller_tangent_xy_not_pin_centers(monkeypatch):
    measurement = LayerZPlaneMeasurement(
        gcode_line="~anchorToTarget(A10,A20)",
        layer="U",
        actual_x=0.0,
        actual_y=0.0,
        actual_z=145.0,
    )

    def _view(pin_a_x, pin_a_y, pin_b_x, pin_b_y):
        return SimpleNamespace(
            command=SimpleNamespace(anchor_pin="A10", target_pin="A20"),
            raw_result=SimpleNamespace(
                tangent_point_a=SimpleNamespace(x=10.0, y=0.0),
                tangent_point_b=SimpleNamespace(x=20.0, y=0.0),
                outbound_intercept=SimpleNamespace(x=30.0, y=0.0),
                pin_a_point=SimpleNamespace(x=pin_a_x, y=pin_a_y, z=145.0),
                pin_b_point=SimpleNamespace(x=pin_b_x, y=pin_b_y, z=145.0),
                arm_corrected_outbound_point=SimpleNamespace(x=1234.5, y=678.9),
            ),
        )

    monkeypatch.setattr(
        z_plane_solver_module,
        "compute_uv_anchor_to_target_view",
        lambda **kwargs: _view(100.0, 200.0, 300.0, 400.0),
    )
    first = build_layer_z_plane_observation(measurement)

    monkeypatch.setattr(
        z_plane_solver_module,
        "compute_uv_anchor_to_target_view",
        lambda **kwargs: _view(-5000.0, 2200.0, 9100.0, -3300.0),
    )
    second = build_layer_z_plane_observation(measurement)

    assert first.effective_x == pytest.approx(1234.5, abs=1e-9)
    assert first.effective_y == pytest.approx(678.9, abs=1e-9)
    assert second.effective_x == pytest.approx(first.effective_x, abs=1e-9)
    assert second.effective_y == pytest.approx(first.effective_y, abs=1e-9)


def test_solver_ignores_logged_actual_xy_values(tmp_path):
    calibration = _copied_layer_calibration(tmp_path, "U")
    shifted_measurements = [
        LayerZPlaneMeasurement(
            gcode_line=measurement.gcode_line,
            layer=measurement.layer,
            actual_x=measurement.actual_x + (1000.0 * (index + 1)),
            actual_y=measurement.actual_y - (750.0 * (index + 1)),
            actual_z=measurement.actual_z,
        )
        for index, measurement in enumerate(_U_SAMPLE_MEASUREMENTS)
    ]

    baseline = fit_layer_z_plane(
        _U_SAMPLE_MEASUREMENTS,
        layer_calibration_path=calibration.getFullFileName(),
    )
    shifted = fit_layer_z_plane(
        shifted_measurements,
        layer_calibration_path=calibration.getFullFileName(),
    )

    assert baseline.coefficients is not None
    assert shifted.coefficients is not None
    assert baseline.coefficients == pytest.approx(shifted.coefficients, abs=1e-9)
    assert [
        (observation.effective_x, observation.effective_y)
        for observation in baseline.observations
    ] == pytest.approx(
        [
            (observation.effective_x, observation.effective_y)
            for observation in shifted.observations
        ],
        abs=1e-9,
    )


def test_one_measurement_reports_insufficient_rank(tmp_path):
    calibration = _copied_layer_calibration(tmp_path, "U")

    fitted = fit_layer_z_plane(
        _U_SAMPLE_MEASUREMENTS[:1],
        layer_calibration_path=calibration.getFullFileName(),
    )

    assert fitted.coefficients is None
    assert fitted.rank == 1
    assert "Need at least 3 non-collinear" in str(fitted.fit_error)


def test_two_measurements_report_insufficient_rank(tmp_path):
    calibration = _copied_layer_calibration(tmp_path, "U")

    fitted = fit_layer_z_plane(
        _U_SAMPLE_MEASUREMENTS[:2],
        layer_calibration_path=calibration.getFullFileName(),
    )

    assert fitted.coefficients is None
    assert fitted.rank == 2
    assert "Need at least 3 non-collinear" in str(fitted.fit_error)


def test_three_non_collinear_measurements_solve_plane(tmp_path):
    calibration = _copied_layer_calibration(tmp_path, "U")

    fitted = fit_layer_z_plane(
        _U_SAMPLE_MEASUREMENTS[:3],
        layer_calibration_path=calibration.getFullFileName(),
    )

    assert fitted.rank == 3
    assert fitted.coefficients is not None
    assert fitted.fit_error is None


def test_three_collinear_effective_points_are_rejected():
    measurements = [
        LayerZPlaneMeasurement("m1", "U", 0.0, 0.0, 10.0),
        LayerZPlaneMeasurement("m2", "U", 0.0, 0.0, 12.0),
        LayerZPlaneMeasurement("m3", "U", 0.0, 0.0, 14.0),
    ]
    observations = [
        LayerZPlaneObservation(
            gcode_line=measurement.gcode_line,
            layer="U",
            anchor_pin="A1",
            target_pin="A2",
            pin_family="A",
            actual_x=measurement.actual_x,
            actual_y=measurement.actual_y,
            actual_z=measurement.actual_z,
            tangent_point_a_x=0.0,
            tangent_point_a_y=0.0,
            tangent_point_b_x=1.0,
            tangent_point_b_y=1.0,
            transfer_point_x=float(index),
            transfer_point_y=float(index),
            lambda_value=float(index),
            effective_x=float(index),
            effective_y=float(index),
            normalized_z=10.0 + (2.0 * index),
        )
        for index, measurement in enumerate(measurements)
    ]

    fitted = fit_layer_z_plane_from_observations(measurements, observations)

    assert fitted.coefficients is None
    assert fitted.rank == 2
    assert "Need at least 3 non-collinear" in str(fitted.fit_error)


def test_b_side_measurement_is_normalized_by_board_width(tmp_path):
    calibration = _copied_layer_calibration(tmp_path, "U")
    measurement = _U_SAMPLE_MEASUREMENTS[1]

    observation = build_layer_z_plane_observation(
        measurement,
        layer_calibration_path=calibration.getFullFileName(),
    )

    assert observation.pin_family == "B"
    assert observation.normalized_z == pytest.approx(
        measurement.actual_z - BOARD_WIDTH_MM,
        abs=1e-9,
    )


def test_offset_changes_effective_point(tmp_path):
    calibration = _copied_layer_calibration(tmp_path, "U")
    plain = LayerZPlaneMeasurement(
        gcode_line="~anchorToTarget(B610,B191)",
        layer="U",
        actual_x=0.0,
        actual_y=0.0,
        actual_z=276.0,
    )
    shifted = LayerZPlaneMeasurement(
        gcode_line="~anchorToTarget(B610,B191,offset=(0,1))",
        layer="U",
        actual_x=0.0,
        actual_y=0.0,
        actual_z=276.0,
    )

    plain_observation = build_layer_z_plane_observation(
        plain,
        layer_calibration_path=calibration.getFullFileName(),
    )
    shifted_observation = build_layer_z_plane_observation(
        shifted,
        layer_calibration_path=calibration.getFullFileName(),
    )

    delta_x = abs(shifted_observation.effective_x - plain_observation.effective_x)
    delta_y = abs(shifted_observation.effective_y - plain_observation.effective_y)

    assert max(delta_x, delta_y) > 1e-6


def test_layer_calibration_json_round_trip_preserves_z_plane_payload(tmp_path):
    calibration = _copied_layer_calibration(tmp_path, "U")
    fitted = fit_layer_z_plane(
        _U_SAMPLE_MEASUREMENTS[:3],
        layer_calibration_path=calibration.getFullFileName(),
    )
    calibration.zPlaneCalibration = fitted
    calibration.save()

    reloaded = LayerCalibration("U")
    reloaded.load(str(tmp_path), "U_Calibration.json", exceptionForMismatch=False)

    assert reloaded.zPlaneCalibration is not None
    assert len(reloaded.zPlaneCalibration.measurements) == 3
    assert reloaded.zPlaneCalibration.coefficients is not None
    assert reloaded.zPlaneCalibration.coefficients == pytest.approx(
        fitted.coefficients,
        abs=1e-9,
    )


def test_sample_measurements_fit_plausible_plane(tmp_path):
    calibration = _copied_layer_calibration(tmp_path, "U")

    fitted = fit_layer_z_plane(
        _U_SAMPLE_MEASUREMENTS,
        layer_calibration_path=calibration.getFullFileName(),
    )

    assert fitted.rank == 3
    assert fitted.coefficients is not None
    assert fitted.fit_error is None
    assert fitted.residual_sum_squares is not None
    assert fitted.residual_sum_squares < 10.0
    assert fitted.max_abs_side_deviation_mm is not None
    assert fitted.max_abs_side_deviation_mm < 20.0


def test_apply_layer_z_plane_calibration_rewrites_pin_z_values_and_side_means(tmp_path):
    calibration = _copied_layer_calibration(tmp_path, "U")
    fitted = fit_layer_z_plane(
        _U_SAMPLE_MEASUREMENTS,
        layer_calibration_path=calibration.getFullFileName(),
    )

    assert apply_layer_z_plane_calibration(calibration, fitted) is True
    assert fitted.coefficients is not None

    a_pin = "A1010"
    b_pin = "B610"
    a_location = calibration.getPinLocation(a_pin)
    b_location = calibration.getPinLocation(b_pin)

    assert a_location.z == pytest.approx(
        evaluate_plane_z(
            fitted.coefficients, a_location.x, a_location.y, pin_family="A"
        ),
        abs=1e-9,
    )
    assert b_location.z == pytest.approx(
        evaluate_plane_z(
            fitted.coefficients, b_location.x, b_location.y, pin_family="B"
        ),
        abs=1e-9,
    )

    a_values = [
        calibration.getPinLocation(pin_name).z
        for pin_name in calibration.getPinNames()
        if pin_name.startswith("A")
    ]
    b_values = [
        calibration.getPinLocation(pin_name).z
        for pin_name in calibration.getPinNames()
        if pin_name.startswith("B")
    ]
    assert calibration.zFront == pytest.approx(sum(a_values) / len(a_values), abs=1e-9)
    assert calibration.zBack == pytest.approx(sum(b_values) / len(b_values), abs=1e-9)


def test_same_side_only_rejects_mixed_pair(tmp_path):
    calibration = _copied_layer_calibration(tmp_path, "U")
    measurement = LayerZPlaneMeasurement(
        gcode_line="~anchorToTarget(B1201,A1201)",
        layer="U",
        actual_x=0.0,
        actual_y=0.0,
        actual_z=200.0,
    )

    with pytest.raises(ValueError, match="same-side A-A or B-B"):
        build_layer_z_plane_observation(
            measurement,
            layer_calibration_path=calibration.getFullFileName(),
        )


def test_process_commands_add_get_and_clear_layer_z_plane_calibration(tmp_path):
    calibration = _copied_layer_calibration(tmp_path, "U")
    process = _CalibrationProcess(calibration)
    machine_calibration = _load_machine_calibration()
    registry = build_command_registry(
        process,
        DummyIO(),
        DummyConfiguration(),
        DummyLowLevelIO,
        DummyLog(),
        machine_calibration,
    )

    first = registry.executeRequest(
        {
            "name": "process.add_layer_z_plane_measurement",
            "args": {
                "gcode_line": _U_SAMPLE_MEASUREMENTS[0].gcode_line,
                "actual_x": _U_SAMPLE_MEASUREMENTS[0].actual_x,
                "actual_y": _U_SAMPLE_MEASUREMENTS[0].actual_y,
                "actual_z": _U_SAMPLE_MEASUREMENTS[0].actual_z,
                "layer": "U",
            },
        }
    )

    assert first["ok"] is True
    assert len(first["data"]["measurements"]) == 1
    assert "Need at least 3 non-collinear" in str(first["data"]["fit_error"])

    for measurement in _U_SAMPLE_MEASUREMENTS[1:3]:
        response = registry.executeRequest(
            {
                "name": "process.add_layer_z_plane_measurement",
                "args": {
                    "gcode_line": measurement.gcode_line,
                    "actual_x": measurement.actual_x,
                    "actual_y": measurement.actual_y,
                    "actual_z": measurement.actual_z,
                    "layer": "U",
                },
            }
        )
        assert response["ok"] is True

    get_response = registry.executeRequest(
        {"name": "process.get_layer_z_plane_calibration", "args": {"layer": "U"}}
    )
    assert get_response["ok"] is True
    assert len(get_response["data"]["measurements"]) == 3
    assert get_response["data"]["coefficients"] is not None
    assert get_response["data"]["fit_error"] is None
    assert process.gCodeHandler.sync_calls

    reloaded = LayerCalibration("U")
    reloaded.load(str(tmp_path), "U_Calibration.json", exceptionForMismatch=False)
    assert reloaded.zPlaneCalibration is not None
    assert reloaded.zPlaneCalibration.coefficients is not None

    clear_response = registry.executeRequest(
        {"name": "process.clear_layer_z_plane_calibration", "args": {"layer": "U"}}
    )
    assert clear_response["ok"] is True
    assert clear_response["data"]["measurements"] == []
    assert clear_response["data"]["observations"] == []

    reloaded.load(str(tmp_path), "U_Calibration.json", exceptionForMismatch=False)
    assert reloaded.zPlaneCalibration is None


def test_process_command_rejects_mixed_pair_measurement(tmp_path):
    calibration = _copied_layer_calibration(tmp_path, "U")
    process = _CalibrationProcess(calibration)
    registry = build_command_registry(
        process,
        DummyIO(),
        DummyConfiguration(),
        DummyLowLevelIO,
        DummyLog(),
        _load_machine_calibration(),
    )

    response = registry.executeRequest(
        {
            "name": "process.add_layer_z_plane_measurement",
            "args": {
                "gcode_line": "~anchorToTarget(B1201,A1201)",
                "actual_x": 0.0,
                "actual_y": 0.0,
                "actual_z": 200.0,
                "layer": "U",
            },
        }
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "VALIDATION_ERROR"
    assert "same-side A-A or B-B" in response["error"]["message"]
