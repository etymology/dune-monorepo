from __future__ import annotations

import argparse
import colorsys
import math
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Optional

from pycomm3 import LogixDriver


# -----------------------------
# Configuration
# -----------------------------

PLC_PATH = "192.168.140.13"  # change to your PLC IP/slot

# Required controller-scope tags
TAG_INCOMING_SEG = "IncomingSeg"
TAG_REQ_ID = "IncomingSegReqID"
TAG_LAST_REQ_ID = "LastIncomingSegReqID"
TAG_ACK = "IncomingSegAck"
TAG_ABORT = "AbortQueue"
TAG_START = "StartQueuedPath"

# Optional diagnostics; set to None if not exposed as controller tags
TAG_MOTION_FAULT = "MotionFault"
TAG_CUR_ISSUED = "CurIssued"
TAG_NEXT_ISSUED = "NextIssued"
TAG_ACTIVE_SEQ = "ActiveSeq"
TAG_PENDING_SEQ = "PendingSeq"
TAG_QUEUE_FAULT = "QueueFault"
TAG_MOVE_A_ER = "moveA.ER"
TAG_MOVE_B_ER = "moveB.ER"
TAG_QUEUE_COUNT = "QueueCount"
TAG_USE_A_AS_CURRENT = "UseAasCurrent"
TAG_MOVE_PENDING_STATUS = "X_Y.MovePendingStatus"
TAG_FAULT_CODE = "FaultCode"

ACK_TIMEOUT_S = 5.0
POLL_S = 0.05
ABORT_PULSE_S = 0.10
START_PULSE_S = 0.10
POST_RESET_SETTLE_S = 0.10
START_TIMEOUT_S = 5.0
IDLE_TIMEOUT_S = 120.0
LISSAJOUS_TESSELLATION_SEGMENTS = 400

PLC_QUEUE_DEPTH = 32
TESTABLE_TERM_TYPES = (0, 1, 2, 3, 4, 5, 6)
DEFAULT_TEST_TERM_TYPE = 4
DEFAULT_MIN_SEGMENT_LENGTH = 0.0
DEFAULT_CONSTANT_VELOCITY_MODE = True
DEFAULT_CURVATURE_SPEED_SAFETY = 0.92
DEFAULT_MIN_JERK_RATIO = 10.0
DEFAULT_MAX_SEGMENT_FACTOR = 4.0


# -----------------------------
# Data model
# -----------------------------


@dataclass(frozen=True)
class MotionSegment:
  seq: int
  x: float
  y: float
  speed: float = 600.0
  accel: float = 2000.0
  decel: float = 2000.0
  jerk_accel: float = 10000.0
  jerk_decel: float = 10000.0
  term_type: int = DEFAULT_TEST_TERM_TYPE  # Command Tolerance Programmed
  seg_type: int = 1  # line


# -----------------------------
# PLC queue client
# -----------------------------


