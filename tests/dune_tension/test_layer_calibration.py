from __future__ import annotations

import json

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


def test_get_bottom_pin_options_returns_first_and_last_bottom_pins() -> None:
    assert layer_calibration.get_bottom_pin_options("U", "A") == [
        ("Bottom first (B401)", "B401"),
        ("Bottom last (B1200)", "B1200"),
    ]
    assert layer_calibration.get_bottom_pin_options("V", "B") == [
        ("Bottom first (B400)", "B400"),
        ("Bottom last (B1199)", "B1199"),
    ]
