from __future__ import annotations

import importlib
import os
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np


class RustAudioUnavailableError(RuntimeError):
    """Raised when a forced Rust backend cannot be used."""


_EXTENSION: ModuleType | None = None
_EXTENSION_ERROR: BaseException | None = None


def _load_extension() -> ModuleType | None:
    global _EXTENSION, _EXTENSION_ERROR

    if _EXTENSION is not None:
        return _EXTENSION
    if _EXTENSION_ERROR is not None:
        return None

    try:
        _EXTENSION = importlib.import_module("dune_tension._rust_audio")
    except BaseException as exc:  # pragma: no cover - depends on local build
        _EXTENSION_ERROR = exc
        return None
    return _EXTENSION


def is_available() -> bool:
    return _load_extension() is not None


def unavailable_reason() -> str:
    if is_available():
        return ""
    if _EXTENSION_ERROR is None:
        return "Rust extension is not installed."
    return str(_EXTENSION_ERROR)


def backend_name() -> str:
    extension = _load_extension()
    if extension is None:
        return "python"
    return str(extension.backend_name())


def _backend_mode(env_name: str) -> str:
    return os.environ.get(env_name, "auto").strip().lower() or "auto"


def should_use_audio_backend() -> bool:
    mode = _backend_mode("DUNE_AUDIO_BACKEND")
    if mode == "python":
        return False
    if mode == "rust":
        _require_extension("DUNE_AUDIO_BACKEND=rust")
        return True
    if mode != "auto":
        raise ValueError(
            f"DUNE_AUDIO_BACKEND must be one of auto, rust, or python; got {mode!r}."
        )
    return is_available()


def capture_backend_available() -> bool:
    extension = _load_extension()
    if extension is None:
        return False
    check = getattr(extension, "capture_backend_available", None)
    if check is None:
        return False
    return bool(check())


def should_use_capture_backend() -> bool:
    mode = _backend_mode("DUNE_AUDIO_BACKEND")
    if mode == "python":
        return False
    if mode == "rust":
        _require_extension("DUNE_AUDIO_BACKEND=rust")
        if not capture_backend_available():
            raise RustAudioUnavailableError(
                "DUNE_AUDIO_BACKEND=rust requested, but the Rust extension was "
                "built without the cpal-capture feature."
            )
        return True
    if mode != "auto":
        raise ValueError(
            f"DUNE_AUDIO_BACKEND must be one of auto, rust, or python; got {mode!r}."
        )
    return capture_backend_available()


def pesto_backend_mode() -> str:
    mode = _backend_mode("PESTO_BACKEND")
    if mode == "":
        return "auto"
    if mode not in {"auto", "rust_onnx", "onnx", "pytorch"}:
        raise ValueError(
            "PESTO_BACKEND must be one of auto, rust_onnx, onnx, or pytorch; "
            f"got {mode!r}."
        )
    return mode


def should_try_rust_pesto() -> bool:
    mode = pesto_backend_mode()
    if mode == "rust_onnx":
        _require_extension("PESTO_BACKEND=rust_onnx")
        return True
    return False


def should_require_rust_pesto() -> bool:
    return pesto_backend_mode() == "rust_onnx"


def _require_extension(context: str) -> ModuleType:
    extension = _load_extension()
    if extension is None:
        raise RustAudioUnavailableError(
            f"{context} requested, but {unavailable_reason()}"
        )
    return extension


def rms(audio: Any) -> float:
    extension = _require_extension("Rust RMS")
    return float(extension.rms(_as_float32(audio)))


def triangle_reference_rms(
    sample_rate: int,
    duration_seconds: float,
    expected_frequency: float | None,
) -> float:
    extension = _require_extension("Rust triangle reference RMS")
    return float(
        extension.triangle_reference_rms(
            int(sample_rate),
            float(duration_seconds),
            None if expected_frequency is None else float(expected_frequency),
        )
    )


def discard_leading_audio(
    audio: Any,
    sample_rate: int,
    discard_seconds: float = 0.05,
) -> np.ndarray:
    extension = _require_extension("Rust leading-audio discard")
    return np.asarray(
        extension.discard_leading_audio(
            _as_float32(audio),
            int(sample_rate),
            float(discard_seconds),
        ),
        dtype=np.float32,
    )


def remove_clicks(
    audio: Any,
    threshold_sigma: float = 4.0,
    max_click_fraction: float = 0.1,
) -> np.ndarray:
    extension = _require_extension("Rust click removal")
    return np.asarray(
        extension.remove_clicks(
            _as_float32(audio),
            float(threshold_sigma),
            float(max_click_fraction),
        ),
        dtype=np.float32,
    )


def harmonic_comb_response(
    frame: Any,
    sample_rate: int,
    window: Any,
    candidates: Any,
    weights: Any,
    min_harmonics: int,
) -> tuple[float, float, bool]:
    extension = _require_extension("Rust harmonic comb")
    score, flatness, valid = extension.harmonic_comb_response(
        _as_float32(frame),
        int(sample_rate),
        _as_float32(window),
        np.asarray(candidates, dtype=np.float64),
        np.asarray(weights, dtype=np.float64),
        int(min_harmonics),
    )
    return float(score), float(flatness), bool(valid)


def autocorrelation_pitch(
    audio: Any,
    sample_rate: int,
    f_min: float = 30.0,
    f_max: float = 2000.0,
) -> float:
    extension = _require_extension("Rust autocorrelation pitch")
    return float(
        extension.autocorrelation_pitch(
            _as_float32(audio),
            int(sample_rate),
            float(f_min),
            float(f_max),
        )
    )


