from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from dune_winder.motion import (
  DEFAULT_CONSTANT_VELOCITY_MODE,
  DEFAULT_CURVATURE_SPEED_SAFETY,
  DEFAULT_ARCHIMEDEAN_BOUNDARY_MARGIN,
  DEFAULT_ARCHIMEDEAN_DIRECTION,
  DEFAULT_ARCHIMEDEAN_INITIAL_ANGLE_DEG,
  DEFAULT_ARCHIMEDEAN_POINTS_PER_TURN,
  DEFAULT_ARCHIMEDEAN_TURNS,
  DEFAULT_FIBONACCI_ARC_COUNT,
  DEFAULT_FIBONACCI_DIRECTION,
  DEFAULT_FIBONACCI_X_MAX,
  DEFAULT_FIBONACCI_X_MIN,
  DEFAULT_FIBONACCI_Y_MAX,
  DEFAULT_FIBONACCI_Y_MIN,
  DEFAULT_ORBIT_BOUNDARY_MARGIN,
  DEFAULT_ORBIT_ECCENTRICITY,
  DEFAULT_ORBIT_INITIAL_APSIS_DEG,
  DEFAULT_ORBIT_POINTS_PER_REVOLUTION,
  DEFAULT_ORBIT_PRECESSION_DEG_PER_REVOLUTION,
  DEFAULT_ORBIT_REVOLUTIONS,
  DEFAULT_WAYPOINT_MIN_ARC_RADIUS,
  DEFAULT_WAYPOINT_ORDER_MODE,
  DEFAULT_WAYPOINT_ALLOW_STOPS,
  DEFAULT_V_X_MAX,
  DEFAULT_V_Y_MAX,
  DEFAULT_MAX_SEGMENT_FACTOR,
  DEFAULT_MIN_JERK_RATIO,
  DEFAULT_MIN_SEGMENT_LENGTH,
  DEFAULT_TEST_TERM_TYPE,
  LISSAJOUS_TESSELLATION_SEGMENTS,
  MotionQueueClient,
  MotionSafetyLimits,
  MotionSegment,
  PLC_QUEUE_DEPTH,
  TESTABLE_TERM_TYPES,
  apply_merge_term_types,
  cap_segments_speed_by_axis_velocity,
  build_segments,
  load_motion_safety_limits,
  print_pattern_summary,
  run_queue_case,
  tune_segments_for_constant_velocity,
  validate_segments_within_safety_limits,
  write_segments_svg,
)


