from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
import re
from pathlib import Path

from dune_winder.gcode.handler_base import GCodeHandlerBase
from dune_winder.gcode.runtime import GCodeExecutionError, execute_text_line
from dune_winder.library.Geometry.location import Location
from dune_winder.machine.calibration.layer import LayerCalibration
from dune_winder.machine.calibration.machine import MachineCalibration
from dune_winder.machine.head_compensation import WirePathModel
from dune_winder.paths import REPO_ROOT
from dune_winder.recipes.u_template_gcode import render_u_template_lines
from dune_winder.recipes.v_template_gcode import render_v_template_lines


_PIN_NAME_RE = re.compile(r"^[BF]\d+$")
_RECIPE_SITE_RE = re.compile(
  r"G109\s+(P[BF]\d+)\s+P([A-Z]{2})\s+G103\s+(P[BF]\d+)\s+(P[BF]\d+).*?\(([^()]*)\)"
)
_DEFAULT_MACHINE_CALIBRATION_PATH = REPO_ROOT / "dune_winder" / "config" / "machineCalibration.json"
_DEFAULT_LAYER_CALIBRATION_DIRECTORIES = (
  REPO_ROOT / "config" / "APA",
  REPO_ROOT / "dune_winder" / "config" / "APA",
)
_AXIS_EPSILON = 1e-9


class UvHeadTargetError(ValueError):
  pass


@dataclass(frozen=True)
class Point2D:
  x: float
  y: float


@dataclass(frozen=True)
class Point3D:
  x: float
  y: float
  z: float


@dataclass(frozen=True)
class TransferBounds:
  left: float
  top: float
  right: float
  bottom: float


@dataclass(frozen=True)
class RecipeSite:
  anchor_pin: str
  orientation_token: str
  recipe_pair_pin_a: str
  recipe_pair_pin_b: str
  site_label: str
  side: str
  position: str


@dataclass(frozen=True)
class UvHeadTargetRequest:
  layer: str
  anchor_pin: str
  wrapped_pin: str
  head_z_mode: str


@dataclass(frozen=True)
class UvHeadTargetResult:
  request: UvHeadTargetRequest
  site_label: str
  site_side: str
  site_position: str
  wrap_side: str
  orientation_token: str
  anchor_pin_point: Point3D
  wrapped_pin_point: Point3D
  inferred_pair_pin: str
  inferred_pair_pin_point: Point3D
  midpoint_point: Point3D
  transfer_point: Point2D
  effective_anchor_point: Point3D
  final_head_point: Point3D
  final_wire_point: Point3D
  transfer_bounds: TransferBounds
  pin_radius: float
  head_arm_length: float
  head_roller_radius: float
  head_roller_gap: float
  validation_error: str | None = None


def _normalize_layer(layer: str) -> str:
  value = str(layer).strip().upper()
  if value not in {"U", "V"}:
    raise UvHeadTargetError("Layer must be 'U' or 'V'.")
  return value


def _normalize_head_z_mode(mode: str) -> str:
  value = str(mode).strip().lower()
  if value not in {"front", "back"}:
    raise UvHeadTargetError("Head Z mode must be 'front' or 'back'.")
  return value


def _normalize_pin_name(pin_name: str, label: str) -> str:
  value = str(pin_name).strip().upper()
  if not _PIN_NAME_RE.match(value):
    raise UvHeadTargetError(f"{label} must be a pin name like B1201 or F799.")
  return value


def _default_layer_calibration_path(layer: str) -> Path:
  file_name = f"{layer}_Calibration.json"
  for directory in _DEFAULT_LAYER_CALIBRATION_DIRECTORIES:
    candidate = directory / file_name
    if candidate.exists():
      return candidate
  return _DEFAULT_LAYER_CALIBRATION_DIRECTORIES[0] / file_name


def _load_machine_calibration(path: str | Path | None = None) -> MachineCalibration:
  resolved_path = Path(path) if path is not None else _DEFAULT_MACHINE_CALIBRATION_PATH
  calibration = MachineCalibration(str(resolved_path.parent), resolved_path.name)
  calibration.load()
  return calibration


def _load_layer_calibration(layer: str, path: str | Path | None = None) -> LayerCalibration:
  resolved_path = Path(path) if path is not None else _default_layer_calibration_path(layer)
  calibration = LayerCalibration(layer)
  calibration.load(str(resolved_path.parent), resolved_path.name, exceptionForMismatch=False)
  return calibration


def _location_to_point3(location: Location) -> Point3D:
  return Point3D(float(location.x), float(location.y), float(location.z))


def _wire_space_pin(layer_calibration: LayerCalibration, pin_name: str) -> Location:
  if not layer_calibration.getPinExists(pin_name):
    raise UvHeadTargetError(
      f"Pin {pin_name} is not present in {layer_calibration.getLayerNames()} calibration."
    )
  return layer_calibration.getPinLocation(pin_name).add(layer_calibration.offset)


