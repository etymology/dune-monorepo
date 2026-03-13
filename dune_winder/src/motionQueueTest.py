from __future__ import annotations

import argparse
from pathlib import Path

from dune_winder.motion import (
  DEFAULT_CONSTANT_VELOCITY_MODE,
  DEFAULT_CURVATURE_SPEED_SAFETY,
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
    ),
    default="lissajous",
    help="Path pattern to enqueue.",
  )
  parser.add_argument(
    "--term-type",
    type=int,
    default=DEFAULT_TEST_TERM_TYPE,
    choices=TESTABLE_TERM_TYPES,
    help="Termination type for all queued segments in the run.",
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
      "Tune segments for smoother single-velocity motion: force TT4 interior, "
      "TT1 final, enforce minimum length from v^2/(2a), and cap speed by curvature."
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


def main() -> None:
  args = parse_args()
  if (args.start_x is None) != (args.start_y is None):
    raise ValueError("Specify both --start-x and --start-y together.")

  start_xy = None if args.start_x is None else (float(args.start_x), float(args.start_y))
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

    segments = apply_merge_term_types(
      segments,
      start_xy=start_xy,
      tangential_term_type=4,
      non_tangential_term_type=0,
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
