###############################################################################
# Name: master_z_go.py
# Uses: Python mirror of the PLC MASTER_Z_GO rung, used as a user-facing
#       preflight before the G-code interpreter queues a head transfer.
# Notes:
#   The PLC remains authoritative -- it trips ERROR_CODE 5001 on its own.  This
#   mirror exists only so the operator gets a descriptive message naming which
#   term is blocking, instead of a transfer that silently does not happen.
#   See specs/motion-safety.allium#ZMotionRequiresMasterZGo and
#   specs/winder-states.allium#RuntimeAndPLCBothEnforceSafety.
#
#   Source of truth for the logic below:
#   winder/plc/state_5_move_z/main/main.rung:13-19
#
#     no_latch_collision    = Z_FIXED_LATCHED and ACTUATOR_POS == 2
#                             or not Z_FIXED_LATCHED
#     no_apa_collision      = X_XFER_OK or Y_XFER_OK
#     no_supports_collision = X_XFER_OK and ( ... ) or Y_XFER_OK
#     MASTER_Z_GO           = no_latch_collision
#                             and no_supports_collision
#                             and no_apa_collision
###############################################################################

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from dune_winder.queued_motion.safety import (
    MotionSafetyLimits,
    QueuedMotionCollisionState,
)


# PLC error code raised by state_5_move_z when MASTER_Z_GO is false.
MASTER_Z_GO_ERROR_CODE = 5001

TERM_NO_LATCH_COLLISION = "no_latch_collision"
TERM_NO_APA_COLLISION = "no_apa_collision"
TERM_NO_SUPPORTS_COLLISION = "no_supports_collision"


@dataclass(frozen=True)
class MasterZGoTerm:
    """One named conjunct of the MASTER_Z_GO rung."""

    name: str
    ok: bool
    detail: str = ""


def _in_band(value: float, minimum: float, maximum: float) -> bool:
    """Inclusive range test, matching the ladder LIM instruction."""
    return float(minimum) <= float(value) <= float(maximum)


def _support_windows(y_position: float, limits: MotionSafetyLimits):
    """
    The three support_collision_window_* bits from main/main.rung:126-130.

    Returns:
      Tuple of (bottom, middle, top) booleans.
    """
    return (
        _in_band(
            y_position,
            limits.support_collision_bottom_min_y,
            limits.support_collision_bottom_max_y,
        ),
        _in_band(
            y_position,
            limits.support_collision_middle_min_y,
            limits.support_collision_middle_max_y,
        ),
        _in_band(
            y_position,
            limits.support_collision_top_min_y,
            limits.support_collision_top_max_y,
        ),
    )


def _evaluate_no_latch_collision(transfer_state, latch_detail: str) -> MasterZGoTerm:
    fixed_latched = bool(transfer_state.get("fixedLatched"))
    actuator_pos = int(transfer_state.get("actuatorPos", 0))

    ok = (not fixed_latched) or actuator_pos == 2
    if ok:
        return MasterZGoTerm(TERM_NO_LATCH_COLLISION, True)

    detail = latch_detail or (
        "fixed-latched, ACTUATOR_POS="
        + str(actuator_pos)
        + " (needs 2 before the arm can extend)"
    )
    return MasterZGoTerm(TERM_NO_LATCH_COLLISION, False, detail)


def _evaluate_no_apa_collision(x_transfer_ok: bool, y_transfer_ok: bool):
    if x_transfer_ok or y_transfer_ok:
        return MasterZGoTerm(TERM_NO_APA_COLLISION, True)

    return MasterZGoTerm(
        TERM_NO_APA_COLLISION,
        False,
        "X_XFER_OK=0, Y_XFER_OK=0 (gantry not parked in a transfer window)",
    )


