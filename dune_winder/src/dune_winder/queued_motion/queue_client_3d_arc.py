from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Iterable, Optional

from dune_winder.io.Devices.controllogix_plc import ControllogixPLC
from dune_winder.io.Devices.simulated_plc import SimulatedPLC


SEG_TYPE_CIRCLE = 2
CIRCLE_TYPE_CENTER = 1

DIR_3D_SHORTEST = 0
DIR_3D_LONGEST = 1
DIR_3D_SHORTEST_FULL = 2
DIR_3D_LONGEST_FULL = 3

TAG_INCOMING_SEG = "IncomingSeg3D"
TAG_REQ_ID = "IncomingSeg3DReqID"
TAG_LAST_REQ_ID = "LastIncomingSeg3DReqID"
TAG_ACK = "IncomingSeg3DAck"
TAG_ABORT = "AbortQueue3D"
TAG_START = "StartQueuedPath3D"

TAG_MOTION_FAULT = "MotionFault3D"
TAG_CUR_ISSUED = "CurIssued3D"
TAG_NEXT_ISSUED = "NextIssued3D"
TAG_ACTIVE_SEQ = "ActiveSeq3D"
TAG_PENDING_SEQ = "PendingSeq3D"
TAG_QUEUE_FAULT = "QueueFault3D"
TAG_MOVE_A_ER = "MoveA3D.ER"
TAG_MOVE_B_ER = "MoveB3D.ER"
TAG_QUEUE_COUNT = "QueueCount3D"
TAG_USE_A_AS_CURRENT = "UseAasCurrent3D"
TAG_MOVE_PENDING_STATUS = "X_Y_Z.MovePendingStatus"
TAG_FAULT_CODE = "FaultCode3D"

# Existing XY queue tags are read-only here and used only as an interlock.
TAG_XY_CUR_ISSUED = "CurIssued"
TAG_XY_NEXT_ISSUED = "NextIssued"
TAG_XY_MOVE_PENDING_STATUS = "X_Y.MovePendingStatus"

TAG_X_ACTUAL_POSITION = "X_axis.ActualPosition"
TAG_Y_ACTUAL_POSITION = "Y_axis.ActualPosition"
TAG_Z_ACTUAL_POSITION = "Z_axis.ActualPosition"

ACK_TIMEOUT_S = 5.0
POLL_S = 0.05
ABORT_PULSE_S = 0.10
START_PULSE_S = 0.10
POST_RESET_SETTLE_S = 0.10
START_TIMEOUT_S = 5.0
IDLE_TIMEOUT_S = 120.0
PLC_QUEUE_DEPTH_3D = 32

EPS_ZERO = 1e-9
COLLINEAR_EPS = 1e-8
RADIUS_ABS_TOL = 1e-3
RADIUS_REL_TOL = 1e-4


@dataclass(frozen=True)
class MotionArc3DSegment:
  seq: int
  x: float
  y: float
  z: float
  via_center_x: float
  via_center_y: float
  via_center_z: float
  speed: float = 1000.0
  accel: float = 2000.0
  decel: float = 2000.0
  jerk_accel: float = 100.0
  jerk_decel: float = 100.0
  term_type: int = 3
  seg_type: int = SEG_TYPE_CIRCLE
  circle_type: int = CIRCLE_TYPE_CENTER
  direction: int = DIR_3D_SHORTEST


