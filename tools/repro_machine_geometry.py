"""Standalone repro for the Machine-XY solver residual problem.

Loads the *real* machine + V-layer calibration and the *real* saved
measurements, then for each failing measurement prints what the solver
currently compares against versus what the documented procedure says it
should compare against.

Procedure (per the operator):
  * Jog the wire to where it is tangent to the pin; the recorded per-line
    offset is therefore an *implied pin-position shift*.
  * To test a new camera-wire offset we re-run ~anchorToTarget (bare) with
    that offset and ask whether the implied pin position lands closer to the
    one implied by (line + existing offset + old camera offset).
  * So the residual that should be minimised is a difference of *implied pin
    positions*, not (observed head) - (projected wire contact).

The solver today computes ``offset = observed - projection["projectedX"]``
where ``projectedX`` is the wire-contact point from ``getActualLocation`` --
a head-vs-wire comparison with no anchor->target lever-arm scaling.  This
script makes the gap measurable.

Run:  uv run python repro_machine_geometry.py
"""

from __future__ import annotations

import json
import math
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from dune_winder.core.machine_geometry_calibration import (  # noqa: E402
    _implied_pin_offset,
    _project_machine_xy_measurement_payload,
    _translate_projection_payload,
)

MACHINE_PATH = os.path.join(REPO_ROOT, "config", "machineCalibration.json")
LAYER_PATH = os.path.join(REPO_ROOT, "config", "APA", "V_Calibration.json")
CACHE_PATH = os.path.join(
    REPO_ROOT, "dune_winder", "cache", "machineGeometryCalibration.json"
)


