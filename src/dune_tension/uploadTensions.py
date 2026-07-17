"""Upload measured wire tensions to the DUNE database via the M2M client.

The summary CSV produced by the tensiometer pipeline is read for one
APA/layer and pushed into an existing "single layer tension measurements"
action record. :func:`upload_tensions` performs the validation the GUI
relies on and raises a specific :class:`UploadError` subclass for each
failure mode surfaced to the operator:

* :class:`DataNotFoundError`        - no summary CSV, or no such action record
* :class:`IncompleteMeasurementsError` - a side is missing expected wires
* :class:`ActionNotEditableError`   - the server refused the edit
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from dune_tension.m2m.common import ConnectToAPI, GetAction, M2MError
from dune_tension.paths import data_path
from dune_tension.summaries import get_expected_range

REPLACED_WIRE_SEGS = "All wire segments are within specified tolerance."
UPLOAD_COMMENT = "Single layer tension measurements uploaded via M2M GUI."


class UploadError(Exception):
    """Base class for tension-upload failures surfaced to the operator."""


class DataNotFoundError(UploadError):
    """The tension summary CSV or the DB action record could not be found."""


class ActionNotEditableError(UploadError):
    """The action record exists but the server refused the edit."""

    def __init__(self, action_id: str, status: int, reason: str) -> None:
        self.action_id = action_id
        self.status = status
        self.reason = reason
        super().__init__(
            f"Action {action_id} is not editable "
            f"(server returned {status} {reason})."
        )


class IncompleteMeasurementsError(UploadError):
    """One or both sides are missing measurements for expected wires."""

    def __init__(
        self, apa_name: str, layer: str, missing: Dict[str, List[int]]
    ) -> None:
        self.apa_name = apa_name
        self.layer = layer
        self.missing = missing
        parts = [
            f"side {side} missing {len(missing[side])} wire(s)"
            for side in ("A", "B")
            if missing.get(side)
        ]
        detail = "; ".join(parts) if parts else "no expected wires for layer"
        super().__init__(
            f"{apa_name} layer {layer}: not all wires measured ({detail})."
        )


@dataclass
class UploadResult:
    """Summary of a successful upload, for display in the GUI/CLI."""

    apa_name: str
    layer: str
    action_id: str
    wires_side_a: int
    wires_side_b: int


def _summary_csv_path(apa_name: str, layer: str) -> Path:
    return data_path("tension_summaries", f"tension_summary_{apa_name}_{layer}.csv")


def _read_summary_df(apa_name: str, layer: str) -> pd.DataFrame:
    csv_path = _summary_csv_path(apa_name, layer)
    if not csv_path.exists():
        raise DataNotFoundError(
            f"No tension summary found for APA {apa_name} layer {layer} "
            f"(expected {csv_path})."
        )
    return pd.read_csv(csv_path).set_index("wire_number")


def _b_side_range(layer: str, wire_range: List[int]) -> List[int]:
    # X and G wires are read from the opposite end on side B.
    if layer.upper() in ("X", "G"):
        return list(reversed(wire_range))
    return wire_range


def _tension_lists(df: pd.DataFrame, layer: str) -> Tuple[List[float], List[float]]:
    wire_range = list(get_expected_range(layer))
    nan = float("nan")
    side_a = [float(df["A"].get(wire, nan)) for wire in wire_range]
    side_b = [
        float(df["B"].get(wire, nan)) for wire in _b_side_range(layer, wire_range)
    ]
    return side_a, side_b


def _missing_wires(df: pd.DataFrame, layer: str) -> Dict[str, List[int]]:
    """Return, per side, the expected wire numbers with no finite measurement."""
    wire_range = list(get_expected_range(layer))
    expected = set(wire_range)
    nan = float("nan")
    missing: Dict[str, List[int]] = {}
    for side in ("A", "B"):
        if side in df.columns:
            column = df[side]
            measured = {
                int(wire)
                for wire in wire_range
                if pd.notna(column.get(wire, nan))
            }
        else:
            measured = set()
        missing[side] = sorted(expected - measured)
    return missing


def load_tension_summary(apa_name: str, layer: str) -> Tuple[List[float], List[float]]:
    """Return per-wire tensions for sides A and B, NaN where unmeasured."""
    return _tension_lists(_read_summary_df(apa_name, layer), layer)


def upload_tensions(apa_name: str, layer: str, action_id: str) -> UploadResult:
    """Validate the summary and push tensions into ``action_id``.

    Raises:
        DataNotFoundError: summary CSV or action record is missing.
        IncompleteMeasurementsError: a side is missing expected wires.
        ActionNotEditableError: the server refused the edit.
    """
    df = _read_summary_df(apa_name, layer)  # DataNotFoundError if absent

    missing = _missing_wires(df, layer)
    if missing["A"] or missing["B"]:
        raise IncompleteMeasurementsError(apa_name, layer, missing)

    tensions_side_a, tensions_side_b = _tension_lists(df, layer)

    connection, headers = ConnectToAPI()
    try:
        try:
            action = GetAction(action_id, connection, headers)
        except (M2MError, ValueError) as exc:
            # M2MError: API returned null for an unknown ID.
            # ValueError: the error response was not valid JSON.
            raise DataNotFoundError(
                f"No action record found with ID {action_id}."
            ) from exc
        if not action:
            raise DataNotFoundError(f"No action record found with ID {action_id}.")

        action.setdefault("data", {})
        action["data"]["measuredTensions_sideA"] = tensions_side_a
        action["data"]["measuredTensions_sideB"] = tensions_side_b
        action["data"]["replacedWireSegs"] = REPLACED_WIRE_SEGS
        action["data"]["comments"] = UPLOAD_COMMENT

        connection.request(
            "POST", "/api/action", body=json.dumps(action), headers=headers
        )
        response = connection.getresponse()
        response.read()  # drain the body so the connection closes cleanly
        if not 200 <= response.status < 300:
            raise ActionNotEditableError(action_id, response.status, response.reason)
    finally:
        connection.close()

    return UploadResult(
        apa_name=apa_name,
        layer=layer,
        action_id=action_id,
        wires_side_a=len(tensions_side_a),
        wires_side_b=len(tensions_side_b),
    )


def main() -> None:
    result = upload_tensions("APAUK007", "G", r"69fa77aefe54e3ab260901a6")
    print(
        f"Uploaded {result.wires_side_a}/{result.wires_side_b} tensions "
        f"to action {result.action_id}."
    )


if __name__ == "__main__":
    main()