def wrap_side(layer, side, position):
  l = layer.upper() == "V"
  s = side.upper() == "A"

  if position.lower() in ("top", "bottom"):
    p = position.lower() == "top"
    return ("-" if (l ^ s ^ p) else "+") + "x"
  if position.lower() in ("head", "foot"):
    p = position.lower() == "foot"
    return ("-" if (l ^ s ^ p) else "+") + "y"
  raise ValueError(f"Unsupported position {position!r}.")


def _parse_site_label(site_label: str) -> tuple[str, str]:
  label = str(site_label).strip().lower()
  if " a " in f" {label} ":
    side = "A"
  elif " b " in f" {label} ":
    side = "B"
  else:
    raise UvHeadTargetError(f"Could not determine site side from {site_label!r}.")

  for position in ("top", "bottom", "head", "foot"):
    if position in label:
      return (side, position)
  raise UvHeadTargetError(f"Could not determine site position from {site_label!r}.")


def _strip_p_prefix(pin_name: str) -> str:
  value = str(pin_name).strip().upper()
  if value.startswith("P"):
    return value[1:]
  return value


def _render_lines_for_layer(layer: str) -> list[str]:
  if layer == "U":
    return render_u_template_lines(strip_g113_params=True)
  return render_v_template_lines(strip_g113_params=True)


@lru_cache(maxsize=2)
def _recipe_sites_by_anchor(layer: str) -> dict[str, list[RecipeSite]]:
  result: dict[str, list[RecipeSite]] = {}
  for line in _render_lines_for_layer(layer):
    match = _RECIPE_SITE_RE.search(line)
    if match is None:
      continue
    anchor_pin, orientation_token, pair_pin_a, pair_pin_b, site_label = match.groups()
    anchor_pin = _strip_p_prefix(anchor_pin)
    pair_pin_a = _strip_p_prefix(pair_pin_a)
    pair_pin_b = _strip_p_prefix(pair_pin_b)
    side, position = _parse_site_label(site_label)
    candidate = RecipeSite(
      anchor_pin=anchor_pin,
      orientation_token=orientation_token,
      recipe_pair_pin_a=pair_pin_a,
      recipe_pair_pin_b=pair_pin_b,
      site_label=site_label,
      side=side,
      position=position,
    )
    result.setdefault(anchor_pin, []).append(candidate)
  return result


def _infer_pair_pin_from_wrap_side(
  layer_calibration: LayerCalibration,
  wrapped_pin: str,
  wrap_side_value: str,
) -> str:
  wrapped_location = _wire_space_pin(layer_calibration, wrapped_pin)
  same_face_pins = [
    pin_name
    for pin_name in layer_calibration.getPinNames()
    if pin_name.startswith(wrapped_pin[0]) and pin_name != wrapped_pin
  ]
  if not same_face_pins:
    raise UvHeadTargetError(f"No same-face candidate pins found for {wrapped_pin}.")

  sign = 1.0 if wrap_side_value.startswith("+") else -1.0
  axis = wrap_side_value[-1].lower()
  best_pin = None
  best_score = None

  for pin_name in same_face_pins:
    location = _wire_space_pin(layer_calibration, pin_name)
    delta_x = float(location.x - wrapped_location.x)
    delta_y = float(location.y - wrapped_location.y)
    axis_delta = delta_x if axis == "x" else delta_y
    perpendicular = abs(delta_y) if axis == "x" else abs(delta_x)
    signed_axis = sign * axis_delta
    if signed_axis <= _AXIS_EPSILON:
      continue
    score = (perpendicular, signed_axis)
    if best_score is None or score < best_score:
      best_score = score
      best_pin = pin_name

  if best_pin is None:
    raise UvHeadTargetError(
      f"Could not infer the second G103 pin from wrapped pin {wrapped_pin} and wrap side {wrap_side_value}."
    )

  return best_pin


def _resolve_site_wrapped_pin(
  layer: str,
  layer_calibration: LayerCalibration,
  site: RecipeSite,
) -> str:
  wrap_side_value = wrap_side(layer, site.side, site.position)
  matches = []
  for wrapped_pin, other_pin in (
    (site.recipe_pair_pin_a, site.recipe_pair_pin_b),
    (site.recipe_pair_pin_b, site.recipe_pair_pin_a),
  ):
    try:
      inferred = _infer_pair_pin_from_wrap_side(layer_calibration, wrapped_pin, wrap_side_value)
    except UvHeadTargetError:
      continue
    if inferred == other_pin:
      matches.append(wrapped_pin)
  if len(matches) != 1:
    raise UvHeadTargetError(
      f"Could not resolve the wrapped pin for site {site.site_label!r} on layer {layer}."
    )
  return matches[0]


def _lookup_recipe_site(
  layer: str,
  layer_calibration: LayerCalibration,
  anchor_pin: str,
  wrapped_pin: str,
) -> RecipeSite:
  matches = []
  for site in _recipe_sites_by_anchor(layer).get(anchor_pin, ()):
    resolved_wrapped_pin = _resolve_site_wrapped_pin(layer, layer_calibration, site)
    if resolved_wrapped_pin == wrapped_pin:
      matches.append(site)
  if len(matches) != 1:
    raise UvHeadTargetError(
      f"No U/V recipe site matches anchor pin {anchor_pin} and wrapped pin {wrapped_pin}."
    )
  return matches[0]


