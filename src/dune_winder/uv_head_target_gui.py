from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
import tkinter as tk

from dune_winder.machine.geometry.uv_tangency import (
  Point2D,
  RectBounds,
  UvHeadTargetError,
  UvTangentViewRequest,
  UvTangentViewResult,
  compute_uv_tangent_view,
  iter_uv_wrap_primary_sites,
  matches_tangent_sides,
  resolve_wrapped_pin_from_g103_pair,
)


CANVAS_WIDTH = 900
CANVAS_HEIGHT = 700
ZOOM_CANVAS_WIDTH = 430
ZOOM_CANVAS_HEIGHT = 230
CANVAS_PADDING = 40.0


def _format_tangent_sides(tangent_sides_value: tuple[str, str] | None) -> str:
  if tangent_sides_value is None:
    return "n/a"
  x_side, y_side = tangent_sides_value
  return f"x={x_side}, y={y_side}"


@dataclass(frozen=True)
class _RecipeSegment:
  layer: str
  wrap_number: int
  segment_number: int
  wrap_line_number: int
  anchor_pin: str
  orientation_token: str
  wrapped_pin: str
  adjacent_pin: str
  g103_pin_a: str
  g103_pin_b: str


@lru_cache(maxsize=2)
def _segments_for_layer(layer: str) -> tuple[_RecipeSegment, ...]:
  layer_value = str(layer).strip().upper()
  if layer_value not in {"U", "V"}:
    raise UvHeadTargetError("Layer must be 'U' or 'V'.")

  raw_segments = iter_uv_wrap_primary_sites(layer_value)
  segments: list[_RecipeSegment] = []
  current_wrap: int | None = None
  current_segment_number = 0
  for site in raw_segments:
    if current_wrap != site.wrap_number:
      current_wrap = site.wrap_number
      current_segment_number = 0
    resolution = resolve_wrapped_pin_from_g103_pair(
      layer_value,
      site.g103_pin_a,
      site.g103_pin_b,
      preferred_wrapped_pin=site.g103_pin_a,
    )

    current_segment_number += 1
    segments.append(
      _RecipeSegment(
        layer=layer_value,
        wrap_number=current_wrap,
        segment_number=current_segment_number,
        wrap_line_number=site.wrap_line_number,
        anchor_pin=site.anchor_pin,
        orientation_token=site.orientation_token,
        wrapped_pin=resolution.wrapped_pin,
        adjacent_pin=resolution.adjacent_pin,
        g103_pin_a=site.g103_pin_a,
        g103_pin_b=site.g103_pin_b,
      )
    )

  return tuple(segments)


@lru_cache(maxsize=2)
def _segment_index_by_wrap_segment(layer: str) -> dict[tuple[int, int], int]:
  index: dict[tuple[int, int], int] = {}
  for global_index, segment in enumerate(_segments_for_layer(layer)):
    index[(segment.wrap_number, segment.segment_number)] = global_index
  return index


@dataclass
class _FormState:
  mode_var: tk.StringVar
  layer_var: tk.StringVar
  pin_a_var: tk.StringVar
  pin_b_var: tk.StringVar
  wrap_var: tk.StringVar
  segment_var: tk.StringVar
  derived_pins_var: tk.StringVar
  error_var: tk.StringVar
  summary_var: tk.StringVar
  canvas: tk.Canvas
  pin_a_zoom_canvas: tk.Canvas
  pin_b_zoom_canvas: tk.Canvas
  outbound_zoom_canvas: tk.Canvas


def build_request_from_form(form: _FormState) -> UvTangentViewRequest:
  mode = str(form.mode_var.get()).strip().lower()
  layer = form.layer_var.get()
  if mode == "wrap/segment":
    try:
      wrap_number = int(str(form.wrap_var.get()).strip())
      segment_number = int(str(form.segment_var.get()).strip())
    except ValueError as exc:
      raise UvHeadTargetError("Wrap # and Segment # must be integers.") from exc

    segments = _segments_for_layer(layer)
    index = _segment_index_by_wrap_segment(layer).get((wrap_number, segment_number))
    if index is None:
      raise UvHeadTargetError(
        f"No primary site found for wrap {wrap_number}, segment {segment_number}."
      )
    segment = segments[index]
    return UvTangentViewRequest(
      layer=layer,
      pin_a=segment.anchor_pin,
      pin_b=segment.wrapped_pin,
      g103_adjacent_pin=segment.adjacent_pin,
    )

  return UvTangentViewRequest(
    layer=layer, pin_a=form.pin_a_var.get(), pin_b=form.pin_b_var.get()
  )


