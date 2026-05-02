//! PyO3 bindings for `dune_geometry`. Exposed as the Python module
//! `dune_geometry`. Mirrors the Rust API as closely as PyO3 allows.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use crate::calibration::{
    CalibrationError, CalibrationPoint, HeadSide, MachineCalibrationFile,
    MachineCalibrationModel, PerPinOffset, PinCalibrationFile, PinCalibrationSnapshot,
    PinCoordinate, Vec3,
};
use crate::pins::{
    endpoint_pins, face_ranges, tangent_sides as rust_tangent_sides, Face, Layer, Pin, PinError,
    Side,
};
use crate::spine::{
    derive_pin_position_from_spine as rust_derive_pin_position_from_spine,
    observe_spine_point_from_touch as rust_observe_spine_point_from_touch,
    solve_spine_loop as rust_solve_spine_loop, CalibrationTouch, SpineCalibrationFile,
    SpineLoop, SpinePoint,
};
use crate::wire::{
    actual_wire_point_from_machine_target as rust_actual_wire_point_from_machine_target,
    compute_arm_corrected_outbound as rust_compute_arm_corrected_outbound,
    line_equation_from_tangent_points as rust_line_equation_from_tangent_points,
    solve_anchor_to_target as rust_solve_anchor_to_target,
    solve_anchor_to_target_from_spine as rust_solve_anchor_to_target_from_spine,
    solve_xg_slots as rust_solve_xg_slots,
    tangent_for_pin_pair as rust_tangent_for_pin_pair, AnchorToTargetRequest,
    AnchorToTargetSolution, AnchorToTargetSpineRequest, HeadQuadrant, RectBounds,
};

fn calibration_error_to_py(err: CalibrationError) -> PyErr {
    PyValueError::new_err(err.to_string())
}

fn parse_head_side(value: &str) -> PyResult<HeadSide> {
    match value {
        "stage" => Ok(HeadSide::Stage),
        "fixed" => Ok(HeadSide::Fixed),
        other => Err(PyValueError::new_err(format!(
            "unknown head_side {other:?}; expected 'stage' or 'fixed'"
        ))),
    }
}

fn head_side_str(side: HeadSide) -> &'static str {
    match side {
        HeadSide::Stage => "stage",
        HeadSide::Fixed => "fixed",
    }
}

fn pin_error_to_py(err: PinError) -> PyErr {
    PyValueError::new_err(err.to_string())
}

fn parse_layer(value: &str) -> PyResult<Layer> {
    match value {
        "U" => Ok(Layer::U),
        "V" => Ok(Layer::V),
        "X" => Ok(Layer::X),
        "G" => Ok(Layer::G),
        other => Err(PyValueError::new_err(format!(
            "unknown layer {other:?}; expected 'U', 'V', 'X' or 'G'"
        ))),
    }
}

fn parse_side(value: &str) -> PyResult<Side> {
    match value {
        "A" => Ok(Side::A),
        "B" => Ok(Side::B),
        other => Err(PyValueError::new_err(format!(
            "unknown side {other:?}; expected 'A' or 'B'"
        ))),
    }
}

fn face_str(face: Face) -> &'static str {
    match face {
        Face::Head => "head",
        Face::Bottom => "bottom",
        Face::Foot => "foot",
        Face::Top => "top",
    }
}

#[pyclass(name = "Pin", module = "dune_geometry", frozen, eq, ord, hash, from_py_object)]
#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct PyPin {
    inner: Pin,
}

#[pymethods]
impl PyPin {
    #[new]
    fn new(layer: &str, side: &str, number: u16) -> PyResult<Self> {
        let layer = parse_layer(layer)?;
        let side = parse_side(side)?;
        Ok(PyPin {
            inner: Pin::new(layer, side, number).map_err(pin_error_to_py)?,
        })
    }

    #[staticmethod]
    fn from_str(name: &str) -> PyResult<Self> {
        let inner: Pin = name.parse().map_err(pin_error_to_py)?;
        Ok(PyPin { inner })
    }

    #[getter]
    fn layer(&self) -> &'static str {
        match self.inner.layer {
            Layer::U => "U",
            Layer::V => "V",
            Layer::X => "X",
            Layer::G => "G",
        }
    }

    #[getter]
    fn side(&self) -> &'static str {
        match self.inner.side {
            Side::A => "A",
            Side::B => "B",
        }
    }

    #[getter]
    fn number(&self) -> u16 {
        self.inner.number
    }

    #[getter]
    fn face(&self) -> &'static str {
        face_str(self.inner.face())
    }

    #[getter]
    fn tangent_normal_sign(&self) -> (i8, i8) {
        self.inner.tangent_normal_sign()
    }

    #[getter]
    fn is_endpoint(&self) -> bool {
        self.inner.is_endpoint()
    }

    #[getter]
    fn board_width_z_mm(&self) -> f64 {
        self.inner.board_width_z_mm()
    }

    #[getter]
    fn half_board_width_z_mm(&self) -> f64 {
        self.inner.half_board_width_z_mm()
    }

    #[getter]
    fn spine_to_face_sign(&self) -> f64 {
        self.inner.spine_to_face_sign()
    }

    fn __str__(&self) -> String {
        self.inner.to_string()
    }

    fn __repr__(&self) -> String {
        format!(
            "Pin(layer='{}', side='{}', number={})",
            self.layer(),
            self.side(),
            self.inner.number
        )
    }
}

