"""Corroboration helpers: validate NN pitch against autocorrelation and FFT."""

from __future__ import annotations

import logging

import numpy as np

LOGGER = logging.getLogger(__name__)


def _normalized_autocorrelation(
    audio: np.ndarray,
    sample_rate: int,
    f_min: float,
    f_max: float,
) -> tuple[np.ndarray, int, int]:
    """Return normalized autocorrelation and inclusive lag search bounds."""

    audio_1d = np.asarray(audio, dtype=np.float64).reshape(-1)
    n = audio_1d.size
    if n < 2:
        return np.array([], dtype=np.float64), 0, -1

    f_min = max(float(f_min), 1.0)
    f_max = max(float(f_max), f_min + 1.0)
    sr = max(int(sample_rate), 1)

    lag_min = max(1, int(sr / f_max))
    lag_max = min(int(sr / f_min), n - 1)
    if lag_min >= lag_max:
        return np.array([], dtype=np.float64), 0, -1

    centered = audio_1d - float(np.mean(audio_1d))
    norm0 = float(np.dot(centered, centered))
    if norm0 <= 0.0:
        return np.array([], dtype=np.float64), 0, -1

    # FFT-based autocorrelation (zero-padded to avoid circular wrap-around)
    n_fft = 1
    while n_fft < 2 * n:
        n_fft <<= 1
    f_spec = np.fft.rfft(centered, n=n_fft)
    acf_raw = np.fft.irfft(f_spec * np.conj(f_spec))[:n]
    return acf_raw / (norm0 + 1e-30), lag_min, lag_max


def _is_local_peak(values: np.ndarray, index: int) -> bool:
    value = float(values[index])
    left = float(values[index - 1]) if index > 0 else float("-inf")
    right = float(values[index + 1]) if index + 1 < values.size else float("-inf")
    return value >= left and value >= right


def autocorrelation_pitch(
    audio: np.ndarray,
    sample_rate: int,
    f_min: float = 30.0,
    f_max: float = 2000.0,
) -> float:
    """Return the fundamental frequency of *audio* from its highest ACF peak.

    Uses an FFT-based normalized autocorrelation.  The search range is limited
    to lags that correspond to [*f_min*, *f_max*] Hz.  Returns ``nan`` when no
    clear pitch can be extracted.
    """
    acf, lag_min, lag_max = _normalized_autocorrelation(
        audio,
        sample_rate,
        f_min,
        f_max,
    )
    if acf.size == 0:
        return float("nan")

    search = acf[lag_min : lag_max + 1]
    if search.size == 0:
        return float("nan")

    peak_offset = int(np.argmax(search))
    peak_lag = peak_offset + lag_min
    return float(max(int(sample_rate), 1)) / float(peak_lag)


def autocorrelation_has_peak_near(
    audio: np.ndarray,
    sample_rate: int,
    frequency: float,
    tolerance_ratio: float = 0.15,
    threshold_ratio: float = 0.20,
    f_min: float = 30.0,
    f_max: float = 2000.0,
) -> bool:
    """Return True if ACF has a notable local peak near *frequency*.

    Unlike :func:`autocorrelation_pitch`, this does not require the target
    frequency to be the highest ACF response.  It only requires a positive
    local peak in the target band whose height is at least *threshold_ratio*
    of the strongest local ACF peak in the searched frequency range.
    """
    if not np.isfinite(frequency) or frequency <= 0.0:
        return False

    acf, lag_min, lag_max = _normalized_autocorrelation(
        audio,
        sample_rate,
        f_min,
        f_max,
    )
    if acf.size == 0:
        return False

    all_peak_lags = [
        lag for lag in range(lag_min, lag_max + 1) if _is_local_peak(acf, lag)
    ]
    if not all_peak_lags:
        LOGGER.debug("ACF had no local peaks; corroboration fails.")
        return False

    strongest_peak = max(float(acf[lag]) for lag in all_peak_lags)
    if strongest_peak <= 0.0:
        LOGGER.debug("ACF local peaks were not positive; corroboration fails.")
        return False

    tolerance = max(float(tolerance_ratio), 0.0)
    f_lo = frequency * (1.0 - tolerance)
    f_hi = frequency * (1.0 + tolerance)
    if f_lo <= 0.0 or f_hi <= 0.0:
        return False

    sr = float(max(int(sample_rate), 1))
    band_lag_min = max(lag_min, int(np.ceil(sr / f_hi)))
    band_lag_max = min(lag_max, int(np.floor(sr / f_lo)))
    if band_lag_min > band_lag_max:
        return False

    minimum_peak = max(float(threshold_ratio), 0.0) * strongest_peak
    candidate_lags = [
        lag
        for lag in range(band_lag_min, band_lag_max + 1)
        if _is_local_peak(acf, lag) and float(acf[lag]) >= minimum_peak
    ]
    if not candidate_lags:
        LOGGER.debug(
            "ACF had no peak near %.1f Hz above %.3f.",
            frequency,
            minimum_peak,
        )
        return False

    best_lag = max(candidate_lags, key=lambda lag: float(acf[lag]))
    LOGGER.debug(
        "ACF peak near %.1f Hz: peak %.1f Hz value=%.3f threshold=%.3f",
        frequency,
        sr / float(best_lag),
        float(acf[best_lag]),
        minimum_peak,
    )
    return True