class MotionQueueClient:
  def __init__(
    self,
    path: str,
    ack_timeout_s: float = ACK_TIMEOUT_S,
    poll_s: float = POLL_S,
  ) -> None:
    self.path = path
    self.ack_timeout_s = ack_timeout_s
    self.poll_s = poll_s
    self.plc: Optional[LogixDriver] = None
    self.req_id = 0

  def __enter__(self) -> "MotionQueueClient":
    self.plc = LogixDriver(self.path, init_tags=True, init_program_tags=False)
    self.plc.open()
    self._sync_req_id_from_plc()
    return self

  def __exit__(self, exc_type, exc, tb) -> None:
    if self.plc is not None:
      self.plc.close()
      self.plc = None

  def _require_plc(self) -> LogixDriver:
    if self.plc is None:
      raise RuntimeError("PLC connection is not open")
    return self.plc

  def _read_one(self, tag: str):
    result = self._require_plc().read(tag)
    if result.error:
      raise RuntimeError(f"Read failed for {tag}: {result.error}")
    return result.value

  def _try_read_one(self, tag: Optional[str]):
    if not tag:
      return None
    try:
      return self._read_one(tag)
    except Exception:
      return None

  def _write_one(self, tag: str, value) -> None:
    result = self._require_plc().write((tag, value))
    if result.error:
      raise RuntimeError(f"Write failed for {tag}: {result.error}")

  def _sync_req_id_from_plc(self) -> None:
    last_req = self._try_read_one(TAG_LAST_REQ_ID)
    if last_req is not None:
      self.req_id = int(last_req)
      return

    req = self._try_read_one(TAG_REQ_ID)
    if req is not None:
      self.req_id = int(req)
      return

    self.req_id = 0

  def reset_queue(self) -> None:
    print("Resetting PLC queue...")
    self._write_one(TAG_ABORT, True)
    time.sleep(ABORT_PULSE_S)
    self._write_one(TAG_ABORT, False)
    time.sleep(POST_RESET_SETTLE_S)
    self._sync_req_id_from_plc()
    print(f"Reset complete. ReqID synchronized to {self.req_id}")

  @staticmethod
  def _segment_to_udt(seg: MotionSegment) -> dict:
    return {
      "Valid": True,
      "SegType": int(seg.seg_type),
      "X": float(seg.x),
      "Y": float(seg.y),
      "Speed": float(seg.speed),
      "Accel": float(seg.accel),
      "Decel": float(seg.decel),
      "JerkAccel": float(seg.jerk_accel),
      "JerkDecel": float(seg.jerk_decel),
      "TermType": int(seg.term_type),
      "Seq": int(seg.seq),
    }

  def _wait_for_ack(self, seq: int) -> None:
    deadline = time.monotonic() + self.ack_timeout_s
    while time.monotonic() < deadline:
      ack = int(self._read_one(TAG_ACK))
      if ack == seq:
        return

      motion_fault = self._try_read_one(TAG_MOTION_FAULT)
      if motion_fault:
        raise RuntimeError(
          f"PLC MotionFault became true while waiting for {TAG_ACK} == {seq}"
        )

      time.sleep(self.poll_s)

    raise TimeoutError(
      f"Timed out waiting for {TAG_ACK} == {seq}. "
      f"LastAck={self._read_one(TAG_ACK)!r}, "
      f"ReqID={self._try_read_one(TAG_REQ_ID)!r}, "
      f"LastReqID={self._try_read_one(TAG_LAST_REQ_ID)!r}, "
      f"MotionFault={self._try_read_one(TAG_MOTION_FAULT)!r}, "
      f"QueueFault={self._try_read_one(TAG_QUEUE_FAULT)!r}, "
      f"MoveA.ER={self._try_read_one(TAG_MOVE_A_ER)!r}, "
      f"MoveB.ER={self._try_read_one(TAG_MOVE_B_ER)!r}, "
      f"CurIssued={self._try_read_one(TAG_CUR_ISSUED)!r}, "
      f"NextIssued={self._try_read_one(TAG_NEXT_ISSUED)!r}, "
      f"QueueCount={self._try_read_one(TAG_QUEUE_COUNT)!r}, "
      f"UseAasCurrent={self._try_read_one(TAG_USE_A_AS_CURRENT)!r}, "
      f"MovePendingStatus={self._try_read_one(TAG_MOVE_PENDING_STATUS)!r}, "
      f"FaultCode={self._try_read_one(TAG_FAULT_CODE)!r}, "
      f"ActiveSeq={self._try_read_one(TAG_ACTIVE_SEQ)!r}, "
      f"PendingSeq={self._try_read_one(TAG_PENDING_SEQ)!r}"
    )

  def enqueue_segment(self, seg: MotionSegment) -> None:
    if seg.seg_type != 1:
      raise ValueError("seg_type must be 1 for the current PLC validation logic")
    if seg.speed <= 0 or seg.accel <= 0 or seg.decel <= 0:
      raise ValueError("speed, accel, and decel must be > 0")
    if not (0 <= seg.term_type <= 6):
      raise ValueError("term_type must be in [0, 6]")

    self._write_one(TAG_INCOMING_SEG, self._segment_to_udt(seg))
    self.req_id += 1
    self._write_one(TAG_REQ_ID, self.req_id)
    self._wait_for_ack(seg.seq)

    print(
      f"Enqueued seq={seg.seq} "
      f"target=({seg.x:.1f},{seg.y:.1f}) "
      f"term_type={seg.term_type}"
    )

  def enqueue_segments(self, segments: Iterable[MotionSegment]) -> None:
    for seg in segments:
      self.enqueue_segment(seg)

  def start_queued_path(self) -> None:
    print("Sending StartQueuedPath pulse...")
    self._write_one(TAG_START, True)
    time.sleep(START_PULSE_S)
    self._write_one(TAG_START, False)

  def wait_until_started(self, timeout_s: float = START_TIMEOUT_S) -> None:
    if TAG_CUR_ISSUED is None:
      return

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
      cur_issued = self._try_read_one(TAG_CUR_ISSUED)
      if cur_issued:
        print("PLC reports motion started.")
        return
      time.sleep(self.poll_s)

    raise TimeoutError(
      f"Timed out waiting for {TAG_CUR_ISSUED} to go true. "
      f"CurIssued={self._try_read_one(TAG_CUR_ISSUED)!r}, "
      f"NextIssued={self._try_read_one(TAG_NEXT_ISSUED)!r}, "
      f"MotionFault={self._try_read_one(TAG_MOTION_FAULT)!r}, "
      f"QueueFault={self._try_read_one(TAG_QUEUE_FAULT)!r}, "
      f"MoveA.ER={self._try_read_one(TAG_MOVE_A_ER)!r}, "
      f"MoveB.ER={self._try_read_one(TAG_MOVE_B_ER)!r}, "
      f"QueueCount={self._try_read_one(TAG_QUEUE_COUNT)!r}, "
      f"UseAasCurrent={self._try_read_one(TAG_USE_A_AS_CURRENT)!r}, "
      f"MovePendingStatus={self._try_read_one(TAG_MOVE_PENDING_STATUS)!r}, "
      f"FaultCode={self._try_read_one(TAG_FAULT_CODE)!r}"
    )

  def wait_until_idle(
    self,
    timeout_s: float = IDLE_TIMEOUT_S,
    expected_seqs: Optional[Iterable[int]] = None,
  ) -> None:
    if TAG_CUR_ISSUED is None or TAG_NEXT_ISSUED is None:
      return

    expected = list(expected_seqs) if expected_seqs is not None else []
    expected_pos = {seq: i for i, seq in enumerate(expected)}
    expected_idx = 0
    observed: list[int] = []
    skipped: list[int] = []

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
      cur_issued = bool(self._read_one(TAG_CUR_ISSUED))
      next_issued = bool(self._read_one(TAG_NEXT_ISSUED))
      active_raw = self._try_read_one(TAG_ACTIVE_SEQ)
      active_seq = int(active_raw) if isinstance(active_raw, (int, float)) else None

      if expected and active_seq is not None:
        pos = expected_pos.get(active_seq)
        if pos is not None and pos >= expected_idx:
          if pos > expected_idx:
            skipped.extend(expected[expected_idx:pos])
          if not observed or observed[-1] != active_seq:
            observed.append(active_seq)
          expected_idx = pos + 1

      if not cur_issued and not next_issued:
        if expected and expected_idx != len(expected):
          final_active_raw = self._try_read_one(TAG_ACTIVE_SEQ)
          final_active = (
            int(final_active_raw)
            if isinstance(final_active_raw, (int, float))
            else None
          )
          final_pos = expected_pos.get(final_active)
          if final_pos is not None and final_pos + 1 > expected_idx:
            if final_pos > expected_idx:
              skipped.extend(expected[expected_idx:final_pos])
            expected_idx = final_pos + 1

        if expected and expected_idx != len(expected):
          missing = expected[expected_idx:]
          raise RuntimeError(
            "PLC went idle before all expected segments became active. "
            f"Observed={observed}, Skipped={skipped}, Missing={missing}"
          )
        if skipped:
          print(
            "PLC skipped one or more expected ActiveSeq transitions "
            f"(likely zero-length or very short segments): {skipped}"
          )
        print("PLC reports motion idle.")
        return

      motion_fault = self._try_read_one(TAG_MOTION_FAULT)
      if motion_fault:
        raise RuntimeError("PLC MotionFault became true while waiting for idle")

      time.sleep(self.poll_s)

    raise TimeoutError(
      f"Timed out waiting for motion to go idle. "
      f"CurIssued={self._try_read_one(TAG_CUR_ISSUED)!r}, "
      f"NextIssued={self._try_read_one(TAG_NEXT_ISSUED)!r}, "
      f"MotionFault={self._try_read_one(TAG_MOTION_FAULT)!r}, "
      f"QueueFault={self._try_read_one(TAG_QUEUE_FAULT)!r}, "
      f"MoveA.ER={self._try_read_one(TAG_MOVE_A_ER)!r}, "
      f"MoveB.ER={self._try_read_one(TAG_MOVE_B_ER)!r}, "
      f"QueueCount={self._try_read_one(TAG_QUEUE_COUNT)!r}, "
      f"UseAasCurrent={self._try_read_one(TAG_USE_A_AS_CURRENT)!r}, "
      f"MovePendingStatus={self._try_read_one(TAG_MOVE_PENDING_STATUS)!r}, "
      f"FaultCode={self._try_read_one(TAG_FAULT_CODE)!r}, "
      f"ActiveSeq={self._try_read_one(TAG_ACTIVE_SEQ)!r}, "
      f"PendingSeq={self._try_read_one(TAG_PENDING_SEQ)!r}, "
      f"ObservedExpectedCount={expected_idx if expected else 'n/a'}, "
      f"Skipped={skipped if expected else 'n/a'}"
    )

  def print_snapshot(self) -> None:
    print("PLC snapshot:")
    print(f"  ReqID         = {self._try_read_one(TAG_REQ_ID)!r}")
    print(f"  LastReqID     = {self._try_read_one(TAG_LAST_REQ_ID)!r}")
    print(f"  Ack           = {self._try_read_one(TAG_ACK)!r}")
    print(f"  MotionFault   = {self._try_read_one(TAG_MOTION_FAULT)!r}")
    print(f"  QueueFault    = {self._try_read_one(TAG_QUEUE_FAULT)!r}")
    print(f"  MoveA.ER      = {self._try_read_one(TAG_MOVE_A_ER)!r}")
    print(f"  MoveB.ER      = {self._try_read_one(TAG_MOVE_B_ER)!r}")
    print(f"  CurIssued     = {self._try_read_one(TAG_CUR_ISSUED)!r}")
    print(f"  NextIssued    = {self._try_read_one(TAG_NEXT_ISSUED)!r}")
    print(f"  QueueCount    = {self._try_read_one(TAG_QUEUE_COUNT)!r}")
    print(f"  UseAasCurrent = {self._try_read_one(TAG_USE_A_AS_CURRENT)!r}")
    print(f"  MovePendingSt = {self._try_read_one(TAG_MOVE_PENDING_STATUS)!r}")
    print(f"  FaultCode     = {self._try_read_one(TAG_FAULT_CODE)!r}")
    print(f"  ActiveSeq     = {self._try_read_one(TAG_ACTIVE_SEQ)!r}")
    print(f"  PendingSeq    = {self._try_read_one(TAG_PENDING_SEQ)!r}")