#[pyfunction]
#[pyo3(name = "tangent_sides")]
fn py_tangent_sides(layer: &str, side: &str, n: u16) -> PyResult<(i8, i8)> {
    Ok(rust_tangent_sides(parse_layer(layer)?, parse_side(side)?, n))
}

#[pyfunction]
#[pyo3(name = "endpoint_pins")]
fn py_endpoint_pins<'py>(py: Python<'py>, layer: &str) -> PyResult<Bound<'py, PyList>> {
    let layer = parse_layer(layer)?;
    PyList::new(py, endpoint_pins(layer).iter().copied())
}

#[pyfunction]
#[pyo3(name = "face_ranges")]
fn py_face_ranges<'py>(
    py: Python<'py>,
    layer: &str,
) -> PyResult<Bound<'py, PyList>> {
    let layer = parse_layer(layer)?;
    let entries: Vec<(&'static str, u16, u16)> = face_ranges(layer)
        .iter()
        .copied()
        .map(|(face, first, last)| (face_str(face), first, last))
        .collect();
    PyList::new(py, entries)
}

#[pyfunction]
fn pin_count(layer: &str) -> PyResult<u16> {
    Ok(parse_layer(layer)?.pin_count())
}

#[pyfunction]
fn board_width_z_mm(layer: &str) -> PyResult<f64> {
    Ok(parse_layer(layer)?.board_width_z_mm())
}

// =========================================================================
// Calibration pyclasses
// =========================================================================

#[pyclass(name = "Vec3", module = "dune_geometry", frozen, eq, from_py_object)]
#[derive(Clone, Copy, PartialEq)]
pub struct PyVec3 {
    inner: Vec3,
}

#[pymethods]
impl PyVec3 {
    #[new]
    fn new(x: f64, y: f64, z: f64) -> Self {
        PyVec3 {
            inner: Vec3 { x, y, z },
        }
    }

    #[getter]
    fn x(&self) -> f64 {
        self.inner.x
    }
    #[getter]
    fn y(&self) -> f64 {
        self.inner.y
    }
    #[getter]
    fn z(&self) -> f64 {
        self.inner.z
    }

    fn as_tuple(&self) -> (f64, f64, f64) {
        (self.inner.x, self.inner.y, self.inner.z)
    }

    fn __repr__(&self) -> String {
        format!("Vec3({}, {}, {})", self.inner.x, self.inner.y, self.inner.z)
    }
}

impl PyVec3 {
    fn from_inner(inner: Vec3) -> Self {
        PyVec3 { inner }
    }
}

#[pyclass(name = "PinCoordinate", module = "dune_geometry", frozen, eq, from_py_object)]
#[derive(Clone, PartialEq)]
pub struct PyPinCoordinate {
    inner: PinCoordinate,
}

#[pymethods]
impl PyPinCoordinate {
    #[new]
    fn new(pin: &PyPin, xyz: &PyVec3) -> Self {
        PyPinCoordinate {
            inner: PinCoordinate {
                pin: pin.inner,
                xyz: xyz.inner,
            },
        }
    }

    #[getter]
    fn pin(&self) -> PyPin {
        PyPin {
            inner: self.inner.pin,
        }
    }

    #[getter]
    fn xyz(&self) -> PyVec3 {
        PyVec3::from_inner(self.inner.xyz)
    }
}

#[pyclass(name = "PinCalibrationSnapshot", module = "dune_geometry", from_py_object)]
#[derive(Clone)]
pub struct PyPinCalibrationSnapshot {
    inner: PinCalibrationSnapshot,
}

#[pymethods]
impl PyPinCalibrationSnapshot {
    #[new]
    #[pyo3(signature = (taken_at, calibration_camera_id, pins, operator=None, notes=None))]
    fn new(
        taken_at: String,
        calibration_camera_id: String,
        pins: Vec<PyPinCoordinate>,
        operator: Option<String>,
        notes: Option<String>,
    ) -> Self {
        PyPinCalibrationSnapshot {
            inner: PinCalibrationSnapshot {
                taken_at,
                calibration_camera_id,
                operator,
                notes,
                pins: pins.into_iter().map(|p| p.inner).collect(),
            },
        }
    }

    #[getter]
    fn taken_at(&self) -> &str {
        &self.inner.taken_at
    }
    #[getter]
    fn calibration_camera_id(&self) -> &str {
        &self.inner.calibration_camera_id
    }
    #[getter]
    fn operator(&self) -> Option<String> {
        self.inner.operator.clone()
    }
    #[getter]
    fn notes(&self) -> Option<String> {
        self.inner.notes.clone()
    }
    #[getter]
    fn pins(&self) -> Vec<PyPinCoordinate> {
        self.inner
            .pins
            .iter()
            .cloned()
            .map(|p| PyPinCoordinate { inner: p })
            .collect()
    }
}

