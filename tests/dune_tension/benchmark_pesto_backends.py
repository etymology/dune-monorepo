"""Benchmark PESTO backends (PyTorch vs ONNX Runtime).

This script compares the performance of the PyTorch and ONNX Runtime backends
for PESTO pitch detection, measuring latency and accuracy.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import Any

import numpy as np


_LOGGER = logging.getLogger(__name__)


def generate_test_audio(
    duration: float, sample_rate: int, frequency: float = 440.0
) -> np.ndarray:
    """Generate synthetic audio for testing.

    Args:
        duration: Duration in seconds
        sample_rate: Sample rate in Hz
        frequency: Fundamental frequency in Hz

    Returns:
        Audio waveform
    """
    t = np.arange(int(duration * sample_rate)) / float(sample_rate)
    audio = np.sin(2 * np.pi * frequency * t)

    harmonics = [2, 3, 4, 5]
    for h in harmonics:
        audio += 0.5 / h * np.sin(2 * np.pi * frequency * h * t)

    audio = audio.astype(np.float32)
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak

    return audio


def benchmark_pytorch_backend(
    audio: np.ndarray,
    sample_rate: int,
    num_iterations: int = 10,
    warmup_iterations: int = 3,
) -> dict[str, Any]:
    """Benchmark PyTorch backend.

    Args:
        audio: Audio waveform
        sample_rate: Sample rate in Hz
        num_iterations: Number of benchmark iterations
        warmup_iterations: Number of warmup iterations

    Returns:
        Dictionary with benchmark results
    """
    _LOGGER.info("Benchmarking PyTorch backend...")

    try:
        from spectrum_analysis.pesto_analysis import analyze_audio_with_pesto
    except ImportError as e:
        _LOGGER.error("Failed to import PyTorch backend: %s", e)
        return {"error": str(e)}

    import os

    original_backend = os.environ.get("PESTO_BACKEND", "")
    os.environ["PESTO_BACKEND"] = "pytorch"

    try:
        for _ in range(warmup_iterations):
            _ = analyze_audio_with_pesto(audio, sample_rate, include_activations=False)

        latencies = []
        frequencies = []
        confidences = []

        for _ in range(num_iterations):
            start_time = time.perf_counter()
            result = analyze_audio_with_pesto(
                audio, sample_rate, include_activations=False
            )
            end_time = time.perf_counter()

            latency_ms = (end_time - start_time) * 1000.0
            latencies.append(latency_ms)
            frequencies.append(result.frequency)
            confidences.append(result.confidence)

        return {
            "latencies_ms": latencies,
            "mean_latency_ms": float(np.mean(latencies)),
            "std_latency_ms": float(np.std(latencies)),
            "min_latency_ms": float(np.min(latencies)),
            "max_latency_ms": float(np.max(latencies)),
            "frequencies": frequencies,
            "mean_frequency": float(np.mean(frequencies)),
            "confidences": confidences,
            "mean_confidence": float(np.mean(confidences)),
            "success": True,
        }
    finally:
        if original_backend:
            os.environ["PESTO_BACKEND"] = original_backend
        else:
            os.environ.pop("PESTO_BACKEND", None)


def benchmark_onnx_backend(
    audio: np.ndarray,
    sample_rate: int,
    num_iterations: int = 10,
    warmup_iterations: int = 3,
) -> dict[str, Any]:
    """Benchmark ONNX Runtime backend.

    Args:
        audio: Audio waveform
        sample_rate: Sample rate in Hz
        num_iterations: Number of benchmark iterations
        warmup_iterations: Number of warmup iterations

    Returns:
        Dictionary with benchmark results
    """
    _LOGGER.info("Benchmarking ONNX Runtime backend...")

    try:
        from spectrum_analysis import pesto_onnx
    except ImportError as e:
        _LOGGER.error("Failed to import ONNX backend: %s", e)
        return {"error": str(e)}

    if not pesto_onnx.use_onnx_backend():
        _LOGGER.error("ONNX backend is not available")
        return {"error": "ONNX backend not available"}

    try:
        for _ in range(warmup_iterations):
            _ = pesto_onnx.analyze_audio_with_onnx(
                audio, sample_rate, include_activations=False
            )

        latencies = []
        frequencies = []
        confidences = []

        for _ in range(num_iterations):
            start_time = time.perf_counter()
            result = pesto_onnx.analyze_audio_with_onnx(
                audio, sample_rate, include_activations=False
            )
            end_time = time.perf_counter()

            latency_ms = (end_time - start_time) * 1000.0
            latencies.append(latency_ms)
            frequencies.append(result.frequency)
            confidences.append(result.confidence)

        return {
            "latencies_ms": latencies,
            "mean_latency_ms": float(np.mean(latencies)),
            "std_latency_ms": float(np.std(latencies)),
            "min_latency_ms": float(np.min(latencies)),
            "max_latency_ms": float(np.max(latencies)),
            "frequencies": frequencies,
            "mean_frequency": float(np.mean(frequencies)),
            "confidences": confidences,
            "mean_confidence": float(np.mean(confidences)),
            "success": True,
        }
    except Exception as e:
        _LOGGER.error("ONNX benchmark failed: %s", e)
        return {"error": str(e)}


def compare_results(
    pytorch_results: dict[str, Any], onnx_results: dict[str, Any]
) -> dict[str, Any]:
    """Compare PyTorch and ONNX Runtime results.

    Args:
        pytorch_results: Results from PyTorch backend
        onnx_results: Results from ONNX Runtime backend

    Returns:
        Dictionary with comparison results
    """
    if not pytorch_results.get("success") or not onnx_results.get("success"):
        return {"error": "One or both backends failed"}

    pytorch_freq = np.mean(pytorch_results["frequencies"])
    onnx_freq = np.mean(onnx_results["frequencies"])
    freq_diff = abs(pytorch_freq - onnx_freq)
    freq_diff_pct = (freq_diff / max(abs(pytorch_freq), 1e-6)) * 100.0

    pytorch_conf = np.mean(pytorch_results["confidences"])
    onnx_conf = np.mean(onnx_results["confidences"])
    conf_diff = abs(pytorch_conf - onnx_conf)

    speedup = pytorch_results["mean_latency_ms"] / max(
        onnx_results["mean_latency_ms"], 1e-6
    )

    return {
        "frequency_diff_hz": float(freq_diff),
        "frequency_diff_pct": float(freq_diff_pct),
        "confidence_diff": float(conf_diff),
        "speedup": float(speedup),
        "pytorch_faster": pytorch_results["mean_latency_ms"]
        < onnx_results["mean_latency_ms"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark PESTO backends (PyTorch vs ONNX Runtime)"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.5,
        help="Audio duration in seconds (default: 0.5)",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=44100,
        help="Sample rate in Hz (default: 44100)",
    )
    parser.add_argument(
        "--frequency",
        type=float,
        default=440.0,
        help="Test frequency in Hz (default: 440.0)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=10,
        help="Number of benchmark iterations (default: 10)",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=3,
        help="Number of warmup iterations (default: 3)",
    )
    parser.add_argument(
        "--backend",
        type=str,
        choices=["pytorch", "onnx", "both"],
        default="both",
        help="Which backend to benchmark (default: both)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    _LOGGER.info(
        "Generating test audio: %.3f s at %d Hz, %s Hz tone",
        args.duration,
        args.sample_rate,
        args.frequency,
    )
    audio = generate_test_audio(args.duration, args.sample_rate, args.frequency)

    pytorch_results = {}
    onnx_results = {}

    if args.backend in ("pytorch", "both"):
        pytorch_results = benchmark_pytorch_backend(
            audio, args.sample_rate, args.iterations, args.warmup
        )

    if args.backend in ("onnx", "both"):
        onnx_results = benchmark_onnx_backend(
            audio, args.sample_rate, args.iterations, args.warmup
        )

    print("\n" + "=" * 80)
    print("PESTO Backend Benchmark Results")
    print("=" * 80)

    if pytorch_results.get("success"):
        print("\nPyTorch Backend:")
        print(f"  Mean latency: {pytorch_results['mean_latency_ms']:.2f} ms")
        print(f"  Std latency:  {pytorch_results['std_latency_ms']:.2f} ms")
        print(f"  Min latency:  {pytorch_results['min_latency_ms']:.2f} ms")
        print(f"  Max latency:  {pytorch_results['max_latency_ms']:.2f} ms")
        print(f"  Mean frequency: {pytorch_results['mean_frequency']:.2f} Hz")
        print(f"  Mean confidence: {pytorch_results['mean_confidence']:.4f}")
    else:
        print("\nPyTorch Backend: FAILED")
        if "error" in pytorch_results:
            print(f"  Error: {pytorch_results['error']}")

    if onnx_results.get("success"):
        print("\nONNX Runtime Backend:")
        print(f"  Mean latency: {onnx_results['mean_latency_ms']:.2f} ms")
        print(f"  Std latency:  {onnx_results['std_latency_ms']:.2f} ms")
        print(f"  Min latency:  {onnx_results['min_latency_ms']:.2f} ms")
        print(f"  Max latency:  {onnx_results['max_latency_ms']:.2f} ms")
        print(f"  Mean frequency: {onnx_results['mean_frequency']:.2f} Hz")
        print(f"  Mean confidence: {onnx_results['mean_confidence']:.4f}")
    else:
        print("\nONNX Runtime Backend: FAILED")
        if "error" in onnx_results:
            print(f"  Error: {onnx_results['error']}")

    if pytorch_results.get("success") and onnx_results.get("success"):
        comparison = compare_results(pytorch_results, onnx_results)
        print("\nComparison:")
        print(
            f"  Frequency difference: {comparison['frequency_diff_hz']:.2f} Hz ({comparison['frequency_diff_pct']:.2f}%)"
        )
        print(f"  Confidence difference: {comparison['confidence_diff']:.4f}")
        print(f"  Speedup: {comparison['speedup']:.2f}x")
        if comparison["pytorch_faster"]:
            print(f"  PyTorch is {comparison['speedup']:.2f}x faster than ONNX Runtime")
        else:
            print(f"  ONNX Runtime is {comparison['speedup']:.2f}x faster than PyTorch")

    print("\n" + "=" * 80)

    if pytorch_results.get("success") and onnx_results.get("success"):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