# -----------------------------
# Test patterns
# -----------------------------


def validate_term_type(term_type: int) -> None:
  if term_type not in TESTABLE_TERM_TYPES:
    allowed = ", ".join(str(t) for t in TESTABLE_TERM_TYPES)
    raise ValueError(f"term_type must be one of: {allowed}")


def square_segments(
  start_seq: int = 100,
  term_type: int = DEFAULT_TEST_TERM_TYPE,
) -> list[MotionSegment]:
  validate_term_type(term_type)
  points = [
    (1000.0, 0.0),
    (1000.0, 1000.0),
    (2000.0, 1000.0),
    (2000.0, 0.0),
    (1000.0, 0.0),
  ]

  segments: list[MotionSegment] = []
  for i, (x, y) in enumerate(points):
    segments.append(
      MotionSegment(
        seq=start_seq + i,
        x=x,
        y=y,
        term_type=term_type,
      )
    )
  return segments


def lissajous_segments(
  start_seq: int = 100,
  tessellation_segments: int = LISSAJOUS_TESSELLATION_SEGMENTS,
  term_type: int = DEFAULT_TEST_TERM_TYPE,
  x_min: float = 1000.0,
  x_max: float = 6000.0,
  y_min: float = 0.0,
  y_max: float = 2500.0,
  x_freq: int = 3,
  y_freq: int = 2,
  phase_rad: float = math.pi / 2.0,
  boundary_margin: float = 10.0,
) -> list[MotionSegment]:
  validate_term_type(term_type)
  if tessellation_segments < 3:
    raise ValueError("tessellation_segments must be >= 3")
  if x_min >= x_max or y_min >= y_max:
    raise ValueError("invalid bounds")
  if boundary_margin < 0.0:
    raise ValueError("boundary_margin must be >= 0")

  x_center = (x_min + x_max) / 2.0
  y_center = (y_min + y_max) / 2.0
  x_amp = (x_max - x_min) / 2.0 - boundary_margin
  y_amp = (y_max - y_min) / 2.0 - boundary_margin

  if x_amp <= 0.0 or y_amp <= 0.0:
    raise ValueError("boundary_margin is too large for the requested box")

  def point_at_t(t: float) -> tuple[float, float]:
    x = x_center + x_amp * math.sin(x_freq * t + phase_rad)
    y = y_center + y_amp * math.sin(y_freq * t)
    return (x, y)

  def point_line_distance(
    p: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
  ) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    abx = bx - ax
    aby = by - ay
    ab2 = abx * abx + aby * aby
    if ab2 <= 1e-12:
      return math.hypot(px - ax, py - ay)
    t = ((px - ax) * abx + (py - ay) * aby) / ab2
    t = max(0.0, min(1.0, t))
    qx = ax + t * abx
    qy = ay + t * aby
    return math.hypot(px - qx, py - qy)

  def turn_angle(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
  ) -> float:
    v1x = b[0] - a[0]
    v1y = b[1] - a[1]
    v2x = c[0] - b[0]
    v2y = c[1] - b[1]
    m1 = math.hypot(v1x, v1y)
    m2 = math.hypot(v2x, v2y)
    if m1 <= 1e-9 or m2 <= 1e-9:
      return 0.0
    cos_theta = (v1x * v2x + v1y * v2y) / (m1 * m2)
    cos_theta = max(-1.0, min(1.0, cos_theta))
    return math.acos(cos_theta)

  # Adaptive criteria:
  # - geometric error (midpoint deviation from chord)
  # - turning angle (dense where curve bends quickly)
  scale = min(x_amp, y_amp) * 2.0
  max_chord_error = max(0.25, scale / (2.0 * float(tessellation_segments)))
  max_turn_rad = math.radians(8.0)
  min_dt = (2.0 * math.pi) / max(4096.0, float(tessellation_segments) * 32.0)
  max_depth = 20
  seed_intervals = max(8, min(64, 2 * (x_freq + y_freq)))

  samples: list[tuple[float, tuple[float, float]]] = []

  def add_segment(
    t0: float,
    p0: tuple[float, float],
    t1: float,
    p1: tuple[float, float],
    depth: int,
  ) -> None:
    tm = (t0 + t1) * 0.5
    pm = point_at_t(tm)
    deviation = point_line_distance(pm, p0, p1)
    angle = turn_angle(p0, pm, p1)
    need_split = deviation > max_chord_error or angle > max_turn_rad

    if need_split and depth < max_depth and (t1 - t0) > min_dt:
      add_segment(t0, p0, tm, pm, depth + 1)
      add_segment(tm, pm, t1, p1, depth + 1)
      return

    samples.append((t1, p1))

  t_start = 0.0
  p_start = point_at_t(t_start)
  samples.append((t_start, p_start))

  for i in range(seed_intervals):
    t0 = (2.0 * math.pi * i) / seed_intervals
    t1 = (2.0 * math.pi * (i + 1)) / seed_intervals
    p0 = point_at_t(t0)
    p1 = point_at_t(t1)
    add_segment(t0, p0, t1, p1, depth=0)

  points = [p for _, p in samples]
  # Avoid a duplicate closure endpoint (t=2*pi equals t=0), which can create
  # pathological post-filter jumps and visible speed artifacts.
  if len(points) >= 2 and math.hypot(
    points[-1][0] - points[0][0], points[-1][1] - points[0][1]
  ) < 1e-6:
    points.pop()

  segments: list[MotionSegment] = []
  for i, (x, y) in enumerate(points):
    segments.append(
      MotionSegment(
        seq=start_seq + i,
        x=x,
        y=y,
        term_type=term_type,
      )
    )

  return segments


