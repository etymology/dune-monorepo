#[cfg(any(feature = "cpal-capture", test))]
use std::collections::VecDeque;
#[cfg(feature = "cpal-capture")]
use std::sync::mpsc;
#[cfg(feature = "cpal-capture")]
use std::time::{Duration, Instant};

#[cfg(feature = "cpal-capture")]
use anyhow::Context;
use anyhow::{anyhow, Result};
#[cfg(feature = "cpal-capture")]
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
#[cfg(feature = "cpal-capture")]
use cpal::{SampleFormat, SampleRate, StreamConfig};

#[cfg(feature = "cpal-capture")]
use crate::dsp::discard_leading_audio;
#[cfg(feature = "cpal-capture")]
use crate::dsp::{hanning, harmonic_comb_response, rms};
#[cfg(any(feature = "cpal-capture", test))]
use crate::dsp::{remove_clicks, CombResponse};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TriggerMode {
    Snr,
    HarmonicComb,
}

#[derive(Debug, Clone)]
pub struct HarmonicCombCaptureConfig {
    pub frame_size: usize,
    pub hop_size: usize,
    pub candidate_count: usize,
    pub harmonic_weight_count: usize,
    pub min_harmonics: usize,
    pub on_score: f64,
    pub off_score: f64,
    pub spectral_flatness_max: f64,
    pub on_frames: usize,
    pub off_frames: usize,
    pub harmonicity_floor_frames: usize,
    pub harmonicity_floor_multiplier: f64,
    pub harmonicity_floor_margin: f64,
    pub noise_rms_multiplier: f64,
}

impl Default for HarmonicCombCaptureConfig {
    fn default() -> Self {
        Self {
            frame_size: 2048,
            hop_size: 1024,
            candidate_count: 36,
            harmonic_weight_count: 10,
            min_harmonics: 3,
            on_score: 0.03,
            off_score: 0.015,
            spectral_flatness_max: 0.85,
            on_frames: 1,
            off_frames: 5,
            harmonicity_floor_frames: 16,
            harmonicity_floor_multiplier: 1.1,
            harmonicity_floor_margin: 0.005,
            noise_rms_multiplier: 2.0,
        }
    }
}

#[derive(Debug, Clone)]
pub struct AudioAcquisitionConfig {
    pub sample_rate: usize,
    pub max_record_seconds: f64,
    pub expected_f0: Option<f64>,
    pub snr_threshold_db: f64,
    pub trigger_mode: TriggerMode,
    pub idle_timeout_seconds: f64,
    pub discard_seconds: f64,
    pub comb: HarmonicCombCaptureConfig,
}

pub fn acquire_audio(
    cfg: &AudioAcquisitionConfig,
    noise_rms: f64,
    timeout_seconds: Option<f64>,
) -> Result<Option<Vec<f32>>> {
    #[cfg(not(feature = "cpal-capture"))]
    {
        let _ = (cfg, noise_rms, timeout_seconds);
        return Err(anyhow!(
            "Rust audio capture was built without the cpal-capture feature"
        ));
    }

    #[cfg(feature = "cpal-capture")]
    {
        let captured = match cfg.trigger_mode {
            TriggerMode::Snr => acquire_audio_snr(cfg, noise_rms, timeout_seconds)?,
            TriggerMode::HarmonicComb => match cfg.expected_f0 {
                Some(expected_f0) if expected_f0.is_finite() && expected_f0 > 0.0 => {
                    acquire_audio_harmonic_comb(cfg, expected_f0, noise_rms, timeout_seconds)?
                }
                _ => acquire_audio_snr(cfg, noise_rms, timeout_seconds)?,
            },
        };

        let Some(audio) = captured else {
            return Ok(None);
        };
        let trimmed = discard_leading_audio(&audio, cfg.sample_rate, cfg.discard_seconds);
        Ok(Some(remove_clicks(&trimmed, 4.0, 0.1)))
    }
}

#[cfg(any(feature = "cpal-capture", test))]
#[derive(Debug, Clone)]
struct SnrCaptureState {
    snr_threshold: f64,
    noise_rms: f64,
    idle_limit_samples: usize,
    max_samples: usize,
    collected: Vec<f32>,
    above_threshold: bool,
    recording_started: bool,
    idle_samples: usize,
}