#[pyclass(name = "PinCalibrationFile", module = "dune_geometry")]
pub struct PyPinCalibrationFile {
    inner: PinCalibrationFile,
}

#[pymethods]
impl PyPinCalibrationFile {
    #[new]
    fn new(machine_id: String) -> Self {
        PyPinCalibrationFile {
            inner: PinCalibrationFile::new(machine_id),
        }
    }

    #[staticmethod]
    fn from_json(s: &str) -> PyResult<Self> {
        Ok(PyPinCalibrationFile {
            inner: PinCalibrationFile::from_json(s).map_err(calibration_error_to_py)?,
        })
    }

    fn to_json(&self) -> PyResult<String> {
        self.inner.to_json().map_err(calibration_error_to_py)
    }

    #[getter]
    fn machine_id(&self) -> &str {
        &self.inner.machine_id
    }

    #[getter]
    fn snapshots(&self) -> Vec<PyPinCalibrationSnapshot> {
        self.inner
            .snapshots
            .iter()
            .cloned()
            .map(|s| PyPinCalibrationSnapshot { inner: s })
            .collect()
    }

    fn append_snapshot(&mut self, snapshot: &PyPinCalibrationSnapshot) {
        self.inner.append_snapshot(snapshot.inner.clone());
    }

    /// Returns the active raw camera-space coordinate for every captured
    /// pin as a list of (Pin, Vec3) pairs (newest snapshot wins).
    fn effective_pin_coords<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let coords: Vec<(PyPin, PyVec3)> = self
            .inner
            .effective_pin_coords()
            .into_iter()
            .map(|(pin, xyz)| (PyPin { inner: pin }, PyVec3::from_inner(xyz)))
            .collect();
        PyList::new(py, coords)
    }
}

#[pyclass(name = "PerPinOffset", module = "dune_geometry", frozen, from_py_object)]
#[derive(Clone)]
pub struct PyPerPinOffset {
    inner: PerPinOffset,
}

#[pymethods]
impl PyPerPinOffset {
    #[new]
    fn new(pin: &PyPin, offset: &PyVec3) -> Self {
        PyPerPinOffset {
            inner: PerPinOffset {
                pin: pin.inner,
                offset: offset.inner,
            },
        }
    }

    #[getter]
    fn pin(&self) -> PyPin {
        PyPin {
            inner: self.inner.pin,
        }
    }

    #[getter]
    fn offset(&self) -> PyVec3 {
        PyVec3::from_inner(self.inner.offset)
    }
}

#[pyclass(name = "MachineCalibrationModel", module = "dune_geometry", from_py_object)]
#[derive(Clone)]
pub struct PyMachineCalibrationModel {
    inner: MachineCalibrationModel,
}

#[pymethods]
impl PyMachineCalibrationModel {
    #[new]
    #[pyo3(signature = (
        base_camera_wire_offset_stage,
        base_camera_wire_offset_fixed,
        per_pin_camera_wire_offset = vec![],
        arm_correction = PyVec3::from_inner(Vec3::ZERO),
    ))]
    fn new(
        base_camera_wire_offset_stage: &PyVec3,
        base_camera_wire_offset_fixed: &PyVec3,
        per_pin_camera_wire_offset: Vec<PyPerPinOffset>,
        arm_correction: PyVec3,
    ) -> Self {
        PyMachineCalibrationModel {
            inner: MachineCalibrationModel {
                base_camera_wire_offset_stage: base_camera_wire_offset_stage.inner,
                base_camera_wire_offset_fixed: base_camera_wire_offset_fixed.inner,
                per_pin_camera_wire_offset: per_pin_camera_wire_offset
                    .into_iter()
                    .map(|p| p.inner)
                    .collect(),
                arm_correction: arm_correction.inner,
            },
        }
    }

    #[staticmethod]
    fn empty() -> Self {
        PyMachineCalibrationModel {
            inner: MachineCalibrationModel::empty(),
        }
    }

    fn effective_offset(&self, pin: &PyPin, head_side: &str) -> PyResult<PyVec3> {
        let hs = parse_head_side(head_side)?;
        Ok(PyVec3::from_inner(self.inner.effective_offset(pin.inner, hs)))
    }

    #[getter]
    fn base_camera_wire_offset_stage(&self) -> PyVec3 {
        PyVec3::from_inner(self.inner.base_camera_wire_offset_stage)
    }

    #[getter]
    fn base_camera_wire_offset_fixed(&self) -> PyVec3 {
        PyVec3::from_inner(self.inner.base_camera_wire_offset_fixed)
    }

    #[getter]
    fn arm_correction(&self) -> PyVec3 {
        PyVec3::from_inner(self.inner.arm_correction)
    }

    #[getter]
    fn per_pin_camera_wire_offset(&self) -> Vec<PyPerPinOffset> {
        self.inner
            .per_pin_camera_wire_offset
            .iter()
            .cloned()
            .map(|p| PyPerPinOffset { inner: p })
            .collect()
    }
}

