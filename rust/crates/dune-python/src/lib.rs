use std::path::PathBuf;

use dune_audio::{
    acquire_audio as acquire_audio_core, analyze_pesto_onnx as analyze_pesto_onnx_core,
    autocorrelation_has_peak_near as autocorrelation_has_peak_near_core,
    autocorrelation_pitch as autocorrelation_pitch_core, discard_leading_audio as discard_core,
    fft_has_peak_near as fft_has_peak_near_core, harmonic_comb_response as harmonic_core,
    nn_pitch_is_corroborated as corroborated_core, remove_clicks as remove_clicks_core,
    rms as rms_core, triangle_reference_rms as triangle_reference_rms_core, AudioAcquisitionConfig,
    HarmonicCombCaptureConfig, PestoOnnxConfig, TriggerMode,
};
use numpy::{IntoPyArray, PyArray1, PyReadonlyArray1};
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyDict;

#[pyfunction]
fn backend_name() -> &'static str {
    "rust"
}

#[pyfunction]
fn capture_backend_available() -> bool {
    cfg!(feature = "cpal-capture")
}

#[pyfunction]
fn rms(audio: PyReadonlyArray1<'_, f32>) -> f64 {
    let audio = audio.as_slice().unwrap_or(&[]);
    rms_core(audio)
}

#[pyfunction]
fn triangle_reference_rms(
    sample_rate: usize,
    duration_seconds: f64,
    expected_frequency: Option<f64>,
) -> f64 {
    triangle_reference_rms_core(sample_rate, duration_seconds, expected_frequency)
}

#[pyfunction]
fn discard_leading_audio<'py>(
    py: Python<'py>,
    audio: PyReadonlyArray1<'py, f32>,
    sample_rate: usize,
    discard_seconds: f64,
) -> PyResult<Bound<'py, PyArray1<f32>>> {
    let output = discard_core(slice(&audio)?, sample_rate, discard_seconds);
    Ok(output.into_pyarray(py))
}

#[pyfunction]
fn remove_clicks<'py>(
    py: Python<'py>,
    audio: PyReadonlyArray1<'py, f32>,
    threshold_sigma: Option<f64>,
    max_click_fraction: Option<f64>,
) -> PyResult<Bound<'py, PyArray1<f32>>> {
    let output = remove_clicks_core(
        slice(&audio)?,
        threshold_sigma.unwrap_or(4.0),
        max_click_fraction.unwrap_or(0.1),
    );
    Ok(output.into_pyarray(py))
}

#[pyfunction]
fn harmonic_comb_response(
    frame: PyReadonlyArray1<'_, f32>,
    sample_rate: usize,
    window: PyReadonlyArray1<'_, f32>,
    candidates: PyReadonlyArray1<'_, f64>,
    weights: PyReadonlyArray1<'_, f64>,
    min_harmonics: usize,
) -> PyResult<(f64, f64, bool)> {
    let response = harmonic_core(
        slice(&frame)?,
        sample_rate,
        slice(&window)?,
        slice(&candidates)?,
        slice(&weights)?,
        min_harmonics,
    );
    Ok((response.score, response.spectral_flatness, response.valid))
}

#[pyfunction]
fn autocorrelation_pitch(
    audio: PyReadonlyArray1<'_, f32>,
    sample_rate: usize,
    f_min: Option<f64>,
    f_max: Option<f64>,
) -> PyResult<f64> {
    Ok(autocorrelation_pitch_core(
        slice(&audio)?,
        sample_rate,
        f_min.unwrap_or(30.0),
        f_max.unwrap_or(2000.0),
    ))
}

#[pyfunction]
fn autocorrelation_has_peak_near(
    audio: PyReadonlyArray1<'_, f32>,
    sample_rate: usize,
    frequency: f64,
    tolerance_ratio: Option<f64>,
    threshold_ratio: Option<f64>,
    f_min: Option<f64>,
    f_max: Option<f64>,
) -> PyResult<bool> {
    Ok(autocorrelation_has_peak_near_core(
        slice(&audio)?,
        sample_rate,
        frequency,
        tolerance_ratio.unwrap_or(0.15),
        threshold_ratio.unwrap_or(0.20),
        f_min.unwrap_or(30.0),
        f_max.unwrap_or(2000.0),
    ))
}

