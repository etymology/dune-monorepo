from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .segment_types import (
  CIRCLE_TYPE_CENTER,
  MCCM_DIR_2D_CCW,
  MCCM_DIR_2D_CW,
  MotionSegment,
  SEG_TYPE_CIRCLE,
  SEG_TYPE_LINE,
)

_EPS = 1e-6
_COMMAND_POSITION_RESOLUTION_MM = 0.1


def distance_xy(p0: tuple[float, float], p1: tuple[float, float]) -> float:
  return math.hypot(p1[0] - p0[0], p1[1] - p0[1])


def unit_vector_between(
  start_xy: tuple[float, float],
  end_xy: tuple[float, float],
) -> Optional[tuple[float, float]]:
  dx = end_xy[0] - start_xy[0]
  dy = end_xy[1] - start_xy[1]
  mag = math.hypot(dx, dy)
  if mag <= _EPS:
    return None
  return (dx / mag, dy / mag)


def _left_normal(direction: tuple[float, float]) -> tuple[float, float]:
  return (-direction[1], direction[0])


def dynamic_min_radius(
  *,
  speed: float,
  base_min_radius: float,
  accel_limit: float,
  jerk_limit: float,
) -> float:
  radius = max(0.0, float(base_min_radius))
  speed = max(0.0, float(speed))
  accel_limit = max(0.0, float(accel_limit))
  jerk_limit = max(0.0, float(jerk_limit))

  if speed <= _EPS:
    return radius
  if accel_limit > _EPS:
    radius = max(radius, (speed * speed) / accel_limit)
  if jerk_limit > _EPS:
    radius = max(radius, math.sqrt((speed * speed * speed) / jerk_limit))
  return radius


@dataclass(frozen=True)
class WaypointCircle:
  waypoint_xy: tuple[float, float]
  center_xy: tuple[float, float]
  radius: float


def build_waypoint_circles(
  *,
  start_xy: tuple[float, float],
  waypoints: list[tuple[float, float]],
  radius: float,
) -> Optional[list[WaypointCircle]]:
  if radius <= _EPS:
    return []

  circles: list[WaypointCircle] = []
  prev_xy = (float(start_xy[0]), float(start_xy[1]))
  for index, point_xy in enumerate(waypoints[:-1]):
    next_xy = waypoints[index + 1]
    incoming = unit_vector_between(point_xy, prev_xy)
    outgoing = unit_vector_between(point_xy, next_xy)
    if incoming is None or outgoing is None:
      return None

    bisector = unit_vector_between(
      (0.0, 0.0),
      (incoming[0] + outgoing[0], incoming[1] + outgoing[1]),
    )
    if bisector is None:
      return None

    center_xy = (
      point_xy[0] + bisector[0] * radius,
      point_xy[1] + bisector[1] * radius,
    )
    circles.append(WaypointCircle(waypoint_xy=point_xy, center_xy=center_xy, radius=radius))
    prev_xy = point_xy

  return circles


def point_circle_tangent_points(
  point_xy: tuple[float, float],
  circle: WaypointCircle,
) -> list[tuple[float, float]]:
  dx = point_xy[0] - circle.center_xy[0]
  dy = point_xy[1] - circle.center_xy[1]
  distance_to_center = math.hypot(dx, dy)
  if distance_to_center <= circle.radius + 1e-9:
    return []

  base_angle = math.atan2(dy, dx)
  delta_angle = math.acos(circle.radius / distance_to_center)
  tangent_points: list[tuple[float, float]] = []
  for sign in (-1.0, 1.0):
    angle = base_angle + sign * delta_angle
    tangent_xy = (
      circle.center_xy[0] + circle.radius * math.cos(angle),
      circle.center_xy[1] + circle.radius * math.sin(angle),
    )
    if not any(distance_xy(tangent_xy, existing) <= 1e-6 for existing in tangent_points):
      tangent_points.append(tangent_xy)
  return tangent_points


