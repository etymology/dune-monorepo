from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import asdict
from dataclasses import dataclass

from dune_winder.queued_motion.queue_client import MotionQueueClient
from dune_winder.queued_motion.safety import load_motion_safety_limits
from dune_winder.queued_motion.safety import validate_segments_within_safety_limits
from dune_winder.queued_motion.segment_patterns import _segment_tangent_component_bounds
from dune_winder.queued_motion.segment_types import (
  CIRCLE_TYPE_CENTER,
  MCCM_DIR_2D_CCW,
  MCCM_DIR_2D_CW,
  MotionSegment,
  SEG_TYPE_CIRCLE,
)


DEFAULT_PLC_PATH = "192.168.140.13"
DEFAULT_TOLERANCE = 0.05
DEFAULT_POLL_DELAY_S = 0.25
_STEP_CANDIDATES = (100.0, 75.0, 50.0, 25.0)


@dataclass(frozen=True)
class QueueCapCase:
  name: str
  segments: list[MotionSegment]
  start_xy: tuple[float, float]


def _preferred_direction(value: float, low: float, high: float) -> int:
  return -1 if value >= ((low + high) * 0.5) else 1


def _candidate_directions(value: float, low: float, high: float) -> list[int]:
  preferred = _preferred_direction(value, low, high)
  return [preferred, -preferred]


def _available_distance(value: float, low: float, high: float, direction: int, margin: float) -> float:
  if direction < 0:
    return max(0.0, value - (low + margin))
  return max(0.0, (high - margin) - value)


def _expected_capped_speed(
  start_xy: tuple[float, float],
  segment: MotionSegment,
  v_x_max: float,
  v_y_max: float,
) -> float:
  max_tx, max_ty = _segment_tangent_component_bounds(start_xy[0], start_xy[1], segment)
  limit_x = math.inf if max_tx <= 1e-9 else (v_x_max / max_tx)
  limit_y = math.inf if max_ty <= 1e-9 else (v_y_max / max_ty)
  return min(float(segment.speed), limit_x, limit_y)


def _build_line_case(
  start_xy: tuple[float, float],
  limits,
  collision_state,
) -> QueueCapCase:
  start_x, start_y = float(start_xy[0]), float(start_xy[1])
  x_dirs = _candidate_directions(start_x, limits.limit_left, limits.limit_right)
  y_dirs = _candidate_directions(start_y, limits.limit_bottom, limits.limit_top)

  for x_dir in x_dirs:
    for y_dir in y_dirs:
      x_room = _available_distance(start_x, limits.limit_left, limits.limit_right, x_dir, 25.0) / 2.0
      y_room = _available_distance(start_y, limits.limit_bottom, limits.limit_top, y_dir, 25.0)
      for base_step in _STEP_CANDIDATES:
        step = min(base_step, x_room, y_room)
        if step < 10.0:
          continue
        seg1 = MotionSegment(
          seq=7001,
          x=start_x + (x_dir * step),
          y=start_y + (y_dir * step),
          speed=9999.0,
        )
        seg2 = MotionSegment(
          seq=7002,
          x=start_x + (x_dir * 2.0 * step),
          y=start_y + (y_dir * step),
          speed=9999.0,
        )
        try:
          validate_segments_within_safety_limits(
            [seg1, seg2],
            limits,
            start_xy=start_xy,
            queued_motion_collision_state=collision_state,
          )
        except ValueError:
          continue
        return QueueCapCase("line_pair", [seg1, seg2], start_xy)
  raise RuntimeError("Could not build a safe line_pair queue-cap test case from the current position")


