//! Wire-path geometry: anchor-to-target solving and per-pose camera wire
//! offsets.
//!
//! Spec source of truth: `specs/uv-wrap-geometry.allium`.
//!
//! Today this module owns:
//!
//! - The per-pose camera-wire-offset resolver
//!   ([`effective_camera_wire_offset`]).
//! - The arithmetic that turns raw camera-space pin coordinates plus a
//!   [`MachineCalibrationModel`] into the offset-applied target pose
//!   ([`apply_anchor_to_target_offsets`]).
//! - A typed [`AnchorToTargetRequest`] / [`AnchorToTargetSolution`] pair
//!   shared by Rust callers and the PyO3 surface.
//!
//! The full wire-tangent geometric solve (the part that picks which side of
//! each pin the wire wraps and emits the final commanded head pose) still
//! lives in `src/dune_winder/uv_head_target_parts/` (Python) and is being
//! ported into [`solve_anchor_to_target`] incrementally, gated by the
//! golden-parity fixtures at `tests/golden/geometry/anchor_to_target/`.
//! Until that port lands, [`solve_anchor_to_target`] returns the
//! offset-applied target pose without doing the tangent solve, and the
//! Python wrapper feeds that result into the existing solver.

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::calibration::{HeadSide, MachineCalibrationModel, Vec3};
use crate::pins::Pin;

/// Inputs to [`solve_anchor_to_target`]. Coordinates are raw camera-space
/// (from `PinCalibrationFile::effective_pin_coords`) — the solver applies
/// the per-pose camera wire offset and arm correction internally.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AnchorToTargetRequest {
    pub anchor_pin: Pin,
    pub anchor_xyz: Vec3,
    pub target_pin: Pin,
    pub target_xyz: Vec3,
    /// Optional `(dx, dy)` to add to `target_xyz` before the offset model
    /// is applied. Mirrors the legacy `offset=(x,y)` keyword on
    /// `~anchorToTarget(...)`.
    pub target_offset: Option<(f64, f64)>,
    pub head_side: HeadSide,
    pub hover: bool,
}

/// Output of [`solve_anchor_to_target`]: the commanded winder pose plus the
/// effective offsets that were applied to get there. Today
/// `commanded_head_xyz` is the offset-applied target pose; the eventual
/// wire-tangent solver will refine it to the pose where the wire is
/// tangent to both pins on the correct sides. Field set will grow as the
/// solver port progresses.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AnchorToTargetSolution {
    /// Offset-applied target pose. Currently `target_xyz + target_offset +
    /// effective_camera_wire_offset + effective_arm_correction`. The
    /// wire-tangent refinement step is still owned by the legacy Python
    /// solver and will move here in a follow-up commit.
    pub commanded_head_xyz: Vec3,
    /// The offset that was looked up for `(target_pin, head_side)` from
    /// the [`MachineCalibrationModel`].
    pub effective_camera_wire_offset: Vec3,
    /// The arm correction from the [`MachineCalibrationModel`] (constant
    /// per machine today).
    pub effective_arm_correction: Vec3,
}

#[derive(Debug, Clone, PartialEq, Error)]
pub enum WireError {
    #[error("anchor and target pins must share the same layer (got {anchor:?} vs {target:?})")]
    LayerMismatch { anchor: Pin, target: Pin },
}

/// Resolve the per-pose camera wire offset for a `(pin, head_side)` pair.
/// Per-pin override wins; falls back to the head-side base offset.
pub fn effective_camera_wire_offset(
    model: &MachineCalibrationModel,
    pin: &Pin,
    head_side: HeadSide,
) -> Vec3 {
    model.effective_offset(*pin, head_side)
}

/// Apply the optional `(dx, dy)` target offset, the per-pose camera wire
/// offset, and the arm correction to a raw camera-space target coordinate.
/// Pure arithmetic — no I/O, no winder coupling. Exposed separately so the
/// Python wrapper can call it directly during the incremental port.
pub fn apply_anchor_to_target_offsets(
    target_xyz: Vec3,
    target_offset: Option<(f64, f64)>,
    effective_camera_wire_offset: Vec3,
    effective_arm_correction: Vec3,
) -> Vec3 {
    let mut commanded = target_xyz;
    if let Some((dx, dy)) = target_offset {
        commanded = commanded.add(Vec3::new(dx, dy, 0.0));
    }
    commanded
        .add(effective_camera_wire_offset)
        .add(effective_arm_correction)
}

