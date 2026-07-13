from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

LOGGER = logging.getLogger(__name__)


def default_harmonic_comb_config() -> Any:
    from spectrum_analysis.comb_trigger import HarmonicCombConfig

    return HarmonicCombConfig()


@dataclass(frozen=True)
class AudioAcquisitionConfig:
    """Minimal runtime config passed into ``acquire_audio``."""

    sample_rate: int
    max_record_seconds: float
    expected_f0: float | None
    snr_threshold_db: float
    trigger_mode: str
    min_frequency: float = 30.0
    max_frequency: float = 2000.0
    min_oscillations_per_window: float = 10.0
    min_window_overlap: float = 0.5
    idle_timeout: float = 0.2
    input_mode: str = "mic"
    input_audio_path: str | None = None
    comb_trigger: Any = field(default_factory=default_harmonic_comb_config)
    recording_started_callback: Callable[[], None] | None = None
    stop_event: threading.Event | None = None
    discard_leading_seconds: float = 0.0


@dataclass(frozen=True)
class DeferredPitchSample:
    """Captured sample metadata retained for deferred pitch analysis."""

    audio_sample: Any
    x: float
    y: float
    focus_position: int | None
    confidence: float


@dataclass(frozen=True)
class HarmonicSampleFeatures:
    """Comb features measured on a captured sample."""

    harmonicity: float = 0.0
    spectral_flatness: float = 1.0
    valid: bool = False


def acquire_audio(*args, **kwargs):
    """Lazily import the runtime audio acquisition helper."""

    from spectrum_analysis.audio_processing import acquire_audio as _acquire_audio

    return _acquire_audio(*args, **kwargs)


def estimate_pitch_from_audio(*args, **kwargs):
    """Lazily import the runtime PESTO pitch estimator."""

    from spectrum_analysis.pesto_analysis import (
        estimate_pitch_from_audio as _estimate_pitch_from_audio,
    )

    return _estimate_pitch_from_audio(*args, **kwargs)


def analyze_audio_with_pesto(*args, **kwargs):
    """Lazily import the runtime PESTO diagnostics helper."""

    from spectrum_analysis.pesto_analysis import (
        analyze_audio_with_pesto as _analyze_audio_with_pesto,
    )

    return _analyze_audio_with_pesto(*args, **kwargs)


