from __future__ import annotations

import hashlib
import json
from pathlib import Path

import dune_tension.layer_calibration as layer_calibration


def test_sync_layer_calibration_from_desktop_writes_local_file(monkeypatch, tmp_path) -> None:
    calibration_dir = tmp_path / "config" / "APA"
    monkeypatch.setattr(layer_calibration, "APA_CALIBRATION_DIR", calibration_dir)
    monkeypatch.setattr(
        layer_calibration,
        "desktop_get_layer_calibration_json",
        lambda layer: {
            "layer": layer,
            "activeLayer": layer,
            "calibrationFile": f"{layer}_Calibration.json",
            "source": "workspace",
            "content": '{\n  "layer": "' + str(layer) + '"\n}\n',
        },
    )

    result = layer_calibration.sync_layer_calibration_from_desktop("V")

    target = calibration_dir / "V_Calibration.json"
    assert target.read_text(encoding="utf-8") == '{\n  "layer": "V"\n}\n'
    assert result.layer == "V"
    assert result.calibration_file == "V_Calibration.json"
    assert result.content_hash == hashlib.sha256('{\n  "layer": "V"\n}\n'.encode("utf-8")).hexdigest()
    assert result.changed is True


def test_sync_layer_calibration_from_desktop_skips_rewrite_when_hash_matches(
    monkeypatch,
    tmp_path,
) -> None:
    calibration_dir = tmp_path / "config" / "APA"
    calibration_dir.mkdir(parents=True, exist_ok=True)
    target = calibration_dir / "V_Calibration.json"
    target.write_text('{\n  "layer": "V"\n}\n', encoding="utf-8")
    monkeypatch.setattr(layer_calibration, "APA_CALIBRATION_DIR", calibration_dir)
    monkeypatch.setattr(
        layer_calibration,
        "desktop_get_layer_calibration_json",
        lambda layer: {
            "layer": layer,
            "activeLayer": layer,
            "calibrationFile": f"{layer}_Calibration.json",
            "source": "workspace",
            "contentHash": hashlib.sha256('{\n  "layer": "V"\n}\n'.encode("utf-8")).hexdigest(),
            "content": '{\n  "layer": "V"\n}\n',
        },
    )

    writes = []
    monkeypatch.setattr(
        layer_calibration,
        "_atomic_write_text",
        lambda path, content: writes.append((path, content)),
    )

    result = layer_calibration.sync_layer_calibration_from_desktop("V")

    assert writes == []
    assert result.changed is False
    assert target.read_text(encoding="utf-8") == '{\n  "layer": "V"\n}\n'


def test_capture_laser_offset_stores_side_keyed_value(monkeypatch, tmp_path) -> None:
    offset_path = tmp_path / "TensionLaserOffsets.json"
    monkeypatch.setattr(layer_calibration, "LASER_OFFSET_PATH", offset_path)
    monkeypatch.setattr(layer_calibration, "get_calibrated_pin_xy", lambda _layer, _pin: (100.0, 200.0))

    entry = layer_calibration.capture_laser_offset(
        layer="U",
        side="B",
        pin_name="B401",
        captured_stage_xy=(96.5, 203.25),
        captured_focus=4100,
    )

    saved = json.loads(offset_path.read_text(encoding="utf-8"))
    assert entry["x"] == 3.5
    assert entry["y"] == -3.25
    assert saved["A"] is None
    assert saved["B"]["captured_pin"] == "B401"
    assert saved["B"]["captured_layer"] == "U"


def test_capture_laser_offset_uses_front_pin_family_for_a_side(monkeypatch, tmp_path) -> None:
    offset_path = tmp_path / "TensionLaserOffsets.json"
    monkeypatch.setattr(layer_calibration, "LASER_OFFSET_PATH", offset_path)

    looked_up_pins = []

    def _record_pin(_layer, pin_name):
        looked_up_pins.append(pin_name)
        return (100.0, 200.0)

    monkeypatch.setattr(layer_calibration, "get_calibrated_pin_xy", _record_pin)

    entry = layer_calibration.capture_laser_offset(
        layer="V",
        side="A",
        pin_name="B400",
        captured_stage_xy=(95.0, 198.0),
        captured_focus=None,
    )

    saved = json.loads(offset_path.read_text(encoding="utf-8"))
    assert looked_up_pins == ["F2399"]
    assert entry["captured_pin"] == "F2399"
    assert saved["A"]["captured_pin"] == "F2399"


def test_get_bottom_pin_options_returns_first_and_last_bottom_pins() -> None:
    assert layer_calibration.get_bottom_pin_options("U", "A") == [
        ("Bottom first (F2401)", "F2401"),
        ("Bottom last (F1602)", "F1602"),
    ]
    assert layer_calibration.get_bottom_pin_options("V", "B") == [
        ("Bottom first (B400)", "B400"),
        ("Bottom last (B1199)", "B1199"),
    ]


