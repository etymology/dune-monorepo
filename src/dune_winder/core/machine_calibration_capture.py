"""Service for capturing spine calibration data during winding.

Records (gcode_label, gcode_line, calculated_xyz, recorded_xyz, head_config)
observations into a MachineCalibrationFile (PyO3). Each capture also
propagates the observed XYZ offset back into the live recipe's
lineOffsetOverrides for **every wrap** sharing the captured line index,
so the rest of the run targets the corrected position immediately.

Spec: specs/spine-calibration.allium, specs/uv-machine-calibration.allium.
"""

from __future__ import annotations

import os
import re

try:
    import dune_geometry

    _DUNE_GEOMETRY_AVAILABLE = True
except ImportError:
    _DUNE_GEOMETRY_AVAILABLE = False

from dune_winder.recipes.line_offset_overrides import (
    extract_line_key,
    normalize_line_key,
    parse_line_key,
)


_CAPTURE_FILE_NAME = "machineCalibrationCapture.json"
_SUPPORTED_LAYERS = ("U", "V")
_PIN_TOKEN_RE = re.compile(r"^([AB])(\d+)$")
_HEAD_CONFIG_LABELS = {
    "stage_a": "stage, Z extended to A (z<207)",
    "stage_b": "stage, Z extended to B (z>207)",
    "fixed": "fixed side latched, stage retracted",
    "retracted": "both heads retracted",
}


def _point_to_dict(point) -> dict:
    offset = point.offset()
    return {
        "capturedAt": point.captured_at,
        "gcodeLabel": point.gcode_label,
        "gcodeLine": point.gcode_line,
        "calculatedXyz": {
            "x": point.calculated_xyz.x,
            "y": point.calculated_xyz.y,
            "z": point.calculated_xyz.z,
        },
        "recordedXyz": {
            "x": point.recorded_xyz.x,
            "y": point.recorded_xyz.y,
            "z": point.recorded_xyz.z,
        },
        "offset": {"x": offset.x, "y": offset.y, "z": offset.z},
        "headConfig": point.head_config,
        "operator": point.operator,
    }


def _trace_pin_side(trace_pin):
    """Return 'A' or 'B' from a trace-pin entry, or None if it does not
    look like a UV pin token."""
    name = str((trace_pin or {}).get("pin", ""))
    match = _PIN_TOKEN_RE.match(name)
    if match is None:
        return None
    return match.group(1)


def _resolve_anchor_target_sides(trace):
    """Find anchor and target side letters from `trace["pins"]`. Returns
    `(anchor_side, target_side)` or `(None, None)` if the trace does not
    correspond to an `~anchorToTarget` move."""
    if not isinstance(trace, dict):
        return None, None
    pins = trace.get("pins")
    if not isinstance(pins, list):
        return None, None
    anchor_side = None
    target_side = None
    for entry in pins:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role")
        if role == "wrapAnchor" and anchor_side is None:
            anchor_side = _trace_pin_side(entry)
        elif role == "wrapTarget" and target_side is None:
            target_side = _trace_pin_side(entry)
    return anchor_side, target_side


def _classify_head_config(anchor_side, target_side):
    if anchor_side is None or target_side is None:
        return None
    if not _DUNE_GEOMETRY_AVAILABLE:
        return None
    try:
        return dune_geometry.head_config_from_sides(anchor_side, target_side)
    except Exception:
        return None


