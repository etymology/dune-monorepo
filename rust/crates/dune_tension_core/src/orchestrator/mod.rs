pub mod models;
pub mod planner;

use pyo3::prelude::*;
use pyo3::exceptions::PyRuntimeError;
use pyo3::types::PyDict;
use numpy::ToPyArray;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;
use crate::motion::MotionController;
use crate::config::TensiometerConfig;
use crate::utils::check_stop_event;
use planner::PlannedWirePose;
use dune_audio::capture::{acquire_audio, AudioAcquisitionConfig, TriggerMode};
use dune_audio::dsp::HarmonicCombCaptureConfig;
use rand::prelude::*;
use rand_distr::Normal;

/// Interval between strums while waiting for the audio trigger to fire.
const STRUM_LOOP_INTERVAL: Duration = Duration::from_millis(200);

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
    pub a_taped: bool,
    pub b_taped: bool,
}

impl MeasurementOrchestrator {
    #[allow(clippy::too_many_arguments)]
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
        a_taped: bool,
        b_taped: bool,
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
            a_taped,
            b_taped,
        }
    }

    /// Whether the wire on the side currently being measured is taped.
    fn current_side_taped(&self) -> bool {
        match self.config.side.to_uppercase().as_str() {
            "A" => self.a_taped,
            "B" => self.b_taped,
            _ => false,
        }
    }

    /// Plan a measurement pose for `wire_number` using the Python U/V planner.
    ///
    /// Returns `None` for non-U/V layers (those run through the Python
    /// measure_list path) or when the planner cannot place the wire.
    fn plan_wire_pose(
        &self,
        py: Python<'_>,
        wire_number: i32,
        focus: i32,
    ) -> PyResult<Option<PlannedWirePose>> {
        let layer = self.config.layer.to_uppercase();
        if layer != "U" && layer != "V" {
            return Ok(None);
        }

        let kwargs = PyDict::new(py);
        kwargs.set_item("taped", self.current_side_taped())?;
        let planned = match py
            .import("dune_tension.uv_wire_planner")?
            .getattr("plan_uv_wire")?
            .call((&layer, &self.config.side, wire_number), Some(&kwargs))
        {
            Ok(planned) => planned,
            Err(err) => {
                eprintln!("U/V planner failed for wire {wire_number}: {err}");
                return Ok(None);
            }
        };

        let midpoint = planned.getattr("midpoint")?;
        let x: f64 = midpoint.get_item(0)?.extract()?;
        let y: f64 = midpoint.get_item(1)?.extract()?;
        let zone: i32 = planned.getattr("zone")?.extract()?;

        Ok(Some(PlannedWirePose {
            wire_number,
            x,
            y,
            focus_position: Some(focus),
            zone: Some(zone),
        }))
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
            let target = self.plan_wire_pose(py, wire_number, focus)?;

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
        let taped = self.current_side_taped();

        // Expected resonant frequency for the wire, used by the harmonic-comb
        // trigger and the pitch analyzer. Falls back to None (SNR trigger) when
        // the length lookup is unavailable.
        let expected_frequency = self.compute_expected_frequency(py, wire_number, zone, taped);

        let mut comb_cfg = HarmonicCombCaptureConfig::default();
        let mut use_harmonic_comb = false;
        if let Some(ref py_comb) = self.harmonic_comb_config {
            comb_cfg = harmonic_comb_from_py(py, py_comb);
            use_harmonic_comb = true;
        }

        let trigger_mode = if use_harmonic_comb && expected_frequency.is_some() {
            TriggerMode::HarmonicComb
        } else {
            TriggerMode::Snr
        };

        let acq_cfg = AudioAcquisitionConfig {
            sample_rate,
            max_record_seconds: self.config.record_duration,
            expected_f0: expected_frequency,
            snr_threshold_db: 1.0,
            trigger_mode,
            idle_timeout_seconds: 0.2,
            discard_seconds: 0.05,
            comb: comb_cfg,
        };

        let noise_rms = noise_threshold / 3.0;
        let acquire_timeout = Some(self.config.record_duration);

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

            // Acquire audio on a background thread while strumming the wire on
            // a fixed interval. Strumming stops as soon as the recording
            // trigger fires, so the captured decay is not contaminated by
            // further strum impacts (mirrors the Python collect-samples loop).
            let recording_started = Arc::new(AtomicBool::new(false));
            let audio_handle = {
                let cfg = acq_cfg.clone();
                let flag = Arc::clone(&recording_started);
                std::thread::spawn(move || {
                    acquire_audio(&cfg, noise_rms, acquire_timeout, Some(flag.as_ref()))
                })
            };

            while !recording_started.load(Ordering::Relaxed) && !audio_handle.is_finished() {
                self.strum_func.call0(py)?;
                py.detach(|| std::thread::sleep(STRUM_LOOP_INTERVAL));
            }

            let audio_opt = audio_handle
                .join()
                .map_err(|_| PyRuntimeError::new_err("audio capture thread panicked"))?
                .map_err(|e| PyRuntimeError::new_err(e.to_string()))?;

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
                    
                    let now = py
                        .import("datetime")?
                        .getattr("datetime")?
                        .call_method0("now")?;

                    let kwargs = PyDict::new(py);
                    kwargs.set_item("apa_name", &self.config.apa_name)?;
                    kwargs.set_item("layer", &self.config.layer)?;
                    kwargs.set_item("side", &self.config.side)?;
                    kwargs.set_item("wire_number", wire_number)?;
                    kwargs.set_item("frequency", frequency)?;
                    kwargs.set_item("confidence", confidence)?;
                    kwargs.set_item("x", current_x)?;
                    kwargs.set_item("y", current_y)?;
                    kwargs.set_item("time", now)?;
                    kwargs.set_item("focus_position", current_focus)?;
                    kwargs.set_item("zone", zone)?;
                    kwargs.set_item("taped", taped)?;

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

    /// Resonant frequency for `wire_number` derived from the wire-length lookup,
    /// or `None` when the length is unavailable (then the SNR trigger is used).
    fn compute_expected_frequency(
        &self,
        py: Python<'_>,
        wire_number: i32,
        zone: Option<i32>,
        taped: bool,
    ) -> Option<f64> {
        let zone = zone?;
        let result = (|| -> PyResult<f64> {
            let length: f64 = py
                .import("dune_tension.geometry")?
                .getattr("length_lookup")?
                .call1((&self.config.layer, wire_number, zone, taped))?
                .extract()?;
            py.import("dune_tension.tension_calculation")?
                .getattr("wire_equation")?
                .call1((length,))?
                .get_item("frequency")?
                .extract()
        })();
        match result {
            Ok(freq) if freq.is_finite() && freq > 0.0 => Some(freq),
            Ok(_) => None,
            Err(err) => {
                eprintln!("expected-frequency lookup failed for wire {wire_number}: {err}");
                None
            }
        }
    }
}

