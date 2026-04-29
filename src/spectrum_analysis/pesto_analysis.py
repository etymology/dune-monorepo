"""Helpers for estimating pitch from audio with PESTO."""

from __future__ import annotations

import os
from dataclasses import dataclass
import logging
from typing import Any, Optional, Tuple

import numpy as np

from spectrum_analysis.pitch_consensus import estimate_pitch_consensus

torch: Any | None = None
load_model: Any | None = None
_RUNTIME_DEPS_LOADED = False
_MODEL_CACHE: dict[tuple[str, float, int], Any] = {}
DEFAULT_PESTO_MODEL_NAME = "mir-1k_g7"
DEFAULT_PESTO_STEP_SIZE_MS = 5.0
DEFAULT_PESTO_IDEAL_PITCH_HZ = 600.0
LOGGER = logging.getLogger(__name__)

_ONNX_BACKEND_AVAILABLE = False


def _check_onnx_backend_available() -> bool:
    """Check if ONNX backend is available and should be used.

    Returns:
        True if ONNX Runtime is available and models exist, False otherwise.
    """
    global _ONNX_BACKEND_AVAILABLE
    if _ONNX_BACKEND_AVAILABLE:
        return True

    env_backend = os.environ.get("PESTO_BACKEND", "").lower()
    if env_backend == "pytorch":
        return False
    if env_backend == "onnx":
        try:
            from spectrum_analysis import pesto_onnx

            _ONNX_BACKEND_AVAILABLE = pesto_onnx.use_onnx_backend()
            return _ONNX_BACKEND_AVAILABLE
        except Exception:
            return False

    try:
        from spectrum_analysis import pesto_onnx

        _ONNX_BACKEND_AVAILABLE = pesto_onnx.use_onnx_backend()
        return _ONNX_BACKEND_AVAILABLE
    except Exception:
        return False


def use_pytorch_backend() -> bool:
    """Check if PyTorch backend should be used.

    Returns:
        True if PyTorch backend is selected, False if ONNX backend should be used.
    """
    import os

    env_backend = os.environ.get("PESTO_BACKEND", "").lower()
    if env_backend == "pytorch":
        return True
    if env_backend in {"onnx", "rust_onnx"}:
        return False
    return True


@dataclass(frozen=True)
class PestoAnalysisResult:
    """Pitch estimate and optional activation diagnostics for one audio buffer."""

    frequency: float
    confidence: float
    expected_frequency: float | None
    frame_times: np.ndarray
    predicted_frequencies: np.ndarray
    frame_confidences: np.ndarray
    activation_map: np.ndarray | None = None
    activation_freq_axis: np.ndarray | None = None


def _to_numpy(value: Any) -> np.ndarray:
    if torch is not None and isinstance(value, torch.Tensor):
        return value.detach().cpu().numpy()
    return np.asarray(value)


def _resolve_step_size_ms(_sample_rate: int, _sample_count: int) -> float:
    return float(max(DEFAULT_PESTO_STEP_SIZE_MS, 1.0))


def _padding_samples(value: Any) -> int:
    if isinstance(value, tuple):
        try:
            return max(int(item) for item in value)
        except (TypeError, ValueError):
            return 0

    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _minimum_input_samples(model: Any) -> int | None:
    preprocessor = getattr(model, "preprocessor", None)
    hcqt_kernels = getattr(preprocessor, "hcqt_kernels", None)
    cqt_kernels = getattr(hcqt_kernels, "cqt_kernels", None)
    if cqt_kernels is None:
        return None

    required = 0
    try:
        iterator = iter(cqt_kernels)
    except TypeError:
        return None

    for cqt in iterator:
        conv = getattr(cqt, "conv", None)
        padding = _padding_samples(
            getattr(conv, "padding", 0) if conv is not None else 0
        )
        if padding <= 0 and bool(getattr(cqt, "center", False)):
            padding = _padding_samples(getattr(cqt, "kernel_width", 0)) // 2
        if padding > 0:
            required = max(required, padding + 1)

    return required or None


def _pad_short_audio_for_model(audio: np.ndarray, model: Any) -> tuple[np.ndarray, int]:
    minimum_input_samples = _minimum_input_samples(model)
    if minimum_input_samples is None or audio.size >= minimum_input_samples:
        return audio, 0

    pad_width = int(minimum_input_samples - audio.size)
    LOGGER.debug(
        "Right-padding short audio from %s to %s samples for PESTO inference.",
        audio.size,
        minimum_input_samples,
    )
    return np.pad(audio, (0, pad_width), mode="constant"), pad_width