def format_result_summary(result: UvTangentViewResult) -> str:
  if result.alternating_plane is not None:
    projected_projection = (
      f"({result.alternating_g109_projection.x:.3f}, {result.alternating_g109_projection.y:.3f})"
      f" -> ({result.alternating_g103_projection.x:.3f}, {result.alternating_g103_projection.y:.3f})"
      if result.alternating_g109_projection is not None
      and result.alternating_g103_projection is not None
      else "unavailable"
    )
    wrap_line = (
      f"({result.alternating_wrap_line_start.x:.3f}, {result.alternating_wrap_line_start.y:.3f})"
      f" -> ({result.alternating_wrap_line_end.x:.3f}, {result.alternating_wrap_line_end.y:.3f})"
      if result.alternating_wrap_line_start is not None
      and result.alternating_wrap_line_end is not None
      else "unavailable"
    )
    return "\n".join(
      (
        f"Layer: {result.request.layer}",
        f"View plane: {result.alternating_plane}",
        f"Alternating face: {result.alternating_face}",
        f"Anchor pin {result.request.pin_a}: ({result.pin_a_point.x:.3f}, {result.pin_a_point.y:.3f}, {result.pin_a_point.z:.3f})",
        f"Target pin {result.request.pin_b}: ({result.pin_b_point.x:.3f}, {result.pin_b_point.y:.3f}, {result.pin_b_point.z:.3f})",
        f"Anchor tangent sides: {_format_tangent_sides(result.anchor_tangent_sides)}",
        f"Wrapped side/face: {result.wrapped_side} / {result.wrapped_face}",
        f"Wrapped tangent sides: {_format_tangent_sides(result.wrap_sides)}",
        f"Runtime orientation: {result.runtime_orientation_token or 'n/a'}",
        f"G109-G103 projection: {projected_projection}",
        f"Projected wrap line: {wrap_line}",
        f"Machine zRetracted/zExtended: {result.z_retracted:.3f} / {result.z_extended:.3f}",
        f"Selection rule: {result.tangent_selection_rule}",
      )
    )

  line_equation = result.line_equation
  if line_equation.is_vertical:
    line_summary = f"x = {line_equation.intercept:.3f}"
  else:
    line_summary = f"y = {line_equation.slope:.6f}x + {line_equation.intercept:.3f}"
  runtime_summary = "Runtime comparison: unavailable"
  if result.runtime_line_equation is not None:
    runtime_summary = "Runtime comparison: " + (
      "same line" if result.matches_runtime_line else "different lines"
    )
  runtime_orientation = result.runtime_orientation_token or "n/a"
  target_delta = None
  if result.runtime_target_point is not None:
    target_delta = Point2D(
      result.outbound_intercept.x - result.runtime_target_point.x,
      result.outbound_intercept.y - result.runtime_target_point.y,
    )
  return "\n".join(
    (
      f"Layer: {result.request.layer}",
      f"Anchor pin {result.request.pin_a}: ({result.pin_a_point.x:.3f}, {result.pin_a_point.y:.3f})",
      f"Target pin {result.request.pin_b}: ({result.pin_b_point.x:.3f}, {result.pin_b_point.y:.3f})",
      f"Tangent A: ({result.tangent_point_a.x:.3f}, {result.tangent_point_a.y:.3f})",
      f"Tangent B: ({result.tangent_point_b.x:.3f}, {result.tangent_point_b.y:.3f})",
      f"Line: {line_summary}",
      (
        "Outbound transfer intercept: "
        f"({result.outbound_intercept.x:.3f}, {result.outbound_intercept.y:.3f})"
      ),
      (
        "G108 target: "
        + (
          f"({result.runtime_target_point.x:.3f}, {result.runtime_target_point.y:.3f})"
          if result.runtime_target_point is not None
          else "unavailable"
        )
      ),
      (
        "Outbound minus G108 target: "
        + (
          f"({target_delta.x:.3f}, {target_delta.y:.3f})"
          if target_delta is not None
          else "unavailable"
        )
      ),
      f"Wrapped side/face: {result.wrapped_side} / {result.wrapped_face}",
      f"Wrapped tangent sides: {_format_tangent_sides(result.wrap_sides)}",
      f"Runtime orientation: {runtime_orientation}",
      runtime_summary,
      f"Selection rule: {result.tangent_selection_rule}",
    )
  )


def _is_alternating_result(result: UvTangentViewResult) -> bool:
  return result.alternating_plane is not None


def _collect_draw_points(result: UvTangentViewResult) -> list[Point2D]:
  bounds = result.transfer_bounds
  apa = result.apa_bounds
  points = [
    Point2D(result.pin_a_point.x, result.pin_a_point.y),
    Point2D(result.pin_b_point.x, result.pin_b_point.y),
    result.tangent_point_a,
    result.tangent_point_b,
    result.clipped_segment_start,
    result.clipped_segment_end,
    result.outbound_intercept,
    Point2D(bounds.left, bounds.top),
    Point2D(bounds.left, bounds.bottom),
    Point2D(bounds.right, bounds.top),
    Point2D(bounds.right, bounds.bottom),
    Point2D(apa.left, apa.top),
    Point2D(apa.left, apa.bottom),
    Point2D(apa.right, apa.top),
    Point2D(apa.right, apa.bottom),
  ]
  optional_points = (
    result.runtime_tangent_point,
    result.runtime_target_point,
    result.runtime_clipped_segment_start,
    result.runtime_clipped_segment_end,
    result.runtime_outbound_intercept,
    result.arm_head_center,
    result.arm_left_endpoint,
    result.arm_right_endpoint,
  ) + tuple(result.roller_centers)
  for point in optional_points:
    if point is not None:
      points.append(point)
  return points


def _build_canvas_transform(result: UvTangentViewResult, width: float, height: float):
  points = _collect_draw_points(result)
  xs = [point.x for point in points]
  ys = [point.y for point in points]
  min_x = min(xs) - result.pin_radius - CANVAS_PADDING
  max_x = max(xs) + result.pin_radius + CANVAS_PADDING
  min_y = min(ys) - result.pin_radius - CANVAS_PADDING
  max_y = max(ys) + result.pin_radius + CANVAS_PADDING
  span_x = max(max_x - min_x, 1.0)
  span_y = max(max_y - min_y, 1.0)
  scale = min(
    max(width - (2.0 * CANVAS_PADDING), 1.0) / span_x,
    max(height - (2.0 * CANVAS_PADDING), 1.0) / span_y,
  )
  x_right = width - CANVAS_PADDING
  y_top = CANVAS_PADDING

  def project(point: Point2D) -> tuple[float, float]:
    # Mirror X so larger values plot to the left and smaller values to the right.
    x = x_right - ((point.x - min_x) * scale)
    y = y_top + ((max_y - point.y) * scale)
    return (x, y)

  return project, scale


def _fit_bounds(
  points: list[Point2D], padding_x: float, padding_y: float
) -> RectBounds:
  xs = [point.x for point in points]
  ys = [point.y for point in points]
  return RectBounds(
    left=min(xs) - padding_x,
    top=max(ys) + padding_y,
    right=max(xs) + padding_x,
    bottom=min(ys) - padding_y,
  )


def _draw_axis_arrows(
  canvas: tk.Canvas,
  project,
  bounds: RectBounds,
) -> None:
  corner_x, corner_y = project(Point2D(bounds.left, bounds.bottom))
  origin_x = corner_x - 55.0
  origin_y = corner_y + 40.0
  axis_length = 45.0
  canvas.create_line(
    origin_x,
    origin_y,
    origin_x - axis_length,
    origin_y,
    fill="#475569",
    width=2,
    arrow="last",
  )
  canvas.create_text(
    origin_x - axis_length - 10.0, origin_y, text="+x", fill="#475569", anchor="e"
  )
  canvas.create_line(
    origin_x,
    origin_y,
    origin_x,
    origin_y - axis_length,
    fill="#475569",
    width=2,
    arrow="last",
  )
  canvas.create_text(
    origin_x, origin_y - axis_length - 10.0, text="+y", fill="#475569", anchor="s"
  )


