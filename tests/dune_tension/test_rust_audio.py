from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from dune_tension import rust_audio
from spectrum_analysis import pesto_analysis


def _simulate_missing_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rust_audio, "_EXTENSION", None)
    monkeypatch.setattr(
        rust_audio,
        "_EXTENSION_ERROR",
        ImportError("missing rust extension"),
    )


def test_auto_audio_backend_falls_back_when_extension_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DUNE_AUDIO_BACKEND", raising=False)
    _simulate_missing_extension(monkeypatch)

    assert rust_audio.should_use_audio_backend() is False


def test_auto_capture_backend_requires_capture_feature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DUNE_AUDIO_BACKEND", raising=False)
    monkeypatch.setattr(
        rust_audio,
        "_EXTENSION",
        SimpleNamespace(capture_backend_available=lambda: False),
    )
    monkeypatch.setattr(rust_audio, "_EXTENSION_ERROR", None)

    assert rust_audio.should_use_capture_backend() is False


def test_forced_rust_capture_backend_fails_without_capture_feature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DUNE_AUDIO_BACKEND", "rust")
    monkeypatch.setattr(
        rust_audio,
        "_EXTENSION",
        SimpleNamespace(capture_backend_available=lambda: False),
    )
    monkeypatch.setattr(rust_audio, "_EXTENSION_ERROR", None)

    with pytest.raises(rust_audio.RustAudioUnavailableError):
        rust_audio.should_use_capture_backend()


def test_forced_rust_audio_backend_fails_fast_when_extension_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DUNE_AUDIO_BACKEND", "rust")
    _simulate_missing_extension(monkeypatch)

    with pytest.raises(rust_audio.RustAudioUnavailableError):
        rust_audio.should_use_audio_backend()


def test_forced_rust_pesto_requires_checked_in_onnx_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PESTO_BACKEND", "rust_onnx")
    monkeypatch.setattr(rust_audio, "_EXTENSION", SimpleNamespace())
    monkeypatch.setattr(rust_audio, "_EXTENSION_ERROR", None)
    monkeypatch.setattr(rust_audio, "find_pesto_onnx_paths", lambda *_args: None)

    with pytest.raises(FileNotFoundError):
        rust_audio.analyze_pesto_onnx(
            np.zeros(8, dtype=np.float32),
            sample_rate=44100,
        )


def test_pesto_onnx_manifest_paths_resolve_checked_in_models() -> None:
    paths = rust_audio.find_pesto_onnx_paths("mir-1k_g7")

    assert paths is not None
    assert all(path.exists() for path in paths)


def test_rust_dsp_wrapper_matches_numpy_rms_when_available() -> None:
    if not rust_audio.is_available():
        pytest.skip(rust_audio.unavailable_reason())

    audio = np.array([3.0, 4.0], dtype=np.float32)

    assert rust_audio.rms(audio) == pytest.approx(float(np.sqrt(12.5)))


def test_rust_dsp_wrapper_discards_leading_audio_when_available() -> None:
    if not rust_audio.is_available():
        pytest.skip(rust_audio.unavailable_reason())

    audio = np.arange(10, dtype=np.float32)

    assert rust_audio.discard_leading_audio(audio, 100, 0.03).tolist() == list(
        range(3, 10)
    )


def test_rust_pitch_validation_wrappers_accept_tone_when_available() -> None:
    if not rust_audio.is_available():
        pytest.skip(rust_audio.unavailable_reason())

    sample_rate = 8000
    times = np.arange(sample_rate // 2, dtype=np.float32) / sample_rate
    audio = np.sin(2.0 * np.pi * 220.0 * times).astype(np.float32)

    assert rust_audio.autocorrelation_pitch(audio, sample_rate) == pytest.approx(
        222.222,
        rel=0.02,
    )
    assert rust_audio.autocorrelation_has_peak_near(audio, sample_rate, 220.0)
    assert rust_audio.fft_has_peak_near(audio, sample_rate, 220.0)


def test_rust_pesto_result_coerces_to_existing_dataclass() -> None:
    result = pesto_analysis._coerce_rust_analysis_result(
        {
            "frequency": 440.0,
            "confidence": 0.9,
            "expected_frequency": None,
            "frame_times": [0.0, 0.005],
            "predicted_frequencies": [439.0, 441.0],
            "frame_confidences": [0.8, 1.0],
            "activation_map": [[0.1, 0.2], [0.3, 0.4]],
            "activation_freq_axis": [55.0, 56.0],
        }
    )

    assert isinstance(result, pesto_analysis.PestoAnalysisResult)
    assert result.frequency == pytest.approx(440.0)
    assert result.frame_times.dtype == np.float32
    assert result.activation_map is not None
    assert result.activation_map.shape == (2, 2)