PLC_PATH = "192.168.140.13"  # change to your PLC IP/slot


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description=(
      "Queue coordinated line/arc segments and execute them on the PLC. "
      "Supported termination types: 0,1,2,3,4,5,6."
    )
  )
  parser.add_argument(
    "--pattern",
    choices=(
      "lissajous",
      "square",
      "simple",
      "tangent_mix",
      "fibonacci_arcs",
      "apsidal_orbit",
      "archimedean_spiral",
      "waypoint_path",
    ),
    default="lissajous",
    help="Path pattern to enqueue.",
  )
  parser.add_argument(
    "--gui",
    action="store_true",
    help=(
      "Launch the waypoint planner GUI. "
      "This mode is intended for waypoint_path planning and execution."
    ),
  )
  parser.add_argument(
    "--term-type",
    type=int,
    default=DEFAULT_TEST_TERM_TYPE,
    choices=TESTABLE_TERM_TYPES,
    help="Termination type for all queued segments in the run.",
  )
  parser.add_argument(
    "--tangential-term-type",
    type=int,
    default=None,
    choices=TESTABLE_TERM_TYPES,
    help=(
      "Termination type applied at tangential merges. "
      "Defaults to --term-type."
    ),
  )
  parser.add_argument(
    "--non-tangential-term-type",
    type=int,
    default=0,
    choices=TESTABLE_TERM_TYPES,
    help="Termination type applied at non-tangential merges.",
  )
  parser.add_argument(
    "--final-term-type",
    type=int,
    default=None,
    choices=TESTABLE_TERM_TYPES,
    help=(
      "Optional termination type override for the final segment after "
      "merge-based assignment."
    ),
  )
  parser.add_argument(
    "--sweep-term-types",
    action="store_true",
    help="Run a sweep across term types: 0,1,2,3,4,5,6.",
  )
  parser.add_argument(
    "--start-seq",
    type=int,
    default=100,
    help="Starting sequence ID for the first queued segment.",
  )
  parser.add_argument(
    "--lissajous-segments",
    type=int,
    default=LISSAJOUS_TESSELLATION_SEGMENTS,
    help=(
      "Adaptive detail target for Lissajous tessellation. Higher values "
      "increase point density, especially in tight turns."
    ),
  )
  parser.add_argument(
    "--fibonacci-arc-count",
    type=int,
    default=DEFAULT_FIBONACCI_ARC_COUNT,
    help="Number of quarter-circle arcs in fibonacci_arcs pattern.",
  )
  parser.add_argument(
    "--fibonacci-x-min",
    type=float,
    default=DEFAULT_FIBONACCI_X_MIN,
    help="Minimum X bound for fibonacci_arcs path fitting.",
  )
  parser.add_argument(
    "--fibonacci-x-max",
    type=float,
    default=DEFAULT_FIBONACCI_X_MAX,
    help="Maximum X bound for fibonacci_arcs path fitting.",
  )
  parser.add_argument(
    "--fibonacci-y-min",
    type=float,
    default=DEFAULT_FIBONACCI_Y_MIN,
    help="Minimum Y bound for fibonacci_arcs path fitting.",
  )
  parser.add_argument(
    "--fibonacci-y-max",
    type=float,
    default=DEFAULT_FIBONACCI_Y_MAX,
    help="Maximum Y bound for fibonacci_arcs path fitting.",
  )
  parser.add_argument(
    "--fibonacci-direction",
    choices=("ccw", "cw"),
    default=DEFAULT_FIBONACCI_DIRECTION,
    help="Spiral rotation direction for fibonacci_arcs.",
  )
  parser.add_argument(
    "--orbit-x-min",
    type=float,
    default=None,
    help="Optional X min bound for apsidal_orbit (defaults to machine limitLeft).",
  )
  parser.add_argument(
    "--orbit-x-max",
    type=float,
    default=None,
    help="Optional X max bound for apsidal_orbit (defaults to machine limitRight).",
  )
  parser.add_argument(
    "--orbit-y-min",
    type=float,
    default=None,
    help="Optional Y min bound for apsidal_orbit (defaults to machine limitBottom).",
  )
  parser.add_argument(
    "--orbit-y-max",
    type=float,
    default=None,
    help="Optional Y max bound for apsidal_orbit (defaults to machine limitTop).",
  )
  parser.add_argument(
    "--orbit-revolutions",
    type=float,
    default=DEFAULT_ORBIT_REVOLUTIONS,
    help="Number of orbit revolutions to generate for apsidal_orbit.",
  )
  parser.add_argument(
    "--orbit-points-per-rev",
    type=int,
    default=DEFAULT_ORBIT_POINTS_PER_REVOLUTION,
    help="Discretization points per revolution for apsidal_orbit.",
  )
  parser.add_argument(
    "--orbit-eccentricity",
    type=float,
    default=DEFAULT_ORBIT_ECCENTRICITY,
    help="Eccentricity [0,1) for apsidal_orbit.",
  )
  parser.add_argument(
    "--orbit-precession-deg-per-rev",
    type=float,
    default=DEFAULT_ORBIT_PRECESSION_DEG_PER_REVOLUTION,
    help="Apsidal precession in degrees per revolution for apsidal_orbit.",
  )
  parser.add_argument(
    "--orbit-initial-apsis-deg",
    type=float,
    default=DEFAULT_ORBIT_INITIAL_APSIS_DEG,
    help="Initial apsis angle in degrees for apsidal_orbit.",
  )
  parser.add_argument(
    "--orbit-boundary-margin",
    type=float,
    default=DEFAULT_ORBIT_BOUNDARY_MARGIN,
    help="Margin from orbit bounds for apsidal_orbit.",
  )
  parser.add_argument(
    "--archimedean-x-min",
    type=float,
    default=None,
    help="Optional X min bound for archimedean_spiral (defaults to machine limitLeft).",
  )
  parser.add_argument(
    "--archimedean-x-max",
    type=float,
    default=None,
    help="Optional X max bound for archimedean_spiral (defaults to machine limitRight).",
  )
  parser.add_argument(
    "--archimedean-y-min",
    type=float,
    default=None,
    help="Optional Y min bound for archimedean_spiral (defaults to machine limitBottom).",
  )
  parser.add_argument(
    "--archimedean-y-max",
    type=float,
    default=None,
    help="Optional Y max bound for archimedean_spiral (defaults to machine limitTop).",
  )
  parser.add_argument(
    "--archimedean-turns",
    type=float,
    default=DEFAULT_ARCHIMEDEAN_TURNS,
    help="Number of turns for archimedean_spiral.",
  )
  parser.add_argument(
    "--archimedean-points-per-turn",
    type=int,
    default=DEFAULT_ARCHIMEDEAN_POINTS_PER_TURN,
    help="Discretization points per turn for archimedean_spiral.",
  )
  parser.add_argument(
    "--archimedean-initial-angle-deg",
    type=float,
    default=DEFAULT_ARCHIMEDEAN_INITIAL_ANGLE_DEG,
    help="Initial angle in degrees for archimedean_spiral.",
  )
  parser.add_argument(
    "--archimedean-boundary-margin",
    type=float,
    default=DEFAULT_ARCHIMEDEAN_BOUNDARY_MARGIN,
    help="Margin from bounds for archimedean_spiral.",
  )
  parser.add_argument(
    "--archimedean-direction",
    choices=("ccw", "cw"),
    default=DEFAULT_ARCHIMEDEAN_DIRECTION,
    help="Rotation direction for archimedean_spiral.",
  )
  parser.add_argument(
    "--waypoints",
    type=str,
    default="",
    help=(
      "Semicolon-delimited waypoint list: "
      "'x1,y1;x2,y2;...'. Used by waypoint_path."
    ),
  )
  parser.add_argument(
    "--waypoints-file",
    type=str,
    default="",
    help=(
      "Optional waypoint file for waypoint_path. "
      "Supports JSON list ([[x,y],...]) or CSV/text lines 'x,y'."
    ),
  )
  parser.add_argument(
    "--waypoint-order",
    choices=("input", "shortest"),
    default=DEFAULT_WAYPOINT_ORDER_MODE,
    help="Waypoint visitation order mode for waypoint_path.",
  )
  parser.add_argument(
    "--waypoint-min-arc-radius",
    type=float,
    default=DEFAULT_WAYPOINT_MIN_ARC_RADIUS,
    help="Minimum allowed radius for arc segments in waypoint_path.",
  )
  parser.add_argument(
    "--waypoint-allow-stops",
    action=argparse.BooleanOptionalAction,
    default=DEFAULT_WAYPOINT_ALLOW_STOPS,
    help=(
      "For waypoint_path, allow fallback to stop-and-restart linear transitions "
      "(term type 1 at non-tangential merges) when smooth biarc segments cannot "
      "fit within machine XY bounds."
    ),
  )
  parser.add_argument(
    "--v-x-max",
    type=float,
    default=DEFAULT_V_X_MAX,
    help=(
      "Maximum allowed X-axis velocity component magnitude. "
      "Segment speed is capped so |vx| <= v-x-max."
    ),
  )
  parser.add_argument(
    "--v-y-max",
    type=float,
    default=DEFAULT_V_Y_MAX,
    help=(
      "Maximum allowed Y-axis velocity component magnitude. "
      "Segment speed is capped so |vy| <= v-y-max."
    ),
  )
  parser.add_argument(
    "--queue-depth",
    type=int,
    default=PLC_QUEUE_DEPTH,
    help="Configured PLC FIFO depth used by the streaming enqueuer.",
  )
  parser.add_argument(
    "--min-segment-length",
    type=float,
    default=DEFAULT_MIN_SEGMENT_LENGTH,
    help="Minimum distance between consecutive queued segment endpoints.",
  )
  parser.add_argument(
    "--constant-velocity-mode",
    action=argparse.BooleanOptionalAction,
    default=DEFAULT_CONSTANT_VELOCITY_MODE,
    help=(
      "Tune segments for smoother single-velocity motion by enforcing segment "
      "length and speed constraints from v^2/(2a) and curvature."
    ),
  )
  parser.add_argument(
    "--curvature-speed-safety",
    type=float,
    default=DEFAULT_CURVATURE_SPEED_SAFETY,
    help="Safety factor (0.1..1.0) applied to curvature-based speed limit.",
  )
  parser.add_argument(
    "--min-jerk-ratio",
    type=float,
    default=DEFAULT_MIN_JERK_RATIO,
    help=(
      "Optional minimum jerk ratio relative to accel/decel used in "
      "constant-velocity mode. Use 0 to keep segment jerk defaults."
    ),
  )
  parser.add_argument(
    "--max-segment-factor",
    type=float,
    default=DEFAULT_MAX_SEGMENT_FACTOR,
    help=(
      "In constant-velocity mode, max segment length is "
      "max-segment-factor * effective-min-segment-length."
    ),
  )
  parser.add_argument(
    "--visualize-svg",
    type=str,
    default="",
    help="Write an SVG visualization of the planned path.",
  )
  parser.add_argument(
    "--position-seq",
    type=int,
    default=None,
    help="Sequence number to highlight as position in visualization.",
  )
  parser.add_argument(
    "--visualize-only",
    action="store_true",
    help="Generate visualization and skip PLC communication.",
  )
  parser.add_argument(
    "--machine-calibration",
    type=str,
    default="",
    help=(
      "Path to machine calibration JSON file (or directory containing it). "
      "Defaults to config/machineCalibration.json."
    ),
  )
  parser.add_argument(
    "--start-x",
    type=float,
    default=None,
    help="Optional current X position used to validate first queued move.",
  )
  parser.add_argument(
    "--start-y",
    type=float,
    default=None,
    help="Optional current Y position used to validate first queued move.",
  )
  return parser.parse_args()


