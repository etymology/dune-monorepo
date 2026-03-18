"""Mapping from Python builtin/math function names to PLC CPT expressions or
expansion markers.  The IR builder uses this to decide whether a call can be
inlined as a CPT function call or needs multi-rung expansion by ir_to_ld."""
from __future__ import annotations
from .types import PLCType

# Functions that map directly to a single CPT function name.
# Key: Python qualified name  Value: (cpt_func_name, result_type)
CPT_INLINE: dict[str, tuple[str, PLCType]] = {
    "abs":        ("ABS",       PLCType.REAL),
    "math.sqrt":  ("SQR",       PLCType.REAL),
    "math.hypot": ("SQR_HYPOT", PLCType.REAL),  # handled specially as SQR(a*a+b*b)
    "math.sin":   ("SIN",       PLCType.REAL),
    "math.cos":   ("COS",       PLCType.REAL),
    "math.tan":   ("TAN",       PLCType.REAL),
    "math.asin":  ("ASN",       PLCType.REAL),
    "math.acos":  ("ACS",       PLCType.REAL),
    "math.floor": ("TRUNC",     PLCType.DINT),
    "float":      ("PASSTHRU",  PLCType.REAL),   # no-op cast
    "int":        ("TRUNC",     PLCType.DINT),
}

# Functions that require multi-rung expansion in ir_to_ld.
# The value is an opaque tag used by LDEmitter to dispatch the right expansion.
EXPAND: dict[str, str] = {
    "math.atan2": "ATAN2",
    "math.ceil":  "CEIL",
    "math.isinf": "ISINF",
    "min":        "MIN",
    "max":        "MAX",
}

# Constants
CONST_MAP: dict[str, float] = {
    "math.pi":  3.14159265358979,
    "math.tau": 6.28318530717959,
    "math.e":   2.71828182845905,
    "math.inf": float("inf"),
}

# MotionSegment Python attribute name → SegQueue UDT field path
SEG_ATTR_MAP: dict[str, str] = {
    "x":            "XY[0]",
    "y":            "XY[1]",
    "speed":        "Speed",
    "accel":        "Accel",
    "decel":        "Decel",
    "jerk_accel":   "JerkAccel",
    "jerk_decel":   "JerkDecel",
    "term_type":    "TermType",
    "seg_type":     "SegType",
    "seq":          "Seq",
    "circle_type":  "CircleType",
    "via_center_x": "ViaCenter[0]",
    "via_center_y": "ViaCenter[1]",
    "direction":    "Direction",
    "valid":        "Valid",
}

# PLCType for each SegQueue field
SEG_FIELD_TYPE: dict[str, PLCType] = {
    "XY[0]":       PLCType.REAL,
    "XY[1]":       PLCType.REAL,
    "Speed":       PLCType.REAL,
    "Accel":       PLCType.REAL,
    "Decel":       PLCType.REAL,
    "JerkAccel":   PLCType.REAL,
    "JerkDecel":   PLCType.REAL,
    "TermType":    PLCType.DINT,
    "SegType":     PLCType.DINT,
    "Seq":         PLCType.DINT,
    "CircleType":  PLCType.DINT,
    "ViaCenter[0]": PLCType.REAL,
    "ViaCenter[1]": PLCType.REAL,
    "Direction":   PLCType.DINT,
    "Valid":       PLCType.BOOL,
}
