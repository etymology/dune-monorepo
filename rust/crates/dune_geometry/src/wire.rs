//! Wire-path geometry: anchor-to-target solving and per-pose camera wire
//! offsets.
//!
//! Spec source of truth: `specs/uv-wrap-geometry.allium`. Today this module
//! exposes the per-pose offset resolver (a thin function over
//! `MachineCalibrationModel`) and a typed input/output shape for
//! `solve_anchor_to_target`. The full wire-tangent solver currently lives in
//! `src/dune_winder/uv_head_target_parts/` (Python) and will be ported into
//! `solve_anchor_to_target` incrementally, gated by golden-parity fixtures
//! at `tests/golden/geometry/anchor_to_target/`.

use serde::{Deserialize, Serialize};

use crate::calibration::{HeadSide, MachineCalibrationModel, Vec3};
use crate::pins::Pin;

/// Inputs to `solve_anchor_to_target`. Coordinates are raw camera-space
/// (from `PinCalibrationFile::effective_pin_coords`) — the solver applies
/// the per-pose camera wire offset and arm correction internally.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AnchorToTargetRequest {
    pub anchor_pin: Pin,
    pub anchor_xyz: Vec3,
    pub target_pin: Pin,
    pub target_xyz: Vec3,
    /// Optional `(dx, dy)` to add to `target_xyz` (mirrors the legacy
    /// `offset=(x,y)` keyword on `~anchorToTarget(...)`).
    pub target_offset: Option<(f64, f64)>,
    pub head_side: HeadSide,
    pub hover: bool,
}

/// Output of `solve_anchor_to_target`: the commanded winder pose and the
/// solved wire-tangent geometry. Field set will grow as the Python
/// `compute_uv_anchor_to_target_view` is ported across.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AnchorToTargetSolution {
    pub commanded_head_xyz: Vec3,
    pub effective_camera_wire_offset: Vec3,
    pub effective_arm_correction: Vec3,
}

/// Resolve the per-pose camera wire offset for a `(pin, head_side)` pair.
/// Per-pin override wins; falls back to the head-side base offset. Pure
/// function over the calibration model — no I/O, no winder coupling.
pub fn effective_camera_wire_offset(
    model: &MachineCalibrationModel,
    pin: &Pin,
    head_side: HeadSide,
) -> Vec3 {
    model.effective_offset(*pin, head_side)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::calibration::PerPinOffset;
    use crate::pins::{Layer, Side};

    fn ua(n: u16) -> Pin {
        Pin::new(Layer::U, Side::A, n).unwrap()
    }

    #[test]
    fn per_pin_override_wins_over_base() {
        let model = MachineCalibrationModel {
            base_camera_wire_offset_stage: Vec3::new(1.0, 0.0, 0.0),
            base_camera_wire_offset_fixed: Vec3::new(2.0, 0.0, 0.0),
            per_pin_camera_wire_offset: vec![PerPinOffset {
                pin: ua(1),
                offset: Vec3::new(99.0, 0.0, 0.0),
            }],
            arm_correction: Vec3::new(0.0, 0.0, 0.0),
        };
        assert_eq!(
            effective_camera_wire_offset(&model, &ua(1), HeadSide::Stage).x,
            99.0
        );
        assert_eq!(
            effective_camera_wire_offset(&model, &ua(2), HeadSide::Fixed).x,
            2.0
        );
    }
}
