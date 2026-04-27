from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import logging
from pathlib import Path
import tempfile
from functools import lru_cache
from typing import Any

from dune_tension.paths import REPO_ROOT
from dune_tension.plc_io import get_plc_io_mode
from dune_tension.plc_desktop import (
    desktop_get_layer_calibration,
    desktop_get_layer_calibration_json,
)
from dune_winder.machine.calibration.defaults import DefaultLayerCalibration
from dune_winder.machine.calibration.layer import LayerCalibration
from dune_winder.machine.geometry.factory import create_layer_geometry
from dune_winder.machine.geometry.layer_functions import LayerFunctions
from dune_winder.machine.geometry.uv_calibration import (
    normalize_layer_calibration_to_absolute,
)
from dune_winder.machine.geometry.uv_layout import get_uv_layout

LOGGER = logging.getLogger(__name__)

UV_LAYERS = frozenset({"U", "V"})
APA_CALIBRATION_DIR = REPO_ROOT / "config" / "APA"
WINDER_WORKSPACE_STATE_PATH = REPO_ROOT / "cache" / "state.json"
LASER_OFFSET_PATH = APA_CALIBRATION_DIR / "TensionLaserOffsets.json"
normalize_calibration = normalize_layer_calibration_to_absolute


@dataclass(frozen=True)
class CalibrationSyncResult:
    layer: str
    calibration_file: str | None
    source: str
    synced_at: str
    local_path: str
    content_hash: str | None = None
    changed: bool = False


def _normalize_layer(layer: str) -> str:
    value = str(layer).strip().upper()
    if value not in {"U", "V", "X", "G"}:
        raise ValueError(f"Unsupported layer {layer!r}.")
    return value


