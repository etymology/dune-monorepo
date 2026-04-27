"""PESTO pitch detection using ONNX Runtime backend.

This module provides an ONNX Runtime-based implementation of PESTO pitch detection
that can be used as a drop-in replacement for the PyTorch backend.

The HCQT preprocessing is done in Python using pesto.preprocessor, while the
CNN encoder and confidence classifier are run with ONNX Runtime for better
performance and reduced GIL contention.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any, Optional, Tuple

import numpy as np


_LOGGER = logging.getLogger(__name__)

onnxruntime = None  # type: ignore
onnx = None  # type: ignore
pesto = None  # type: ignore
torch = None  # type: ignore
_RUNTIME_DEPS_LOADED = False

_ONNX_MODEL_CACHE: dict[str, ONNXPestoModel] = {}
_DEFAULT_MODEL_NAME = "mir-1k_g7"


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


def _ensure_runtime_dependencies() -> bool:
    """Ensure ONNX Runtime, PyTorch, and pesto-pitch dependencies are available.

    Returns:
        True if all dependencies are available, False otherwise.
    """
    global onnxruntime, onnx, pesto, torch, _RUNTIME_DEPS_LOADED

    if _RUNTIME_DEPS_LOADED:
        return onnxruntime is not None and pesto is not None and torch is not None

    try:
        import onnx as onnx_module  # type: ignore
        import onnxruntime as ort_module  # type: ignore
        import torch as torch_module  # type: ignore
        from pesto import load_model as pesto_load_model  # type: ignore
    except Exception as e:
        _LOGGER.debug("Failed to import ONNX Runtime, PyTorch, or pesto: %s", e)
        onnxruntime = None  # type: ignore
        onnx = None  # type: ignore
        pesto = None  # type: ignore
        torch = None  # type: ignore
        _RUNTIME_DEPS_LOADED = True
        return False

    onnxruntime = ort_module  # type: ignore
    onnx = onnx_module  # type: ignore
    torch = torch_module  # type: ignore
    pesto_load_model  # noqa: B018
    pesto = onnxruntime  # type: ignore
    _RUNTIME_DEPS_LOADED = True
    return True


def _find_onnx_model_path(model_name: str, model_type: str) -> Optional[Path]:
    """Find the path to an exported ONNX model.

    Args:
        model_name: Name of the PESTO model (e.g., "mir-1k_g7")
        model_type: Type of model ("encoder" or "confidence")

    Returns:
        Path to the ONNX model file, or None if not found.
    """
    if not _ensure_runtime_dependencies():
        return None

    filename = f"{model_name}_{model_type}.onnx"

    candidate_paths = [
        Path(__file__).resolve().parent.parent.parent
        / "dune_tension"
        / "data"
        / "pesto_onnx"
        / filename,
        Path(__file__).resolve().parent / "pesto_onnx" / filename,
        Path("dune_tension") / "data" / "pesto_onnx" / filename,
    ]

    for path in candidate_paths:
        if path.exists():
            _LOGGER.debug("Found %s model at %s", model_type, path)
            return path

    _LOGGER.debug("Could not find %s model: %s", model_type, filename)
    return None


def _reduce_activations_alwa(
    activations: np.ndarray, bins_per_semitone: int
) -> np.ndarray:
    """Reduce pitch activations to pitch estimates using ALWA method.

    Args:
        activations: Activations array of shape (num_timesteps, num_bins)
        bins_per_semitone: Number of bins per semitone

    Returns:
        Pitch estimates as fractional MIDI semitones, shape (num_timesteps,)
    """
    num_bins = activations.shape[-1]
    bps = num_bins // 128

    if num_bins % 128 != 0:
        _LOGGER.warning(
            "Activations should have output size 128*bins_per_semitone, got %d. Using argmax instead.",
            num_bins,
        )
        return activations.argmax(axis=-1).astype(np.float32) / float(bps)

    all_pitches = np.arange(num_bins, dtype=np.float32) / float(bps)

    center_bin = np.argmax(activations, axis=-1, keepdims=True)
    window = np.arange(1, 2 * bps, dtype=np.int32) - bps
    indices = np.clip(center_bin + window, 0, num_bins - 1)

    batch_size = activations.shape[0]
    expanded_indices = np.broadcast_to(indices, (batch_size, *indices.shape))
    cropped_activations = np.take_along_axis(activations, expanded_indices, axis=-1)

    expanded_pitches = np.broadcast_to(all_pitches, (batch_size, *all_pitches.shape))
    cropped_pitches = np.take_along_axis(expanded_pitches, expanded_indices, axis=-1)

    weighted_sum = (cropped_activations * cropped_pitches).sum(axis=-1)
    activation_sum = cropped_activations.sum(axis=-1)

    return np.where(activation_sum > 1e-8, weighted_sum / activation_sum, 0.0)


def _activation_frequency_axis(
    num_bins: int, bins_per_semitone: int, fmin: float = 32.7
) -> np.ndarray:
    """Compute frequency axis for activation bins.

    Args:
        num_bins: Number of activation bins
        bins_per_semitone: Number of bins per semitone
        fmin: Minimum frequency in Hz

    Returns:
        Frequency axis in Hz, shape (num_bins,)
    """
    return (
        fmin
        * np.power(
            2.0, np.arange(num_bins, dtype=np.float32) / (12.0 * bins_per_semitone)
        )
    ).astype(np.float32, copy=False)


class ONNXPestoModel:
    """Wrapper for PESTO model using ONNX Runtime.

    This class loads ONNX models for the encoder and confidence classifier,
    and provides an inference interface compatible with the PyTorch PESTO model.
    """

    def __init__(
        self,
        encoder_path: Path,
        confidence_path: Path,
        model_name: str,
        bins_per_semitone: int = 2,
        fmin: float = 32.7,
        num_octaves: int = 6,
        hop_size_ms: float = 5.0,
    ):
        """Initialize ONNX PESTO model.

        Args:
            encoder_path: Path to encoder ONNX model
            confidence_path: Path to confidence classifier ONNX model
            model_name: Name of the PESTO model
            bins_per_semitone: Number of bins per semitone
            fmin: Minimum frequency in Hz
            num_octaves: Number of octaves
            hop_size_ms: Hop size in milliseconds
        """
        if not _ensure_runtime_dependencies():
            raise RuntimeError("ONNX Runtime dependencies are not available")

        self.model_name = model_name
        self.bins_per_semitone = bins_per_semitone
        self.fmin = fmin
        self.num_octaves = num_octaves
        self.hop_size_ms = hop_size_ms

        _LOGGER.info("Loading ONNX encoder from %s", encoder_path)
        self.encoder_session = onnxruntime.InferenceSession(
            str(encoder_path),
            providers=["CPUExecutionProvider"],
        )

        _LOGGER.info("Loading ONNX confidence classifier from %s", confidence_path)
        self.confidence_session = onnxruntime.InferenceSession(
            str(confidence_path),
            providers=["CPUExecutionProvider"],
        )

        self.num_freq_bins = 12 * bins_per_semitone * num_octaves
        self.output_dim = 128 * bins_per_semitone

        _LOGGER.info(
            "ONNX PESTO model loaded: bins_per_semitone=%d, output_dim=%d",
            bins_per_semitone,
            self.output_dim,
        )

    @property
    def preprocessor(self) -> Any:
        """Return the PESTO preprocessor (for HCQT computation).

        Returns:
            PESTO Preprocessor instance
        """
        if pesto is None:
            raise RuntimeError("PESTO library is not available")

        if not hasattr(self, "_preprocessor"):
            from pesto import Preprocessor

            self._preprocessor = Preprocessor(
                hop_size=self.hop_size_ms,
                sampling_rate=None,
                fmin=self.fmin,
                harmonics=6,
                bins_per_semitone=self.bins_per_semitone,
                n_octaves=self.num_octaves,
            )

        return self._preprocessor

    def forward(
        self,
        audio: np.ndarray,
        sample_rate: int,
        convert_to_freq: bool = False,
        return_activations: bool = True,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Run forward pass through the PESTO model.

        Args:
            audio: Audio waveform, shape (num_samples,)
            sample_rate: Sampling rate in Hz
            convert_to_freq: Whether to convert predictions to Hz
            return_activations: Whether to return activations

        Returns:
            Tuple of (predictions, confidence, volume, activations)
        """
        preprocessor = self.preprocessor

        audio_tensor = (
            torch.from_numpy(audio).unsqueeze(0) if torch is not None else audio
        )
        if torch is not None:
            import torch as torch_module

            with torch_module.no_grad():
                cqt_output = preprocessor(audio_tensor, sr=sample_rate)

                energy = (cqt_output * (np.log(10) / 10.0)).exp().squeeze(1)
                vol = energy.sum(dim=-1)

                confidence_input = energy.cpu().numpy().astype(np.float32)
                confidence_output = self.confidence_session.run(
                    ["confidence"], {"energy": confidence_input}
                )[0]
                confidence = confidence_output.squeeze(-1).astype(np.float32)

                encoder_input = cqt_output.cpu().numpy().astype(np.float32)

            activations_output = self.encoder_session.run(
                ["activations"], {"hcqt_features": encoder_input}
            )[0]
            activations = activations_output.astype(np.float32)

        else:
            raise RuntimeError("PyTorch is required for HCQT preprocessing")

        predictions = _reduce_activations_alwa(activations, self.bins_per_semitone)

        if convert_to_freq:
            predictions = 440.0 * np.power(2.0, (predictions - 69.0) / 12.0)

        if not return_activations:
            return predictions, confidence, vol.cpu().numpy().astype(np.float32)

        return (
            predictions,
            confidence,
            vol.cpu().numpy().astype(np.float32),
            activations,
        )