#[cfg(any(feature = "cpal-capture", test))]
impl SnrCaptureState {
    fn new(
        noise_rms: f64,
        snr_threshold_db: f64,
        idle_limit_samples: usize,
        max_samples: usize,
    ) -> Self {
        Self {
            snr_threshold: 10.0_f64.powf(snr_threshold_db / 20.0),
            noise_rms,
            idle_limit_samples,
            max_samples,
            collected: Vec::new(),
            above_threshold: false,
            recording_started: false,
            idle_samples: 0,
        }
    }

    fn recording_started(&self) -> bool {
        self.recording_started
    }

    fn push_chunk(&mut self, chunk: &[f32]) -> bool {
        if chunk.is_empty() || self.collected.len() >= self.max_samples {
            return self.collected.len() >= self.max_samples;
        }

        let ratio = crate::dsp::rms(chunk) / (self.noise_rms + 1e-12);
        if ratio >= self.snr_threshold {
            self.recording_started = true;
            self.above_threshold = true;
            self.idle_samples = 0;
            self.collected.extend_from_slice(chunk);
        } else if self.above_threshold {
            self.idle_samples += chunk.len();
            self.collected.extend_from_slice(chunk);
            if self.idle_samples >= self.idle_limit_samples {
                return true;
            }
        }
        self.collected.len() >= self.max_samples
    }

    fn finish(mut self) -> Option<Vec<f32>> {
        if self.collected.is_empty() {
            None
        } else {
            self.collected.truncate(self.max_samples);
            Some(self.collected)
        }
    }
}

#[cfg(feature = "cpal-capture")]
fn acquire_audio_snr(
    cfg: &AudioAcquisitionConfig,
    noise_rms: f64,
    timeout_seconds: Option<f64>,
) -> Result<Option<Vec<f32>>> {
    let hop = ((cfg.sample_rate as f64 * 0.01).round() as usize).max(128);
    let mut source = CpalInputSource::start(cfg.sample_rate, hop)?;
    let idle_limit = (cfg.idle_timeout_seconds.max(0.0) * cfg.sample_rate as f64) as usize;
    let max_samples = (cfg.max_record_seconds.max(0.0) * cfg.sample_rate as f64) as usize;
    let start = Instant::now();
    let timeout = timeout_seconds.map(|seconds| Duration::from_secs_f64(seconds.max(0.0)));
    let mut state = SnrCaptureState::new(noise_rms, cfg.snr_threshold_db, idle_limit, max_samples);

    while state.collected.len() < max_samples {
        if let Some(timeout) = timeout {
            if !state.recording_started() && start.elapsed() >= timeout {
                break;
            }
        }

        let chunk = source.read()?;
        if chunk.is_empty() {
            continue;
        }
        if state.push_chunk(&chunk) {
            break;
        }
    }
    Ok(state.finish())
}

#[cfg(any(feature = "cpal-capture", test))]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum HarmonicTriggerEvent {
    Waiting,
    StartRecording,
    Recording,
    StopRecording,
}

#[cfg(any(feature = "cpal-capture", test))]
#[derive(Debug, Clone)]
struct HarmonicNoiseFloor {
    scores: VecDeque<f64>,
    capacity: usize,
}

#[cfg(any(feature = "cpal-capture", test))]
impl HarmonicNoiseFloor {
    fn new(capacity: usize) -> Self {
        let capacity = capacity.max(1);
        Self {
            scores: VecDeque::with_capacity(capacity),
            capacity,
        }
    }

    fn push(&mut self, score: f64) {
        if !score.is_finite() || score < 0.0 {
            return;
        }
        while self.scores.len() >= self.capacity {
            self.scores.pop_front();
        }
        self.scores.push_back(score);
    }

    fn percentile(&self, quantile: f64) -> Option<f64> {
        if self.scores.is_empty() {
            return None;
        }
        let mut values = self.scores.iter().copied().collect::<Vec<_>>();
        values.sort_by(|left, right| left.total_cmp(right));
        let index = ((values.len() - 1) as f64 * quantile.clamp(0.0, 1.0)).round() as usize;
        values.get(index).copied()
    }
}

#[cfg(any(feature = "cpal-capture", test))]
#[derive(Debug, Clone)]
struct HarmonicTriggerState {
    comb: HarmonicCombCaptureConfig,
    noise_rms: f64,
    floor: HarmonicNoiseFloor,
    on_counter: usize,
    off_counter: usize,
    triggered: bool,
}

