"""Tests for scripts/convert_legacy_pin_calibration.py and the
round-trip through dune_geometry.PinCalibrationFile."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import convert_legacy_pin_calibration as clpc  # noqa: E402

dune_geometry = pytest.importorskip("dune_geometry")


def _write_legacy(path: Path, layer: str, locations: dict, offset=None) -> None:
    legacy = {
        "layer": layer,
        "zFront": 145,
        "zBack": 275,
        "zPlaneCalibration": None,
        "hashValue": "abc",
        "offset": offset or {"x": 0.0, "y": 0.0, "z": 0.0},
        "locations": locations,
    }
    path.write_text(json.dumps(legacy), encoding="utf-8")


def test_split_legacy_key_handles_legacy_and_canonical() -> None:
    assert clpc._split_legacy_key("A1") == ("A", "1")
    assert clpc._split_legacy_key("B400") == ("B", "400")
    assert clpc._split_legacy_key("UA1") == ("A", "1")
    assert clpc._split_legacy_key("VB23") == ("B", "23")
    assert clpc._split_legacy_key("X1") == (None, "")


def test_convert_single_layer(tmp_path: Path) -> None:
    legacy_u = tmp_path / "U_Calibration.json"
    _write_legacy(
        legacy_u,
        "U",
        {
            "A1": {"x": 1.0, "y": 2.0, "z": 145},
            "B400": {"x": 4.0, "y": 5.0, "z": 145},
        },
    )
    new_doc = clpc.convert(
        legacy_u=legacy_u,
        legacy_v=None,
        machine_id="apa-stand-01",
        camera_id="default",
    )
    assert new_doc["machine_id"] == "apa-stand-01"
    assert len(new_doc["snapshots"]) == 1
    snap = new_doc["snapshots"][0]
    assert snap["calibration_camera_id"] == "default"
    assert snap["notes"] == "Imported from legacy U_Calibration.json"
    pin_objs = {
        (entry["pin"]["layer"], entry["pin"]["side"], entry["pin"]["number"])
        for entry in snap["pins"]
    }
    assert pin_objs == {("U", "A", 1), ("U", "B", 400)}


def test_convert_subtracts_top_level_offset(tmp_path: Path) -> None:
    legacy_u = tmp_path / "U_Calibration.json"
    _write_legacy(
        legacy_u,
        "U",
        {"A1": {"x": 100.0, "y": 200.0, "z": 50.0}},
        offset={"x": 10.0, "y": 20.0, "z": 5.0},
    )
    new_doc = clpc.convert(
        legacy_u=legacy_u,
        legacy_v=None,
        machine_id="apa",
        camera_id="default",
    )
    pin = new_doc["snapshots"][0]["pins"][0]
    assert pin["xyz"] == {"x": 90.0, "y": 180.0, "z": 45.0}


def test_convert_combines_u_and_v(tmp_path: Path) -> None:
    legacy_u = tmp_path / "U_Calibration.json"
    legacy_v = tmp_path / "V_Calibration.json"
    _write_legacy(legacy_u, "U", {"A1": {"x": 1.0, "y": 1.0, "z": 1.0}})
    _write_legacy(legacy_v, "V", {"B23": {"x": 2.0, "y": 2.0, "z": 2.0}})

    # Make V older than U so snapshots sort V-first.
    older_mtime = os.stat(legacy_v).st_mtime - 10
    os.utime(legacy_v, (older_mtime, older_mtime))

    new_doc = clpc.convert(
        legacy_u=legacy_u,
        legacy_v=legacy_v,
        machine_id="apa",
        camera_id="default",
    )
    assert len(new_doc["snapshots"]) == 2
    layers = [snap["pins"][0]["pin"]["layer"] for snap in new_doc["snapshots"]]
    assert layers == ["V", "U"]


def test_convert_output_is_loadable_by_rust(tmp_path: Path) -> None:
    legacy_u = tmp_path / "U_Calibration.json"
    _write_legacy(
        legacy_u,
        "U",
        {
            "A1": {"x": 1.0, "y": 2.0, "z": 3.0},
            "B400": {"x": 4.0, "y": 5.0, "z": 6.0},
            "garbage_key": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
    )
    new_doc = clpc.convert(
        legacy_u=legacy_u,
        legacy_v=None,
        machine_id="apa-stand-01",
        camera_id="default",
    )
    text = json.dumps(new_doc)
    file = dune_geometry.PinCalibrationFile.from_json(text)
    assert file.machine_id == "apa-stand-01"
    assert len(file.snapshots) == 1
    pins = {str(c.pin) for c in file.snapshots[0].pins}
    assert pins == {"UA1", "UB400"}


def test_convert_real_legacy_files_roundtrip_via_rust() -> None:
    """Smoke test against the actual config/APA legacy JSONs in this repo."""
    repo_u = REPO_ROOT / "config" / "APA" / "U_Calibration.json"
    repo_v = REPO_ROOT / "config" / "APA" / "V_Calibration.json"
    if not repo_u.exists() or not repo_v.exists():
        pytest.skip("legacy calibration files not present in this checkout")
    new_doc = clpc.convert(
        legacy_u=repo_u,
        legacy_v=repo_v,
        machine_id="apa-stand-01",
        camera_id="default",
    )
    text = json.dumps(new_doc)
    file = dune_geometry.PinCalibrationFile.from_json(text)
    assert file.machine_id == "apa-stand-01"
    assert len(file.snapshots) == 2
    eff = dict(file.effective_pin_coords())
    # Both layers populate the effective coord map.
    layers = {pin.layer for pin in eff.keys()}
    assert layers == {"U", "V"}
