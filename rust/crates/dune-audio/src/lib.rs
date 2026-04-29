pub mod capture;
pub mod dsp;
pub mod pesto;

pub use capture::{acquire_audio, AudioAcquisitionConfig, HarmonicCombCaptureConfig, TriggerMode};
pub use dsp::{
    autocorrelation_has_peak_near, autocorrelation_pitch, discard_leading_audio, fft_has_peak_near,
    harmonic_comb_response, nn_pitch_is_corroborated, remove_clicks, rms, triangle_reference_rms,
    CombResponse,
};
pub use pesto::{analyze_pesto_onnx, PestoAnalysis, PestoOnnxConfig};