def fft_has_peak_near(
    audio: np.ndarray,
    sample_rate: int,
    frequency: float,
    tolerance_ratio: float = 0.10,
    threshold_ratio: float = 0.20,
) -> bool:
    """Return True if the FFT power spectrum has a notable peak near *frequency*.

    A peak is considered "notable" if the maximum spectral magnitude in the
    band [frequency*(1-tolerance_ratio), frequency*(1+tolerance_ratio)] is at
    least *threshold_ratio* of the global spectral maximum.
    """
    if not np.isfinite(frequency) or frequency <= 0.0:
        return False

    audio_1d = np.asarray(audio, dtype=np.float64).reshape(-1)
    n = audio_1d.size
    if n < 4:
        return False

    window = np.hanning(n)
    spectrum = np.abs(np.fft.rfft(audio_1d * window))
    global_max = float(np.max(spectrum))
    if global_max <= 0.0:
        return False

    freq_bins = np.fft.rfftfreq(n, d=1.0 / float(sample_rate))
    f_lo = frequency * (1.0 - tolerance_ratio)
    f_hi = frequency * (1.0 + tolerance_ratio)
    mask = (freq_bins >= f_lo) & (freq_bins <= f_hi)
    if not np.any(mask):
        return False

    local_max = float(np.max(spectrum[mask]))
    return (local_max / global_max) >= threshold_ratio


def nn_pitch_is_corroborated(
    audio: np.ndarray,
    sample_rate: int,
    nn_frequency: float,
    f_min: float = 30.0,
    f_max: float = 2000.0,
    acf_tolerance_ratio: float = 0.15,
    fft_tolerance_ratio: float = 0.10,
    fft_threshold_ratio: float = 0.20,
    acf_peak_threshold_ratio: float = 0.20,
) -> bool:
    """Return True if *nn_frequency* is supported by both ACF and FFT evidence.

    The NN estimate is accepted when:
    1. A notable autocorrelation peak falls within *acf_tolerance_ratio* of
       *nn_frequency* (≈ ±2.5 semitones at 15 %).
    2. The FFT has a notable peak within *fft_tolerance_ratio* of *nn_frequency*.
    """
    if not np.isfinite(nn_frequency) or nn_frequency <= 0.0:
        return False

    acf_ok = autocorrelation_has_peak_near(
        audio,
        sample_rate,
        nn_frequency,
        tolerance_ratio=acf_tolerance_ratio,
        threshold_ratio=acf_peak_threshold_ratio,
        f_min=f_min,
        f_max=f_max,
    )
    LOGGER.debug("ACF peak near %.1f Hz: %s", nn_frequency, acf_ok)
    if not acf_ok:
        return False

    fft_ok = fft_has_peak_near(
        audio,
        sample_rate,
        nn_frequency,
        tolerance_ratio=fft_tolerance_ratio,
        threshold_ratio=fft_threshold_ratio,
    )
    LOGGER.debug("FFT peak near %.1f Hz: %s", nn_frequency, fft_ok)
    return fft_ok


__all__ = [
    "autocorrelation_has_peak_near",
    "autocorrelation_pitch",
    "fft_has_peak_near",
    "nn_pitch_is_corroborated",
]