def _parse_waypoint_text(text: str) -> list[tuple[float, float]]:
  points: list[tuple[float, float]] = []
  if not text.strip():
    return points

  chunks = text.replace("\n", ";").split(";")
  for chunk in chunks:
    token = chunk.strip()
    if not token:
      continue
    parts = [part.strip() for part in token.split(",")]
    if len(parts) != 2:
      raise ValueError(
        f"Invalid waypoint token '{token}'. Expected format 'x,y'."
      )
    points.append((float(parts[0]), float(parts[1])))

  return points


def _load_waypoints_file(path: str) -> list[tuple[float, float]]:
  file_path = Path(path)
  raw = file_path.read_text(encoding="utf-8-sig")
  if file_path.suffix.lower() == ".json":
    data = json.loads(raw)
    if not isinstance(data, list):
      raise ValueError("waypoints JSON must be a list")
    points: list[tuple[float, float]] = []
    for idx, item in enumerate(data):
      if isinstance(item, dict):
        if "x" not in item or "y" not in item:
          raise ValueError(f"waypoints JSON item {idx} must contain x and y")
        points.append((float(item["x"]), float(item["y"])))
      elif isinstance(item, (list, tuple)) and len(item) == 2:
        points.append((float(item[0]), float(item[1])))
      else:
        raise ValueError(
          f"waypoints JSON item {idx} must be [x,y] or {{'x':..,'y':..}}"
        )
    return points

  # CSV/text fallback: one waypoint per line, "x,y"
  points: list[tuple[float, float]] = []
  for idx, line in enumerate(raw.splitlines(), start=1):
    token = line.strip()
    if not token:
      continue
    parts = [part.strip() for part in token.split(",")]
    if len(parts) != 2:
      raise ValueError(
        f"Invalid waypoint line {idx} in {file_path}: expected 'x,y'"
      )
    points.append((float(parts[0]), float(parts[1])))
  return points