def _draw_labeled_point(
  canvas: tk.Canvas,
  project,
  point: Point2D,
  *,
  label: str,
  color: str,
  radius: float = 4.0,
  text_dx: float = 8.0,
  text_dy: float = -10.0,
  text_anchor: str = "w",
) -> None:
  x, y = project(point)
  canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline=color)
  canvas.create_text(
    x + text_dx, y + text_dy, text=label, fill=color, anchor=text_anchor
  )


def _draw_bounds(
  canvas: tk.Canvas,
  project,
  bounds: RectBounds,
  *,
  outline: str,
  dash: tuple[int, int] | None = None,
) -> None:
  left_top = project(Point2D(bounds.left, bounds.top))
  right_bottom = project(Point2D(bounds.right, bounds.bottom))
  canvas.create_rectangle(
    left_top[0],
    left_top[1],
    right_bottom[0],
    right_bottom[1],
    outline=outline,
    dash=dash,
  )


def _pin_sort_key(pin_name: str) -> tuple[str, int]:
  return (pin_name[:1], int(pin_name[1:]))


def _neighbor_points(
  result: UvTangentViewResult,
  pin_name: str,
) -> tuple[tuple[str, Point2D], tuple[str, Point2D] | None, tuple[str, Point2D] | None]:
  points_by_name = dict(result.apa_pin_points_by_name)
  pin_family = pin_name[:1]
  same_family = sorted(
    (
      (candidate_name, candidate_point)
      for candidate_name, candidate_point in result.apa_pin_points_by_name
      if candidate_name.startswith(pin_family)
    ),
    key=lambda item: _pin_sort_key(item[0]),
  )
  target_index = next(
    index for index, item in enumerate(same_family) if item[0] == pin_name
  )
  previous_item = same_family[target_index - 1] if target_index > 0 else None
  next_item = (
    same_family[target_index + 1] if target_index < len(same_family) - 1 else None
  )
  return ((pin_name, points_by_name[pin_name]), previous_item, next_item)


def _clip_line_to_bounds(
  line_point: Point2D,
  line_direction: Point2D,
  bounds: RectBounds,
) -> tuple[Point2D, Point2D] | None:
  dx = line_direction.x
  dy = line_direction.y
  if abs(dx) <= 1e-9 and abs(dy) <= 1e-9:
    return None

  candidates: list[tuple[float, Point2D]] = []

  def add_candidate(parameter: float, x_value: float, y_value: float) -> None:
    if x_value < bounds.left - 1e-9 or x_value > bounds.right + 1e-9:
      return
    if y_value < bounds.bottom - 1e-9 or y_value > bounds.top + 1e-9:
      return
    point = Point2D(x_value, y_value)
    for existing_parameter, existing_point in candidates:
      if abs(existing_parameter - parameter) <= 1e-8 or (
        abs(existing_point.x - point.x) <= 1e-8
        and abs(existing_point.y - point.y) <= 1e-8
      ):
        return
    candidates.append((parameter, point))

  if abs(dx) > 1e-9:
    for x_value in (bounds.left, bounds.right):
      parameter = (x_value - line_point.x) / dx
      add_candidate(parameter, x_value, line_point.y + (parameter * dy))
  if abs(dy) > 1e-9:
    for y_value in (bounds.bottom, bounds.top):
      parameter = (y_value - line_point.y) / dy
      add_candidate(parameter, line_point.x + (parameter * dx), y_value)

  if len(candidates) < 2:
    return None
  candidates.sort(key=lambda item: item[0])
  return (candidates[0][1], candidates[-1][1])


def _draw_local_axes(
  canvas: tk.Canvas, *, width: float, height: float, x_direction: float
) -> None:
  origin_x = 55.0
  origin_y = height - 30.0
  axis_length = 32.0
  x_tip_x = origin_x - axis_length
  canvas.create_line(
    origin_x,
    origin_y,
    x_tip_x,
    origin_y,
    fill="#475569",
    width=2,
    arrow="last",
  )
  canvas.create_text(x_tip_x - 8.0, origin_y, text="+x", fill="#475569", anchor="e")
  canvas.create_text(origin_x + axis_length + 8.0, origin_y, text="-x", fill="#475569", anchor="w")
  canvas.create_line(
    origin_x,
    origin_y,
    origin_x,
    origin_y - axis_length,
    fill="#475569",
    width=2,
    arrow="last",
  )
  canvas.create_text(
    origin_x, origin_y - axis_length - 8.0, text="+y", fill="#475569", anchor="s"
  )


def _draw_clipped_line(
  canvas: tk.Canvas,
  project,
  segment: tuple[Point2D, Point2D] | None,
  *,
  fill: str,
  width: int = 2,
  dash: tuple[int, int] | None = None,
) -> None:
  if segment is None:
    return
  start_xy = project(segment[0])
  end_xy = project(segment[1])
  canvas.create_line(
    start_xy[0], start_xy[1], end_xy[0], end_xy[1], fill=fill, width=width, dash=dash
  )


def _runtime_anchor_tangent_point(result: UvTangentViewResult) -> Point2D | None:
  """
  Build a tangent-from-anchor-to-runtime-target line, selecting the tangent point
  on the side of the anchor requested by the anchor pin's tangent-side rule.
  """
  if result.runtime_target_point is None:
    return None

  center = Point2D(result.pin_a_point.x, result.pin_a_point.y)
  target = result.runtime_target_point
  vx = target.x - center.x
  vy = target.y - center.y
  distance = math.hypot(vx, vy)
  if distance <= result.pin_radius + 1e-9:
    return None

  base_angle = math.atan2(vy, vx)
  offset_angle = math.acos(min(max(result.pin_radius / distance, -1.0), 1.0))

  def point_at(angle: float) -> Point2D:
    return Point2D(
      center.x + (result.pin_radius * math.cos(angle)),
      center.y + (result.pin_radius * math.sin(angle)),
    )

  candidate_a = point_at(base_angle + offset_angle)
  candidate_b = point_at(base_angle - offset_angle)

  candidate_a_matches = matches_tangent_sides(
    candidate_a,
    center,
    result.anchor_tangent_sides,
  )
  candidate_b_matches = matches_tangent_sides(
    candidate_b,
    center,
    result.anchor_tangent_sides,
  )
  if candidate_a_matches and not candidate_b_matches:
    return candidate_a
  if candidate_b_matches and not candidate_a_matches:
    return candidate_b

  # Fallback: choose whichever tangent point is closer to the selected anchor tangent point.
  sel = result.tangent_point_a
  da = math.hypot(candidate_a.x - sel.x, candidate_a.y - sel.y)
  db = math.hypot(candidate_b.x - sel.x, candidate_b.y - sel.y)
  return candidate_a if da <= db else candidate_b