def test_get_bottom_pin_options_uses_front_family_for_a_side() -> None:
    assert layer_calibration.get_bottom_pin_options("V", "A") == [
        ("Bottom first (F2399)", "F2399"),
        ("Bottom last (F1600)", "F1600"),
    ]


def test_resolve_pin_name_for_side_uses_requested_family() -> None:
    assert layer_calibration.resolve_pin_name_for_side("V", "A", "B400") == "F2399"
    assert layer_calibration.resolve_pin_name_for_side("V", "B", "F2399") == "B400"


def test_get_calibrated_pin_xy_for_side_uses_resolved_pin_name(monkeypatch) -> None:
    monkeypatch.setattr(
        layer_calibration,
        "load_normalized_layer_calibration",
        lambda _layer: {
            "locations": {
                "B400": {"x": 1.0, "y": 2.0},
                "F2399": {"x": 3.0, "y": 4.0},
            }
        },
    )

    assert layer_calibration.get_calibrated_pin_xy_for_side("V", "A", "B400") == (3.0, 4.0)
    assert layer_calibration.get_calibrated_pin_xy_for_side("V", "B", "F2399") == (1.0, 2.0)


def test_ensure_local_layer_calibration_file_generates_default_when_missing(
    monkeypatch,
    tmp_path,
) -> None:
    calibration_dir = tmp_path / "config" / "APA"
    monkeypatch.setattr(layer_calibration, "APA_CALIBRATION_DIR", calibration_dir)

    generated = []

    class _FakeDefaultLayerCalibration:
        def __init__(self, output_file_path, output_file_name, layer_name):
            generated.append((output_file_path, output_file_name, layer_name))
            target = calibration_dir / output_file_name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('{\n  "layer": "' + layer_name + '"\n}\n', encoding="utf-8")

    monkeypatch.setattr(
        layer_calibration,
        "DefaultLayerCalibration",
        _FakeDefaultLayerCalibration,
    )

    path = layer_calibration.ensure_local_layer_calibration_file("V")

    assert path == calibration_dir / "V_Calibration.json"
    assert path.read_text(encoding="utf-8") == '{\n  "layer": "V"\n}\n'
    assert generated == [(str(calibration_dir), "V_Calibration.json", "V")]


def test_load_normalized_layer_calibration_uses_generated_default_when_missing(
    monkeypatch,
    tmp_path,
) -> None:
    calibration_dir = tmp_path / "config" / "APA"
    monkeypatch.setattr(layer_calibration, "APA_CALIBRATION_DIR", calibration_dir)

    class _FakeDefaultLayerCalibration:
        def __init__(self, output_file_path, output_file_name, layer_name):
            target = Path(output_file_path) / output_file_name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('{\n  "layer": "' + layer_name + '"\n}\n', encoding="utf-8")

    class _FakeLayerCalibration:
        def __init__(self, layer):
            self.layer = layer
            self.loaded = None

        def load(self, directory, filename):
            self.loaded = (directory, filename)

    class _FakeNormalizedCalibration:
        def getPinNames(self):
            return ["B1"]

        def getPinLocation(self, pin_name):
            assert pin_name == "B1"
            return type("Location", (), {"x": 1.0, "y": 2.0, "z": 3.0})()

    monkeypatch.setattr(
        layer_calibration,
        "DefaultLayerCalibration",
        _FakeDefaultLayerCalibration,
    )
    monkeypatch.setattr(layer_calibration, "LayerCalibration", _FakeLayerCalibration)
    monkeypatch.setattr(
        layer_calibration,
        "normalize_calibration",
        lambda calibration, requested_layer: _FakeNormalizedCalibration(),
    )
    monkeypatch.setattr(
        layer_calibration,
        "create_layer_geometry",
        lambda _layer: type("Geometry", (), {"pinDiameter": 2.43})(),
    )

    payload = layer_calibration.load_normalized_layer_calibration("V")

    assert payload["layer"] == "V"
    assert payload["calibrationFile"] == "V_Calibration.json"
    assert payload["pinDiameterMm"] == 2.43
    assert payload["locations"]["B1"] == {"x": 1.0, "y": 2.0, "z": 3.0}


def test_bottom_back_pin_to_front_pin_uses_uv_translation_formula() -> None:
    assert layer_calibration._bottom_back_pin_to_front_pin("V", 400) == 2399
    assert layer_calibration._bottom_back_pin_to_front_pin("V", 1199) == 1600
    assert layer_calibration._bottom_back_pin_to_front_pin("U", 401) == 2401
    assert layer_calibration._bottom_back_pin_to_front_pin("U", 1200) == 1602
