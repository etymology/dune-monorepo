from __future__ import annotations

import time
from typing import Iterable

from dune_winder.io.Devices.controllogix_plc import ControllogixPLC
from dune_winder.io.Devices.simulated_plc import SimulatedPLC

from .plc_interface import (
  ACK_TIMEOUT_S,
  IDLE_TIMEOUT_S,
  PLC_QUEUE_DEPTH,
)
from .plc_interface import (
  QueuedMotionPLCInterface,
  START_TIMEOUT_S,
)
from .segment_types import MotionSegment, segment_kind


POLL_S = 0.05


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
    self._plc = None
    self._queue = None
    self.req_id = 0

  def __enter__(self) -> "MotionQueueClient":
    if str(self.path).strip().upper() == "SIM":
      self._plc = SimulatedPLC("SIM")
    else:
      self._plc = ControllogixPLC(self.path)
    self._queue = QueuedMotionPLCInterface(self._plc)
    self._queue.poll()
    self.req_id = self._queue.sync_req_id()
    return self

  def __exit__(self, exc_type, exc, tb) -> None:
    if getattr(self._plc, "_plcDriver", None) is not None:
      try:
        self._plc._plcDriver.close()
      except Exception:
        pass
    self._plc = None
    self._queue = None

  def _require_queue(self) -> QueuedMotionPLCInterface:
    if self._queue is None:
      raise RuntimeError("PLC connection is not open")
    return self._queue

  def reset_queue(self) -> None:
    print("Resetting PLC queue...")
    queue = self._require_queue()
    queue.set_abort(True)
    time.sleep(0.10)
    queue.set_abort(False)
    queue.poll()
    self.req_id = queue.sync_req_id()
    print(f"Reset complete. ReqID synchronized to {self.req_id}")

  def _wait_for_ack(self, seq: int) -> None:
    queue = self._require_queue()
    deadline = time.monotonic() + self.ack_timeout_s
    while time.monotonic() < deadline:
      queue.poll()
      status = queue.status()
      if status.ack == seq:
        return
      if status.motion_fault:
        raise RuntimeError("PLC MotionFault became true while waiting for queued ACK")
      if status.queue_fault:
        raise RuntimeError("PLC QueueFault became true while waiting for queued ACK")
      time.sleep(self.poll_s)
    queue.poll()
    raise TimeoutError(
      f"Timed out waiting for IncomingSegAck == {seq}. "
      f"LastAck={queue.status().ack!r}"
    )

  def enqueue_segment(self, seg: MotionSegment) -> None:
    queue = self._require_queue()
    queue.write_segment(seg)
    self.req_id += 1
    queue.set_req_id(self.req_id)
    self._wait_for_ack(seg.seq)

    kind = segment_kind(seg.seg_type)
    arc_info = ""
    if seg.seg_type != 1:
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
    queue = self._require_queue()
    queue.set_start(True)
    time.sleep(0.10)
    queue.set_start(False)

  def wait_until_started(self, timeout_s: float = START_TIMEOUT_S) -> None:
    queue = self._require_queue()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
      queue.poll()
      if queue.status().cur_issued:
        print("PLC reports motion started.")
        return
      time.sleep(self.poll_s)
    raise TimeoutError("Timed out waiting for CurIssued to go true")

  def wait_until_idle(self, timeout_s: float = IDLE_TIMEOUT_S) -> None:
    queue = self._require_queue()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
      queue.poll()
      status = queue.status()
      if status.is_idle:
        print("PLC reports motion idle.")
        return
      if status.motion_fault:
        raise RuntimeError("PLC MotionFault became true while waiting for idle")
      if status.queue_fault:
        raise RuntimeError("PLC QueueFault became true while waiting for idle")
      time.sleep(self.poll_s)
    raise TimeoutError("Timed out waiting for motion to go idle")

  def print_snapshot(self) -> None:
    queue = self._require_queue()
    queue.poll()
    print("PLC snapshot:")
    for line in queue.snapshot_lines():
      print("  " + line)


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
  motion.wait_until_started()

  while next_to_enqueue < total:
    motion._require_queue().poll()
    status = motion._require_queue().status()
    room = max(0, queue_depth - int(status.queue_count))
    if room <= 0:
      if status.motion_fault:
        raise RuntimeError("PLC MotionFault became true while streaming queued segments")
      if status.queue_fault:
        raise RuntimeError("PLC QueueFault became true while streaming queued segments")
      time.sleep(motion.poll_s)
      continue

    burst = min(room, total - next_to_enqueue)
    for _ in range(burst):
      motion.enqueue_segment(segments[next_to_enqueue])
      next_to_enqueue += 1

  print("\nAll segments enqueued; waiting for motion completion...")
  motion.wait_until_idle()
  print("\nQueue-pattern test completed successfully.")