def _draw_touch_zoom(
  canvas: tk.Canvas,
  result: UvTangentViewResult,
  *,
  pin_name: str,
  pin_point: Point2D,
  tangent_point: Point2D,
  title: str,
  pin_color: str,
) -> None:
  width = float(canvas.winfo_width() or ZOOM_CANVAS_WIDTH)
  height = float(canvas.winfo_height() or ZOOM_CANVAS_HEIGHT)
  canvas.delete("all")
  target_pin, previous_pin, next_pin = _neighbor_points(result, pin_name)
  neighborhood = [target_pin]
  if previous_pin is not None:
    neighborhood.append(previous_pin)
  if next_pin is not None:
    neighborhood.append(next_pin)

  points = [point for _, point in neighborhood]
  points.append(tangent_point)
  padding = max(result.pin_radius * 2.0, 8.0)
  local_bounds = _fit_bounds(points + [pin_point], padding, padding)
  span_x = max(local_bounds.right - local_bounds.left, result.pin_radius * 8.0)
  span_y = max(local_bounds.top - local_bounds.bottom, result.pin_radius * 8.0)
  scale = min(
    max(width - (2.0 * CANVAS_PADDING), 1.0) / span_x,
    max(height - (2.0 * CANVAS_PADDING), 1.0) / span_y,
  )
  center_x = width / 2.0
  center_y = height / 2.0
  tangent_direction = Point2D(
    result.tangent_point_b.x - result.tangent_point_a.x,
    result.tangent_point_b.y - result.tangent_point_a.y,
  )
  local_tangent_segment = _clip_line_to_bounds(
    result.tangent_point_a, tangent_direction, local_bounds
  )
  local_runtime_segment = None
  runtime_anchor_tangent = _runtime_anchor_tangent_point(result)
  if runtime_anchor_tangent is not None and result.runtime_target_point is not None:
    runtime_direction = Point2D(
      result.runtime_target_point.x - runtime_anchor_tangent.x,
      result.runtime_target_point.y - runtime_anchor_tangent.y,
    )
    local_runtime_segment = _clip_line_to_bounds(
      runtime_anchor_tangent, runtime_direction, local_bounds
    )

  def project(point: Point2D) -> tuple[float, float]:
    return (
      center_x - ((point.x - pin_point.x) * scale),
      center_y - ((point.y - pin_point.y) * scale),
    )

  scaled_pin_radius = result.pin_radius * scale
  _draw_local_axes(canvas, width=width, height=height, x_direction=1.0)
  _draw_clipped_line(canvas, project, local_tangent_segment, fill="#7c3aed", width=2)
  _draw_clipped_line(
    canvas,
    project,
    local_runtime_segment,
    fill="#dc2626",
    width=2,
    dash=(2, 2),
  )
  for neighbor_name, neighbor_point in neighborhood:
    x, y = project(neighbor_point)
    outline = pin_color if neighbor_name == pin_name else "#cbd5e1"
    width_value = 2 if neighbor_name == pin_name else 1
    canvas.create_oval(
      x - scaled_pin_radius,
      y - scaled_pin_radius,
      x + scaled_pin_radius,
      y + scaled_pin_radius,
      outline=outline,
      width=width_value,
    )
    if neighbor_name != pin_name:
      canvas.create_text(
        x, y + scaled_pin_radius + 10.0, text=neighbor_name, fill="#64748b", anchor="n"
      )

  pin_xy = project(pin_point)
  tangent_xy = project(tangent_point)
  canvas.create_line(
    pin_xy[0], pin_xy[1], tangent_xy[0], tangent_xy[1], fill="#94a3b8", dash=(2, 2)
  )
  _draw_labeled_point(
    canvas,
    project,
    pin_point,
    label=pin_name,
    color=pin_color,
    radius=2.0,
    text_dx=0.0,
    text_dy=scaled_pin_radius + 16.0,
    text_anchor="n",
  )
  _draw_labeled_point(
    canvas,
    project,
    tangent_point,
    label="",
    color="#7c3aed",
    radius=2.0,
    text_dx=8.0,
    text_dy=-10.0,
    text_anchor="w",
  )
  canvas.create_text(10, 10, anchor="nw", fill="#222222", text=title)