def _collect_waypoints(args: argparse.Namespace) -> list[tuple[float, float]]:
  points: list[tuple[float, float]] = []
  if args.waypoints_file:
    points.extend(_load_waypoints_file(args.waypoints_file))
  if args.waypoints:
    points.extend(_parse_waypoint_text(args.waypoints))
  return points


def main() -> None:
  args = parse_args()
  if (args.start_x is None) != (args.start_y is None):
    raise ValueError("Specify both --start-x and --start-y together.")

  if args.gui:
    from motionQueueTest_gui import WaypointPlannerApp

    app = WaypointPlannerApp(
      plc_path=PLC_PATH,
      machine_calibration=args.machine_calibration or "",
    )
    app.allow_stops_var.set(bool(args.waypoint_allow_stops))
    if args.start_x is not None and args.start_y is not None:
      app.start_x_var.set(str(float(args.start_x)))
      app.start_y_var.set(str(float(args.start_y)))
    app.mainloop()
    return

  start_xy = None if args.start_x is None else (float(args.start_x), float(args.start_y))
  waypoint_points = _collect_waypoints(args)
  if args.pattern == "waypoint_path" and len(waypoint_points) < 2:
    raise ValueError(
      "waypoint_path requires at least two waypoints via --waypoints and/or --waypoints-file"
    )
  safety_limits = load_motion_safety_limits(args.machine_calibration or None)
  term_types = list(TESTABLE_TERM_TYPES) if args.sweep_term_types else [args.term_type]
  failures: list[tuple[int, Exception]] = []

  def build_case_segments(term_type: int) -> tuple[list[MotionSegment], float]:
    orbit_x_min = (
      safety_limits.limit_left if args.orbit_x_min is None else args.orbit_x_min
    )
    orbit_x_max = (
      safety_limits.limit_right if args.orbit_x_max is None else args.orbit_x_max
    )
    orbit_y_min = (
      safety_limits.limit_bottom if args.orbit_y_min is None else args.orbit_y_min
    )
    orbit_y_max = (
      safety_limits.limit_top if args.orbit_y_max is None else args.orbit_y_max
    )
    archimedean_x_min = (
      safety_limits.limit_left
      if args.archimedean_x_min is None
      else args.archimedean_x_min
    )
    archimedean_x_max = (
      safety_limits.limit_right
      if args.archimedean_x_max is None
      else args.archimedean_x_max
    )
    archimedean_y_min = (
      safety_limits.limit_bottom
      if args.archimedean_y_min is None
      else args.archimedean_y_min
    )
    archimedean_y_max = (
      safety_limits.limit_top
      if args.archimedean_y_max is None
      else args.archimedean_y_max
    )

    segments = build_segments(
      pattern=args.pattern,
      start_seq=args.start_seq,
      term_type=term_type,
      lissajous_segments_count=args.lissajous_segments,
      min_segment_length=args.min_segment_length,
      fibonacci_arc_count=args.fibonacci_arc_count,
      fibonacci_x_min=args.fibonacci_x_min,
      fibonacci_x_max=args.fibonacci_x_max,
      fibonacci_y_min=args.fibonacci_y_min,
      fibonacci_y_max=args.fibonacci_y_max,
      fibonacci_direction=args.fibonacci_direction,
      orbit_x_min=orbit_x_min,
      orbit_x_max=orbit_x_max,
      orbit_y_min=orbit_y_min,
      orbit_y_max=orbit_y_max,
      orbit_revolutions=args.orbit_revolutions,
      orbit_points_per_revolution=args.orbit_points_per_rev,
      orbit_eccentricity=args.orbit_eccentricity,
      orbit_precession_deg_per_revolution=args.orbit_precession_deg_per_rev,
      orbit_initial_apsis_deg=args.orbit_initial_apsis_deg,
      orbit_boundary_margin=args.orbit_boundary_margin,
      archimedean_x_min=archimedean_x_min,
      archimedean_x_max=archimedean_x_max,
      archimedean_y_min=archimedean_y_min,
      archimedean_y_max=archimedean_y_max,
      archimedean_turns=args.archimedean_turns,
      archimedean_points_per_turn=args.archimedean_points_per_turn,
      archimedean_initial_angle_deg=args.archimedean_initial_angle_deg,
      archimedean_boundary_margin=args.archimedean_boundary_margin,
      archimedean_direction=args.archimedean_direction,
      waypoint_points=waypoint_points,
      waypoint_min_arc_radius=args.waypoint_min_arc_radius,
      waypoint_order_mode=args.waypoint_order,
      waypoint_start_xy=start_xy,
      waypoint_bounds=(
        safety_limits.limit_left,
        safety_limits.limit_right,
        safety_limits.limit_bottom,
        safety_limits.limit_top,
      ),
      waypoint_allow_stops=args.waypoint_allow_stops,
    )
    effective_min_segment_length = args.min_segment_length

    if args.constant_velocity_mode:
      segments, effective_min_segment_length, vmax_by_curvature, kmax = (
        tune_segments_for_constant_velocity(
          segments=segments,
          requested_min_segment_length=args.min_segment_length,
          curvature_speed_safety=args.curvature_speed_safety,
          min_jerk_ratio=args.min_jerk_ratio,
          max_segment_factor=args.max_segment_factor,
        )
      )
      print(
        "Constant-velocity tuning: "
        f"effective_min_segment_length={effective_min_segment_length:.2f} "
        f"max_segment_length={effective_min_segment_length * args.max_segment_factor:.2f} "
        f"kmax={kmax:.5f} "
        f"curvature_speed_limit={vmax_by_curvature:.2f} "
        f"configured_speed={segments[0].speed:.2f}"
      )

    before_caps = [float(seg.speed) for seg in segments]
    segments = cap_segments_speed_by_axis_velocity(
      segments=segments,
      v_x_max=float(args.v_x_max),
      v_y_max=float(args.v_y_max),
      start_xy=start_xy,
    )
    after_caps = [float(seg.speed) for seg in segments]
    if before_caps and after_caps and (
      not math.isinf(float(args.v_x_max)) or not math.isinf(float(args.v_y_max))
    ):
      print(
        "Axis-component speed capping: "
        f"v_x_max={args.v_x_max:.2f} "
        f"v_y_max={args.v_y_max:.2f} "
        f"speed[min/max]={min(after_caps):.2f}/{max(after_caps):.2f}"
      )
      if start_xy is None:
        print(
          "Axis-component speed capping note: "
          "start XY is unknown, so the first segment is conservatively "
          "capped to min(v_x_max, v_y_max). "
          "Set --start-x/--start-y for exact first-segment capping."
        )

    tangential_term_type = (
      term_type if args.tangential_term_type is None else args.tangential_term_type
    )
    non_tangential_term_type = args.non_tangential_term_type
    if (
      args.pattern == "waypoint_path"
      and args.waypoint_allow_stops
      and non_tangential_term_type == 0
    ):
      non_tangential_term_type = 1

    segments = apply_merge_term_types(
      segments,
      start_xy=start_xy,
      tangential_term_type=tangential_term_type,
      non_tangential_term_type=non_tangential_term_type,
      final_term_type=args.final_term_type,
    )

    return segments, effective_min_segment_length

  def maybe_write_visual(term_type: int, segments: list[MotionSegment]) -> None:
    if not args.visualize_svg:
      return
    out = Path(args.visualize_svg)
    if args.sweep_term_types:
      out = out.with_name(f"{out.stem}_tt{term_type}{out.suffix or '.svg'}")
    write_segments_svg(
      segments=segments,
      output_path=str(out),
      title=f"{args.pattern} term_type={term_type}",
      position_seq=args.position_seq,
    )
    print(f"Wrote visualization: {out}")

  def enforce_motion_safety(
    term_type: int,
    segments: list[MotionSegment],
    limits: MotionSafetyLimits,
  ) -> None:
    validate_segments_within_safety_limits(segments, limits, start_xy=start_xy)
    print(
      "Safety bounds check passed: "
      f"term_type={term_type} "
      f"box=[{limits.limit_left:.1f},{limits.limit_bottom:.1f}].."
      f"[{limits.limit_right:.1f},{limits.limit_top:.1f}] "
      f"pivot_center=({limits.headward_pivot_x:.1f},{limits.headward_pivot_y:.1f}) "
      f"pivot_half=({limits.headward_pivot_x_tolerance:.1f},{limits.headward_pivot_y_tolerance:.1f})"
    )

  if args.visualize_only:
    for term_type in term_types:
      print("\n" + "=" * 60)
      print(f"Visualizing pattern={args.pattern} term_type={term_type}")
      print("=" * 60)
      segments, effective_min_segment_length = build_case_segments(term_type)
      enforce_motion_safety(term_type, segments, safety_limits)
      print_pattern_summary(
        args.pattern,
        term_type,
        segments,
        min_segment_length=effective_min_segment_length,
      )
      maybe_write_visual(term_type, segments)
    return

  with MotionQueueClient(PLC_PATH) as motion:
    for term_type in term_types:
      print("\n" + "=" * 60)
      print(f"Running pattern={args.pattern} term_type={term_type}")
      print("=" * 60)

      segments, effective_min_segment_length = build_case_segments(term_type)
      enforce_motion_safety(term_type, segments, safety_limits)
      print_pattern_summary(
        args.pattern,
        term_type,
        segments,
        min_segment_length=effective_min_segment_length,
      )
      maybe_write_visual(term_type, segments)

      try:
        run_queue_case(motion, segments, queue_depth=args.queue_depth)
      except Exception as exc:
        if not args.sweep_term_types:
          raise
        failures.append((term_type, exc))
        print(f"Run failed for term_type={term_type}: {exc}")

  if args.sweep_term_types:
    print("\nTermination type sweep summary:")
    for term_type in term_types:
      status = "FAIL" if any(f[0] == term_type for f in failures) else "PASS"
      print(f"  term_type={term_type}: {status}")
    if failures:
      raise RuntimeError(f"{len(failures)} termination-type run(s) failed.")


if __name__ == "__main__":
  main()