def simple_two_segment_test(
  start_seq: int = 200,
  term_type: int = DEFAULT_TEST_TERM_TYPE,
) -> list[MotionSegment]:
  validate_term_type(term_type)
  return [
    MotionSegment(seq=start_seq, x=1000.0, y=0.0, term_type=term_type),
    MotionSegment(seq=start_seq + 1, x=1000.0, y=1000.0, term_type=term_type),
  ]


def enforce_min_segment_length(
  segments: list[MotionSegment],
  min_segment_length: float,
) -> list[MotionSegment]:
  if min_segment_length <= 0.0 or len(segments) <= 2:
    return segments

  filtered: list[MotionSegment] = [segments[0]]
  for seg in segments[1:-1]:
    prev = filtered[-1]
    if math.hypot(seg.x - prev.x, seg.y - prev.y) >= min_segment_length:
      filtered.append(seg)

  # Always preserve the last endpoint, while still trying to honor minimum length.
  last = segments[-1]
  if len(filtered) >= 2:
    prev = filtered[-1]
    if math.hypot(last.x - prev.x, last.y - prev.y) < min_segment_length:
      prev_prev = filtered[-2]
      if math.hypot(last.x - prev_prev.x, last.y - prev_prev.y) >= min_segment_length:
        filtered[-1] = last
      else:
        filtered.append(last)
    else:
      filtered.append(last)
  else:
    filtered.append(last)

  base_seq = filtered[0].seq
  return [replace(seg, seq=base_seq + i) for i, seg in enumerate(filtered)]


