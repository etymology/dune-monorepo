"""Export PESTO CNN encoder and confidence classifier to ONNX format.

This script exports the Resnet1d encoder and ConfidenceClassifier from PESTO to ONNX,
which can then be used with ONNX Runtime for faster inference.

The HCQT preprocessing is kept in Python to avoid dynamic sampling rate issues.
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import sys

import numpy as np
import torch
import torch.onnx


_LOGGER = logging.getLogger(__name__)


def _load_pesto_model(
    model_name: str, step_size: float, sampling_rate: int
) -> torch.nn.Module:
    """Load PESTO model using the pesto-pitch library."""
    try:
        from pesto import load_model
    except ImportError as e:
        _LOGGER.error("Failed to import pesto-pitch: %s", e)
        sys.exit(1)

    model = load_model(
        model_name,
        step_size=float(step_size),
        sampling_rate=int(sampling_rate),
        streaming=False,
        max_batch_size=1,
    )
    model.eval()
    return model


def export_encoder_to_onnx(
    model: torch.nn.Module,
    output_path: str,
    num_harmonics: int = 6,
    num_freq_bins: int = 216,
    num_timesteps: int = 100,
    opset_version: int = 17,
) -> None:
    """Export the Resnet1d encoder to ONNX format.

    Args:
        model: PESTO model containing the encoder
        output_path: Path where ONNX model will be saved
        num_harmonics: Number of harmonic channels in HCQT
        num_freq_bins: Number of frequency bins in HCQT
        num_timesteps: Number of time steps (dynamic in practice)
        opset_version: ONNX opset version
    """
    encoder = model.encoder
    encoder.eval()

    input_shape = (num_timesteps, num_harmonics, num_freq_bins)
    dummy_input = torch.randn(*input_shape, dtype=torch.float32)

    input_names = ["hcqt_features"]
    output_names = ["activations"]

    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    _LOGGER.info("Exporting encoder to %s...", output_path)
    _LOGGER.info("Input shape: %s", input_shape)

    torch.onnx.export(
        encoder,
        dummy_input,
        output_path,
        input_names=input_names,
        output_names=output_names,
        dynamic_axes={
            "hcqt_features": {0: "num_timesteps"},
            "activations": {0: "num_timesteps"},
        },
        opset_version=opset_version,
        do_constant_folding=True,
    )

    _LOGGER.info("Successfully exported encoder to %s", output_path)


def export_confidence_to_onnx(
    model: torch.nn.Module,
    output_path: str,
    num_harmonics: int = 6,
    num_freq_bins: int = 216,
    num_timesteps: int = 100,
    opset_version: int = 17,
) -> None:
    """Export the confidence classifier to ONNX format.

    Args:
        model: PESTO model containing the confidence classifier
        output_path: Path where ONNX model will be saved
        num_harmonics: Number of harmonic channels in HCQT
        num_freq_bins: Number of frequency bins in HCQT
        num_timesteps: Number of time steps (dynamic in practice)
        opset_version: ONNX opset version
    """
    confidence = model.confidence
    confidence.eval()

    input_shape = (num_timesteps, num_harmonics, num_freq_bins)
    dummy_input = torch.randn(*input_shape, dtype=torch.float32)

    input_names = ["energy"]
    output_names = ["confidence"]

    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    _LOGGER.info("Exporting confidence classifier to %s...", output_path)
    _LOGGER.info("Input shape: %s", input_shape)

    torch.onnx.export(
        confidence,
        dummy_input,
        output_path,
        input_names=input_names,
        output_names=output_names,
        dynamic_axes={
            "energy": {0: "num_timesteps"},
            "confidence": {0: "num_timesteps"},
        },
        opset_version=opset_version,
        do_constant_folding=True,
    )

    _LOGGER.info("Successfully exported confidence classifier to %s", output_path)


def get_model_hparams(model: torch.nn.Module) -> dict:
    """Extract hyperparameters from PESTO model.

    Returns:
        Dictionary with model hyperparameters needed for ONNX export
    """
    preprocessor = model.preprocessor
    hcqt_kwargs = preprocessor.hcqt_kwargs

    bins_per_semitone = hcqt_kwargs.get("bins_per_semitone", 2)
    fmin = hcqt_kwargs.get("fmin", 32.7)
    num_octaves = hcqt_kwargs.get("n_octaves", 6)

    num_freq_bins = 12 * bins_per_semitone * num_octaves
    num_harmonics = hcqt_kwargs.get("harmonics", 6)

    return {
        "num_harmonics": num_harmonics,
        "num_freq_bins": num_freq_bins,
        "bins_per_semitone": bins_per_semitone,
        "fmin": fmin,
        "num_octaves": num_octaves,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export PESTO CNN encoder and confidence classifier to ONNX format"
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default="mir-1k_g7",
        help="PESTO model name (default: mir-1k_g7)",
    )
    parser.add_argument(
        "--step-size",
        type=float,
        default=5.0,
        help="Step size in milliseconds (default: 5.0)",
    )
    parser.add_argument(
        "--sampling-rate",
        type=int,
        default=44100,
        help="Sampling rate in Hz (default: 44100)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for ONNX models (default: dune_tension/data/pesto_onnx)",
    )
    parser.add_argument(
        "--opset-version",
        type=int,
        default=17,
        help="ONNX opset version (default: 17)",
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

    if args.output_dir is None:
        script_dir = Path(__file__).resolve().parent
        repo_root = script_dir.parent.parent
        args.output_dir = str(repo_root / "dune_tension" / "data" / "pesto_onnx")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    _LOGGER.info("Loading PESTO model: %s", args.model_name)
    model = _load_pesto_model(args.model_name, args.step_size, args.sampling_rate)

    hparams = get_model_hparams(model)
    _LOGGER.info("Model hyperparameters: %s", hparams)

    encoder_path = output_dir / f"{args.model_name}_encoder.onnx"
    confidence_path = output_dir / f"{args.model_name}_confidence.onnx"

    try:
        export_encoder_to_onnx(
            model,
            str(encoder_path),
            num_harmonics=hparams["num_harmonics"],
            num_freq_bins=hparams["num_freq_bins"],
            opset_version=args.opset_version,
        )
    except Exception as e:
        _LOGGER.error("Failed to export encoder: %s", e)
        return 1

    try:
        export_confidence_to_onnx(
            model,
            str(confidence_path),
            num_harmonics=hparams["num_harmonics"],
            num_freq_bins=hparams["num_freq_bins"],
            opset_version=args.opset_version,
        )
    except Exception as e:
        _LOGGER.error("Failed to export confidence classifier: %s", e)
        return 1

    _LOGGER.info("Export complete. Models saved to %s", output_dir)
    _LOGGER.info("  - Encoder: %s", encoder_path)
    _LOGGER.info("  - Confidence: %s", confidence_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
