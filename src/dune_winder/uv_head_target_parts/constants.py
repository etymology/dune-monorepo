from __future__ import annotations

import re

from dune_winder.paths import PACKAGE_ROOT, REPO_ROOT


_PIN_NAME_RE = re.compile(r"^P?[ABF]\d+$")
_RECIPE_SITE_RE = re.compile(
    r"G109\s+(P[AB]\d+)\s+P([A-Z]{2})\s+G103\s+(P[AB]\d+)\s+(P[AB]\d+).*?\(([^()]*)\)"
)
_DEFAULT_MACHINE_CALIBRATION_PATH = (
    REPO_ROOT / "dune_winder" / "config" / "machineCalibration.json"
)
_DEFAULT_LAYER_CALIBRATION_DIRECTORIES = (PACKAGE_ROOT / "config" / "APA",)
_AXIS_EPSILON = 1e-9
_ORIENTATION_TOKENS = ("BR", "BL", "LT", "LB", "RT", "RB", "TR", "TL")
_ANCHOR_TO_TARGET_RE = re.compile(
    r"~anchorToTarget\("
    r"(?P<anchor>[PAB]\d+),(?P<target>[PAB]\d+)"
    r"(?:,(?:offset=\([^)]+\)|hover=(?:True|False|1|0|yes|no|on|off))){0,2}"
    r"\)",
    re.IGNORECASE,
)