def enforce_max_segment_length(
  segments: list[MotionSegment],
  max_segment_length: float,
) -> list[MotionSegment]:
  if max_segment_length <= 0.0 or len(segments) <= 1:
    return segments

  out: list[MotionSegment] = [segments[0]]
  next_seq = segments[0].seq + 1

  for seg in segments[1:]:
    prev = out[-1]
    dx = seg.x - prev.x
    dy = seg.y - prev.y
    dist = math.hypot(dx, dy)

    if dist <= max_segment_length:
      out.append(replace(seg, seq=next_seq))
      next_seq += 1
      continue

    parts = int(math.ceil(dist / max_segment_length))
    for i in range(1, parts + 1):
      frac = i / parts
      out.append(
        replace(
          seg,
          seq=next_seq,
          x=prev.x + dx * frac,
          y=prev.y + dy * frac,
        )
      )
      next_seq += 1

  return out


def segment_lengths(segments: list[MotionSegment]) -> list[float]:
  return [
    math.hypot(segments[i].x - segments[i - 1].x, segments[i].y - segments[i - 1].y)
    for i in range(1, len(segments))
  ]


def estimate_max_curvature(segments: list[MotionSegment]) -> float:
  if len(segments) < 3:
    return 0.0

  kmax = 0.0
  for i in range(1, len(segments) - 1):
    x1, y1 = segments[i - 1].x, segments[i - 1].y
    x2, y2 = segments[i].x, segments[i].y
    x3, y3 = segments[i + 1].x, segments[i + 1].y
    a = math.hypot(x2 - x1, y2 - y1)
    b = math.hypot(x3 - x2, y3 - y2)
    c = math.hypot(x3 - x1, y3 - y1)
    if a <= 1e-9 or b <= 1e-9 or c <= 1e-9:
      continue

    area2 = abs((x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1))
    if area2 <= 1e-12:
      continue

    curvature = (2.0 * area2) / (a * b * c)
    if curvature > kmax:
      kmax = curvature

  return kmax


