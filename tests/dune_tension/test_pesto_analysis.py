from contextlib import nullcontext
from pathlib import Path
import sys

import numpy as np
import pytest


from spectrum_analysis import pesto_analysis, pesto_onnx


class _FakeTensor:
    def __init__(self, value):
        self.value = np.asarray(value, dtype=np.float32)

    def to(self, dtype=None):
        return self

    def unsqueeze(self, axis):
        return _FakeTensor(np.expand_dims(self.value, axis=axis))

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self.value


class _FakeTorch:
    Tensor = _FakeTensor
    float32 = np.float32

    @staticmethod
    def from_numpy(value):
        return _FakeTensor(value)

    @staticmethod
    def inference_mode():
        return nullcontext()


def test_estimate_pitch_from_audio_uses_expected_frequency_mask(monkeypatch):
    monkeypatch.setenv("PESTO_BACKEND", "pytorch")
    captured = {}

    def fake_load_model(name, step_size, sampling_rate, streaming, max_batch_size):
        captured["model_name"] = name
        captured["step_size"] = step_size
        captured["sampling_rate"] = sampling_rate
        captured["streaming"] = streaming
        captured["max_batch_size"] = max_batch_size

        def fake_model(audio_tensor, sr, convert_to_freq, return_activations):
            captured["audio_shape"] = audio_tensor.value.shape
            captured["sr"] = sr
            captured["convert_to_freq"] = convert_to_freq
            captured["return_activations"] = return_activations
            return (
                _FakeTensor([[660.0, 2520.0]]),
                _FakeTensor([[0.7, 0.9]]),
                _FakeTensor([[0.0, 0.0]]),
            )

        return fake_model

    monkeypatch.setattr(pesto_analysis, "torch", _FakeTorch)
    monkeypatch.setattr(pesto_analysis, "load_model", fake_load_model)
    monkeypatch.setattr(pesto_analysis, "_RUNTIME_DEPS_LOADED", True)
    monkeypatch.setattr(pesto_analysis, "_MODEL_CACHE", {})
    monkeypatch.setattr(pesto_analysis, "_resolve_step_size_ms", lambda *_args: 5.0)

    frequency, confidence = pesto_analysis.estimate_pitch_from_audio(
        np.zeros(16, dtype=np.float32),
        sample_rate=16000,
        expected_frequency=100.0,
    )

    # The augmented rate is derived rather than hard-coded: _sr_augment_factor
    # snaps the factor to a coarse grid so neighbouring wires share a model, so
    # pinning a literal here would just re-break when that grid changes.
    expected_rate = int(round(16000 * pesto_analysis._sr_augment_factor(100.0)))

    assert captured["model_name"] == "mir-1k_g7"
    assert captured["step_size"] == 5.0
    assert captured["sampling_rate"] == expected_rate
    assert captured["streaming"] is False
    assert captured["max_batch_size"] == 1
    assert captured["audio_shape"] == (1, 16)
    assert captured["sr"] == expected_rate
    assert captured["convert_to_freq"] is True
    assert captured["return_activations"] is False

    # The fake model reports 660 Hz and 2520 Hz in augmented space; only the
    # first survives the <= 1.5 * expected mask once de-augmented, so its
    # confidence is the one that comes back.
    de_augmented = 660.0 / pesto_analysis._sr_augment_factor(100.0)
    assert np.isclose(frequency, de_augmented)
    assert np.isclose(confidence, 0.7)


def test_sr_augment_factor_snaps_neighbouring_frequencies_to_one_model():
    """Nearby wire pitches must share an augment factor.

    The factor reaches the PESTO model cache key through the augmented sample
    rate, so distinct factors mean a several-hundred-MB model reload per wire.
    """

    factor = pesto_analysis._sr_augment_factor
    assert factor(55.0) == factor(61.4)
    assert factor(55.0) != factor(158.0)

    # Snapping must still land the pitch near PESTO's ideal; a third-octave
    # grid bounds the error at 2**(1/6), i.e. about 12%.
    for f0 in (49.8, 61.4, 80.0, 158.0, 600.0, 2185.0):
        ratio = (f0 * factor(f0)) / pesto_analysis.DEFAULT_PESTO_IDEAL_PITCH_HZ
        assert 0.88 <= ratio <= 1.14, (f0, ratio)

    for degenerate in (None, 0.0, -5.0, float("nan"), float("inf")):
        assert factor(degenerate) == 1.0


