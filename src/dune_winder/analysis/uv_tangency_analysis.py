from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from dune_winder.gcode.handler_base import GCodeHandlerBase
from dune_winder.gcode.runtime import GCodeExecutionError, execute_text_line
from dune_winder.library.Geometry.location import Location
from dune_winder.machine.calibration.layer import LayerCalibration
from dune_winder.machine.calibration.machine import MachineCalibration
from dune_winder.machine.head_compensation import WirePathModel
from dune_winder.recipes.u_template_gcode import render_u_template_lines
from dune_winder.recipes.v_template_gcode import render_v_template_lines


class UVTangencyAnalysisError(ValueError):
  pass


@dataclass(frozen=True)
class _SiteSpec:
  site_id: str
  comment_label: str
  offset_axis: str


@dataclass(frozen=True)
class _CalibrationPerturbationSpec:
  name: str
  description: str
  step: float
  a0: float = 0.0
  a1: float = 0.0
  a2: float = 0.0
  b0: float = 0.0
  b1: float = 0.0
  b2: float = 0.0
  front_a0: float = 0.0
  front_b0: float = 0.0
  back_a0: float = 0.0
  back_b0: float = 0.0


_RENDERED_LINE_NUMBER_RE = re.compile(r"^N(\d+)\b")
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_MACHINE_CALIBRATION_PATH = _REPO_ROOT / "dune_winder/config/machineCalibration.json"
_DEFAULT_LAYER_CALIBRATION_DIRECTORIES = (
  _REPO_ROOT / "dune_winder/config/APA",
  _REPO_ROOT / "config/APA",
)

_SITE_SPECS = {
  "U": (
    _SiteSpec("top_b_foot_end", "Top B corner - foot end", "x"),
    _SiteSpec("top_a_foot_end", "Top A corner - foot end", "x"),
    _SiteSpec("bottom_a_head_end", "Bottom A corner - head end", "x"),
    _SiteSpec("bottom_b_head_end", "Bottom B corner - head end, rewind", "x"),
    _SiteSpec("head_b_corner", "Head B corner", "y"),
    _SiteSpec("head_a_corner", "Head A corner, rewind", "y"),
    _SiteSpec("top_a_head_end", "Top A corner - head end", "x"),
    _SiteSpec("top_b_head_end", "Top B corner - head end", "x"),
    _SiteSpec("bottom_b_foot_end", "Bottom B corner - foot end", "x"),
    _SiteSpec("bottom_a_foot_end", "Bottom A corner - foot end, rewind", "x"),
    _SiteSpec("foot_a_corner", "Foot A corner", "y"),
    _SiteSpec("foot_b_corner", "Foot B corner, rewind", "y"),
  ),
  "V": (
    _SiteSpec("top_b_foot_end", "Top B corner - foot end", "x"),
    _SiteSpec("top_a_foot_end", "Top A corner - foot end", "x"),
    _SiteSpec("foot_a_corner", "Foot A corner", "y"),
    _SiteSpec("foot_b_corner", "Foot B corner", "y"),
    _SiteSpec("bottom_b_foot_end", "Bottom B corner - foot end", "x"),
    _SiteSpec("bottom_a_foot_end", "Bottom A corner - foot end", "x"),
    _SiteSpec("top_a_head_end", "Top A corner - head end", "x"),
    _SiteSpec("top_b_head_end", "Top B corner - head end", "x"),
    _SiteSpec("head_b_corner", "Head B corner", "y"),
    _SiteSpec("head_a_corner", "Head A corner", "y"),
    _SiteSpec("bottom_a_head_end", "Bottom A corner - head end", "x"),
    _SiteSpec("bottom_b_head_end", "Bottom B corner - head end", "x"),
  ),
}

