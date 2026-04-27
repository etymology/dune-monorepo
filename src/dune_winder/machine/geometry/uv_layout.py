from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re

from dune_winder.machine.calibration.defaults import get_layer_z_defaults
from dune_winder.machine.geometry.factory import create_layer_geometry
from dune_winder.machine.geometry.layer_functions import LayerFunctions


UV_LAYERS = ("U", "V")
FACE_ORDER = ("head", "bottom", "foot", "top")
_PIN_NAME_RE = re.compile(r"^(P?)([ABF])(\d+)$")

_SIDE_RANGES = {
    "U": {
        "head": (1, 400),
        "bottom": (401, 1200),
        "foot": (1201, 1601),
        "top": (1602, 2401),
    },
    "V": {
        "head": (1, 399),
        "bottom": (400, 1199),
        "foot": (1200, 1599),
        "top": (1600, 2399),
    },
}

_ENDPOINT_PINS = {
    "U": (
        1,
        40,
        41,
        80,
        81,
        120,
        121,
        160,
        161,
        200,
        201,
        240,
        241,
        280,
        281,
        320,
        321,
        360,
        361,
        400,
        401,
        424,
        425,
        449,
        450,
        473,
        474,
        510,
        511,
        547,
        548,
        584,
        585,
        621,
        622,
        658,
        659,
        695,
        696,
        732,
        733,
        769,
        770,
        806,
        807,
        843,
        844,
        880,
        881,
        917,
        918,
        954,
        955,
        991,
        992,
        1028,
        1029,
        1065,
        1066,
        1102,
        1103,
        1139,
        1140,
        1176,
        1177,
        1200,
        1201,
        1240,
        1241,
        1280,
        1281,
        1320,
        1321,
        1360,
        1361,
        1400,
        1401,
        1440,
        1441,
        1480,
        1481,
        1520,
        1521,
        1560,
        1561,
        1601,
        1602,
        1625,
        1626,
        1662,
        1663,
        1699,
        1700,
        1736,
        1737,
        1773,
        1774,
        1810,
        1811,
        1847,
        1848,
        1884,
        1885,
        1921,
        1922,
        1958,
        1959,
        1995,
        1996,
        2032,
        2033,
        2069,
        2070,
        2106,
        2107,
        2143,
        2144,
        2180,
        2181,
        2217,
        2218,
        2254,
        2255,
        2291,
        2292,
        2328,
        2329,
        2352,
        2353,
        2377,
        2378,
        2401,
    ),
    "V": (
        1,
        40,
        41,
        80,
        81,
        120,
        121,
        160,
        161,
        200,
        201,
        240,
        241,
        280,
        281,
        320,
        321,
        360,
        361,
        399,
        400,
        423,
        424,
        448,
        449,
        472,
        473,
        509,
        510,
        546,
        547,
        583,
        584,
        620,
        621,
        657,
        658,
        694,
        695,
        731,
        732,
        768,
        769,
        805,
        806,
        842,
        843,
        879,
        880,
        916,
        917,
        953,
        954,
        990,
        991,
        1027,
        1028,
        1064,
        1065,
        1101,
        1102,
        1138,
        1139,
        1175,
        1176,
        1199,
        1200,
        1239,
        1240,
        1279,
        1280,
        1319,
        1320,
        1359,
        1360,
        1399,
        1400,
        1439,
        1440,
        1479,
        1480,
        1519,
        1520,
        1559,
        1560,
        1599,
        1600,
        1623,
        1624,
        1660,
        1661,
        1697,
        1698,
        1734,
        1735,
        1771,
        1772,
        1808,
        1809,
        1845,
        1846,
        1882,
        1883,
        1919,
        1920,
        1956,
        1957,
        1993,
        1994,
        2030,
        2031,
        2067,
        2068,
        2104,
        2105,
        2141,
        2142,
        2178,
        2179,
        2215,
        2216,
        2252,
        2253,
        2289,
        2290,
        2326,
        2327,
        2350,
        2351,
        2375,
        2376,
        2399,
    ),
}

_LAYOUT_SPECS = {
    "U": {
        "wire_segment_1_pin_a": 450,
        "wire_segment_1_pin_b": 350,
        "wire_segment_formula_min": 1,
        "wire_segment_formula_max": 1151,
        "wire_segment_min": 8,
        "wire_segment_max": 1146,
        "b1_target_xy": (570.0, 2455.0),
        "measurement_dy_sign": {"A": -1, "B": 1},
        "tangent_ranges": (
            (1, 1200, True, False),
            (1201, 2401, False, True),
        ),
    },
    "V": {
        "wire_segment_1_pin_a": 49,
        "wire_segment_1_pin_b": 2350,
        "wire_segment_formula_min": 1,
        "wire_segment_formula_max": 1151,
        "wire_segment_min": 8,
        "wire_segment_max": 1146,
        "b1_target_xy": (635.0, 2350.0),
        "measurement_dy_sign": {"A": 1, "B": -1},
        "tangent_ranges": (
            (1, 399, True, True),
            (400, 1599, False, False),
            (1600, 2399, True, True),
        ),
    },
}


