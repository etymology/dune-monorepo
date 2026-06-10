"""PESTO-confidence trigger: record while PESTO reports voiced audio.

Mirrors :func:`spectrum_analysis.comb_trigger.record_with_harmonic_comb`, but
gates on PESTO's own per-window confidence instead of the harmonic comb score.
PESTO inference on a ~0.35 s window costs ~60 ms warm, so the trigger
re-evaluates every ``eval_period_seconds`` rather than every hop.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
import logging
import threading
import time

import numpy as np

from spectrum_analysis.audio_sources import MicSource, sd
from spectrum_analysis.pesto_analysis import analyze_audio_with_pesto

LOGGER = logging.getLogger(__name__)


@dataclass
class PestoTriggerConfig:
    """Runtime configuration for the PESTO confidence trigger."""

    window_seconds: float = 0.35
    eval_period_seconds: float = 0.10
    hop_size: int = 1024
    on_confidence: float = 0.5
    off_confidence: float = 0.3
    on_windows: int = 1
    off_windows: int = 3


def warm_up_pesto(expected_f0: float, sample_rate: int, window_seconds: float) -> None:
    """Load the PESTO model used by the trigger (first inference is slow)."""

    samples = max(1024, int(window_seconds * sample_rate))
    t = np.arange(samples, dtype=np.float64) / sample_rate
    tone = (0.1 * np.sin(2.0 * np.pi * expected_f0 * t)).astype(np.float32)
    analyze_audio_with_pesto(tone, sample_rate, expected_frequency=expected_f0)


def record_with_pesto_trigger(
    *,
    expected_f0: float,
    sample_rate: int,
    max_record_seconds: float,
    timeout_seconds: float | None = None,
    cfg: PestoTriggerConfig = PestoTriggerConfig(),
    recording_started_callback: Callable[[], None] | None = None,
    stop_event: threading.Event | None = None,
    frame_callback: Callable[[float, float, float, bool], None] | None = None,
) -> np.ndarray | None:
    """Record audio gated on PESTO confidence.

    Waits until PESTO confidence over a sliding window reaches
    ``cfg.on_confidence`` for ``cfg.on_windows`` consecutive evaluations
    (the pre-trigger window is included in the capture), then records until
    confidence stays below ``cfg.off_confidence`` for ``cfg.off_windows``
    evaluations, the capture reaches ``max_record_seconds``, or the overall
    ``timeout_seconds`` elapses.

    ``frame_callback`` (if given) receives
    ``(elapsed_seconds, confidence, frequency_hz, triggered)`` per evaluation.

    Returns the captured audio, or ``None`` if the trigger never fired.
    """

    start_time = time.time()
    if timeout_seconds is None:
        timeout_seconds = max_record_seconds
    if sd is None:
        raise RuntimeError(
            "sounddevice is required for microphone recording but is not available."
        )

    hop = max(1, int(cfg.hop_size))
    window_samples = max(1024, int(cfg.window_seconds * sample_rate))
    eval_samples = max(hop, int(cfg.eval_period_seconds * sample_rate))
    on_windows = max(1, int(cfg.on_windows))
    off_windows = max(1, int(cfg.off_windows))

    source = MicSource(sample_rate, hop)
    source.start()
    LOGGER.info("Listening for audio events (PESTO confidence trigger)...")

    collected: list[np.ndarray] = []
    max_samples = int(max_record_seconds * sample_rate)
    collected_samples = 0

    # Rolling buffer of the latest audio: serves as the PESTO analysis window
    # and as the pre-trigger audio included in the capture.
    recent_chunks: deque[np.ndarray] = deque()
    recent_samples = 0

    samples_since_eval = 0
    on_counter = 0
    off_counter = 0
    triggered = False

    try:
        while collected_samples < max_samples:
            if stop_event is not None and stop_event.is_set():
                LOGGER.info("Audio acquisition interrupted (PESTO trigger).")
                break
            chunk = source.read()
            if chunk.size == 0:
                continue
            if chunk.dtype != np.float32:
                chunk = chunk.astype(np.float32, copy=False)

            if triggered:
                collected.append(chunk)
                collected_samples += len(chunk)

            recent_chunks.append(chunk)
            recent_samples += len(chunk)
            while recent_samples - len(recent_chunks[0]) >= window_samples:
                removed = recent_chunks.popleft()
                recent_samples -= len(removed)

            samples_since_eval += len(chunk)
            if samples_since_eval >= eval_samples and recent_samples >= window_samples:
                samples_since_eval = 0
                window = np.concatenate(list(recent_chunks))[-window_samples:]
                analysis = analyze_audio_with_pesto(
                    window, sample_rate, expected_frequency=expected_f0
                )
                confidence = float(analysis.confidence)
                if not np.isfinite(confidence):
                    confidence = 0.0

                if not triggered:
                    if confidence >= cfg.on_confidence:
                        on_counter += 1
                    else:
                        on_counter = 0
                    if on_counter >= on_windows:
                        triggered = True
                        on_counter = 0
                        off_counter = 0
                        pre_audio = np.concatenate(list(recent_chunks))
                        collected.append(pre_audio)
                        collected_samples += pre_audio.size
                        LOGGER.info("Recording started (PESTO trigger).")
                        if recording_started_callback is not None:
                            recording_started_callback()
                else:
                    if confidence < cfg.off_confidence:
                        off_counter += 1
                    else:
                        off_counter = 0

                if frame_callback is not None:
                    frame_callback(
                        time.time() - start_time,
                        confidence,
                        float(analysis.frequency),
                        triggered,
                    )

                if triggered and off_counter >= off_windows:
                    LOGGER.info("Recording stopped (PESTO trigger released).")
                    break

            if collected_samples >= max_samples:
                LOGGER.warning("Max recording length reached.")
                break
            if time.time() > start_time + timeout_seconds:
                LOGGER.warning("Recording timed out.")
                break
    finally:
        source.stop()

    if not collected:
        LOGGER.warning("No audio captured above the PESTO confidence threshold.")
        return None

    return np.concatenate(collected).astype(np.float32)


__all__ = [
    "PestoTriggerConfig",
    "record_with_pesto_trigger",
    "warm_up_pesto",
]
