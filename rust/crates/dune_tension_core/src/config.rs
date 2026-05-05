use pyo3::prelude::*;

#[derive(Clone)]
pub struct TensiometerConfig {
    pub apa_name: String,
    pub layer: String,
    pub side: String,
    pub dx: f64,
    pub dy: f64,
    pub wire_min: i32,
    pub wire_max: i32,
    pub flipped: bool,
    pub samples_per_wire: i32,
    pub confidence_threshold: f64,
    pub confidence_source: String,
    pub save_audio: bool,
    pub spoof: bool,
    pub plot_audio: bool,
    pub record_duration: f64,
    pub measuring_duration: f64,
    pub data_path: String,
}

impl TensiometerConfig {
    pub fn from_py(py: Python<'_>, config: Py<PyAny>) -> PyResult<Self> {
        let apa_name = config.getattr(py, "apa_name")?.extract::<String>(py)?;
        let layer = config.getattr(py, "layer")?.extract::<String>(py)?;
        let side = config.getattr(py, "side")?.extract::<String>(py)?;
        let dx = config.getattr(py, "dx")?.extract::<f64>(py)?;
        let dy = config.getattr(py, "dy")?.extract::<f64>(py)?;
        let wire_min = config.getattr(py, "wire_min")?.extract::<i32>(py)?;
        let wire_max = config.getattr(py, "wire_max")?.extract::<i32>(py)?;
        let flipped = config.getattr(py, "flipped")?.extract::<bool>(py)?;
        let samples_per_wire = config.getattr(py, "samples_per_wire")?.extract::<i32>(py)?;
        let confidence_threshold = config
            .getattr(py, "confidence_threshold")?
            .extract::<f64>(py)?;
        let confidence_source = config
            .getattr(py, "confidence_source")?
            .extract::<String>(py)?;
        let save_audio = config.getattr(py, "save_audio")?.extract::<bool>(py)?;
        let spoof = config.getattr(py, "spoof")?.extract::<bool>(py)?;
        let plot_audio = config.getattr(py, "plot_audio")?.extract::<bool>(py)?;
        let record_duration = config.getattr(py, "record_duration")?.extract::<f64>(py)?;
        let measuring_duration = config
            .getattr(py, "measuring_duration")?
            .extract::<f64>(py)?;
        let data_path = config.getattr(py, "data_path")?.extract::<String>(py)?;

        Ok(TensiometerConfig {
            apa_name,
            layer,
            side,
            dx,
            dy,
            wire_min,
            wire_max,
            flipped,
            samples_per_wire,
            confidence_threshold,
            confidence_source,
            save_audio,
            spoof,
            plot_audio,
            record_duration,
            measuring_duration,
            data_path,
        })
    }
}