def _initial_handler(
  machine_calibration: MachineCalibration,
  layer_calibration: LayerCalibration,
) -> GCodeHandlerBase:
  handler = GCodeHandlerBase(machine_calibration, WirePathModel(machine_calibration))
  handler.useLayerCalibration(layer_calibration)
  handler._x = 0.0
  handler._y = 0.0
  handler._z = 0.0
  handler._headPosition = None
  return handler


def _execute_line(handler: GCodeHandlerBase, line: str) -> None:
  try:
    execute_text_line(line, handler._callbacks.get)
  except GCodeExecutionError as exc:
    raise UvHeadTargetError(f"Failed to execute {line!r}: {exc}.") from exc


def compute_uv_head_target(
  request: UvHeadTargetRequest,
  *,
  machine_calibration_path: str | Path | None = None,
  layer_calibration_path: str | Path | None = None,
) -> UvHeadTargetResult:
  normalized_request = UvHeadTargetRequest(
    layer=_normalize_layer(request.layer),
    anchor_pin=_normalize_pin_name(request.anchor_pin, "Anchor pin"),
    wrapped_pin=_normalize_pin_name(request.wrapped_pin, "Wrapped pin"),
    head_z_mode=_normalize_head_z_mode(request.head_z_mode),
  )
  machine_calibration = _load_machine_calibration(machine_calibration_path)
  layer_calibration = _load_layer_calibration(
    normalized_request.layer,
    layer_calibration_path,
  )
  anchor_point = _wire_space_pin(layer_calibration, normalized_request.anchor_pin)
  wrapped_point = _wire_space_pin(layer_calibration, normalized_request.wrapped_pin)

  recipe_site = _lookup_recipe_site(
    normalized_request.layer,
    layer_calibration,
    normalized_request.anchor_pin,
    normalized_request.wrapped_pin,
  )
  wrap_side_value = wrap_side(
    normalized_request.layer,
    recipe_site.side,
    recipe_site.position,
  )
  inferred_pair_pin = _infer_pair_pin_from_wrap_side(
    layer_calibration,
    normalized_request.wrapped_pin,
    wrap_side_value,
  )
  inferred_pair_point = _wire_space_pin(layer_calibration, inferred_pair_pin)

  head_position = 1 if normalized_request.head_z_mode == "front" else 2
  handler = _initial_handler(machine_calibration, layer_calibration)
  _execute_line(handler, f"G106 P{head_position}")
  _execute_line(handler, f"G109 P{normalized_request.anchor_pin} P{recipe_site.orientation_token}")
  _execute_line(
    handler,
    f"G103 P{normalized_request.wrapped_pin} P{inferred_pair_pin} PXY",
  )
  midpoint_point = Point3D(float(handler._x), float(handler._y), float(handler._z))
  _execute_line(handler, "G102")
  transfer_point = Point2D(float(handler._x), float(handler._y))
  effective_anchor = handler._headCompensation.compensatedAnchorPoint()
  _execute_line(handler, "G108")
  head_z = float(handler._getHeadPosition(head_position))
  final_head_location = Location(float(handler._x), float(handler._y), head_z)
  final_wire_location = handler._headCompensation.getActualLocation(final_head_location)

  return UvHeadTargetResult(
    request=normalized_request,
    site_label=recipe_site.site_label,
    site_side=recipe_site.side,
    site_position=recipe_site.position,
    wrap_side=wrap_side_value,
    orientation_token=recipe_site.orientation_token,
    anchor_pin_point=_location_to_point3(anchor_point),
    wrapped_pin_point=_location_to_point3(wrapped_point),
    inferred_pair_pin=inferred_pair_pin,
    inferred_pair_pin_point=_location_to_point3(inferred_pair_point),
    midpoint_point=midpoint_point,
    transfer_point=transfer_point,
    effective_anchor_point=_location_to_point3(effective_anchor),
    final_head_point=_location_to_point3(final_head_location),
    final_wire_point=_location_to_point3(final_wire_location),
    transfer_bounds=TransferBounds(
      left=float(machine_calibration.transferLeft),
      top=float(machine_calibration.transferTop),
      right=float(machine_calibration.transferRight),
      bottom=float(machine_calibration.transferBottom),
    ),
    pin_radius=float(machine_calibration.pinDiameter) / 2.0,
    head_arm_length=float(machine_calibration.headArmLength),
    head_roller_radius=float(machine_calibration.headRollerRadius),
    head_roller_gap=float(machine_calibration.headRollerGap),
    validation_error=None,
  )


__all__ = [
  "Point2D",
  "Point3D",
  "RecipeSite",
  "TransferBounds",
  "UvHeadTargetError",
  "UvHeadTargetRequest",
  "UvHeadTargetResult",
  "compute_uv_head_target",
  "wrap_side",
]
