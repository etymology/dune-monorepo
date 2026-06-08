###############################################################################
# Name: loadcell.py
# Uses: Load-cell calibration: sample storage, quartic fit, and PLC coefficient
#       read/write for the tension_pid tension_tag -> tension conversion.
###############################################################################
"""Calibrate the load-cell ``tension_tag`` to ``tension`` (newtons).

The PLC converts the raw load-cell reading ``tension_tag`` into a tension in
newtons with a quartic polynomial::

    tension = a0 + a1*t + a2*t**2 + a3*t**3 + a4*t**4      (t = tension_tag)

whose coefficients live in the program-scope tags
``Program:tension_pid.a0 .. a4``.

This module records calibration samples (a known hung weight versus the
stabilised ``tension_tag`` reading), fits the quartic with least squares
(optionally forcing ``a0 = 0``), and reads/writes the coefficients on the PLC.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

LOGGER = logging.getLogger(__name__)

# Standard gravity (m/s^2). One gram-force = grams * GRAVITY / 1000 newtons.
GRAVITY = 9.80665
GRAMS_TO_NEWTONS = GRAVITY / 1000.0

# Raw load-cell tag (controller scope) and the converted output tag.
RAW_TENSION_TAG = "tension_tag"
TENSION_OUTPUT_TAG = "tension"

# Program-scope quartic coefficient tags, ordered a0..a4.
COEFFICIENT_KEYS = ("a0", "a1", "a2", "a3", "a4")
COEFFICIENT_TAGS = {key: f"Program:tension_pid.{key}" for key in COEFFICIENT_KEYS}

# Highest polynomial degree the PLC quartic form (a0 + a1*t + ... + a4*t^4)
# can represent. Lower-degree fits zero-fill the unused high-order terms so the
# PLC math stays as simple as the data allows.
MAX_DEGREE = 4
DEFAULT_MAX_DEGREE = 1  # Default to a straight line; simplest on the PLC.

# Defaults for stabilised capture of the load cell.
DEFAULT_CAPTURE_WINDOW = 10  # Number of readings that must agree.
DEFAULT_CAPTURE_INTERVAL = 0.1  # Seconds between readings.
DEFAULT_CAPTURE_TOLERANCE = 0.05  # Max peak-to-peak spread (tension_tag units).
DEFAULT_CAPTURE_TIMEOUT = 8.0  # Seconds before giving up on stabilisation.


# ---------------------------------------------------------------------------
# Sample model
# ---------------------------------------------------------------------------
@dataclass
class TensionSample:
    """A single calibration point: a hung weight and its load-cell reading."""

    id: int
    grams: float
    tension_tag: float
    created_at: float

    @property
    def newtons(self) -> float:
        """Calibrated weight expressed as a force in newtons."""
        return self.grams * GRAMS_TO_NEWTONS

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "grams": self.grams,
            "tensionTag": self.tension_tag,
            "newtons": self.newtons,
            "createdAt": self.created_at,
        }


# ---------------------------------------------------------------------------
# Fit
# ---------------------------------------------------------------------------
def effective_degree(point_count: int, max_degree: int, fix_intercept: bool) -> int:
    """Highest degree that ``point_count`` samples can support.

    A degree-d polynomial has ``d + 1`` free coefficients, or ``d`` when the
    intercept is pinned to zero. The result is clamped to ``[0, MAX_DEGREE]`` and
    capped by ``max_degree``; 0 means too few samples to fit anything.
    """
    cap = max(0, min(MAX_DEGREE, int(max_degree)))
    supported = point_count if fix_intercept else point_count - 1
    return max(0, min(cap, supported))


def fit_polynomial(
    tension_tags: list[float],
    newtons: list[float],
    max_degree: int,
    fix_intercept: bool,
) -> dict[str, Any] | None:
    """Least-squares fit of newtons against tension_tag.

    The fit degree is the largest the sample count supports, capped by
    ``max_degree`` (so few samples automatically yield a lower-degree fit).
    Unused high-order coefficients are returned as zero, collapsing the PLC
    quartic to the simplest form the data justifies.

    Args:
      tension_tags: Raw load-cell readings (the x values).
      newtons: Calibrated forces in newtons (the y values).
      max_degree: Upper bound on the polynomial degree (1..MAX_DEGREE).
      fix_intercept: When True, force ``a0 = 0`` (fit through the origin). The
        lever dead zone means the intercept is normally non-zero, so this is
        usually left off.

    Returns:
      A dict describing the fit, a dict with an ``error`` key when the fit is
      degenerate, or None when there are too few points to fit.
    """
    xs = np.asarray(tension_tags, dtype=np.float64)
    ys = np.asarray(newtons, dtype=np.float64)

    degree = effective_degree(int(xs.size), max_degree, fix_intercept)
    if degree < 1:
        return None

    try:
        if fix_intercept:
            # Columns t^1 .. t^degree; the intercept is pinned to zero.
            design = np.vstack([xs**power for power in range(1, degree + 1)]).T
            solution, _residuals, _rank, _singular = np.linalg.lstsq(
                design, ys, rcond=None
            )
            coefficients = [0.0, *solution.tolist()]
        else:
            # polyfit returns highest power first; reverse to a0..a_degree.
            poly = np.polyfit(xs, ys, degree)
            coefficients = poly[::-1].tolist()
    except (np.linalg.LinAlgError, ValueError) as exc:
        return {"error": f"Could not fit the samples: {exc}"}

    # Zero-fill the unused high-order coefficients up to a4.
    while len(coefficients) < len(COEFFICIENT_KEYS):
        coefficients.append(0.0)

    if not all(np.isfinite(coefficients)):
        return {"error": "Fit produced non-finite coefficients."}

    predicted = np.polyval(coefficients[::-1], xs)
    residuals = ys - predicted
    rms = float(np.sqrt(np.mean(residuals**2))) if residuals.size else 0.0
    max_residual = float(np.max(np.abs(residuals))) if residuals.size else 0.0

    return {
        "coefficients": {
            key: float(value) for key, value in zip(COEFFICIENT_KEYS, coefficients)
        },
        "degree": degree,
        "maxDegree": max(1, min(MAX_DEGREE, int(max_degree))),
        "fixIntercept": fix_intercept,
        "rmsNewtons": rms,
        "maxResidualNewtons": max_residual,
        "pointCount": int(xs.size),
    }


# ---------------------------------------------------------------------------
# PLC access helpers
# ---------------------------------------------------------------------------
def _read_tag_value(plc: Any, name: str) -> float | None:
    """Read a single numeric PLC tag, returning None on any failure."""
    if plc is None:
        return None
    # NOTE: pass a list. ControllogixPLC.read does ``driver.read(*tag)``, so a
    # bare string would be unpacked into individual characters and read a tag
    # named after its first letter.
    try:
        result = plc.read([name])
    except Exception as exc:  # noqa: BLE001 - PLC drivers raise broadly.
        LOGGER.warning("Failed to read PLC tag %s: %s", name, exc)
        return None
    if not result:
        return None

    entry = result[0]
    error = getattr(entry, "error", None)
    if error:
        LOGGER.warning("PLC reported error reading %s: %s", name, error)
        return None

    value = getattr(entry, "value", None)
    if value is None and isinstance(entry, (list, tuple)) and len(entry) > 1:
        value = entry[1]
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_live(plc: Any) -> dict[str, float | None]:
    """Return the current raw load-cell reading and converted tension."""
    return {
        "tensionTag": _read_tag_value(plc, RAW_TENSION_TAG),
        "tension": _read_tag_value(plc, TENSION_OUTPUT_TAG),
    }


def read_plc_coefficients(plc: Any) -> dict[str, Any]:
    """Read a0..a4 from the PLC.

    Returns a dict with ``available`` plus a ``coefficients`` mapping. When a
    coefficient cannot be read its value is None and ``available`` is False.
    """
    coefficients: dict[str, float | None] = {}
    available = plc is not None
    for key in COEFFICIENT_KEYS:
        value = _read_tag_value(plc, COEFFICIENT_TAGS[key])
        if value is None:
            available = False
        coefficients[key] = value
    return {"available": available, "coefficients": coefficients}


def write_plc_coefficients(plc: Any, coefficients: dict[str, float]) -> None:
    """Write a0..a4 to the PLC, raising RuntimeError on any failure."""
    if plc is None:
        raise RuntimeError("PLC is not available.")

    for key in COEFFICIENT_KEYS:
        if key not in coefficients:
            raise RuntimeError(f"Missing coefficient {key}.")
        tag = COEFFICIENT_TAGS[key]
        value = float(coefficients[key])
        try:
            result = plc.write((tag, value), typeName="REAL")
        except Exception as exc:  # noqa: BLE001 - PLC drivers raise broadly.
            raise RuntimeError(f"Failed to write {tag}: {exc}") from exc
        if result is None:
            raise RuntimeError(f"PLC rejected the write to {tag}.")


def capture_stable_tension(
    plc: Any,
    *,
    window: int = DEFAULT_CAPTURE_WINDOW,
    interval: float = DEFAULT_CAPTURE_INTERVAL,
    tolerance: float = DEFAULT_CAPTURE_TOLERANCE,
    timeout: float = DEFAULT_CAPTURE_TIMEOUT,
    sleep: Any = time.sleep,
    monotonic: Any = time.monotonic,
) -> dict[str, Any]:
    """Sample ``tension_tag`` until the reading settles.

    Reads repeatedly at ``interval`` seconds. Once the most recent ``window``
    readings span no more than ``tolerance`` (peak to peak), returns their mean
    with ``settled=True``. On timeout, returns the best available mean with
    ``settled=False`` so the operator can decide whether to keep it.

    Raises:
      RuntimeError: when no reading could be obtained at all.
    """
    if plc is None:
        raise RuntimeError("PLC is not available.")

    readings: list[float] = []
    deadline = monotonic() + max(timeout, interval)

    while True:
        value = _read_tag_value(plc, RAW_TENSION_TAG)
        if value is not None:
            readings.append(value)
            recent = readings[-window:]
            if len(recent) >= window:
                spread = max(recent) - min(recent)
                if spread <= tolerance:
                    return {
                        "tensionTag": float(np.mean(recent)),
                        "settled": True,
                        "spread": float(spread),
                        "sampleCount": len(recent),
                    }

        if monotonic() >= deadline:
            break
        sleep(interval)

    if not readings:
        raise RuntimeError("Could not read the load cell.")

    recent = readings[-window:]
    spread = max(recent) - min(recent)
    return {
        "tensionTag": float(np.mean(recent)),
        "settled": False,
        "spread": float(spread),
        "sampleCount": len(recent),
    }


# ---------------------------------------------------------------------------
# Persistent calibration store
# ---------------------------------------------------------------------------
class LoadcellCalibration:
    """Persistent store of calibration samples plus the fit configuration."""

    def __init__(self, storage_path: str | Path):
        self._path = Path(storage_path)
        self._samples: list[TensionSample] = []
        self._next_id = 1
        # The lever dead zone means the curve does not pass through the origin,
        # so the intercept is left free by default.
        self._fix_intercept = False
        self._max_degree = DEFAULT_MAX_DEGREE
        self._load()

    # -- persistence --------------------------------------------------------
    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("Could not read tension calibration %s: %s", self._path, exc)
            return

        self._fix_intercept = bool(data.get("fixIntercept", False))
        self._max_degree = int(data.get("maxDegree", DEFAULT_MAX_DEGREE))
        self._next_id = int(data.get("nextId", 1))
        self._samples = []
        for entry in data.get("samples", []):
            try:
                self._samples.append(
                    TensionSample(
                        id=int(entry["id"]),
                        grams=float(entry["grams"]),
                        tension_tag=float(entry["tensionTag"]),
                        created_at=float(entry.get("createdAt", 0.0)),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                LOGGER.warning("Skipping malformed tension sample %r: %s", entry, exc)
        # Keep nextId ahead of any loaded ids.
        for sample in self._samples:
            self._next_id = max(self._next_id, sample.id + 1)

    def _save(self) -> None:
        payload = {
            "fixIntercept": self._fix_intercept,
            "maxDegree": self._max_degree,
            "nextId": self._next_id,
            "samples": [
                {
                    "id": sample.id,
                    "grams": sample.grams,
                    "tensionTag": sample.tension_tag,
                    "createdAt": sample.created_at,
                }
                for sample in self._samples
            ],
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # -- mutations ----------------------------------------------------------
    def add_sample(self, grams: float, tension_tag: float) -> TensionSample:
        sample = TensionSample(
            id=self._next_id,
            grams=float(grams),
            tension_tag=float(tension_tag),
            created_at=time.time(),
        )
        self._next_id += 1
        self._samples.append(sample)
        self._save()
        return sample

    def delete_sample(self, sample_id: int) -> bool:
        before = len(self._samples)
        self._samples = [s for s in self._samples if s.id != sample_id]
        removed = len(self._samples) != before
        if removed:
            self._save()
        return removed

    def clear(self) -> None:
        self._samples = []
        self._save()

    def set_fix_intercept(self, enabled: bool) -> None:
        self._fix_intercept = bool(enabled)
        self._save()

    def set_max_degree(self, max_degree: int) -> None:
        self._max_degree = max(1, min(MAX_DEGREE, int(max_degree)))
        self._save()

    # -- queries ------------------------------------------------------------
    @property
    def fix_intercept(self) -> bool:
        return self._fix_intercept

    @property
    def max_degree(self) -> int:
        return self._max_degree

    @property
    def samples(self) -> list[TensionSample]:
        return list(self._samples)

    def fit(self) -> dict[str, Any] | None:
        return fit_polynomial(
            [s.tension_tag for s in self._samples],
            [s.newtons for s in self._samples],
            self._max_degree,
            self._fix_intercept,
        )

    def state(self, plc: Any = None) -> dict[str, Any]:
        """Assemble the full UI state payload."""
        live = read_live(plc)
        return {
            "samples": [sample.to_dict() for sample in self._samples],
            "fixIntercept": self._fix_intercept,
            "maxDegree": self._max_degree,
            "fit": self.fit(),
            "plc": read_plc_coefficients(plc),
            "live": live,
            "gramsToNewtons": GRAMS_TO_NEWTONS,
            "coefficientKeys": list(COEFFICIENT_KEYS),
        }
