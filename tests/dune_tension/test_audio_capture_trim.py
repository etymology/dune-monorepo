from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import dune_tension.audio_runtime as audio_runtime
from spectrum_analysis.audio_processing import (
    acquire_audio,
    discard_leading_audio,
)
from spectrum_analysis.pitch_compare_config import PitchCompareConfig


def test_discard_leading_audio_drops_first_50ms() -> None:
    sample_rate = 100
    audio = np.arange(20, dtype=np.float32)

    trimmed = discard_leading_audio(audio, sample_rate, discard_seconds=0.05)

    assert trimmed.tolist() == list(range(5, 20))


def test_acquire_audio_discards_first_50ms_after_snr_capture(monkeypatch) -> None:
    sample_rate = 100
    cfg = PitchCompareConfig(
        sample_rate=sample_rate,
        max_record_seconds=1.0,
        trigger_mode="snr",
    )

    monkeypatch.setattr(
        "spectrum_analysis.audio_processing._acquire_audio_snr",
        lambda *_args, **_kwargs: np.arange(20, dtype=np.float32),
    )

    captured = acquire_audio(cfg, noise_rms=0.0)

    assert captured is not None
    assert captured.tolist() == list(range(5, 20))


def test_record_audio_filtered_discards_first_50ms(monkeypatch) -> None:
    sample_rate = 100
    raw_audio = np.arange(20, dtype=np.float32)

    monkeypatch.setattr(
        audio_runtime,
        "_load_audio_processing_helpers",
        lambda: {
            "record_noise_sample": lambda _cfg: raw_audio,
            "discard_leading_audio": discard_leading_audio,
            "apply_noise_filter": lambda audio, *_args, **_kwargs: audio,
            "compute_noise_profile": lambda *_args, **_kwargs: None,
            "load_noise_profile": lambda *_args, **_kwargs: None,
            "save_noise_profile": lambda *_args, **_kwargs: None,
        },
    )
    monkeypatch.setattr(audio_runtime, "_load_noise_profile", lambda **_kwargs: None)

    trimmed, amplitude = audio_runtime.record_audio_filtered(
        duration=0.2,
        sample_rate=sample_rate,
        normalize=False,
    )

    assert trimmed.tolist() == list(range(5, 20))
    assert amplitude == np.mean(np.abs(trimmed))
