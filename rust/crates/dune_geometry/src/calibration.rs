//! Calibration storage schemas for the UV diagonal-layer workflow.
//!
//! Spec source of truth: `specs/uv-machine-calibration.allium`.
//!
//! Two storage files are modelled here:
//!
//! - [`PinCalibrationFile`] — append-only, snapshot-based store of raw
//!   camera-space pin coordinates. **No camera-wire-offset and no
//!   arm-correction are baked into the values.** Both U and V pins coexist
//!   in one file (snapshots are layer-agnostic).
//!
//! - [`MachineCalibrationFile`] — the operator-driven machine calibration:
//!   captured pose-vs-target deltas during paused recipe execution, plus
//!   the fitted [`MachineCalibrationModel`] (camera wire offsets, roller
//!   offsets) emitted by the solver.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::pins::Pin;

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Vec3 {
    pub x: f64,
    pub y: f64,
    pub z: f64,
}

impl Vec3 {
    pub const ZERO: Vec3 = Vec3 {
        x: 0.0,
        y: 0.0,
        z: 0.0,
    };

    pub fn new(x: f64, y: f64, z: f64) -> Vec3 {
        Vec3 { x, y, z }
    }

    pub fn sub(self, other: Vec3) -> Vec3 {
        Vec3 {
            x: self.x - other.x,
            y: self.y - other.y,
            z: self.z - other.z,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum HeadSide {
    Stage,
    Fixed,
}

// =========================================================================
// Pin calibration: snapshot-based, raw camera-space coordinates
// =========================================================================

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PinCoordinate {
    pub pin: Pin,
    pub xyz: Vec3,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PinCalibrationSnapshot {
    pub taken_at: String,
    pub calibration_camera_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub operator: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub notes: Option<String>,
    pub pins: Vec<PinCoordinate>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PinCalibrationFile {
    pub machine_id: String,
    #[serde(default)]
    pub snapshots: Vec<PinCalibrationSnapshot>,
}

impl PinCalibrationFile {
    pub fn new(machine_id: impl Into<String>) -> Self {
        Self {
            machine_id: machine_id.into(),
            snapshots: Vec::new(),
        }
    }

    pub fn append_snapshot(&mut self, snapshot: PinCalibrationSnapshot) {
        self.snapshots.push(snapshot);
    }

    /// Resolve the active raw camera-space coordinate for every pin
    /// captured in any snapshot. Walks snapshots newest-first and keeps the
    /// first XYZ seen for each pin. Pins that never appear are absent from
    /// the result.
    pub fn effective_pin_coords(&self) -> BTreeMap<Pin, Vec3> {
        let mut out: BTreeMap<Pin, Vec3> = BTreeMap::new();
        for snapshot in self.snapshots.iter().rev() {
            for entry in &snapshot.pins {
                out.entry(entry.pin).or_insert(entry.xyz);
            }
        }
        out
    }

    pub fn to_json(&self) -> Result<String, CalibrationError> {
        serde_json::to_string_pretty(self).map_err(CalibrationError::from)
    }

    pub fn from_json(s: &str) -> Result<Self, CalibrationError> {
        serde_json::from_str(s).map_err(CalibrationError::from)
    }
}

// =========================================================================
// Machine calibration: capture points + fitted model
// =========================================================================

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CalibrationPoint {
    pub captured_at: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub operator: Option<String>,
    pub gcode_label: String,
    pub gcode_line: String,
    pub calculated_xyz: Vec3,
    pub recorded_xyz: Vec3,
    pub head_side: HeadSide,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub pin: Option<Pin>,
}

impl CalibrationPoint {
    /// The 3D offset that, when applied to `calculated_xyz`, would have
    /// produced `recorded_xyz`. This is the gcode `offset(x, y, z)` value
    /// label-propagated to every gcode line sharing `gcode_label`.
    pub fn offset(&self) -> Vec3 {
        self.recorded_xyz.sub(self.calculated_xyz)
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MachineCalibrationModel {
    pub base_camera_wire_offset_stage: Vec3,
    pub base_camera_wire_offset_fixed: Vec3,
    /// Per-pin camera-wire-offset overrides; stored as a list (not a map)
    /// so the JSON form remains stable when a Pin is re-keyed.
    pub per_pin_camera_wire_offset: Vec<PerPinOffset>,
    /// Constant per machine.
    pub arm_correction: Vec3,
}

impl MachineCalibrationModel {
    pub fn empty() -> Self {
        Self {
            base_camera_wire_offset_stage: Vec3::ZERO,
            base_camera_wire_offset_fixed: Vec3::ZERO,
            per_pin_camera_wire_offset: Vec::new(),
            arm_correction: Vec3::ZERO,
        }
    }

    /// Resolve the effective camera wire offset for a given pin/head-side.
    /// Per-pin override wins; otherwise the head-side base is returned.
    pub fn effective_offset(&self, pin: Pin, head_side: HeadSide) -> Vec3 {
        for entry in &self.per_pin_camera_wire_offset {
            if entry.pin == pin {
                return entry.offset;
            }
        }
        match head_side {
            HeadSide::Stage => self.base_camera_wire_offset_stage,
            HeadSide::Fixed => self.base_camera_wire_offset_fixed,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PerPinOffset {
    pub pin: Pin,
    pub offset: Vec3,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MachineCalibrationFile {
    pub machine_id: String,
    #[serde(default)]
    pub capture_points: Vec<CalibrationPoint>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub fitted_model: Option<MachineCalibrationModel>,
    /// Roller offsets are opaque at the spec level: the solver writes them
    /// and the gcode regenerator reads them, but the spec does not
    /// constrain shape. Stored as raw JSON to allow implementations to
    /// evolve without breaking the file format.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub roller_offsets: Option<serde_json::Value>,
}

impl MachineCalibrationFile {
    pub fn new(machine_id: impl Into<String>) -> Self {
        Self {
            machine_id: machine_id.into(),
            capture_points: Vec::new(),
            fitted_model: None,
            roller_offsets: None,
        }
    }

    pub fn append_capture(&mut self, point: CalibrationPoint) {
        self.capture_points.push(point);
    }

    pub fn to_json(&self) -> Result<String, CalibrationError> {
        serde_json::to_string_pretty(self).map_err(CalibrationError::from)
    }

    pub fn from_json(s: &str) -> Result<Self, CalibrationError> {
        serde_json::from_str(s).map_err(CalibrationError::from)
    }
}

// =========================================================================
// Errors
// =========================================================================

#[derive(Debug, Error)]
pub enum CalibrationError {
    #[error("calibration JSON serialization failed: {0}")]
    Json(#[from] serde_json::Error),
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::pins::{Layer, Side};

    fn pin(layer: Layer, side: Side, n: u16) -> Pin {
        Pin::new(layer, side, n).expect("test pin construction")
    }

    fn coord(p: Pin, x: f64, y: f64, z: f64) -> PinCoordinate {
        PinCoordinate {
            pin: p,
            xyz: Vec3 { x, y, z },
        }
    }

    #[test]
    fn pin_calibration_file_roundtrip_json() {
        let mut file = PinCalibrationFile::new("apa-stand-01");
        file.append_snapshot(PinCalibrationSnapshot {
            taken_at: "2026-05-02T12:00:00Z".into(),
            calibration_camera_id: "cam-A".into(),
            operator: Some("ben".into()),
            notes: None,
            pins: vec![
                coord(pin(Layer::U, Side::A, 1), 1.0, 2.0, 3.0),
                coord(pin(Layer::V, Side::B, 23), 4.0, 5.0, 6.0),
            ],
        });
        let text = file.to_json().unwrap();
        let restored = PinCalibrationFile::from_json(&text).unwrap();
        assert_eq!(file, restored);
        // Pins serialise as object form, not strings.
        assert!(text.contains("\"layer\": \"U\""));
        assert!(text.contains("\"side\": \"A\""));
        assert!(text.contains("\"number\": 1"));
        assert!(!text.contains("\"UA1\""));
    }

    #[test]
    fn effective_pin_coords_takes_latest_snapshot() {
        let mut file = PinCalibrationFile::new("apa");
        // Older snapshot.
        file.append_snapshot(PinCalibrationSnapshot {
            taken_at: "2026-05-01T00:00:00Z".into(),
            calibration_camera_id: "cam".into(),
            operator: None,
            notes: None,
            pins: vec![
                coord(pin(Layer::U, Side::A, 1), 1.0, 0.0, 0.0),
                coord(pin(Layer::U, Side::A, 2), 2.0, 0.0, 0.0),
            ],
        });
        // Newer snapshot rewrites pin 1 only.
        file.append_snapshot(PinCalibrationSnapshot {
            taken_at: "2026-05-02T00:00:00Z".into(),
            calibration_camera_id: "cam".into(),
            operator: None,
            notes: None,
            pins: vec![coord(pin(Layer::U, Side::A, 1), 99.0, 0.0, 0.0)],
        });
        let eff = file.effective_pin_coords();
        assert_eq!(eff[&pin(Layer::U, Side::A, 1)].x, 99.0);
        assert_eq!(eff[&pin(Layer::U, Side::A, 2)].x, 2.0);
    }

    #[test]
    fn calibration_point_offset_is_recorded_minus_calculated() {
        let p = CalibrationPoint {
            captured_at: "now".into(),
            operator: None,
            gcode_label: "Top B Corner".into(),
            gcode_line: "G1 X1 Y2 Z3".into(),
            calculated_xyz: Vec3 { x: 1.0, y: 2.0, z: 3.0 },
            recorded_xyz: Vec3 { x: 1.5, y: 2.25, z: 3.75 },
            head_side: HeadSide::Stage,
            pin: None,
        };
        let off = p.offset();
        assert!((off.x - 0.5).abs() < 1e-12);
        assert!((off.y - 0.25).abs() < 1e-12);
        assert!((off.z - 0.75).abs() < 1e-12);
    }

    #[test]
    fn machine_calibration_model_per_pin_overrides_base() {
        let pin_a = pin(Layer::U, Side::A, 1);
        let model = MachineCalibrationModel {
            base_camera_wire_offset_stage: Vec3 { x: 1.0, y: 0.0, z: 0.0 },
            base_camera_wire_offset_fixed: Vec3 { x: 2.0, y: 0.0, z: 0.0 },
            per_pin_camera_wire_offset: vec![PerPinOffset {
                pin: pin_a,
                offset: Vec3 { x: 99.0, y: 0.0, z: 0.0 },
            }],
            arm_correction: Vec3::ZERO,
        };
        assert_eq!(model.effective_offset(pin_a, HeadSide::Stage).x, 99.0);
        assert_eq!(model.effective_offset(pin_a, HeadSide::Fixed).x, 99.0);
        // Non-overridden pin falls back to head-side base.
        let pin_b = pin(Layer::U, Side::B, 1);
        assert_eq!(model.effective_offset(pin_b, HeadSide::Stage).x, 1.0);
        assert_eq!(model.effective_offset(pin_b, HeadSide::Fixed).x, 2.0);
    }

    #[test]
    fn machine_calibration_file_roundtrip() {
        let mut file = MachineCalibrationFile::new("apa-stand-01");
        file.append_capture(CalibrationPoint {
            captured_at: "now".into(),
            operator: Some("ben".into()),
            gcode_label: "Top B Corner".into(),
            gcode_line: "~anchorToTarget(B1201,B2001)".into(),
            calculated_xyz: Vec3 { x: 1.0, y: 2.0, z: 3.0 },
            recorded_xyz: Vec3 { x: 1.5, y: 2.25, z: 3.75 },
            head_side: HeadSide::Fixed,
            pin: Some(pin(Layer::U, Side::B, 1201)),
        });
        let text = file.to_json().unwrap();
        let restored = MachineCalibrationFile::from_json(&text).unwrap();
        assert_eq!(file, restored);
        assert!(text.contains("\"head_side\": \"fixed\""));
    }
}