#[cfg(any(feature = "cpal-capture", test))]
impl HarmonicTriggerState {
    fn new(comb: &HarmonicCombCaptureConfig, noise_rms: f64) -> Self {
        Self {
            comb: comb.clone(),
            noise_rms,
            floor: HarmonicNoiseFloor::new(comb.harmonicity_floor_frames),
            on_counter: 0,
            off_counter: 0,
            triggered: false,
        }
    }

    fn triggered(&self) -> bool {
        self.triggered
    }

    fn adaptive_on_score(&self) -> f64 {
        let configured = self.comb.on_score.max(0.0);
        let Some(floor_score) = self.floor.percentile(0.90) else {
            return configured;
        };
        let multiplier = self.comb.harmonicity_floor_multiplier.max(1.0);
        let margin = self.comb.harmonicity_floor_margin.max(0.0);
        configured.max((floor_score * multiplier) + margin)
    }

    fn adaptive_off_score(&self) -> f64 {
        let Some(floor_score) = self.floor.percentile(0.75) else {
            return self.comb.off_score.max(0.0);
        };
        self.comb.off_score.max(floor_score)
    }

    fn is_calibrated_noise_frame(&self, frame_rms: f64) -> bool {
        self.noise_rms.is_finite()
            && self.noise_rms > 0.0
            && frame_rms.is_finite()
            && frame_rms <= self.noise_rms * self.comb.noise_rms_multiplier.max(1.0)
    }

    fn observe(&mut self, response: CombResponse, frame_rms: f64) -> HarmonicTriggerEvent {
        if !self.triggered && self.is_calibrated_noise_frame(frame_rms) {
            self.floor.push(response.score);
        }

        if !self.triggered {
            if response.valid
                && response.score > self.adaptive_on_score()
                && response.spectral_flatness < self.comb.spectral_flatness_max
            {
                self.on_counter += 1;
            } else {
                self.on_counter = 0;
            }

            if self.on_counter >= self.comb.on_frames.max(1) {
                self.triggered = true;
                self.on_counter = 0;
                self.off_counter = 0;
                return HarmonicTriggerEvent::StartRecording;
            }
            return HarmonicTriggerEvent::Waiting;
        }

        if !response.valid
            || response.score < self.adaptive_off_score()
            || response.spectral_flatness >= self.comb.spectral_flatness_max
        {
            self.off_counter += 1;
            if self.off_counter >= self.comb.off_frames.max(1) {
                self.triggered = false;
                return HarmonicTriggerEvent::StopRecording;
            }
        } else {
            self.off_counter = 0;
        }
        HarmonicTriggerEvent::Recording
    }
}

#[cfg(any(feature = "cpal-capture", test))]
fn clean_harmonic_detection_frame(frame: &[f32]) -> Vec<f32> {
    remove_clicks(frame, 4.0, 0.05)
}

