from __future__ import annotations

import argparse
from pathlib import Path

from dune_winder.motion import (
  DEFAULT_CONSTANT_VELOCITY_MODE,
  DEFAULT_CURVATURE_SPEED_SAFETY,
  DEFAULT_FIBONACCI_ARC_COUNT,
  DEFAULT_FIBONACCI_SCALE,
  DEFAULT_MAX_SEGMENT_FACTOR,
  DEFAULT_MIN_JERK_RATIO,
  DEFAULT_MIN_SEGMENT_LENGTH,
  DEFAULT_TEST_TERM_TYPE,
  LISSAJOUS_TESSELLATION_SEGMENTS,
  MotionQueueClient,
  MotionSegment,
  PLC_QUEUE_DEPTH,
  TESTABLE_TERM_TYPES,
  build_segments,
  print_pattern_summary,
  run_queue_case,
  tune_segments_for_constant_velocity,
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
    choices=("lissajous", "square", "simple", "tangent_mix", "fibonacci_arcs"),
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
    "--fibonacci-scale",
    type=float,
    default=DEFAULT_FIBONACCI_SCALE,
    help="Scale factor applied to Fibonacci radii.",
  )
  parser.add_argument(
    "--fibonacci-ccw",
    action=argparse.BooleanOptionalAction,
    default=True,
    help="Rotate Fibonacci spiral CCW (or CW with --no-fibonacci-ccw).",
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
    help="Minimum jerk ratio relative to accel/decel used in constant-velocity mode.",
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
  return parser.parse_args()


def main() -> None:
  args = parse_args()
  term_types = list(TESTABLE_TERM_TYPES) if args.sweep_term_types else [args.term_type]
  failures: list[tuple[int, Exception]] = []

  def build_case_segments(term_type: int) -> tuple[list[MotionSegment], float]:
    segments = build_segments(
      pattern=args.pattern,
      start_seq=args.start_seq,
      term_type=term_type,
      lissajous_segments_count=args.lissajous_segments,
      min_segment_length=args.min_segment_length,
      fibonacci_arc_count=args.fibonacci_arc_count,
      fibonacci_scale=args.fibonacci_scale,
      fibonacci_ccw=args.fibonacci_ccw,
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

  if args.visualize_only:
    for term_type in term_types:
      print("\n" + "=" * 60)
      print(f"Visualizing pattern={args.pattern} term_type={term_type}")
      print("=" * 60)
      segments, effective_min_segment_length = build_case_segments(term_type)
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
