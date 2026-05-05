pub mod models;
pub mod planner;

use pyo3::prelude::*;
use pyo3::types::PyDict;
use numpy::ToPyArray;
use crate::motion::MotionController;
use crate::config::TensiometerConfig;
use crate::utils::check_stop_event;
use planner::WirePositionProvider;
use dune_audio::capture::{acquire_audio, AudioAcquisitionConfig, TriggerMode};
use dune_audio::dsp::HarmonicCombCaptureConfig;
use rand::prelude::*;
use rand_distr::Normal;

pub struct MeasurementOrchestrator {
    pub motion: MotionController,
    pub config: TensiometerConfig,
    pub py_config: Py<PyAny>,
    pub stop_event: Option<Py<PyAny>>,
    pub repository: Py<PyAny>,
    pub audio_service: Py<PyAny>,
    pub strum_func: Py<PyAny>,
    pub pesto_func: Py<PyAny>,
    pub harmonic_comb_config: Option<Py<PyAny>>,
    pub planner: WirePositionProvider,
}

impl MeasurementOrchestrator {
    pub fn new(
        motion: MotionController, 
        config: TensiometerConfig, 
        py_config: Py<PyAny>, 
        stop_event: Option<Py<PyAny>>,
        repository: Py<PyAny>,
        audio_service: Py<PyAny>,
        strum_func: Py<PyAny>,
        pesto_func: Py<PyAny>,
        harmonic_comb_config: Option<Py<PyAny>>,
    ) -> Self {
        MeasurementOrchestrator { 
            motion, 
            config, 
            py_config, 
            stop_event, 
            repository, 
            audio_service,
            strum_func,
            pesto_func,
            harmonic_comb_config,
            planner: WirePositionProvider::new(),
        }
    }

    fn get_samplerate(&self, py: Python<'_>) -> PyResult<usize> {
        self.audio_service.getattr(py, "samplerate")?.extract(py)
    }

    fn get_noise_threshold(&self, py: Python<'_>) -> PyResult<f64> {
        self.audio_service.getattr(py, "noise_threshold")?.extract(py)
    }

    pub fn measure_auto(&self, py: Python<'_>) -> PyResult<()> {
        println!("Rust Orchestrator: measure_auto starting");
        
        let summaries = py.import("dune_tension.summaries")?;
        let get_missing_wires = summaries.getattr("get_missing_wires")?;
        let wires_dict_obj = get_missing_wires.call1((self.py_config.clone_ref(py),))?;
        let wires_dict = wires_dict_obj.downcast::<PyDict>().map_err(|_| pyo3::exceptions::PyTypeError::new_err("Expected dict"))?;
        
        let side_key = self.config.side.clone();
        let wires_to_measure: Vec<i32> = match wires_dict.get_item(side_key)? {
            Some(wires) => wires.extract()?,
            None => {
                println!("All wires are already measured.");
                return Ok(());
            }
        };

        if wires_to_measure.is_empty() {
            println!("All wires are already measured.");
            return Ok(());
        }

        let run_scope = self.repository.call_method0(py, "run_scope")?;
        let _scope_obj = run_scope.call_method0(py, "__enter__")?;

        for wire_number in wires_to_measure {
            if check_stop_event(py, &self.stop_event) {
                let _ = run_scope.call_method1(py, "__exit__", (py.None(), py.None(), py.None()))?;
                return Ok(());
            }

            println!("Measuring wire {}", wire_number);
            
            let focus = self.motion.get_focus_position(py)?;
            let target = self.planner.get_pose(&self.config, wire_number, Some(focus));
            
            if let Some(t) = target {
                let result = self.collect_samples(py, t.wire_number, t.x, t.y, t.focus_position, t.zone)?;
                if let Some(r) = result {
                    let _ = self.repository.call_method1(py, "append_result", (r,))?;
                }
            }
        }

        let _ = run_scope.call_method1(py, "__exit__", (py.None(), py.None(), py.None()))?;
        Ok(())
    }