def _evaluate_no_supports_collision(
    *,
    x_transfer_ok: bool,
    y_transfer_ok: bool,
    x_position: float,
    y_position: float,
    limits: MotionSafetyLimits,
    collision_state: QueuedMotionCollisionState,
):
    if y_transfer_ok:
        return MasterZGoTerm(TERM_NO_SUPPORTS_COLLISION, True)

    bottom, middle, top = _support_windows(y_position, limits)

    if not bottom and not middle and not top:
        # Y is clear of every support band, so no frame lock can be in the way.
        if x_transfer_ok:
            return MasterZGoTerm(TERM_NO_SUPPORTS_COLLISION, True)
        return MasterZGoTerm(
            TERM_NO_SUPPORTS_COLLISION,
            False,
            "X_XFER_OK=0 and Y_XFER_OK=0",
        )

    in_head_band = _in_band(
        x_position, limits.transfer_zone_head_min_x, limits.transfer_zone_head_max_x
    )
    in_foot_band = _in_band(
        x_position, limits.transfer_zone_foot_min_x, limits.transfer_zone_foot_max_x
    )

    rows = (
        (
            "bottom",
            bottom,
            collision_state.frame_lock_head_btm,
            collision_state.frame_lock_foot_btm,
        ),
        (
            "middle",
            middle,
            collision_state.frame_lock_head_mid,
            collision_state.frame_lock_foot_mid,
        ),
        (
            "top",
            top,
            collision_state.frame_lock_head_top,
            collision_state.frame_lock_foot_top,
        ),
    )

    head_clear = in_head_band and any(
        active and not bool(head_lock) for _row, active, head_lock, _foot_lock in rows
    )
    foot_clear = in_foot_band and any(
        active and not bool(foot_lock) for _row, active, _head_lock, foot_lock in rows
    )

    if x_transfer_ok and (head_clear or foot_clear):
        return MasterZGoTerm(TERM_NO_SUPPORTS_COLLISION, True)

    active_rows = [row for row, active, _h, _f in rows if active]
    detail = "Y=" + str(round(float(y_position), 1)) + " is inside the "
    detail += "/".join(active_rows) + " support band"
    detail += "s" if len(active_rows) > 1 else ""

    if not x_transfer_ok:
        detail += "; X_XFER_OK=0"
    elif not in_head_band and not in_foot_band:
        detail += (
            "; X="
            + str(round(float(x_position), 1))
            + " is in neither the head band ["
            + str(limits.transfer_zone_head_min_x)
            + ", "
            + str(limits.transfer_zone_head_max_x)
            + "] nor the foot band ["
            + str(limits.transfer_zone_foot_min_x)
            + ", "
            + str(limits.transfer_zone_foot_max_x)
            + "]"
        )
    else:
        blocking = []
        for row, active, head_lock, foot_lock in rows:
            if not active:
                continue
            if in_head_band and bool(head_lock):
                blocking.append("FRAME_LOC_HD_" + row.upper()[:3])
            if in_foot_band and bool(foot_lock):
                blocking.append("FRAME_LOC_FT_" + row.upper()[:3])
        if blocking:
            detail += " with " + ", ".join(blocking) + " asserted"

    return MasterZGoTerm(TERM_NO_SUPPORTS_COLLISION, False, detail)


def evaluate_master_z_go(
    *,
    transfer_state,
    x_transfer_ok: bool,
    y_transfer_ok: bool,
    x_position: float,
    y_position: float,
    limits: MotionSafetyLimits,
    collision_state: QueuedMotionCollisionState,
    latch_detail: str = "",
) -> list[MasterZGoTerm]:
    """
    Evaluate the three MASTER_Z_GO conjuncts against live machine state.

    Args:
      transfer_state: A Head._readTransferStateNow() dictionary.
      x_transfer_ok: Live X_XFER_OK.
      y_transfer_ok: Live Y_XFER_OK.
      x_position: Current X axis position (mm).
      y_position: Current Y axis position (mm).
      limits: Machine geometry bands.
      collision_state: Live frame-lock sensor state.
      latch_detail: Optional richer explanation for a failing latch term,
        typically Head.describeLatchConflict().

    Returns:
      One MasterZGoTerm per conjunct, in rung order.
    """
    return [
        _evaluate_no_latch_collision(transfer_state, latch_detail),
        _evaluate_no_apa_collision(bool(x_transfer_ok), bool(y_transfer_ok)),
        _evaluate_no_supports_collision(
            x_transfer_ok=bool(x_transfer_ok),
            y_transfer_ok=bool(y_transfer_ok),
            x_position=float(x_position),
            y_position=float(y_position),
            limits=limits,
            collision_state=collision_state,
        ),
    ]


def master_z_go_is_ready(terms) -> bool:
    """True when every conjunct holds, i.e. the PLC would set MASTER_Z_GO."""
    return all(term.ok for term in terms)


def format_master_z_go_message(
    terms,
    *,
    headline: str = "Head transfer blocked: MASTER_Z_GO transfer lockout is not ready.",
    state_summary: Optional[str] = None,
) -> str:
    """
    Render the operator-facing explanation of a blocked transfer.

    Args:
      terms: Result of evaluate_master_z_go().
      headline: First line of the message.
      state_summary: Optional raw sensor dump appended as a final line.

    Returns:
      Multi-line message string.
    """
    width = max(len(term.name) for term in terms) + 1

    lines = [headline, "", "Blocking terms:"]
    for term in terms:
        label = (term.name + ":").ljust(width)
        lines.append("  - " + label + " " + ("OK" if term.ok else term.detail))

    lines.append("")
    lines.append("(PLC would raise ERROR_CODE " + str(MASTER_Z_GO_ERROR_CODE) + ".)")

    if state_summary:
        lines.append("")
        lines.append(state_summary)

    return "\n".join(lines)