def circle_pair_tangent_pairs(
  first: WaypointCircle,
  second: WaypointCircle,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
  tangent_pairs: list[tuple[tuple[float, float], tuple[float, float]]] = []
  dx = second.center_xy[0] - first.center_xy[0]
  dy = second.center_xy[1] - first.center_xy[1]
  z = dx * dx + dy * dy
  if z <= _EPS:
    return []

  for radius_sign in (-1.0, 1.0):
    r = second.radius * radius_sign - first.radius
    h_sq = z - r * r
    if h_sq < -1e-9:
      continue
    h = math.sqrt(max(0.0, h_sq))
    for tangent_sign in (-1.0, 1.0):
      nx = (dx * r - dy * h * tangent_sign) / z
      ny = (dy * r + dx * h * tangent_sign) / z
      first_xy = (
        first.center_xy[0] + first.radius * nx,
        first.center_xy[1] + first.radius * ny,
      )
      second_xy = (
        second.center_xy[0] + second.radius * radius_sign * nx,
        second.center_xy[1] + second.radius * radius_sign * ny,
      )
      if not any(
        distance_xy(first_xy, existing_first) <= 1e-6
        and distance_xy(second_xy, existing_second) <= 1e-6
        for existing_first, existing_second in tangent_pairs
      ):
        tangent_pairs.append((first_xy, second_xy))
  return tangent_pairs


def _interior_angle(
  prev_xy: tuple[float, float],
  point_xy: tuple[float, float],
  next_xy: tuple[float, float],
) -> Optional[float]:
  in_vec = unit_vector_between(point_xy, prev_xy)
  out_vec = unit_vector_between(point_xy, next_xy)
  if in_vec is None or out_vec is None:
    return None
  dot = max(-1.0, min(1.0, in_vec[0] * out_vec[0] + in_vec[1] * out_vec[1]))
  return math.acos(dot)


def arc_choice_through_waypoint(
  circle: WaypointCircle,
  line_start_xy: tuple[float, float],
  incoming_xy: tuple[float, float],
  outgoing_xy: tuple[float, float],
  line_end_xy: tuple[float, float],
  target_sweep: float,
) -> Optional[tuple[int, float]]:
  if (
    distance_xy(incoming_xy, circle.waypoint_xy) <= _COMMAND_POSITION_RESOLUTION_MM
    or distance_xy(outgoing_xy, circle.waypoint_xy) <= _COMMAND_POSITION_RESOLUTION_MM
  ):
    return None

  incoming_dir = unit_vector_between(line_start_xy, incoming_xy)
  outgoing_dir = unit_vector_between(outgoing_xy, line_end_xy)
  if incoming_dir is None or outgoing_dir is None:
    return None

  def tangent_at(point_xy: tuple[float, float], direction: int) -> tuple[float, float]:
    radial_x = point_xy[0] - circle.center_xy[0]
    radial_y = point_xy[1] - circle.center_xy[1]
    radial_mag = math.hypot(radial_x, radial_y)
    if direction == MCCM_DIR_2D_CCW:
      return (-radial_y / radial_mag, radial_x / radial_mag)
    return (radial_y / radial_mag, -radial_x / radial_mag)

  tau = 2.0 * math.pi
  start_angle = math.atan2(
    incoming_xy[1] - circle.center_xy[1],
    incoming_xy[0] - circle.center_xy[0],
  )
  waypoint_angle = math.atan2(
    circle.waypoint_xy[1] - circle.center_xy[1],
    circle.waypoint_xy[0] - circle.center_xy[0],
  )
  end_angle = math.atan2(
    outgoing_xy[1] - circle.center_xy[1],
    outgoing_xy[0] - circle.center_xy[0],
  )

  candidates: list[tuple[float, int]] = []
  ccw_total = (end_angle - start_angle) % tau
  ccw_waypoint = (waypoint_angle - start_angle) % tau
  if 1e-6 < ccw_waypoint < ccw_total - 1e-6:
    candidates.append((ccw_total, MCCM_DIR_2D_CCW))

  cw_total = (start_angle - end_angle) % tau
  cw_waypoint = (start_angle - waypoint_angle) % tau
  if 1e-6 < cw_waypoint < cw_total - 1e-6:
    candidates.append((cw_total, MCCM_DIR_2D_CW))

  if not candidates:
    return None

  valid_candidates: list[tuple[float, int]] = []
  for sweep, direction in candidates:
    start_tangent = tangent_at(incoming_xy, direction)
    end_tangent = tangent_at(outgoing_xy, direction)
    start_dot = start_tangent[0] * incoming_dir[0] + start_tangent[1] * incoming_dir[1]
    end_dot = end_tangent[0] * outgoing_dir[0] + end_tangent[1] * outgoing_dir[1]
    if start_dot >= 1.0 - 1e-6 and end_dot >= 1.0 - 1e-6:
      valid_candidates.append((sweep, direction))

  if not valid_candidates:
    return None

  valid_candidates.sort(key=lambda item: (abs(item[0] - target_sweep), item[0]))
  best_sweep, best_direction = valid_candidates[0]
  return (best_direction, best_sweep)


def filleted_polygon_segments(
  *,
  start_xy: tuple[float, float],
  waypoints: list[tuple[float, float]],
  radius: float,
  line_term_type: int,
  arc_term_type: int,
  final_term_type: int,
) -> Optional[list[MotionSegment]]:
  if not waypoints:
    return []

  if len(waypoints) == 1:
    return [
      MotionSegment(
        seq=0,
        x=float(waypoints[0][0]),
        y=float(waypoints[0][1]),
        term_type=final_term_type,
        seg_type=SEG_TYPE_LINE,
      )
    ]

  circles = build_waypoint_circles(start_xy=start_xy, waypoints=waypoints, radius=radius)
  if circles is None or not circles:
    return None

  start_tangent_options = sorted(
    point_circle_tangent_points(start_xy, circles[0]),
    key=lambda tangent_xy: distance_xy(start_xy, tangent_xy),
  )
  if not start_tangent_options:
    return None

  end_xy = waypoints[-1]
  end_tangent_options = sorted(
    point_circle_tangent_points(end_xy, circles[-1]),
    key=lambda tangent_xy: distance_xy(end_xy, tangent_xy),
  )
  if not end_tangent_options:
    return None

  pair_tangent_options = [
    sorted(
      circle_pair_tangent_pairs(circles[index], circles[index + 1]),
      key=lambda pair: distance_xy(pair[0], pair[1]),
    )
    for index in range(len(circles) - 1)
  ]
  if any(not options for options in pair_tangent_options):
    return None

  points = [start_xy]
  points.extend(waypoints)
  target_sweeps: list[float] = []
  for index in range(1, len(points) - 1):
    interior_angle = _interior_angle(points[index - 1], points[index], points[index + 1])
    if interior_angle is None:
      return None
    target_sweeps.append(max(0.0, math.pi - interior_angle))

  def search(
    circle_index: int,
    line_start_xy: tuple[float, float],
    incoming_xy: tuple[float, float],
  ) -> Optional[tuple[tuple[float, float, float], list[tuple[tuple[float, float], tuple[float, float], int]]]]:
    circle = circles[circle_index]
    target_sweep = target_sweeps[circle_index]
    if circle_index == len(circles) - 1:
      best_result = None
      for outgoing_xy in end_tangent_options:
        choice = arc_choice_through_waypoint(
          circle,
          line_start_xy,
          incoming_xy,
          outgoing_xy,
          end_xy,
          target_sweep,
        )
        if choice is None:
          continue
        direction, sweep = choice
        score = (
          abs(sweep - target_sweep),
          sweep,
          distance_xy(line_start_xy, incoming_xy) + distance_xy(outgoing_xy, end_xy),
        )
        result = (score, [(incoming_xy, outgoing_xy, direction)])
        if best_result is None or result[0] < best_result[0]:
          best_result = result
      return best_result

    best_result = None
    for outgoing_xy, next_incoming_xy in pair_tangent_options[circle_index]:
      choice = arc_choice_through_waypoint(
        circle,
        line_start_xy,
        incoming_xy,
        outgoing_xy,
        next_incoming_xy,
        target_sweep,
      )
      if choice is None:
        continue
      direction, sweep = choice
      child_result = search(circle_index + 1, outgoing_xy, next_incoming_xy)
      if child_result is None:
        continue
      child_score, child_arcs = child_result
      score = (
        abs(sweep - target_sweep) + child_score[0],
        sweep + child_score[1],
        distance_xy(line_start_xy, incoming_xy)
        + distance_xy(outgoing_xy, next_incoming_xy)
        + child_score[2],
      )
      result = (score, [(incoming_xy, outgoing_xy, direction)] + child_arcs)
      if best_result is None or result[0] < best_result[0]:
        best_result = result
    return best_result

  best_path = None
  for incoming_xy in start_tangent_options:
    candidate = search(0, start_xy, incoming_xy)
    if candidate is None:
      continue
    if best_path is None or candidate[0] < best_path[0]:
      best_path = candidate

  if best_path is None:
    return None
  chosen_arcs = best_path[1]

  segments: list[MotionSegment] = []
  cursor_xy = (float(start_xy[0]), float(start_xy[1]))
  for circle, (incoming_xy, outgoing_xy, direction) in zip(circles, chosen_arcs):
    if distance_xy(cursor_xy, incoming_xy) > _EPS:
      segments.append(
        MotionSegment(
          seq=0,
          x=incoming_xy[0],
          y=incoming_xy[1],
          term_type=line_term_type,
          seg_type=SEG_TYPE_LINE,
        )
      )
    segments.append(
      MotionSegment(
        seq=0,
        x=outgoing_xy[0],
        y=outgoing_xy[1],
        term_type=arc_term_type,
        seg_type=SEG_TYPE_CIRCLE,
        circle_type=CIRCLE_TYPE_CENTER,
        via_center_x=circle.center_xy[0],
        via_center_y=circle.center_xy[1],
        direction=direction,
      )
    )
    cursor_xy = outgoing_xy

  if distance_xy(cursor_xy, end_xy) > _EPS:
    segments.append(
      MotionSegment(
        seq=0,
        x=end_xy[0],
        y=end_xy[1],
        term_type=final_term_type,
        seg_type=SEG_TYPE_LINE,
      )
    )
  elif segments:
    last = segments[-1]
    segments[-1] = MotionSegment(
      seq=last.seq,
      x=last.x,
      y=last.y,
      speed=last.speed,
      accel=last.accel,
      decel=last.decel,
      jerk_accel=last.jerk_accel,
      jerk_decel=last.jerk_decel,
      term_type=final_term_type,
      seg_type=last.seg_type,
      direction=last.direction,
      circle_type=last.circle_type,
      via_x=last.via_x,
      via_y=last.via_y,
      via_center_x=last.via_center_x,
      via_center_y=last.via_center_y,
      z=last.z,
    )

  return segments