def test_estimate_pitch_from_audio_returns_nan_without_pesto(monkeypatch):
    monkeypatch.setenv("PESTO_BACKEND", "pytorch")
    monkeypatch.setattr(pesto_analysis, "torch", None)
    monkeypatch.setattr(pesto_analysis, "load_model", None)
    monkeypatch.setattr(pesto_analysis, "_RUNTIME_DEPS_LOADED", True)

    frequency, confidence = pesto_analysis.estimate_pitch_from_audio(
        np.zeros(8, dtype=np.float32),
        sample_rate=44100,
    )

    assert np.isnan(frequency)
    assert np.isnan(confidence)


def test_analyze_audio_with_pesto_returns_activation_map(monkeypatch):
    monkeypatch.setenv("PESTO_BACKEND", "pytorch")

    def fake_load_model(name, step_size, sampling_rate, streaming, max_batch_size):
        class _FakeModel:
            bins_per_semitone = 2
            preprocessor = type("Preprocessor", (), {"hcqt_kwargs": {"fmin": 55.0}})()

            def __call__(self, audio_tensor, sr, convert_to_freq, return_activations):
                assert audio_tensor.value.shape == (1, 16)
                assert sr == 16000
                assert convert_to_freq is True
                assert return_activations is True
                return (
                    _FakeTensor([[110.0, 120.0]]),
                    _FakeTensor([[0.7, 0.9]]),
                    _FakeTensor([[0.0, 0.0]]),
                    _FakeTensor([[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]]),
                )

        return _FakeModel()

    monkeypatch.setattr(pesto_analysis, "torch", _FakeTorch)
    monkeypatch.setattr(pesto_analysis, "load_model", fake_load_model)
    monkeypatch.setattr(pesto_analysis, "_RUNTIME_DEPS_LOADED", True)
    monkeypatch.setattr(pesto_analysis, "_MODEL_CACHE", {})
    monkeypatch.setattr(pesto_analysis, "_resolve_step_size_ms", lambda *_args: 5.0)

    result = pesto_analysis.analyze_audio_with_pesto(
        np.zeros(16, dtype=np.float32),
        sample_rate=16000,
        include_activations=True,
    )

    assert np.isclose(result.frequency, 115.625)
    assert np.isclose(result.confidence, 0.8)
    assert result.expected_frequency is None
    assert result.activation_map is not None
    assert result.activation_map.shape == (3, 2)
    assert result.activation_freq_axis is not None
    assert result.activation_freq_axis.shape == (3,)
    assert np.all(np.diff(result.activation_freq_axis) > 0)


def test_analyze_audio_with_pesto_uses_majority_pitch_area(monkeypatch):
    monkeypatch.setenv("PESTO_BACKEND", "pytorch")

    def fake_load_model(name, step_size, sampling_rate, streaming, max_batch_size):
        class _FakeModel:
            bins_per_semitone = 2
            preprocessor = type("Preprocessor", (), {"hcqt_kwargs": {"fmin": 55.0}})()

            def __call__(self, audio_tensor, sr, convert_to_freq, return_activations):
                assert audio_tensor.value.shape == (1, 16)
                assert sr == 16000
                assert convert_to_freq is True
                assert return_activations is False
                return (
                    _FakeTensor([[170.0, 171.0, 100.0, 101.0, 170.0, 169.0]]),
                    _FakeTensor([[0.5, 0.5, 0.99, 0.99, 0.5, 0.5]]),
                    _FakeTensor([[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]]),
                )

        return _FakeModel()

    monkeypatch.setattr(pesto_analysis, "torch", _FakeTorch)
    monkeypatch.setattr(pesto_analysis, "load_model", fake_load_model)
    monkeypatch.setattr(pesto_analysis, "_RUNTIME_DEPS_LOADED", True)
    monkeypatch.setattr(pesto_analysis, "_MODEL_CACHE", {})
    monkeypatch.setattr(pesto_analysis, "_resolve_step_size_ms", lambda *_args: 5.0)

    result = pesto_analysis.analyze_audio_with_pesto(
        np.ones(16, dtype=np.float32),
        sample_rate=16000,
        include_activations=False,
    )

    assert np.isclose(result.frequency, 170.0)
    assert np.isclose(result.confidence, 0.5)
    assert np.allclose(
        result.predicted_frequencies,
        np.array([170.0, 171.0, 100.0, 101.0, 170.0, 169.0], dtype=np.float32),
    )


