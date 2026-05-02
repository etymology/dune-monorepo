//! Pin identity and derived geometry properties for U/V layers.
//!
//! Spec source of truth: `specs/layer-geometry.allium`
//! (see also `specs/uv-wrap-geometry.allium` for the wrap-side parity rule
//! mirrored by [`tangent_sides`]).

use std::fmt;
use std::str::FromStr;

use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum Layer {
    U,
    V,
}

impl Layer {
    pub const fn pin_count(self) -> u16 {
        match self {
            Layer::U => 2401,
            Layer::V => 2399,
        }
    }

    /// Per-layer board width along Z, in millimetres. The two pin-bearing
    /// faces (A and B) sit one half-board-width to either side of the
    /// spine along Z. Mirrors `config.{u,v,x,g}_board_width_z_mm` in
    /// `specs/layer-geometry.allium`. X and G are returned for
    /// completeness even though `Layer` is currently `U | V` — the helper
    /// is `match`-exhaustive so adding X/G layer variants later will
    /// require a code update here.
    pub const fn board_width_z_mm(self) -> f64 {
        match self {
            Layer::U => 130.0,
            Layer::V => 120.0,
        }
    }

    /// Half the layer's board width along Z. The displacement from the
    /// spine to either pin face is `± half_board_width_z_mm` along Z
    /// (A is `+`, B is `-`).
    pub const fn half_board_width_z_mm(self) -> f64 {
        self.board_width_z_mm() / 2.0
    }

