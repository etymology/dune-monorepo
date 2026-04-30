use realfft::RealFftPlanner;
use rustfft::num_complex::Complex;

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
            min_harmonics: 1,
            on_score: 1e-13,
            off_score: 1e-15,
            spectral_flatness_max: 1.0,
            on_frames: 1,
            off_frames: 5,
            harmonicity_floor_frames: 16,
            harmonicity_floor_multiplier: 1.0,
            harmonicity_floor_margin: 0.0,
            noise_rms_multiplier: 2.0,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CombResponse {
    pub score: f64,
    pub spectral_flatness: f64,
    pub valid: bool,
}

pub fn rms(audio: &[f32]) -> f64 {
    if audio.is_empty() {
        return 0.0;
    }
    let sum_squares = audio
        .iter()
        .map(|sample| {
            let value = f64::from(*sample);
            value * value
        })
        .sum::<f64>();
    (sum_squares / audio.len() as f64).sqrt()
}

pub fn triangle_reference_rms(
    sample_rate: usize,
    duration_seconds: f64,
    expected_frequency: Option<f64>,
) -> f64 {
    let Some(frequency) = expected_frequency else {
        return f64::NAN;
    };
    if sample_rate == 0
        || !duration_seconds.is_finite()
        || duration_seconds <= 0.0
        || !frequency.is_finite()
        || frequency <= 0.0
    {
        return f64::NAN;
    }

    let sample_count = ((duration_seconds * sample_rate as f64).round() as usize).max(1);
    let sum_squares = (0..sample_count)
        .map(|index| {
            let time = index as f64 / sample_rate as f64;
            let phase = (time * frequency).rem_euclid(1.0);
            let value = 1.0 - 4.0 * (phase - 0.5).abs();
            value * value
        })
        .sum::<f64>();
    (sum_squares / sample_count as f64).sqrt()
}

pub fn discard_leading_audio(audio: &[f32], sample_rate: usize, discard_seconds: f64) -> Vec<f32> {
    if audio.is_empty() {
        return Vec::new();
    }
    let discard_samples =
        ((discard_seconds.max(0.0) * sample_rate as f64).round() as usize).min(audio.len());
    audio[discard_samples..].to_vec()
}

pub fn remove_clicks(audio: &[f32], threshold_sigma: f64, max_click_fraction: f64) -> Vec<f32> {
    if audio.len() < 4 {
        return audio.to_vec();
    }

    let median = median_f64(audio.iter().map(|value| f64::from(*value)).collect());
    let deviations = audio
        .iter()
        .map(|value| (f64::from(*value) - median).abs())
        .collect::<Vec<_>>();
    let mad = median_f64(deviations);
    if mad < 1e-12 {
        return audio.to_vec();
    }

    let sigma_hat = mad / 0.6745;
    let threshold = threshold_sigma.max(0.0) * sigma_hat;
    let click_mask = audio
        .iter()
        .map(|value| (f64::from(*value) - median).abs() > threshold)
        .collect::<Vec<_>>();
    let click_count = click_mask.iter().filter(|is_click| **is_click).count();
    if click_count == 0 || click_count as f64 > max_click_fraction.max(0.0) * audio.len() as f64 {
        return audio.to_vec();
    }

    let good_indices = click_mask
        .iter()
        .enumerate()
        .filter_map(|(index, is_click)| (!*is_click).then_some(index))
        .collect::<Vec<_>>();
    if good_indices.is_empty() {
        return audio.to_vec();
    }

    let mut cleaned = audio.to_vec();
    for (index, is_click) in click_mask.iter().enumerate() {
        if !*is_click {
            continue;
        }
        let right_pos = good_indices.partition_point(|good_index| *good_index < index);
        if right_pos == 0 {
            cleaned[index] = audio[good_indices[0]];
        } else if right_pos >= good_indices.len() {
            cleaned[index] = audio[*good_indices.last().unwrap_or(&index)];
        } else {
            let left_index = good_indices[right_pos - 1];
            let right_index = good_indices[right_pos];
            let span = (right_index - left_index) as f64;
            let ratio = (index - left_index) as f64 / span;
            let left = f64::from(audio[left_index]);
            let right = f64::from(audio[right_index]);
            cleaned[index] = (left + (right - left) * ratio) as f32;
        }
    }
    cleaned
}

