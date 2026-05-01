use pyo3::prelude::*;

pub struct PlannedWirePose {
    pub wire_number: i32,
    pub x: f64,
    pub y: f64,
    pub focus_position: Option<i32>,
    pub zone: Option<i32>,
}

impl PlannedWirePose {
    pub fn from_py(py: Python<'_>, pose: Py<PyAny>) -> PyResult<Self> {
        let wire_number = pose.getattr(py, "wire_number")?.extract::<i32>(py)?;
        let x = pose.getattr(py, "x")?.extract::<f64>(py)?;
        let y = pose.getattr(py, "y")?.extract::<f64>(py)?;
        let focus_position = pose
            .getattr(py, "focus_position")?
            .extract::<Option<i32>>(py)?;
        let zone = pose.getattr(py, "zone")?.extract::<Option<i32>>(py)?;
        Ok(PlannedWirePose {
            wire_number,
            x,
            y,
            focus_position,
            zone,
        })
    }
}
