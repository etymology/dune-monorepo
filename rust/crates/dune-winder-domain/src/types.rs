use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Layer {
    U,
    V,
    X,
    G,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum PinSide {
    A,
    B,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct PinName {
    pub layer: Layer,
    pub side: PinSide,
    pub number: u32,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Vec2 {
    pub x: f64,
    pub y: f64,
}

impl Vec2 {
    pub const ZERO: Self = Self { x: 0.0, y: 0.0 };

    pub const fn new(x: f64, y: f64) -> Self {
        Self { x, y }
    }
}

macro_rules! unit {
    ($name:ident, $doc:literal) => {
        #[doc = $doc]
        #[derive(Debug, Clone, Copy, PartialEq, PartialOrd, Serialize, Deserialize)]
        pub struct $name(pub f64);

        impl $name {
            pub const ZERO: Self = Self(0.0);
            pub const fn new(value: f64) -> Self {
                Self(value)
            }
        }

        impl From<f64> for $name {
            fn from(value: f64) -> Self {
                Self(value)
            }
        }

        impl From<$name> for f64 {
            fn from(value: $name) -> Self {
                value.0
            }
        }
    };
}

unit!(Mm, "Millimetres of position.");
unit!(MmPerS, "Millimetres per second of velocity.");
unit!(MmPerS2, "Millimetres per second squared of acceleration.");
unit!(MmPerS3, "Millimetres per second cubed of jerk.");