#[pyclass(name = "CalibrationPoint", module = "dune_geometry", from_py_object)]
#[derive(Clone)]
pub struct PyCalibrationPoint {
    inner: CalibrationPoint,
}

#[pymethods]
impl PyCalibrationPoint {
    #[new]
    #[pyo3(signature = (
        captured_at,
        gcode_label,
        gcode_line,
        calculated_xyz,
        recorded_xyz,
        head_side,
        operator = None,
        pin = None,
    ))]
    fn new(
        captured_at: String,
        gcode_label: String,
        gcode_line: String,
        calculated_xyz: &PyVec3,
        recorded_xyz: &PyVec3,
        head_side: &str,
        operator: Option<String>,
        pin: Option<PyPin>,
    ) -> PyResult<Self> {
        let hs = parse_head_side(head_side)?;
        Ok(PyCalibrationPoint {
            inner: CalibrationPoint {
                captured_at,
                operator,
                gcode_label,
                gcode_line,
                calculated_xyz: calculated_xyz.inner,
                recorded_xyz: recorded_xyz.inner,
                head_side: hs,
                pin: pin.map(|p| p.inner),
            },
        })
    }

    #[getter]
    fn captured_at(&self) -> &str {
        &self.inner.captured_at
    }
    #[getter]
    fn operator(&self) -> Option<String> {
        self.inner.operator.clone()
    }
    #[getter]
    fn gcode_label(&self) -> &str {
        &self.inner.gcode_label
    }
    #[getter]
    fn gcode_line(&self) -> &str {
        &self.inner.gcode_line
    }
    #[getter]
    fn calculated_xyz(&self) -> PyVec3 {
        PyVec3::from_inner(self.inner.calculated_xyz)
    }
    #[getter]
    fn recorded_xyz(&self) -> PyVec3 {
        PyVec3::from_inner(self.inner.recorded_xyz)
    }
    #[getter]
    fn head_side(&self) -> &'static str {
        head_side_str(self.inner.head_side)
    }
    #[getter]
    fn pin(&self) -> Option<PyPin> {
        self.inner.pin.map(|p| PyPin { inner: p })
    }

    fn offset(&self) -> PyVec3 {
        PyVec3::from_inner(self.inner.offset())
    }
}

#[pyclass(name = "MachineCalibrationFile", module = "dune_geometry")]
pub struct PyMachineCalibrationFile {
    inner: MachineCalibrationFile,
}

#[pymethods]
impl PyMachineCalibrationFile {
    #[new]
    fn new(machine_id: String) -> Self {
        PyMachineCalibrationFile {
            inner: MachineCalibrationFile::new(machine_id),
        }
    }

    #[staticmethod]
    fn from_json(s: &str) -> PyResult<Self> {
        Ok(PyMachineCalibrationFile {
            inner: MachineCalibrationFile::from_json(s).map_err(calibration_error_to_py)?,
        })
    }

    fn to_json(&self) -> PyResult<String> {
        self.inner.to_json().map_err(calibration_error_to_py)
    }

    #[getter]
    fn machine_id(&self) -> &str {
        &self.inner.machine_id
    }

    #[getter]
    fn capture_points(&self) -> Vec<PyCalibrationPoint> {
        self.inner
            .capture_points
            .iter()
            .cloned()
            .map(|p| PyCalibrationPoint { inner: p })
            .collect()
    }

    #[getter]
    fn fitted_model(&self) -> Option<PyMachineCalibrationModel> {
        self.inner
            .fitted_model
            .as_ref()
            .cloned()
            .map(|m| PyMachineCalibrationModel { inner: m })
    }

    fn append_capture(&mut self, point: &PyCalibrationPoint) {
        self.inner.append_capture(point.inner.clone());
    }

    fn set_fitted_model(&mut self, model: &PyMachineCalibrationModel) {
        self.inner.fitted_model = Some(model.inner.clone());
    }

    /// roller_offsets is opaque: it round-trips as a Python dict / list /
    /// scalar via JSON. None when no roller fit has been written.
    fn roller_offsets<'py>(&self, py: Python<'py>) -> PyResult<Option<Bound<'py, PyAny>>> {
        let Some(value) = self.inner.roller_offsets.as_ref() else {
            return Ok(None);
        };
        let text = serde_json::to_string(value).map_err(|e| PyValueError::new_err(e.to_string()))?;
        let json_loads = py.import("json")?.getattr("loads")?;
        Ok(Some(json_loads.call1((text,))?))
    }

    fn set_roller_offsets(&mut self, value: Bound<'_, PyAny>) -> PyResult<()> {
        let py = value.py();
        let json_dumps = py.import("json")?.getattr("dumps")?;
        let text: String = json_dumps.call1((value,))?.extract()?;
        self.inner.roller_offsets = Some(
            serde_json::from_str(&text)
                .map_err(|e| PyValueError::new_err(e.to_string()))?,
        );
        Ok(())
    }
}