def _draw_outbound_zoom(canvas: tk.Canvas, result: UvTangentViewResult) -> None:
  width = float(canvas.winfo_width() or ZOOM_CANVAS_WIDTH)
  height = float(canvas.winfo_height() or ZOOM_CANVAS_HEIGHT)
  canvas.delete("all")

  focus_points = [result.outbound_intercept]
  optional_points = [
    result.runtime_outbound_intercept,
    result.arm_head_center,
    result.arm_left_endpoint,
    result.arm_right_endpoint,
    result.runtime_target_point,
  ]
  focus_points.extend(point for point in optional_points if point is not None)
  focus_points.extend(result.roller_centers)

  padding = max(result.pin_radius * 4.0, result.head_roller_radius * 3.0, 15.0)
  local_bounds = _fit_bounds(focus_points, padding, padding)
  span_x = max(local_bounds.right - local_bounds.left, result.pin_radius * 8.0)
  span_y = max(local_bounds.top - local_bounds.bottom, result.pin_radius * 8.0)
  scale = min(
    max(width - (2.0 * CANVAS_PADDING), 1.0) / span_x,
    max(height - (2.0 * CANVAS_PADDING), 1.0) / span_y,
  )
  center_x = width / 2.0
  center_y = height / 2.0
  midpoint = Point2D(
    (local_bounds.left + local_bounds.right) / 2.0,
    (local_bounds.top + local_bounds.bottom) / 2.0,
  )

  def project(point: Point2D) -> tuple[float, float]:
    return (
      center_x - ((point.x - midpoint.x) * scale),
      center_y - ((point.y - midpoint.y) * scale),
    )

  _draw_local_axes(canvas, width=width, height=height, x_direction=1.0)
  _draw_bounds(canvas, project, result.transfer_bounds, outline="#64748b", dash=(4, 4))
  selected_direction = Point2D(
    result.tangent_point_b.x - result.tangent_point_a.x,
    result.tangent_point_b.y - result.tangent_point_a.y,
  )
  _draw_clipped_line(
    canvas,
    project,
    _clip_line_to_bounds(result.tangent_point_a, selected_direction, local_bounds),
    fill="#7c3aed",
    width=2,
  )
  if (
    result.runtime_tangent_point is not None and result.runtime_target_point is not None
  ):
    runtime_direction = Point2D(
      result.runtime_target_point.x - result.runtime_tangent_point.x,
      result.runtime_target_point.y - result.runtime_tangent_point.y,
    )
    _draw_clipped_line(
      canvas,
      project,
      _clip_line_to_bounds(
        result.runtime_tangent_point, runtime_direction, local_bounds
      ),
      fill="#ea580c",
      width=2,
      dash=(6, 3),
    )

  if result.arm_left_endpoint is not None and result.arm_right_endpoint is not None:
    left_xy = project(result.arm_left_endpoint)
    right_xy = project(result.arm_right_endpoint)
    canvas.create_line(
      left_xy[0], left_xy[1], right_xy[0], right_xy[1], fill="#0f172a", width=2
    )
  if result.arm_head_center is not None:
    _draw_labeled_point(
      canvas,
      project,
      result.arm_head_center,
      label="head",
      color="#0f172a",
      radius=2.0,
      text_dx=8.0,
      text_dy=12.0,
      text_anchor="w",
    )
  if result.roller_centers:
    scaled_roller_radius = max(result.head_roller_radius * scale, 2.0)
    for roller_center in result.roller_centers:
      x, y = project(roller_center)
      canvas.create_oval(
        x - scaled_roller_radius,
        y - scaled_roller_radius,
        x + scaled_roller_radius,
        y + scaled_roller_radius,
        outline="#0f172a",
      )

  _draw_labeled_point(
    canvas,
    project,
    result.outbound_intercept,
    label="selected outbound",
    color="#7c3aed",
    radius=2.0,
    text_dx=8.0,
    text_dy=-10.0,
    text_anchor="w",
  )
  if result.runtime_outbound_intercept is not None:
    _draw_labeled_point(
      canvas,
      project,
      result.runtime_outbound_intercept,
      label="runtime outbound",
      color="#ea580c",
      radius=2.0,
      text_dx=8.0,
      text_dy=12.0,
      text_anchor="w",
    )
  text_lines = [
    "Transfer zone",
    f"Outbound: ({result.outbound_intercept.x:.3f}, {result.outbound_intercept.y:.3f})",
  ]
  if result.runtime_target_point is not None:
    delta = Point2D(
      result.outbound_intercept.x - result.runtime_target_point.x,
      result.outbound_intercept.y - result.runtime_target_point.y,
    )
    text_lines.extend(
      (
        f"G108 target: ({result.runtime_target_point.x:.3f}, {result.runtime_target_point.y:.3f})",
        f"Outbound - G108: ({delta.x:.3f}, {delta.y:.3f})",
      )
    )
  else:
    text_lines.append("G108 target: unavailable")
    text_lines.append("Outbound - G108: unavailable")
  canvas.create_text(
    10,
    10,
    anchor="nw",
    fill="#222222",
    text="\n".join(text_lines),
    justify="left",
  )


def _build_alternating_canvas_transform(
  result: UvTangentViewResult,
  width: float,
  height: float,
):
  assert result.alternating_plane is not None
  points = [
    result.alternating_anchor_center,
    result.alternating_wrapped_center,
    result.alternating_anchor_segment_start,
    result.alternating_anchor_segment_end,
    result.alternating_wrapped_segment_start,
    result.alternating_wrapped_segment_end,
    result.alternating_wrap_line_start,
    result.alternating_wrap_line_end,
    result.alternating_g109_projection,
    result.alternating_g103_projection,
  ]
  plot_points = [point for point in points if point is not None]
  x_padding = max(result.pin_radius * 4.0, CANVAS_PADDING)
  if result.alternating_plane == "xz":
    x_values = [point.x for point in plot_points]
    min_x = min(x_values) - x_padding
    max_x = max(x_values) + x_padding
    min_z = result.z_retracted
    max_z = result.z_extended
    span_x = max(max_x - min_x, result.pin_radius * 8.0)
    span_z = max(max_z - min_z, 1.0)
    scale = min(
      max(width - (2.0 * CANVAS_PADDING), 1.0) / span_x,
      max(height - (2.0 * CANVAS_PADDING), 1.0) / span_z,
    )

    def project(point: Point2D) -> tuple[float, float]:
      return (
        width - CANVAS_PADDING - ((point.x - min_x) * scale),
        CANVAS_PADDING + ((point.y - min_z) * scale),
      )

    return project

  y_values = [point.y for point in plot_points]
  min_y = min(y_values) - x_padding
  max_y = max(y_values) + x_padding
  min_z = result.z_retracted
  max_z = result.z_extended
  span_y = max(max_y - min_y, result.pin_radius * 8.0)
  span_z = max(max_z - min_z, 1.0)
  scale = min(
    max(width - (2.0 * CANVAS_PADDING), 1.0) / span_z,
    max(height - (2.0 * CANVAS_PADDING), 1.0) / span_y,
  )

  def project(point: Point2D) -> tuple[float, float]:
    return (
      CANVAS_PADDING + ((point.x - min_z) * scale),
      height - CANVAS_PADDING - ((point.y - min_y) * scale),
    )

  return project


def _draw_alternating_axes(
  canvas: tk.Canvas,
  result: UvTangentViewResult,
  *,
  width: float,
  height: float,
) -> None:
  origin_x = 55.0
  origin_y = height - 35.0
  axis_length = 40.0
  if result.alternating_plane == "xz":
    canvas.create_line(
      origin_x,
      origin_y,
      origin_x - axis_length,
      origin_y,
      fill="#475569",
      width=2,
      arrow="last",
    )
    canvas.create_text(origin_x - axis_length - 8.0, origin_y, text="+x", fill="#475569", anchor="e")
    canvas.create_line(
      origin_x,
      origin_y,
      origin_x,
      origin_y + axis_length,
      fill="#475569",
      width=2,
      arrow="last",
    )
    canvas.create_text(origin_x, origin_y + axis_length + 8.0, text="+z", fill="#475569", anchor="n")
    return

  canvas.create_line(
    origin_x,
    origin_y,
    origin_x + axis_length,
    origin_y,
    fill="#475569",
    width=2,
    arrow="last",
  )
  canvas.create_text(origin_x + axis_length + 8.0, origin_y, text="+z", fill="#475569", anchor="w")
  canvas.create_line(
    origin_x,
    origin_y,
    origin_x,
    origin_y - axis_length,
    fill="#475569",
    width=2,
    arrow="last",
  )
  canvas.create_text(origin_x, origin_y - axis_length - 8.0, text="+y", fill="#475569", anchor="s")