pub fn harmonic_comb_response(
    frame: &[f32],
    sample_rate: usize,
    window: &[f32],
    candidates: &[f64],
    weights: &[f64],
    min_harmonics: usize,
) -> CombResponse {
    if frame.is_empty() || sample_rate == 0 || window.len() != frame.len() || weights.is_empty() {
        return CombResponse {
            score: 0.0,
            spectral_flatness: 1.0,
            valid: false,
        };
    }

    let magnitude = magnitude_spectrum(frame, Some(window));
    if magnitude.is_empty() {
        return CombResponse {
            score: 0.0,
            spectral_flatness: 1.0,
            valid: false,
        };
    }

    let spectral_flatness = spectral_flatness(&magnitude);
    let magnitude_db = magnitude
        .iter()
        .map(|value| 20.0 * value.max(1e-12).log10())
        .collect::<Vec<_>>();
    let max_mag = magnitude.iter().copied().fold(0.0_f64, f64::max) + 1e-12;
    let nyquist = sample_rate as f64 / 2.0;
    let bin_width = if magnitude.len() > 1 {
        sample_rate as f64 / frame.len() as f64
    } else {
        nyquist
    };

    let mut best_score = 0.0;
    let mut found = false;
    let min_harmonics = min_harmonics.max(1);

    for candidate in candidates {
        if !candidate.is_finite() || *candidate <= 0.0 {
            continue;
        }

        let mut sampled = Vec::new();
        let mut harmonics = Vec::new();
        for (index, weight) in weights.iter().enumerate() {
            if *weight <= 0.0 {
                continue;
            }
            let harmonic = *candidate * (index + 1) as f64;
            if harmonic > nyquist {
                continue;
            }
            harmonics.push(harmonic);
            sampled.push(interpolate_spectrum(&magnitude, harmonic, bin_width));
        }
        if sampled.len() < min_harmonics {
            continue;
        }

        let prominent = harmonics
            .iter()
            .zip(sampled.iter())
            .filter(|(harmonic, amplitude)| {
                let amps_db = 20.0 * amplitude.max(1e-12).log10();
                let bin_idx = ((*harmonic / bin_width.max(1e-12)).round() as isize)
                    .clamp(0, magnitude_db.len().saturating_sub(1) as isize)
                    as usize;
                let lo = bin_idx.saturating_sub(3);
                let hi = (bin_idx + 3).min(magnitude_db.len().saturating_sub(1));
                let floor_db = median_f64(magnitude_db[lo..=hi].to_vec());
                amps_db - floor_db >= 8.0
            })
            .count();
        if prominent < min_harmonics {
            continue;
        }

        let local_weight_sum = weights.iter().take(sampled.len()).sum::<f64>();
        let weighted_sum = sampled
            .iter()
            .zip(weights.iter())
            .map(|(amplitude, weight)| amplitude * weight)
            .sum::<f64>();
        let score = if local_weight_sum > 0.0 {
            weighted_sum / (local_weight_sum * max_mag)
        } else {
            0.0
        };
        if score > best_score {
            best_score = score;
            found = true;
        }
    }

    CombResponse {
        score: best_score,
        spectral_flatness,
        valid: found,
    }
}