def _empty_analysis_result() -> PestoAnalysisResult:
    empty = np.zeros(0, dtype=np.float32)
    return PestoAnalysisResult(
        frequency=float("nan"),
        confidence=float("nan"),
        expected_frequency=None,
        frame_times=empty,
        predicted_frequencies=empty,
        frame_confidences=empty,
        activation_map=None,
        activation_freq_axis=None,
    )


def _coerce_analysis_result(result: Any) -> PestoAnalysisResult:
    activation_map = result.activation_map
    activation_freq_axis = result.activation_freq_axis
    return PestoAnalysisResult(
        frequency=float(result.frequency),
        confidence=float(result.confidence),
        expected_frequency=(
            None
            if result.expected_frequency is None
            else float(result.expected_frequency)
        ),
        frame_times=np.asarray(result.frame_times, dtype=np.float32),
        predicted_frequencies=np.asarray(
            result.predicted_frequencies, dtype=np.float32
        ),
        frame_confidences=np.asarray(result.frame_confidences, dtype=np.float32),
        activation_map=None
        if activation_map is None
        else np.asarray(activation_map, dtype=np.float32),
        activation_freq_axis=None
        if activation_freq_axis is None
        else np.asarray(activation_freq_axis, dtype=np.float32),
    )


def _coerce_rust_analysis_result(result: dict[str, Any]) -> PestoAnalysisResult:
    activation_map = result.get("activation_map")
    activation_freq_axis = result.get("activation_freq_axis")
    return PestoAnalysisResult(
        frequency=float(result["frequency"]),
        confidence=float(result["confidence"]),
        expected_frequency=(
            None
            if result.get("expected_frequency") is None
            else float(result["expected_frequency"])
        ),
        frame_times=np.asarray(result["frame_times"], dtype=np.float32),
        predicted_frequencies=np.asarray(
            result["predicted_frequencies"], dtype=np.float32
        ),
        frame_confidences=np.asarray(result["frame_confidences"], dtype=np.float32),
        activation_map=None
        if activation_map is None
        else np.asarray(activation_map, dtype=np.float32),
        activation_freq_axis=None
        if activation_freq_axis is None
        else np.asarray(activation_freq_axis, dtype=np.float32),
    )


def _activation_frequency_axis(model: Any, num_bins: int) -> np.ndarray:
    bins_per_semitone = max(int(getattr(model, "bins_per_semitone", 1)), 1)
    preprocessor = getattr(model, "preprocessor", None)
    hcqt_kwargs = (
        getattr(preprocessor, "hcqt_kwargs", {}) if preprocessor is not None else {}
    )
    fmin = float(hcqt_kwargs.get("fmin", 32.7))
    return (
        fmin
        * np.power(
            2.0,
            np.arange(num_bins, dtype=np.float32) / (12.0 * bins_per_semitone),
        )
    ).astype(np.float32, copy=False)


def _sr_augment_factor(expected_frequency: Optional[float]) -> float:
    if expected_frequency is None:
        return 1.0

    try:
        expected = float(expected_frequency)
    except (TypeError, ValueError):
        expected = float("nan")

    if not np.isfinite(expected) or expected <= 0.0:
        return 1.0

    return DEFAULT_PESTO_IDEAL_PITCH_HZ / expected


def _reverse_sr_augment(
    activation: np.ndarray,
    sr_augment_factor: float,
    bins_per_semitone: int,
) -> np.ndarray:
    """Shift PESTO activations back onto the original pitch axis."""

    num_bins = activation.shape[1]
    bin_shift = int(round(-np.log2(sr_augment_factor) * 12.0 * bins_per_semitone))
    if abs(bin_shift) >= num_bins:
        return np.zeros_like(activation)
    if bin_shift > 0:
        return np.pad(activation, ((0, 0), (bin_shift, 0)), mode="constant")[
            :, :num_bins
        ]
    if bin_shift < 0:
        return np.pad(activation, ((0, 0), (0, -bin_shift)), mode="constant")[
            :,
            -bin_shift:,
        ]
    return activation