#[cfg(feature = "cpal-capture")]
fn acquire_audio_harmonic_comb(
    cfg: &AudioAcquisitionConfig,
    expected_f0: f64,
    noise_rms: f64,
    timeout_seconds: Option<f64>,
) -> Result<Option<Vec<f32>>> {
    let comb = &cfg.comb;
    let frame_size = comb.frame_size.max(1);
    let hop = comb.hop_size.max(1);
    let mut source = CpalInputSource::start(cfg.sample_rate, hop)?;
    let window = hanning(frame_size);
    let nyquist = cfg.sample_rate as f64 / 2.0;
    let freq_bin_one = cfg.sample_rate as f64 / frame_size as f64;
    let f_min = (expected_f0 / 1.5).max(freq_bin_one);
    let f_max = (expected_f0 * 1.5).min(nyquist);
    if !f_min.is_finite() || !f_max.is_finite() || f_max <= f_min {
        return Err(anyhow!("invalid harmonic comb frequency band"));
    }
    let candidates = geomspace(f_min, f_max, comb.candidate_count.max(1));
    let weights = (1..=comb.harmonic_weight_count.max(1))
        .map(|index| 1.0 / index as f64)
        .collect::<Vec<_>>();

    let max_samples = (cfg.max_record_seconds.max(0.0) * cfg.sample_rate as f64) as usize;
    if max_samples == 0 {
        return Ok(None);
    }
    let start = Instant::now();
    let wait_timeout = timeout_seconds.map(|seconds| Duration::from_secs_f64(seconds.max(0.0)));

    let mut collected = Vec::new();
    let mut frame_buffer = Vec::<f32>::new();
    let mut recent_chunks = VecDeque::<Vec<f32>>::new();
    let mut recent_samples = 0usize;
    let mut trigger_state = HarmonicTriggerState::new(comb, noise_rms);

    while !trigger_state.triggered() || collected.len() < max_samples {
        if !trigger_state.triggered() {
            if let Some(timeout) = wait_timeout {
                if start.elapsed() >= timeout {
                    break;
                }
            }
        }

        let chunk = source.read()?;
        if chunk.is_empty() {
            continue;
        }

        frame_buffer.extend_from_slice(&chunk);
        recent_samples += chunk.len();
        recent_chunks.push_back(chunk.clone());
        while recent_samples > frame_size {
            if let Some(removed) = recent_chunks.pop_front() {
                recent_samples = recent_samples.saturating_sub(removed.len());
            } else {
                break;
            }
        }

        let was_triggered = trigger_state.triggered();
        let mut chunk_included = false;
        let mut stop_recording = false;

        while frame_buffer.len() >= frame_size {
            let detection_frame = clean_harmonic_detection_frame(&frame_buffer[..frame_size]);
            let response = harmonic_comb_response(
                &detection_frame,
                cfg.sample_rate,
                &window,
                &candidates,
                &weights,
                comb.min_harmonics,
            );
            let frame_rms = rms(&detection_frame);
            frame_buffer.drain(..hop.min(frame_buffer.len()));

            match trigger_state.observe(response, frame_rms) {
                HarmonicTriggerEvent::StartRecording => {
                    chunk_included = true;
                    for recent in recent_chunks.drain(..) {
                        collected.extend_from_slice(&recent);
                    }
                    recent_samples = 0;
                    if collected.len() >= max_samples {
                        stop_recording = true;
                        break;
                    }
                }
                HarmonicTriggerEvent::StopRecording => {
                    stop_recording = true;
                    break;
                }
                HarmonicTriggerEvent::Waiting | HarmonicTriggerEvent::Recording => {}
            }
        }

        if was_triggered && !chunk_included {
            collected.extend_from_slice(&chunk);
        }
        if stop_recording {
            break;
        }
    }

    if collected.is_empty() {
        Ok(None)
    } else {
        collected.truncate(max_samples);
        Ok(Some(collected))
    }
}

#[cfg(feature = "cpal-capture")]
struct CpalInputSource {
    receiver: mpsc::Receiver<Vec<f32>>,
    _stream: cpal::Stream,
}

#[cfg(feature = "cpal-capture")]
impl CpalInputSource {
    fn start(sample_rate: usize, block_size: usize) -> Result<Self> {
        let host = cpal::default_host();
        let device = host
            .default_input_device()
            .ok_or_else(|| anyhow!("no default input device available"))?;
        let supported_config = device
            .default_input_config()
            .context("failed to query default input config")?;
        let channels = supported_config.channels().max(1) as usize;
        let mut config: StreamConfig = supported_config.clone().into();
        config.channels = supported_config.channels().max(1);
        config.sample_rate = SampleRate(sample_rate as u32);
        config.buffer_size = cpal::BufferSize::Fixed(block_size as u32);

        let (sender, receiver) = mpsc::sync_channel::<Vec<f32>>(64);
        let err_fn = |err| eprintln!("audio input stream error: {err}");

        let stream = match supported_config.sample_format() {
            SampleFormat::F32 => {
                let sender = sender.clone();
                device.build_input_stream(
                    &config,
                    move |data: &[f32], _| {
                        let _ = sender.try_send(mix_to_mono_f32(data, channels));
                    },
                    err_fn,
                    None,
                )?
            }
            SampleFormat::I16 => {
                let sender = sender.clone();
                device.build_input_stream(
                    &config,
                    move |data: &[i16], _| {
                        let mono =
                            mix_to_mono(data, channels, |sample| sample as f32 / i16::MAX as f32);
                        let _ = sender.try_send(mono);
                    },
                    err_fn,
                    None,
                )?
            }
            SampleFormat::U16 => {
                let sender = sender.clone();
                device.build_input_stream(
                    &config,
                    move |data: &[u16], _| {
                        let mono = mix_to_mono(data, channels, |sample| {
                            (sample as f32 / u16::MAX as f32) * 2.0 - 1.0
                        });
                        let _ = sender.try_send(mono);
                    },
                    err_fn,
                    None,
                )?
            }
            other => return Err(anyhow!("unsupported input sample format: {other:?}")),
        };
        stream.play().context("failed to start input stream")?;
        Ok(Self {
            receiver,
            _stream: stream,
        })
    }