_SENSITIVITY_SPECS = (
  _CalibrationPerturbationSpec(
    "global_x_shift",
    "Translate the full calibration map in +X.",
    1.0,
    a0=1.0,
  ),
  _CalibrationPerturbationSpec(
    "global_y_shift",
    "Translate the full calibration map in +Y.",
    1.0,
    b0=1.0,
  ),
  _CalibrationPerturbationSpec(
    "x_scale",
    "Apply x += c * x to the full calibration map.",
    0.001,
    a1=1.0,
  ),
  _CalibrationPerturbationSpec(
    "x_from_y_skew",
    "Apply x += c * y to the full calibration map.",
    0.001,
    a2=1.0,
  ),
  _CalibrationPerturbationSpec(
    "y_from_x_skew",
    "Apply y += c * x to the full calibration map.",
    0.001,
    b1=1.0,
  ),
  _CalibrationPerturbationSpec(
    "y_scale",
    "Apply y += c * y to the full calibration map.",
    0.001,
    b2=1.0,
  ),
  _CalibrationPerturbationSpec(
    "front_x_shift",
    "Translate only the front pin family in +X.",
    1.0,
    front_a0=1.0,
  ),
  _CalibrationPerturbationSpec(
    "front_y_shift",
    "Translate only the front pin family in +Y.",
    1.0,
    front_b0=1.0,
  ),
  _CalibrationPerturbationSpec(
    "back_x_shift",
    "Translate only the back pin family in +X.",
    1.0,
    back_a0=1.0,
  ),
  _CalibrationPerturbationSpec(
    "back_y_shift",
    "Translate only the back pin family in +Y.",
    1.0,
    back_b0=1.0,
  ),
)

AVAILABLE_SITE_IDS = tuple(
  spec.site_id for spec in _SITE_SPECS["U"] if spec.site_id in {site.site_id for site in _SITE_SPECS["V"]}
)
AVAILABLE_SENSITIVITY_IDS = tuple(spec.name for spec in _SENSITIVITY_SPECS)


def _normalize_layer(layer: str) -> str:
  normalized = str(layer).strip().upper()
  if normalized not in _SITE_SPECS:
    raise UVTangencyAnalysisError("Layer must be 'U' or 'V'.")
  return normalized


def _normalize_wrap(wrap: int) -> int:
  normalized = int(wrap)
  if normalized < 1:
    raise UVTangencyAnalysisError("Wrap must be >= 1.")
  return normalized


def _normalize_site_ids(layer: str, site_ids: Sequence[str] | None) -> list[str]:
  available = [spec.site_id for spec in _SITE_SPECS[layer]]
  if site_ids is None:
    return list(available)

  normalized: list[str] = []
  for site_id in site_ids:
    value = str(site_id).strip()
    if value not in available:
      raise UVTangencyAnalysisError(
        "Unknown site_id {!r} for layer {}.".format(value, layer)
      )
    if value not in normalized:
      normalized.append(value)
  return normalized


def _normalize_sensitivity_names(
  sensitivity_names: Sequence[str] | None,
) -> list[_CalibrationPerturbationSpec]:
  if sensitivity_names is None:
    return list(_SENSITIVITY_SPECS)

  by_name = {spec.name: spec for spec in _SENSITIVITY_SPECS}
  normalized: list[_CalibrationPerturbationSpec] = []
  for name in sensitivity_names:
    value = str(name).strip()
    if value not in by_name:
      raise UVTangencyAnalysisError(
        "Unknown sensitivity {!r}. Choices: {}.".format(
          value,
          ", ".join(AVAILABLE_SENSITIVITY_IDS),
        )
      )
    normalized.append(by_name[value])
  return normalized


def _default_layer_calibration_path(layer: str) -> Path:
  file_name = "{}_Calibration.json".format(layer)
  for directory in _DEFAULT_LAYER_CALIBRATION_DIRECTORIES:
    candidate = directory / file_name
    if candidate.exists():
      return candidate
  return _DEFAULT_LAYER_CALIBRATION_DIRECTORIES[0] / file_name


def _load_machine_calibration(path: str | Path | None) -> tuple[MachineCalibration, Path | None]:
  if path is None:
    resolved_path = _DEFAULT_MACHINE_CALIBRATION_PATH
  else:
    resolved_path = Path(path).expanduser().resolve()

  calibration = MachineCalibration(str(resolved_path.parent), resolved_path.name)
  calibration.load()
  return calibration, resolved_path


def _load_layer_calibration(
  layer: str,
  path: str | Path | None,
) -> tuple[LayerCalibration, Path | None]:
  if path is None:
    resolved_path = _default_layer_calibration_path(layer)
  else:
    resolved_path = Path(path).expanduser().resolve()

  calibration = LayerCalibration()
  calibration.load(str(resolved_path.parent), resolved_path.name)
  return calibration, resolved_path