def _build_circle_case(
  start_xy: tuple[float, float],
  limits,
  collision_state,
) -> QueueCapCase:
  start_x, start_y = float(start_xy[0]), float(start_xy[1])
  x_dirs = _candidate_directions(start_x, limits.limit_left, limits.limit_right)
  y_dirs = _candidate_directions(start_y, limits.limit_bottom, limits.limit_top)

  for x_dir in x_dirs:
    for y_dir in y_dirs:
      x_room = _available_distance(start_x, limits.limit_left, limits.limit_right, x_dir, 25.0)
      y_room = _available_distance(start_y, limits.limit_bottom, limits.limit_top, y_dir, 25.0)
      for base_step in _STEP_CANDIDATES:
        step = min(base_step, x_room, y_room)
        if step < 10.0:
          continue
        end_x = start_x + (x_dir * step)
        end_y = start_y + (y_dir * step)
        direction = MCCM_DIR_2D_CCW if (x_dir * y_dir) < 0 else MCCM_DIR_2D_CW
        segment = MotionSegment(
          seq=7101,
          x=end_x,
          y=end_y,
          speed=9999.0,
          seg_type=SEG_TYPE_CIRCLE,
          circle_type=CIRCLE_TYPE_CENTER,
          via_center_x=end_x,
          via_center_y=start_y,
          direction=direction,
        )
        try:
          validate_segments_within_safety_limits(
            [segment],
            limits,
            start_xy=start_xy,
            queued_motion_collision_state=collision_state,
          )
        except ValueError:
          continue
        return QueueCapCase("circle_single", [segment], start_xy)
  raise RuntimeError("Could not build a safe circle_single queue-cap test case from the current position")


def _run_case(
  motion: MotionQueueClient,
  case: QueueCapCase,
  *,
  v_x_max: float,
  v_y_max: float,
  poll_delay_s: float,
  tolerance: float,
) -> dict[str, object]:
  queue = motion._require_queue()
  motion.reset_queue()
  queue.poll()
  actual_start_xy = queue.read_actual_xy()
  motion.set_start_point(*actual_start_xy)

  for segment in case.segments:
    motion.enqueue_segment(segment)

  time.sleep(poll_delay_s)
  queue.poll()
  status = queue.status()
  start_flag = bool(queue._read_one("StartQueuedPath"))
  speeds = queue.read_seg_queue_speeds(len(case.segments))
  seqs = [int(queue._read_one(f"SegQueue[{i}].Seq")) for i in range(len(case.segments))]
  xy = [
    (
      float(queue._read_one(f"SegQueue[{i}].XY[0]")),
      float(queue._read_one(f"SegQueue[{i}].XY[1]")),
    )
    for i in range(len(case.segments))
  ]

  expected = []
  cursor_xy = actual_start_xy
  for segment in case.segments:
    expected.append(_expected_capped_speed(cursor_xy, segment, v_x_max, v_y_max))
    cursor_xy = (float(segment.x), float(segment.y))

  comparisons = []
  comparisons_ok = True
  for index, (actual_speed, expected_speed) in enumerate(zip(speeds, expected)):
    abs_diff = abs(actual_speed - expected_speed)
    speed_ok = abs_diff <= tolerance
    comparisons_ok = comparisons_ok and speed_ok
    comparisons.append(
      {
        "index": index,
        "actual_speed": actual_speed,
        "expected_speed": expected_speed,
        "abs_diff": abs_diff,
        "within_tolerance": speed_ok,
      }
    )

  queue_state_ok = (
    status.queue_count == len(case.segments)
    and (not status.cur_issued)
    and (not status.next_issued)
    and (not status.queue_fault)
    and (not status.motion_fault)
    and (not start_flag)
  )

  return {
    "name": case.name,
    "start_xy": [float(actual_start_xy[0]), float(actual_start_xy[1])],
    "segments": [asdict(segment) for segment in case.segments],
    "status": {
      "queue_count": status.queue_count,
      "cur_issued": status.cur_issued,
      "next_issued": status.next_issued,
      "queue_fault": status.queue_fault,
      "motion_fault": status.motion_fault,
      "start_flag": start_flag,
      "ack": status.ack,
    },
    "queue_readback": {
      "seqs": seqs,
      "xy": [[float(px), float(py)] for px, py in xy],
      "speeds": speeds,
    },
    "expected_speeds": expected,
    "comparisons": comparisons,
    "passed": bool(queue_state_ok and comparisons_ok),
  }


