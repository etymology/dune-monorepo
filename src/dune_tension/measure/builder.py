from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Any, Callable, ContextManager, Optional

import numpy as np

from dune_tension.audio_store import AudioStore
from dune_tension.config import MEASUREMENT_WIGGLE_CONFIG
from dune_tension.services import (
    RuntimeBundle,
    build_runtime_bundle,
    resolve_runtime_options,
)
from dune_tension.tensiometer_functions import WirePositionProvider, make_config

if TYPE_CHECKING:
    from dune_tension.tensiometer import Tensiometer


def build_tensiometer(
    *,
    apa_name: str,
    layer: str,
    side: str,
    flipped: bool = False,
    a_taped: bool = False,
    b_taped: bool = False,
    stop_event: Optional[threading.Event] = None,
    samples_per_wire: int = 1,
    confidence_threshold: float = 2,
    confidence_source: str = "neural_net",
    save_audio: bool = True,
    plot_audio: bool = False,
    record_duration: float = 0.5,
    measuring_duration: float = 10.0,
    snr: float = 1,
    spoof: bool = False,
    spoof_movement: bool = False,
    wiggle_y_sigma_mm: float = MEASUREMENT_WIGGLE_CONFIG.y_sigma_mm,
    sweeping_wiggle: bool = False,
    sweeping_wiggle_span_mm: float = 1.0,
    focus_wiggle_sigma_quarter_us: float = (
        MEASUREMENT_WIGGLE_CONFIG.focus_sigma_quarter_us
    ),
    strum: Optional[Callable[[], None]] = None,
    measurement_session: Optional[Callable[[], ContextManager[Any]]] = None,
    focus_wiggle: Optional[Callable[[float], None]] = None,
    focus_position_getter: Optional[Callable[[], int]] = None,
    focus_range_getter: Optional[Callable[[], tuple[int, int] | None]] = None,
    legacy_tension_condition: str | None = None,
    use_manual_focus: bool = False,
    manual_focus_target: int | None = None,
    quiet_waiter: Optional[Callable[[], None]] = None,
    estimated_time_callback: Optional[Callable[[str], None]] = None,
    audio_sample_callback: Optional[Callable[[Any, int, Any | None], None]] = None,
    summary_refresh_callback: Optional[Callable[[Any], None]] = None,
    wire_preview_callback: Optional[Callable[[int, float, float], None]] = None,
    runtime_bundle: RuntimeBundle | None = None,
    wire_position_provider: WirePositionProvider | None = None,
    audio_store: AudioStore | None = None,
    use_harmonic_comb_trigger: bool = False,
) -> "Tensiometer":
    from dune_tension.tensiometer import Tensiometer

    config = make_config(
        apa_name=apa_name,
        layer=layer,
        side=side,
        flipped=flipped,
        samples_per_wire=samples_per_wire,
        confidence_threshold=confidence_threshold,
        confidence_source=confidence_source,
        save_audio=save_audio,
        spoof=spoof,
        plot_audio=plot_audio,
        record_duration=record_duration,
        measuring_duration=measuring_duration,
    )

    active_runtime = runtime_bundle
    if active_runtime is None:
        options = resolve_runtime_options()
        if spoof:
            options = type(options)(
                spoof_audio=True,
                spoof_movement=options.spoof_movement,
                spoof_servo=options.spoof_servo,
                spoof_valve=options.spoof_valve,
            )
        if spoof_movement:
            options = type(options)(
                spoof_audio=options.spoof_audio,
                spoof_movement=True,
                spoof_servo=options.spoof_servo,
                spoof_valve=options.spoof_valve,
            )
        active_runtime = build_runtime_bundle(options)

    active_strum = strum or active_runtime.strum
    active_measurement_session = (
        measurement_session or active_runtime.sensor_power_session
    )
    active_focus_wiggle = focus_wiggle or getattr(
        active_runtime.servo_controller,
        "nudge_focus",
        None,
    )
    active_focus_position_getter = focus_position_getter
    if active_focus_position_getter is None:

        def active_focus_position_getter() -> int:
            return int(getattr(active_runtime.servo_controller, "focus_position", 0))

    active_focus_range_getter = focus_range_getter
    if active_focus_range_getter is None:

        def active_focus_range_getter() -> tuple[int, int]:
            low = 4000
            high = 8000
            try:
                servo = getattr(active_runtime.servo_controller, "servo", None)
                get_min = getattr(servo, "getMin", None)
                get_max = getattr(servo, "getMax", None)
                if callable(get_min):
                    low = int(get_min(1) or low)
                if callable(get_max):
                    high = int(get_max(1) or high)
            except Exception:
                return (4000, 8000)
            if low > high:
                return (4000, 8000)
            return (low, high)

    active_quiet_waiter = quiet_waiter
    if active_quiet_waiter is None:

        def active_quiet_waiter() -> None:
            try:
                from spectrum_analysis.audio_sources import MicSource
            except Exception:
                return

            sample_rate = max(
                int(getattr(active_runtime.audio, "samplerate", 0) or 0), 1
            )
            noise_floor = float(
                getattr(active_runtime.audio, "noise_threshold", 0.0) or 0.0
            )
            quiet_threshold = max(noise_floor * 1.25, noise_floor + 1e-4, 1e-4)
            quiet_seconds_required = 1.0
            quiet_seconds = 0.0
            chunk_size = max(int(sample_rate * 0.01), 128)
            source = MicSource(sample_rate, chunk_size)
            deadline = time.monotonic() + max(quiet_seconds_required + 1.0, 2.0)
            try:
                source.start()
                while time.monotonic() < deadline:
                    chunk = source.read()
                    if chunk.size == 0:
                        continue
                    chunk_rms = float(
                        np.sqrt(np.mean(np.square(chunk, dtype=np.float64)) + 1e-12)
                    )
                    chunk_seconds = float(chunk.size) / float(sample_rate)
                    if chunk_rms <= quiet_threshold:
                        quiet_seconds += chunk_seconds
                        if quiet_seconds >= quiet_seconds_required:
                            return
                    else:
                        quiet_seconds = 0.0
            except Exception:
                return
            finally:
                try:
                    source.stop()
                except Exception:
                    pass

    return Tensiometer(
        apa_name=apa_name,
        layer=layer,
        side=side,
        flipped=flipped,
        a_taped=a_taped,
        b_taped=b_taped,
        stop_event=stop_event,
        samples_per_wire=samples_per_wire,
        confidence_threshold=confidence_threshold,
        confidence_source=confidence_source,
        save_audio=save_audio,
        plot_audio=plot_audio,
        record_duration=record_duration,
        measuring_duration=measuring_duration,
        snr=snr,
        spoof=spoof,
        spoof_movement=spoof_movement,
        wiggle_y_sigma_mm=wiggle_y_sigma_mm,
        sweeping_wiggle=sweeping_wiggle,
        sweeping_wiggle_span_mm=sweeping_wiggle_span_mm,
        focus_wiggle_sigma_quarter_us=focus_wiggle_sigma_quarter_us,
        strum=active_strum,
        measurement_session=active_measurement_session,
        focus_wiggle=active_focus_wiggle,
        focus_position_getter=active_focus_position_getter,
        focus_range_getter=active_focus_range_getter,
        legacy_tension_condition=legacy_tension_condition,
        use_manual_focus=use_manual_focus,
        manual_focus_target=manual_focus_target,
        quiet_waiter=active_quiet_waiter,
        estimated_time_callback=estimated_time_callback,
        audio_sample_callback=audio_sample_callback,
        summary_refresh_callback=summary_refresh_callback,
        wire_preview_callback=wire_preview_callback,
        config=config,
        motion=active_runtime.motion,
        audio=active_runtime.audio,
        repository=active_runtime.build_repository(config.data_path),
        wire_position_provider=(
            wire_position_provider
            or active_runtime.wire_position_provider
            or WirePositionProvider()
        ),
        audio_store=audio_store or getattr(active_runtime, "audio_store", None),
        use_harmonic_comb_trigger=use_harmonic_comb_trigger,
    )