def _ensure_runtime_dependencies() -> bool:
    global torch, load_model, _RUNTIME_DEPS_LOADED

    if torch is not None and load_model is not None:
        return True
    if _RUNTIME_DEPS_LOADED:
        return False

    try:  # pragma: no cover - dependency availability depends on environment
        import torch as torch_module
        from pesto import load_model as pesto_load_model
    except Exception:
        torch = None
        load_model = None
        _RUNTIME_DEPS_LOADED = True
        return False

    torch = torch_module
    load_model = pesto_load_model
    _RUNTIME_DEPS_LOADED = True
    return True


def _load_pesto_model_cached(
    model_name: str, step_size_ms: float, sample_rate: int
) -> Any:
    if load_model is None:
        return None

    cache_key = (str(model_name), float(step_size_ms), int(sample_rate))
    model = _MODEL_CACHE.get(cache_key)
    if model is None:
        model = load_model(
            model_name,
            step_size=float(step_size_ms),
            sampling_rate=int(sample_rate),
            streaming=False,
            max_batch_size=1,
        )
        _MODEL_CACHE[cache_key] = model
    return model


def estimate_pitch_from_audio(
    audio: np.ndarray,
    sample_rate: int,
    expected_frequency: Optional[float] = None,
) -> Tuple[float, float]:
    """Estimate pitch for ``audio`` using PESTO.

    Returns ``(nan, nan)`` when inference dependencies are unavailable or the
    audio does not yield any voiced frames.
    """

    result = analyze_audio_with_pesto(
        audio,
        sample_rate,
        expected_frequency=expected_frequency,
        include_activations=False,
    )
    return result.frequency, result.confidence


