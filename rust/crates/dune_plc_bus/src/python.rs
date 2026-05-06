//! PyO3 bindings. The Python surface mirrors the Rust API but is string-keyed
//! (the bus's typed handles can't cross FFI cleanly). Tag identity is resolved
//! against the generated `all_tags()` table; unknown names raise `ValueError`.

use std::collections::HashMap;
use std::sync::{Arc, OnceLock};
use std::time::Duration;

use pyo3::exceptions::{PyRuntimeError, PyTimeoutError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};
use pyo3::IntoPyObject;

use crate::bus::{BusConfig, TagBus};
use crate::driver::PlcDriver;
use crate::drivers::{PyCallbackDriver, SimulatedDriver};
use crate::error::{StaleReadError, WriteFailed};
use crate::schema::all_tags;
use crate::snapshot::{CipType, Source, Tier, Value};
use crate::tag::ErasedTagId;

fn tag_table() -> &'static HashMap<String, ErasedTagId> {
    static TABLE: OnceLock<HashMap<String, ErasedTagId>> = OnceLock::new();
    TABLE.get_or_init(|| {
        all_tags()
            .iter()
            .map(|t| (t.name.to_string(), *t))
            .collect()
    })
}

fn resolve_tag(name: &str) -> PyResult<ErasedTagId> {
    tag_table()
        .get(name)
        .copied()
        .ok_or_else(|| PyValueError::new_err(format!("unknown tag: {name}")))
}

fn value_to_py<'py>(py: Python<'py>, v: &Value) -> PyResult<Bound<'py, PyAny>> {
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

fn py_to_value(value: &Bound<'_, PyAny>, cip: CipType) -> PyResult<Value> {
    Ok(match cip {
        CipType::Bool => Value::Bool(value.extract::<bool>()?),
        CipType::Sint => Value::Sint(value.extract::<i32>()? as i8),
        CipType::Int => Value::Int(value.extract::<i32>()? as i16),
        CipType::Dint => Value::Dint(value.extract::<i32>()?),
        CipType::Real => Value::Real(value.extract::<f32>()?),
        CipType::RealArray2 => {
            let v: Vec<f32> = value.extract()?;
            if v.len() != 2 {
                return Err(PyValueError::new_err("REAL[2] requires 2 elements"));
            }
            Value::RealArray2([v[0], v[1]])
        }
        CipType::RealArray3 => {
            let v: Vec<f32> = value.extract()?;
            if v.len() != 3 {
                return Err(PyValueError::new_err("REAL[3] requires 3 elements"));
            }
            Value::RealArray3([v[0], v[1], v[2]])
        }
    })
}

fn source_str(s: Source) -> &'static str {
    match s {
        Source::Default => "default",
        Source::Plc => "plc",
        Source::WriteEcho => "write_echo",
        Source::Stale => "stale",
    }
}

fn stale_to_py(e: StaleReadError) -> PyErr {
    match e {
        StaleReadError::TimedOut { .. } => PyTimeoutError::new_err(e.to_string()),
        _ => PyRuntimeError::new_err(e.to_string()),
    }
}

fn write_to_py(e: WriteFailed) -> PyErr {
    match e {
        WriteFailed::TimedOut { .. } => PyTimeoutError::new_err(e.to_string()),
        _ => PyRuntimeError::new_err(e.to_string()),
    }
}

#[pyclass(name = "Snapshot", module = "dune_plc_bus")]
pub struct PySnapshot {
    #[pyo3(get)]
    pub value: Py<PyAny>,
    #[pyo3(get)]
    pub age_ms: f64,
    #[pyo3(get)]
    pub sequence: u64,
    #[pyo3(get)]
    pub source: String,
}

fn make_snapshot(py: Python<'_>, snap: crate::snapshot::Snapshot<Value>) -> PyResult<PySnapshot> {
    Ok(PySnapshot {
        value: value_to_py(py, &snap.value)?.unbind(),
        age_ms: snap.age().as_secs_f64() * 1000.0,
        sequence: snap.sequence,
        source: source_str(snap.source).to_string(),
    })
}

#[pyclass(name = "TagBus", module = "dune_plc_bus")]
pub struct PyTagBus {
    inner: Arc<TagBus>,
}

