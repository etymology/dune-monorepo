from __future__ import annotations

import time
from typing import Iterable, Optional

from pycomm3 import LogixDriver

from .segment_types import (
  MotionSegment,
  SEG_TYPE_CIRCLE,
  SEG_TYPE_LINE,
  segment_kind,
)


TAG_INCOMING_SEG = "IncomingSeg"
TAG_REQ_ID = "IncomingSegReqID"
TAG_LAST_REQ_ID = "LastIncomingSegReqID"
TAG_ACK = "IncomingSegAck"
TAG_ABORT = "AbortQueue"
TAG_START = "StartQueuedPath"

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
PLC_QUEUE_DEPTH = 32


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
      "XY": [float(seg.x), float(seg.y)],
      "CircleType": int(seg.circle_type),
      "ViaCenter": [float(seg.via_center_x), float(seg.via_center_y)],
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
    if seg.seg_type not in (SEG_TYPE_LINE, SEG_TYPE_CIRCLE):
      raise ValueError("seg_type must be 1 (line) or 2 (circle)")
    if seg.speed <= 0 or seg.accel <= 0 or seg.decel <= 0:
      raise ValueError("speed, accel, and decel must be > 0")
    if not (0 <= seg.term_type <= 6):
      raise ValueError("term_type must be in [0, 6]")
    if seg.seg_type == SEG_TYPE_CIRCLE:
      if not (0 <= seg.circle_type <= 3):
        raise ValueError("circle_type must be in [0, 3]")
      if not (0 <= seg.direction <= 3):
        raise ValueError("direction must be in [0, 3] for 2D MCCM")

    self._write_one(TAG_INCOMING_SEG, self._segment_to_udt(seg))
    self.req_id += 1
    self._write_one(TAG_REQ_ID, self.req_id)
    self._wait_for_ack(seg.seq)

    kind = segment_kind(seg.seg_type)
    arc_info = ""
    if seg.seg_type == SEG_TYPE_CIRCLE:
      arc_info = (
        f" circle_type={seg.circle_type} "
        f"via_center=({seg.via_center_x:.1f},{seg.via_center_y:.1f}) "
        f"direction={seg.direction}"
      )

    print(
      f"Enqueued seq={seg.seq} "
      f"type={kind} "
      f"target=({seg.x:.1f},{seg.y:.1f}) "
      f"term_type={seg.term_type}"
      f"{arc_info}"
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
