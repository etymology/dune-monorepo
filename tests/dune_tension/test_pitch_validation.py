from __future__ import annotations

import numpy as np

from spectrum_analysis.pitch_validation import (
    autocorrelation_has_peak_near,
    autocorrelation_pitch,
    fft_has_peak_near,
    nn_pitch_is_corroborated,
)


def _tone_mix(
    sample_rate: int,
    duration_s: float,
    components: list[tuple[float, float]],
) -> np.ndarray:
    times = np.arange(int(sample_rate * duration_s), dtype=np.float64) / float(
        sample_rate
    )
    audio = np.zeros_like(times)
    for frequency, amplitude in components:
        audio += float(amplitude) * np.sin(2.0 * np.pi * float(frequency) * times)
    return audio


def test_nn_pitch_accepts_non_global_acf_peak() -> None:
    sample_rate = 8000
    nn_frequency = 80.0
    audio = _tone_mix(
        sample_rate,
        0.8,
        [
            (nn_frequency, 1.0),
            (40.0, 0.3),
        ],
    )

    acf_frequency = autocorrelation_pitch(audio, sample_rate)
    assert abs(acf_frequency - nn_frequency) / nn_frequency > 0.15
    assert autocorrelation_has_peak_near(audio, sample_rate, nn_frequency)
    assert fft_has_peak_near(audio, sample_rate, nn_frequency)
    assert nn_pitch_is_corroborated(audio, sample_rate, nn_frequency)


def test_nn_pitch_rejects_when_acf_has_no_peak_near_prediction() -> None:
    sample_rate = 8000
    audio = _tone_mix(sample_rate, 0.8, [(40.0, 1.0)])

    assert not autocorrelation_has_peak_near(audio, sample_rate, 80.0)
    assert not nn_pitch_is_corroborated(audio, sample_rate, 80.0)