#[pymethods]
impl PyTagBus {
    /// Construct a bus over the in-process simulator. Convenience for tests
    /// and dev. Returns `(bus, driver_handle)` so the caller can `poke`.
    #[staticmethod]
    fn simulated() -> (Self, PySimulatedDriver) {
        let drv = SimulatedDriver::new();
        let bus = TagBus::with_tags(
            Box::new(drv.clone()) as Box<dyn PlcDriver>,
            BusConfig::default(),
            all_tags(),
        );
        (
            PyTagBus {
                inner: Arc::new(bus),
            },
            PySimulatedDriver { driver: drv },
        )
    }

    /// Construct a bus over a Python object that exposes `read(list[str]) ->
    /// dict[str, value]` and `write(list[(str, value)]) -> dict[str, bool]`.
    /// CIP types are resolved against the generated schema.
    #[staticmethod]
    fn from_python(py_obj: Py<PyAny>) -> Self {
        let resolver = Box::new(|name: &str| {
            tag_table().get(name).map(|t| t.cip)
        });
        let drv = PyCallbackDriver::new(py_obj, resolver);
        let bus = TagBus::with_tags(
            Box::new(drv) as Box<dyn PlcDriver>,
            BusConfig::default(),
            all_tags(),
        );
        PyTagBus {
            inner: Arc::new(bus),
        }
    }

    fn start(&self) {
        self.inner.start();
    }

    fn stop(&self) {
        self.inner.stop();
    }

    fn snapshot(&self, py: Python<'_>, name: &str) -> PyResult<Option<PySnapshot>> {
        let tag = resolve_tag(name)?;
        self.inner.register(tag);
        let Some(snap) = self.inner.snapshot_value(tag.name) else {
            return Ok(None);
        };
        Ok(Some(make_snapshot(py, snap)?))
    }

    #[pyo3(signature = (name, within_ms, timeout_ms = 250))]
    fn read_fresh(
        &self,
        py: Python<'_>,
        name: &str,
        within_ms: u64,
        timeout_ms: u64,
    ) -> PyResult<PySnapshot> {
        let tag = resolve_tag(name)?;
        self.inner.register(tag);
        let inner = self.inner.clone();
        let snap = py
            .detach(move || {
                inner.read_fresh_value(
                    tag.name,
                    Duration::from_millis(within_ms),
                    Duration::from_millis(timeout_ms),
                )
            })
            .map_err(stale_to_py)?;
        make_snapshot(py, snap)
    }