def _draw_alternating_result(canvas: tk.Canvas, result: UvTangentViewResult) -> None:
  width = float(canvas.winfo_width() or CANVAS_WIDTH)
  height = float(canvas.winfo_height() or CANVAS_HEIGHT)
  canvas.delete("all")
  project = _build_alternating_canvas_transform(result, width, height)
  _draw_alternating_axes(canvas, result, width=width, height=height)

  assert result.alternating_wrap_line_start is not None
  assert result.alternating_wrap_line_end is not None
  assert result.alternating_anchor_segment_start is not None
  assert result.alternating_anchor_segment_end is not None
  assert result.alternating_wrapped_segment_start is not None
  assert result.alternating_wrapped_segment_end is not None
  assert result.alternating_anchor_center is not None
  assert result.alternating_wrapped_center is not None

  z_retracted_start = (
    Point2D(result.alternating_wrap_line_start.x - 50.0, result.z_retracted)
    if result.alternating_plane == "xz"
    else Point2D(result.z_retracted, result.alternating_wrap_line_start.y - 50.0)
  )
  z_retracted_end = (
    Point2D(result.alternating_wrap_line_start.x + 50.0, result.z_retracted)
    if result.alternating_plane == "xz"
    else Point2D(result.z_retracted, result.alternating_wrap_line_start.y + 50.0)
  )
  z_extended_start = (
    Point2D(result.alternating_wrap_line_end.x - 50.0, result.z_extended)
    if result.alternating_plane == "xz"
    else Point2D(result.z_extended, result.alternating_wrap_line_end.y - 50.0)
  )
  z_extended_end = (
    Point2D(result.alternating_wrap_line_end.x + 50.0, result.z_extended)
    if result.alternating_plane == "xz"
    else Point2D(result.z_extended, result.alternating_wrap_line_end.y + 50.0)
  )
  _draw_clipped_line(canvas, project, (z_retracted_start, z_retracted_end), fill="#cbd5e1", dash=(4, 4))
  _draw_clipped_line(canvas, project, (z_extended_start, z_extended_end), fill="#cbd5e1", dash=(4, 4))

  _draw_clipped_line(
    canvas,
    project,
    (result.alternating_anchor_segment_start, result.alternating_anchor_segment_end),
    fill="#2563eb",
    width=3,
  )
  _draw_clipped_line(
    canvas,
    project,
    (result.alternating_wrapped_segment_start, result.alternating_wrapped_segment_end),
    fill="#059669",
    width=3,
  )
  _draw_clipped_line(
    canvas,
    project,
    (result.alternating_wrap_line_start, result.alternating_wrap_line_end),
    fill="#7c3aed",
    width=2,
  )
  if result.alternating_g109_projection is not None and result.alternating_g103_projection is not None:
    _draw_clipped_line(
      canvas,
      project,
      (result.alternating_g109_projection, result.alternating_g103_projection),
      fill="#ea580c",
      width=2,
      dash=(6, 3),
    )
  _draw_labeled_point(
    canvas,
    project,
    result.alternating_anchor_center,
    label=f"anchor {result.request.pin_a}",
    color="#1d4ed8",
    radius=2.0,
    text_dx=8.0,
    text_dy=12.0,
  )
  _draw_labeled_point(
    canvas,
    project,
    result.alternating_wrapped_center,
    label=f"target {result.request.pin_b}",
    color="#047857",
    radius=2.0,
    text_dx=8.0,
    text_dy=-12.0,
  )
  canvas.create_text(
    10,
    10,
    anchor="nw",
    fill="#222222",
    text=(
      f"{result.request.layer} alternating-side view ({result.alternating_plane}, "
      f"{result.alternating_face})"
    ),
  )


def _draw_alternating_zoom_views(form: _FormState, result: UvTangentViewResult) -> None:
  messages = (
    ("Anchor segment", form.pin_a_zoom_canvas),
    ("Wrapped segment", form.pin_b_zoom_canvas),
    ("Projection details", form.outbound_zoom_canvas),
  )
  for title, canvas in messages:
    canvas.delete("all")
    canvas.create_text(
      10,
      10,
      anchor="nw",
      fill="#222222",
      text=f"{title}\nSee main canvas for alternating-side projection.",
      justify="left",
    )


