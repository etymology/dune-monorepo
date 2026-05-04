from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from dune_winder.core.machine_calibration_capture import MachineCaptureService


class _Axis:
    def __init__(self, position: float):
        self._position = float(position)

    def getPosition(self):
        return self._position


class _IO:
    def __init__(self, x: float, y: float, z: float):
        self.xAxis = _Axis(x)
        self.yAxis = _Axis(y)
        self.zAxis = _Axis(z)


class _TimeSource:
    def __init__(self):
        self._value = 0

    def get(self):
        self._value += 1
        return f"t{self._value}"


class _StateClass:
    pass


class _ControlStateMachine:
    def __init__(self, *, active: bool):
        cls = type("WindMode" if active else "StopMode", (_StateClass,), {})
        self.state = cls()


class _MachineCalibration:
    def __init__(self):
        self._outputFileName = "test-machine"


class _TemplateService:
    """Pretend U/V template service. Captures replaceLineOffsetOverrides
    and generateRecipeFile calls for assertion."""

    def __init__(self, wrap_count: int):
        self.WRAP_COUNT = wrap_count
        self._lineOffsetOverrides: dict = {}
        self._lastGeneratedScriptVariant = None
        self.regenerated_count = 0

    def replaceLineOffsetOverrides(self, overrides):
        self._lineOffsetOverrides = dict(overrides)
        return {"ok": True}

    def generateRecipeFile(self, scriptVariant=None):
        del scriptVariant
        self.regenerated_count += 1
        return {"ok": True}


class _Process:
    def __init__(
        self,
        tmp_path,
        *,
        layer: str = "U",
        active: bool = False,
        wrap_count: int = 4,
        current_xyz=(10.0, 20.0, 207.5),
    ):
        self._workspaceCalibrationDirectory = str(tmp_path)
        self._systemTime = _TimeSource()
        self._io = _IO(*current_xyz)
        self._machineCalibration = _MachineCalibration()
        self.controlStateMachine = _ControlStateMachine(active=active)
        self.workspace = None
        self.uTemplateRecipe = _TemplateService(wrap_count)
        self.vTemplateRecipe = _TemplateService(wrap_count)
        self._layer = layer
        self._lastTrace = None

    def getRecipeLayer(self):
        return self._layer

    def getLastInstructionTrace(self):
        return self._lastTrace

    def isGCodeExecutionActive(self):
        return (
            getattr(self.controlStateMachine.state.__class__, "__name__", "")
            == "WindMode"
        )


def _trace(
    *,
    anchor: str,
    target: str,
    line: str | None = None,
    calc_x: float = 100.0,
    calc_y: float = 200.0,
    calc_z: float = 207.0,
):
    """Build a `lastTrace` matching what handler_base records for an
    `~anchorToTarget` move."""
    if line is None:
        line = f"~anchorToTarget({anchor},{target}) (3,8)"
    return {
        "line": line,
        "resultingTarget": {
            "x": calc_x,
            "y": calc_y,
            "pinZ": calc_z,
            "headZ": calc_z,
        },
        "pins": [
            {"role": "wrapAnchor", "pin": anchor},
            {"role": "wrapTarget", "pin": target},
        ],
    }


# -- get_state ----------------------------------------------------------


def test_get_state_classifies_head_config_for_all_four_pin_combos(tmp_path):
    cases = [
        ("A1", "A2", "stage_a"),
        ("B1", "B2", "stage_b"),
        ("A1", "B2", "fixed"),
        ("B1", "A2", "retracted"),
    ]
    for anchor, target, expected in cases:
        process = _Process(tmp_path)
        process._lastTrace = _trace(anchor=anchor, target=target)
        service = MachineCaptureService(process)

        state = service.get_state()

        assert state["headConfig"] == expected, (anchor, target)
        assert state["anchorSide"] == anchor[0]
        assert state["targetSide"] == target[0]
        assert state["canRecord"] is True


def test_get_state_includes_current_xyz_and_propagation_scope(tmp_path):
    process = _Process(tmp_path, current_xyz=(11.5, 22.25, 208.75), wrap_count=400)
    process._lastTrace = _trace(anchor="A1", target="A40")
    service = MachineCaptureService(process)

    state = service.get_state()

    assert state["currentXyz"] == {"x": 11.5, "y": 22.25, "z": 208.75}
    assert state["propagationScope"] == {
        "wrapLineNumber": 8,
        "wrapCount": 400,
        "layer": "U",
    }


def test_get_state_disables_capture_while_gcode_running(tmp_path):
    process = _Process(tmp_path, active=True)
    process._lastTrace = _trace(anchor="A1", target="A40")
    service = MachineCaptureService(process)

    state = service.get_state()

    assert state["canRecord"] is False