    /// Bulk fresh-read. Single driver round-trip. Returns dict[name, Snapshot|None].
    /// `None` is returned for any tag the driver did not respond with.
    fn read_many_fresh<'py>(
        &self,
        py: Python<'py>,
        names: Vec<String>,
    ) -> PyResult<Bound<'py, PyDict>> {
        let mut resolved: Vec<&'static str> = Vec::with_capacity(names.len());
        for n in &names {
            let tag = resolve_tag(n)?;
            self.inner.register(tag);
            resolved.push(tag.name);
        }
        let inner = self.inner.clone();
        let result = py.detach(move || inner.read_many_fresh(&resolved));
        let out = PyDict::new(py);
        for name in &names {
            let key: &str = name;
            // Look up by static-interned key.
            let static_name = tag_table().get(name).map(|t| t.name).unwrap();
            match result.get(&static_name) {
                Some(Ok(snap)) => {
                    out.set_item(key, make_snapshot(py, snap.clone())?)?;
                }
                Some(Err(_)) | None => {
                    out.set_item(key, py.None())?;
                }
            }
        }
        Ok(out)
    }

    #[pyo3(signature = (name, value, timeout_ms = 250))]
    fn write(
        &self,
        py: Python<'_>,
        name: &str,
        value: Bound<'_, PyAny>,
        timeout_ms: u64,
    ) -> PyResult<()> {
        let tag = resolve_tag(name)?;
        self.inner.register(tag);
        let v = py_to_value(&value, tag.cip)?;
        let inner = self.inner.clone();
        py.detach(move || {
            inner
                .write_value(tag.name, v, Duration::from_millis(timeout_ms))
        })
        .map(|_| ())
        .map_err(write_to_py)
    }

    #[pyo3(signature = (updates, timeout_ms = 250))]
    fn write_many(
        &self,
        py: Python<'_>,
        updates: &Bound<'_, PyDict>,
        timeout_ms: u64,
    ) -> PyResult<()> {
        let mut prepared: Vec<(ErasedTagId, Value)> = Vec::with_capacity(updates.len());
        for (k, v) in updates.iter() {
            let name: String = k.extract()?;
            let tag = resolve_tag(&name)?;
            self.inner.register(tag);
            prepared.push((tag, py_to_value(&v, tag.cip)?));
        }
        let inner = self.inner.clone();
        let result: HashMap<&'static str, Result<crate::WriteOutcome, WriteFailed>> =
            py.detach(move || inner.write_many(prepared, Duration::from_millis(timeout_ms)));
        for (_name, outcome) in result {
            outcome.map_err(write_to_py)?;
        }
        Ok(())
    }

    #[pyo3(signature = (name, max_age_ms))]
    fn subscribe(&self, name: &str, max_age_ms: u64) -> PyResult<()> {
        let tag = resolve_tag(name)?;
        self.inner.register(tag);
        // Phase A binding limitation: subscriptions need the typed Rust
        // handle. Fall back to a one-shot fetch. Typed Python wrappers in a
        // follow-up will call `subscribe` on the typed Rust API directly.
        let _ = max_age_ms;
        let _ = self.inner.snapshot_value(tag.name);
        Ok(())
    }

    fn metrics<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let m = self.inner.metrics();
        let d = PyDict::new(py);
        d.set_item("reads", m.reads())?;
        d.set_item("writes", m.writes())?;
        d.set_item("stale_errors", m.stale_errors())?;
        d.set_item("batches", m.batches())?;
        Ok(d)
    }

    fn health<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let h = self.inner.health();
        let d = PyDict::new(py);
        d.set_item("connected", h.connected)?;
        d.set_item("consecutive_failures", h.consecutive_failures)?;
        d.set_item("last_error", h.last_error)?;
        Ok(d)
    }
}

#[pyclass(name = "SimulatedDriver", module = "dune_plc_bus")]
pub struct PySimulatedDriver {
    driver: SimulatedDriver,
}

#[pymethods]
impl PySimulatedDriver {
    fn poke(&self, name: &str, value: Bound<'_, PyAny>) -> PyResult<()> {
        let tag = resolve_tag(name)?;
        let v = py_to_value(&value, tag.cip)?;
        self.driver.poke(name, v);
        Ok(())
    }

    fn peek<'py>(&self, py: Python<'py>, name: &str) -> PyResult<Option<Bound<'py, PyAny>>> {
        let _ = resolve_tag(name)?;
        match self.driver.peek(name) {
            None => Ok(None),
            Some(v) => Ok(Some(value_to_py(py, &v)?)),
        }
    }

    fn set_failed(&self, failed: bool) {
        self.driver.set_failed(failed);
    }

    fn read_calls(&self) -> u64 {
        self.driver.read_calls()
    }

    fn write_calls(&self) -> u64 {
        self.driver.write_calls()
    }
}

/// Returns a list of `(name, cip, tier)` for every tag in the generated schema.
#[pyfunction]
pub fn all_tag_descriptors<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
    let mut tuples: Vec<Bound<'py, PyTuple>> = Vec::with_capacity(all_tags().len());
    for t in all_tags() {
        let cip = match t.cip {
            CipType::Bool => "BOOL",
            CipType::Sint => "SINT",
            CipType::Int => "INT",
            CipType::Dint => "DINT",
            CipType::Real => "REAL",
            CipType::RealArray2 => "REAL[2]",
            CipType::RealArray3 => "REAL[3]",
        };
        let tier = match t.tier {
            Tier::Critical => "critical",
            Tier::High => "high",
            Tier::Normal => "normal",
            Tier::Slow => "slow",
            Tier::OnDemand => "on_demand",
        };
        tuples.push(PyTuple::new(py, [t.name, cip, tier])?);
    }
    PyList::new(py, tuples)
}

#[pymodule]
pub fn dune_plc_bus(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyTagBus>()?;
    m.add_class::<PySimulatedDriver>()?;
    m.add_class::<PySnapshot>()?;
    m.add_function(wrap_pyfunction!(all_tag_descriptors, m)?)?;
    Ok(())
}
