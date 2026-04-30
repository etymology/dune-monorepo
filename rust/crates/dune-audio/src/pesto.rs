use std::collections::HashMap;
use std::f64::consts::PI;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{LazyLock, Mutex};

use anyhow::{anyhow, Context, Result};
use ndarray::{Array2, Array3};
use ort::session::{builder::GraphOptimizationLevel, Session};
use ort::value::TensorRef;
use serde::{Deserialize, Serialize};

const DEFAULT_STEP_SIZE_MS: f64 = 5.0;
const DEFAULT_IDEAL_PITCH_HZ: f64 = 600.0;

static MODEL_CACHE: LazyLock<Mutex<HashMap<String, PestoOnnxModel>>> =
    LazyLock::new(|| Mutex::new(HashMap::new()));

#[derive(Debug, Clone)]
pub struct PestoOnnxConfig {
    pub encoder_path: PathBuf,
    pub confidence_path: PathBuf,
    pub manifest_path: Option<PathBuf>,
    pub sample_rate: usize,
    pub expected_frequency: Option<f64>,
    pub include_activations: bool,
}

#[derive(Debug, Clone)]
pub struct PestoAnalysis {
    pub frequency: f64,
    pub confidence: f64,
    pub expected_frequency: Option<f64>,
    pub frame_times: Vec<f32>,
    pub predicted_frequencies: Vec<f32>,
    pub frame_confidences: Vec<f32>,
    pub activation_map: Option<Vec<f32>>,
    pub activation_map_shape: Option<(usize, usize)>,
    pub activation_freq_axis: Option<Vec<f32>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PestoModelManifest {
    pub model_name: String,
    pub encoder_sha256: Option<String>,
    pub confidence_sha256: Option<String>,
    pub hparams: PestoHparams,
    pub onnx: Option<PestoOnnxIo>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PestoOnnxIo {
    pub encoder_input: String,
    pub encoder_output: String,
    pub confidence_input: String,
    pub confidence_output: String,
    pub opset_version: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PestoHparams {
    pub step_size_ms: f64,
    pub harmonics: Vec<f64>,
    pub fmin: f64,
    pub fmax: Option<f64>,
    pub bins_per_semitone: usize,
    pub n_bins: usize,
    pub center_bins: bool,
    pub gamma: f64,
    pub center: bool,
    pub crop_min_steps: isize,
    pub crop_max_steps: isize,
    pub shift: f64,
    pub output_dim: usize,
}

impl Default for PestoHparams {
    fn default() -> Self {
        Self {
            step_size_ms: DEFAULT_STEP_SIZE_MS,
            harmonics: vec![1.0],
            fmin: 27.5,
            fmax: None,
            bins_per_semitone: 3,
            n_bins: 251,
            center_bins: true,
            gamma: 7.0,
            center: true,
            crop_min_steps: -16,
            crop_max_steps: 16,
            shift: 6.677_955_627_441_406,
            output_dim: 384,
        }
    }
}

impl Default for PestoOnnxIo {
    fn default() -> Self {
        Self {
            encoder_input: "hcqt_features".to_string(),
            encoder_output: "activations".to_string(),
            confidence_input: "energy".to_string(),
            confidence_output: "confidence".to_string(),
            opset_version: 17,
        }
    }
}

pub fn analyze_pesto_onnx(config: &PestoOnnxConfig, audio: &[f32]) -> Result<PestoAnalysis> {
    if config.sample_rate == 0 {
        return Err(anyhow!("sample_rate must be positive"));
    }
    if audio.is_empty() {
        return Ok(empty_analysis(config.expected_frequency));
    }

    let manifest = load_manifest(config.manifest_path.as_deref())?;
    let io = manifest
        .as_ref()
        .and_then(|manifest| manifest.onnx.clone())
        .unwrap_or_default();
    let hparams = manifest
        .map(|manifest| manifest.hparams)
        .unwrap_or_else(PestoHparams::default);

    let sr_augment_factor = sr_augment_factor(config.expected_frequency);
    let augmented_sample_rate = (config.sample_rate as f64 * sr_augment_factor)
        .round()
        .max(1.0) as usize;
    let step_size_ms = hparams.step_size_ms.max(1.0);
    let original_sample_count = audio.len();
    let audio = pad_short_audio(audio, &hparams, augmented_sample_rate);

    let key = format!(
        "{}|{}|{}",
        config.encoder_path.display(),
        config.confidence_path.display(),
        hparams.step_size_ms
    );
    let mut cache = MODEL_CACHE
        .lock()
        .map_err(|_| anyhow!("pesto ONNX model cache lock poisoned"))?;
    if !cache.contains_key(&key) {
        let model = PestoOnnxModel::load(&config.encoder_path, &config.confidence_path, &io)?;
        cache.insert(key.clone(), model);
    }
    let model = cache
        .get_mut(&key)
        .ok_or_else(|| anyhow!("failed to load pesto ONNX model"))?;

    let features = compute_hcqt_log_features(&audio, augmented_sample_rate, &hparams)?;
    let energy = compute_confidence_energy(&features)?;
    let cropped = crop_features(&features, &hparams)?;

    let confidence_values = model.run_confidence(&energy)?;
    let mut activations = model.run_encoder(&cropped)?;
    apply_activation_shift(&mut activations, &hparams);

    let mut predicted_frequencies =
        reduce_activations_alwa(&activations, hparams.bins_per_semitone)
            .into_iter()
            .map(|pitch| 440.0 * 2.0_f32.powf((pitch - 69.0) / 12.0))
            .collect::<Vec<_>>();
    let mut frame_confidences = confidence_values;
    let mut frame_times = (0..predicted_frequencies.len())
        .map(|index| index as f32 * (step_size_ms as f32 / 1000.0))
        .collect::<Vec<_>>();

    if (sr_augment_factor - 1.0).abs() > f64::EPSILON {
        for frequency in &mut predicted_frequencies {
            *frequency /= sr_augment_factor as f32;
        }
        for time in &mut frame_times {
            *time *= sr_augment_factor as f32;
        }
    }

    trim_padded_frames(
        original_sample_count,
        config.sample_rate,
        &mut frame_times,
        &mut predicted_frequencies,
        &mut frame_confidences,
        &mut activations,
    );

    let valid_mask = expected_valid_mask(
        &predicted_frequencies,
        &frame_confidences,
        config.expected_frequency,
    );
    let consensus =
        estimate_pitch_consensus(&predicted_frequencies, &frame_confidences, &valid_mask);

    let (activation_map, activation_shape, activation_freq_axis) = if config.include_activations {
        if (sr_augment_factor - 1.0).abs() > f64::EPSILON {
            reverse_sr_augment_activations(
                &mut activations,
                sr_augment_factor,
                hparams.bins_per_semitone,
            );
        }
        let bins = activations.shape()[1];
        let frames = activations.shape()[0];
        let mut transposed = Vec::with_capacity(bins * frames);
        for bin in 0..bins {
            for frame in 0..frames {
                transposed.push(activations[[frame, 0, bin]]);
            }
        }
        (
            Some(transposed),
            Some((bins, frames)),
            Some(activation_frequency_axis(
                bins,
                hparams.bins_per_semitone,
                hparams.fmin,
            )),
        )
    } else {
        (None, None, None)
    };

    Ok(PestoAnalysis {
        frequency: consensus.frequency,
        confidence: consensus.confidence,
        expected_frequency: config.expected_frequency,
        frame_times,
        predicted_frequencies,
        frame_confidences,
        activation_map,
        activation_map_shape: activation_shape,
        activation_freq_axis,
    })
}

struct PestoOnnxModel {
    encoder: Session,
    confidence: Session,
    io: PestoOnnxIo,
}

impl PestoOnnxModel {
    fn load(encoder_path: &Path, confidence_path: &Path, io: &PestoOnnxIo) -> Result<Self> {
        if !encoder_path.exists() {
            return Err(anyhow!(
                "encoder ONNX model not found: {}",
                encoder_path.display()
            ));
        }
        if !confidence_path.exists() {
            return Err(anyhow!(
                "confidence ONNX model not found: {}",
                confidence_path.display()
            ));
        }
        let encoder = Session::builder()
            .map_err(ort_err)?
            .with_optimization_level(GraphOptimizationLevel::Level3)
            .map_err(ort_err)?
            .with_intra_threads(1)
            .map_err(ort_err)?
            .commit_from_file(encoder_path)
            .map_err(ort_err)?;
        let confidence = Session::builder()
            .map_err(ort_err)?
            .with_optimization_level(GraphOptimizationLevel::Level3)
            .map_err(ort_err)?
            .with_intra_threads(1)
            .map_err(ort_err)?
            .commit_from_file(confidence_path)
            .map_err(ort_err)?;
        Ok(Self {
            encoder,
            confidence,
            io: io.clone(),
        })
    }

    fn run_encoder(&mut self, input: &Array3<f32>) -> Result<Array3<f32>> {
        let outputs = self.encoder.run(ort::inputs![
            self.io.encoder_input.as_str() => TensorRef::from_array_view(input.view()).map_err(ort_err)?
        ]).map_err(ort_err)?;
        let (shape, values) = {
            let view = outputs[self.io.encoder_output.as_str()]
                .try_extract_array::<f32>()
                .map_err(|err| {
                    anyhow!(
                        "failed to extract ONNX output {}: {err}",
                        self.io.encoder_output
                    )
                })?;
            (
                view.shape().to_vec(),
                view.iter().copied().collect::<Vec<_>>(),
            )
        };
        if shape.len() != 2 {
            return Err(anyhow!(
                "encoder output must be rank 2, got shape {:?}",
                shape
            ));
        }
        Array3::from_shape_vec((shape[0], shape[1], 1), values)
            .map(|array| array.permuted_axes([0, 2, 1]).to_owned())
            .context("failed to shape encoder output")
    }

    fn run_confidence(&mut self, input: &Array2<f32>) -> Result<Vec<f32>> {
        let outputs = self.confidence.run(ort::inputs![
            self.io.confidence_input.as_str() => TensorRef::from_array_view(input.view()).map_err(ort_err)?
        ]).map_err(ort_err)?;
        let values = {
            let view = outputs[self.io.confidence_output.as_str()]
                .try_extract_array::<f32>()
                .map_err(|err| {
                    anyhow!(
                        "failed to extract ONNX output {}: {err}",
                        self.io.confidence_output
                    )
                })?;
            view.iter().copied().collect()
        };
        Ok(values)
    }
}

fn compute_confidence_energy(features: &Array3<f32>) -> Result<Array2<f32>> {
    let frames = features.shape()[0];
    let harmonics = features.shape()[1];
    let bins = features.shape()[2];
    if harmonics != 1 {
        return Err(anyhow!(
            "Rust PESTO confidence export currently expects one harmonic, got {harmonics}"
        ));
    }
    let mut values = Vec::with_capacity(frames * bins);
    for frame in 0..frames {
        for bin in 0..bins {
            let log_magnitude = features[[frame, 0, bin]];
            values.push(((log_magnitude as f64) * std::f64::consts::LN_10 / 10.0).exp() as f32);
        }
    }
    Array2::from_shape_vec((frames, bins), values).context("failed to shape confidence energy")
}

fn compute_hcqt_log_features(
    audio: &[f32],
    sample_rate: usize,
    hparams: &PestoHparams,
) -> Result<Array3<f32>> {
    let hop_length = (hparams.step_size_ms * sample_rate as f64 / 1000.0 + 0.5) as usize;
    if hop_length == 0 {
        return Err(anyhow!("invalid PESTO hop length"));
    }
    let mut channels = Vec::new();
    for harmonic in &hparams.harmonics {
        channels.push(compute_cqt_log_channel(
            audio,
            sample_rate,
            hop_length,
            *harmonic,
            hparams,
        )?);
    }
    if channels.is_empty() {
        return Err(anyhow!("Pesto model must define at least one harmonic"));
    }

    let frames = channels[0].len();
    let bins = hparams.n_bins;
    let harmonics = channels.len();
    let mut values = Vec::with_capacity(frames * harmonics * bins);
    for frame in 0..frames {
        for harmonic in 0..harmonics {
            let channel = &channels[harmonic];
            for bin in 0..bins {
                values.push(channel[frame][bin]);
            }
        }
    }

    Array3::from_shape_vec((frames, harmonics, bins), values)
        .context("failed to shape HCQT features")
}

fn compute_cqt_log_channel(
    audio: &[f32],
    sample_rate: usize,
    hop_length: usize,
    harmonic: f64,
    hparams: &PestoHparams,
) -> Result<Vec<Vec<f32>>> {
    let bins_per_octave = 12 * hparams.bins_per_semitone;
    let mut fmin = hparams.fmin;
    if hparams.center_bins {
        fmin /= 2.0_f64.powf(
            (hparams.bins_per_semitone as f64 - 1.0) / (24.0 * hparams.bins_per_semitone as f64),
        );
    }
    fmin *= harmonic;

    let kernel = create_cqt_kernels(
        sample_rate,
        fmin,
        hparams.fmax,
        hparams.n_bins,
        bins_per_octave,
        hparams.gamma,
    )?;
    let padding = if hparams.center { kernel.width / 2 } else { 0 };
    let padded = reflect_pad(audio, padding);
    let output_frames = if padded.len() < kernel.width {
        0
    } else {
        ((padded.len() - kernel.width) / hop_length) + 1
    };
    let mut frames = vec![vec![0.0_f32; hparams.n_bins]; output_frames];

    for frame in 0..output_frames {
        let offset = frame * hop_length;
        for bin in 0..hparams.n_bins {
            let mut real = 0.0_f64;
            let mut imag = 0.0_f64;
            for tap in 0..kernel.width {
                let sample = f64::from(padded[offset + tap]);
                real += sample * kernel.real[bin][tap];
                imag += sample * kernel.neg_imag[bin][tap];
            }
            real *= kernel.sqrt_lengths[bin];
            imag *= kernel.sqrt_lengths[bin];
            let magnitude = (real * real + imag * imag).sqrt().max(f32::EPSILON as f64);
            frames[frame][bin] = (20.0 * magnitude.log10()) as f32;
        }
    }
    Ok(frames)
}

struct CqtKernel {
    width: usize,
    real: Vec<Vec<f64>>,
    neg_imag: Vec<Vec<f64>>,
    sqrt_lengths: Vec<f64>,
}

fn create_cqt_kernels(
    sample_rate: usize,
    fmin: f64,
    fmax: Option<f64>,
    n_bins: usize,
    bins_per_octave: usize,
    gamma: f64,
) -> Result<CqtKernel> {
    let q = 1.0 / (2.0_f64.powf(1.0 / bins_per_octave as f64) - 1.0);
    let freqs = if let Some(fmax) = fmax {
        let count = (bins_per_octave as f64 * (fmax / fmin).log2()).ceil() as usize;
        (0..count)
            .map(|index| fmin * 2.0_f64.powf(index as f64 / bins_per_octave as f64))
            .collect::<Vec<_>>()
    } else {
        (0..n_bins)
            .map(|index| fmin * 2.0_f64.powf(index as f64 / bins_per_octave as f64))
            .collect::<Vec<_>>()
    };
    if freqs.len() != n_bins {
        return Err(anyhow!(
            "Pesto CQT expected {n_bins} bins but generated {}",
            freqs.len()
        ));
    }
    if freqs.iter().copied().fold(0.0_f64, f64::max) > sample_rate as f64 / 2.0 {
        return Err(anyhow!("Pesto CQT top bin exceeds Nyquist"));
    }

    let alpha = 2.0_f64.powf(1.0 / bins_per_octave as f64) - 1.0;
    let lengths = freqs
        .iter()
        .map(|freq| (q * sample_rate as f64 / (freq + gamma / alpha)).ceil())
        .collect::<Vec<_>>();
    let max_len = lengths.iter().copied().fold(1.0_f64, f64::max) as usize;
    let width = max_len.next_power_of_two();
    let mut real = vec![vec![0.0; width]; n_bins];
    let mut neg_imag = vec![vec![0.0; width]; n_bins];
    let mut sqrt_lengths = Vec::with_capacity(n_bins);

    for (bin, freq) in freqs.iter().enumerate() {
        let length = lengths[bin] as usize;
        sqrt_lengths.push((lengths[bin]).sqrt());
        let start = if length % 2 == 1 {
            (width as f64 / 2.0 - length as f64 / 2.0).ceil() as isize - 1
        } else {
            (width as f64 / 2.0 - length as f64 / 2.0).ceil() as isize
        }
        .max(0) as usize;

        let window = hann_periodic(length);
        let mut temp_real = vec![0.0; length];
        let mut temp_imag = vec![0.0; length];
        let left = -((length as isize + 1) / 2);
        for index in 0..length {
            let phase_index = (left + index as isize) as f64;
            let phase = phase_index * 2.0 * PI * freq / sample_rate as f64;
            temp_real[index] = window[index] * phase.cos() / length as f64;
            temp_imag[index] = window[index] * phase.sin() / length as f64;
        }
        let norm = temp_real
            .iter()
            .zip(temp_imag.iter())
            .map(|(real, imag)| (real * real + imag * imag).sqrt())
            .sum::<f64>();
        if norm <= 0.0 {
            continue;
        }
        for index in 0..length {
            real[bin][start + index] = temp_real[index] / norm;
            neg_imag[bin][start + index] = -temp_imag[index] / norm;
        }
    }

    Ok(CqtKernel {
        width,
        real,
        neg_imag,
        sqrt_lengths,
    })
}

fn crop_features(features: &Array3<f32>, hparams: &PestoHparams) -> Result<Array3<f32>> {
    let bins = features.shape()[2] as isize;
    let start = hparams.crop_max_steps.max(0);
    let stop = if hparams.crop_min_steps < 0 {
        bins + hparams.crop_min_steps
    } else {
        hparams.crop_min_steps
    };
    if start < 0 || stop <= start || stop > bins {
        return Err(anyhow!(
            "invalid PESTO crop range {start}:{stop} for {bins} bins"
        ));
    }
    let start = start as usize;
    let stop = stop as usize;
    let frames = features.shape()[0];
    let harmonics = features.shape()[1];
    let mut values = Vec::with_capacity(frames * harmonics * (stop - start));
    for frame in 0..frames {
        for harmonic in 0..harmonics {
            for bin in start..stop {
                values.push(features[[frame, harmonic, bin]]);
            }
        }
    }
    Array3::from_shape_vec((frames, harmonics, stop - start), values)
        .context("failed to shape cropped PESTO features")
}

fn reduce_activations_alwa(activations: &Array3<f32>, bins_per_semitone: usize) -> Vec<f32> {
    let frames = activations.shape()[0];
    let bins = activations.shape()[2];
    let bps = if bins % 128 == 0 {
        bins / 128
    } else {
        bins_per_semitone.max(1)
    };
    let mut predictions = Vec::with_capacity(frames);
    for frame in 0..frames {
        let mut center_bin = 0usize;
        let mut best = f32::NEG_INFINITY;
        for bin in 0..bins {
            let value = activations[[frame, 0, bin]];
            if value > best {
                best = value;
                center_bin = bin;
            }
        }
        let start = center_bin.saturating_sub(bps.saturating_sub(1));
        let stop = (center_bin + bps).min(bins);
        let mut weighted_sum = 0.0_f32;
        let mut activation_sum = 0.0_f32;
        for bin in start..stop {
            let value = activations[[frame, 0, bin]].max(0.0);
            weighted_sum += value * (bin as f32 / bps as f32);
            activation_sum += value;
        }
        predictions.push(if activation_sum > 1e-8 {
            weighted_sum / activation_sum
        } else {
            0.0
        });
    }
    predictions
}

fn apply_activation_shift(activations: &mut Array3<f32>, hparams: &PestoHparams) {
    let bins = activations.shape()[2];
    if bins == 0 {
        return;
    }
    let shift = -((hparams.shift * hparams.bins_per_semitone as f64).round() as isize);
    if shift == 0 {
        return;
    }
    let frames = activations.shape()[0];
    let mut shifted = activations.clone();
    for frame in 0..frames {
        for bin in 0..bins {
            let source = (bin as isize - shift).rem_euclid(bins as isize) as usize;
            shifted[[frame, 0, bin]] = activations[[frame, 0, source]];
        }
    }
    *activations = shifted;
}

fn reverse_sr_augment_activations(
    activations: &mut Array3<f32>,
    sr_augment_factor: f64,
    bins_per_semitone: usize,
) {
    let frames = activations.shape()[0];
    let bins = activations.shape()[2];
    let bin_shift = (-sr_augment_factor.log2() * 12.0 * bins_per_semitone as f64).round() as isize;
    if bin_shift.unsigned_abs() >= bins {
        activations.fill(0.0);
        return;
    }
    if bin_shift == 0 {
        return;
    }

    let original = activations.clone();
    activations.fill(0.0);
    for frame in 0..frames {
        for bin in 0..bins {
            let target = bin as isize + bin_shift;
            if (0..bins as isize).contains(&target) {
                activations[[frame, 0, target as usize]] = original[[frame, 0, bin]];
            }
        }
    }
}

fn expected_valid_mask(
    predicted_frequencies: &[f32],
    confidences: &[f32],
    expected_frequency: Option<f64>,
) -> Vec<bool> {
    let mut valid = predicted_frequencies
        .iter()
        .zip(confidences.iter())
        .map(|(frequency, confidence)| {
            frequency.is_finite() && *frequency > 0.0 && confidence.is_finite() && *confidence > 0.0
        })
        .collect::<Vec<_>>();
    if let Some(expected) = expected_frequency {
        let max_allowed = expected * 1.5;
        if max_allowed.is_finite() && max_allowed > 0.0 {
            let expected_mask = predicted_frequencies
                .iter()
                .zip(valid.iter())
                .map(|(frequency, is_valid)| *is_valid && f64::from(*frequency) <= max_allowed)
                .collect::<Vec<_>>();
            if expected_mask.iter().any(|value| *value) {
                valid = expected_mask;
            }
        }
    }
    valid
}

struct PitchConsensus {
    frequency: f64,
    confidence: f64,
}

fn estimate_pitch_consensus(
    predicted_frequencies: &[f32],
    confidences: &[f32],
    valid_mask: &[bool],
) -> PitchConsensus {
    let valid = predicted_frequencies
        .iter()
        .zip(confidences.iter())
        .zip(valid_mask.iter())
        .filter_map(|((frequency, confidence), is_valid)| {
            (*is_valid).then_some((f64::from(*frequency), f64::from(*confidence)))
        })
        .collect::<Vec<_>>();
    if valid.is_empty() {
        return PitchConsensus {
            frequency: f64::NAN,
            confidence: f64::NAN,
        };
    }
    if valid.len() == 1 {
        return PitchConsensus {
            frequency: valid[0].0,
            confidence: valid[0].1,
        };
    }

    let jump_threshold = 250.0 / 1200.0;
    let merge_threshold = 250.0 / 1200.0;
    let mut areas: Vec<PitchArea> = Vec::new();
    let mut segment = Vec::new();
    let mut previous_log: Option<f64> = None;
    for (frequency, confidence) in valid {
        let log_frequency = frequency.log2();
        let starts_new = previous_log
            .map(|previous| (log_frequency - previous).abs() > jump_threshold)
            .unwrap_or(false);
        if starts_new && !segment.is_empty() {
            merge_segment(&mut areas, &segment, merge_threshold);
            segment.clear();
        }
        segment.push((frequency, confidence));
        previous_log = Some(log_frequency);
    }
    if !segment.is_empty() {
        merge_segment(&mut areas, &segment, merge_threshold);
    }

    let best = areas
        .iter()
        .max_by(|left, right| {
            left.frame_count
                .cmp(&right.frame_count)
                .then_with(|| left.confidence_sum.total_cmp(&right.confidence_sum))
        })
        .unwrap();
    let weight_sum = best
        .samples
        .iter()
        .map(|(_, confidence)| confidence)
        .sum::<f64>();
    let frequency = if weight_sum > 0.0 {
        best.samples
            .iter()
            .map(|(frequency, confidence)| frequency * confidence)
            .sum::<f64>()
            / weight_sum
    } else {
        best.samples
            .iter()
            .map(|(frequency, _)| frequency)
            .sum::<f64>()
            / best.samples.len() as f64
    };
    PitchConsensus {
        frequency,
        confidence: weight_sum / best.samples.len() as f64,
    }
}

struct PitchArea {
    samples: Vec<(f64, f64)>,
    frame_count: usize,
    confidence_sum: f64,
    center_log2: f64,
}

fn merge_segment(areas: &mut Vec<PitchArea>, segment: &[(f64, f64)], merge_threshold: f64) {
    let confidence_sum = segment
        .iter()
        .map(|(_, confidence)| confidence)
        .sum::<f64>();
    let weight_sum = if confidence_sum > 0.0 {
        confidence_sum
    } else {
        segment.len() as f64
    };
    let center_log2 = segment
        .iter()
        .map(|(frequency, confidence)| {
            let weight = if confidence_sum > 0.0 {
                *confidence
            } else {
                1.0
            };
            frequency.log2() * weight
        })
        .sum::<f64>()
        / weight_sum;

    if let Some(area) = areas
        .iter_mut()
        .filter(|area| (area.center_log2 - center_log2).abs() <= merge_threshold)
        .min_by(|left, right| {
            (left.center_log2 - center_log2)
                .abs()
                .total_cmp(&(right.center_log2 - center_log2).abs())
        })
    {
        let old_weight = if area.confidence_sum > 0.0 {
            area.confidence_sum
        } else {
            area.frame_count as f64
        };
        area.samples.extend_from_slice(segment);
        area.frame_count += segment.len();
        area.confidence_sum += confidence_sum;
        area.center_log2 =
            (area.center_log2 * old_weight + center_log2 * weight_sum) / (old_weight + weight_sum);
    } else {
        areas.push(PitchArea {
            samples: segment.to_vec(),
            frame_count: segment.len(),
            confidence_sum,
            center_log2,
        });
    }
}

fn trim_padded_frames(
    original_sample_count: usize,
    sample_rate: usize,
    frame_times: &mut Vec<f32>,
    predicted_frequencies: &mut Vec<f32>,
    confidences: &mut Vec<f32>,
    activations: &mut Array3<f32>,
) {
    let original_duration_seconds = original_sample_count as f32 / sample_rate.max(1) as f32;
    let keep_count = frame_times
        .iter()
        .take_while(|time| **time <= original_duration_seconds + 1e-9)
        .count();
    if keep_count == frame_times.len() {
        return;
    }
    frame_times.truncate(keep_count);
    predicted_frequencies.truncate(keep_count);
    confidences.truncate(keep_count);
    let bins = activations.shape()[2];
    let mut values = Vec::with_capacity(keep_count * bins);
    for frame in 0..keep_count {
        for bin in 0..bins {
            values.push(activations[[frame, 0, bin]]);
        }
    }
    *activations = Array3::from_shape_vec((keep_count, 1, bins), values)
        .unwrap_or_else(|_| Array3::zeros((0, 1, bins)));
}

fn activation_frequency_axis(num_bins: usize, bins_per_semitone: usize, fmin: f64) -> Vec<f32> {
    (0..num_bins)
        .map(|index| {
            (fmin * 2.0_f64.powf(index as f64 / (12.0 * bins_per_semitone.max(1) as f64))) as f32
        })
        .collect()
}

fn sr_augment_factor(expected_frequency: Option<f64>) -> f64 {
    let Some(expected) = expected_frequency else {
        return 1.0;
    };
    if !expected.is_finite() || expected <= 0.0 {
        1.0
    } else {
        DEFAULT_IDEAL_PITCH_HZ / expected
    }
}

fn pad_short_audio(audio: &[f32], hparams: &PestoHparams, sample_rate: usize) -> Vec<f32> {
    let hop_length = (hparams.step_size_ms * sample_rate as f64 / 1000.0 + 0.5) as usize;
    let min_samples = create_cqt_kernels(
        sample_rate,
        hparams.fmin,
        hparams.fmax,
        hparams.n_bins,
        12 * hparams.bins_per_semitone,
        hparams.gamma,
    )
    .map(|kernel| kernel.width / 2 + 1 + hop_length.saturating_sub(hop_length))
    .unwrap_or(0);
    if audio.len() >= min_samples {
        audio.to_vec()
    } else {
        let mut padded = audio.to_vec();
        padded.resize(min_samples, 0.0);
        padded
    }
}

fn reflect_pad(audio: &[f32], padding: usize) -> Vec<f32> {
    if padding == 0 || audio.is_empty() {
        return audio.to_vec();
    }
    let mut padded = Vec::with_capacity(audio.len() + padding * 2);
    for index in 0..padding {
        let source = reflect_index(index as isize - padding as isize, audio.len());
        padded.push(audio[source]);
    }
    padded.extend_from_slice(audio);
    for index in 0..padding {
        let source = reflect_index(audio.len() as isize + index as isize, audio.len());
        padded.push(audio[source]);
    }
    padded
}

fn reflect_index(mut index: isize, len: usize) -> usize {
    if len == 1 {
        return 0;
    }
    let len = len as isize;
    while index < 0 || index >= len {
        if index < 0 {
            index = -index;
        } else {
            index = 2 * len - index - 2;
        }
    }
    index as usize
}

fn hann_periodic(length: usize) -> Vec<f64> {
    if length == 0 {
        return Vec::new();
    }
    (0..length)
        .map(|index| 0.5 - 0.5 * (2.0 * PI * index as f64 / length as f64).cos())
        .collect()
}

fn load_manifest(path: Option<&Path>) -> Result<Option<PestoModelManifest>> {
    let Some(path) = path else {
        return Ok(None);
    };
    if !path.exists() {
        return Ok(None);
    }
    let text = fs::read_to_string(path)
        .with_context(|| format!("failed to read PESTO ONNX manifest {}", path.display()))?;
    let manifest = serde_json::from_str(&text)
        .with_context(|| format!("failed to parse PESTO ONNX manifest {}", path.display()))?;
    Ok(Some(manifest))
}

fn ort_err<E: std::fmt::Display>(err: E) -> anyhow::Error {
    anyhow!(err.to_string())
}

fn empty_analysis(expected_frequency: Option<f64>) -> PestoAnalysis {
    PestoAnalysis {
        frequency: f64::NAN,
        confidence: f64::NAN,
        expected_frequency,
        frame_times: Vec::new(),
        predicted_frequencies: Vec::new(),
        frame_confidences: Vec::new(),
        activation_map: None,
        activation_map_shape: None,
        activation_freq_axis: None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn alwa_reduction_uses_local_average() {
        let mut activations = Array3::zeros((1, 1, 384));
        activations[[0, 0, 30]] = 0.5;
        activations[[0, 0, 31]] = 1.0;
        activations[[0, 0, 32]] = 0.5;

        let pred = reduce_activations_alwa(&activations, 3);

        assert!((pred[0] - (31.0 / 3.0)).abs() < 1e-6);
    }

    #[test]
    fn reflect_padding_excludes_edges() {
        let padded = reflect_pad(&[0.0, 1.0, 2.0], 2);
        assert_eq!(padded, vec![2.0, 1.0, 0.0, 1.0, 2.0, 1.0, 0.0]);
    }

    #[test]
    fn crop_features_matches_pesto_crop() {
        let features = Array3::from_shape_vec((1, 1, 6), vec![0., 1., 2., 3., 4., 5.]).unwrap();
        let hparams = PestoHparams {
            crop_max_steps: 1,
            crop_min_steps: -1,
            n_bins: 6,
            ..PestoHparams::default()
        };

        let cropped = crop_features(&features, &hparams).unwrap();

        assert_eq!(
            cropped.iter().copied().collect::<Vec<_>>(),
            vec![1., 2., 3., 4.]
        );
    }
}