/// Solve an anchor-to-target request against a [`MachineCalibrationModel`].
///
/// This currently performs steps 1–3 of the spec obligation
/// (`SolveAnchorToTarget` in `specs/uv-wrap-geometry.allium`):
/// raw-coordinate lookup, per-pose camera-wire-offset resolution, and arm
/// correction. The wire-tangent refinement (step 4) is still owned by the
/// Python solver in `src/dune_winder/uv_head_target_parts/` and will move
/// here in a follow-up commit gated by golden fixtures.
pub fn solve_anchor_to_target(
    request: &AnchorToTargetRequest,
    model: &MachineCalibrationModel,
) -> Result<AnchorToTargetSolution, WireError> {
    if request.anchor_pin.layer != request.target_pin.layer {
        return Err(WireError::LayerMismatch {
            anchor: request.anchor_pin,
            target: request.target_pin,
        });
    }
    let effective_camera_wire_offset =
        effective_camera_wire_offset(model, &request.target_pin, request.head_side);
    let effective_arm_correction = model.arm_correction;
    let commanded_head_xyz = apply_anchor_to_target_offsets(
        request.target_xyz,
        request.target_offset,
        effective_camera_wire_offset,
        effective_arm_correction,
    );
    Ok(AnchorToTargetSolution {
        commanded_head_xyz,
        effective_camera_wire_offset,
        effective_arm_correction,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::calibration::PerPinOffset;
    use crate::pins::{Layer, Side};

    fn ua(n: u16) -> Pin {
        Pin::new(Layer::U, Side::A, n).unwrap()
    }

    fn ub(n: u16) -> Pin {
        Pin::new(Layer::U, Side::B, n).unwrap()
    }

    fn vb(n: u16) -> Pin {
        Pin::new(Layer::V, Side::B, n).unwrap()
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

    #[test]
    fn solve_applies_offset_and_arm_correction() {
        let model = MachineCalibrationModel {
            base_camera_wire_offset_stage: Vec3::new(1.0, 2.0, 0.0),
            base_camera_wire_offset_fixed: Vec3::new(0.0, 0.0, 0.0),
            per_pin_camera_wire_offset: vec![],
            arm_correction: Vec3::new(0.5, 0.0, -0.25),
        };
        let request = AnchorToTargetRequest {
            anchor_pin: ua(1),
            anchor_xyz: Vec3::new(100.0, 100.0, 50.0),
            target_pin: ub(2),
            target_xyz: Vec3::new(200.0, 200.0, 60.0),
            target_offset: None,
            head_side: HeadSide::Stage,
            hover: false,
        };
        let sol = solve_anchor_to_target(&request, &model).unwrap();
        assert_eq!(sol.effective_camera_wire_offset, Vec3::new(1.0, 2.0, 0.0));
        assert_eq!(sol.effective_arm_correction, Vec3::new(0.5, 0.0, -0.25));
        // 200 + 1 + 0.5, 200 + 2 + 0, 60 + 0 + -0.25
        assert_eq!(sol.commanded_head_xyz, Vec3::new(201.5, 202.0, 59.75));
    }

    #[test]
    fn solve_applies_target_offset_before_model_offsets() {
        let model = MachineCalibrationModel {
            base_camera_wire_offset_stage: Vec3::new(0.0, 0.0, 0.0),
            base_camera_wire_offset_fixed: Vec3::new(10.0, 20.0, 0.0),
            per_pin_camera_wire_offset: vec![],
            arm_correction: Vec3::new(0.0, 0.0, 5.0),
        };
        let request = AnchorToTargetRequest {
            anchor_pin: ua(1),
            anchor_xyz: Vec3::new(0.0, 0.0, 0.0),
            target_pin: ub(2),
            target_xyz: Vec3::new(100.0, 100.0, 100.0),
            target_offset: Some((1.0, 2.0)),
            head_side: HeadSide::Fixed,
            hover: false,
        };
        let sol = solve_anchor_to_target(&request, &model).unwrap();
        // 100 + 1 + 10, 100 + 2 + 20, 100 + 0 + 5
        assert_eq!(sol.commanded_head_xyz, Vec3::new(111.0, 122.0, 105.0));
    }

    #[test]
    fn solve_per_pin_override_wins() {
        let model = MachineCalibrationModel {
            base_camera_wire_offset_stage: Vec3::new(0.0, 0.0, 0.0),
            base_camera_wire_offset_fixed: Vec3::new(0.0, 0.0, 0.0),
            per_pin_camera_wire_offset: vec![PerPinOffset {
                pin: ub(2),
                offset: Vec3::new(7.0, 8.0, 9.0),
            }],
            arm_correction: Vec3::ZERO,
        };
        let request = AnchorToTargetRequest {
            anchor_pin: ua(1),
            anchor_xyz: Vec3::ZERO,
            target_pin: ub(2),
            target_xyz: Vec3::new(0.0, 0.0, 0.0),
            target_offset: None,
            head_side: HeadSide::Stage,
            hover: false,
        };
        let sol = solve_anchor_to_target(&request, &model).unwrap();
        assert_eq!(sol.commanded_head_xyz, Vec3::new(7.0, 8.0, 9.0));
    }

    #[test]
    fn solve_rejects_layer_mismatch() {
        let model = MachineCalibrationModel::empty();
        let request = AnchorToTargetRequest {
            anchor_pin: ua(1),
            anchor_xyz: Vec3::ZERO,
            target_pin: vb(2),
            target_xyz: Vec3::ZERO,
            target_offset: None,
            head_side: HeadSide::Stage,
            hover: false,
        };
        assert!(matches!(
            solve_anchor_to_target(&request, &model),
            Err(WireError::LayerMismatch { .. })
        ));
    }
}
