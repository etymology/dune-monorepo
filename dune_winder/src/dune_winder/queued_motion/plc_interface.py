from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from dune_winder.io.devices.plc import PLC

from .segment_types import (
  MotionSegment,
  SEG_TYPE_CIRCLE,
  SEG_TYPE_LINE,
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
TAG_MOVE_A_ER = "MoveA.ER"
TAG_MOVE_B_ER = "MoveB.ER"
TAG_QUEUE_COUNT = "QueueCount"
TAG_USE_A_AS_CURRENT = "UseAasCurrent"
TAG_MOVE_PENDING_STATUS = "X_Y.MovePendingStatus"
TAG_FAULT_CODE = "FaultCode"

ACK_TIMEOUT_S = 5.0
ABORT_PULSE_S = 0.10
START_PULSE_S = 0.10
POST_RESET_SETTLE_S = 0.10
START_TIMEOUT_S = 5.0
IDLE_TIMEOUT_S = 120.0
PLC_QUEUE_DEPTH = 32


@dataclass(frozen=True)
class QueuedMotionStatus:
  req_id: int
  last_req_id: int
  ack: int
  motion_fault: bool
  cur_issued: bool
  next_issued: bool
  active_seq: int
  pending_seq: int
  queue_fault: bool
  move_a_er: int
  move_b_er: int
  queue_count: int
  use_a_as_current: bool
  move_pending_status: int
  fault_code: int

  @property
  def is_idle(self) -> bool:
    return (not self.cur_issued) and (not self.next_issued) and self.queue_count <= 0


def validate_queue_segment(seg: MotionSegment) -> None:
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


class QueuedMotionPLCInterface:
  def __init__(self, plc) -> None:
    self._plc = plc

    polled = PLC.Tag.Attributes()
    polled.isPolled = True

    self._incoming_seg = PLC.Tag(plc, TAG_INCOMING_SEG, tagType="MotionSeg")
    self._req_id = PLC.Tag(plc, TAG_REQ_ID, polled, tagType="DINT")
    self._last_req_id = PLC.Tag(plc, TAG_LAST_REQ_ID, polled, tagType="DINT")
    self._ack = PLC.Tag(plc, TAG_ACK, polled, tagType="DINT")
    self._abort = PLC.Tag(plc, TAG_ABORT, tagType="BOOL")
    self._start = PLC.Tag(plc, TAG_START, tagType="BOOL")

    self._motion_fault = PLC.Tag(plc, TAG_MOTION_FAULT, polled, tagType="BOOL")
    self._cur_issued = PLC.Tag(plc, TAG_CUR_ISSUED, polled, tagType="BOOL")
    self._next_issued = PLC.Tag(plc, TAG_NEXT_ISSUED, polled, tagType="BOOL")
    self._active_seq = PLC.Tag(plc, TAG_ACTIVE_SEQ, polled, tagType="DINT")
    self._pending_seq = PLC.Tag(plc, TAG_PENDING_SEQ, polled, tagType="DINT")
    self._queue_fault = PLC.Tag(plc, TAG_QUEUE_FAULT, polled, tagType="BOOL")
    self._move_a_er = PLC.Tag(plc, TAG_MOVE_A_ER, polled, tagType="DINT")
    self._move_b_er = PLC.Tag(plc, TAG_MOVE_B_ER, polled, tagType="DINT")
    self._queue_count = PLC.Tag(plc, TAG_QUEUE_COUNT, polled, tagType="DINT")
    self._use_a_as_current = PLC.Tag(plc, TAG_USE_A_AS_CURRENT, polled, tagType="BOOL")
    self._move_pending_status = PLC.Tag(plc, TAG_MOVE_PENDING_STATUS, polled, tagType="DINT")
    self._fault_code = PLC.Tag(plc, TAG_FAULT_CODE, polled, tagType="DINT")

  @staticmethod
  def segment_to_udt(seg: MotionSegment) -> dict:
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

  def poll(self) -> None:
    PLC.Tag.pollAll(self._plc)

  def set_abort(self, enabled: bool) -> None:
    self._abort.set(bool(enabled))

  def set_start(self, enabled: bool) -> None:
    self._start.set(bool(enabled))

  def write_segment(self, seg: MotionSegment) -> None:
    validate_queue_segment(seg)
    self._incoming_seg.set(self.segment_to_udt(seg))

  def set_req_id(self, req_id: int) -> None:
    self._req_id.set(int(req_id))

  def sync_req_id(self) -> int:
    last_req = self._last_req_id.get()
    if last_req is not None:
      return int(last_req)
    req = self._req_id.get()
    if req is not None:
      return int(req)
    return 0

  def status(self) -> QueuedMotionStatus:
    return QueuedMotionStatus(
      req_id=int(self._req_id.get() or 0),
      last_req_id=int(self._last_req_id.get() or 0),
      ack=int(self._ack.get() or 0),
      motion_fault=bool(self._motion_fault.get()),
      cur_issued=bool(self._cur_issued.get()),
      next_issued=bool(self._next_issued.get()),
      active_seq=int(self._active_seq.get() or 0),
      pending_seq=int(self._pending_seq.get() or 0),
      queue_fault=bool(self._queue_fault.get()),
      move_a_er=int(self._move_a_er.get() or 0),
      move_b_er=int(self._move_b_er.get() or 0),
      queue_count=int(self._queue_count.get() or 0),
      use_a_as_current=bool(self._use_a_as_current.get()),
      move_pending_status=int(self._move_pending_status.get() or 0),
      fault_code=int(self._fault_code.get() or 0),
    )

  def snapshot_lines(self) -> list[str]:
    status = self.status()
    return [
      f"ReqID         = {status.req_id!r}",
      f"LastReqID     = {status.last_req_id!r}",
      f"Ack           = {status.ack!r}",
      f"MotionFault   = {status.motion_fault!r}",
      f"QueueFault    = {status.queue_fault!r}",
      f"MoveA.ER      = {status.move_a_er!r}",
      f"MoveB.ER      = {status.move_b_er!r}",
      f"CurIssued     = {status.cur_issued!r}",
      f"NextIssued    = {status.next_issued!r}",
      f"QueueCount    = {status.queue_count!r}",
      f"UseAasCurrent = {status.use_a_as_current!r}",
      f"MovePendingSt = {status.move_pending_status!r}",
      f"FaultCode     = {status.fault_code!r}",
      f"ActiveSeq     = {status.active_seq!r}",
      f"PendingSeq    = {status.pending_seq!r}",
    ]


class QueuedMotionPortAdapter:
  """Small adapter so runtime code can target PLC_Logic or direct PLC ports."""

  def __init__(self, port: QueuedMotionPLCInterface) -> None:
    self.port = port

  def poll(self) -> None:
    self.port.poll()

  def sync_req_id(self) -> int:
    return self.port.sync_req_id()

  def write_segment(self, seg: MotionSegment) -> None:
    self.port.write_segment(seg)

  def set_req_id(self, req_id: int) -> None:
    self.port.set_req_id(req_id)

  def set_abort(self, enabled: bool) -> None:
    self.port.set_abort(enabled)

  def set_start(self, enabled: bool) -> None:
    self.port.set_start(enabled)

  def status(self) -> QueuedMotionStatus:
    return self.port.status()

  def snapshot_lines(self) -> list[str]:
    return self.port.snapshot_lines()