#[pyfunction]
fn fft_has_peak_near(
    audio: PyReadonlyArray1<'_, f32>,
    sample_rate: usize,
    frequency: f64,
    tolerance_ratio: Option<f64>,
    threshold_ratio: Option<f64>,
) -> PyResult<bool> {
    Ok(fft_has_peak_near_core(
        slice(&audio)?,
        sample_rate,
        frequency,
        tolerance_ratio.unwrap_or(0.10),
        threshold_ratio.unwrap_or(0.20),
    ))
}

#[pyfunction]
fn nn_pitch_is_corroborated(
    audio: PyReadonlyArray1<'_, f32>,
    sample_rate: usize,
    nn_frequency: f64,
    f_min: Option<f64>,
    f_max: Option<f64>,
    acf_tolerance_ratio: Option<f64>,
    fft_tolerance_ratio: Option<f64>,
    fft_threshold_ratio: Option<f64>,
    acf_peak_threshold_ratio: Option<f64>,
) -> PyResult<bool> {
    Ok(corroborated_core(
        slice(&audio)?,
        sample_rate,
        nn_frequency,
        f_min.unwrap_or(30.0),
        f_max.unwrap_or(2000.0),
        acf_tolerance_ratio.unwrap_or(0.15),
        fft_tolerance_ratio.unwrap_or(0.10),
        fft_threshold_ratio.unwrap_or(0.20),
        acf_peak_threshold_ratio.unwrap_or(0.20),
    ))
}

#[allow(clippy::too_many_arguments)]
#[pyfunction]
fn acquire_audio<'py>(
    py: Python<'py>,
    sample_rate: usize,
    max_record_seconds: f64,
    expected_f0: Option<f64>,
    snr_threshold_db: f64,
    trigger_mode: &str,
    idle_timeout: Option<f64>,
    noise_rms: f64,
    timeout: Option<f64>,
    comb_frame_size: Option<usize>,
    comb_hop_size: Option<usize>,
    comb_candidate_count: Option<usize>,
    comb_harmonic_weight_count: Option<usize>,
    comb_min_harmonics: Option<usize>,
    comb_on_score: Option<f64>,
    comb_off_score: Option<f64>,
    comb_spectral_flatness_max: Option<f64>,
    comb_on_frames: Option<usize>,
    comb_off_frames: Option<usize>,
) -> PyResult<Option<Bound<'py, PyArray1<f32>>>> {
    let trigger_mode = match trigger_mode {
        "snr" | "rms" => TriggerMode::Snr,
        "harmonic_comb" | "harmonic" | "harmonic-comb" => TriggerMode::HarmonicComb,
        other => {
            return Err(PyValueError::new_err(format!(
                "unknown trigger mode: {other}"
            )))
        }
    };
    let default_comb = HarmonicCombCaptureConfig::default();
    let cfg = AudioAcquisitionConfig {
        sample_rate,
        max_record_seconds,
        expected_f0,
        snr_threshold_db,
        trigger_mode,
        idle_timeout_seconds: idle_timeout.unwrap_or(0.2),
        discard_seconds: 0.05,
        comb: HarmonicCombCaptureConfig {
            frame_size: comb_frame_size.unwrap_or(default_comb.frame_size),
            hop_size: comb_hop_size.unwrap_or(default_comb.hop_size),
            candidate_count: comb_candidate_count.unwrap_or(default_comb.candidate_count),
            harmonic_weight_count: comb_harmonic_weight_count
                .unwrap_or(default_comb.harmonic_weight_count),
            min_harmonics: comb_min_harmonics.unwrap_or(default_comb.min_harmonics),
            on_score: comb_on_score.unwrap_or(default_comb.on_score),
            off_score: comb_off_score.unwrap_or(default_comb.off_score),
            spectral_flatness_max: comb_spectral_flatness_max
                .unwrap_or(default_comb.spectral_flatness_max),
            on_frames: comb_on_frames.unwrap_or(default_comb.on_frames),
            off_frames: comb_off_frames.unwrap_or(default_comb.off_frames),
            ..default_comb
        },
    };
    acquire_audio_core(&cfg, noise_rms, timeout)
        .map(|maybe_audio| maybe_audio.map(|audio| audio.into_pyarray(py)))
        .map_err(runtime_error)
}