/// Build a Rust harmonic-comb capture config from the Python `HarmonicCombConfig`,
/// falling back to the Rust defaults for any attribute that is missing.
fn harmonic_comb_from_py(py: Python<'_>, py_comb: &Py<PyAny>) -> HarmonicCombCaptureConfig {
    let mut cfg = HarmonicCombCaptureConfig::default();
    if let Ok(v) = py_comb.getattr(py, "frame_size").and_then(|a| a.extract(py)) {
        cfg.frame_size = v;
    }
    if let Ok(v) = py_comb.getattr(py, "hop_size").and_then(|a| a.extract(py)) {
        cfg.hop_size = v;
    }
    if let Ok(v) = py_comb.getattr(py, "candidate_count").and_then(|a| a.extract(py)) {
        cfg.candidate_count = v;
    }
    if let Ok(v) = py_comb
        .getattr(py, "harmonic_weight_count")
        .and_then(|a| a.extract(py))
    {
        cfg.harmonic_weight_count = v;
    }
    if let Ok(v) = py_comb.getattr(py, "min_harmonics").and_then(|a| a.extract(py)) {
        cfg.min_harmonics = v;
    }
    if let Ok(v) = py_comb.getattr(py, "on_rmax").and_then(|a| a.extract(py)) {
        cfg.on_score = v;
    }
    if let Ok(v) = py_comb.getattr(py, "off_rmax").and_then(|a| a.extract(py)) {
        cfg.off_score = v;
    }
    if let Ok(v) = py_comb.getattr(py, "sfm_max").and_then(|a| a.extract(py)) {
        cfg.spectral_flatness_max = v;
    }
    if let Ok(v) = py_comb.getattr(py, "on_frames").and_then(|a| a.extract(py)) {
        cfg.on_frames = v;
    }
    if let Ok(v) = py_comb.getattr(py, "off_frames").and_then(|a| a.extract(py)) {
        cfg.off_frames = v;
    }
    if let Ok(v) = py_comb
        .getattr(py, "harmonicity_floor_multiplier")
        .and_then(|a| a.extract(py))
    {
        cfg.harmonicity_floor_multiplier = v;
    }
    if let Ok(v) = py_comb
        .getattr(py, "harmonicity_floor_margin")
        .and_then(|a| a.extract(py))
    {
        cfg.harmonicity_floor_margin = v;
    }
    cfg
}