// =========================================================================
// Wire / anchor-to-target pyclasses
// =========================================================================

#[pyclass(name = "AnchorToTargetRequest", module = "dune_geometry", from_py_object)]
#[derive(Clone)]
pub struct PyAnchorToTargetRequest {
    inner: AnchorToTargetRequest,
}

#[pymethods]
impl PyAnchorToTargetRequest {
    #[new]
    #[pyo3(signature = (
        anchor_pin,
        anchor_xyz,
        target_pin,
        target_xyz,
        head_side,
        target_offset = None,
        hover = false,
    ))]
    fn new(
        anchor_pin: &PyPin,
        anchor_xyz: &PyVec3,
        target_pin: &PyPin,
        target_xyz: &PyVec3,
        head_side: &str,
        target_offset: Option<(f64, f64)>,
        hover: bool,
    ) -> PyResult<Self> {
        let hs = parse_head_side(head_side)?;
        Ok(PyAnchorToTargetRequest {
            inner: AnchorToTargetRequest {
                anchor_pin: anchor_pin.inner,
                anchor_xyz: anchor_xyz.inner,
                target_pin: target_pin.inner,
                target_xyz: target_xyz.inner,
                target_offset,
                head_side: hs,
                hover,
            },
        })
    }

    #[getter]
    fn anchor_pin(&self) -> PyPin {
        PyPin {
            inner: self.inner.anchor_pin,
        }
    }
    #[getter]
    fn anchor_xyz(&self) -> PyVec3 {
        PyVec3::from_inner(self.inner.anchor_xyz)
    }
    #[getter]
    fn target_pin(&self) -> PyPin {
        PyPin {
            inner: self.inner.target_pin,
        }
    }
    #[getter]
    fn target_xyz(&self) -> PyVec3 {
        PyVec3::from_inner(self.inner.target_xyz)
    }
    #[getter]
    fn target_offset(&self) -> Option<(f64, f64)> {
        self.inner.target_offset
    }
    #[getter]
    fn head_side(&self) -> &'static str {
        head_side_str(self.inner.head_side)
    }
    #[getter]
    fn hover(&self) -> bool {
        self.inner.hover
    }
}

#[pyclass(name = "AnchorToTargetSolution", module = "dune_geometry", from_py_object)]
#[derive(Clone)]
pub struct PyAnchorToTargetSolution {
    inner: AnchorToTargetSolution,
}

#[pymethods]
impl PyAnchorToTargetSolution {
    #[getter]
    fn commanded_head_xyz(&self) -> PyVec3 {
        PyVec3::from_inner(self.inner.commanded_head_xyz)
    }
    #[getter]
    fn effective_camera_wire_offset(&self) -> PyVec3 {
        PyVec3::from_inner(self.inner.effective_camera_wire_offset)
    }
    #[getter]
    fn effective_arm_correction(&self) -> PyVec3 {
        PyVec3::from_inner(self.inner.effective_arm_correction)
    }
}

#[pyfunction]
#[pyo3(name = "solve_anchor_to_target")]
fn py_solve_anchor_to_target(
    request: &PyAnchorToTargetRequest,
    model: &PyMachineCalibrationModel,
) -> PyResult<PyAnchorToTargetSolution> {
    rust_solve_anchor_to_target(&request.inner, &model.inner)
        .map(|s| PyAnchorToTargetSolution { inner: s })
        .map_err(|e| PyValueError::new_err(e.to_string()))
}

/// Compute the line equation `(slope, intercept, is_vertical)` through two
/// tangent points. Vertical lines return `slope = float('inf')` and the
/// `intercept` carries the `x` coordinate.
#[pyfunction]
#[pyo3(name = "line_equation_from_tangent_points")]
fn py_line_equation_from_tangent_points(
    tangent_a: (f64, f64),
    tangent_b: (f64, f64),
) -> (f64, f64, bool) {
    let eq = rust_line_equation_from_tangent_points(tangent_a, tangent_b);
    (eq.slope, eq.intercept, eq.is_vertical)
}

/// Compute the unique wire-side tangent line between two pins, derived
/// directly from each pin's `tangent_sides` rule. Returns
/// `((tangent_a_x, tangent_a_y), (tangent_b_x, tangent_b_y))`.
#[pyfunction]
#[pyo3(name = "tangent_for_pin_pair")]
fn py_tangent_for_pin_pair(
    anchor: &PyPin,
    anchor_xy: (f64, f64),
    anchor_radius: f64,
    target: &PyPin,
    target_xy: (f64, f64),
    target_radius: f64,
) -> PyResult<((f64, f64), (f64, f64))> {
    rust_tangent_for_pin_pair(
        anchor.inner,
        anchor_xy,
        anchor_radius,
        target.inner,
        target_xy,
        target_radius,
    )
    .map_err(|e| PyValueError::new_err(e.to_string()))
}