def _normalize_side(side: str) -> str:
    value = str(side).strip().upper()
    if value not in {"A", "B"}:
        raise ValueError(f"Unsupported side {side!r}.")
    return value


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _load_json_file(path: Path, *, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default


def _hash_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _hash_file(path: Path) -> str | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return _hash_text(handle.read())
    except FileNotFoundError:
        return None


def get_local_layer_calibration_path(layer: str) -> Path:
    return APA_CALIBRATION_DIR / f"{_normalize_layer(layer)}_Calibration.json"


def ensure_local_layer_calibration_file(layer: str) -> Path:
    requested_layer = _normalize_layer(layer)
    local_path = get_local_layer_calibration_path(requested_layer)
    if local_path.is_file():
        return local_path

    local_path.parent.mkdir(parents=True, exist_ok=True)
    DefaultLayerCalibration(str(local_path.parent), local_path.name, requested_layer)
    clear_layer_calibration_cache()
    LOGGER.warning(
        "Local calibration file missing for layer %s; generated default calibration at %s.",
        requested_layer,
        local_path,
    )
    return local_path


def get_active_loaded_layer() -> str | None:
    state = _load_json_file(WINDER_WORKSPACE_STATE_PATH, default={})
    value = state.get("_layer")
    if value is None:
        return None
    return str(value).strip().upper() or None


def ensure_local_layer_matches_active(layer: str) -> None:
    requested_layer = _normalize_layer(layer)
    active_layer = get_active_loaded_layer()
    if active_layer and active_layer != requested_layer:
        raise ValueError(
            f"Requested layer {requested_layer} does not match active loaded layer {active_layer}."
        )


def sync_layer_calibration_from_desktop(layer: str) -> CalibrationSyncResult:
    requested_layer = _normalize_layer(layer)
    payload = desktop_get_layer_calibration_json(requested_layer)
    if payload is None:
        raise ValueError(
            f"Failed to fetch layer {requested_layer} calibration JSON from desktop."
        )

    active_layer = str(payload.get("activeLayer") or "").strip().upper()
    if active_layer != requested_layer:
        raise ValueError(
            f"Desktop active layer {active_layer or '<unset>'} does not match requested layer {requested_layer}."
        )

    calibration_file = Path(
        str(payload.get("calibrationFile") or f"{requested_layer}_Calibration.json")
    ).name
    local_path = APA_CALIBRATION_DIR / calibration_file
    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError(
            f"Desktop returned empty calibration JSON for layer {requested_layer}."
        )

    content_hash = str(payload.get("contentHash") or "").strip() or _hash_text(content)
    local_hash = _hash_file(local_path)
    changed = local_hash != content_hash
    if changed:
        _atomic_write_text(local_path, content)
        clear_layer_calibration_cache()
    synced_at = datetime.now(UTC).isoformat()
    if changed:
        LOGGER.info(
            "Synced layer %s calibration from desktop to %s (file=%s hash=%s).",
            requested_layer,
            local_path,
            calibration_file,
            content_hash,
        )
    else:
        LOGGER.info(
            "Layer %s calibration cache is current at %s (file=%s hash=%s).",
            requested_layer,
            local_path,
            calibration_file,
            content_hash,
        )
    return CalibrationSyncResult(
        layer=requested_layer,
        calibration_file=calibration_file,
        source=str(payload.get("source") or "desktop"),
        synced_at=synced_at,
        local_path=str(local_path),
        content_hash=content_hash,
        changed=changed,
    )


def ensure_layer_calibration_ready(layer: str) -> CalibrationSyncResult | None:
    requested_layer = _normalize_layer(layer)
    if requested_layer not in UV_LAYERS:
        return None

    if get_plc_io_mode() == "desktop":
        return sync_layer_calibration_from_desktop(requested_layer)

    ensure_local_layer_matches_active(requested_layer)
    ensure_local_layer_calibration_file(requested_layer)
    return None


def load_normalized_layer_calibration(layer: str) -> dict[str, Any]:
    requested_layer = _normalize_layer(layer)
    local_path = ensure_local_layer_calibration_file(requested_layer)
    calibration = LayerCalibration(layer=requested_layer)
    calibration.load(str(local_path.parent), local_path.name)
    normalized = normalize_calibration(calibration, requested_layer)
    geometry = create_layer_geometry(requested_layer)
    return {
        "layer": requested_layer,
        "calibrationFile": local_path.name,
        "pinDiameterMm": float(getattr(geometry, "pinDiameter")),
        "locations": {
            pin_name: {
                "x": float(location.x),
                "y": float(location.y),
                "z": float(location.z),
            }
            for pin_name in normalized.getPinNames()
            for location in [normalized.getPinLocation(pin_name)]
        },
    }


@lru_cache(maxsize=4)
def _load_normalized_layer_calibration_cached(layer: str) -> dict[str, Any]:
    return load_normalized_layer_calibration(layer)


@lru_cache(maxsize=2)
def _load_laser_offset_store_cached() -> dict[str, Any]:
    data = _load_json_file(LASER_OFFSET_PATH, default=_default_laser_offset_store())
    if not isinstance(data, dict):
        return _default_laser_offset_store()
    normalized = _default_laser_offset_store()
    for side in ("A", "B"):
        value = data.get(side)
        normalized[side] = value if isinstance(value, dict) else None
    return normalized


def clear_layer_calibration_cache() -> None:
    _load_normalized_layer_calibration_cached.cache_clear()
    _load_laser_offset_store_cached.cache_clear()


def load_layer_calibration_summary(layer: str) -> dict[str, Any]:
    requested_layer = _normalize_layer(layer)
    ensure_local_layer_matches_active(requested_layer)
    return _load_normalized_layer_calibration_cached(requested_layer)


def get_calibrated_pin_xy(layer: str, pin_name: str) -> tuple[float, float]:
    requested_layer = _normalize_layer(layer)
    normalized_pin = str(pin_name).strip().upper()
    calibration = load_normalized_layer_calibration(requested_layer)
    try:
        location = calibration["locations"][normalized_pin]
    except KeyError as exc:
        raise ValueError(
            f"Pin {normalized_pin} is not present in {requested_layer} calibration."
        ) from exc
    return (float(location["x"]), float(location["y"]))


def _normalize_pin_name(pin_name: str) -> str:
    value = str(pin_name).strip().upper()
    if len(value) < 2 or value[0] not in {"A", "B"} or not value[1:].isdigit():
        raise ValueError(f"Unsupported pin name {pin_name!r}.")
    return value


def _translate_pin_name_family(layer: str, pin_name: str, target_family: str) -> str:
    requested_layer = _normalize_layer(layer)
    normalized_pin = _normalize_pin_name(pin_name)
    desired_family = str(target_family).strip().upper()
    if desired_family not in {"A", "B"}:
        raise ValueError(f"Unsupported target pin family {target_family!r}.")
    if normalized_pin[0] == desired_family:
        return normalized_pin

    if requested_layer in UV_LAYERS:
        return get_uv_layout(requested_layer).translate_pin(
            normalized_pin,
            target_family=desired_family,
        )

    geometry = create_layer_geometry(requested_layer)
    translated_pin = int(
        LayerFunctions.translateFrontBack(geometry, int(normalized_pin[1:]))
    )
    return f"{desired_family}{translated_pin}"


def resolve_pin_name_for_side(layer: str, side: str, pin_name: str) -> str:
    requested_side = _normalize_side(side)
    target_family = "A" if requested_side == "A" else "B"
    return _translate_pin_name_family(layer, pin_name, target_family)


def get_calibrated_pin_xy_for_side(
    layer: str, side: str, pin_name: str
) -> tuple[float, float]:
    resolved_pin = resolve_pin_name_for_side(layer, side, pin_name)
    return get_calibrated_pin_xy(layer, resolved_pin)


def _bottom_back_pin_to_a_pin(layer: str, back_pin: int) -> int:
    translated = _translate_pin_name_family(layer, f"B{int(back_pin)}", "A")
    return int(translated[1:])


def get_bottom_pin_options(layer: str, side: str) -> list[tuple[str, str]]:
    requested_layer = _normalize_layer(layer)
    requested_side = _normalize_side(side)
    if requested_layer not in UV_LAYERS:
        return []

    layout = get_uv_layout(requested_layer)
    back_start_pin, back_end_pin = layout.side_ranges["bottom"]
    if requested_side == "A":
        start_pin = _bottom_back_pin_to_a_pin(requested_layer, back_start_pin)
        end_pin = _bottom_back_pin_to_a_pin(requested_layer, back_end_pin)
        pin_family = "A"
    else:
        start_pin = back_start_pin
        end_pin = back_end_pin
        pin_family = "B"
    options = [
        (f"Bottom first ({pin_family}{start_pin})", f"{pin_family}{start_pin}"),
        (f"Bottom last ({pin_family}{end_pin})", f"{pin_family}{end_pin}"),
    ]
    LOGGER.debug(
        "Bottom pin options for layer=%s side=%s resolved to %s.",
        requested_layer,
        requested_side,
        [value for _label, value in options],
    )
    return options


def _default_laser_offset_store() -> dict[str, Any]:
    return {"A": None, "B": None}


def load_laser_offset_store() -> dict[str, Any]:
    return dict(_load_laser_offset_store_cached())


def save_laser_offset_store(store: dict[str, Any]) -> None:
    _atomic_write_text(
        LASER_OFFSET_PATH, json.dumps(store, indent=2, sort_keys=True) + "\n"
    )
    _load_laser_offset_store_cached.cache_clear()


def get_laser_offset(side: str) -> dict[str, Any] | None:
    return load_laser_offset_store().get(_normalize_side(side))


def capture_laser_offset(
    *,
    layer: str,
    side: str,
    pin_name: str,
    captured_stage_xy: tuple[float, float],
    captured_focus: int | None,
) -> dict[str, Any]:
    requested_layer = _normalize_layer(layer)
    requested_side = _normalize_side(side)
    resolved_pin = resolve_pin_name_for_side(requested_layer, requested_side, pin_name)
    pin_x, pin_y = get_calibrated_pin_xy(requested_layer, resolved_pin)
    stage_x = float(captured_stage_xy[0])
    stage_y = float(captured_stage_xy[1])
    entry = {
        "x": float(pin_x - stage_x),
        "y": float(pin_y - stage_y),
        "captured_layer": requested_layer,
        "captured_pin": resolved_pin,
        "captured_focus": None if captured_focus is None else int(captured_focus),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    store = dict(load_laser_offset_store())
    store[requested_side] = entry
    save_laser_offset_store(store)
    clear_layer_calibration_cache()
    return entry
