"""Unit tests for scripts/migrate_pin_names.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import migrate_pin_names as mpn  # noqa: E402  (sys.path injection above)


def test_to_canonical_legacy_keys() -> None:
    assert mpn.to_canonical("U", "A1") == "UA1"
    assert mpn.to_canonical("V", "B2399") == "VB2399"


def test_to_canonical_passes_through_canonical_keys() -> None:
    assert mpn.to_canonical("U", "UA1") == "UA1"
    assert mpn.to_canonical("V", "VB23") == "VB23"


def test_to_canonical_passes_through_non_pin_keys() -> None:
    assert mpn.to_canonical("U", "layer") == "layer"
    assert mpn.to_canonical("U", "x") == "x"
    assert mpn.to_canonical("U", "A0extra") == "A0extra"


def test_rewrite_pin_keys_walks_nested_dicts() -> None:
    doc = {
        "layer": "U",
        "locations": {
            "A1": {"x": 1.0, "y": 2.0, "z": 3.0},
            "B400": {"x": 4.0, "y": 5.0, "z": 6.0},
        },
        "metadata": {"hash": "abc", "perPin": {"A1": 0.5, "B400": 0.6}},
    }
    out = mpn.rewrite_pin_keys(doc, "U")
    assert set(out["locations"].keys()) == {"UA1", "UB400"}
    assert out["locations"]["UA1"] == {"x": 1.0, "y": 2.0, "z": 3.0}
    assert set(out["metadata"]["perPin"].keys()) == {"UA1", "UB400"}
    # Non-pin keys preserved.
    assert out["metadata"]["hash"] == "abc"
    assert out["layer"] == "U"


def test_infer_layer_from_top_level_field(tmp_path: Path) -> None:
    p = tmp_path / "anything.json"
    p.write_text("{}", encoding="utf-8")
    assert mpn.infer_layer(p, {"layer": "v"}, None) == "V"


def test_infer_layer_from_filename(tmp_path: Path) -> None:
    p = tmp_path / "U_Calibration.json"
    p.write_text("{}", encoding="utf-8")
    assert mpn.infer_layer(p, {}, None) == "U"


def test_infer_layer_explicit_overrides(tmp_path: Path) -> None:
    p = tmp_path / "ambiguous.json"
    p.write_text("{}", encoding="utf-8")
    assert mpn.infer_layer(p, {"layer": "U"}, "v") == "V"


def test_infer_layer_raises_when_unknown(tmp_path: Path) -> None:
    p = tmp_path / "unrelated.json"
    p.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        mpn.infer_layer(p, {}, None)


def test_migrate_file_dry_run_emits_diff(tmp_path, capsys) -> None:
    p = tmp_path / "U_Calibration.json"
    p.write_text(
        json.dumps({"layer": "U", "locations": {"A1": {"x": 0, "y": 0, "z": 0}}}),
        encoding="utf-8",
    )
    changed = mpn.migrate_file(p, layer_hint=None, write=False)
    assert changed == 1
    captured = capsys.readouterr()
    assert "+" in captured.out and '"UA1"' in captured.out


def test_migrate_file_write_rewrites_in_place(tmp_path: Path) -> None:
    p = tmp_path / "U_Calibration.json"
    p.write_text(
        json.dumps({"layer": "U", "locations": {"A1": {"x": 1.5, "y": 2.5, "z": 3.5}}}),
        encoding="utf-8",
    )
    changed = mpn.migrate_file(p, layer_hint=None, write=True)
    assert changed == 1
    after = json.loads(p.read_text(encoding="utf-8"))
    assert "UA1" in after["locations"]
    assert "A1" not in after["locations"]
    assert after["locations"]["UA1"] == {"x": 1.5, "y": 2.5, "z": 3.5}


def test_migrate_file_idempotent(tmp_path: Path) -> None:
    p = tmp_path / "V_Calibration.json"
    p.write_text(
        json.dumps({"layer": "V", "locations": {"VB23": {"x": 0, "y": 0, "z": 0}}}),
        encoding="utf-8",
    )
    changed = mpn.migrate_file(p, layer_hint=None, write=True)
    assert changed == 0  # already canonical