def _render_lines(layer: str, script_variant: str = "default") -> list[str]:
  if layer == "U":
    if str(script_variant).strip().lower() not in ("", "default"):
      raise UVTangencyAnalysisError("The U layer does not support script variants.")
    return render_u_template_lines(strip_g113_params=True)

  return render_v_template_lines(
    strip_g113_params=True,
    script_variant=script_variant,
  )


def _site_specs_by_id(layer: str) -> dict[str, _SiteSpec]:
  return {spec.site_id: spec for spec in _SITE_SPECS[layer]}


def _find_site_line_numbers(
  layer: str,
  wrap: int,
  site_ids: Sequence[str],
  lines: Sequence[str],
) -> dict[str, tuple[int, str]]:
  marker = "({},".format(wrap)
  specs = _site_specs_by_id(layer)
  found: dict[str, tuple[int, str]] = {}

  for index, line in enumerate(lines, start=1):
    upper = line.upper()
    if marker not in upper:
      continue
    if "G109" not in upper or "G103" not in upper:
      continue

    for site_id in site_ids:
      spec = specs[site_id]
      if site_id in found:
        continue
      if spec.comment_label.upper() in upper:
        found[site_id] = (index, line)

  missing = [site_id for site_id in site_ids if site_id not in found]
  if missing:
    raise UVTangencyAnalysisError(
      "Could not find wrap {} sites {} in rendered {} recipe.".format(
        wrap,
        ", ".join(missing),
        layer,
      )
    )
  return found


def _rendered_line_number(line: str) -> int | None:
  match = _RENDERED_LINE_NUMBER_RE.match(str(line).strip())
  if match is None:
    return None
  return int(match.group(1))


def _location_to_dict(location: Location | None) -> dict[str, float] | None:
  if location is None:
    return None
  return {
    "x": float(location.x),
    "y": float(location.y),
    "z": float(location.z),
  }


def _delta_dict(
  first: Location | None,
  second: Location | None,
) -> dict[str, float] | None:
  if first is None or second is None:
    return None
  return {
    "x": float(first.x - second.x),
    "y": float(first.y - second.y),
    "z": float(first.z - second.z),
  }


def _initial_handler(
  machine_calibration: MachineCalibration,
  layer_calibration: LayerCalibration,
) -> GCodeHandlerBase:
  handler = GCodeHandlerBase(
    machine_calibration,
    WirePathModel(machine_calibration),
  )
  handler.useLayerCalibration(layer_calibration)
  handler._x = 0.0
  handler._y = 0.0
  handler._z = 0.0
  handler._headPosition = None
  return handler


def _resolve_head_z(handler: GCodeHandlerBase) -> float | None:
  head_position = getattr(handler, "_headPosition", None)
  if head_position is None or head_position == -1:
    return None
  return float(handler._getHeadPosition(head_position))


def _capture_site_state(
  site_spec: _SiteSpec,
  recipe_index: int,
  line_text: str,
  handler: GCodeHandlerBase,
) -> dict[str, object]:
  head_z = _resolve_head_z(handler)
  commanded = None
  actual = None
  delta = None

  if head_z is not None:
    commanded = Location(float(handler._x), float(handler._y), float(head_z))
    actual = handler._headCompensation.getActualLocation(commanded)
    delta = _delta_dict(actual, commanded)

  anchor_point = handler._headCompensation.anchorPoint()
  anchor_offset = handler._headCompensation.anchorOffset()
  effective_anchor = handler._headCompensation.compensatedAnchorPoint()

  return {
    "siteId": site_spec.site_id,
    "commentLabel": site_spec.comment_label,
    "offsetAxis": site_spec.offset_axis,
    "recipeIndex": int(recipe_index),
    "renderedLineNumber": _rendered_line_number(line_text),
    "lineText": str(line_text),
    "headPosition": getattr(handler, "_headPosition", None),
    "segmentPinZ": float(handler._z) if handler._z is not None else None,
    "commandedMachinePoint": _location_to_dict(commanded),
    "actualWirePoint": _location_to_dict(actual),
    "machineToActualDelta": delta,
    "anchorPoint": _location_to_dict(anchor_point),
    "anchorOffset": _location_to_dict(anchor_offset),
    "effectiveAnchorPoint": _location_to_dict(effective_anchor),
    "orientation": handler._headCompensation.orientation(),
  }