def _dist3(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
  return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _cross3(
  a: tuple[float, float, float],
  b: tuple[float, float, float],
) -> tuple[float, float, float]:
  return (
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  )


def _norm3(v: tuple[float, float, float]) -> float:
  return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _all_finite(values: Iterable[float]) -> bool:
  return all(math.isfinite(float(v)) for v in values)


def validate_arc3d_segment(
  seg: MotionArc3DSegment,
  start_xyz: tuple[float, float, float],
) -> None:
  if seg.seg_type != SEG_TYPE_CIRCLE:
    raise ValueError("3D arc branch only accepts seg_type=2 (circle)")
  if seg.circle_type != CIRCLE_TYPE_CENTER:
    raise ValueError("3D arc branch only accepts circle_type=1 (center)")
  if seg.direction not in (DIR_3D_SHORTEST, DIR_3D_LONGEST):
    raise ValueError("3D arc branch only accepts direction 0/1 (shortest/longest)")

  if seg.seq <= 0:
    raise ValueError("seq must be > 0")
  if seg.speed <= 0.0 or seg.accel <= 0.0 or seg.decel <= 0.0:
    raise ValueError("speed, accel, and decel must be > 0")
  if not (0 <= seg.term_type <= 6):
    raise ValueError("term_type must be in [0, 6]")

  if not _all_finite(
    (
      start_xyz[0],
      start_xyz[1],
      start_xyz[2],
      seg.x,
      seg.y,
      seg.z,
      seg.via_center_x,
      seg.via_center_y,
      seg.via_center_z,
      seg.speed,
      seg.accel,
      seg.decel,
      seg.jerk_accel,
      seg.jerk_decel,
    )
  ):
    raise ValueError("segment fields must be finite")

  start = (float(start_xyz[0]), float(start_xyz[1]), float(start_xyz[2]))
  end = (float(seg.x), float(seg.y), float(seg.z))
  center = (
    float(seg.via_center_x),
    float(seg.via_center_y),
    float(seg.via_center_z),
  )

  if _dist3(start, end) <= EPS_ZERO:
    raise ValueError("full-circle arcs (start == end) are not supported in v1")

  r0 = _dist3(start, center)
  r1 = _dist3(end, center)
  if r0 <= EPS_ZERO or r1 <= EPS_ZERO:
    raise ValueError("invalid arc geometry: radius must be > 0")

  radius_tol = max(RADIUS_ABS_TOL, RADIUS_REL_TOL * max(r0, r1))
  if abs(r0 - r1) > radius_tol:
    raise ValueError(
      "invalid arc geometry: start/end radii from center do not match. "
      f"r0={r0:.6f}, r1={r1:.6f}, tol={radius_tol:.6f}"
    )

  v0 = (start[0] - center[0], start[1] - center[1], start[2] - center[2])
  v1 = (end[0] - center[0], end[1] - center[1], end[2] - center[2])
  cross = _cross3(v0, v1)
  scale = max(r0, r1)
  if _norm3(cross) <= COLLINEAR_EPS * scale * scale:
    raise ValueError(
      "invalid arc geometry: start-center-end are collinear or nearly collinear"
    )


class MotionArc3DQueueClient:
  def __init__(
    self,
    path: str,
    ack_timeout_s: float = ACK_TIMEOUT_S,
    poll_s: float = POLL_S,
  ) -> None:
    self.path = path
    self.ack_timeout_s = ack_timeout_s
    self.poll_s = poll_s
    self.plc = None
    self.req_id = 0
    self._last_point: Optional[tuple[float, float, float]] = None

  def __enter__(self) -> "MotionArc3DQueueClient":
    if str(self.path).strip().upper() == "SIM":
      self.plc = SimulatedPLC("SIM")
    else:
      self.plc = ControllogixPLC(self.path)
    self._sync_req_id_from_plc()
    self._last_point = self._read_actual_xyz_if_available()
    return self

  def __exit__(self, exc_type, exc, tb) -> None:
    if getattr(self.plc, "_plcDriver", None) is not None:
      try:
        self.plc._plcDriver.close()
      except Exception:
        pass
    self.plc = None

  def _require_plc(self):
    if self.plc is None:
      raise RuntimeError("PLC connection is not open")
    return self.plc

  @staticmethod
  def _extract_read_value(read_result, tag: str):
    if read_result is None:
      raise RuntimeError(f"Read failed for {tag}: no response")

    if isinstance(read_result, list):
      if not read_result:
        raise RuntimeError(f"Read failed for {tag}: empty response")
      first = read_result[0]
      if hasattr(first, "error"):
        if first.error:
          raise RuntimeError(f"Read failed for {tag}: {first.error}")
        return first.value
      if isinstance(first, (list, tuple)):
        if len(first) >= 2:
          return first[1]
        if len(first) == 1:
          return first[0]
      return first

    if hasattr(read_result, "error"):
      if read_result.error:
        raise RuntimeError(f"Read failed for {tag}: {read_result.error}")
      return read_result.value

    return read_result

  @staticmethod
  def _assert_write_ok(write_result, tag: str) -> None:
    if write_result is None:
      raise RuntimeError(f"Write failed for {tag}: no response")
    if isinstance(write_result, list):
      for item in write_result:
        if hasattr(item, "error") and item.error:
          raise RuntimeError(f"Write failed for {tag}: {item.error}")
      return
    if hasattr(write_result, "error") and write_result.error:
      raise RuntimeError(f"Write failed for {tag}: {write_result.error}")

  def _read_one(self, tag: str):
    result = self._require_plc().read([tag])
    return self._extract_read_value(result, tag)

  def _try_read_one(self, tag: Optional[str]):
    if not tag:
      return None
    try:
      return self._read_one(tag)
    except Exception:
      return None

  def _write_one(self, tag: str, value) -> None:
    result = self._require_plc().write((tag, value))
    self._assert_write_ok(result, tag)

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

  def _read_actual_xyz(self) -> tuple[float, float, float]:
    return (
      float(self._read_one(TAG_X_ACTUAL_POSITION)),
      float(self._read_one(TAG_Y_ACTUAL_POSITION)),
      float(self._read_one(TAG_Z_ACTUAL_POSITION)),
    )

  def _read_actual_xyz_if_available(self) -> Optional[tuple[float, float, float]]:
    try:
      return self._read_actual_xyz()
    except Exception:
      return None

  def set_start_point(self, x: float, y: float, z: float) -> None:
    if not _all_finite((x, y, z)):
      raise ValueError("start point values must be finite")
    self._last_point = (float(x), float(y), float(z))

  def _assert_xy_idle(self, context: str) -> None:
    xy_cur = bool(self._try_read_one(TAG_XY_CUR_ISSUED))
    xy_next = bool(self._try_read_one(TAG_XY_NEXT_ISSUED))
    xy_pending = bool(self._try_read_one(TAG_XY_MOVE_PENDING_STATUS))
    if xy_cur or xy_next or xy_pending:
      raise RuntimeError(
        f"Cannot {context}: existing XY queue appears active "
        f"(CurIssued={xy_cur}, NextIssued={xy_next}, MovePending={xy_pending})"
      )

  def reset_queue(self) -> None:
    print("Resetting PLC 3D arc queue...")
    self._write_one(TAG_ABORT, True)
    time.sleep(ABORT_PULSE_S)
    self._write_one(TAG_ABORT, False)
    time.sleep(POST_RESET_SETTLE_S)
    self._sync_req_id_from_plc()
    self._last_point = self._read_actual_xyz_if_available()
    print(f"Reset complete. ReqID synchronized to {self.req_id}")

  @staticmethod
  def _segment_to_udt(seg: MotionArc3DSegment) -> dict:
    return {
      "Valid": True,
      "SegType": int(seg.seg_type),
      "XYZ": [float(seg.x), float(seg.y), float(seg.z)],
      "CircleType": int(seg.circle_type),
      "ViaCenter": [
        float(seg.via_center_x),
        float(seg.via_center_y),
        float(seg.via_center_z),
      ],
      "Direction": int(seg.direction),
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
          f"PLC MotionFault3D became true while waiting for {TAG_ACK} == {seq}"
        )

      time.sleep(self.poll_s)

    raise TimeoutError(
      f"Timed out waiting for {TAG_ACK} == {seq}. "
      f"LastAck={self._read_one(TAG_ACK)!r}, "
      f"ReqID={self._try_read_one(TAG_REQ_ID)!r}, "
      f"LastReqID={self._try_read_one(TAG_LAST_REQ_ID)!r}, "
      f"MotionFault={self._try_read_one(TAG_MOTION_FAULT)!r}, "
      f"QueueFault={self._try_read_one(TAG_QUEUE_FAULT)!r}, "
      f"MoveA3D.ER={self._try_read_one(TAG_MOVE_A_ER)!r}, "
      f"MoveB3D.ER={self._try_read_one(TAG_MOVE_B_ER)!r}, "
      f"CurIssued3D={self._try_read_one(TAG_CUR_ISSUED)!r}, "
      f"NextIssued3D={self._try_read_one(TAG_NEXT_ISSUED)!r}, "
      f"QueueCount3D={self._try_read_one(TAG_QUEUE_COUNT)!r}, "
      f"UseAasCurrent3D={self._try_read_one(TAG_USE_A_AS_CURRENT)!r}, "
      f"MovePendingStatus3D={self._try_read_one(TAG_MOVE_PENDING_STATUS)!r}, "
      f"FaultCode3D={self._try_read_one(TAG_FAULT_CODE)!r}, "
      f"ActiveSeq3D={self._try_read_one(TAG_ACTIVE_SEQ)!r}, "
      f"PendingSeq3D={self._try_read_one(TAG_PENDING_SEQ)!r}"
    )

  def enqueue_segment(self, seg: MotionArc3DSegment) -> None:
    self._assert_xy_idle("enqueue to 3D arc queue")

    if self._last_point is None:
      self._last_point = self._read_actual_xyz_if_available()
    if self._last_point is None:
      raise RuntimeError(
        "Cannot validate first arc geometry: start point is unknown. "
        "Call set_start_point(x, y, z) or ensure axis actual position tags are readable."
      )

    validate_arc3d_segment(seg, self._last_point)

    self._write_one(TAG_INCOMING_SEG, self._segment_to_udt(seg))
    self.req_id += 1
    self._write_one(TAG_REQ_ID, self.req_id)
    self._wait_for_ack(seg.seq)

    self._last_point = (float(seg.x), float(seg.y), float(seg.z))
    print(
      f"Enqueued seq={seg.seq} type=3d_arc "
      f"target=({seg.x:.3f},{seg.y:.3f},{seg.z:.3f}) "
      f"center=({seg.via_center_x:.3f},{seg.via_center_y:.3f},{seg.via_center_z:.3f}) "
      f"direction={seg.direction} term_type={seg.term_type}"
    )

  def enqueue_segments(self, segments: Iterable[MotionArc3DSegment]) -> None:
    for seg in segments:
      self.enqueue_segment(seg)

  def start_queued_path(self) -> None:
    self._assert_xy_idle("start 3D arc queue")
    print("Sending StartQueuedPath3D pulse...")
    self._write_one(TAG_START, True)
    time.sleep(START_PULSE_S)
    self._write_one(TAG_START, False)

  def wait_until_started(self, timeout_s: float = START_TIMEOUT_S) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
      cur_issued = self._try_read_one(TAG_CUR_ISSUED)
      if cur_issued:
        print("PLC reports 3D arc motion started.")
        return
      time.sleep(self.poll_s)

    raise TimeoutError(
      f"Timed out waiting for {TAG_CUR_ISSUED} to go true. "
      f"CurIssued3D={self._try_read_one(TAG_CUR_ISSUED)!r}, "
      f"NextIssued3D={self._try_read_one(TAG_NEXT_ISSUED)!r}, "
      f"MotionFault3D={self._try_read_one(TAG_MOTION_FAULT)!r}, "
      f"QueueFault3D={self._try_read_one(TAG_QUEUE_FAULT)!r}, "
      f"MoveA3D.ER={self._try_read_one(TAG_MOVE_A_ER)!r}, "
      f"MoveB3D.ER={self._try_read_one(TAG_MOVE_B_ER)!r}, "
      f"QueueCount3D={self._try_read_one(TAG_QUEUE_COUNT)!r}, "
      f"UseAasCurrent3D={self._try_read_one(TAG_USE_A_AS_CURRENT)!r}, "
      f"MovePendingStatus3D={self._try_read_one(TAG_MOVE_PENDING_STATUS)!r}, "
      f"FaultCode3D={self._try_read_one(TAG_FAULT_CODE)!r}"
    )

  def wait_until_idle(
    self,
    timeout_s: float = IDLE_TIMEOUT_S,
    expected_seqs: Optional[Iterable[int]] = None,
  ) -> None:
    expected = list(expected_seqs) if expected_seqs is not None else []
    expected_pos = {seq: i for i, seq in enumerate(expected)}
    expected_idx = 0

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
      cur_issued = bool(self._read_one(TAG_CUR_ISSUED))
      next_issued = bool(self._read_one(TAG_NEXT_ISSUED))
      active_raw = self._try_read_one(TAG_ACTIVE_SEQ)
      active_seq = int(active_raw) if isinstance(active_raw, (int, float)) else None

      if expected and active_seq is not None:
        pos = expected_pos.get(active_seq)
        if pos is not None and pos >= expected_idx:
          expected_idx = pos + 1

      if not cur_issued and not next_issued:
        if expected and expected_idx != len(expected):
          missing = expected[expected_idx:]
          raise RuntimeError(
            "PLC 3D queue went idle before all expected segments became active. "
            f"Missing={missing}"
          )
        print("PLC reports 3D arc motion idle.")
        return

      motion_fault = self._try_read_one(TAG_MOTION_FAULT)
      if motion_fault:
        raise RuntimeError("PLC MotionFault3D became true while waiting for idle")

      time.sleep(self.poll_s)

    raise TimeoutError(
      f"Timed out waiting for 3D arc motion to go idle. "
      f"CurIssued3D={self._try_read_one(TAG_CUR_ISSUED)!r}, "
      f"NextIssued3D={self._try_read_one(TAG_NEXT_ISSUED)!r}, "
      f"MotionFault3D={self._try_read_one(TAG_MOTION_FAULT)!r}, "
      f"QueueFault3D={self._try_read_one(TAG_QUEUE_FAULT)!r}, "
      f"MoveA3D.ER={self._try_read_one(TAG_MOVE_A_ER)!r}, "
      f"MoveB3D.ER={self._try_read_one(TAG_MOVE_B_ER)!r}, "
      f"QueueCount3D={self._try_read_one(TAG_QUEUE_COUNT)!r}, "
      f"UseAasCurrent3D={self._try_read_one(TAG_USE_A_AS_CURRENT)!r}, "
      f"MovePendingStatus3D={self._try_read_one(TAG_MOVE_PENDING_STATUS)!r}, "
      f"FaultCode3D={self._try_read_one(TAG_FAULT_CODE)!r}, "
      f"ActiveSeq3D={self._try_read_one(TAG_ACTIVE_SEQ)!r}, "
      f"PendingSeq3D={self._try_read_one(TAG_PENDING_SEQ)!r}"
    )

  def print_snapshot(self) -> None:
    print("PLC 3D arc queue snapshot:")
    print(f"  ReqID3D         = {self._try_read_one(TAG_REQ_ID)!r}")
    print(f"  LastReqID3D     = {self._try_read_one(TAG_LAST_REQ_ID)!r}")
    print(f"  Ack3D           = {self._try_read_one(TAG_ACK)!r}")
    print(f"  MotionFault3D   = {self._try_read_one(TAG_MOTION_FAULT)!r}")
    print(f"  QueueFault3D    = {self._try_read_one(TAG_QUEUE_FAULT)!r}")
    print(f"  MoveA3D.ER      = {self._try_read_one(TAG_MOVE_A_ER)!r}")
    print(f"  MoveB3D.ER      = {self._try_read_one(TAG_MOVE_B_ER)!r}")
    print(f"  CurIssued3D     = {self._try_read_one(TAG_CUR_ISSUED)!r}")
    print(f"  NextIssued3D    = {self._try_read_one(TAG_NEXT_ISSUED)!r}")
    print(f"  QueueCount3D    = {self._try_read_one(TAG_QUEUE_COUNT)!r}")
    print(f"  UseAasCurrent3D = {self._try_read_one(TAG_USE_A_AS_CURRENT)!r}")
    print(f"  MovePending3D   = {self._try_read_one(TAG_MOVE_PENDING_STATUS)!r}")
    print(f"  FaultCode3D     = {self._try_read_one(TAG_FAULT_CODE)!r}")
    print(f"  ActiveSeq3D     = {self._try_read_one(TAG_ACTIVE_SEQ)!r}")
    print(f"  PendingSeq3D    = {self._try_read_one(TAG_PENDING_SEQ)!r}")
    print(f"  XY CurIssued    = {self._try_read_one(TAG_XY_CUR_ISSUED)!r}")
    print(f"  XY NextIssued   = {self._try_read_one(TAG_XY_NEXT_ISSUED)!r}")
    print(f"  XY MovePending  = {self._try_read_one(TAG_XY_MOVE_PENDING_STATUS)!r}")


def run_arc3d_queue_case(
  motion: MotionArc3DQueueClient,
  segments: list[MotionArc3DSegment],
  queue_depth: int = PLC_QUEUE_DEPTH_3D,
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

  print(f"\nQueueing initial {prefill_count}/{total} 3D arc segments...")
  motion.enqueue_segments(segments[:prefill_count])

  print("\nInitial queue fill complete.")
  motion.print_snapshot()

  print("\nStarting 3D arc queued path...")
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
      "\nStreaming remaining 3D arc segments as PLC consumes queue "
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
      raise RuntimeError("PLC MotionFault3D became true while streaming queued segments")

    queue_fault = motion._try_read_one(TAG_QUEUE_FAULT)
    if queue_fault:
      raise RuntimeError("PLC QueueFault3D became true while streaming queued segments")

    cur_issued = bool(motion._try_read_one(TAG_CUR_ISSUED))
    next_issued = bool(motion._try_read_one(TAG_NEXT_ISSUED))
    if not cur_issued and not next_issued:
      raise RuntimeError(
        "PLC went idle before all 3D arc segments were enqueued. "
        f"Enqueued={next_to_enqueue}/{total}"
      )

    time.sleep(motion.poll_s)

  print("\nAll 3D arc segments enqueued; waiting for motion completion...")

  try:
    motion.wait_until_idle(expected_seqs=[seg.seq for seg in segments])
  except Exception as exc:
    print(f"3D arc motion did not complete cleanly: {exc}")
    motion.print_snapshot()
    raise

  print("\n3D arc queue test completed successfully.")
  motion.print_snapshot()


__all__ = [
  "DIR_3D_SHORTEST",
  "DIR_3D_LONGEST",
  "DIR_3D_SHORTEST_FULL",
  "DIR_3D_LONGEST_FULL",
  "MotionArc3DSegment",
  "MotionArc3DQueueClient",
  "PLC_QUEUE_DEPTH_3D",
  "run_arc3d_queue_case",
  "validate_arc3d_segment",
]
