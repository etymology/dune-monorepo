//! PyO3 bindings for `dune_geometry`. Exposed as the Python module
//! `dune_geometry`. Mirrors the Rust API as closely as PyO3 allows.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyList;

use crate::pins::{
    endpoint_pins, face_ranges, tangent_sides as rust_tangent_sides, Face, Layer, Pin, PinError,
    Side,
};

fn pin_error_to_py(err: PinError) -> PyErr {
    PyValueError::new_err(err.to_string())
}

fn parse_layer(value: &str) -> PyResult<Layer> {
    match value {
        "U" => Ok(Layer::U),
        "V" => Ok(Layer::V),
        other => Err(PyValueError::new_err(format!(
            "unknown layer {other:?}; expected 'U' or 'V'"
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
    fn board_a_to_b_z_mm(&self) -> f64 {
        self.inner.board_a_to_b_z_mm()
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
fn board_a_to_b_z_mm(layer: &str) -> PyResult<f64> {
    Ok(parse_layer(layer)?.board_a_to_b_z_mm())
}

#[pymodule]
pub fn dune_geometry(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyPin>()?;
    m.add_function(wrap_pyfunction!(py_tangent_sides, m)?)?;
    m.add_function(wrap_pyfunction!(py_endpoint_pins, m)?)?;
    m.add_function(wrap_pyfunction!(py_face_ranges, m)?)?;
    m.add_function(wrap_pyfunction!(pin_count, m)?)?;
    m.add_function(wrap_pyfunction!(board_a_to_b_z_mm, m)?)?;
    Ok(())
}