def test_get_state_disables_capture_when_trace_is_not_anchor_to_target(tmp_path):
    process = _Process(tmp_path)
    # No pins => not an anchor-to-target move.
    process._lastTrace = {
        "line": "G113 PPRECISE (3,8)",
        "resultingTarget": {"x": 0.0, "y": 0.0, "pinZ": 207.0, "headZ": 207.0},
        "pins": [],
    }
    service = MachineCaptureService(process)

    state = service.get_state()

    assert state["headConfig"] is None
    assert state["canRecord"] is False


def test_get_state_returns_no_lastTrace_gracefully(tmp_path):
    process = _Process(tmp_path)
    service = MachineCaptureService(process)

    state = service.get_state()

    assert state["lastTrace"] is None
    assert state["headConfig"] is None
    assert state["propagationScope"] is None
    assert state["canRecord"] is False
    # currentXyz should still be readable.
    assert state["currentXyz"] == {"x": 10.0, "y": 20.0, "z": 207.5}


# -- record_capture -----------------------------------------------------


def test_record_capture_propagates_offset_across_all_wraps(tmp_path):
    """Capturing on a (3,8) line writes overrides for (1,8), (2,8), …
    (WRAP_COUNT, 8) with the same offset."""
    process = _Process(tmp_path, wrap_count=5, current_xyz=(101.5, 200.25, 207.75))
    process._lastTrace = _trace(
        anchor="A1",
        target="A2",
        calc_x=100.0,
        calc_y=200.0,
        calc_z=207.0,
    )
    service = MachineCaptureService(process)

    point = service.record_capture()

    expected_offset = {"x": 1.5, "y": 0.25, "z": 0.75}
    assert point["offset"] == pytest.approx(expected_offset)
    assert point["headConfig"] == "stage_a"

    overrides = process.uTemplateRecipe._lineOffsetOverrides
    assert sorted(overrides.keys()) == [
        "(1,8)",
        "(2,8)",
        "(3,8)",
        "(4,8)",
        "(5,8)",
    ]
    for entry in overrides.values():
        assert entry["x"] == pytest.approx(1.5)
        assert entry["y"] == pytest.approx(0.25)
        assert entry["z"] == pytest.approx(0.75)
    assert process.uTemplateRecipe.regenerated_count == 1


def test_record_capture_combines_with_existing_overrides(tmp_path):
    process = _Process(tmp_path, wrap_count=3, current_xyz=(101.0, 200.0, 207.5))
    process._lastTrace = _trace(
        anchor="B1",
        target="B2",
        calc_x=100.0,
        calc_y=200.0,
        calc_z=207.0,
    )
    # Pre-existing override on (2,8) should additively combine.
    process.uTemplateRecipe._lineOffsetOverrides = {
        "(2,8)": {"x": 0.1, "y": 0.2, "z": 0.3}
    }
    service = MachineCaptureService(process)

    service.record_capture()

    overrides = process.uTemplateRecipe._lineOffsetOverrides
    # New wraps get just the delta.
    assert overrides["(1,8)"]["x"] == pytest.approx(1.0)
    assert overrides["(3,8)"]["x"] == pytest.approx(1.0)
    # Pre-existing entry was combined.
    assert overrides["(2,8)"]["x"] == pytest.approx(1.1)
    assert overrides["(2,8)"]["y"] == pytest.approx(0.2)
    assert overrides["(2,8)"]["z"] == pytest.approx(0.8)


def test_record_capture_persists_to_machine_calibration_file(tmp_path):
    process = _Process(tmp_path, wrap_count=2)
    process._lastTrace = _trace(anchor="A1", target="B2")
    service = MachineCaptureService(process)

    service.record_capture()

    on_disk = tmp_path / "machineCalibrationCapture.json"
    assert on_disk.is_file()
    payload = json.loads(on_disk.read_text())
    assert len(payload["capture_points"]) == 1
    point = payload["capture_points"][0]
    assert point["head_config"] == "fixed"
    assert "head_side" not in point


def test_record_capture_rejected_when_trace_is_not_anchor_to_target(tmp_path):
    process = _Process(tmp_path)
    process._lastTrace = {
        "line": "G113 PPRECISE (3,8)",
        "resultingTarget": {"x": 0.0, "y": 0.0, "pinZ": 207.0, "headZ": 207.0},
        "pins": [],
    }
    service = MachineCaptureService(process)

    with pytest.raises(ValueError):
        service.record_capture()


def test_record_capture_rejected_while_gcode_running(tmp_path):
    process = _Process(tmp_path, active=True)
    process._lastTrace = _trace(anchor="A1", target="A2")
    service = MachineCaptureService(process)

    with pytest.raises(RuntimeError):
        service.record_capture()
