###############################################################################
# Name: support_collision_forecast.py
# Uses: Forecast which frame-support keepouts an upcoming wrap will drive a
#       same-side transfer into, so the machine-layout support bars can blink
#       ahead of the move.  Pure/​injectable so the geometry source can be
#       faked in tests.
###############################################################################

from __future__ import annotations

import re
from typing import Callable, Optional

# Six frame-support keepouts: a transfer-zone X band (head/foot) crossed with a
# support-collision Y band (top/middle/bottom).
SUPPORT_COLLISION_KEYS = (
    "headTop",
    "headMid",
    "headBtm",
    "footTop",
    "footMid",
    "footBtm",
)

# Wrap labels look like ``(n,m)`` at the head of a recipe line.  The negative
# look-behind keeps ``offset=(1,0)`` from being mistaken for a wrap label, and
# requiring a digit after the comma skips ``~increment(0,-50)``.
_WRAP_LABEL_RE = re.compile(r"(?<![=\w])\(\s*(\d+)\s*,\s*\d+")

# Two pins of an anchor-to-target command, e.g. ``~anchorToTarget(A12,A34,...)``.
_ANCHOR_PINS_RE = re.compile(
    r"~anchorToTarget\(\s*(P?[AB]\d+)\s*,\s*(P?[AB]\d+)",
    re.IGNORECASE,
)

_ANCHOR_MARKER = "~anchortotarget"


def empty_forecast() -> dict[str, bool]:
    return {key: False for key in SUPPORT_COLLISION_KEYS}


def _line_wrap_number(line: str) -> Optional[int]:
    match = _WRAP_LABEL_RE.search(line)
    if match is None:
        return None
    return int(match.group(1))


def current_wrap_number(lines, current_line_index) -> Optional[int]:
    """Wrap number labelling the current gcode line.

    ``current_line_index`` is the zero-based index reported by
    ``GCodeHandler.getLine()``.  When the current line carries no label we walk
    backwards to the most recent labelled line (the program is partway through
    that wrap), and only then forwards to the first upcoming label.
    """
    if not lines:
        return None

    if current_line_index is None or current_line_index < 0:
        start = -1
    else:
        start = min(int(current_line_index), len(lines) - 1)

    for index in range(start, -1, -1):
        wrap = _line_wrap_number(lines[index])
        if wrap is not None:
            return wrap

    for index in range(start + 1, len(lines)):
        wrap = _line_wrap_number(lines[index])
        if wrap is not None:
            return wrap

    return None


def _iter_anchor_to_target_commands(line: str):
    """Yield ``(command_text, anchor_pin, target_pin)`` for each command.

    The command text is extracted with balanced parentheses so an inner
    ``offset=(x,y)`` does not truncate it.
    """
    lower = line.lower()
    search_from = 0
    while True:
        start = lower.find(_ANCHOR_MARKER, search_from)
        if start < 0:
            return

        open_paren = line.find("(", start)
        if open_paren < 0:
            return

        depth = 0
        end = None
        for index in range(open_paren, len(line)):
            char = line[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end = index
                    break

        if end is None:
            return

        command_text = line[start : end + 1]
        search_from = end + 1

        pins = _ANCHOR_PINS_RE.match(command_text)
        if pins is None:
            continue
        yield command_text, pins.group(1), pins.group(2)


def _pin_family(pin: str) -> str:
    text = str(pin).strip().upper()
    if text.startswith("P"):
        text = text[1:]
    return text[:1]


def _is_same_side(anchor_pin: str, target_pin: str) -> bool:
    return _pin_family(anchor_pin) == _pin_family(target_pin)


def _classify(
    x: float,
    y: float,
    transfer_zones: dict[str, tuple[float, float]],
    support_bands: dict[str, tuple[float, float]],
) -> Optional[str]:
    side = None
    for side_key, (x_min, x_max) in transfer_zones.items():
        if x_min <= x <= x_max:
            side = side_key
            break
    if side is None:
        return None

    for band_key, (y_min, y_max) in support_bands.items():
        if y_min <= y <= y_max:
            return side + band_key

    return None


def compute_support_collision_forecast(
    lines,
    current_line_index,
    *,
    head_point_fn: Callable[[str], Optional[tuple[float, float]]],
    transfer_zones: dict[str, tuple[float, float]],
    support_bands: dict[str, tuple[float, float]],
    wraps_ahead: int = 1,
) -> dict[str, bool]:
    """Flag each support keepout that an upcoming same-side transfer enters.

    Looks at the current wrap ``n`` through ``n + wraps_ahead`` and, for every
    same-side (A-A / B-B) ``~anchorToTarget`` command labelled with one of those
    wraps, asks ``head_point_fn`` for the transfer's head end point and tests it
    against the six keepout boxes.  Independent of live machine state - it
    forecasts purely from the wrap-number annotations.
    """
    flags = empty_forecast()

    wrap = current_wrap_number(lines, current_line_index)
    if wrap is None:
        return flags

    target_wraps = {wrap + delta for delta in range(0, int(wraps_ahead) + 1)}

    for line in lines:
        line_wrap = _line_wrap_number(line)
        if line_wrap is None or line_wrap not in target_wraps:
            continue

        for command_text, anchor_pin, target_pin in _iter_anchor_to_target_commands(
            line
        ):
            if not _is_same_side(anchor_pin, target_pin):
                continue

            point = head_point_fn(command_text)
            if point is None:
                continue

            key = _classify(point[0], point[1], transfer_zones, support_bands)
            if key is not None:
                flags[key] = True

    return flags