def test_auto_backend_uses_pytorch_inference(monkeypatch):
    monkeypatch.delenv("PESTO_BACKEND", raising=False)

    def fake_load_model(_name, **_kwargs):
        def fake_model(_audio_tensor, **_model_kwargs):
            return (
                _FakeTensor([[220.0, 221.0]]),
                _FakeTensor([[0.8, 0.9]]),
                _FakeTensor([[0.0, 0.0]]),
            )

        return fake_model

    monkeypatch.setattr(pesto_analysis, "torch", _FakeTorch)
    monkeypatch.setattr(pesto_analysis, "load_model", fake_load_model)
    monkeypatch.setattr(pesto_analysis, "_RUNTIME_DEPS_LOADED", True)
    monkeypatch.setattr(pesto_analysis, "_MODEL_CACHE", {})
    monkeypatch.setattr(pesto_analysis, "_resolve_step_size_ms", lambda *_args: 5.0)

    result = pesto_analysis.analyze_audio_with_pesto(
        np.ones(16, dtype=np.float32),
        sample_rate=16000,
        include_activations=False,
    )

    assert np.isclose(result.frequency, 220.5294118)
    assert np.isclose(result.confidence, 0.85)


def test_analyze_audio_with_onnx_uses_majority_pitch_area(monkeypatch):
    class _FakeOnnxModel:
        bins_per_semitone = 2
        fmin = 55.0

        def forward(self, audio, sample_rate, convert_to_freq, return_activations):
            assert audio.shape == (16,)
            assert sample_rate == 16000
            assert convert_to_freq is True
            assert return_activations is False
            return (
                np.array([170.0, 171.0, 100.0, 101.0, 170.0, 169.0], dtype=np.float32),
                np.array([0.5, 0.5, 0.99, 0.99, 0.5, 0.5], dtype=np.float32),
                np.zeros(6, dtype=np.float32),
                None,
            )

    monkeypatch.setattr(
        pesto_onnx,
        "load_onnx_model",
        lambda *_args, **_kwargs: _FakeOnnxModel(),
    )

    result = pesto_onnx.analyze_audio_with_onnx(
        np.ones(16, dtype=np.float32),
        sample_rate=16000,
        include_activations=False,
    )

    assert np.isclose(result.frequency, 170.0)
    assert np.isclose(result.confidence, 0.5)
    assert result.activation_map is None


