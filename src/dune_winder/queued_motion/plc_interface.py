from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dune_winder.io.devices.tag_bus_registry import tag_bus_for

from .jerk_limits import is_valid_queued_motion_jerk
from .safety import QueuedMotionCollisionState
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
TAG_STOP_REQUEST = "QueueStopRequest"

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
TAG_X_ACTUAL_POSITION = "X_axis.ActualPosition"
TAG_Y_ACTUAL_POSITION = "Y_axis.ActualPosition"
TAG_Z_ACTUAL_POSITION = "Z_axis.ActualPosition"
TAG_SEG_QUEUE = "SegQueue"
TAG_FRAME_LOCK_HEAD_TOP = "MACHINE_SW_STAT[26]"
TAG_FRAME_LOCK_HEAD_MID = "MACHINE_SW_STAT[27]"
TAG_FRAME_LOCK_HEAD_BTM = "MACHINE_SW_STAT[28]"
TAG_FRAME_LOCK_FOOT_TOP = "MACHINE_SW_STAT[29]"
TAG_FRAME_LOCK_FOOT_MID = "MACHINE_SW_STAT[30]"
TAG_FRAME_LOCK_FOOT_BTM = "MACHINE_SW_STAT[31]"

ACK_TIMEOUT_S = 5.0
ABORT_PULSE_S = 0.10
START_PULSE_S = 0.10
POST_RESET_SETTLE_S = 0.10
START_TIMEOUT_S = 5.0
IDLE_TIMEOUT_S = 120.0
PLC_QUEUE_DEPTH = 32

_FRESH_WITHIN_MS = 50
_READ_TIMEOUT_MS = 250

_STATUS_TAGS = (
    TAG_REQ_ID,
    TAG_LAST_REQ_ID,
    TAG_ACK,
    TAG_MOTION_FAULT,
    TAG_CUR_ISSUED,
    TAG_NEXT_ISSUED,
    TAG_ACTIVE_SEQ,
    TAG_PENDING_SEQ,
    TAG_QUEUE_FAULT,
    TAG_MOVE_A_ER,
    TAG_MOVE_B_ER,
    TAG_QUEUE_COUNT,
    TAG_USE_A_AS_CURRENT,
    TAG_MOVE_PENDING_STATUS,
    TAG_FAULT_CODE,
)

_FRAME_LOCK_TAGS = (
    TAG_FRAME_LOCK_HEAD_TOP,
    TAG_FRAME_LOCK_HEAD_MID,
    TAG_FRAME_LOCK_HEAD_BTM,
    TAG_FRAME_LOCK_FOOT_TOP,
    TAG_FRAME_LOCK_FOOT_MID,
    TAG_FRAME_LOCK_FOOT_BTM,
)


def _snap_value(snap, default):
    if snap is None or snap.source == "default":
        return default
    return snap.value


def _frame_lock_bool(snap) -> bool:
    if snap is None or snap.source == "default":
        return False
    try:
        return bool(int(snap.value) & 0x01)
    except (TypeError, ValueError):
        return False


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
        return (
            (not self.cur_issued) and (not self.next_issued) and self.queue_count <= 0
        )


def validate_queue_segment(seg: MotionSegment) -> None:
    if seg.seg_type not in (SEG_TYPE_LINE, SEG_TYPE_CIRCLE):
        raise ValueError("seg_type must be 1 (line) or 2 (circle)")
    if seg.speed <= 0 or seg.accel <= 0 or seg.decel <= 0:
        raise ValueError("speed, accel, and decel must be > 0")
    if not is_valid_queued_motion_jerk(seg.jerk_accel):
        raise ValueError("jerk_accel must be finite and > 0 for queued motion")
    if not is_valid_queued_motion_jerk(seg.jerk_decel):
        raise ValueError("jerk_decel must be finite and > 0 for queued motion")
    if not (0 <= seg.term_type <= 6):
        raise ValueError("term_type must be in [0, 6]")
    if seg.seg_type == SEG_TYPE_CIRCLE:
        if not (0 <= seg.circle_type <= 3):
            raise ValueError("circle_type must be in [0, 3]")
        if not (0 <= seg.direction <= 3):
            raise ValueError("direction must be in [0, 3] for 2D MCCM")