    pub fn collect_samples(
        &self, 
        py: Python<'_>, 
        wire_number: i32, 
        wire_x: f64, 
        wire_y: f64, 
        focus_position: Option<i32>,
        zone: Option<i32>,
    ) -> PyResult<Option<Py<PyAny>>> {
        let sample_rate = self.get_samplerate(py)?;
        let noise_threshold = self.get_noise_threshold(py)?;
        
        // Simplified expected frequency calculation for now
        let expected_frequency = 600.0; 

        let mut comb_cfg = HarmonicCombCaptureConfig::default();
        if let Some(ref py_comb) = self.harmonic_comb_config {
            comb_cfg.on_score = py_comb.getattr(py, "on_rmax")?.extract(py)?;
            comb_cfg.off_score = py_comb.getattr(py, "off_rmax")?.extract(py)?;
            comb_cfg.spectral_flatness_max = py_comb.getattr(py, "sfm_max")?.extract(py)?;
        }

        let acq_cfg = AudioAcquisitionConfig {
            sample_rate,
            max_record_seconds: self.config.record_duration,
            expected_f0: Some(expected_frequency),
            snr_threshold_db: 1.0, // Assuming 1.0 for now
            trigger_mode: TriggerMode::Snr,
            idle_timeout_seconds: 0.2,
            discard_seconds: 0.05,
            comb: comb_cfg,
        };

        let mut best_confidence = -1.0;
        let mut best_sample: Option<Py<PyAny>> = None;
        let mut current_x = wire_x;
        let mut current_y = wire_y;
        let mut current_focus = focus_position.unwrap_or(6000);

        let start_time = std::time::Instant::now();
        let timeout = std::time::Duration::from_secs_f64(self.config.measuring_duration);

        let mut rng = thread_rng();
        let mut axis_index = 0;

        while start_time.elapsed() < timeout {
            if check_stop_event(py, &self.stop_event) {
                return Ok(None);
            }

            self.motion.move_to_measurement_pose(py, current_x, current_y, Some(current_focus))?;
            
            // Strum
            self.strum_func.call0(py)?;
            
            // Acquire audio (Rust)
            let audio_opt = acquire_audio(&acq_cfg, noise_threshold / 3.0, Some(self.config.record_duration))
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

            if let Some(audio_vec) = audio_opt {
                let audio_np = audio_vec.to_pyarray(py);
                
                // Call PESTO (Python)
                let analysis = self.pesto_func.call1(py, (audio_np, sample_rate, expected_frequency))?;
                let confidence: f64 = analysis.getattr(py, "confidence")?.extract(py)?;
                let frequency: f64 = analysis.getattr(py, "frequency")?.extract(py)?;

                println!("Wire {}: freq={:.2}, conf={:.2}", wire_number, frequency, confidence);

                if confidence > best_confidence {
                    best_confidence = confidence;
                    
                    let results_mod = py.import("dune_tension.results")?;
                    let tension_result_cls = results_mod.getattr("TensionResult")?;
                    
                    let kwargs = PyDict::new(py);
                    kwargs.set_item("apa_name", &self.config.apa_name)?;
                    kwargs.set_item("layer", &self.config.layer)?;
                    kwargs.set_item("side", &self.config.side)?;
                    kwargs.set_item("wire_number", wire_number)?;
                    kwargs.set_item("frequency", frequency)?;
                    kwargs.set_item("confidence", confidence)?;
                    kwargs.set_item("x", current_x)?;
                    kwargs.set_item("y", current_y)?;
                    kwargs.set_item("focus_position", current_focus)?;
                    kwargs.set_item("zone", zone)?;

                    best_sample = Some(tension_result_cls.call_method("from_measurement", (), Some(&kwargs))?.unbind());
                }

                if confidence >= self.config.confidence_threshold {
                    return Ok(best_sample);
                }
            }

            // Wiggle
            let x_sigma = 0.5; // Placeholder
            let y_sigma = 0.2; // Placeholder
            if axis_index == 0 {
                current_x = Normal::new(wire_x, x_sigma).unwrap().sample(&mut rng);
                axis_index = 1;
            } else {
                current_y = Normal::new(wire_y, y_sigma).unwrap().sample(&mut rng);
                axis_index = 0;
            }
        }

        Ok(best_sample)
    }
}
