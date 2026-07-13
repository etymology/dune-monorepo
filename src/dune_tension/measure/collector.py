from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable

from dune_tension.audio_store import AudioRecordingMeta
from dune_tension.config import MEASUREMENT_WIGGLE_CONFIG
from dune_tension.measure.analysis import AudioAcquisitionConfig, DeferredPitchSample
from dune_tension.results import TensionResult

LOGGER = logging.getLogger(__name__)

_STRUM_LOOP_INTERVAL_SECONDS = 0.5


@dataclass(frozen=True)
class WireRequest:
    """One wire's measurement target -- the former _collect_samples params."""

    wire_number: int
    length: float
    start_time: float
    wire_y: float
    wire_x: float
    zone: int | None = None
    return_to_center: bool = True


class WireOptimizer:
    """Search XY+focus space for the best sample of a single wire.

    This is the former ``Tensiometer._collect_samples`` loop, carved into its
    own unit. It reads live host state/collaborators through ``host`` and takes
    the monkeypatch-sensitive module globals (acquire_audio, wire_equation,
    tension_plausible, check_stop_event) as injected callables so the engine's
    test seams keep working. Construct one per wire; ``collect()`` returns the
    candidate list (or None if the stop event fires mid-run).
    """

    def __init__(
        self,
        host: Any,
        request: WireRequest,
        *,
        acquire_audio: Callable[..., Any],
        wire_equation: Callable[..., Any],
        tension_plausible: Callable[[float], bool],
        check_stop_event: Callable[..., bool],
    ) -> None:
        self._host = host
        self._r = request
        self._acquire_audio = acquire_audio
        self._wire_equation = wire_equation
        self._tension_plausible = tension_plausible
        self._check_stop_event = check_stop_event

    def collect(self) -> list[TensionResult] | None:
        host = self._host
        wire_number = self._r.wire_number
        length = self._r.length
        start_time = self._r.start_time
        wire_y = self._r.wire_y
        wire_x = self._r.wire_x
        zone = self._r.zone
        return_to_center = self._r.return_to_center
        expected_frequency = self._wire_equation(length=length)["frequency"]
        amplitude_mode = host.config.confidence_source == "signal_amplitude"
        measuring_timeout = host.config.measuring_duration
        candidate_wires: list[TensionResult] = []
        measured_zone = int(zone) if zone is not None else None

        recording_started_event = threading.Event()

        def on_recording_started() -> None:
            recording_started_event.set()
            host._record_wire_stage(
                "wait_for_audio_trigger", host._profile_time() - strum_started
            )

        audio_acquisition_config = AudioAcquisitionConfig(
            sample_rate=host.samplerate,
            max_record_seconds=host.config.record_duration,
            expected_f0=expected_frequency,
            snr_threshold_db=host.snr,
            trigger_mode=("harmonic_comb" if host.use_harmonic_comb_trigger else "snr"),
            comb_trigger=host._harmonic_comb_config,
            recording_started_callback=on_recording_started,
            stop_event=host.stop_event,
        )

        x_step_mm = max(
            0.1,
            min(
                length * MEASUREMENT_WIGGLE_CONFIG.xy_sigma_per_meter,
                MEASUREMENT_WIGGLE_CONFIG.xy_sigma_cap_mm,
            ),
        )
        y_step_mm = max(0.05, float(host.wiggle_y_sigma_mm))
        focus_step_quarter_us = max(10, int(abs(host.focus_wiggle_sigma_quarter_us)))

        min_x_step_mm = 0.1
        min_y_step_mm = 0.05
        min_focus_step_quarter_us = 5

        best_confidence = -1.0
        best_x = float(wire_x)
        best_y = float(wire_y)
        initial_focus = host._active_focus_target()
        best_focus = (
            host._get_focus_position() if initial_focus is None else int(initial_focus)
        )
        axis_index = 0
        threshold_reached = False
        pending_best_sample: DeferredPitchSample | None = None
        legacy_tension_condition_active = (
            host._legacy_tension_condition_predicate is not None
        )

        def _legacy_tension_condition_ok(tension: float) -> bool:
            predicate = host._legacy_tension_condition_predicate
            if predicate is None:
                return True
            return bool(predicate(tension))

        def _publish_audio_sample(audio_sample: Any, analysis: Any | None) -> None:
            try:
                host.audio_sample_callback(audio_sample, host.samplerate, analysis)
            except Exception as exc:
                LOGGER.debug("Audio sample callback failed: %s", exc)

        def _flush_pending_skipped_sample() -> None:
            nonlocal pending_best_sample
            if pending_best_sample is None:
                return
            _publish_audio_sample(pending_best_sample.audio_sample, None)
            pending_best_sample = None

        def _build_wire_result(
            *,
            confidence: float,
            frequency: float,
            x: float,
            y: float,
            focus_position: int | None,
            zone: int | None,
            amplitude: float = 0.0,
            harmonicity: float = 0.0,
        ) -> TensionResult:
            LOGGER.info(
                "Sample of wire %s: measured frequency %.2f Hz %s with confidence %.2f (amp=%.4f, harm=%.4f)",
                wire_number,
                frequency,
                self._wire_equation(length=length, frequency=frequency),
                confidence,
                amplitude,
                harmonicity,
            )
            return TensionResult.from_measurement(
                apa_name=host.config.apa_name,
                layer=host.config.layer,
                side=host.config.side,
                wire_number=wire_number,
                frequency=frequency,
                confidence=confidence,
                x=x,
                y=y,
                focus_position=focus_position,
                zone=zone,
                time=host._now(),
                taped=host._is_current_side_taped(),
                amplitude=amplitude,
                harmonicity=harmonicity,
            )

        def _analyze_sample(
            sample: DeferredPitchSample,
        ) -> TensionResult:
            analysis, frequency, _nn_confidence, _accepted = (
                host._estimate_sample_pitch(
                    sample.audio_sample,
                    expected_frequency,
                )
            )
            _publish_audio_sample(sample.audio_sample, analysis)

            features = host._sample_harmonic_features(
                sample.audio_sample,
                frequency,
                expected_frequency,
            )
            host._learn_harmonic_trigger(
                features,
                host._last_pitch_triplet_accepted,
            )

            wire_result = _build_wire_result(
                confidence=sample.confidence,
                frequency=frequency,
                x=sample.x,
                y=sample.y,
                focus_position=sample.focus_position,
                zone=measured_zone,
                amplitude=host._sample_rms(sample.audio_sample),
                harmonicity=features.harmonicity,
            )
            host.repository.append_sample(wire_result)
            return wire_result

        def _move_to_pose(x_target: float, y_target: float, focus_target: int) -> None:
            diagonal_geometry = (
                abs(float(host.config.dx)) > 1e-9 and abs(float(host.config.dy)) > 1e-9
            )
            y_per_x = (
                (-float(host.config.dy) / float(host.config.dx))
                if diagonal_geometry
                else 0.0
            )
            clamped_focus = host._active_focus_target(focus_target)
            if clamped_focus is None:
                clamped_focus = host._clamp_focus_position(int(focus_target))
            current_focus = host._get_focus_position()
            delta_focus = int(clamped_focus - current_focus)
            if delta_focus != 0:
                prior_x: float | None = None
                try:
                    prior_x, _prior_y = host.get_current_xy_position()
                except Exception:
                    prior_x = None

                compensated_x = host._apply_focus_wiggle_with_x_compensation(
                    delta_focus
                )
                focus_x_delta = host._focus_to_x_delta_mm(delta_focus)
                if compensated_x is not None and prior_x is not None:
                    focus_x_delta = float(compensated_x) - float(prior_x)

                if not host.use_manual_focus:
                    x_target = float(x_target + focus_x_delta)
                    if diagonal_geometry:
                        y_target = float(y_target + (focus_x_delta * y_per_x))
            if not host._goto_xy_with_reset_recovery(
                x_target,
                y_target,
                context=f"Optimizer pose for wire {wire_number}",
                wait_for_completion=False,
            ):
                raise RuntimeError(
                    f"Failed to move to optimizer pose {x_target},{y_target} for wire {wire_number}"
                )

        def _next_pose() -> tuple[float, float, int]:
            nonlocal axis_index, x_step_mm, y_step_mm, focus_step_quarter_us

            diagonal_geometry = (
                abs(float(host.config.dx)) > 1e-9 and abs(float(host.config.dy)) > 1e-9
            )
            y_per_x = (
                (-float(host.config.dy) / float(host.config.dx))
                if diagonal_geometry
                else 0.0
            )

            target_x = float(host._gauss(best_x, x_step_mm))
            if diagonal_geometry:
                target_y = float(best_y + ((target_x - best_x) * y_per_x))
            else:
                target_y = float(host._gauss(best_y, y_step_mm))
            target_focus = int(best_focus)

            if (
                host._has_focus_wiggle_callback
                and not host.use_manual_focus
                and focus_step_quarter_us > 0
            ):
                target_focus = host._clamp_focus_position(
                    int(round(host._gauss(best_focus, focus_step_quarter_us)))
                )

            axis_index += 1
            if axis_index >= 2:
                axis_index = 0
                x_step_mm = max(min_x_step_mm, x_step_mm * 0.85)
                y_step_mm = max(min_y_step_mm, y_step_mm * 0.85)
                if host._has_focus_wiggle_callback and not host.use_manual_focus:
                    focus_step_quarter_us = max(
                        min_focus_step_quarter_us,
                        int(focus_step_quarter_us * 0.85),
                    )

            return float(target_x), float(target_y), int(target_focus)

        sweep_center_x = float(wire_x)
        sweep_center_y = float(wire_y)

        def _adjust_sweep_focus() -> None:
            """Refocus (with X compensation) after a sweep without a good recording.

            The sweep thread owns the gantry while it runs, so it is stopped
            before the focus/X compensation move and restarted around the
            compensated center.
            """
            nonlocal sweep_center_x, sweep_center_y, focus_step_quarter_us

            if (
                not host._has_focus_wiggle_callback
                or host.use_manual_focus
                or focus_step_quarter_us <= 0
            ):
                return

            target_focus = host._clamp_focus_position(
                int(round(host._gauss(best_focus, focus_step_quarter_us)))
            )
            delta_focus = int(target_focus - host._get_focus_position())
            focus_step_quarter_us = max(
                min_focus_step_quarter_us,
                int(focus_step_quarter_us * 0.85),
            )
            if delta_focus == 0:
                return

            host._stop_sweeping_wiggle(return_to_center=False)

            prior_x: float | None = None
            try:
                prior_x, _prior_y = host.get_current_xy_position()
            except Exception:
                prior_x = None

            compensated_x = host._apply_focus_wiggle_with_x_compensation(delta_focus)
            focus_x_delta = host._focus_to_x_delta_mm(delta_focus)
            if compensated_x is not None and prior_x is not None:
                focus_x_delta = float(compensated_x) - float(prior_x)

            sweep_center_x = float(sweep_center_x + focus_x_delta)
            diagonal_geometry = (
                abs(float(host.config.dx)) > 1e-9 and abs(float(host.config.dy)) > 1e-9
            )
            if diagonal_geometry:
                y_per_x = -float(host.config.dy) / float(host.config.dx)
                sweep_center_y = float(sweep_center_y + (focus_x_delta * y_per_x))

            LOGGER.info(
                "Sweeping wiggle refocus for wire %s: focus delta %s, new center %.3f,%.3f",
                wire_number,
                delta_focus,
                sweep_center_x,
                sweep_center_y,
            )
            host._start_sweeping_wiggle(
                center_x=sweep_center_x,
                center_y=sweep_center_y,
                focus_target=target_focus,
            )

        if host.sweeping_wiggle and host.sweeping_wiggle_span_mm > 0.0:
            host._start_sweeping_wiggle(
                center_x=sweep_center_x,
                center_y=sweep_center_y,
                focus_target=best_focus,
            )

        try:
            while (host._time() - start_time) < measuring_timeout:
                if self._check_stop_event(
                    host.stop_event, "tension measurement interrupted!"
                ):
                    return None
                x, y = host.get_current_xy_position()

                # Strum on a regular interval while audio acquisition runs in
                # a background thread, stopping as soon as the audio trigger
                # callback fires (or the thread completes).
                strum_started = host._profile_time()
                recording_started_event.clear()
                acquired_audio: list[Any] = []
                acquired_exc: list[BaseException] = []

                def _audio_worker() -> None:
                    try:
                        sample = self._acquire_audio(
                            cfg=audio_acquisition_config,
                            noise_rms=host.noise_threshold / 3,
                            timeout=max(float(host.config.record_duration), 0.0),
                        )
                        acquired_audio.append(sample)
                    except BaseException as exc:
                        acquired_exc.append(exc)

                acquire_started = host._profile_time()
                audio_thread = threading.Thread(target=_audio_worker, daemon=True)
                audio_thread.start()

                while audio_thread.is_alive() and not recording_started_event.is_set():
                    host.strum_func()
                    if recording_started_event.wait(
                        timeout=_STRUM_LOOP_INTERVAL_SECONDS
                    ):
                        break

                audio_thread.join()
                host._record_wire_stage("strum", host._profile_time() - strum_started)
                host._record_wire_stage(
                    "acquire_audio",
                    host._profile_time() - acquire_started,
                )
                if acquired_exc:
                    raise acquired_exc[0]
                audio_sample = acquired_audio[0] if acquired_audio else None

                if audio_sample is not None:
                    focus_position = host._get_focus_position()
                    if host._audio_store is not None:
                        _rec_meta = AudioRecordingMeta(
                            apa_name=host.config.apa_name,
                            layer=host.config.layer,
                            side=host.config.side,
                            wire_number=wire_number,
                            x_mm=float(x),
                            y_mm=float(y),
                            focus_position=focus_position,
                            zone=measured_zone,
                            wire_length_m=float(length),
                            timestamp=host._now(),
                        )
                        host._audio_store.save(audio_sample, host.samplerate, _rec_meta)
                    if amplitude_mode:
                        analyze_started = host._profile_time()
                        confidence = host._amplitude_confidence(
                            audio_sample,
                            expected_frequency,
                        )
                        host._record_wire_stage(
                            "analyze_audio",
                            host._profile_time() - analyze_started,
                        )
                        current_sample = DeferredPitchSample(
                            audio_sample=audio_sample,
                            x=x,
                            y=y,
                            focus_position=focus_position,
                            confidence=confidence,
                        )
                        is_new_best = confidence > best_confidence
                        if is_new_best:
                            best_confidence = confidence
                            best_x = current_sample.x
                            best_y = current_sample.y
                            best_focus = (
                                current_sample.focus_position
                                if current_sample.focus_position is not None
                                else best_focus
                            )
                            axis_index = 0

                        if confidence >= host.config.confidence_threshold:
                            threshold_reached = True
                            _flush_pending_skipped_sample()
                            wire_result = _analyze_sample(current_sample)
                            condition_ok = _legacy_tension_condition_ok(
                                wire_result.tension
                            )
                            if not condition_ok and legacy_tension_condition_active:
                                LOGGER.info(
                                    "Sample of wire %s tension %.2f did not satisfy legacy tension condition %r; continuing.",
                                    wire_number,
                                    wire_result.tension,
                                    host.legacy_tension_condition,
                                )
                            if self._tension_plausible(wire_result.tension) and condition_ok:
                                candidate_wires.append(wire_result)
                                break
                        elif is_new_best:
                            _flush_pending_skipped_sample()
                            pending_best_sample = current_sample
                        else:
                            _publish_audio_sample(audio_sample, None)
                    else:
                        analyze_started = host._profile_time()
                        analysis, frequency, confidence, accepted = (
                            host._estimate_sample_pitch(
                                audio_sample,
                                expected_frequency,
                            )
                        )
                        host._record_wire_stage(
                            "analyze_audio",
                            host._profile_time() - analyze_started,
                        )
                        _publish_audio_sample(audio_sample, analysis)
                        features = host._sample_harmonic_features(
                            audio_sample,
                            frequency,
                            expected_frequency,
                        )
                        host._learn_harmonic_trigger(
                            features,
                            host._last_pitch_triplet_accepted,
                        )
                        wire_result = _build_wire_result(
                            confidence=confidence,
                            frequency=frequency,
                            x=x,
                            y=y,
                            focus_position=focus_position,
                            zone=measured_zone,
                            harmonicity=features.harmonicity,
                        )
                        host.repository.append_sample(wire_result)

                        condition_ok = _legacy_tension_condition_ok(wire_result.tension)
                        if not condition_ok and legacy_tension_condition_active:
                            LOGGER.info(
                                "Sample of wire %s tension %.2f did not satisfy legacy tension condition %r; continuing.",
                                wire_number,
                                wire_result.tension,
                                host.legacy_tension_condition,
                            )
                        if self._tension_plausible(wire_result.tension) and condition_ok:
                            candidate_wires.append(wire_result)
                            if wire_result.confidence > best_confidence:
                                best_confidence = wire_result.confidence
                                best_x = wire_result.x
                                best_y = wire_result.y
                                best_focus = (
                                    wire_result.focus_position
                                    if wire_result.focus_position is not None
                                    else best_focus
                                )
                                axis_index = 0
                            if accepted:
                                break
                else:
                    LOGGER.info("Sample of wire %s: no audio detected.", wire_number)
                if (host._time() - start_time) >= measuring_timeout:
                    break

                if host.sweeping_wiggle and host.sweeping_wiggle_span_mm > 0.0:
                    _adjust_sweep_focus()
                    continue

                target_x, target_y, target_focus = _next_pose()
                LOGGER.info(
                    "Optimizer next pose: x=%s y=%s focus=%s",
                    target_x,
                    target_y,
                    target_focus,
                )
                optimizer_move_started = host._profile_time()
                try:
                    _move_to_pose(target_x, target_y, target_focus)
                except RuntimeError as exc:
                    host._record_wire_stage(
                        "optimizer_move",
                        host._profile_time() - optimizer_move_started,
                    )
                    LOGGER.warning("%s", exc)
                    break
                host._record_wire_stage(
                    "optimizer_move",
                    host._profile_time() - optimizer_move_started,
                )
        finally:
            host._stop_sweeping_wiggle(
                return_to_center=return_to_center
                and bool(host.sweeping_wiggle and host.sweeping_wiggle_span_mm > 0.0),
                center_x=sweep_center_x,
                center_y=sweep_center_y,
                focus_target=best_focus,
            )

        if amplitude_mode and pending_best_sample is not None:
            if threshold_reached and not legacy_tension_condition_active:
                _flush_pending_skipped_sample()
            else:
                wire_result = _analyze_sample(pending_best_sample)
                pending_best_sample = None
                if self._tension_plausible(
                    wire_result.tension
                ) and _legacy_tension_condition_ok(wire_result.tension):
                    candidate_wires.append(wire_result)
        else:
            _flush_pending_skipped_sample()
        return candidate_wires
