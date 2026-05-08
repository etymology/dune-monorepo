from pathlib import Path
import sys
import threading
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import dune_tension.audio_runtime as audio_runtime
from spectrum_analysis import audio_processing, comb_trigger as comb_trigger_module
from spectrum_analysis.audio_processing import (
    _acquire_audio_snr,
    acquire_audio,
    discard_leading_audio,
)
from spectrum_analysis.comb_trigger import HarmonicCombConfig, record_with_harmonic_comb
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


class _FakeMicSource:
    """MicSource stand-in that returns a chunk of zeros every read."""

    def __init__(self, samplerate: int, hop: int, *_args, **_kwargs) -> None:
        self.samplerate = samplerate
        self.hop = hop
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def read(self) -> np.ndarray:
        time.sleep(0.01)
        return np.zeros(self.hop, dtype=np.float32)

    def stop(self) -> None:
        self.stopped = True


def test_acquire_audio_snr_returns_promptly_when_stop_event_set(monkeypatch) -> None:
    monkeypatch.setattr(audio_processing, "MicSource", _FakeMicSource)

    stop_event = threading.Event()
    stop_event.set()

    cfg = PitchCompareConfig(
        sample_rate=1000,
        max_record_seconds=10.0,
        snr_threshold_db=60.0,
        trigger_mode="snr",
        idle_timeout=10.0,
    )
    cfg.stop_event = stop_event  # type: ignore[attr-defined]

    started = time.monotonic()
    audio = _acquire_audio_snr(cfg, noise_rms=1.0, timeout=10.0)
    elapsed = time.monotonic() - started

    assert audio is None
    assert elapsed < 0.5


def test_record_with_harmonic_comb_returns_promptly_when_stop_event_set(
    monkeypatch,
) -> None:
    monkeypatch.setattr(comb_trigger_module, "MicSource", _FakeMicSource)
    monkeypatch.setattr(comb_trigger_module, "sd", object())

    stop_event = threading.Event()
    stop_event.set()

    started = time.monotonic()
    audio = record_with_harmonic_comb(
        expected_f0=100.0,
        sample_rate=1000,
        max_record_seconds=10.0,
        timeout_seconds=10.0,
        comb_cfg=HarmonicCombConfig(),
        stop_event=stop_event,
    )
    elapsed = time.monotonic() - started

    assert audio is None
    assert elapsed < 0.5


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