    pub const fn letter(self) -> char {
        match self {
            Layer::U => 'U',
            Layer::V => 'V',
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum Side {
    A,
    B,
}

impl Side {
    pub const fn letter(self) -> char {
        match self {
            Side::A => 'A',
            Side::B => 'B',
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Face {
    Head,
    Bottom,
    Foot,
    Top,
}

/// Inclusive `(first, last)` pin-number ranges per layer face.
/// Mirrors `_FACE_RANGES` in the source plan and the `u_head` / `u_bottom` /
/// `u_foot` / `u_top` config in `layer-geometry.allium`.
pub const FACE_RANGES_U: [(Face, u16, u16); 4] = [
    (Face::Head, 1, 400),
    (Face::Bottom, 401, 1200),
    (Face::Foot, 1201, 1601),
    (Face::Top, 1602, 2401),
];

pub const FACE_RANGES_V: [(Face, u16, u16); 4] = [
    (Face::Head, 1, 399),
    (Face::Bottom, 400, 1199),
    (Face::Foot, 1200, 1599),
    (Face::Top, 1600, 2399),
];

pub const fn face_ranges(layer: Layer) -> &'static [(Face, u16, u16); 4] {
    match layer {
        Layer::U => &FACE_RANGES_U,
        Layer::V => &FACE_RANGES_V,
    }
}

/// Wire-endpoint pin numbers per layer (side-independent).
pub const ENDPOINT_PINS_U: &[u16] = &[
    1, 40, 41, 80, 81, 120, 121, 160, 161, 200, 201, 240, 241, 280, 281, 320, 321, 360, 361, 400,
    401, 424, 425, 449, 450, 473, 474, 510, 511, 547, 548, 584, 585, 621, 622, 658, 659, 695, 696,
    732, 733, 769, 770, 806, 807, 843, 844, 880, 881, 917, 918, 954, 955, 991, 992, 1028, 1029,
    1065, 1066, 1102, 1103, 1139, 1140, 1176, 1177, 1200, 1201, 1240, 1241, 1280, 1281, 1320, 1321,
    1360, 1361, 1400, 1401, 1440, 1441, 1480, 1481, 1520, 1521, 1560, 1561, 1601, 1602, 1625, 1626,
    1662, 1663, 1699, 1700, 1736, 1737, 1773, 1774, 1810, 1811, 1847, 1848, 1884, 1885, 1921, 1922,
    1958, 1959, 1995, 1996, 2032, 2033, 2069, 2070, 2106, 2107, 2143, 2144, 2180, 2181, 2217, 2218,
    2254, 2255, 2291, 2292, 2328, 2329, 2352, 2353, 2377, 2378, 2401,
];

pub const ENDPOINT_PINS_V: &[u16] = &[
    1, 40, 41, 80, 81, 120, 121, 160, 161, 200, 201, 240, 241, 280, 281, 320, 321, 360, 361, 399,
    400, 423, 424, 448, 449, 472, 473, 509, 510, 546, 547, 583, 584, 620, 621, 657, 658, 694, 695,
    731, 732, 768, 769, 805, 806, 842, 843, 879, 880, 916, 917, 953, 954, 990, 991, 1027, 1028,
    1064, 1065, 1101, 1102, 1138, 1139, 1175, 1176, 1199, 1200, 1239, 1240, 1279, 1280, 1319, 1320,
    1359, 1360, 1399, 1400, 1439, 1440, 1479, 1480, 1519, 1520, 1559, 1560, 1599, 1600, 1623, 1624,
    1660, 1661, 1697, 1698, 1734, 1735, 1771, 1772, 1808, 1809, 1845, 1846, 1882, 1883, 1919, 1920,
    1956, 1957, 1993, 1994, 2030, 2031, 2067, 2068, 2104, 2105, 2141, 2142, 2178, 2179, 2215, 2216,
    2252, 2253, 2289, 2290, 2326, 2327, 2350, 2351, 2375, 2376, 2399,
];

pub const fn endpoint_pins(layer: Layer) -> &'static [u16] {
    match layer {
        Layer::U => ENDPOINT_PINS_U,
        Layer::V => ENDPOINT_PINS_V,
    }
}

/// Wrap-side tangent-normal sign components (x, y) for a pin.
///
/// Mirrors the `tangent_sides` reference in the plan and the parity rule in
/// `specs/layer-geometry.allium :: ClassifyPinWrapSide`. The returned values
/// are in `{-1, 1}`.
pub const fn tangent_sides(layer: Layer, side: Side, n: u16) -> (i8, i8) {
    let x = match layer {
        Layer::U => {
            if n <= 1200 {
                1
            } else {
                -1
            }
        }
        Layer::V => {
            if n <= 399 || n >= 1600 {
                1
            } else {
                -1
            }
        }
    };

    let y_factor = match (layer, side) {
        (Layer::U, Side::B) | (Layer::V, Side::A) => 1,
        _ => -1,
    };

    (x, y_factor * x)
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum PinError {
    #[error("pin number {number} out of range for layer {layer:?} (1..={max})")]
    NumberOutOfRange {
        layer: Layer,
        number: u16,
        max: u16,
    },
    #[error("could not parse pin name {0:?}: expected {{layer}}{{side}}{{number}} like 'UA1'")]
    ParseFailed(String),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub struct Pin {
    pub layer: Layer,
    pub side: Side,
    pub number: u16,
}

impl Pin {
    pub fn new(layer: Layer, side: Side, number: u16) -> Result<Self, PinError> {
        let max = layer.pin_count();
        if number < 1 || number > max {
            return Err(PinError::NumberOutOfRange {
                layer,
                number,
                max,
            });
        }
        Ok(Pin {
            layer,
            side,
            number,
        })
    }

    pub fn face(self) -> Face {
        for (face, first, last) in face_ranges(self.layer).iter().copied() {
            if self.number >= first && self.number <= last {
                return face;
            }
        }
        unreachable!(
            "pin {self:?} validated by Pin::new must fall in one of the layer's face ranges"
        )
    }

    pub fn tangent_normal_sign(self) -> (i8, i8) {
        tangent_sides(self.layer, self.side, self.number)
    }

    pub fn is_endpoint(self) -> bool {
        endpoint_pins(self.layer).binary_search(&self.number).is_ok()
    }

    pub fn board_width_z_mm(self) -> f64 {
        self.layer.board_width_z_mm()
    }

    pub fn half_board_width_z_mm(self) -> f64 {
        self.layer.half_board_width_z_mm()
    }

    /// Sign of the Z displacement from spine to this pin's face: `+1`
    /// for the A side, `-1` for the B side. Mirrors the
    /// `DerivePinPositionFromSpine` rule in
    /// `specs/spine-calibration.allium`.
    pub const fn spine_to_face_sign(self) -> f64 {
        match self.side {
            Side::A => 1.0,
            Side::B => -1.0,
        }
    }
}

impl fmt::Display for Pin {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}{}{}", self.layer.letter(), self.side.letter(), self.number)
    }
}

impl FromStr for Pin {
    type Err = PinError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        let bytes = s.as_bytes();
        if bytes.len() < 3 {
            return Err(PinError::ParseFailed(s.to_string()));
        }
        let layer = match bytes[0] {
            b'U' => Layer::U,
            b'V' => Layer::V,
            _ => return Err(PinError::ParseFailed(s.to_string())),
        };
        let side = match bytes[1] {
            b'A' => Side::A,
            b'B' => Side::B,
            _ => return Err(PinError::ParseFailed(s.to_string())),
        };
        let number: u16 = s[2..]
            .parse()
            .map_err(|_| PinError::ParseFailed(s.to_string()))?;
        Pin::new(layer, side, number)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pin_count_matches_spec() {
        assert_eq!(Layer::U.pin_count(), 2401);
        assert_eq!(Layer::V.pin_count(), 2399);
    }

    #[test]
    fn board_widths() {
        assert_eq!(Layer::U.board_width_z_mm(), 130.0);
        assert_eq!(Layer::V.board_width_z_mm(), 120.0);
        assert_eq!(Layer::U.half_board_width_z_mm(), 65.0);
        assert_eq!(Layer::V.half_board_width_z_mm(), 60.0);
    }

    #[test]
    fn spine_to_face_sign_is_positive_for_a_negative_for_b() {
        assert_eq!(Pin::new(Layer::U, Side::A, 1).unwrap().spine_to_face_sign(), 1.0);
        assert_eq!(Pin::new(Layer::U, Side::B, 1).unwrap().spine_to_face_sign(), -1.0);
        assert_eq!(Pin::new(Layer::V, Side::A, 1).unwrap().spine_to_face_sign(), 1.0);
        assert_eq!(Pin::new(Layer::V, Side::B, 1).unwrap().spine_to_face_sign(), -1.0);
    }

    #[test]
    fn pin_string_roundtrip() {
        let cases = [
            Pin::new(Layer::U, Side::A, 1).unwrap(),
            Pin::new(Layer::U, Side::A, 2401).unwrap(),
            Pin::new(Layer::V, Side::B, 1199).unwrap(),
            Pin::new(Layer::V, Side::A, 2399).unwrap(),
        ];
        for p in cases {
            assert_eq!(p, p.to_string().parse().unwrap());
        }
    }

    #[test]
    fn pin_string_format() {
        assert_eq!(Pin::new(Layer::U, Side::A, 1).unwrap().to_string(), "UA1");
        assert_eq!(Pin::new(Layer::V, Side::B, 23).unwrap().to_string(), "VB23");
        assert_eq!(
            Pin::new(Layer::U, Side::A, 2401).unwrap().to_string(),
            "UA2401"
        );
    }

    #[test]
    fn out_of_range_rejected() {
        assert!(matches!(
            Pin::new(Layer::U, Side::A, 0),
            Err(PinError::NumberOutOfRange { .. })
        ));
        assert!(matches!(
            Pin::new(Layer::U, Side::A, 2402),
            Err(PinError::NumberOutOfRange { .. })
        ));
        assert!(matches!(
            Pin::new(Layer::V, Side::A, 2400),
            Err(PinError::NumberOutOfRange { .. })
        ));
    }

    #[test]
    fn face_ranges_partition_layer() {
        for layer in [Layer::U, Layer::V] {
            for n in 1..=layer.pin_count() {
                let pin = Pin::new(layer, Side::A, n).unwrap();
                let face = pin.face();
                let (_, first, last) = face_ranges(layer)
                    .iter()
                    .copied()
                    .find(|(f, _, _)| *f == face)
                    .unwrap();
                assert!(
                    n >= first && n <= last,
                    "pin {n} on layer {layer:?} got face {face:?} but ranges say {first}..={last}"
                );
            }
        }
    }

    #[test]
    fn tangent_signs_match_spec_examples() {
        assert_eq!(tangent_sides(Layer::U, Side::B, 1), (1, 1));
        assert_eq!(tangent_sides(Layer::U, Side::A, 1), (1, -1));
        assert_eq!(tangent_sides(Layer::U, Side::A, 1500), (-1, 1));
        assert_eq!(tangent_sides(Layer::U, Side::B, 1500), (-1, -1));
        assert_eq!(tangent_sides(Layer::V, Side::A, 200), (1, 1));
        assert_eq!(tangent_sides(Layer::V, Side::B, 200), (1, -1));
        assert_eq!(tangent_sides(Layer::V, Side::A, 1700), (1, 1));
    }

    #[test]
    fn tangent_components_are_signs() {
        for layer in [Layer::U, Layer::V] {
            for n in 1..=layer.pin_count() {
                for side in [Side::A, Side::B] {
                    let (x, y) = tangent_sides(layer, side, n);
                    assert!(x == 1 || x == -1);
                    assert!(y == 1 || y == -1);
                }
            }
        }
    }

    #[test]
    fn endpoint_lookup_matches_table() {
        for layer in [Layer::U, Layer::V] {
            let table: std::collections::HashSet<u16> =
                endpoint_pins(layer).iter().copied().collect();
            for n in 1..=layer.pin_count() {
                let pin = Pin::new(layer, Side::A, n).unwrap();
                let expected = table.contains(&n);
                assert_eq!(
                    pin.is_endpoint(),
                    expected,
                    "endpoint mismatch for {pin} (table contains: {expected})"
                );
            }
        }
    }

    #[test]
    fn endpoint_tables_are_sorted() {
        for layer in [Layer::U, Layer::V] {
            let pins = endpoint_pins(layer);
            for w in pins.windows(2) {
                assert!(w[0] < w[1], "{layer:?} endpoint table not strictly sorted at {:?}", w);
            }
        }
    }

    #[test]
    fn parse_rejects_garbage() {
        assert!("".parse::<Pin>().is_err());
        assert!("X1".parse::<Pin>().is_err());
        assert!("UC1".parse::<Pin>().is_err());
        assert!("UA0".parse::<Pin>().is_err());
        assert!("UAabc".parse::<Pin>().is_err());
    }
}