def _replay_site_reports(
  layer: str,
  wrap: int,
  site_ids: Sequence[str],
  lines: Sequence[str],
  machine_calibration: MachineCalibration,
  layer_calibration: LayerCalibration,
) -> dict[str, dict[str, object]]:
  site_line_numbers = _find_site_line_numbers(layer, wrap, site_ids, lines)
  max_index = max(recipe_index for recipe_index, _line in site_line_numbers.values())
  site_by_index = {
    recipe_index: _site_specs_by_id(layer)[site_id]
    for site_id, (recipe_index, _line) in site_line_numbers.items()
  }
  line_text_by_index = {
    recipe_index: line_text for _site_id, (recipe_index, line_text) in site_line_numbers.items()
  }

  handler = _initial_handler(machine_calibration, layer_calibration)
  site_reports: dict[str, dict[str, object]] = {}

  for recipe_index, line_text in enumerate(lines, start=1):
    if recipe_index > max_index:
      break
    try:
      execute_text_line(line_text, handler._callbacks.get)
    except GCodeExecutionError as exc:
      raise UVTangencyAnalysisError(
        "Failed to replay {} wrap {} at recipe index {}: {}.".format(
          layer,
          wrap,
          recipe_index,
          exc,
        )
      ) from exc

    handler._pending_actions = []
    handler._pending_stop_request = False

    site_spec = site_by_index.get(recipe_index)
    if site_spec is None:
      continue

    site_reports[site_spec.site_id] = _capture_site_state(
      site_spec,
      recipe_index,
      line_text_by_index[recipe_index],
      handler,
    )

  missing = [site_id for site_id in site_ids if site_id not in site_reports]
  if missing:
    raise UVTangencyAnalysisError(
      "Replay ended before capturing {}.".format(", ".join(missing))
    )
  return site_reports


def _apply_calibration_perturbation(
  layer_calibration: LayerCalibration,
  perturbation: _CalibrationPerturbationSpec,
  *,
  direction: float,
) -> LayerCalibration:
  updated = layer_calibration.copy()
  a0 = float(direction * perturbation.step * perturbation.a0)
  a1 = float(direction * perturbation.step * perturbation.a1)
  a2 = float(direction * perturbation.step * perturbation.a2)
  b0 = float(direction * perturbation.step * perturbation.b0)
  b1 = float(direction * perturbation.step * perturbation.b1)
  b2 = float(direction * perturbation.step * perturbation.b2)
  front_a0 = float(direction * perturbation.step * perturbation.front_a0)
  front_b0 = float(direction * perturbation.step * perturbation.front_b0)
  back_a0 = float(direction * perturbation.step * perturbation.back_a0)
  back_b0 = float(direction * perturbation.step * perturbation.back_b0)

  for pin_name in updated.getPinNames():
    location = updated.getPinLocation(pin_name)
    source_x = float(location.x)
    source_y = float(location.y)
    delta_x = a0 + (a1 * source_x) + (a2 * source_y)
    delta_y = b0 + (b1 * source_x) + (b2 * source_y)

    if pin_name.startswith("F"):
      delta_x += front_a0
      delta_y += front_b0
    elif pin_name.startswith("B"):
      delta_x += back_a0
      delta_y += back_b0

    location.x = source_x + delta_x
    location.y = source_y + delta_y

  return updated


def _point_component(report: dict[str, object], point_key: str, axis: str) -> float:
  point = report.get(point_key)
  if not isinstance(point, dict) or axis not in point:
    raise UVTangencyAnalysisError(
      "Report for {} is missing {}.".format(report.get("siteId"), point_key)
    )
  return float(point[axis])