@dataclass(frozen=True)
class Point3D:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class WrapOrientation:
    x_side: str
    y_side: str

    @property
    def as_tuple(self) -> tuple[str, str]:
        return (self.x_side, self.y_side)

    @property
    def x_sign(self) -> int:
        return 1 if self.x_side == "plus" else -1

    @property
    def y_sign(self) -> int:
        return 1 if self.y_side == "plus" else -1


@dataclass(frozen=True)
class UvBoard:
    board_index: int
    face: str
    face_index: int
    start_pin: int
    end_pin: int

    @property
    def pin_count(self) -> int:
        return self.end_pin - self.start_pin + 1


@dataclass(frozen=True)
class UvEndpointInfo:
    pin: int
    board_index: int
    face: str
    face_index: int
    endpoint: str


@dataclass(frozen=True)
class UvBoardPin:
    layer: str
    family: str
    face: str
    board_index: int
    board_number: int
    pin_number_on_board: int
    physical_pin: int
    pin_number: int
    pin_name: str


def _normalize_layer(layer: str) -> str:
    value = str(layer).strip().upper()
    if value not in UV_LAYERS:
        raise ValueError(f"Unsupported U/V layer {layer!r}.")
    return value


def _normalize_family(family: str, *, allow_front_alias: bool = True) -> str:
    value = str(family).strip().upper()
    if allow_front_alias and value == "F":
        return "A"
    if value not in {"A", "B"}:
        raise ValueError(f"Unsupported pin family {family!r}.")
    return value


def _wrap_inclusive(value: int, low: int, high: int) -> int:
    span = int(high) - int(low) + 1
    return int(low) + ((int(value) - int(low)) % span)


def _pairwise(values: tuple[int, ...]) -> list[tuple[int, int]]:
    return [(values[index], values[index + 1]) for index in range(0, len(values), 2)]


def _bootstrap_pins_for_side(side_boards: list[UvBoard]) -> list[int]:
    if not side_boards:
        return []

    first_pin = side_boards[0].start_pin
    last_pin = side_boards[-1].end_pin
    midpoint = (first_pin + last_pin) / 2.0
    candidate_pins = [board.end_pin for board in side_boards]
    middle_pin = min(candidate_pins, key=lambda pin: (abs(pin - midpoint), pin))
    return [first_pin, middle_pin, last_pin]