class QueuedMotionPLCInterface:
    def __init__(self, plc) -> None:
        # `plc` is the legacy PLC handle; the bus carries atomic tag traffic
        # while UDT (IncomingSeg) and parametric (SegQueue[i].Speed) accesses
        # still go through the legacy driver, which the bus does not model.
        self._plc = plc
        self._bus = tag_bus_for(plc)

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
        # The bus owns its poll thread when started. For non-started buses,
        # `status()` and friends drive their own fresh reads.
        pass

    def set_abort(self, enabled: bool) -> None:
        self._bus.write(TAG_ABORT, bool(enabled), _READ_TIMEOUT_MS)

    def set_start(self, enabled: bool) -> None:
        self._bus.write(TAG_START, bool(enabled), _READ_TIMEOUT_MS)

    def set_stop_request(self, enabled: bool) -> None:
        self._bus.write(TAG_STOP_REQUEST, bool(enabled), _READ_TIMEOUT_MS)

    def write_segment(self, seg: MotionSegment) -> None:
        # IncomingSeg is a UDT; write through the legacy driver.
        validate_queue_segment(seg)
        result = self._plc.write((TAG_INCOMING_SEG, self.segment_to_udt(seg)))
        if result is None:
            raise RuntimeError(f"Write failed for {TAG_INCOMING_SEG}")

    def set_req_id(self, req_id: int) -> None:
        self._bus.write(TAG_REQ_ID, int(req_id), _READ_TIMEOUT_MS)

    def sync_req_id(self) -> int:
        snaps = self._bus.read_many_fresh([TAG_LAST_REQ_ID, TAG_REQ_ID])
        last = snaps.get(TAG_LAST_REQ_ID)
        if last is not None and last.source != "default":
            return int(last.value)
        cur = snaps.get(TAG_REQ_ID)
        if cur is not None and cur.source != "default":
            return int(cur.value)
        return 0

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

    def _read_one_legacy(self, tag: str) -> Any:
        return self._extract_read_value(self._plc.read([tag]), tag)

    def read_seg_queue_speeds(self, count: int) -> list[float]:
        """Read the Speed field from SegQueue[0..count-1]."""
        return [
            float(self._read_one_legacy(f"{TAG_SEG_QUEUE}[{i}].Speed"))
            for i in range(count)
        ]

    def write_seg_queue_speed(self, index: int, speed: float) -> None:
        """Write the Speed field of SegQueue[index]."""
        result = self._plc.write((f"{TAG_SEG_QUEUE}[{index}].Speed", float(speed)))
        if result is None:
            raise RuntimeError(f"Write failed for {TAG_SEG_QUEUE}[{index}].Speed")

    def read_actual_xy(self) -> tuple[float, float]:
        snaps = self._bus.read_many_fresh(
            [TAG_X_ACTUAL_POSITION, TAG_Y_ACTUAL_POSITION]
        )
        return (
            float(_snap_value(snaps.get(TAG_X_ACTUAL_POSITION), 0.0)),
            float(_snap_value(snaps.get(TAG_Y_ACTUAL_POSITION), 0.0)),
        )

    def read_actual_z(self) -> float:
        snap = self._bus.read_fresh(
            TAG_Z_ACTUAL_POSITION, _FRESH_WITHIN_MS, _READ_TIMEOUT_MS
        )
        return float(_snap_value(snap, 0.0))

    def read_collision_state(self) -> QueuedMotionCollisionState:
        snaps = self._bus.read_many_fresh([TAG_Z_ACTUAL_POSITION, *_FRAME_LOCK_TAGS])
        return QueuedMotionCollisionState(
            z_actual_position=float(_snap_value(snaps.get(TAG_Z_ACTUAL_POSITION), 0.0)),
            frame_lock_head_top=_frame_lock_bool(snaps.get(TAG_FRAME_LOCK_HEAD_TOP)),
            frame_lock_head_mid=_frame_lock_bool(snaps.get(TAG_FRAME_LOCK_HEAD_MID)),
            frame_lock_head_btm=_frame_lock_bool(snaps.get(TAG_FRAME_LOCK_HEAD_BTM)),
            frame_lock_foot_top=_frame_lock_bool(snaps.get(TAG_FRAME_LOCK_FOOT_TOP)),
            frame_lock_foot_mid=_frame_lock_bool(snaps.get(TAG_FRAME_LOCK_FOOT_MID)),
            frame_lock_foot_btm=_frame_lock_bool(snaps.get(TAG_FRAME_LOCK_FOOT_BTM)),
        )

    def status(self) -> QueuedMotionStatus:
        snaps = self._bus.read_many_fresh(list(_STATUS_TAGS))

        def get_int(tag: str) -> int:
            return int(_snap_value(snaps.get(tag), 0) or 0)

        def get_bool(tag: str) -> bool:
            return bool(_snap_value(snaps.get(tag), False))

        return QueuedMotionStatus(
            req_id=get_int(TAG_REQ_ID),
            last_req_id=get_int(TAG_LAST_REQ_ID),
            ack=get_int(TAG_ACK),
            motion_fault=get_bool(TAG_MOTION_FAULT),
            cur_issued=get_bool(TAG_CUR_ISSUED),
            next_issued=get_bool(TAG_NEXT_ISSUED),
            active_seq=get_int(TAG_ACTIVE_SEQ),
            pending_seq=get_int(TAG_PENDING_SEQ),
            queue_fault=get_bool(TAG_QUEUE_FAULT),
            move_a_er=get_int(TAG_MOVE_A_ER),
            move_b_er=get_int(TAG_MOVE_B_ER),
            queue_count=get_int(TAG_QUEUE_COUNT),
            use_a_as_current=get_bool(TAG_USE_A_AS_CURRENT),
            move_pending_status=get_int(TAG_MOVE_PENDING_STATUS),
            fault_code=get_int(TAG_FAULT_CODE),
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

    def set_stop_request(self, enabled: bool) -> None:
        self.port.set_stop_request(enabled)

    def read_seg_queue_speeds(self, count: int) -> list[float]:
        return self.port.read_seg_queue_speeds(count)

    def write_seg_queue_speed(self, index: int, speed: float) -> None:
        self.port.write_seg_queue_speed(index, speed)

    def status(self) -> QueuedMotionStatus:
        return self.port.status()

    def snapshot_lines(self) -> list[str]:
        return self.port.snapshot_lines()
