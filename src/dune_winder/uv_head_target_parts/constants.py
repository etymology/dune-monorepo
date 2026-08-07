from __future__ import annotations

import re

from dune_winder.paths import REPO_ROOT


_PIN_NAME_RE = re.compile(r"^P?[ABF]\d+$")
_RECIPE_SITE_RE = re.compile(
    r"G109\s+(P[AB]\d+)\s+P([A-Z]{2})\s+G103\s+(P[AB]\d+)\s+(P[AB]\d+).*?\(([^()]*)\)"
)
_DEFAULT_MACHINE_CALIBRATION_PATH = REPO_ROOT / "config" / "machineCalibration.json"
_DEFAULT_LAYER_CALIBRATION_DIRECTORIES = (REPO_ROOT / "config" / "APA",)
_AXIS_EPSILON = 1e-9
_ORIENTATION_TOKENS = ("BR", "BL", "LT", "LB", "RT", "RB", "TR", "TL")
# Keep in sync with the copy in api/commands.py (machine_compute_roller_y_cal)
# and the runtime keyword loop in gcode/handler_base.py (_run_macro_call).
_ANCHOR_TO_TARGET_RE = re.compile(
    r"~anchorToTarget\("
    r"(?P<anchor>[PAB]\d+),(?P<target>[PAB]\d+)"
    r"(?:,(?:offset=\([^)]+\)"
    r"|hover=(?:True|False|1|0|yes|no|on|off)"
    r"|inTwoMoves=(?:True|False|1|0|yes|no|on|off)"
    r"|jerk=(?:default|gentle|jerky)"
    r")){0,4}"
    r"\)",
    re.IGNORECASE,
)