fn quadrant_str(q: HeadQuadrant) -> &'static str {
    match q {
        HeadQuadrant::NW => "NW",
        HeadQuadrant::NE => "NE",
        HeadQuadrant::SW => "SW",
        HeadQuadrant::SE => "SE",
    }
}

/// Solve the head pose so the active roller is tangent to the wire-tangent
/// line, returning
/// `((corrected_outbound_x, corrected_outbound_y),
///   (corrected_head_center_x, corrected_head_center_y),
///   roller_index, "NW" | "NE" | "SW" | "SE")`.
///
/// `transfer_bounds = (left, top, right, bottom)`.
/// `roller_arm_y_offsets = (y0, y1, y2, y3)` or `None` for nominal.
#[pyfunction]
#[pyo3(name = "compute_arm_corrected_outbound")]
#[pyo3(signature = (
    anchor_pin_point,
    target_pin_point,
    tangent_point_a,
    tangent_point_b,
    transfer_bounds,
    head_arm_length,
    head_roller_radius,
    head_roller_gap,
    roller_arm_y_offsets = None,
))]
#[allow(clippy::too_many_arguments)]
fn py_compute_arm_corrected_outbound(
    anchor_pin_point: (f64, f64),
    target_pin_point: (f64, f64),
    tangent_point_a: (f64, f64),
    tangent_point_b: (f64, f64),
    transfer_bounds: (f64, f64, f64, f64),
    head_arm_length: f64,
    head_roller_radius: f64,
    head_roller_gap: f64,
    roller_arm_y_offsets: Option<(f64, f64, f64, f64)>,
) -> PyResult<((f64, f64), (f64, f64), u8, &'static str)> {
    let (left, top, right, bottom) = transfer_bounds;
    let bounds = RectBounds {
        left,
        top,
        right,
        bottom,
    };
    let result = rust_compute_arm_corrected_outbound(
        anchor_pin_point,
        target_pin_point,
        tangent_point_a,
        tangent_point_b,
        bounds,
        head_arm_length,
        head_roller_radius,
        head_roller_gap,
        roller_arm_y_offsets,
    )
    .map_err(|e| PyValueError::new_err(e.to_string()))?;
    Ok((
        result.corrected_outbound,
        result.corrected_head_center,
        result.roller_index,
        quadrant_str(result.quadrant),
    ))
}

/// Project the actual wire-end XY for a commanded head pose. Returns
/// `(wire_x, wire_y)`.
#[pyfunction]
#[pyo3(name = "actual_wire_point_from_machine_target")]
#[allow(clippy::too_many_arguments)]
fn py_actual_wire_point_from_machine_target(
    final_head_xy: (f64, f64),
    compensated_anchor_xy: (f64, f64),
    anchor_z: f64,
    head_z: f64,
    head_arm_length: f64,
    head_roller_radius: f64,
    head_roller_gap: f64,
) -> (f64, f64) {
    rust_actual_wire_point_from_machine_target(
        final_head_xy,
        compensated_anchor_xy,
        anchor_z,
        head_z,
        head_arm_length,
        head_roller_radius,
        head_roller_gap,
    )
}

// =========================================================================
// Spine calibration pyclasses & functions
// =========================================================================

#[pyclass(name = "SpinePoint", module = "dune_geometry", frozen, eq, from_py_object)]
#[derive(Clone, Copy, PartialEq)]
pub struct PySpinePoint {
    inner: SpinePoint,
}

#[pymethods]
impl PySpinePoint {
    #[new]
    fn new(layer: &str, number: u16, xyz: &PyVec3) -> PyResult<Self> {
        Ok(PySpinePoint {
            inner: SpinePoint {
                layer: parse_layer(layer)?,
                number,
                xyz: xyz.inner,
            },
        })
    }

    #[getter]
    fn layer(&self) -> &'static str {
        match self.inner.layer {
            Layer::U => "U",
            Layer::V => "V",
            Layer::X => "X",
            Layer::G => "G",
        }
    }

    #[getter]
    fn number(&self) -> u16 {
        self.inner.number
    }

    #[getter]
    fn xyz(&self) -> PyVec3 {
        PyVec3::from_inner(self.inner.xyz)
    }
}

#[pyclass(name = "SpineLoop", module = "dune_geometry", from_py_object)]
#[derive(Clone)]
pub struct PySpineLoop {
    inner: SpineLoop,
}

#[pymethods]
impl PySpineLoop {
    #[new]
    fn new(layer: &str, points: Vec<PySpinePoint>) -> PyResult<Self> {
        Ok(PySpineLoop {
            inner: SpineLoop {
                layer: parse_layer(layer)?,
                points: points.into_iter().map(|p| p.inner).collect(),
            },
        })
    }