class MachineCaptureService:
    def __init__(self, process):
        self._process = process

    # -- file plumbing -----------------------------------------------------

    def _calibration_dir(self) -> str:
        workspace = getattr(self._process, "workspace", None)
        if workspace is not None and hasattr(workspace, "getPath"):
            return workspace.getPath()
        return self._process._workspaceCalibrationDirectory

    def _file_path(self) -> str:
        return os.path.join(self._calibration_dir(), _CAPTURE_FILE_NAME)

    def _machine_id(self) -> str:
        cal = getattr(self._process, "_machineCalibration", None)
        if cal is not None:
            name = getattr(cal, "_outputFileName", None)
            if name:
                return str(name)
        return "unknown"

    def _load_file(self):
        if not _DUNE_GEOMETRY_AVAILABLE:
            return None
        path = self._file_path()
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    return dune_geometry.MachineCalibrationFile.from_json(fh.read())
            except Exception:
                pass
        return dune_geometry.MachineCalibrationFile(self._machine_id())

    def _save_file(self, cal_file) -> None:
        path = self._file_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(cal_file.to_json())

    # -- recipe propagation ------------------------------------------------

    def _template_service(self, layer):
        if layer == "U":
            return getattr(self._process, "uTemplateRecipe", None)
        if layer == "V":
            return getattr(self._process, "vTemplateRecipe", None)
        return None

    def _wrap_count_for_layer(self, layer):
        service = self._template_service(layer)
        if service is None:
            return None
        wrap_count = getattr(service, "WRAP_COUNT", None)
        if wrap_count is None:
            wrap_count = getattr(type(service), "WRAP_COUNT", None)
        try:
            return int(wrap_count) if wrap_count is not None else None
        except (TypeError, ValueError):
            return None

    def _apply_xyz_offset_to_recipe(self, wrap_line_number, delta) -> None:
        """Add `delta = (dx, dy, dz)` to the offset of every wrap's line at
        index `wrap_line_number`, then regenerate the recipe file. No-op
        when the recipe layer is unsupported or the template service is
        missing."""
        layer = self._process.getRecipeLayer()
        if layer not in _SUPPORTED_LAYERS:
            return
        service = self._template_service(layer)
        if service is None:
            return
        wrap_count = self._wrap_count_for_layer(layer)
        if wrap_count is None:
            return

        delta_x = float(delta.x)
        delta_y = float(delta.y)
        delta_z = float(delta.z)

        current = dict(getattr(service, "_lineOffsetOverrides", {}))
        for wrap_number in range(1, wrap_count + 1):
            key = normalize_line_key(f"({wrap_number},{wrap_line_number})")
            entry = dict(current.get(key, {}))
            entry["x"] = float(entry.get("x", 0.0)) + delta_x
            entry["y"] = float(entry.get("y", 0.0)) + delta_y
            entry["z"] = float(entry.get("z", 0.0)) + delta_z
            current[key] = entry

        replace_result = service.replaceLineOffsetOverrides(current)
        if not (replace_result or {}).get("ok"):
            return
        script_variant = getattr(service, "_lastGeneratedScriptVariant", None)
        service.generateRecipeFile(scriptVariant=script_variant)

    # -- public API --------------------------------------------------------

    def get_state(self) -> dict:
        cal_file = self._load_file()
        last_trace = getattr(self._process, "getLastInstructionTrace", lambda: None)()
        is_active = getattr(self._process, "isGCodeExecutionActive", lambda: False)()

        capture_points = []
        if cal_file is not None:
            capture_points = [_point_to_dict(p) for p in cal_file.capture_points]

        anchor_side, target_side = _resolve_anchor_target_sides(last_trace)
        head_config = _classify_head_config(anchor_side, target_side)

        line_text = (
            (last_trace or {}).get("line", "") if isinstance(last_trace, dict) else ""
        )
        line_key = extract_line_key(line_text) if line_text else None

        propagation_scope = None
        if line_key is not None:
            try:
                _, wrap_line_number = parse_line_key(line_key)
            except Exception:
                wrap_line_number = None
            if wrap_line_number is not None:
                try:
                    layer = self._process.getRecipeLayer()
                except Exception:
                    layer = None
                wrap_count = self._wrap_count_for_layer(layer) if layer else None
                propagation_scope = {
                    "wrapLineNumber": int(wrap_line_number),
                    "wrapCount": int(wrap_count) if wrap_count is not None else None,
                    "layer": layer,
                }

        # Live machine position (always available even when not eligible
        # to record; the panel uses this for the live delta display).
        try:
            io = self._process._io
            current_xyz = {
                "x": float(io.xAxis.getPosition()),
                "y": float(io.yAxis.getPosition()),
                "z": float(io.zAxis.getPosition()),
            }
        except Exception:
            current_xyz = None

        can_record = (
            _DUNE_GEOMETRY_AVAILABLE
            and not is_active
            and last_trace is not None
            and line_key is not None
            and head_config is not None
            and propagation_scope is not None
            and propagation_scope.get("wrapCount") is not None
            and current_xyz is not None
        )

        return {
            "available": _DUNE_GEOMETRY_AVAILABLE,
            "captureCount": len(capture_points),
            "capturePoints": capture_points,
            "lastTrace": last_trace,
            "currentXyz": current_xyz,
            "headConfig": head_config,
            "headConfigLabel": _HEAD_CONFIG_LABELS.get(head_config)
            if head_config
            else None,
            "anchorSide": anchor_side,
            "targetSide": target_side,
            "propagationScope": propagation_scope,
            "canRecord": can_record,
        }

    def record_capture(self) -> dict:
        if not _DUNE_GEOMETRY_AVAILABLE:
            raise RuntimeError("dune_geometry is not available.")

        if getattr(self._process, "isGCodeExecutionActive", lambda: False)():
            raise RuntimeError("Cannot capture while gcode execution is active.")

        trace = getattr(self._process, "getLastInstructionTrace", lambda: None)()
        if trace is None:
            raise ValueError("No instruction trace available.")

        gcode_line = str(trace.get("line", ""))
        label = extract_line_key(gcode_line)
        if label is None:
            raise ValueError(
                "Last trace line has no (wrap,line) label; cannot capture."
            )

        anchor_side, target_side = _resolve_anchor_target_sides(trace)
        head_config = _classify_head_config(anchor_side, target_side)
        if head_config is None:
            raise ValueError(
                "Last trace is not an ~anchorToTarget move; head config "
                "cannot be classified."
            )

        resulting = trace.get("resultingTarget") or {}
        calc_x = resulting.get("x")
        calc_y = resulting.get("y")
        calc_z = resulting.get("pinZ")
        if None in (calc_x, calc_y, calc_z):
            raise ValueError("Trace does not contain a full calculated XYZ position.")

        io = self._process._io
        actual_x = float(io.xAxis.getPosition())
        actual_y = float(io.yAxis.getPosition())
        actual_z = float(io.zAxis.getPosition())

        now = str(self._process._systemTime.get())
        calc_vec = dune_geometry.Vec3(float(calc_x), float(calc_y), float(calc_z))
        recorded_vec = dune_geometry.Vec3(actual_x, actual_y, actual_z)
        point = dune_geometry.CalibrationPoint(
            captured_at=now,
            gcode_label=label,
            gcode_line=gcode_line,
            calculated_xyz=calc_vec,
            recorded_xyz=recorded_vec,
            head_config=head_config,
        )

        cal_file = self._load_file()
        cal_file.append_capture(point)
        self._save_file(cal_file)

        offset = point.offset()
        try:
            _, wrap_line_number = parse_line_key(label)
        except Exception:
            wrap_line_number = None
        if wrap_line_number is not None:
            self._apply_xyz_offset_to_recipe(int(wrap_line_number), offset)

        return _point_to_dict(point)