def analyze_audio_with_pesto(
    audio: np.ndarray,
    sample_rate: int,
    expected_frequency: Optional[float] = None,
    *,
    include_activations: bool = False,
) -> PestoAnalysisResult:
    """Return pitch estimates and optional activation diagnostics for ``audio``."""

    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive.")

    try:
        from dune_tension import rust_audio

        if rust_audio.should_try_rust_pesto():
            rust_result = rust_audio.analyze_pesto_onnx(
                audio,
                sample_rate,
                expected_frequency=expected_frequency,
                include_activations=include_activations,
                model_name=DEFAULT_PESTO_MODEL_NAME,
            )
            if rust_result is not None:
                LOGGER.debug("Using Rust ONNX backend for PESTO inference")
                return _coerce_rust_analysis_result(rust_result)
    except Exception as exc:
        import os

        if os.environ.get("PESTO_BACKEND", "").strip().lower() == "rust_onnx":
            raise
        LOGGER.warning("Rust ONNX backend failed, falling back: %s", exc)

    if not use_pytorch_backend():
        try:
            from spectrum_analysis import pesto_onnx

            LOGGER.debug("Using ONNX backend for PESTO inference")
            return _coerce_analysis_result(
                pesto_onnx.analyze_audio_with_onnx(
                    audio,
                    sample_rate,
                    expected_frequency=expected_frequency,
                    include_activations=include_activations,
                )
            )
        except Exception as exc:
            LOGGER.warning("ONNX backend failed, falling back to PyTorch: %s", exc)

    if not _ensure_runtime_dependencies():
        LOGGER.warning("pesto-pitch is unavailable; cannot estimate pitch.")
        return _empty_analysis_result()
    active_torch = torch
    if active_torch is None:
        LOGGER.warning("torch is unavailable; cannot estimate pitch.")
        return _empty_analysis_result()

    audio_array = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio_array.size == 0:
        return _empty_analysis_result()
    if (
        expected_frequency is None
        and not include_activations
        and (
            not np.any(np.isfinite(audio_array))
            or float(np.max(np.abs(audio_array))) <= 0.0
        )
    ):
        return _empty_analysis_result()

    sr_augment_factor = _sr_augment_factor(expected_frequency)
    augmented_sample_rate = int(round(float(sample_rate) * sr_augment_factor))
    step_size_ms = _resolve_step_size_ms(augmented_sample_rate, int(audio_array.size))
    model = _load_pesto_model_cached(
        DEFAULT_PESTO_MODEL_NAME,
        step_size_ms,
        augmented_sample_rate,
    )
    if model is None:
        LOGGER.warning("pesto model loader is unavailable; cannot estimate pitch.")
        return _empty_analysis_result()

    original_sample_count = int(audio_array.size)
    padded_audio_array, pad_width = _pad_short_audio_for_model(audio_array, model)
    audio_tensor = (
        active_torch.from_numpy(padded_audio_array)
        .to(dtype=active_torch.float32)
        .unsqueeze(0)
    )

    try:
        with active_torch.inference_mode():
            outputs = model(
                audio_tensor,
                sr=augmented_sample_rate,
                convert_to_freq=True,
                return_activations=bool(include_activations),
            )
    except (
        Exception
    ) as exc:  # pragma: no cover - environment-specific inference failure
        LOGGER.warning("PESTO pitch estimation failed: %s", exc)
        return _empty_analysis_result()

    if len(outputs) < 2:
        return _empty_analysis_result()

    predictions = outputs[0]
    confidences = outputs[1]
    activations = outputs[3] if include_activations and len(outputs) >= 4 else None

    predicted_frequencies = (
        _to_numpy(predictions).reshape(-1).astype(np.float32, copy=False)
    )
    confidence_values = (
        _to_numpy(confidences).reshape(-1).astype(np.float32, copy=False)
    )
    frame_times = np.arange(predicted_frequencies.size, dtype=np.float32) * (
        step_size_ms / 1000.0
    )
    if sr_augment_factor != 1.0:
        predicted_frequencies = predicted_frequencies / float(sr_augment_factor)
        frame_times = frame_times * float(sr_augment_factor)

    frame_keep_mask: np.ndarray | None = None
    if pad_width > 0:
        original_duration_seconds = float(original_sample_count) / float(sample_rate)
        frame_keep_mask = frame_times <= (original_duration_seconds + 1e-9)
        predicted_frequencies = predicted_frequencies[frame_keep_mask]
        confidence_values = confidence_values[frame_keep_mask]
        frame_times = frame_times[frame_keep_mask]

    valid = np.isfinite(predicted_frequencies) & (predicted_frequencies > 0.0)
    valid &= np.isfinite(confidence_values) & (confidence_values > 0.0)

    if expected_frequency is not None:
        try:
            max_allowed = float(expected_frequency) * 1.5
        except (TypeError, ValueError):
            max_allowed = float("nan")
        if np.isfinite(max_allowed) and max_allowed > 0.0:
            expected_mask = valid & (predicted_frequencies <= max_allowed)
            if np.any(expected_mask):
                valid = expected_mask

    consensus = estimate_pitch_consensus(
        predicted_frequencies,
        confidence_values,
        valid,
    )
    frequency = consensus.frequency
    confidence = consensus.confidence
    if consensus.area_count > 1:
        LOGGER.debug(
            "PESTO pitch consensus selected %s/%s frames from %s pitch areas.",
            consensus.selected_frame_count,
            consensus.total_frame_count,
            consensus.area_count,
        )

    activation_map: np.ndarray | None = None
    activation_freq_axis: np.ndarray | None = None
    if activations is not None:
        activation_np = _to_numpy(activations)
        if activation_np.ndim == 3 and activation_np.shape[0] == 1:
            activation_np = activation_np[0]
        if activation_np.ndim == 2:
            if frame_keep_mask is not None and frame_keep_mask.size > 0:
                frame_count = min(
                    int(activation_np.shape[0]), int(frame_keep_mask.size)
                )
                activation_np = activation_np[:frame_count]
                activation_np = activation_np[frame_keep_mask[:frame_count]]
            bins_per_semitone = max(int(getattr(model, "bins_per_semitone", 1)), 1)
            if sr_augment_factor != 1.0:
                activation_np = _reverse_sr_augment(
                    activation_np,
                    sr_augment_factor,
                    bins_per_semitone,
                )
            activation_map = activation_np.T.astype(np.float32, copy=False)
            activation_freq_axis = _activation_frequency_axis(
                model,
                activation_map.shape[0],
            )

    return PestoAnalysisResult(
        frequency=frequency,
        confidence=confidence,
        expected_frequency=(
            None if expected_frequency is None else float(expected_frequency)
        ),
        frame_times=frame_times,
        predicted_frequencies=predicted_frequencies,
        frame_confidences=confidence_values,
        activation_map=activation_map,
        activation_freq_axis=activation_freq_axis,
    )