    #[getter]
    fn layer(&self) -> &'static str {
        match self.inner.layer {
            Layer::U => "U",
            Layer::V => "V",
            Layer::X => "X",
            Layer::G => "G",
        }
    }

    #[getter]
    fn points(&self) -> Vec<PySpinePoint> {
        self.inner
            .points
            .iter()
            .copied()
            .map(|p| PySpinePoint { inner: p })
            .collect()
    }

    fn point(&self, number: u16) -> Option<PySpinePoint> {
        self.inner.point(number).copied().map(|p| PySpinePoint { inner: p })
    }
}

#[pyclass(name = "SpineCalibrationFile", module = "dune_geometry", from_py_object)]
#[derive(Clone)]
pub struct PySpineCalibrationFile {
    inner: SpineCalibrationFile,
}

#[pymethods]
impl PySpineCalibrationFile {
    #[new]
    #[pyo3(signature = (machine_id, loops = vec![]))]
    fn new(machine_id: String, loops: Vec<PySpineLoop>) -> Self {
        PySpineCalibrationFile {
            inner: SpineCalibrationFile {
                machine_id,
                loops: loops.into_iter().map(|l| l.inner).collect(),
            },
        }
    }

    #[getter]
    fn machine_id(&self) -> String {
        self.inner.machine_id.clone()
    }

    #[getter]
    fn loops(&self) -> Vec<PySpineLoop> {
        self.inner
            .loops
            .iter()
            .cloned()
            .map(|l| PySpineLoop { inner: l })
            .collect()
    }

    fn loop_for(&self, layer: &str) -> PyResult<Option<PySpineLoop>> {
        let layer = parse_layer(layer)?;
        Ok(self
            .inner
            .loop_for(layer)
            .cloned()
            .map(|l| PySpineLoop { inner: l }))
    }

    /// Derived raw camera-space XYZ for a `(layer, side, number)` pin.
    /// Returns `None` when the layer's loop is missing or the loop has
    /// no spine point at that number.
    fn raw_pin_position(&self, pin: &PyPin) -> Option<(f64, f64, f64)> {
        self.inner
            .raw_pin_position(pin.inner)
            .map(|v| (v.x, v.y, v.z))
    }
}

#[pyclass(name = "AnchorToTargetSpineRequest", module = "dune_geometry", from_py_object)]
#[derive(Clone)]
pub struct PyAnchorToTargetSpineRequest {
    inner: AnchorToTargetSpineRequest,
}

#[pymethods]
impl PyAnchorToTargetSpineRequest {
    #[new]
    #[pyo3(signature = (
        anchor_pin,
        target_pin,
        head_side,
        target_offset = None,
        hover = false,
    ))]
    fn new(
        anchor_pin: &PyPin,
        target_pin: &PyPin,
        head_side: &str,
        target_offset: Option<(f64, f64)>,
        hover: bool,
    ) -> PyResult<Self> {
        let hs = parse_head_side(head_side)?;
        Ok(PyAnchorToTargetSpineRequest {
            inner: AnchorToTargetSpineRequest {
                anchor_pin: anchor_pin.inner,
                target_pin: target_pin.inner,
                target_offset,
                head_side: hs,
                hover,
            },
        })
    }

    #[getter]
    fn anchor_pin(&self) -> PyPin {
        PyPin { inner: self.inner.anchor_pin }
    }
    #[getter]
    fn target_pin(&self) -> PyPin {
        PyPin { inner: self.inner.target_pin }
    }
    #[getter]
    fn target_offset(&self) -> Option<(f64, f64)> {
        self.inner.target_offset
    }
    #[getter]
    fn head_side(&self) -> &'static str {
        head_side_str(self.inner.head_side)
    }
    #[getter]
    fn hover(&self) -> bool {
        self.inner.hover
    }
}

/// Spine-backed parallel of `solve_anchor_to_target`: resolves the
/// anchor and target raw XYZ from `spine_file` and delegates to the
/// existing solver. Errors with `ValueError` if either pin's spine
/// point is missing or if the two pins are on different layers.
#[pyfunction]
#[pyo3(name = "solve_anchor_to_target_from_spine")]
fn py_solve_anchor_to_target_from_spine(
    request: &PyAnchorToTargetSpineRequest,
    spine_file: &PySpineCalibrationFile,
    model: &PyMachineCalibrationModel,
) -> PyResult<PyAnchorToTargetSolution> {
    rust_solve_anchor_to_target_from_spine(&request.inner, &spine_file.inner, &model.inner)
        .map(|s| PyAnchorToTargetSolution { inner: s })
        .map_err(|e| PyValueError::new_err(e.to_string()))
}

/// Derive raw camera-space pin XYZ from a spine XYZ at the same pin
/// number. Returns `(x, y, z)`. Mirrors
/// `derive_pin_position_from_spine` in `dune_geometry::spine`.
#[pyfunction]
#[pyo3(name = "derive_pin_position_from_spine")]
fn py_derive_pin_position_from_spine(
    spine_xyz: (f64, f64, f64),
    pin: &PyPin,
) -> (f64, f64, f64) {
    let (x, y, z) = spine_xyz;
    let derived = rust_derive_pin_position_from_spine(Vec3::new(x, y, z), pin.inner);
    (derived.x, derived.y, derived.z)
}