pub fn remove_non_harmonic_cycles(
    samples: &[f32],
    sample_rate: usize,
    expected_f0: f64,
    comb: &HarmonicCombCaptureConfig,
) -> Vec<f32> {
    if samples.is_empty()
        || sample_rate == 0
        || !expected_f0.is_finite()
        || expected_f0 <= 0.0
        || samples.len() < 4
    {
        return samples.to_vec();
    }

    let cycle_samples = ((sample_rate as f64 / expected_f0).round() as usize).max(1);
    let slice_len = cycle_samples * 8;

    if samples.len() < slice_len {
        return samples.to_vec();
    }

    let window = hanning(slice_len);
    let candidates = vec![expected_f0];
    let weights = (1..=comb.harmonic_weight_count.max(1))
        .map(|index| 1.0 / index as f64)
        .collect::<Vec<_>>();

    let mut kept = Vec::new();
    let mut last_chunk_kept = false;

    for chunk in samples.chunks_exact(slice_len) {
        let response = harmonic_comb_response(
            chunk,
            sample_rate,
            &window,
            &candidates,
            &weights,
            comb.min_harmonics,
        );

        if response.valid
            && response.score > comb.on_score
            && response.spectral_flatness < comb.spectral_flatness_max
        {
            kept.extend_from_slice(chunk);
            last_chunk_kept = true;
        } else {
            last_chunk_kept = false;
        }
    }

    if last_chunk_kept {
        let remainder = samples.len() % slice_len;
        if remainder > 0 {
            kept.extend_from_slice(&samples[samples.len() - remainder..]);
        }
    }

    kept
}

pub fn autocorrelation_pitch(audio: &[f32], sample_rate: usize, f_min: f64, f_max: f64) -> f64 {
    let Some((acf, lag_min, lag_max)) =
        normalized_autocorrelation(audio, sample_rate, f_min, f_max)
    else {
        return f64::NAN;
    };
    let mut best_lag = lag_min;
    let mut best_value = f64::NEG_INFINITY;
    for lag in lag_min..=lag_max {
        if acf[lag] > best_value {
            best_value = acf[lag];
            best_lag = lag;
        }
    }
    sample_rate.max(1) as f64 / best_lag as f64
}

pub fn autocorrelation_has_peak_near(
    audio: &[f32],
    sample_rate: usize,
    frequency: f64,
    tolerance_ratio: f64,
    threshold_ratio: f64,
    f_min: f64,
    f_max: f64,
) -> bool {
    if !frequency.is_finite() || frequency <= 0.0 {
        return false;
    }
    let Some((acf, lag_min, lag_max)) =
        normalized_autocorrelation(audio, sample_rate, f_min, f_max)
    else {
        return false;
    };

    let all_peak_lags = (lag_min..=lag_max)
        .filter(|lag| is_local_peak(&acf, *lag))
        .collect::<Vec<_>>();
    if all_peak_lags.is_empty() {
        return false;
    }
    let strongest_peak = all_peak_lags
        .iter()
        .map(|lag| acf[*lag])
        .fold(f64::NEG_INFINITY, f64::max);
    if strongest_peak <= 0.0 {
        return false;
    }

    let tolerance = tolerance_ratio.max(0.0);
    let f_lo = frequency * (1.0 - tolerance);
    let f_hi = frequency * (1.0 + tolerance);
    if f_lo <= 0.0 || f_hi <= 0.0 {
        return false;
    }

    let sr = sample_rate.max(1) as f64;
    let band_lag_min = lag_min.max((sr / f_hi).ceil() as usize);
    let band_lag_max = lag_max.min((sr / f_lo).floor() as usize);
    if band_lag_min > band_lag_max {
        return false;
    }

    let minimum_peak = threshold_ratio.max(0.0) * strongest_peak;
    (band_lag_min..=band_lag_max).any(|lag| is_local_peak(&acf, lag) && acf[lag] >= minimum_peak)
}