def tune_segments_for_constant_velocity(
  segments: list[MotionSegment],
  requested_min_segment_length: float,
  curvature_speed_safety: float,
  min_jerk_ratio: float,
  max_segment_factor: float,
) -> tuple[list[MotionSegment], float, float, float]:
  if not segments:
    return segments, requested_min_segment_length, 0.0, 0.0

  if not (0.1 <= curvature_speed_safety <= 1.0):
    raise ValueError("curvature_speed_safety must be in [0.1, 1.0]")
  if min_jerk_ratio <= 0.0:
    raise ValueError("min_jerk_ratio must be > 0")
  if max_segment_factor <= 1.0:
    raise ValueError("max_segment_factor must be > 1.0")

  base_speed = float(segments[0].speed)
  base_accel = max(1e-9, min(float(seg.accel) for seg in segments))
  base_decel = max(1e-9, min(float(seg.decel) for seg in segments))
  base_a = min(base_accel, base_decel)

  # To avoid forced slowdown on short segments, each segment should be at least
  # the accel distance needed to reach target speed.
  required_min_length = (base_speed * base_speed) / (2.0 * base_a)
  effective_min_length = max(requested_min_segment_length, required_min_length)
  tuned = enforce_min_segment_length(segments, effective_min_length)
  tuned = enforce_max_segment_length(tuned, effective_min_length * max_segment_factor)

  kmax = estimate_max_curvature(tuned)
  if kmax > 0.0:
    max_speed_for_curvature = math.sqrt(base_a / kmax) * curvature_speed_safety
    tuned_speed = min(base_speed, max_speed_for_curvature)
  else:
    max_speed_for_curvature = float("inf")
    tuned_speed = base_speed

  min_jerk = base_a * min_jerk_ratio
  tuned_segments: list[MotionSegment] = []
  for i, seg in enumerate(tuned):
    interior = i < len(tuned) - 1
    tuned_segments.append(
      replace(
        seg,
        speed=tuned_speed,
        jerk_accel=max(seg.jerk_accel, min_jerk),
        jerk_decel=max(seg.jerk_decel, min_jerk),
        term_type=4 if interior else 1,
      )
    )

  return tuned_segments, effective_min_length, max_speed_for_curvature, kmax


def build_segments(
  pattern: str,
  start_seq: int,
  term_type: int,
  lissajous_segments_count: int,
  min_segment_length: float,
) -> list[MotionSegment]:
  if min_segment_length < 0.0:
    raise ValueError("min_segment_length must be >= 0")

  if pattern == "lissajous":
    segments = lissajous_segments(
      start_seq=start_seq,
      tessellation_segments=lissajous_segments_count,
      term_type=term_type,
    )
  elif pattern == "square":
    segments = square_segments(start_seq=start_seq, term_type=term_type)
  elif pattern == "simple":
    segments = simple_two_segment_test(start_seq=start_seq, term_type=term_type)
  else:
    raise ValueError(f"Unsupported pattern: {pattern}")

  return enforce_min_segment_length(segments, min_segment_length=min_segment_length)