def _load_machine_config():
    with open(MACHINE_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _strip_offset(gcode_line: str) -> str:
    """Return the gcode line with the rendered ``offset=(...)`` term removed."""
    return re.sub(r",\s*offset=\([^)]*\)", "", gcode_line)


def _lever_arm_ratio(payload: dict) -> float:
    """anchor->target / anchor->head distance, the head-delta -> pin-delta scale.

    Mirrors ``_head_delta_to_pin_delta`` for the same-side case using the
    tangent points and head target carried in the projection payload.
    """
    ax, ay = payload["anchorTangentX"], payload["anchorTangentY"]
    tx, ty = payload["targetTangentX"], payload["targetTangentY"]
    hx, hy = payload["projectedHeadX"], payload["projectedHeadY"]
    d_at = math.hypot(tx - ax, ty - ay)
    d_ah = math.hypot(hx - ax, hy - ay)
    if d_at < 1e-9 or d_ah < 1e-9:
        return 1.0
    return d_at / d_ah


def main() -> None:
    machine_config = _load_machine_config()
    live_camera = (
        float(machine_config["cameraWireOffsetX"]),
        float(machine_config["cameraWireOffsetY"]),
    )
    roller_y_cals = tuple(
        float(v) for v in machine_config["rollerArmCalibration"]["fitted_y_cals"][:4]
    )

    with open(CACHE_PATH, "r", encoding="utf-8") as handle:
        cache = json.load(handle)

    measurements = [
        measurement
        for measurement in cache["measurements"]
        if str(measurement.get("layer")).upper() == "V"
        and measurement.get("gcodeLine")
        and measurement.get("actualWireX") is not None
    ]

    candidate_offsets = {
        "raw(0,0)": (0.0, 0.0),
        "live": live_camera,
        "live+10x": (live_camera[0] + 10.0, live_camera[1]),
    }

    print(f"machine     : {MACHINE_PATH}")
    print(f"layer       : {LAYER_PATH}")
    print(f"live camera : {live_camera}")
    print(f"roller_y    : {roller_y_cals}")
    print("=" * 96)

    for measurement in measurements:
        line_key = measurement.get("lineKey")
        site = measurement.get("siteLabel")
        observed = (
            float(measurement["actualWireX"]),
            float(measurement["actualWireY"]),
        )
        commanded = (
            measurement.get("commandedX"),
            measurement.get("commandedY"),
        )
        same_side = measurement.get("sameSide")
        gcode_line = measurement["gcodeLine"]

        print(f"\n{line_key}  {site}   sameSide={same_side}")
        print(f"  gcode      : {gcode_line}")
        print(f"  observed   : ({observed[0]:.3f}, {observed[1]:.3f})  [head/motor XY]")
        if commanded[0] is not None:
            print(
                f"  commanded  : ({float(commanded[0]):.3f}, "
                f"{float(commanded[1]):.3f})  [live recipe head target]"
            )

        # Project the line AS STORED (rendered offset baked in) in raw-camera
        # space, then translate to each candidate camera offset.
        try:
            with_offset_raw = _project_machine_xy_measurement_payload(
                measurement,
                layer_path=LAYER_PATH,
                machine_path=MACHINE_PATH,
                roller_y_cals=roller_y_cals,
                cameraWireOffset=(0.0, 0.0),
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  !! projection failed: {exc!r}")
            continue

        # Project the BARE line (no per-line offset) for the implied-pin metric.
        bare_measurement = dict(measurement)
        bare_measurement["gcodeLine"] = _strip_offset(gcode_line)
        try:
            bare_raw = _project_machine_xy_measurement_payload(
                bare_measurement,
                layer_path=LAYER_PATH,
                machine_path=MACHINE_PATH,
                roller_y_cals=roller_y_cals,
                cameraWireOffset=(0.0, 0.0),
            )
        except Exception as exc:  # noqa: BLE001
            bare_raw = None
            print(f"  !! bare projection failed: {exc!r}")

        for label, camera in candidate_offsets.items():
            proj = _translate_projection_payload(with_offset_raw, camera)
            head = (proj["projectedHeadX"], proj["projectedHeadY"])
            wire = (proj["projectedX"], proj["projectedY"])
            old_resid = (observed[0] - wire[0], observed[1] - wire[1])
            # The fixed solver residual: implied pin-position shift.
            new_resid = _implied_pin_offset(observed[0], observed[1], proj)
            print(
                f"  [{label:9s}] head=({head[0]:9.3f},{head[1]:9.3f}) "
                f"wire=({wire[0]:9.3f},{wire[1]:9.3f})"
            )
            print(
                f"              OLD resid(obs-wire)=({old_resid[0]:8.3f},"
                f"{old_resid[1]:8.3f})   NEW implied-pin resid=({new_resid[0]:8.3f},"
                f"{new_resid[1]:8.3f})"
            )

        # Implied-pin-position metric (the documented procedure):
        #   A = implied pin from BARE line + candidate camera offset
        #   B = implied pin from line+offset + OLD (live) camera offset
        # Approximate "implied pin" by scaling the head residual by the
        # anchor->target lever-arm ratio, matching _head_delta_to_pin_delta.
        if bare_raw is not None:
            b_proj = _translate_projection_payload(with_offset_raw, live_camera)
            ratio = _lever_arm_ratio(with_offset_raw)
            print(f"  lever-arm ratio (d_at/d_ah) = {ratio:.4f}")
            for label, camera in candidate_offsets.items():
                a_proj = _translate_projection_payload(bare_raw, camera)
                # head-space gap between bare(C) and with-offset(live)
                gap_head = (
                    a_proj["projectedHeadX"] - b_proj["projectedHeadX"],
                    a_proj["projectedHeadY"] - b_proj["projectedHeadY"],
                )
                implied_pin_shift = (gap_head[0] * ratio, gap_head[1] * ratio)
                print(
                    f"  [{label:9s}] implied-pin shift needed = "
                    f"({implied_pin_shift[0]:8.3f}, {implied_pin_shift[1]:8.3f})"
                )

    print("\n" + "=" * 96)
    print(
        "Read: SOLVER resid(obs-wire) is what fails the bound today.\n"
        "Compare it to resid(obs-head) and the implied-pin shift at [live]."
    )


if __name__ == "__main__":
    main()