def load_onnx_model(
    model_name: str = _DEFAULT_MODEL_NAME,
    step_size_ms: float = 5.0,
    sample_rate: int = 44100,
) -> Optional[ONNXPestoModel]:
    """Load ONNX PESTO model from exported files.

    Args:
        model_name: Name of the PESTO model
        step_size_ms: Step size in milliseconds
        sample_rate: Sampling rate in Hz

    Returns:
        ONNXPestoModel instance, or None if models are not found.
    """
    cache_key = f"{model_name}_{step_size_ms}_{sample_rate}"
    if cache_key in _ONNX_MODEL_CACHE:
        return _ONNX_MODEL_CACHE[cache_key]

    encoder_path = _find_onnx_model_path(model_name, "encoder")
    confidence_path = _find_onnx_model_path(model_name, "confidence")

    if encoder_path is None or confidence_path is None:
        _LOGGER.warning("ONNX models not found for %s", model_name)
        return None

    model = ONNXPestoModel(
        encoder_path=encoder_path,
        confidence_path=confidence_path,
        model_name=model_name,
        bins_per_semitone=2,
        fmin=32.7,
        num_octaves=6,
        hop_size_ms=step_size_ms,
    )

    _ONNX_MODEL_CACHE[cache_key] = model
    return model


def analyze_audio_with_onnx(
    audio: np.ndarray,
    sample_rate: int,
    expected_frequency: Optional[float] = None,
    *,
    include_activations: bool = False,
    model_name: str = _DEFAULT_MODEL_NAME,
    step_size_ms: float = 5.0,
) -> PestoAnalysisResult:
    """Analyze audio using ONNX Runtime backend.

    Args:
        audio: Audio waveform, shape (num_samples,)
        sample_rate: Sampling rate in Hz
        expected_frequency: Expected pitch frequency in Hz
        include_activations: Whether to return activation map
        model_name: Name of the PESTO model
        step_size_ms: Step size in milliseconds

    Returns:
        PestoAnalysisResult with pitch estimates
    """
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")

    model = load_onnx_model(model_name, step_size_ms, sample_rate)
    if model is None:
        _LOGGER.warning("ONNX model not available, cannot estimate pitch")
        return PestoAnalysisResult(
            frequency=float("nan"),
            confidence=float("nan"),
            expected_frequency=None,
            frame_times=np.zeros(0, dtype=np.float32),
            predicted_frequencies=np.zeros(0, dtype=np.float32),
            frame_confidences=np.zeros(0, dtype=np.float32),
            activation_map=None,
            activation_freq_axis=None,
        )

    audio_array = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio_array.size == 0:
        return PestoAnalysisResult(
            frequency=float("nan"),
            confidence=float("nan"),
            expected_frequency=None,
            frame_times=np.zeros(0, dtype=np.float32),
            predicted_frequencies=np.zeros(0, dtype=np.float32),
            frame_confidences=np.zeros(0, dtype=np.float32),
            activation_map=None,
            activation_freq_axis=None,
        )

    try:
        preds, confidence, vol, activations = model.forward(
            audio_array,
            sample_rate,
            convert_to_freq=True,
            return_activations=include_activations,
        )
    except Exception as exc:
        _LOGGER.warning("ONNX PESTO inference failed: %s", exc)
        return PestoAnalysisResult(
            frequency=float("nan"),
            confidence=float("nan"),
            expected_frequency=None,
            frame_times=np.zeros(0, dtype=np.float32),
            predicted_frequencies=np.zeros(0, dtype=np.float32),
            frame_confidences=np.zeros(0, dtype=np.float32),
            activation_map=None,
            activation_freq_axis=None,
        )

    frame_times = np.arange(preds.size, dtype=np.float32) * (step_size_ms / 1000.0)

    predicted_frequencies = preds.astype(np.float32, copy=False)
    confidence_values = confidence.astype(np.float32, copy=False)

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

    if np.any(valid):
        weighted_frequencies = predicted_frequencies[valid]
        weights = confidence_values[valid]
        weight_sum = float(np.sum(weights))
        if weight_sum <= 0.0:
            frequency = float(np.mean(weighted_frequencies))
        else:
            frequency = float(np.average(weighted_frequencies, weights=weights))
        confidence_avg = float(np.mean(weights))
    else:
        frequency = float("nan")
        confidence_avg = float("nan")

    activation_map: np.ndarray | None = None
    activation_freq_axis: np.ndarray | None = None

    if include_activations and activations is not None:
        activation_map = activations.T.astype(np.float32, copy=False)
        activation_freq_axis = _activation_frequency_axis(
            activation_map.shape[0], model.bins_per_semitone, model.fmin
        )

    return PestoAnalysisResult(
        frequency=frequency,
        confidence=confidence_avg,
        expected_frequency=None
        if expected_frequency is None
        else float(expected_frequency),
        frame_times=frame_times,
        predicted_frequencies=predicted_frequencies,
        frame_confidences=confidence_values,
        activation_map=activation_map,
        activation_freq_axis=activation_freq_axis,
    )