def print_pattern_summary(
  pattern: str,
  term_type: int,
  segments: list[MotionSegment],
  min_segment_length: float,
) -> None:
  xs = [seg.x for seg in segments]
  ys = [seg.y for seg in segments]
  lengths = segment_lengths(segments)
  min_len = min(lengths) if lengths else 0.0
  max_len = max(lengths) if lengths else 0.0
  avg_len = (sum(lengths) / len(lengths)) if lengths else 0.0
  speed = segments[0].speed if segments else 0.0
  accel = segments[0].accel if segments else 0.0
  jerk = segments[0].jerk_accel if segments else 0.0
  kmax = estimate_max_curvature(segments)
  vmax_from_curvature = math.sqrt(accel / kmax) if (kmax > 0 and accel > 0) else float(
    "inf"
  )
  vmax_text = f"{vmax_from_curvature:.1f}" if math.isfinite(vmax_from_curvature) else "inf"
  print(
    f"{pattern} queue generated: "
    f"term_type={term_type} "
    f"min_segment_length={min_segment_length:.2f} "
    f"segments={len(segments)} "
    f"x_range=({min(xs):.1f},{max(xs):.1f}) "
    f"y_range=({min(ys):.1f},{max(ys):.1f}) "
    f"segment_len[min/avg/max]=({min_len:.2f}/{avg_len:.2f}/{max_len:.2f}) "
    f"v={speed:.1f} a={accel:.1f} j={jerk:.1f} "
    f"kmax={kmax:.5f} vmax_from_a={vmax_text}"
  )


def write_segments_svg(
  segments: list[MotionSegment],
  output_path: str,
  title: str,
  position_seq: Optional[int] = None,
) -> None:
  if len(segments) < 2:
    raise ValueError("Need at least two segments to render SVG")

  xs = [seg.x for seg in segments]
  ys = [seg.y for seg in segments]
  min_x = min(xs)
  max_x = max(xs)
  min_y = min(ys)
  max_y = max(ys)

  width = 1200
  height = 900
  margin = 70.0
  plot_w = width - 2.0 * margin
  plot_h = height - 2.0 * margin

  span_x = max(max_x - min_x, 1e-9)
  span_y = max(max_y - min_y, 1e-9)
  scale = min(plot_w / span_x, plot_h / span_y)
  used_w = span_x * scale
  used_h = span_y * scale
  x_off = margin + (plot_w - used_w) * 0.5
  y_off = margin + (plot_h - used_h) * 0.5

  def to_svg(x: float, y: float) -> tuple[float, float]:
    px = x_off + (x - min_x) * scale
    py = y_off + used_h - (y - min_y) * scale
    return px, py

  seq_to_idx = {seg.seq: i for i, seg in enumerate(segments)}
  if position_seq is None:
    pos_idx = 0
  elif position_seq in seq_to_idx:
    pos_idx = seq_to_idx[position_seq]
  else:
    pos_idx = min(
      range(len(segments)),
      key=lambda i: abs(segments[i].seq - position_seq),
    )

  def rgb_hex(r: float, g: float, b: float) -> str:
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"

  lines: list[str] = []
  lines.append(
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
    f'viewBox="0 0 {width} {height}">'
  )
  lines.append('<rect width="100%" height="100%" fill="#0f172a"/>')
  lines.append(
    f'<rect x="{x_off:.2f}" y="{y_off:.2f}" width="{used_w:.2f}" height="{used_h:.2f}" '
    'fill="#111827" stroke="#334155" stroke-width="2"/>'
  )

  seg_count = len(segments) - 1
  denom = max(1, seg_count - 1)
  for i in range(seg_count):
    a = segments[i]
    b = segments[i + 1]
    x1, y1 = to_svg(a.x, a.y)
    x2, y2 = to_svg(b.x, b.y)
    t = i / denom
    r, g, bcol = colorsys.hsv_to_rgb((1.0 - t) * 0.65, 0.8, 0.95)
    color = rgb_hex(r, g, bcol)
    lines.append(
      f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
      f'stroke="{color}" stroke-width="2.2" stroke-linecap="round"/>'
    )

  sx, sy = to_svg(segments[0].x, segments[0].y)
  ex, ey = to_svg(segments[-1].x, segments[-1].y)
  px, py = to_svg(segments[pos_idx].x, segments[pos_idx].y)

  lines.append(f'<circle cx="{sx:.2f}" cy="{sy:.2f}" r="7" fill="#22c55e"/>')
  lines.append(f'<circle cx="{ex:.2f}" cy="{ey:.2f}" r="7" fill="#ef4444"/>')
  lines.append(
    f'<circle cx="{px:.2f}" cy="{py:.2f}" r="9" fill="#f59e0b" stroke="#0b0f18" stroke-width="2"/>'
  )

  lines.append(
    f'<text x="{margin:.0f}" y="36" fill="#e5e7eb" '
    'font-family="Consolas, Menlo, monospace" font-size="24">'
    f"{title}</text>"
  )
  lines.append(
    f'<text x="{margin:.0f}" y="{height - 36}" fill="#cbd5e1" '
    'font-family="Consolas, Menlo, monospace" font-size="18">'
    f"Position seq={segments[pos_idx].seq} index={pos_idx}/{len(segments) - 1}</text>"
  )
  lines.append("</svg>")

  out = Path(output_path)
  out.parent.mkdir(parents=True, exist_ok=True)
  out.write_text("\n".join(lines), encoding="utf-8")