pub fn fft_has_peak_near(
    audio: &[f32],
    sample_rate: usize,
    frequency: f64,
    tolerance_ratio: f64,
    threshold_ratio: f64,
) -> bool {
    if !frequency.is_finite() || frequency <= 0.0 || audio.len() < 4 || sample_rate == 0 {
        return false;
    }

    let window = hanning(audio.len());
    let magnitude = magnitude_spectrum(audio, Some(&window));
    let global_max = magnitude.iter().copied().fold(0.0_f64, f64::max);
    if global_max <= 0.0 {
        return false;
    }

    let f_lo = frequency * (1.0 - tolerance_ratio);
    let f_hi = frequency * (1.0 + tolerance_ratio);
    let bin_width = sample_rate as f64 / audio.len() as f64;
    let local_max = magnitude
        .iter()
        .enumerate()
        .filter_map(|(index, value)| {
            let freq = index as f64 * bin_width;
            (freq >= f_lo && freq <= f_hi).then_some(*value)
        })
        .fold(0.0_f64, f64::max);
    local_max / global_max >= threshold_ratio
}

pub fn nn_pitch_is_corroborated(
    audio: &[f32],
    sample_rate: usize,
    nn_frequency: f64,
    f_min: f64,
    f_max: f64,
    acf_tolerance_ratio: f64,
    fft_tolerance_ratio: f64,
    fft_threshold_ratio: f64,
    acf_peak_threshold_ratio: f64,
) -> bool {
    if !nn_frequency.is_finite() || nn_frequency <= 0.0 {
        return false;
    }
    autocorrelation_has_peak_near(
        audio,
        sample_rate,
        nn_frequency,
        acf_tolerance_ratio,
        acf_peak_threshold_ratio,
        f_min,
        f_max,
    ) && fft_has_peak_near(
        audio,
        sample_rate,
        nn_frequency,
        fft_tolerance_ratio,
        fft_threshold_ratio,
    )
}

pub fn hanning(size: usize) -> Vec<f32> {
    if size <= 1 {
        return vec![1.0; size];
    }
    (0..size)
        .map(|index| {
            (0.5 - 0.5 * (2.0 * std::f64::consts::PI * index as f64 / (size - 1) as f64).cos())
                as f32
        })
        .collect()
}

fn normalized_autocorrelation(
    audio: &[f32],
    sample_rate: usize,
    f_min: f64,
    f_max: f64,
) -> Option<(Vec<f64>, usize, usize)> {
    let n = audio.len();
    if n < 2 || sample_rate == 0 {
        return None;
    }
    let f_min = f_min.max(1.0);
    let f_max = f_max.max(f_min + 1.0);
    let lag_min = (sample_rate as f64 / f_max).floor().max(1.0) as usize;
    let lag_max = ((sample_rate as f64 / f_min).floor() as usize).min(n - 1);
    if lag_min >= lag_max {
        return None;
    }

    let mean = audio.iter().map(|value| f64::from(*value)).sum::<f64>() / n as f64;
    let centered = audio
        .iter()
        .map(|value| f64::from(*value) - mean)
        .collect::<Vec<_>>();
    let norm0 = centered.iter().map(|value| value * value).sum::<f64>();
    if norm0 <= 0.0 {
        return None;
    }

    let mut n_fft = 1;
    while n_fft < 2 * n {
        n_fft <<= 1;
    }

    let mut planner = RealFftPlanner::<f64>::new();
    let fft_forward = planner.plan_fft_forward(n_fft);
    let fft_inverse = planner.plan_fft_inverse(n_fft);

    let mut input = vec![0.0; n_fft];
    for (i, &val) in centered.iter().enumerate() {
        input[i] = val;
    }

    let mut spectrum = fft_forward.make_output_vec();
    fft_forward.process(&mut input, &mut spectrum).ok()?;

    for val in spectrum.iter_mut() {
        *val = Complex::new(val.norm_sqr(), 0.0);
    }

    let mut acf_raw = fft_inverse.make_output_vec();
    fft_inverse.process(&mut spectrum, &mut acf_raw).ok()?;

    let scale = 1.0 / (n_fft as f64 * (norm0 + 1e-30));
    let acf = acf_raw[..n].iter().map(|&val| val * scale).collect();

    Some((acf, lag_min, lag_max))
}