def autocorrelation_has_peak_near(
    audio: Any,
    sample_rate: int,
    frequency: float,
    *,
    tolerance_ratio: float = 0.15,
    threshold_ratio: float = 0.20,
    f_min: float = 30.0,
    f_max: float = 2000.0,
) -> bool:
    extension = _require_extension("Rust autocorrelation peak check")
    return bool(
        extension.autocorrelation_has_peak_near(
            _as_float32(audio),
            int(sample_rate),
            float(frequency),
            float(tolerance_ratio),
            float(threshold_ratio),
            float(f_min),
            float(f_max),
        )
    )


def fft_has_peak_near(
    audio: Any,
    sample_rate: int,
    frequency: float,
    *,
    tolerance_ratio: float = 0.10,
    threshold_ratio: float = 0.20,
) -> bool:
    extension = _require_extension("Rust FFT peak check")
    return bool(
        extension.fft_has_peak_near(
            _as_float32(audio),
            int(sample_rate),
            float(frequency),
            float(tolerance_ratio),
            float(threshold_ratio),
        )
    )


def nn_pitch_is_corroborated(
    audio: Any,
    sample_rate: int,
    nn_frequency: float,
    *,
    f_min: float = 30.0,
    f_max: float = 2000.0,
    acf_tolerance_ratio: float = 0.15,
    fft_tolerance_ratio: float = 0.10,
    fft_threshold_ratio: float = 0.20,
    acf_peak_threshold_ratio: float = 0.20,
) -> bool:
    extension = _require_extension("Rust pitch corroboration")
    return bool(
        extension.nn_pitch_is_corroborated(
            _as_float32(audio),
            int(sample_rate),
            float(nn_frequency),
            float(f_min),
            float(f_max),
            float(acf_tolerance_ratio),
            float(fft_tolerance_ratio),
            float(fft_threshold_ratio),
            float(acf_peak_threshold_ratio),
        )
    )


def acquire_audio(
    cfg: Any, noise_rms: float, timeout: float | None = None
) -> np.ndarray | None:
    extension = _require_extension("Rust audio capture")
    comb = getattr(cfg, "comb_trigger", None)
    captured = extension.acquire_audio(
        int(cfg.sample_rate),
        float(cfg.max_record_seconds),
        _optional_float(getattr(cfg, "expected_f0", None)),
        float(cfg.snr_threshold_db),
        str(getattr(cfg, "trigger_mode", "snr")),
        _optional_float(getattr(cfg, "idle_timeout", None)),
        float(noise_rms),
        _optional_float(timeout),
        _optional_int(getattr(comb, "frame_size", None)),
        _optional_int(getattr(comb, "hop_size", None)),
        _optional_int(getattr(comb, "candidate_count", None)),
        _optional_int(getattr(comb, "harmonic_weight_count", None)),
        _optional_int(getattr(comb, "min_harmonics", None)),
        _optional_float(getattr(comb, "on_rmax", None)),
        _optional_float(getattr(comb, "off_rmax", None)),
        _optional_float(getattr(comb, "sfm_max", None)),
        _optional_int(getattr(comb, "on_frames", None)),
        _optional_int(getattr(comb, "off_frames", None)),
    )
    if captured is None:
        return None
    return np.asarray(captured, dtype=np.float32)


def analyze_pesto_onnx(
    audio: Any,
    sample_rate: int,
    expected_frequency: float | None = None,
    *,
    include_activations: bool = False,
    model_name: str = "mir-1k_g7",
) -> dict[str, Any] | None:
    if not should_try_rust_pesto():
        return None
    extension = _require_extension("Rust PESTO ONNX")
    paths = find_pesto_onnx_paths(model_name)
    if paths is None:
        if should_require_rust_pesto():
            raise FileNotFoundError(
                f"Rust PESTO ONNX artifacts not found for {model_name!r}"
            )
        return None

    encoder_path, confidence_path, manifest_path = paths
    raw = extension.analyze_pesto_onnx(
        _as_float32(audio),
        int(sample_rate),
        _optional_float(expected_frequency),
        bool(include_activations),
        str(encoder_path),
        str(confidence_path),
        str(manifest_path),
    )
    result = dict(raw)
    result["frame_times"] = np.asarray(result["frame_times"], dtype=np.float32)
    result["predicted_frequencies"] = np.asarray(
        result["predicted_frequencies"], dtype=np.float32
    )
    result["frame_confidences"] = np.asarray(
        result["frame_confidences"], dtype=np.float32
    )
    activation_map = result.get("activation_map")
    activation_shape = result.pop("activation_map_shape", None)
    if activation_map is None or activation_shape is None:
        result["activation_map"] = None
    else:
        result["activation_map"] = np.asarray(activation_map, dtype=np.float32).reshape(
            tuple(map(int, activation_shape))
        )
    activation_axis = result.get("activation_freq_axis")
    result["activation_freq_axis"] = (
        None
        if activation_axis is None
        else np.asarray(activation_axis, dtype=np.float32)
    )
    return result


def find_pesto_onnx_paths(model_name: str) -> tuple[Path, Path, Path] | None:
    filename_prefix = str(model_name)
    candidates = [
        Path(__file__).resolve().parents[2] / "dune_tension" / "data" / "pesto_onnx",
        Path(__file__).resolve().parent / "pesto_onnx",
        Path.cwd() / "dune_tension" / "data" / "pesto_onnx",
    ]
    for directory in candidates:
        encoder = directory / f"{filename_prefix}_encoder.onnx"
        confidence = directory / f"{filename_prefix}_confidence.onnx"
        manifest = directory / f"{filename_prefix}_manifest.json"
        if encoder.exists() and confidence.exists() and manifest.exists():
            return encoder, confidence, manifest
    return None


def _as_float32(audio: Any) -> np.ndarray:
    return np.asarray(audio, dtype=np.float32).reshape(-1)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
