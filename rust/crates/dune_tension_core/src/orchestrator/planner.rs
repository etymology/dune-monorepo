/// A planned measurement pose for a single wire.
///
/// Positions are produced by the Python U/V planner (`dune_tension.uv_wire_planner`)
/// rather than reimplemented in Rust: planning happens once per wire (outside the
/// audio hot loop) and the Python planner owns the calibration- and layout-derived
/// geometry.
pub struct PlannedWirePose {
    pub wire_number: i32,
    pub x: f64,
    pub y: f64,
    pub focus_position: Option<i32>,
    pub zone: Option<i32>,
}