def _attach_sensitivities(
  site_reports: dict[str, dict[str, object]],
  plus_reports: dict[str, dict[str, object]],
  minus_reports: dict[str, dict[str, object]],
  perturbation: _CalibrationPerturbationSpec,
) -> None:
  for site_id, site_report in site_reports.items():
    axis = str(site_report["offsetAxis"])
    actual_x_per_unit = (
      _point_component(plus_reports[site_id], "actualWirePoint", "x")
      - _point_component(minus_reports[site_id], "actualWirePoint", "x")
    ) / (2.0 * perturbation.step)
    actual_y_per_unit = (
      _point_component(plus_reports[site_id], "actualWirePoint", "y")
      - _point_component(minus_reports[site_id], "actualWirePoint", "y")
    ) / (2.0 * perturbation.step)
    actual_z_per_unit = (
      _point_component(plus_reports[site_id], "actualWirePoint", "z")
      - _point_component(minus_reports[site_id], "actualWirePoint", "z")
    ) / (2.0 * perturbation.step)
    actual_axis_per_unit = actual_x_per_unit if axis == "x" else actual_y_per_unit

    sensitivities = site_report.setdefault("sensitivities", {})
    sensitivities[perturbation.name] = {
      "description": perturbation.description,
      "step": float(perturbation.step),
      "actualXPerUnit": float(actual_x_per_unit),
      "actualYPerUnit": float(actual_y_per_unit),
      "actualZPerUnit": float(actual_z_per_unit),
      "actualAxisPerUnit": float(actual_axis_per_unit),
      "actualXDeltaForStep": float(actual_x_per_unit * perturbation.step),
      "actualYDeltaForStep": float(actual_y_per_unit * perturbation.step),
      "actualZDeltaForStep": float(actual_z_per_unit * perturbation.step),
      "actualAxisDeltaForStep": float(actual_axis_per_unit * perturbation.step),
    }


def build_uv_tangency_report(
  layer: str,
  wrap: int,
  *,
  site_ids: Sequence[str] | None = None,
  sensitivity_names: Sequence[str] | None = None,
  machine_calibration: MachineCalibration | None = None,
  machine_calibration_path: str | Path | None = None,
  layer_calibration: LayerCalibration | None = None,
  layer_calibration_path: str | Path | None = None,
  script_variant: str = "default",
) -> dict[str, object]:
  normalized_layer = _normalize_layer(layer)
  normalized_wrap = _normalize_wrap(wrap)
  normalized_site_ids = _normalize_site_ids(normalized_layer, site_ids)
  perturbations = _normalize_sensitivity_names(sensitivity_names)

  machine_path = None
  if machine_calibration is None:
    machine_calibration, machine_path = _load_machine_calibration(machine_calibration_path)
  elif machine_calibration_path is not None:
    machine_path = Path(machine_calibration_path).expanduser().resolve()

  calibration_path = None
  if layer_calibration is None:
    layer_calibration, calibration_path = _load_layer_calibration(
      normalized_layer,
      layer_calibration_path,
    )
  elif layer_calibration_path is not None:
    calibration_path = Path(layer_calibration_path).expanduser().resolve()

  lines = _render_lines(normalized_layer, script_variant=script_variant)
  site_reports = _replay_site_reports(
    normalized_layer,
    normalized_wrap,
    normalized_site_ids,
    lines,
    machine_calibration,
    layer_calibration,
  )

  for perturbation in perturbations:
    plus_calibration = _apply_calibration_perturbation(
      layer_calibration,
      perturbation,
      direction=1.0,
    )
    minus_calibration = _apply_calibration_perturbation(
      layer_calibration,
      perturbation,
      direction=-1.0,
    )
    plus_reports = _replay_site_reports(
      normalized_layer,
      normalized_wrap,
      normalized_site_ids,
      lines,
      machine_calibration,
      plus_calibration,
    )
    minus_reports = _replay_site_reports(
      normalized_layer,
      normalized_wrap,
      normalized_site_ids,
      lines,
      machine_calibration,
      minus_calibration,
    )
    _attach_sensitivities(site_reports, plus_reports, minus_reports, perturbation)

  ordered_sites = [site_reports[site_id] for site_id in normalized_site_ids]
  return {
    "layer": normalized_layer,
    "wrap": normalized_wrap,
    "scriptVariant": str(script_variant),
    "machineCalibrationPath": str(machine_path) if machine_path is not None else None,
    "layerCalibrationPath": str(calibration_path) if calibration_path is not None else None,
    "sites": ordered_sites,
  }


