//! Bridge driver: every read/write delegates to a Python object via PyO3.
//!
//! Accepts any Python object exposing the methods:
//!
//! ```text
//!     read(names: list[str]) -> dict[str, value]
//!     write(updates: list[(str, value)]) -> dict[str, bool]
//!     is_functional() -> bool   # optional; defaults to True
//! ```
//!
//! Used during migration so the bus can run over the existing pycomm3 driver
//! and `simulated_plc.py` ladder without touching them. Bridge overhead is a
//! GIL acquisition per batch — acceptable while the architecture beds in.
//! A future PR can replace this with a native EIP/CIP driver.

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;

use parking_lot::Mutex;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

use crate::driver::{Health, PlcDriver};
use crate::error::DriverError;
use crate::snapshot::{CipType, Value};

pub struct PyCallbackDriver {
    py_obj: Py<PyAny>,
    inner: Arc<Mutex<DriverState>>,
    cip_resolver: Box<dyn Fn(&str) -> Option<CipType> + Send>,
}

struct DriverState {
    health: Health,
}

impl PyCallbackDriver {
    pub fn new(
        py_obj: Py<PyAny>,
        cip_resolver: Box<dyn Fn(&str) -> Option<CipType> + Send>,
    ) -> Self {
        Self {
            py_obj,
            inner: Arc::new(Mutex::new(DriverState {
                health: Health::default(),
            })),
            cip_resolver,
        }
    }

    fn record_ok(&self) {
        let mut g = self.inner.lock();
        g.health.connected = true;
        g.health.last_ok = Some(Instant::now());
        g.health.consecutive_failures = 0;
        g.health.last_error = None;
    }

    fn record_err(&self, err: &str) {
        let mut g = self.inner.lock();
        g.health.connected = false;
        g.health.consecutive_failures = g.health.consecutive_failures.saturating_add(1);
        g.health.last_error = Some(err.to_string());
    }
}

impl PlcDriver for PyCallbackDriver {
    fn connect(&mut self) -> Result<(), DriverError> {
        let result: PyResult<bool> = Python::attach(|py| {
            let obj = self.py_obj.bind(py);
            if obj.hasattr("is_functional")? {
                obj.call_method0("is_functional")?.extract::<bool>()
            } else {
                Ok(true)
            }
        });
        match result {
            Ok(true) => {
                self.record_ok();
                Ok(())
            }
            Ok(false) => {
                self.record_err("python driver reports not functional");
                Err(DriverError::NotConnected)
            }
            Err(e) => {
                self.record_err(&e.to_string());
                Err(DriverError::Io(e.to_string()))
            }
        }
    }

    fn disconnect(&mut self) {
        let mut g = self.inner.lock();
        g.health.connected = false;
    }

    fn health(&self) -> Health {
        self.inner.lock().health.clone()
    }

    fn read(&mut self, names: &[&str]) -> Result<HashMap<String, Value>, DriverError> {
        let cip_for = &self.cip_resolver;
        let result: PyResult<HashMap<String, Value>> = Python::attach(|py| {
            let obj = self.py_obj.bind(py);
            let names_list = PyList::new(py, names.iter().copied())?;
            let raw = obj.call_method1("read", (names_list,))?;
            let raw_dict = raw.cast_into::<PyDict>()?;
            let mut out = HashMap::with_capacity(names.len());
            for (k, v) in raw_dict.iter() {
                let name: String = k.extract()?;
                let cip = cip_for(&name).ok_or_else(|| {
                    pyo3::exceptions::PyValueError::new_err(format!(
                        "unknown CIP type for tag {name}"
                    ))
                })?;
                let value = py_obj_to_value(&v, cip)?;
                out.insert(name, value);
            }
            Ok(out)
        });
        match result {
            Ok(map) => {
                self.record_ok();
                Ok(map)
            }
            Err(e) => {
                self.record_err(&e.to_string());
                Err(DriverError::Io(e.to_string()))
            }
        }
    }

    fn write(&mut self, updates: &[(&str, Value)]) -> Result<HashMap<String, bool>, DriverError> {
        let result: PyResult<HashMap<String, bool>> = Python::attach(|py| {
            let obj = self.py_obj.bind(py);
            let mut tuples: Vec<Bound<'_, PyTuple>> = Vec::with_capacity(updates.len());
            for (name, value) in updates {
                let py_value = value_to_py_obj(py, value)?;
                tuples.push(PyTuple::new(py, [name.into_pyobject(py)?.into_any(), py_value])?);
            }
            let updates_list = PyList::new(py, tuples)?;
            let raw = obj.call_method1("write", (updates_list,))?;
            if raw.is_none() {
                let mut out = HashMap::with_capacity(updates.len());
                for (name, _) in updates {
                    out.insert((*name).to_string(), false);
                }
                return Ok(out);
            }
            let raw_dict = raw.cast_into::<PyDict>()?;
            let mut out = HashMap::with_capacity(updates.len());
            for (k, v) in raw_dict.iter() {
                out.insert(k.extract::<String>()?, v.extract::<bool>()?);
            }
            Ok(out)
        });
        match result {
            Ok(map) => {
                self.record_ok();
                Ok(map)
            }
            Err(e) => {
                self.record_err(&e.to_string());
                Err(DriverError::Io(e.to_string()))
            }
        }
    }
}

fn py_obj_to_value(value: &Bound<'_, PyAny>, cip: CipType) -> PyResult<Value> {
    Ok(match cip {
        CipType::Bool => Value::Bool(value.extract::<bool>().or_else(|_| {
            value.extract::<i64>().map(|x| x != 0)
        })?),
        CipType::Sint => Value::Sint(value.extract::<i64>()? as i8),
        CipType::Int => Value::Int(value.extract::<i64>()? as i16),
        CipType::Dint => Value::Dint(value.extract::<i64>()? as i32),
        CipType::Real => Value::Real(value.extract::<f64>()? as f32),
        CipType::RealArray2 => {
            let v: Vec<f32> = value.extract()?;
            if v.len() != 2 {
                return Err(pyo3::exceptions::PyValueError::new_err(
                    "REAL[2] requires 2 elements",
                ));
            }
            Value::RealArray2([v[0], v[1]])
        }
        CipType::RealArray3 => {
            let v: Vec<f32> = value.extract()?;
            if v.len() != 3 {
                return Err(pyo3::exceptions::PyValueError::new_err(
                    "REAL[3] requires 3 elements",
                ));
            }
            Value::RealArray3([v[0], v[1], v[2]])
        }
    })
}

fn value_to_py_obj<'py>(py: Python<'py>, v: &Value) -> PyResult<Bound<'py, PyAny>> {
    Ok(match v {
        Value::Bool(b) => b.into_pyobject(py)?.to_owned().into_any(),
        Value::Sint(x) => (*x as i64).into_pyobject(py)?.into_any(),
        Value::Int(x) => (*x as i64).into_pyobject(py)?.into_any(),
        Value::Dint(x) => (*x as i64).into_pyobject(py)?.into_any(),
        Value::Real(x) => (*x as f64).into_pyobject(py)?.into_any(),
        Value::RealArray2(a) => PyList::new(py, a.iter().copied())?.into_any(),
        Value::RealArray3(a) => PyList::new(py, a.iter().copied())?.into_any(),
    })
}