def estimate_pitch_with_onnx(
    audio: np.ndarray,
    sample_rate: int,
    expected_frequency: Optional[float] = None,
    model_name: str = _DEFAULT_MODEL_NAME,
    step_size_ms: float = 5.0,
) -> Tuple[float, float]:
    """Estimate pitch from audio using ONNX Runtime backend.

    Args:
        audio: Audio waveform, shape (num_samples,)
        sample_rate: Sampling rate in Hz
        expected_frequency: Expected pitch frequency in Hz
        model_name: Name of the PESTO model
        step_size_ms: Step size in milliseconds

    Returns:
        Tuple of (frequency, confidence). Returns (nan, nan) on failure.
    """
    result = analyze_audio_with_onnx(
        audio,
        sample_rate,
        expected_frequency=expected_frequency,
        include_activations=False,
        model_name=model_name,
        step_size_ms=step_size_ms,
    )
    return result.frequency, result.confidence


def use_onnx_backend() -> bool:
    """Check if ONNX backend should be used.

    Returns:
        True if ONNX Runtime is available and models exist, False otherwise.
    """
    import os

    env_backend = os.environ.get("PESTO_BACKEND", "").lower()

    if env_backend == "pytorch":
        return False
    if env_backend == "onnx":
        return True

    return (
        _ensure_runtime_dependencies()
        and _find_onnx_model_path(_DEFAULT_MODEL_NAME, "encoder") is not None
    )