def draw_result(canvas: tk.Canvas, result: UvTangentViewResult) -> None:
  if _is_alternating_result(result):
    _draw_alternating_result(canvas, result)
    return

  width = float(canvas.winfo_width() or CANVAS_WIDTH)
  height = float(canvas.winfo_height() or CANVAS_HEIGHT)
  canvas.delete("all")
  project, scale = _build_canvas_transform(result, width, height)

  _draw_bounds(canvas, project, result.apa_bounds, outline="#cbd5e1")
  _draw_bounds(canvas, project, result.transfer_bounds, outline="#64748b", dash=(4, 4))
  _draw_axis_arrows(canvas, project, result.transfer_bounds)

  scaled_pin_radius = result.pin_radius * scale
  for point in result.apa_pin_points:
    x, y = project(point)
    canvas.create_oval(
      x - scaled_pin_radius,
      y - scaled_pin_radius,
      x + scaled_pin_radius,
      y + scaled_pin_radius,
      outline="#d4d4d8",
    )

  pin_a_center = Point2D(result.pin_a_point.x, result.pin_a_point.y)
  pin_b_center = Point2D(result.pin_b_point.x, result.pin_b_point.y)
  for center, outline in ((pin_a_center, "#2563eb"), (pin_b_center, "#059669")):
    center_x, center_y = project(center)
    canvas.create_oval(
      center_x - scaled_pin_radius,
      center_y - scaled_pin_radius,
      center_x + scaled_pin_radius,
      center_y + scaled_pin_radius,
      outline=outline,
      width=2,
    )

  start_xy = project(result.clipped_segment_start)
  end_xy = project(result.clipped_segment_end)
  canvas.create_line(
    start_xy[0], start_xy[1], end_xy[0], end_xy[1], fill="#7c3aed", width=2
  )
  runtime_anchor_tangent = _runtime_anchor_tangent_point(result)
  if runtime_anchor_tangent is not None and result.runtime_target_point is not None:
    runtime_direction = Point2D(
      result.runtime_target_point.x - runtime_anchor_tangent.x,
      result.runtime_target_point.y - runtime_anchor_tangent.y,
    )
    runtime_segment = _clip_line_to_bounds(
      runtime_anchor_tangent, runtime_direction, result.transfer_bounds
    )
    if runtime_segment is not None:
      runtime_start_xy = project(runtime_segment[0])
      runtime_end_xy = project(runtime_segment[1])
      canvas.create_line(
        runtime_start_xy[0],
        runtime_start_xy[1],
        runtime_end_xy[0],
        runtime_end_xy[1],
        fill="#dc2626",
        width=2,
        dash=(2, 2),
      )
  canvas.create_line(
    project(pin_a_center)[0],
    project(pin_a_center)[1],
    project(result.tangent_point_a)[0],
    project(result.tangent_point_a)[1],
    fill="#94a3b8",
    dash=(2, 2),
  )
  canvas.create_line(
    project(pin_b_center)[0],
    project(pin_b_center)[1],
    project(result.tangent_point_b)[0],
    project(result.tangent_point_b)[1],
    fill="#94a3b8",
    dash=(2, 2),
  )

  _draw_labeled_point(
    canvas,
    project,
    pin_a_center,
    label=f"anchor {result.request.pin_a}",
    color="#1d4ed8",
    radius=2.0,
    text_dx=-8.0,
    text_dy=12.0,
    text_anchor="e",
  )
  _draw_labeled_point(
    canvas,
    project,
    pin_b_center,
    label=f"target {result.request.pin_b}",
    color="#047857",
    radius=2.0,
    text_dx=-8.0,
    text_dy=-12.0,
    text_anchor="e",
  )
  _draw_labeled_point(
    canvas,
    project,
    result.outbound_intercept,
    label="outbound",
    color="#7c3aed",
    radius=2.0,
  )
  if result.runtime_target_point is not None:
    _draw_labeled_point(
      canvas,
      project,
      result.runtime_target_point,
      label="g108 target",
      color="#ea580c",
      radius=2.0,
      text_dx=8.0,
      text_dy=12.0,
      text_anchor="w",
    )
  canvas.create_text(
    10, 10, anchor="nw", fill="#222222", text=f"{result.request.layer} tangent view"
  )


def draw_zoom_views(form: _FormState, result: UvTangentViewResult) -> None:
  if _is_alternating_result(result):
    _draw_alternating_zoom_views(form, result)
    return

  _draw_touch_zoom(
    form.pin_a_zoom_canvas,
    result,
    pin_name=result.request.pin_a,
    pin_point=Point2D(result.pin_a_point.x, result.pin_a_point.y),
    tangent_point=result.tangent_point_a,
    title="Anchor pin tangent",
    pin_color="#1d4ed8",
  )
  _draw_touch_zoom(
    form.pin_b_zoom_canvas,
    result,
    pin_name=result.request.pin_b,
    pin_point=Point2D(result.pin_b_point.x, result.pin_b_point.y),
    tangent_point=result.tangent_point_b,
    title="Target pin tangent",
    pin_color="#047857",
  )
  _draw_outbound_zoom(form.outbound_zoom_canvas, result)


def calculate_and_render(
  form: _FormState,
  *,
  compute_fn=compute_uv_tangent_view,
) -> UvTangentViewResult | None:
  try:
    request = build_request_from_form(form)
    result = compute_fn(request)
  except UvHeadTargetError as exc:
    form.error_var.set(str(exc))
    form.summary_var.set("")
    form.canvas.delete("all")
    form.pin_a_zoom_canvas.delete("all")
    form.pin_b_zoom_canvas.delete("all")
    form.outbound_zoom_canvas.delete("all")
    return None

  form.error_var.set("")
  form.summary_var.set(format_result_summary(result))
  draw_result(form.canvas, result)
  draw_zoom_views(form, result)
  return result