def run_check(
  plc_path: str,
  *,
  tolerance: float = DEFAULT_TOLERANCE,
  poll_delay_s: float = DEFAULT_POLL_DELAY_S,
) -> dict[str, object]:
  report: dict[str, object] = {
    "plc_path": plc_path,
    "tolerance": tolerance,
    "poll_delay_s": poll_delay_s,
    "cases": [],
    "cleanup": {},
    "passed": False,
  }

  with MotionQueueClient(plc_path) as motion:
    queue = motion._require_queue()
    queue.poll()
    initial_status = queue.status()
    initial_start_flag = bool(queue._read_one("StartQueuedPath"))
    initial_actual_xy = queue.read_actual_xy()
    v_x_max = float(queue._read_one("v_x_max"))
    v_y_max = float(queue._read_one("v_y_max"))

    report["initial"] = {
      "queue_count": initial_status.queue_count,
      "cur_issued": initial_status.cur_issued,
      "next_issued": initial_status.next_issued,
      "queue_fault": initial_status.queue_fault,
      "motion_fault": initial_status.motion_fault,
      "start_flag": initial_start_flag,
      "actual_xy": [float(initial_actual_xy[0]), float(initial_actual_xy[1])],
      "v_x_max": v_x_max,
      "v_y_max": v_y_max,
    }

    if (
      initial_status.queue_count != 0
      or initial_status.cur_issued
      or initial_status.next_issued
      or initial_status.queue_fault
      or initial_status.motion_fault
      or initial_start_flag
    ):
      raise RuntimeError("Refusing to run because the PLC queue is not idle and fault-free")

    limits = load_motion_safety_limits()
    collision_state = queue.read_collision_state()
    line_case = _build_line_case(initial_actual_xy, limits, collision_state)
    circle_case = _build_circle_case(initial_actual_xy, limits, collision_state)

    try:
      report["cases"].append(
        _run_case(
          motion,
          line_case,
          v_x_max=v_x_max,
          v_y_max=v_y_max,
          poll_delay_s=poll_delay_s,
          tolerance=tolerance,
        )
      )
      report["cases"].append(
        _run_case(
          motion,
          circle_case,
          v_x_max=v_x_max,
          v_y_max=v_y_max,
          poll_delay_s=poll_delay_s,
          tolerance=tolerance,
        )
      )
    finally:
      motion.reset_queue()
      queue.poll()
      final_status = queue.status()
      report["cleanup"] = {
        "queue_count": final_status.queue_count,
        "cur_issued": final_status.cur_issued,
        "next_issued": final_status.next_issued,
        "queue_fault": final_status.queue_fault,
        "motion_fault": final_status.motion_fault,
      }

    report["passed"] = bool(
      report["cases"]
      and all(case["passed"] for case in report["cases"])
      and report["cleanup"]["queue_count"] == 0
      and (not report["cleanup"]["cur_issued"])
      and (not report["cleanup"]["next_issued"])
      and (not report["cleanup"]["queue_fault"])
      and (not report["cleanup"]["motion_fault"])
    )
  return report


def build_argument_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description=(
      "Write queued-motion segments to the PLC without starting motion and verify "
      "that the ladder caps their speeds in-place."
    )
  )
  parser.add_argument(
    "plc_path",
    nargs="?",
    default=DEFAULT_PLC_PATH,
    help="PLC IP or pycomm3 path. Defaults to 192.168.140.13.",
  )
  parser.add_argument(
    "--tolerance",
    type=float,
    default=DEFAULT_TOLERANCE,
    help="Maximum allowed absolute speed error when comparing expected vs readback speeds.",
  )
  parser.add_argument(
    "--poll-delay-s",
    type=float,
    default=DEFAULT_POLL_DELAY_S,
    help="Delay after enqueue before reading queue tags back from the PLC.",
  )
  return parser


def main(argv: list[str] | None = None) -> int:
  parser = build_argument_parser()
  args = parser.parse_args(argv)
  try:
    report = run_check(
      args.plc_path,
      tolerance=float(args.tolerance),
      poll_delay_s=float(args.poll_delay_s),
    )
  except Exception as exc:
    print(
      json.dumps(
        {
          "plc_path": args.plc_path,
          "passed": False,
          "error": str(exc),
        },
        indent=2,
      )
    )
    return 1

  print(json.dumps(report, indent=2))
  return 0 if report["passed"] else 1


if __name__ == "__main__":
  raise SystemExit(main())
