"""Shared helpers for U/V/XG template gcode tests."""

MERGE = "G113 PPRECISE "
TOLERANT = "G113 PTOLERANT "


def coord(axis: str, value: float) -> str:
    text = "{0:.6f}".format(float(value)).rstrip("0").rstrip(".")
    if text in ("", "-0"):
        text = "0"
    return axis + text