    fn read(&mut self) -> Result<Vec<f32>> {
        match self.receiver.recv_timeout(Duration::from_millis(100)) {
            Ok(chunk) => Ok(chunk),
            Err(mpsc::RecvTimeoutError::Timeout) => Ok(Vec::new()),
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                Err(anyhow!("audio input stream disconnected"))
            }
        }
    }
}

#[cfg(feature = "cpal-capture")]
fn mix_to_mono_f32(data: &[f32], channels: usize) -> Vec<f32> {
    mix_to_mono(data, channels, |sample| sample)
}

#[cfg(feature = "cpal-capture")]
fn mix_to_mono<T: Copy>(data: &[T], channels: usize, convert: impl Fn(T) -> f32) -> Vec<f32> {
    let channels = channels.max(1);
    if channels == 1 {
        return data.iter().map(|sample| convert(*sample)).collect();
    }
    data.chunks(channels)
        .map(|frame| frame.iter().map(|sample| convert(*sample)).sum::<f32>() / frame.len() as f32)
        .collect()
}

#[cfg(feature = "cpal-capture")]
fn geomspace(start: f64, stop: f64, count: usize) -> Vec<f64> {
    if count <= 1 {
        return vec![start];
    }
    let log_start = start.ln();
    let log_stop = stop.ln();
    (0..count)
        .map(|index| {
            let ratio = index as f64 / (count - 1) as f64;
            (log_start + (log_stop - log_start) * ratio).exp()
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn snr_capture_starts_on_threshold_and_stops_after_idle() {
        let mut state = SnrCaptureState::new(0.1, 6.0, 4, 100);

        assert!(!state.push_chunk(&[0.01, -0.01]));
        assert!(!state.recording_started());

        assert!(!state.push_chunk(&[0.4, -0.4, 0.4, -0.4]));
        assert!(state.recording_started());

        assert!(state.push_chunk(&[0.01, -0.01, 0.01, -0.01]));
        let captured = state.finish().unwrap();

        assert_eq!(captured.len(), 8);
        assert_eq!(&captured[..4], &[0.4, -0.4, 0.4, -0.4]);
    }

    #[test]
    fn snr_capture_returns_none_without_trigger() {
        let mut state = SnrCaptureState::new(0.1, 6.0, 4, 100);

        assert!(!state.push_chunk(&[0.01, -0.01]));

        assert!(state.finish().is_none());
    }

    #[test]
    fn harmonic_comb_defaults_start_permissive() {
        let cfg = HarmonicCombCaptureConfig::default();

        assert!(cfg.on_score <= 0.03);
        assert!(cfg.off_score < cfg.on_score);
        assert_eq!(cfg.on_frames, 1);
        assert!(cfg.spectral_flatness_max >= 0.8);
        assert!(cfg.harmonicity_floor_margin <= 0.005);
    }

    #[test]
    fn harmonic_trigger_starts_only_above_calibrated_noise_floor() {
        let cfg = HarmonicCombCaptureConfig {
            on_score: 0.01,
            on_frames: 1,
            harmonicity_floor_frames: 4,
            harmonicity_floor_multiplier: 2.0,
            harmonicity_floor_margin: 0.01,
            ..Default::default()
        };
        let mut state = HarmonicTriggerState::new(&cfg, 0.1);
        assert!(!state.triggered());

        for score in [0.04, 0.05, 0.06] {
            let event = state.observe(
                CombResponse {
                    score,
                    spectral_flatness: 0.2,
                    valid: true,
                },
                0.05,
            );
            assert_eq!(event, HarmonicTriggerEvent::Waiting);
        }

        let below_floor = state.observe(
            CombResponse {
                score: 0.12,
                spectral_flatness: 0.2,
                valid: true,
            },
            0.3,
        );
        assert_eq!(below_floor, HarmonicTriggerEvent::Waiting);

        let above_floor = state.observe(
            CombResponse {
                score: 0.14,
                spectral_flatness: 0.2,
                valid: true,
            },
            0.3,
        );
        assert_eq!(above_floor, HarmonicTriggerEvent::StartRecording);
        assert!(state.triggered());
    }

    #[test]
    fn harmonic_detection_frame_suppresses_isolated_clicks() {
        let mut frame = (0..32)
            .map(|index| if index % 2 == 0 { 0.1_f32 } else { -0.1_f32 })
            .collect::<Vec<_>>();
        frame[15] = 8.0;

        let cleaned = clean_harmonic_detection_frame(&frame);

        assert!(cleaned[15].abs() < 1.0);
    }
}
