from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable


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


# Backwards-compatible private alias for the historical name.
_default_harmonic_comb_config = default_harmonic_comb_config
