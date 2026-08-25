# functions related to the geometry of the APA
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from dune_tension.config import GEOMETRY_CONFIG

G_LENGTH: float = GEOMETRY_CONFIG.g_length_m
X_LENGTH: float = GEOMETRY_CONFIG.x_length_m

comb_positions: list[int] = list(GEOMETRY_CONFIG.comb_positions)
COMB_SPACING: float = GEOMETRY_CONFIG.comb_spacing


def zone_lookup(x: float) -> int:
    """Return zone index in ``[1, 5]`` for coordinate ``x``.

    Zones are the segments between consecutive comb boundaries in
    :data:`comb_positions`.  Coordinates outside the comb span are clamped
    to the nearest comb boundary.
    """

    boundaries = comb_positions
    clamped_x = min(max(float(x), boundaries[0]), boundaries[-1])

    for idx in range(1, len(boundaries) - 1):
        if clamped_x < boundaries[idx]:
            return idx
    return len(boundaries) - 1


@lru_cache(maxsize=2)
def _load_wire_length_lut(layer: str):
    import pandas as pd

    from dune_tension.paths import package_path

    file_path = package_path("wire_lengths", f"{layer}_LUT.csv")
    try:
        return pd.read_csv(file_path, index_col=0)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"File {file_path} not found") from exc


def length_lookup(
    layer: str, wire_number: int, zone: int, taped: bool = False
) -> float:
    if layer not in GEOMETRY_CONFIG.valid_layers:
        raise ValueError("Invalid layer. Must be 'U', 'V', 'X', or 'G'")
    if layer == "G":
        return G_LENGTH
    if layer == "X":
        return X_LENGTH

    spreadsheet = _load_wire_length_lut(layer)

    if (
        wire_number < GEOMETRY_CONFIG.wire_number_min
        or wire_number > GEOMETRY_CONFIG.wire_number_max
    ):
        raise ValueError(
            "Wire number must be between 1 and 1151 (geometry data available for all wires, but only 8-1146 are collected/uploaded for U/V layers)"
        )
    if zone < 1 or zone > GEOMETRY_CONFIG.zone_count:
        raise ValueError("Zone must be between 1 and 5")

    try:
        raw_value = spreadsheet.at[wire_number, str(zone)]
        if pd.isna(raw_value) or raw_value == "":
            raise ValueError(
                f"no value found for wire {wire_number} in zone {zone} for layer {layer}"
            )
        value = float(raw_value)
        if taped and zone == 1:
            return (value - GEOMETRY_CONFIG.taped_length_offset_mm) / 1000
        return value / 1000
    except KeyError:
        raise ValueError(
            f"no value found for wire {wire_number} in zone {zone} for layer {layer}"
        )


def is_wire_in_zone(layer: str, wire_number: int, zone: int) -> bool:
    """Return True if the given wire passes through the given zone."""
    try:
        length_lookup(layer, wire_number, zone)
        return True
    except (ValueError, KeyError, FileNotFoundError):
        return False
