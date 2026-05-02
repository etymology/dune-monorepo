//! `dune_geometry` — pin geometry, wire-path math, calibration schemas, and
//! the continuous-loop B-pin solver shared by `dune_winder` and
//! `dune_tension`.
//!
//! Spec source of truth: `specs/layer-geometry.allium`,
//! `specs/uv-wrap-geometry.allium`, `specs/uv-machine-calibration.allium`.

pub mod calibration;
pub mod pins;
pub mod spine;
pub mod tension;
pub mod wire;

pub use calibration::{
    CalibrationError, CalibrationPoint, HeadSide, MachineCalibrationFile,
    MachineCalibrationModel, PerPinOffset, PinCalibrationFile, PinCalibrationSnapshot,
    PinCoordinate, Vec3,
};
pub use pins::{
    endpoint_pins, face_ranges, tangent_sides, Face, Layer, Pin, PinError, Side,
    ENDPOINT_PINS_U, ENDPOINT_PINS_V, FACE_RANGES_U, FACE_RANGES_V,
};
pub use spine::{
    derive_pin_position_from_spine, observe_spine_point_from_touch, solve_spine_loop,
    CalibrationTouch, SpineCalibrationFile, SpineError, SpineLoop, SpinePoint,
};
pub use tension::Geometry;
pub use wire::{
    actual_wire_point_from_machine_target, apply_anchor_to_target_offsets,
    circle_pair_tangent_pairs, compute_arm_corrected_outbound, effective_camera_wire_offset,
    line_equation_from_tangent_points, select_tangent_solution, solve_anchor_to_target,
    tangent_candidates_for_pin_pair, AnchorToTargetRequest, AnchorToTargetSolution,
    ArmCorrectedOutbound, HeadQuadrant, LineEquation, RectBounds, TangentSide, TangentSolution,
    WireError,
};

#[cfg(feature = "pyo3")]
pub mod python;