def test_analyze_audio_with_pesto_reverses_sr_augmentation(monkeypatch):
    monkeypatch.setenv("PESTO_BACKEND", "pytorch")
    activation = np.arange(60, dtype=np.float32).reshape(2, 30)

    def fake_load_model(name, step_size, sampling_rate, streaming, max_batch_size):
        class _FakeModel:
            bins_per_semitone = 2
            preprocessor = type("Preprocessor", (), {"hcqt_kwargs": {"fmin": 55.0}})()

            def __call__(self, _audio_tensor, sr, convert_to_freq, return_activations):
                assert sr == 32000
                assert convert_to_freq is True
                assert return_activations is True
                return (
                    _FakeTensor([[220.0, 240.0]]),
                    _FakeTensor([[0.5, 0.75]]),
                    _FakeTensor([[0.0, 0.0]]),
                    _FakeTensor([activation]),
                )

        return _FakeModel()

    monkeypatch.setattr(pesto_analysis, "torch", _FakeTorch)
    monkeypatch.setattr(pesto_analysis, "load_model", fake_load_model)
    monkeypatch.setattr(pesto_analysis, "_RUNTIME_DEPS_LOADED", True)
    monkeypatch.setattr(pesto_analysis, "_MODEL_CACHE", {})
    monkeypatch.setattr(pesto_analysis, "_resolve_step_size_ms", lambda *_args: 5.0)

    result = pesto_analysis.analyze_audio_with_pesto(
        np.zeros(16, dtype=np.float32),
        sample_rate=16000,
        expected_frequency=300.0,
        include_activations=True,
    )

    assert np.isclose(result.frequency, 116.0)
    assert np.isclose(result.confidence, 0.625)
    assert np.isclose(result.expected_frequency, 300.0)
    assert np.allclose(result.frame_times, np.array([0.0, 0.01], dtype=np.float32))
    assert np.allclose(
        result.predicted_frequencies,
        np.array([110.0, 120.0], dtype=np.float32),
    )
    assert result.activation_map is not None
    assert result.activation_map.shape == (30, 2)
    assert np.allclose(
        result.activation_map[:6, 0],
        np.array([24, 25, 26, 27, 28, 29], dtype=np.float32),
    )
    assert np.allclose(
        result.activation_map[:6, 1],
        np.array([54, 55, 56, 57, 58, 59], dtype=np.float32),
    )
    assert np.allclose(result.activation_map[6:, :], 0.0)


def test_analyze_audio_with_pesto_pads_short_audio_and_trims_outputs(monkeypatch):
    monkeypatch.setenv("PESTO_BACKEND", "pytorch")
    captured = {}

    def fake_load_model(name, step_size, sampling_rate, streaming, max_batch_size):
        class _FakeConv:
            padding = (32768,)

        class _FakeCQT:
            conv = _FakeConv()

        class _FakeHCQT:
            cqt_kernels = [_FakeCQT()]

        class _FakeModel:
            bins_per_semitone = 2
            preprocessor = type(
                "Preprocessor",
                (),
                {
                    "hcqt_kwargs": {"fmin": 55.0},
                    "hcqt_kernels": _FakeHCQT(),
                },
            )()

            def __call__(self, audio_tensor, sr, convert_to_freq, return_activations):
                captured["audio_shape"] = audio_tensor.value.shape
                assert sr == 24000
                assert convert_to_freq is True
                assert return_activations is True
                return (
                    _FakeTensor([[110.0, 120.0, 130.0, 1000.0]]),
                    _FakeTensor([[0.9, 0.6, 0.3, 0.4]]),
                    _FakeTensor([[0.0, 0.0, 0.0, 0.0]]),
                    _FakeTensor(
                        [
                            [
                                [1.0, 2.0, 3.0],
                                [4.0, 5.0, 6.0],
                                [7.0, 8.0, 9.0],
                                [10.0, 11.0, 12.0],
                            ]
                        ]
                    ),
                )

        return _FakeModel()

    monkeypatch.setattr(pesto_analysis, "torch", _FakeTorch)
    monkeypatch.setattr(pesto_analysis, "load_model", fake_load_model)
    monkeypatch.setattr(pesto_analysis, "_RUNTIME_DEPS_LOADED", True)
    monkeypatch.setattr(pesto_analysis, "_MODEL_CACHE", {})
    monkeypatch.setattr(pesto_analysis, "_resolve_step_size_ms", lambda *_args: 500.0)

    result = pesto_analysis.analyze_audio_with_pesto(
        np.zeros(24000, dtype=np.float32),
        sample_rate=24000,
        include_activations=True,
    )

    assert captured["audio_shape"] == (1, 32769)
    assert np.allclose(result.frame_times, np.array([0.0, 0.5, 1.0], dtype=np.float32))
    assert np.allclose(
        result.predicted_frequencies,
        np.array([110.0, 120.0, 130.0], dtype=np.float32),
    )
    assert np.allclose(
        result.frame_confidences,
        np.array([0.9, 0.6, 0.3], dtype=np.float32),
    )
    assert np.isclose(result.frequency, 116.6666667)
    assert np.isclose(result.confidence, 0.6)
    assert result.activation_map is not None
    assert result.activation_map.shape == (3, 3)
    assert np.allclose(
        result.activation_map,
        np.array(
            [
                [1.0, 4.0, 7.0],
                [2.0, 5.0, 8.0],
                [3.0, 6.0, 9.0],
            ],
            dtype=np.float32,
        ),
    )