fn is_local_peak(values: &[f64], index: usize) -> bool {
    let value = values[index];
    let left = if index > 0 {
        values[index - 1]
    } else {
        f64::NEG_INFINITY
    };
    let right = values.get(index + 1).copied().unwrap_or(f64::NEG_INFINITY);
    value >= left && value >= right
}

fn magnitude_spectrum(audio: &[f32], window: Option<&[f32]>) -> Vec<f64> {
    if audio.is_empty() {
        return Vec::new();
    }
    let mut planner = RealFftPlanner::<f64>::new();
    let fft = planner.plan_fft_forward(audio.len());
    let mut input = audio
        .iter()
        .enumerate()
        .map(|(index, sample)| {
            let weight = window
                .and_then(|values| values.get(index))
                .copied()
                .unwrap_or(1.0);
            f64::from(*sample) * f64::from(weight)
        })
        .collect::<Vec<_>>();
    let mut spectrum = fft.make_output_vec();
    if fft.process(&mut input, &mut spectrum).is_err() {
        return Vec::new();
    }
    spectrum.iter().map(|value| value.norm()).collect()
}

fn spectral_flatness(magnitude: &[f64]) -> f64 {
    if magnitude.is_empty() {
        return 1.0;
    }
    let eps = 1e-12_f64;
    let geom_mean = (magnitude
        .iter()
        .map(|value| value.max(eps).ln())
        .sum::<f64>()
        / magnitude.len() as f64)
        .exp();
    let arith_mean = magnitude.iter().sum::<f64>() / magnitude.len() as f64;
    geom_mean / (arith_mean + eps)
}

fn interpolate_spectrum(magnitude: &[f64], frequency: f64, bin_width: f64) -> f64 {
    if magnitude.is_empty() || bin_width <= 0.0 {
        return 0.0;
    }
    let position = frequency / bin_width;
    if position <= 0.0 {
        return magnitude[0];
    }
    let lower = position.floor() as usize;
    if lower >= magnitude.len().saturating_sub(1) {
        return *magnitude.last().unwrap_or(&0.0);
    }
    let ratio = position - lower as f64;
    magnitude[lower] * (1.0 - ratio) + magnitude[lower + 1] * ratio
}

