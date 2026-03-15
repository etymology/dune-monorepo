from __future__ import annotations

import time
from typing import Callable, Optional

from .plc_interface import (
  ACK_TIMEOUT_S,
  ABORT_PULSE_S,
  IDLE_TIMEOUT_S,
  PLC_QUEUE_DEPTH,
  POST_RESET_SETTLE_S,
  START_PULSE_S,
  START_TIMEOUT_S,
  QueuedMotionPortAdapter,
)
from .segment_types import MotionSegment


class QueuedMotionSession:
  def __init__(
    self,
    port,
    segments: list[MotionSegment],
    *,
    queue_depth: int = PLC_QUEUE_DEPTH,
    now_fn: Callable[[], float] = time.monotonic,
  ) -> None:
    if queue_depth < 1:
      raise ValueError("queue_depth must be >= 1")
    if len(segments) < 1:
      raise ValueError("At least 1 segment is required to start the queued path")

    self._port = port if isinstance(port, QueuedMotionPortAdapter) else QueuedMotionPortAdapter(port)
    self._segments = list(segments)
    self._queue_depth = int(queue_depth)
    self._now_fn = now_fn

    self._req_id = 0
    self._next_to_enqueue = 0
    self._prefill_count = min(len(self._segments), self._queue_depth)
    self._waiting_ack_seq: Optional[int] = None
    self._waiting_ack_deadline: Optional[float] = None
    self._pulse_release_at: Optional[float] = None
    self._start_deadline: Optional[float] = None
    self._idle_deadline: Optional[float] = None
    self._reset_release_at: Optional[float] = None

    self._state = "reset_assert"
    self._done = False
    self._aborted = False
    self._error: Optional[str] = None

  @property
  def done(self) -> bool:
    return self._done

  @property
  def aborted(self) -> bool:
    return self._aborted

  @property
  def error(self) -> Optional[str]:
    return self._error

  @property
  def active(self) -> bool:
    return not (self._done or self._aborted or self._error)

  def request_abort(self) -> None:
    if self._done or self._aborted or self._error:
      return
    self._state = "abort_assert"
    self._waiting_ack_seq = None
    self._waiting_ack_deadline = None
    self._pulse_release_at = None

  def _fail(self, message: str) -> None:
    self._error = message

  def _issue_enqueue(self, now: float) -> None:
    seg = self._segments[self._next_to_enqueue]
    self._port.write_segment(seg)
    self._req_id += 1
    self._port.set_req_id(self._req_id)
    self._waiting_ack_seq = int(seg.seq)
    self._waiting_ack_deadline = now + ACK_TIMEOUT_S

  def _check_ack(self, now: float, status) -> bool:
    if self._waiting_ack_seq is None:
      return False
    if status.ack == self._waiting_ack_seq:
      self._next_to_enqueue += 1
      self._waiting_ack_seq = None
      self._waiting_ack_deadline = None
      return True
    if status.motion_fault:
      self._fail("PLC MotionFault became true while waiting for queued segment ACK")
      return False
    if status.queue_fault:
      self._fail("PLC QueueFault became true while waiting for queued segment ACK")
      return False
    if self._waiting_ack_deadline is not None and now > self._waiting_ack_deadline:
      self._fail(
        f"Timed out waiting for IncomingSegAck == {self._waiting_ack_seq}; "
        f"last ack was {status.ack}"
      )
    return False

  def advance(self) -> None:
    if self._done or self._aborted or self._error:
      return

    now = self._now_fn()
    self._port.poll()
    status = self._port.status()

    if self._state == "reset_assert":
      self._port.set_abort(True)
      self._pulse_release_at = now + ABORT_PULSE_S
      self._state = "reset_release"
      return

    if self._state == "reset_release":
      if now < (self._pulse_release_at or 0.0):
        return
      self._port.set_abort(False)
      self._req_id = self._port.sync_req_id()
      self._reset_release_at = now + POST_RESET_SETTLE_S
      self._state = "enqueue_prefill"
      return

    if self._state == "enqueue_prefill":
      if now < (self._reset_release_at or 0.0):
        return
      if self._check_ack(now, status):
        return
      if self._error:
        return
      if self._waiting_ack_seq is not None:
        return
      if self._next_to_enqueue < self._prefill_count:
        self._issue_enqueue(now)
        return
      self._state = "start_assert"

    if self._state == "start_assert":
      self._port.set_start(True)
      self._pulse_release_at = now + START_PULSE_S
      self._start_deadline = now + START_TIMEOUT_S
      self._state = "start_release"
      return

    if self._state == "start_release":
      if now < (self._pulse_release_at or 0.0):
        return
      self._port.set_start(False)
      self._state = "wait_started"
      return

    if self._state == "wait_started":
      if status.motion_fault:
        self._fail("PLC MotionFault became true before queued path started")
        return
      if status.queue_fault:
        self._fail("PLC QueueFault became true before queued path started")
        return
      if status.cur_issued:
        self._idle_deadline = now + IDLE_TIMEOUT_S
        self._state = "streaming" if self._next_to_enqueue < len(self._segments) else "wait_idle"
        return
      if (
        self._next_to_enqueue >= len(self._segments)
        and status.is_idle
        and status.ack == int(self._segments[-1].seq)
      ):
        self._done = True
        return
      if self._start_deadline is not None and now > self._start_deadline:
        self._fail("Timed out waiting for queued motion to start")
      return

    if self._state == "streaming":
      if self._check_ack(now, status):
        return
      if self._error:
        return
      if status.motion_fault:
        self._fail("PLC MotionFault became true while streaming queued segments")
        return
      if status.queue_fault:
        self._fail("PLC QueueFault became true while streaming queued segments")
        return
      if self._waiting_ack_seq is not None:
        return
      if self._next_to_enqueue >= len(self._segments):
        self._state = "wait_idle"
        return
      room = max(0, self._queue_depth - int(status.queue_count))
      if room > 0:
        self._issue_enqueue(now)
        return
      if status.is_idle:
        self._fail("PLC went idle before all queued segments were enqueued")
      return

    if self._state == "wait_idle":
      if status.motion_fault:
        self._fail("PLC MotionFault became true while waiting for queued idle")
        return
      if status.queue_fault:
        self._fail("PLC QueueFault became true while waiting for queued idle")
        return
      if status.is_idle:
        self._done = True
        return
      if self._idle_deadline is not None and now > self._idle_deadline:
        self._fail("Timed out waiting for queued motion to go idle")
      return

    if self._state == "abort_assert":
      self._port.set_abort(True)
      self._pulse_release_at = now + ABORT_PULSE_S
      self._state = "abort_release"
      return

    if self._state == "abort_release":
      if now < (self._pulse_release_at or 0.0):
        return
      self._port.set_abort(False)
      self._state = "abort_wait_idle"
      self._idle_deadline = now + IDLE_TIMEOUT_S
      return

    if self._state == "abort_wait_idle":
      if status.is_idle:
        self._aborted = True
        return
      if self._idle_deadline is not None and now > self._idle_deadline:
        self._aborted = True