def test_onnx_backend_fallback_to_pytorch(monkeypatch):
    """Test that ONNX backend falls back to PyTorch when not available."""
    monkeypatch.setenv("PESTO_BACKEND", "onnx")

    def fake_use_onnx_backend():
        return False

    monkeypatch.setattr(
        pesto_analysis, "_check_onnx_backend_available", fake_use_onnx_backend
    )

    import os

    original_backend = os.environ.get("PESTO_BACKEND", "")
    os.environ["PESTO_BACKEND"] = "pytorch"

    try:
        frequency, confidence = pesto_analysis.estimate_pitch_from_audio(
            np.zeros(16, dtype=np.float32),
            sample_rate=44100,
        )

        assert np.isnan(frequency)
        assert np.isnan(confidence)
    finally:
        if original_backend:
            os.environ["PESTO_BACKEND"] = original_backend
        else:
            os.environ.pop("PESTO_BACKEND", None)


def test_pytorch_backend_forced_via_env(monkeypatch):
    """Test that PyTorch backend is used when PESTO_BACKEND=pytorch."""
    monkeypatch.setenv("PESTO_BACKEND", "pytorch")

    assert pesto_analysis.use_pytorch_backend() is True


def test_onnx_backend_selected_via_env(monkeypatch):
    """Test that ONNX backend is selected when PESTO_BACKEND=onnx."""
    monkeypatch.setenv("PESTO_BACKEND", "onnx")

    def fake_use_onnx_backend():
        return True

    monkeypatch.setattr(
        pesto_analysis, "_check_onnx_backend_available", fake_use_onnx_backend
    )

    assert pesto_analysis.use_pytorch_backend() is False


def test_backend_selection_without_env(monkeypatch):
    """Test backend selection when PESTO_BACKEND is not set."""
    monkeypatch.delenv("PESTO_BACKEND", raising=False)

    def fake_check_available():
        return False

    monkeypatch.setattr(
        pesto_analysis, "_check_onnx_backend_available", fake_check_available
    )

    assert pesto_analysis.use_pytorch_backend() is True


def test_auto_backend_keeps_pytorch_even_when_onnx_available(monkeypatch):
    """Test backend selection when ONNX is available."""
    monkeypatch.delenv("PESTO_BACKEND", raising=False)

    def fake_check_available():
        return True

    monkeypatch.setattr(
        pesto_analysis, "_check_onnx_backend_available", fake_check_available
    )

    assert pesto_analysis.use_pytorch_backend() is True