def run_queue_case(
  motion: MotionQueueClient,
  segments: list[MotionSegment],
  queue_depth: int = PLC_QUEUE_DEPTH,
) -> None:
  if queue_depth < 2:
    raise ValueError("queue_depth must be >= 2")
  if len(segments) < 2:
    raise ValueError("At least 2 segments are required to start the queued path")

  total = len(segments)
  prefill_count = min(total, queue_depth)
  next_to_enqueue = prefill_count

  motion.reset_queue()
  motion.print_snapshot()

  print(f"\nQueueing initial {prefill_count}/{total} segments...")
  motion.enqueue_segments(segments[:prefill_count])

  print("\nInitial queue fill complete.")
  motion.print_snapshot()

  print("\nStarting queued path...")
  motion.start_queued_path()

  try:
    motion.wait_until_started()
  except Exception as exc:
    print(f"Start pulse sent, but start confirmation was not clean: {exc}")
    motion.print_snapshot()
    raise

  if next_to_enqueue < total:
    if motion._try_read_one(TAG_QUEUE_COUNT) is None:
      raise RuntimeError(
        f"{TAG_QUEUE_COUNT} is required to stream beyond queue depth "
        "but the tag could not be read."
      )
    print(
      "\nStreaming remaining segments as PLC consumes queue "
      f"({next_to_enqueue}/{total} enqueued)..."
    )

  while next_to_enqueue < total:
    queue_count_raw = motion._try_read_one(TAG_QUEUE_COUNT)
    if queue_count_raw is None:
      raise RuntimeError(
        f"Lost access to {TAG_QUEUE_COUNT} while streaming queued segments"
      )

    queue_count = int(queue_count_raw)
    room = max(0, queue_depth - queue_count)

    if room > 0:
      burst = min(room, total - next_to_enqueue)
      for _ in range(burst):
        motion.enqueue_segment(segments[next_to_enqueue])
        next_to_enqueue += 1

      print(
        "Streamed "
        f"{burst} segment(s); enqueued {next_to_enqueue}/{total}; "
        f"PLC queue count now {motion._try_read_one(TAG_QUEUE_COUNT)!r}"
      )
      continue

    motion_fault = motion._try_read_one(TAG_MOTION_FAULT)
    if motion_fault:
      raise RuntimeError("PLC MotionFault became true while streaming queued segments")

    queue_fault = motion._try_read_one(TAG_QUEUE_FAULT)
    if queue_fault:
      raise RuntimeError("PLC QueueFault became true while streaming queued segments")

    cur_issued = bool(motion._try_read_one(TAG_CUR_ISSUED))
    next_issued = bool(motion._try_read_one(TAG_NEXT_ISSUED))
    if not cur_issued and not next_issued:
      raise RuntimeError(
        "PLC went idle before all segments were enqueued. "
        f"Enqueued={next_to_enqueue}/{total}"
      )

    time.sleep(motion.poll_s)

  print("\nAll segments enqueued; waiting for motion completion...")

  try:
    motion.wait_until_idle(expected_seqs=[seg.seq for seg in segments])
  except Exception as exc:
    print(f"Motion did not complete cleanly: {exc}")
    motion.print_snapshot()
    raise

  print("\nQueue-pattern test completed successfully.")
  motion.print_snapshot()


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description=(
      "Queue tessellated coordinated moves and execute them on the PLC. "
      "Supported termination types for this test harness are 0,1,2,3,4,5,6."
    )
  )
  parser.add_argument(
    "--pattern",
    choices=("lissajous", "square", "simple"),
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
    "--queue-depth",
    type=int,
    default=PLC_QUEUE_DEPTH,
    help="Configured PLC FIFO depth used by the streaming enqueuer.",
  )
  parser.add_argument(
    "--min-segment-length",
    type=float,
    default=DEFAULT_MIN_SEGMENT_LENGTH,
    help=(
      "Minimum distance between consecutive queued segment endpoints. Use 0 to disable."
    ),
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
    help=(
      "Write an SVG visualization of the planned path. Example: cache/lissajous.svg"
    ),
  )
  parser.add_argument(
    "--position-seq",
    type=int,
    default=None,
    help=(
      "Sequence number to highlight as position in visualization. "
      "If omitted, highlights the first point."
    ),
  )
  parser.add_argument(
    "--visualize-only",
    action="store_true",
    help="Generate visualization and skip PLC communication.",
  )
  return parser.parse_args()


# -----------------------------
# Main test
# -----------------------------


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