fn median_f64(mut values: Vec<f64>) -> f64 {
    if values.is_empty() {
        return f64::NAN;
    }
    values.sort_by(|left, right| left.total_cmp(right));
    let mid = values.len() / 2;
    if values.len() % 2 == 0 {
        (values[mid - 1] + values[mid]) / 2.0
    } else {
        values[mid]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rms_matches_expected_value() {
        assert!((rms(&[1.0, -1.0]) - 1.0).abs() < 1e-12);
    }

    #[test]
    fn click_removal_interpolates_isolated_impulse() {
        let cleaned = remove_clicks(&[0.0, 0.1, 10.0, 0.2, 0.0], 2.0, 0.5);
        assert!((cleaned[2] - 0.15).abs() < 1e-6);
    }

    #[test]
    fn harmonic_comb_detects_harmonic_signal() {
        let sample_rate = 16_000;
        let frame_size = 2048;
        let frame = (0..frame_size)
            .map(|index| {
                let t = index as f64 / sample_rate as f64;
                (0.8 * (2.0 * std::f64::consts::PI * 220.0 * t).sin()
                    + 0.3 * (2.0 * std::f64::consts::PI * 440.0 * t).sin()
                    + 0.2 * (2.0 * std::f64::consts::PI * 660.0 * t).sin()) as f32
            })
            .collect::<Vec<_>>();
        let window = hanning(frame_size);
        let candidates = geomspace(180.0, 260.0, 24);
        let weights = (1..8).map(|index| 1.0 / index as f64).collect::<Vec<_>>();

        let response =
            harmonic_comb_response(&frame, sample_rate, &window, &candidates, &weights, 3);

        assert!(response.valid);
        assert!(response.score > 0.1);
        assert!(response.spectral_flatness < 0.6);
    }

    #[test]
    fn nn_pitch_can_be_corroborated() {
        let sample_rate = 8000;
        let audio = (0..(sample_rate as f64 * 0.8) as usize)
            .map(|index| {
                let t = index as f64 / sample_rate as f64;
                ((2.0 * std::f64::consts::PI * 80.0 * t).sin()
                    + 0.3 * (2.0 * std::f64::consts::PI * 40.0 * t).sin()) as f32
            })
            .collect::<Vec<_>>();
        assert!(nn_pitch_is_corroborated(
            &audio,
            sample_rate,
            80.0,
            30.0,
            2000.0,
            0.15,
            0.10,
            0.20,
            0.20
        ));
    }

    #[test]
    fn remove_non_harmonic_cycles_filters_noise_between_signals() {
        let sample_rate = 8000;
        let f0 = 200.0;
        let cycle_samples = (sample_rate as f64 / f0).round() as usize;
        let slice_len = cycle_samples * 8;

        let mut audio = Vec::new();
        // Signal 1
        for i in 0..slice_len {
            audio.push(
                (2.0 * std::f64::consts::PI * f0 * i as f64 / sample_rate as f64).sin() as f32,
            );
        }
        // Noise (represented by a frequency far from f0)
        for i in 0..slice_len {
            audio.push(
                (2.0 * std::f64::consts::PI * (f0 * 1.7) * i as f64 / sample_rate as f64).sin()
                    as f32,
            );
        }
        // Signal 2
        for i in 0..slice_len {
            audio.push(
                (2.0 * std::f64::consts::PI * f0 * i as f64 / sample_rate as f64).sin() as f32,
            );
        }
        // Partial Signal (remainder)
        for i in 0..(slice_len / 2) {
            audio.push(
                (2.0 * std::f64::consts::PI * f0 * i as f64 / sample_rate as f64).sin() as f32,
            );
        }

        let mut comb = HarmonicCombCaptureConfig::default();
        comb.on_score = 0.1;
        comb.spectral_flatness_max = 0.5;

        let filtered = remove_non_harmonic_cycles(&audio, sample_rate, f0, &comb);

        // Expected: Signal 1 + Signal 2 + Partial Signal (since Signal 2 was kept)
        // Length should be slice_len * 2 + slice_len / 2 = 2.5 * slice_len
        assert_eq!(filtered.len(), (2.5 * slice_len as f64) as usize);
    }

    #[test]
    fn remove_non_harmonic_cycles_returns_empty_on_pure_noise() {
        let sample_rate = 8000;
        let f0 = 200.0;
        let cycle_samples = (sample_rate as f64 / f0).round() as usize;
        let slice_len = cycle_samples * 8;

        let audio = (0..(slice_len * 2))
            .map(|i| {
                (2.0 * std::f64::consts::PI * (f0 * 1.7) * i as f64 / sample_rate as f64).sin()
                    as f32
            })
            .collect::<Vec<_>>();

        let mut comb = HarmonicCombCaptureConfig::default();
        comb.on_score = 0.1;

        let filtered = remove_non_harmonic_cycles(&audio, sample_rate, f0, &comb);
        assert!(filtered.is_empty());
    }

    fn geomspace(start: f64, stop: f64, count: usize) -> Vec<f64> {
        let log_start = start.ln();
        let log_stop = stop.ln();
        (0..count)
            .map(|index| {
                let ratio = index as f64 / (count - 1) as f64;
                (log_start + (log_stop - log_start) * ratio).exp()
            })
            .collect()
    }
}