def test_model_cache_is_bounded_and_lru(monkeypatch):
    """Distinct sample rates must not grow the model cache without bound.

    Each PESTO model is keyed by augmented sample rate and weighs hundreds of
    MB, so an unbounded cache OOM-kills the GUI over a measuring session. The
    cache must evict least-recently-used models down to the configured size.
    """

    monkeypatch.setattr(pesto_analysis, "_MODEL_CACHE", {})
    monkeypatch.setattr(pesto_analysis, "load_model", lambda *a, **k: object())
    monkeypatch.setenv("DUNE_PESTO_MODEL_CACHE_SIZE", "2")

    # Load three distinct models (e.g. three wires at different frequencies).
    m_a = pesto_analysis._load_pesto_model_cached("m", 5.0, 100_000)
    pesto_analysis._load_pesto_model_cached("m", 5.0, 200_000)
    pesto_analysis._load_pesto_model_cached("m", 5.0, 300_000)

    # Cache stays at the bound; the oldest (A) was evicted, not B/C.
    assert len(pesto_analysis._MODEL_CACHE) == 2
    assert ("m", 5.0, 100_000) not in pesto_analysis._MODEL_CACHE
    assert ("m", 5.0, 300_000) in pesto_analysis._MODEL_CACHE

    # A hit refreshes recency: re-touching B keeps it alive when D arrives.
    m_b = pesto_analysis._load_pesto_model_cached("m", 5.0, 200_000)
    pesto_analysis._load_pesto_model_cached("m", 5.0, 400_000)
    assert ("m", 5.0, 200_000) in pesto_analysis._MODEL_CACHE
    assert len(pesto_analysis._MODEL_CACHE) == 2

    # Re-loading an evicted key produces a fresh object, not the stale one.
    assert pesto_analysis._load_pesto_model_cached("m", 5.0, 100_000) is not m_a
    assert m_b is not None


def test_onnx_result_without_frames_falls_back_to_pytorch(monkeypatch, caplog):
    """A frameless ONNX result must not surface as a NaN pitch.

    ``analyze_audio_with_onnx`` reports failure by returning an all-NaN result
    instead of raising, so without an explicit check a broken ONNX model is
    indistinguishable from audio that genuinely had no detectable pitch.
    """

    monkeypatch.setenv("PESTO_BACKEND", "onnx")

    def fake_onnx(*_args, **_kwargs):
        return pesto_analysis._empty_analysis_result()

    def fake_load_model(name, step_size, sampling_rate, streaming, max_batch_size):
        def fake_model(audio_tensor, sr, convert_to_freq, return_activations):
            return (
                _FakeTensor([[660.0, 660.0]]),
                _FakeTensor([[0.9, 0.9]]),
                _FakeTensor([[0.0, 0.0]]),
            )

        return fake_model

    monkeypatch.setattr(pesto_onnx, "analyze_audio_with_onnx", fake_onnx)
    monkeypatch.setattr(pesto_analysis, "torch", _FakeTorch)
    monkeypatch.setattr(pesto_analysis, "load_model", fake_load_model)
    monkeypatch.setattr(pesto_analysis, "_RUNTIME_DEPS_LOADED", True)
    monkeypatch.setattr(pesto_analysis, "_MODEL_CACHE", {})
    monkeypatch.setattr(pesto_analysis, "_resolve_step_size_ms", lambda *_args: 5.0)

    audio = np.full(16, 0.25, dtype=np.float32)
    with caplog.at_level("WARNING"):
        result = pesto_analysis.analyze_audio_with_pesto(audio, 16000)

    assert result.frame_confidences.size > 0
    assert np.isfinite(result.frequency)
    assert "falling back to PyTorch" in caplog.text


def test_onnx_empty_result_is_kept_for_silent_audio(monkeypatch):
    """Silent audio legitimately has no pitch, so don't retry on PyTorch."""

    monkeypatch.setenv("PESTO_BACKEND", "onnx")

    def fake_onnx(*_args, **_kwargs):
        return pesto_analysis._empty_analysis_result()

    def unexpected_load_model(*_args, **_kwargs):
        raise AssertionError("PyTorch fallback must not run for silent audio")

    monkeypatch.setattr(pesto_onnx, "analyze_audio_with_onnx", fake_onnx)
    monkeypatch.setattr(pesto_analysis, "torch", _FakeTorch)
    monkeypatch.setattr(pesto_analysis, "load_model", unexpected_load_model)
    monkeypatch.setattr(pesto_analysis, "_RUNTIME_DEPS_LOADED", True)
    monkeypatch.setattr(pesto_analysis, "_MODEL_CACHE", {})

    result = pesto_analysis.analyze_audio_with_pesto(
        np.zeros(16, dtype=np.float32), 16000
    )

    assert result.frame_confidences.size == 0