/// Inverse of `derive_pin_position_from_spine`: collapse a calibration
/// touch (`pin`, recorded `winder_xyz`) into the implied spine XYZ at
/// `pin.number`. Returns `(x, y, z)`.
#[pyfunction]
#[pyo3(name = "observe_spine_point_from_touch")]
fn py_observe_spine_point_from_touch(
    pin: &PyPin,
    winder_xyz: (f64, f64, f64),
) -> (f64, f64, f64) {
    let (x, y, z) = winder_xyz;
    let observed = rust_observe_spine_point_from_touch(CalibrationTouch {
        pin: pin.inner,
        winder_xyz: Vec3::new(x, y, z),
    });
    (observed.x, observed.y, observed.z)
}

/// Fit a closed continuous spine loop to a list of calibration touches
/// `[(pin, (winder_x, winder_y, winder_z)), ...]`. Returns a
/// `SpineLoop` covering every pin number in `1..=pin_count(layer)`.
#[pyfunction]
#[pyo3(name = "solve_spine_loop")]
fn py_solve_spine_loop(
    layer: &str,
    touches: Vec<(PyPin, (f64, f64, f64))>,
) -> PyResult<PySpineLoop> {
    let layer = parse_layer(layer)?;
    let touches: Vec<CalibrationTouch> = touches
        .into_iter()
        .map(|(pin, (x, y, z))| CalibrationTouch {
            pin: pin.inner,
            winder_xyz: Vec3::new(x, y, z),
        })
        .collect();
    rust_solve_spine_loop(layer, &touches)
        .map(|loop_| PySpineLoop { inner: loop_ })
        .map_err(|e| PyValueError::new_err(e.to_string()))
}

// silence unused-import warnings under different feature combos
#[allow(dead_code)]
fn _unused(_: &PyDict) {}

#[pyfunction]
#[pyo3(name = "solve_xg_slots")]
fn py_solve_xg_slots(
    layer: &str,
    bh1: &PyVec3,
    bh_max: &PyVec3,
    bf1: &PyVec3,
    bf_max: &PyVec3,
) -> PyResult<Vec<PyPinCoordinate>> {
    let layer = parse_layer(layer)?;
    Ok(rust_solve_xg_slots(layer, bh1.inner, bh_max.inner, bf1.inner, bf_max.inner)
        .into_iter()
        .map(|c| PyPinCoordinate { inner: c })
        .collect())
}

#[pymodule]
pub fn dune_geometry(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyPin>()?;
    m.add_class::<PyVec3>()?;
    m.add_class::<PyPinCoordinate>()?;
    m.add_class::<PyPinCalibrationSnapshot>()?;
    m.add_class::<PyPinCalibrationFile>()?;
    m.add_class::<PyPerPinOffset>()?;
    m.add_class::<PyMachineCalibrationModel>()?;
    m.add_class::<PyCalibrationPoint>()?;
    m.add_class::<PyMachineCalibrationFile>()?;
    m.add_class::<PyAnchorToTargetRequest>()?;
    m.add_class::<PyAnchorToTargetSolution>()?;
    m.add_function(wrap_pyfunction!(py_tangent_sides, m)?)?;
    m.add_function(wrap_pyfunction!(py_endpoint_pins, m)?)?;
    m.add_function(wrap_pyfunction!(py_face_ranges, m)?)?;
    m.add_function(wrap_pyfunction!(pin_count, m)?)?;
    m.add_function(wrap_pyfunction!(board_width_z_mm, m)?)?;
    m.add_function(wrap_pyfunction!(py_solve_anchor_to_target, m)?)?;
    m.add_function(wrap_pyfunction!(py_solve_xg_slots, m)?)?;
    m.add_function(wrap_pyfunction!(py_line_equation_from_tangent_points, m)?)?;
    m.add_function(wrap_pyfunction!(py_tangent_for_pin_pair, m)?)?;
    m.add_function(wrap_pyfunction!(py_compute_arm_corrected_outbound, m)?)?;
    m.add_function(wrap_pyfunction!(py_actual_wire_point_from_machine_target, m)?)?;
    m.add_class::<PySpinePoint>()?;
    m.add_class::<PySpineLoop>()?;
    m.add_class::<PySpineCalibrationFile>()?;
    m.add_class::<PyAnchorToTargetSpineRequest>()?;
    m.add_function(wrap_pyfunction!(py_derive_pin_position_from_spine, m)?)?;
    m.add_function(wrap_pyfunction!(py_observe_spine_point_from_touch, m)?)?;
    m.add_function(wrap_pyfunction!(py_solve_spine_loop, m)?)?;
    m.add_function(wrap_pyfunction!(py_solve_anchor_to_target_from_spine, m)?)?;
    Ok(())
}
