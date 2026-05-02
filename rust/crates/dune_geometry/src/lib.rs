//! `dune_geometry` — pin geometry, wire-path math, calibration schemas, and
//! the continuous-loop B-pin solver shared by `dune_winder` and
//! `dune_tension`.
//!
//! Spec source of truth: `specs/layer-geometry.allium`,
//! `specs/uv-wrap-geometry.allium`, `specs/uv-machine-calibration.allium`.

pub mod pins;

pub use pins::{
    endpoint_pins, face_ranges, tangent_sides, Face, Layer, Pin, PinError, Side,
    ENDPOINT_PINS_U, ENDPOINT_PINS_V, FACE_RANGES_U, FACE_RANGES_V,
};

#[cfg(feature = "pyo3")]
pub mod python;
