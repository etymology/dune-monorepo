from __future__ import annotations

import argparse
import math

from dune_winder.queued_motion.queue_client_3d_arc import (
  DIR_3D_SHORTEST,
  MotionArc3DSegment,
  MotionArc3DQueueClient,
  PLC_QUEUE_DEPTH_3D,
  run_arc3d_queue_case,
)


DEFAULT_PLC_PATH = "192.168.140.13"


def _normalize(v: tuple[float, float, float]) -> tuple[float, float, float]:
  mag = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
  if mag <= 1e-9:
    raise ValueError("normal vector magnitude must be > 0")
  return (v[0] / mag, v[1] / mag, v[2] / mag)


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
  return (
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  )


def _rotate_about_axis(
  vector: tuple[float, float, float],
  axis_unit: tuple[float, float, float],
  angle_rad: float,
) -> tuple[float, float, float]:
  ux, uy, uz = axis_unit
  vx, vy, vz = vector
  cos_a = math.cos(angle_rad)
  sin_a = math.sin(angle_rad)

  cross = _cross(axis_unit, vector)
  dot = ux * vx + uy * vy + uz * vz

  return (
    vx * cos_a + cross[0] * sin_a + ux * dot * (1.0 - cos_a),
    vy * cos_a + cross[1] * sin_a + uy * dot * (1.0 - cos_a),
    vz * cos_a + cross[2] * sin_a + uz * dot * (1.0 - cos_a),
  )


def build_demo_segments(
  start_xyz: tuple[float, float, float],
  radius: float,
  term_type: int,
  normal_xyz: tuple[float, float, float],
) -> list[MotionArc3DSegment]:
  if radius <= 0.0:
    raise ValueError("radius must be > 0")

  nx, ny, nz = _normalize(normal_xyz)
  sx, sy, sz = start_xyz

  helper = (1.0, 0.0, 0.0)
  if abs(nx) > 0.95:
    helper = (0.0, 1.0, 0.0)

  radial_dir = _cross((nx, ny, nz), helper)
  radial_dir = _normalize(radial_dir)

  center = (
    sx - radial_dir[0] * radius,
    sy - radial_dir[1] * radius,
    sz - radial_dir[2] * radius,
  )

  start_radius_vec = (
    sx - center[0],
    sy - center[1],
    sz - center[2],
  )

  mid_radius_vec = _rotate_about_axis(start_radius_vec, (nx, ny, nz), math.pi / 2.0)
  end_radius_vec = _rotate_about_axis(start_radius_vec, (nx, ny, nz), math.pi)

  mid = (
    center[0] + mid_radius_vec[0],
    center[1] + mid_radius_vec[1],
    center[2] + mid_radius_vec[2],
  )
  end = (
    center[0] + end_radius_vec[0],
    center[1] + end_radius_vec[1],
    center[2] + end_radius_vec[2],
  )

  return [
    MotionArc3DSegment(
      seq=100,
      x=mid[0],
      y=mid[1],
      z=mid[2],
      via_center_x=center[0],
      via_center_y=center[1],
      via_center_z=center[2],
      term_type=term_type,
      direction=DIR_3D_SHORTEST,
    ),
    MotionArc3DSegment(
      seq=101,
      x=end[0],
      y=end[1],
      z=end[2],
      via_center_x=center[0],
      via_center_y=center[1],
      via_center_z=center[2],
      term_type=term_type,
      direction=DIR_3D_SHORTEST,
    ),
  ]


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description="Development runner for the isolated 3D arc queue branch."
  )
  parser.add_argument("--plc-path", type=str, default=DEFAULT_PLC_PATH)
  parser.add_argument("--start-x", type=float, default=1200.0)
  parser.add_argument("--start-y", type=float, default=800.0)
  parser.add_argument("--start-z", type=float, default=120.0)
  parser.add_argument("--radius", type=float, default=250.0)
  parser.add_argument("--term-type", type=int, default=3)
  parser.add_argument("--normal-x", type=float, default=0.25)
  parser.add_argument("--normal-y", type=float, default=0.35)
  parser.add_argument("--normal-z", type=float, default=1.0)
  parser.add_argument("--queue-depth", type=int, default=PLC_QUEUE_DEPTH_3D)
  parser.add_argument("--dry-run", action="store_true")
  return parser.parse_args()


def main() -> None:
  args = parse_args()

  start = (float(args.start_x), float(args.start_y), float(args.start_z))
  normal = (float(args.normal_x), float(args.normal_y), float(args.normal_z))
  segments = build_demo_segments(
    start_xyz=start,
    radius=float(args.radius),
    term_type=int(args.term_type),
    normal_xyz=normal,
  )

  print("Built demo 3D arc segments:")
  for seg in segments:
    print(
      f"  seq={seg.seq} target=({seg.x:.3f}, {seg.y:.3f}, {seg.z:.3f}) "
      f"center=({seg.via_center_x:.3f}, {seg.via_center_y:.3f}, {seg.via_center_z:.3f}) "
      f"direction={seg.direction}"
    )

  if args.dry_run:
    return

  with MotionArc3DQueueClient(args.plc_path) as motion:
    motion.set_start_point(*start)
    run_arc3d_queue_case(
      motion=motion,
      segments=segments,
      queue_depth=int(args.queue_depth),
    )


if __name__ == "__main__":
  main()