def _build_form(root: tk.Misc) -> _FormState:
  controls = tk.Frame(root, padx=12, pady=12)
  controls.grid(row=0, column=0, sticky="ns")
  viewer = tk.Frame(root, padx=12, pady=12)
  viewer.grid(row=0, column=1, sticky="nsew")
  root.columnconfigure(1, weight=1)
  root.rowconfigure(0, weight=1)
  viewer.columnconfigure(0, weight=1)
  viewer.rowconfigure(1, weight=1)
  viewer.rowconfigure(2, weight=0)

  mode_var = tk.StringVar(master=root, value="Pins")
  layer_var = tk.StringVar(master=root, value="U")
  pin_a_var = tk.StringVar(master=root, value="B1201")
  pin_b_var = tk.StringVar(master=root, value="B2001")
  wrap_var = tk.StringVar(master=root, value="1")
  segment_var = tk.StringVar(master=root, value="1")
  derived_pins_var = tk.StringVar(master=root, value="")
  error_var = tk.StringVar(master=root, value="")
  summary_var = tk.StringVar(master=root, value="")

  tk.Label(controls, text="Mode").grid(row=0, column=0, sticky="w")
  tk.OptionMenu(controls, mode_var, "Pins", "Wrap/Segment").grid(
    row=1, column=0, sticky="ew"
  )
  tk.Label(controls, text="Layer").grid(row=2, column=0, sticky="w", pady=(10, 0))
  tk.OptionMenu(controls, layer_var, "U", "V").grid(row=3, column=0, sticky="ew")

  pins_frame = tk.Frame(controls)
  pins_frame.grid(row=4, column=0, sticky="ew", pady=(10, 0))
  tk.Label(pins_frame, text="Anchor Pin").grid(row=0, column=0, sticky="w")
  tk.Entry(pins_frame, textvariable=pin_a_var).grid(row=1, column=0, sticky="ew")
  tk.Label(pins_frame, text="Target Pin").grid(
    row=2, column=0, sticky="w", pady=(10, 0)
  )
  tk.Entry(pins_frame, textvariable=pin_b_var).grid(row=3, column=0, sticky="ew")
  pins_frame.columnconfigure(0, weight=1)

  wrap_frame = tk.Frame(controls)
  wrap_frame.grid(row=5, column=0, sticky="ew", pady=(10, 0))
  tk.Label(wrap_frame, text="Wrap #").grid(row=0, column=0, sticky="w")
  tk.Entry(wrap_frame, textvariable=wrap_var).grid(row=1, column=0, sticky="ew")
  tk.Label(wrap_frame, text="Segment #").grid(
    row=2, column=0, sticky="w", pady=(10, 0)
  )
  tk.Entry(wrap_frame, textvariable=segment_var).grid(row=3, column=0, sticky="ew")
  derived_label = tk.Label(
    wrap_frame,
    textvariable=derived_pins_var,
    fg="#475569",
    justify="left",
    wraplength=240,
  )
  derived_label.grid(row=4, column=0, sticky="ew", pady=(10, 0))
  nav_frame = tk.Frame(wrap_frame)
  nav_frame.grid(row=5, column=0, sticky="ew", pady=(8, 0))
  prev_button = tk.Button(nav_frame, text="Prev")
  next_button = tk.Button(nav_frame, text="Next")
  prev_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
  next_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))
  nav_frame.columnconfigure(0, weight=1)
  nav_frame.columnconfigure(1, weight=1)
  wrap_frame.columnconfigure(0, weight=1)

  canvas = tk.Canvas(viewer, width=CANVAS_WIDTH, height=CANVAS_HEIGHT, bg="white", highlightthickness=1, highlightbackground="#cccccc")
  canvas.grid(row=1, column=0, sticky="nsew")
  zoom_frame = tk.Frame(viewer)
  zoom_frame.grid(row=2, column=0, sticky="ew", pady=(12, 0))
  pin_a_zoom_canvas = tk.Canvas(
    zoom_frame,
    width=ZOOM_CANVAS_WIDTH,
    height=ZOOM_CANVAS_HEIGHT,
    bg="white",
    highlightthickness=1,
    highlightbackground="#cccccc",
  )
  pin_a_zoom_canvas.grid(row=0, column=0, sticky="ew", padx=(0, 6))
  pin_b_zoom_canvas = tk.Canvas(
    zoom_frame,
    width=ZOOM_CANVAS_WIDTH,
    height=ZOOM_CANVAS_HEIGHT,
    bg="white",
    highlightthickness=1,
    highlightbackground="#cccccc",
  )
  pin_b_zoom_canvas.grid(row=0, column=1, sticky="ew", padx=(6, 0))
  outbound_zoom_canvas = tk.Canvas(
    zoom_frame,
    width=ZOOM_CANVAS_WIDTH,
    height=ZOOM_CANVAS_HEIGHT,
    bg="white",
    highlightthickness=1,
    highlightbackground="#cccccc",
  )
  outbound_zoom_canvas.grid(row=0, column=2, sticky="ew", padx=(6, 0))

  form = _FormState(
    mode_var=mode_var,
    layer_var=layer_var,
    pin_a_var=pin_a_var,
    pin_b_var=pin_b_var,
    wrap_var=wrap_var,
    segment_var=segment_var,
    derived_pins_var=derived_pins_var,
    error_var=error_var,
    summary_var=summary_var,
    canvas=canvas,
    pin_a_zoom_canvas=pin_a_zoom_canvas,
    pin_b_zoom_canvas=pin_b_zoom_canvas,
    outbound_zoom_canvas=outbound_zoom_canvas,
  )

  def update_mode_visibility() -> None:
    mode = str(mode_var.get()).strip().lower()
    if mode == "wrap/segment":
      pins_frame.grid_remove()
      wrap_frame.grid()
    else:
      wrap_frame.grid_remove()
      pins_frame.grid()

  def update_derived_pins() -> None:
    if str(mode_var.get()).strip().lower() != "wrap/segment":
      derived_pins_var.set("")
      return
    layer = layer_var.get()
    try:
      wrap_number = int(str(wrap_var.get()).strip())
      segment_number = int(str(segment_var.get()).strip())
    except ValueError:
      derived_pins_var.set("Site: (enter wrap + segment)")
      return
    index = _segment_index_by_wrap_segment(layer).get((wrap_number, segment_number))
    if index is None:
      derived_pins_var.set("Site: (no primary site for that wrap/segment)")
      return
    segment = _segments_for_layer(layer)[index]
    derived_pins_var.set(
      "Anchor: "
      f"{segment.anchor_pin}  Wrapped: {segment.wrapped_pin}  "
      f"Neighbor: {segment.adjacent_pin}  (wrap line {segment.wrap_line_number})"
    )

  def step_segment(delta: int) -> None:
    if str(mode_var.get()).strip().lower() != "wrap/segment":
      return
    layer = layer_var.get()
    try:
      wrap_number = int(str(wrap_var.get()).strip())
      segment_number = int(str(segment_var.get()).strip())
    except ValueError:
      error_var.set("Wrap # and Segment # must be integers.")
      return
    index = _segment_index_by_wrap_segment(layer).get((wrap_number, segment_number))
    if index is None:
      error_var.set(
        f"No primary site found for wrap {wrap_number}, segment {segment_number}."
      )
      return
    segments = _segments_for_layer(layer)
    new_index = index + delta
    if new_index < 0:
      error_var.set("Already at first segment for this layer.")
      return
    if new_index >= len(segments):
      error_var.set("Already at last segment for this layer.")
      return
    next_segment = segments[new_index]
    wrap_var.set(str(next_segment.wrap_number))
    segment_var.set(str(next_segment.segment_number))
    update_derived_pins()
    calculate_and_render(form)

  prev_button.configure(command=lambda: step_segment(-1))
  next_button.configure(command=lambda: step_segment(1))

  tk.Button(
    controls,
    text="Calculate",
    command=lambda: calculate_and_render(form),
  ).grid(row=6, column=0, sticky="ew", pady=(12, 0))
  tk.Label(
    controls, textvariable=error_var, fg="#b91c1c", justify="left", wraplength=240
  ).grid(row=7, column=0, sticky="ew", pady=(10, 0))
  tk.Label(viewer, textvariable=summary_var, justify="left", anchor="w").grid(row=0, column=0, sticky="ew", pady=(0, 10))

  mode_var.trace_add(
    "write", lambda *_: (update_mode_visibility(), update_derived_pins())
  )
  layer_var.trace_add("write", lambda *_: update_derived_pins())
  wrap_var.trace_add("write", lambda *_: update_derived_pins())
  segment_var.trace_add("write", lambda *_: update_derived_pins())
  update_mode_visibility()
  update_derived_pins()
  return form


def run_app(root: tk.Misc | None = None) -> None:
  root = root or tk.Tk()
  root.title("UV Tangent Viewer")
  _build_form(root)
  root.mainloop()


if __name__ == "__main__":
  run_app()