class UvLayerLayout:
    def __init__(self, layer: str):
        self.layer = _normalize_layer(layer)
        self.geometry = create_layer_geometry(self.layer)
        self.pin_max = int(self.geometry.pins)
        spec = _LAYOUT_SPECS[self.layer]
        self.pitch_dx = float(self.geometry.deltaX)
        self.pitch_dy = float(self.geometry.deltaY)
        self.wire_segment_min = int(spec["wire_segment_min"])
        self.wire_segment_max = int(spec["wire_segment_max"])
        self.wire_segment_formula_min = int(spec["wire_segment_formula_min"])
        self.wire_segment_formula_max = int(spec["wire_segment_formula_max"])
        self.face_order = FACE_ORDER
        self.side_ranges = {
            face: tuple(bounds) for face, bounds in _SIDE_RANGES[self.layer].items()
        }
        self.endpoint_pins = tuple(_ENDPOINT_PINS[self.layer])
        self._wire_segment_1_pin_a = int(spec["wire_segment_1_pin_a"])
        self._wire_segment_1_pin_b = int(spec["wire_segment_1_pin_b"])
        self._b1_target_xy = tuple(spec["b1_target_xy"])
        self._measurement_dy_sign = {
            family: int(sign) for family, sign in spec["measurement_dy_sign"].items()
        }
        self._tangent_ranges = tuple(
            (
                int(start_pin),
                int(end_pin),
                bool(x_plus),
                bool(y_a_plus),
            )
            for start_pin, end_pin, x_plus, y_a_plus in spec["tangent_ranges"]
        )
        self._boards = self._build_boards()
        self._boards_by_face = {
            face: tuple(board for board in self._boards if board.face == face)
            for face in FACE_ORDER
        }
        self._pin_to_board = self._build_pin_to_board()
        self._endpoint_info = self._build_endpoint_info()
        self._bootstrap_pins = tuple(
            pin
            for face in FACE_ORDER
            for pin in _bootstrap_pins_for_side(list(self._boards_by_face[face]))
        )
        self._nominal_positions = self._build_nominal_positions()

    def _build_boards(self) -> tuple[UvBoard, ...]:
        if self.endpoint_pins[-1] != self.pin_max:
            raise ValueError(
                f"Endpoint metadata does not match geometry for layer {self.layer}."
            )

        face_counts = {face: 0 for face in FACE_ORDER}
        boards: list[UvBoard] = []
        for board_index, (start_pin, end_pin) in enumerate(
            _pairwise(self.endpoint_pins), start=1
        ):
            face = self._face_for_physical_pin(start_pin)
            face_counts[face] += 1
            boards.append(
                UvBoard(
                    board_index=board_index,
                    face=face,
                    face_index=face_counts[face],
                    start_pin=int(start_pin),
                    end_pin=int(end_pin),
                )
            )
        return tuple(boards)

    def _build_pin_to_board(self) -> dict[int, UvBoard]:
        result: dict[int, UvBoard] = {}
        for board in self._boards:
            for pin in range(board.start_pin, board.end_pin + 1):
                result[int(pin)] = board
        return result

    def _build_endpoint_info(self) -> dict[int, UvEndpointInfo]:
        result: dict[int, UvEndpointInfo] = {}
        for board in self._boards:
            result[board.start_pin] = UvEndpointInfo(
                pin=board.start_pin,
                board_index=board.board_index,
                face=board.face,
                face_index=board.face_index,
                endpoint="start",
            )
            result[board.end_pin] = UvEndpointInfo(
                pin=board.end_pin,
                board_index=board.board_index,
                face=board.face,
                face_index=board.face_index,
                endpoint="end",
            )
        return result

    def _build_nominal_positions(self) -> dict[str, Point3D]:
        z_front, z_back = get_layer_z_defaults(self.layer, self.geometry)
        origin = self.geometry.apaLocation.add(self.geometry.apaOffset)
        positions: dict[str, Point3D] = {}
        grids = (
            (
                "A",
                self.geometry.gridBack,
                z_front,
                self.geometry.startPinBack,
                self.geometry.directionBack,
            ),
            (
                "B",
                self.geometry.gridFront,
                z_back,
                self.geometry.startPinFront,
                self.geometry.directionFront,
            ),
        )
        for family, grid, depth, start_pin, direction in grids:
            x_value = 0.0
            y_value = 0.0
            pin_number = int(start_pin)
            for (
                count,
                x_increment,
                y_increment,
                x_offset,
                y_offset,
                _orientation,
            ) in grid:
                x_value += x_offset
                y_value += y_offset
                for _ in range(int(count)):
                    positions[f"{family}{pin_number}"] = Point3D(
                        float(round(x_value, 5) + origin.x),
                        float(round(y_value, 5) + origin.y),
                        float(depth),
                    )
                    pin_number += int(direction)
                    if pin_number <= 0:
                        pin_number = self.pin_max
                    elif pin_number > self.pin_max:
                        pin_number = 1
                    x_value += x_increment
                    y_value += y_increment
                x_value -= x_increment
                y_value -= y_increment

        b1 = positions["B1"]
        delta_x = float(self._b1_target_xy[0] - b1.x)
        delta_y = float(self._b1_target_xy[1] - b1.y)
        return {
            pin_name: Point3D(
                float(point.x + delta_x),
                float(point.y + delta_y),
                float(point.z),
            )
            for pin_name, point in positions.items()
        }

    def parse_pin_name(self, pin_name: str) -> tuple[str, str, int]:
        value = str(pin_name).strip().upper()
        match = _PIN_NAME_RE.match(value)
        if match is None:
            raise ValueError(f"Unsupported pin name {pin_name!r}.")
        prefix, family, pin_number_text = match.groups()
        pin_number = int(pin_number_text)
        if pin_number < 1 or pin_number > self.pin_max:
            raise ValueError(
                f"Pin number {pin_number} is out of range for layer {self.layer}."
            )
        return (prefix, _normalize_family(family), pin_number)

    def format_pin_name(
        self,
        family: str,
        pin_number: int,
        *,
        prefix: str = "",
    ) -> str:
        normalized_family = _normalize_family(family)
        normalized_prefix = str(prefix).strip().upper()
        if normalized_prefix not in {"", "P"}:
            raise ValueError(f"Unsupported pin prefix {prefix!r}.")
        pin_value = int(pin_number)
        if pin_value < 1 or pin_value > self.pin_max:
            raise ValueError(
                f"Pin number {pin_value} is out of range for layer {self.layer}."
            )
        return f"{normalized_prefix}{normalized_family}{pin_value}"

    def translate_pin(self, pin_name: str, target_family: str = "A") -> str:
        prefix, family, pin_number = self.parse_pin_name(pin_name)
        normalized_target = _normalize_family(target_family)
        translated_pin = pin_number
        if family != normalized_target:
            translated_pin = int(
                LayerFunctions.translateFrontBack(self.geometry, pin_number)
            )
        return self.format_pin_name(normalized_target, translated_pin, prefix=prefix)

    def physical_pin_number(self, pin: int | str) -> int:
        if isinstance(pin, int):
            pin_number = int(pin)
            if pin_number < 1 or pin_number > self.pin_max:
                raise ValueError(
                    f"Pin number {pin_number} is out of range for layer {self.layer}."
                )
            return pin_number

        _prefix, family, pin_number = self.parse_pin_name(pin)
        if family == "B":
            return pin_number
        translated = self.translate_pin(self.format_pin_name(family, pin_number), "B")
        return int(translated[1:])

    def _face_for_physical_pin(self, pin_number: int) -> str:
        pin_value = int(pin_number)
        for face in FACE_ORDER:
            start_pin, end_pin = self.side_ranges[face]
            if start_pin <= pin_value <= end_pin:
                return face
        raise ValueError(
            f"Pin number {pin_value} is out of range for layer {self.layer}."
        )

    def face_for_pin(self, pin: int | str) -> str:
        physical_pin = self.physical_pin_number(pin)
        if hasattr(self, "_pin_to_board") and physical_pin in self._pin_to_board:
            return self._pin_to_board[physical_pin].face
        return self._face_for_physical_pin(physical_pin)

    def board_lookup(
        self,
        family: str,
        face: str,
        board_number: int,
        pin_number_on_board: int,
    ) -> UvBoardPin:
        normalized_family = _normalize_family(family)
        normalized_face = str(face).strip().lower()
        if normalized_face not in FACE_ORDER:
            raise ValueError("Board face must be one of head, bottom, foot, or top.")
        normalized_board_number = int(board_number)
        if normalized_board_number == 0:
            raise ValueError("board_number must not be 0.")
        normalized_pin_number = int(pin_number_on_board)
        if normalized_pin_number == 0:
            raise ValueError("pin_number must not be 0.")

        face_boards = self._boards_by_face[normalized_face]
        if normalized_board_number > len(face_boards) or normalized_board_number < -len(
            face_boards
        ):
            raise ValueError(
                f"board_number {normalized_board_number} is outside the {normalized_face} "
                f"face range for layer {self.layer}."
            )

        if normalized_board_number > 0:
            board = face_boards[normalized_board_number - 1]
            resolved_board_number = normalized_board_number
        else:
            board = face_boards[normalized_board_number]
            resolved_board_number = len(face_boards) + normalized_board_number + 1
        if normalized_pin_number > board.pin_count or normalized_pin_number < -board.pin_count:
            raise ValueError(
                f"pin_number {normalized_pin_number} is outside board {normalized_board_number} "
                f"on the {normalized_face} face for layer {self.layer}."
            )

        if normalized_pin_number > 0:
            physical_pin = board.start_pin + normalized_pin_number - 1
            resolved_pin_number = normalized_pin_number
        else:
            physical_pin = board.end_pin + normalized_pin_number + 1
            resolved_pin_number = board.pin_count + normalized_pin_number + 1
        pin_name = self.translate_pin(
            self.format_pin_name("B", physical_pin),
            target_family=normalized_family,
        )
        return UvBoardPin(
            layer=self.layer,
            family=normalized_family,
            face=board.face,
            board_index=board.board_index,
            board_number=resolved_board_number,
            pin_number_on_board=resolved_pin_number,
            physical_pin=physical_pin,
            pin_number=int(pin_name[1:]),
            pin_name=pin_name,
        )

    def wire_segment_endpoints(
        self, segment_number: int, family: str = "B"
    ) -> tuple[str, str]:
        normalized_family = _normalize_family(family)
        number = int(segment_number)
        if (
            number < self.wire_segment_formula_min
            or number > self.wire_segment_formula_max
        ):
            raise ValueError(
                f"Wire segment number {number} is outside the supported range "
                f"{self.wire_segment_formula_min}-{self.wire_segment_formula_max} for layer {self.layer}."
            )
        pin_a = _wrap_inclusive(
            self._wire_segment_1_pin_a + (number - 1), 1, self.pin_max
        )
        pin_b = _wrap_inclusive(
            self._wire_segment_1_pin_b - (number - 1), 1, self.pin_max
        )
        endpoints = (
            self.format_pin_name("B", pin_a),
            self.format_pin_name("B", pin_b),
        )
        if normalized_family == "B":
            return endpoints
        return tuple(
            self.translate_pin(pin_name, target_family=normalized_family)
            for pin_name in endpoints
        )

    def wrap_orientation(self, pin_name: str) -> WrapOrientation:
        _prefix, family, pin_number = self.parse_pin_name(pin_name)
        for start_pin, end_pin, x_plus, y_a_plus in self._tangent_ranges:
            if start_pin <= pin_number <= end_pin:
                return WrapOrientation(
                    x_side="plus" if x_plus else "minus",
                    y_side="plus" if ((family == "A") == y_a_plus) else "minus",
                )
        raise ValueError(
            f"Pin number {pin_number} is out of range for layer {self.layer}."
        )

    def tangent_sides(self, pin_name: str) -> tuple[str, str]:
        return self.wrap_orientation(pin_name).as_tuple

    def measurement_pitch(self, family: str) -> tuple[float, float]:
        normalized_family = _normalize_family(family)
        return (
            float(self.pitch_dx),
            float(self.pitch_dy * self._measurement_dy_sign[normalized_family]),
        )

    def nominal_positions(self) -> dict[str, Point3D]:
        return dict(self._nominal_positions)

    @property
    def boards(self) -> tuple[UvBoard, ...]:
        return self._boards

    @property
    def pin_to_board(self) -> dict[int, UvBoard]:
        return dict(self._pin_to_board)

    @property
    def endpoint_info(self) -> dict[int, UvEndpointInfo]:
        return dict(self._endpoint_info)

    @property
    def bootstrap_pins(self) -> tuple[int, ...]:
        return self._bootstrap_pins

    def wrap_pin(self, value: int) -> int:
        return _wrap_inclusive(int(value), 1, self.pin_max)

    @property
    def named_pins(self) -> dict[str, int]:
        return {
            "bottom_foot_end": self.side_ranges["bottom"][1],
            "bottom_head_end": self.side_ranges["bottom"][0],
            "top_foot_end": self.side_ranges["top"][0],
            "top_head_end": self.side_ranges["top"][1],
            "foot_bottom_end": self.side_ranges["foot"][0],
            "foot_top_end": self.side_ranges["foot"][1],
            "head_bottom_end": self.side_ranges["head"][1],
            "head_top_end": self.side_ranges["head"][0],
        }

    def b_to_a_pin_number(self, b_pin: int) -> int:
        head_end = self.side_ranges["head"][1]
        return 1 + ((head_end - int(b_pin)) % self.pin_max)

    def legacy_metadata(self) -> dict[str, object]:
        boards = [
            {
                "boardIndex": board.board_index,
                "side": board.face,
                "sideIndex": board.face_index,
                "startPin": board.start_pin,
                "endPin": board.end_pin,
            }
            for board in self._boards
        ]
        endpoint_info = {
            pin: {
                "pin": info.pin,
                "boardIndex": info.board_index,
                "side": info.face,
                "sideIndex": info.face_index,
                "endpoint": info.endpoint,
            }
            for pin, info in self._endpoint_info.items()
        }
        board_lookup = {
            pin: {
                "boardIndex": board.board_index,
                "side": board.face,
                "sideIndex": board.face_index,
                "startPin": board.start_pin,
                "endPin": board.end_pin,
            }
            for pin, board in self._pin_to_board.items()
        }
        return {
            "layer": self.layer,
            "pinMax": self.pin_max,
            "geometry": self.geometry,
            "boards": boards,
            "endpointInfo": endpoint_info,
            "endpointPins": list(self.endpoint_pins),
            "pinToBoard": board_lookup,
            "bootstrapPins": list(self._bootstrap_pins),
            "bootstrapSet": set(self._bootstrap_pins),
            "sideRanges": {
                face: tuple(bounds) for face, bounds in self.side_ranges.items()
            },
            "pitchDx": self.pitch_dx,
            "pitchDy": self.pitch_dy,
            "wireSegmentMin": self.wire_segment_min,
            "wireSegmentMax": self.wire_segment_max,
        }


@lru_cache(maxsize=2)
def get_uv_layout(layer: str) -> UvLayerLayout:
    return UvLayerLayout(layer)


__all__ = [
    "FACE_ORDER",
    "Point3D",
    "UV_LAYERS",
    "UvBoard",
    "UvBoardPin",
    "UvEndpointInfo",
    "UvLayerLayout",
    "WrapOrientation",
    "get_uv_layout",
]
