mod motion;
mod geometry;
mod config;
mod orchestrator;
mod utils;

use pyo3::prelude::*;
use motion::MotionController;
use geometry::Geometry;
use config::TensiometerConfig;
use orchestrator::MeasurementOrchestrator;

#[pyclass]
struct Tensiometer {
    motion: Option<MotionController>,
    geometry: Geometry,
    config: Option<TensiometerConfig>,
    py_config: Option<Py<PyAny>>,
    stop_event: Option<Py<PyAny>>,
    orchestrator: Option<MeasurementOrchestrator>,
}

#[pymethods]
impl Tensiometer {
    #[new]
    #[pyo3(signature = (
        config=None, 
        motion_service=None, 
        goto_xy_func=None, 
        get_current_xy_position=None, 
        focus_wiggle_func=None, 
        focus_position_getter=None, 
        focus_range_getter=None, 
        use_manual_focus=false, 
        manual_focus_target=None, 
        stop_event=None, 
        repository=None, 
        audio_service=None,
        strum_func=None,
        pesto_func=None,
        harmonic_comb_config=None
    ))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        py: Python<'_>,
        config: Option<Py<PyAny>>,
        motion_service: Option<Py<PyAny>>,
        goto_xy_func: Option<Py<PyAny>>,
        get_current_xy_position: Option<Py<PyAny>>,
        focus_wiggle_func: Option<Py<PyAny>>,
        focus_position_getter: Option<Py<PyAny>>,
        focus_range_getter: Option<Py<PyAny>>,
        use_manual_focus: bool,
        manual_focus_target: Option<i32>,
        stop_event: Option<Py<PyAny>>,
        repository: Option<Py<PyAny>>,
        audio_service: Option<Py<PyAny>>,
        strum_func: Option<Py<PyAny>>,
        pesto_func: Option<Py<PyAny>>,
        harmonic_comb_config: Option<Py<PyAny>>,
    ) -> PyResult<Self> {
        let rust_config = if let Some(ref cfg) = config {
            Some(TensiometerConfig::from_py(py, cfg.clone_ref(py))?)
        } else {
            None
        };

        let layer = rust_config.as_ref().map(|c| c.layer.clone()).unwrap_or_else(|| "U".to_string());

        let motion = if let (Some(ms), Some(gxy), Some(gcxy), Some(fwf), Some(fpg), Some(frg)) = 
            (motion_service, goto_xy_func, get_current_xy_position, focus_wiggle_func, focus_position_getter, focus_range_getter) 
        {
            Some(MotionController::new(ms, gxy, gcxy, fwf, fpg, frg, use_manual_focus, manual_focus_target, layer))
        } else {
            None
        };

        let orchestrator = if let (Some(ref m), Some(ref c), Some(ref py_c), Some(ref repo), Some(ref audio), Some(ref strum), Some(ref pesto)) = 
            (motion.as_ref(), rust_config.as_ref(), config.as_ref(), repository.as_ref(), audio_service.as_ref(), strum_func.as_ref(), pesto_func.as_ref()) 
        {
            Some(MeasurementOrchestrator::new(
                m.clone_with_gil(py), 
                (*c).clone(), 
                py_c.clone_ref(py), 
                stop_event.as_ref().map(|e| e.clone_ref(py)), 
                repo.clone_ref(py), 
                audio.clone_ref(py),
                strum.clone_ref(py),
                pesto.clone_ref(py),
                harmonic_comb_config.as_ref().map(|c| c.clone_ref(py)),
            ))
        } else {
            None
        };

        Ok(Tensiometer {
            motion,
            geometry: Geometry::new(),
            config: rust_config,
            py_config: config,
            stop_event,
            orchestrator,
        })
    }

    fn measure_auto(&self, py: Python<'_>) -> PyResult<()> {
        if let Some(ref o) = self.orchestrator {
            o.measure_auto(py)
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err("Tensiometer not fully initialized for measurement"))
        }
    }

    fn get_focus_position(&self, py: Python<'_>) -> PyResult<i32> {
        if let Some(ref m) = self.motion {
            m.get_focus_position(py)
        } else {
            Ok(0)
        }
    }

    fn refine_position(&self, x: f64, y: f64, dx: f64, dy: f64) -> (f64, f64) {
        self.geometry.refine_position(x, y, dx, dy)
    }

    fn zone_lookup(&self, x: f64) -> i32 {
        self.geometry.zone_lookup(x)
    }

    fn move_to_measurement_pose(&self, py: Python<'_>, x: f64, y: f64, focus: Option<i32>) -> PyResult<bool> {
        if let Some(ref m) = self.motion {
            m.move_to_measurement_pose(py, x, y, focus)
        } else {
            Ok(false)
        }
    }
}

#[pymodule]
fn dune_tension_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Tensiometer>()?;
    Ok(())
}