#[pyfunction]
fn analyze_pesto_onnx<'py>(
    py: Python<'py>,
    audio: PyReadonlyArray1<'py, f32>,
    sample_rate: usize,
    expected_frequency: Option<f64>,
    include_activations: bool,
    encoder_path: String,
    confidence_path: String,
    manifest_path: Option<String>,
) -> PyResult<Py<PyDict>> {
    let config = PestoOnnxConfig {
        encoder_path: PathBuf::from(encoder_path),
        confidence_path: PathBuf::from(confidence_path),
        manifest_path: manifest_path.map(PathBuf::from),
        sample_rate,
        expected_frequency,
        include_activations,
    };
    let result = analyze_pesto_onnx_core(&config, slice(&audio)?).map_err(runtime_error)?;
    let dict = PyDict::new(py);
    dict.set_item("frequency", result.frequency)?;
    dict.set_item("confidence", result.confidence)?;
    dict.set_item("expected_frequency", result.expected_frequency)?;
    dict.set_item("frame_times", result.frame_times.into_pyarray(py))?;
    dict.set_item(
        "predicted_frequencies",
        result.predicted_frequencies.into_pyarray(py),
    )?;
    dict.set_item(
        "frame_confidences",
        result.frame_confidences.into_pyarray(py),
    )?;
    match result.activation_map {
        Some(values) => {
            dict.set_item("activation_map", values.into_pyarray(py))?;
            dict.set_item("activation_map_shape", result.activation_map_shape)?;
        }
        None => {
            dict.set_item("activation_map", py.None())?;
            dict.set_item("activation_map_shape", py.None())?;
        }
    }
    match result.activation_freq_axis {
        Some(values) => dict.set_item("activation_freq_axis", values.into_pyarray(py))?,
        None => dict.set_item("activation_freq_axis", py.None())?,
    }
    Ok(dict.unbind())
}

#[pymodule]
fn _rust_audio(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(backend_name, m)?)?;
    m.add_function(wrap_pyfunction!(capture_backend_available, m)?)?;
    m.add_function(wrap_pyfunction!(rms, m)?)?;
    m.add_function(wrap_pyfunction!(triangle_reference_rms, m)?)?;
    m.add_function(wrap_pyfunction!(discard_leading_audio, m)?)?;
    m.add_function(wrap_pyfunction!(remove_clicks, m)?)?;
    m.add_function(wrap_pyfunction!(harmonic_comb_response, m)?)?;
    m.add_function(wrap_pyfunction!(autocorrelation_pitch, m)?)?;
    m.add_function(wrap_pyfunction!(autocorrelation_has_peak_near, m)?)?;
    m.add_function(wrap_pyfunction!(fft_has_peak_near, m)?)?;
    m.add_function(wrap_pyfunction!(nn_pitch_is_corroborated, m)?)?;
    m.add_function(wrap_pyfunction!(acquire_audio, m)?)?;
    m.add_function(wrap_pyfunction!(analyze_pesto_onnx, m)?)?;
    Ok(())
}

fn slice<'py, T: numpy::Element>(array: &'py PyReadonlyArray1<'py, T>) -> PyResult<&'py [T]> {
    array
        .as_slice()
        .map_err(|_| PyValueError::new_err("expected a contiguous one-dimensional array"))
}

fn runtime_error(err: anyhow::Error) -> PyErr {
    PyRuntimeError::new_err(err.to_string())
}