def compare_uv_tangency_reports(
  layer: str,
  wrap: int,
  *,
  compare_layer: str,
  compare_wrap: int | None = None,
  site_ids: Sequence[str] | None = None,
  sensitivity_names: Sequence[str] | None = None,
  machine_calibration: MachineCalibration | None = None,
  machine_calibration_path: str | Path | None = None,
  layer_calibration: LayerCalibration | None = None,
  layer_calibration_path: str | Path | None = None,
  script_variant: str = "default",
  compare_script_variant: str = "default",
  compare_machine_calibration: MachineCalibration | None = None,
  compare_machine_calibration_path: str | Path | None = None,
  compare_layer_calibration: LayerCalibration | None = None,
  compare_layer_calibration_path: str | Path | None = None,
) -> dict[str, object]:
  primary_machine = machine_calibration
  compare_machine = compare_machine_calibration
  if primary_machine is not None and compare_machine is None:
    compare_machine = primary_machine
  if compare_machine_calibration_path is None:
    compare_machine_calibration_path = machine_calibration_path

  return {
    "primary": build_uv_tangency_report(
      layer,
      wrap,
      site_ids=site_ids,
      sensitivity_names=sensitivity_names,
      machine_calibration=primary_machine,
      machine_calibration_path=machine_calibration_path,
      layer_calibration=layer_calibration,
      layer_calibration_path=layer_calibration_path,
      script_variant=script_variant,
    ),
    "comparison": build_uv_tangency_report(
      compare_layer,
      wrap if compare_wrap is None else compare_wrap,
      site_ids=site_ids,
      sensitivity_names=sensitivity_names,
      machine_calibration=compare_machine,
      machine_calibration_path=compare_machine_calibration_path,
      layer_calibration=compare_layer_calibration,
      layer_calibration_path=compare_layer_calibration_path,
      script_variant=compare_script_variant,
    ),
  }


def _build_argument_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description=(
      "Replay a rendered U/V recipe line and report commanded vs actual wire "
      "geometry together with calibration-frame sensitivities."
    )
  )
  parser.add_argument("--layer", required=True, choices=("U", "V"))
  parser.add_argument("--wrap", required=True, type=int)
  parser.add_argument(
    "--site",
    dest="site_ids",
    action="append",
    choices=AVAILABLE_SITE_IDS,
    help="Repeat to limit the report to selected site ids. Defaults to all sites.",
  )
  parser.add_argument(
    "--sensitivity",
    dest="sensitivity_names",
    action="append",
    choices=AVAILABLE_SENSITIVITY_IDS,
    help="Repeat to limit the sensitivity set. Defaults to all supported perturbations.",
  )
  parser.add_argument(
    "--script-variant",
    default="default",
    help="Recipe script variant. Only V currently supports non-default variants.",
  )
  parser.add_argument("--machine-calibration", default=None)
  parser.add_argument("--layer-calibration", default=None)
  parser.add_argument("--compare-layer", default=None, choices=("U", "V"))
  parser.add_argument("--compare-wrap", type=int, default=None)
  parser.add_argument("--compare-script-variant", default="default")
  parser.add_argument("--compare-machine-calibration", default=None)
  parser.add_argument("--compare-layer-calibration", default=None)
  parser.add_argument("--indent", type=int, default=2)
  return parser


def main(argv: Sequence[str] | None = None) -> int:
  parser = _build_argument_parser()
  args = parser.parse_args(argv)

  if args.compare_layer:
    payload = compare_uv_tangency_reports(
      args.layer,
      args.wrap,
      compare_layer=args.compare_layer,
      compare_wrap=args.compare_wrap,
      site_ids=args.site_ids,
      sensitivity_names=args.sensitivity_names,
      machine_calibration_path=args.machine_calibration,
      layer_calibration_path=args.layer_calibration,
      script_variant=args.script_variant,
      compare_script_variant=args.compare_script_variant,
      compare_machine_calibration_path=args.compare_machine_calibration,
      compare_layer_calibration_path=args.compare_layer_calibration,
    )
  else:
    payload = build_uv_tangency_report(
      args.layer,
      args.wrap,
      site_ids=args.site_ids,
      sensitivity_names=args.sensitivity_names,
      machine_calibration_path=args.machine_calibration,
      layer_calibration_path=args.layer_calibration,
      script_variant=args.script_variant,
    )

  print(json.dumps(payload, indent=args.indent, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
