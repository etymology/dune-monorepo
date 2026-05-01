use pyo3::prelude::*;

pub fn check_stop_event(py: Python<'_>, stop_event: &Option<Py<PyAny>>) -> bool {
    if let Some(event) = stop_event {
        match event.call_method0(py, "is_set") {
            Ok(res) => res.extract::<bool>(py).unwrap_or(false),
            Err(_) => false,
        }
    } else {
        false
    }
}