class SampleAnalyzer:
    """Signal-processing for one measurement run: RMS, amplitude confidence,
    PESTO pitch estimation (FFT-corroborated), and harmonic-comb trigger
    learning.

    Carved out of ``Tensiometer``; the engine keeps thin delegating methods so
    call sites and tests reaching ``_estimate_sample_pitch`` /
    ``_amplitude_confidence`` are unaffected. Holds the run-scoped audio params
    (sample rate, noise floor, comb config/learner) and the last pitch-triplet
    acceptance flag read back by the measurement loop.
    """

    def __init__(
        self,
        *,
        config: Any,
        samplerate: int,
        noise_threshold: float,
        harmonic_comb_config: Any,
        harmonic_trigger_learner: Any,
    ) -> None:
        self.config = config
        self.samplerate = samplerate
        self.noise_threshold = noise_threshold
        self._harmonic_comb_config = harmonic_comb_config
        self._harmonic_trigger_learner = harmonic_trigger_learner
        self.last_pitch_triplet_accepted: bool | None = None

    @staticmethod
    def sample_rms(audio_sample: Any) -> float:
        """Return the RMS amplitude of an audio sample."""

        audio_array = np.asarray(audio_sample, dtype=np.float32).reshape(-1)
        if audio_array.size == 0:
            return 0.0
        audio_float = audio_array.astype(np.float64, copy=False)
        return float(np.sqrt(np.mean(np.square(audio_float))))

    def triangle_reference_rms(self, expected_frequency: float | None) -> float:
        """Return the RMS of a unit-peak triangle wave over the full record window."""

        try:
            sample_rate = int(self.samplerate)
            duration = float(self.config.record_duration)
            if expected_frequency is None:
                return float("nan")
            frequency = float(expected_frequency)
        except (TypeError, ValueError):
            return float("nan")

        if sample_rate <= 0 or not np.isfinite(duration) or duration <= 0.0:
            return float("nan")
        if not np.isfinite(frequency) or frequency <= 0.0:
            return float("nan")
        sample_count = max(int(round(duration * sample_rate)), 1)
        times = np.arange(sample_count, dtype=np.float64) / float(sample_rate)
        phase = np.mod(times * frequency, 1.0)
        triangle_wave = 1.0 - 4.0 * np.abs(phase - 0.5)
        return float(np.sqrt(np.mean(np.square(triangle_wave))))

    def amplitude_confidence(
        self,
        audio_sample: Any,
        expected_frequency: float | None,
    ) -> float:
        """Return amplitude confidence normalized to the expected triangle-wave RMS."""

        measured_rms = self.sample_rms(audio_sample)
        reference_rms = self.triangle_reference_rms(expected_frequency)
        if not np.isfinite(reference_rms) or reference_rms <= 0.0:
            return measured_rms
        return measured_rms / reference_rms

    def is_audio_worth_analyzing(self, audio_sample: Any) -> bool:
        """Return True if the sample has enough signal to justify NN analysis."""

        measured_rms = self.sample_rms(audio_sample)
        if self.noise_threshold > 0.0 and measured_rms < self.noise_threshold * 1.5:
            return False

        return True

    def estimate_sample_pitch(
        self,
        audio_sample: Any,
        expected_frequency: float | None,
    ) -> tuple[Any | None, float, float, bool]:
        """Estimate pitch using PESTO, gated by FFT corroboration.

        Returns ``(analysis, frequency, confidence, accepted)`` where
        ``confidence`` is the model's own confidence for the waveform and
        ``accepted`` signals whether the measurement loop should accept the
        sample.

        A sample is accepted only when it is *both* corroborated and the NN
        confidence clears the configured threshold.  Corroboration means the NN
        frequency lines up with a notable FFT peak (within ±10 %); the peak does
        not have to be the global maximum.  Autocorrelation is no longer
        consulted.  The reported confidence is always the model's real value for
        the waveform — it is never inflated to the threshold.  When not
        corroborated, the sample is rejected (``accepted=False`` and confidence
        zeroed) so the loop keeps searching regardless of what PESTO reported.
        """
        from spectrum_analysis.pitch_validation import fft_has_peak_near

        self.last_pitch_triplet_accepted = None
        analysis = None

        if not self.is_audio_worth_analyzing(audio_sample):
            return None, 0.0, 0.0, False

        require_corroboration = False
        try:
            analysis = analyze_audio_with_pesto(
                audio_sample,
                self.samplerate,
                expected_frequency=expected_frequency,
                include_activations=True,
            )
            frequency, confidence = analysis.frequency, analysis.confidence
            require_corroboration = True
        except Exception:
            frequency, confidence = estimate_pitch_from_audio(
                audio_sample,
                self.samplerate,
                expected_frequency,
            )

        accepted = float(confidence) >= float(self.config.confidence_threshold)

        if require_corroboration and np.isfinite(frequency) and frequency > 0.0:
            corroborated = fft_has_peak_near(
                np.asarray(audio_sample, dtype=np.float64),
                self.samplerate,
                float(frequency),
            )
            if corroborated:
                self.last_pitch_triplet_accepted = True
                # FFT agrees: accept only if the model's real confidence also
                # clears the threshold.  Keep the real confidence value for
                # reporting/ranking either way.
                accepted = float(confidence) >= float(self.config.confidence_threshold)
                LOGGER.debug(
                    "NN pitch %.1f Hz corroborated by FFT; confidence=%.2f accepted=%s.",
                    frequency,
                    confidence,
                    accepted,
                )
            else:
                LOGGER.debug(
                    "NN pitch %.1f Hz not corroborated by FFT; rejecting sample.",
                    frequency,
                )
                self.last_pitch_triplet_accepted = False
                accepted = False
                confidence = 0.0

        return analysis, float(frequency), float(confidence), bool(accepted)

    def sample_harmonic_features(
        self,
        audio_sample: Any,
        frequency: float,
        expected_frequency: float | None,
    ) -> HarmonicSampleFeatures:
        """Measure comb features on a captured sample for trigger learning."""

        comb_cfg = self._harmonic_comb_config
        frame_size = max(1, int(getattr(comb_cfg, "frame_size", 2048)))
        harmonicity_audio = np.asarray(audio_sample, dtype=np.float32).reshape(-1)
        if harmonicity_audio.size < frame_size:
            return HarmonicSampleFeatures()

        frame = harmonicity_audio[:frame_size]
        f0 = None
        if expected_frequency is not None:
            expected = float(expected_frequency)
            if np.isfinite(expected) and expected > 0.0:
                f0 = expected
        if f0 is None and np.isfinite(frequency) and frequency > 0.0:
            f0 = float(frequency)
        if f0 is None:
            return HarmonicSampleFeatures()

        from spectrum_analysis.comb_trigger import harmonic_comb_response

        window = np.hanning(frame_size).astype(np.float32)
        freq_bins = np.fft.rfftfreq(frame_size, d=1.0 / self.samplerate)
        candidates = np.array([float(f0)], dtype=np.float64)
        weights = comb_cfg.harmonic_weights()
        harmonicity, spectral_flatness, valid = harmonic_comb_response(
            frame,
            self.samplerate,
            window,
            freq_bins,
            candidates,
            weights,
            int(comb_cfg.min_harmonics),
        )
        return HarmonicSampleFeatures(
            harmonicity=float(harmonicity),
            spectral_flatness=float(spectral_flatness),
            valid=bool(valid),
        )

    def learn_harmonic_trigger(
        self,
        features: HarmonicSampleFeatures,
        accepted_by_triplet: bool | None,
    ) -> None:
        """Adapt comb trigger parameters from downstream pitch acceptance."""

        if accepted_by_triplet is None or not features.valid:
            return
        learner = self._harmonic_trigger_learner
        if learner is None:
            return
        try:
            from spectrum_analysis.comb_trigger import HarmonicCombTriggerObservation

            learner.observe(
                HarmonicCombTriggerObservation(
                    harmonicity=features.harmonicity,
                    spectral_flatness=features.spectral_flatness,
                    accepted_by_triplet=bool(accepted_by_triplet),
                )
            )
        except Exception as exc:
            LOGGER.debug("Harmonic trigger learning skipped: %s", exc)


# Backwards-compatible private alias for the historical name.
_default_harmonic_comb_config = default_harmonic_comb_config
