import threading
from contextlib import nullcontext
from datetime import datetime, timedelta
import logging
from typing import Any, ContextManager, Optional, Callable
import time
import numpy as np
from random import gauss

from dune_tension.audio_store import AudioStore
from dune_tension.config import MEASUREMENT_WIGGLE_CONFIG
from dune_tension.geometry import zone_lookup, length_lookup
from dune_tension.results import TensionResult
from dune_tension.services import (
    AudioCaptureService,
    MotionService,
    ResultRepository,
)
from dune_tension.tension_calculation import wire_equation, tension_plausible
from dune_tension.tensiometer_functions import (
    PlannedWirePose,
    TensiometerConfig,
    WirePositionProvider,
    check_stop_event,
    make_config,
    normalize_confidence_source,
    plan_measurement_poses,
)

# Pure leaves carved out of this module (Stage 1 of the tensiometer refactor).
# Re-exported here so existing ``dune_tension.tensiometer`` import sites keep
# working while the measurement core moves into ``dune_tension.measure``.
from dune_tension.measure._concurrency import (
    invoke_with_timeout as _invoke_with_timeout,
)
from dune_tension.measure.analysis import (
    AudioAcquisitionConfig,
    DeferredPitchSample,
    HarmonicSampleFeatures,
    SampleAnalyzer,
    acquire_audio,
    analyze_audio_with_pesto,
    default_harmonic_comb_config as _default_harmonic_comb_config,
    estimate_pitch_from_audio,
)
from dune_tension.measure.builder import build_tensiometer
from dune_tension.measure.collector import WireOptimizer, WireRequest
from dune_tension.measure.conditions import (
    compile_legacy_tension_condition as _compile_legacy_tension_condition,
)
from dune_tension.measure.focus import (
    FOCUS_MM_PER_QUARTER_US,
    FOCUS_X_MM_PER_QUARTER_US,
    FocusController,
)
from dune_tension.measure.motion import Mover
from dune_tension.measure.profiling import (
    BatchMeasurementProfile,
    MeasurementProfiler,
    WireMeasurementProfile,
)
from dune_tension.measure.wiggle import WiggleController

LOGGER = logging.getLogger(__name__)
_SUMMARY_REFRESH_GUARD_S = 0.5

# Live outlier detection during ``measure_list``. A fresh measurement is flagged
# as an outlier (and remeasured once) when, relative to nearby wires already
# measured in the same run, it differs from their mean by more than
# ``_OUTLIER_ABS_NEWTONS`` newtons OR by more than ``_OUTLIER_SIGMA`` standard
# deviations (the residual metric). "Nearby" means wires whose number is within
# ``_OUTLIER_WINDOW`` of the current wire; the check is skipped until at least
# ``_OUTLIER_MIN_NEIGHBORS`` such neighbors exist.
_OUTLIER_ABS_NEWTONS = 0.5
_OUTLIER_SIGMA = 1
_OUTLIER_WINDOW = 10
_OUTLIER_MIN_NEIGHBORS = 5

# Public surface of this module. Several names are re-exported from
# ``dune_tension.measure`` for import-site stability during the carve-up; listing
# them here documents the intent and marks them as re-exports for linters.
__all__ = [
    "Tensiometer",
    "build_tensiometer",
    "AudioAcquisitionConfig",
    "DeferredPitchSample",
    "HarmonicSampleFeatures",
    "WireMeasurementProfile",
    "BatchMeasurementProfile",
    "SampleAnalyzer",
    "MeasurementProfiler",
    "acquire_audio",
    "analyze_audio_with_pesto",
    "estimate_pitch_from_audio",
    "FOCUS_MM_PER_QUARTER_US",
    "FOCUS_X_MM_PER_QUARTER_US",
]


class Tensiometer:
    def __init__(
        self,
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
        config: TensiometerConfig | None = None,
        motion: MotionService | None = None,
        audio: AudioCaptureService | None = None,
        repository: ResultRepository | None = None,
        wire_position_provider: WirePositionProvider | None = None,
        time_provider: Callable[[], float] | None = None,
        datetime_provider: Callable[[], datetime] | None = None,
        gauss_func: Callable[[float, float], float] | None = None,
        audio_store: AudioStore | None = None,
        use_harmonic_comb_trigger: bool = False,
    ) -> None:
        self.config = config or make_config(
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
        self.stop_event = stop_event or threading.Event()
        self.config.confidence_source = normalize_confidence_source(
            self.config.confidence_source
        )
        self.snr = snr
        self.wiggle_y_sigma_mm = float(wiggle_y_sigma_mm)
        self.sweeping_wiggle = bool(sweeping_wiggle)
        self.sweeping_wiggle_span_mm = float(sweeping_wiggle_span_mm)
        self.focus_wiggle_sigma_quarter_us = float(focus_wiggle_sigma_quarter_us)
        self._time = time_provider or time.time
        self._profile_time = time.perf_counter
        self._now = datetime_provider or datetime.now
        self._gauss = gauss_func or gauss
        if self.wiggle_y_sigma_mm < 0:
            raise ValueError("wiggle_y_sigma_mm must be non-negative")
        if self.sweeping_wiggle_span_mm < 0:
            raise ValueError("sweeping_wiggle_span_mm must be non-negative")
        if self.focus_wiggle_sigma_quarter_us < 0:
            raise ValueError("focus_wiggle_sigma_quarter_us must be non-negative")
        self.motion = motion or MotionService.build(spoof_movement=spoof_movement)
        self.audio = audio or AudioCaptureService.build(spoof=spoof)
        self.repository = repository or ResultRepository(self.config.data_path)
        self.wire_position_provider = wire_position_provider or WirePositionProvider()
        self.noise_threshold = self.audio.noise_threshold
        self.samplerate = self.audio.samplerate
        self.record_audio_func = self.audio.record_audio
        self._harmonic_comb_config = _default_harmonic_comb_config()
        try:
            from spectrum_analysis.comb_trigger import HarmonicCombTriggerLearner

            self._harmonic_trigger_learner = HarmonicCombTriggerLearner(
                self._harmonic_comb_config
            )
        except Exception:
            self._harmonic_trigger_learner = None
        self._analyzer = SampleAnalyzer(
            config=self.config,
            samplerate=self.samplerate,
            noise_threshold=self.noise_threshold,
            harmonic_comb_config=self._harmonic_comb_config,
            harmonic_trigger_learner=self._harmonic_trigger_learner,
        )

        self.get_current_xy_position = getattr(
            self.motion, "get_live_xy", self.motion.get_xy
        )
        self.goto_xy_func = self.motion.goto_xy
        self.wiggle_func = self.motion.increment

        self._has_focus_wiggle_callback = focus_wiggle is not None
        self.focus_wiggle_func = focus_wiggle or (lambda _delta: None)
        self.focus_position_getter = focus_position_getter or (lambda: 0)
        self.focus_range_getter = focus_range_getter or (lambda: (4000, 8000))
        self.legacy_tension_condition = str(legacy_tension_condition or "").strip()
        self._legacy_tension_condition_predicate = (
            _compile_legacy_tension_condition(self.legacy_tension_condition)
            if self.legacy_tension_condition
            else None
        )
        self.use_manual_focus = bool(use_manual_focus)
        self.manual_focus_target = (
            None if manual_focus_target is None else int(manual_focus_target)
        )
        self.quiet_waiter = quiet_waiter or (lambda: None)
        self.strum_func = strum or (lambda: None)
        self.measurement_session = measurement_session or (lambda: nullcontext())
        self.estimated_time_callback = estimated_time_callback or (lambda _value: None)
        self.audio_sample_callback = audio_sample_callback or (
            lambda _sample, _samplerate, _analysis: None
        )
        self.summary_refresh_callback = summary_refresh_callback or (
            lambda _config: None
        )
        self.wire_preview_callback = wire_preview_callback or (lambda *_args: None)

        self.a_taped = bool(a_taped)
        self.b_taped = bool(b_taped)
        self._audio_store = audio_store
        self.use_harmonic_comb_trigger = bool(use_harmonic_comb_trigger)

        # Motion/focus/wiggle collaborators (read live host attributes).
        self._mover = Mover(self)
        self._focus = FocusController(self)
        self._wiggle = WiggleController(self)
        self._profiler = MeasurementProfiler(self._profile_time)

    # Timing/profiling delegates to MeasurementProfiler. The ``_active_*``
    # properties preserve the historical attribute-style access used by tests.
    @property
    def _active_batch_profile(self) -> BatchMeasurementProfile | None:
        return self._profiler.active_batch

    @property
    def _active_wire_profile(self) -> WireMeasurementProfile | None:
        return self._profiler.active_wire

    def _start_batch_profile(
        self,
        *,
        workflow: str,
        requested_wires: list[int],
    ) -> BatchMeasurementProfile:
        return self._profiler.start_batch(
            workflow=workflow, requested_wires=requested_wires
        )

    def _finish_batch_profile(self) -> None:
        self._profiler.finish_batch()

    def _start_wire_profile(self, workflow: str, wire_number: int) -> None:
        self._profiler.start_wire(workflow, wire_number)

    def _record_wire_stage(self, stage: str, elapsed: float) -> None:
        self._profiler.record_stage(stage, elapsed)

    def _complete_wire_profile(self, *, skipped: bool = False) -> None:
        self._profiler.complete_wire(skipped=skipped)

    # Focus positioning delegates to FocusController; XY moves to Mover. Thin
    # wrappers preserve the historical ``Tensiometer`` method API used by tests
    # and the measure loop.
    def _focus_wiggle_x_sign(self) -> float:
        return self._focus.wiggle_x_sign()

    def _focus_to_x_delta_mm(self, delta_focus_units: float) -> float:
        return self._focus.focus_to_x_delta_mm(delta_focus_units)

    def _get_focus_position(self) -> int:
        return self._focus.get_focus_position()

    def _apply_focus_wiggle_with_x_compensation(
        self, delta_focus: float
    ) -> float | None:
        return self._focus.apply_focus_wiggle_with_x_compensation(delta_focus)

    def _get_focus_bounds(self) -> tuple[int, int]:
        return self._focus.get_focus_bounds()

    def _clamp_focus_position(self, focus_position: int) -> int:
        return self._focus.clamp_focus_position(focus_position)

    def _active_focus_target(self, focus_target: int | None = None) -> int | None:
        return self._focus.active_focus_target(focus_target)

    def _goto_xy_with_reset_recovery(
        self,
        x_target: float,
        y_target: float,
        *,
        context: str,
        **move_kwargs: Any,
    ) -> bool:
        return self._mover.goto_with_reset_recovery(
            x_target, y_target, context=context, **move_kwargs
        )

    def _move_to_measurement_pose(
        self,
        x_target: float,
        y_target: float,
        focus_target: int | None = None,
    ) -> bool:
        clamped_focus = self._focus.active_focus_target(focus_target)
        if clamped_focus is not None:
            current_focus = self._focus.get_focus_position()
            delta_focus = clamped_focus - current_focus
            if delta_focus != 0:
                self._focus.apply_focus_wiggle_with_x_compensation(delta_focus)
        return self._mover.goto_with_reset_recovery(
            x_target,
            y_target,
            context="Measurement pose",
        )

    def _plan_auto_measurement_pose(
        self,
        wire_number: int,
        *,
        last_successful_result: TensionResult | None = None,
        last_successful_wire_number: int | None = None,
    ) -> PlannedWirePose | None:
        """Return the next auto-measurement pose.

        The first wire, or any wire after a run without a successful anchor, still
        uses the shared wire-position provider. Once we have a successful
        measurement, later wire positions are stepped locally from that measured
        pose using the per-wire geometry spacing.
        """

        if self.config.layer in ["V", "U"]:
            return self.wire_position_provider.get_pose(
                self.config,
                wire_number,
                self._get_focus_position(),
            )

        if last_successful_result is None or last_successful_wire_number is None:
            return self.wire_position_provider.get_pose(
                self.config,
                wire_number,
                self._get_focus_position(),
            )

        wire_delta = int(wire_number) - int(last_successful_wire_number)
        target_x = float(last_successful_result.x)
        target_y = float(last_successful_result.y) + (
            wire_delta * float(self.config.dy)
        )

        focus_position = last_successful_result.focus_position
        if focus_position is None:
            focus_position = self._get_focus_position()

        return PlannedWirePose(
            wire_number=int(wire_number),
            x=float(target_x),
            y=float(target_y),
            focus_position=int(focus_position) if focus_position is not None else None,
        )

    def _plan_batch_measurement_pose(
        self,
        wire_number: int,
        *,
        last_successful_result: TensionResult | None = None,
        last_successful_wire_number: int | None = None,
    ) -> PlannedWirePose | None:
        """Return the absolute target pose for a batch measurement wire.

        U/V legacy runs should always go to the provider-computed pose for the
        requested wire, even in list/auto workflows. X/G retains the historical
        step-from-last-success path.
        """

        if self.config.layer in ["U", "V"]:
            return self.wire_position_provider.get_pose(
                self.config,
                int(wire_number),
                self._get_focus_position(),
            )

        return self._plan_auto_measurement_pose(
            int(wire_number),
            last_successful_result=last_successful_result,
            last_successful_wire_number=last_successful_wire_number,
        )

    @staticmethod
    def _sample_sort_key(result: TensionResult) -> tuple[float, datetime]:
        timestamp = getattr(result, "time", None)
        return (
            float(result.confidence),
            timestamp if timestamp is not None else datetime.min,
        )

    def _is_current_side_taped(self) -> bool:
        side = self.config.side.upper()
        if side == "A":
            return self.a_taped
        if side == "B":
            return self.b_taped
        return False

    def start_wiggle(self) -> None:
        """Begin wiggling the winder in a background thread."""
        self._wiggle.start()

    def stop_wiggle(self) -> None:
        """Stop the background winder wiggle thread."""
        self._wiggle.stop()

    def _plot_audio(self, audio_sample) -> None:
        """Save a plot of the recorded audio sample to a temporary file."""
        try:
            import matplotlib.pyplot as plt  # Local import to avoid optional dep
        except Exception as exc:  # pragma: no cover - plotting is optional
            LOGGER.warning("Failed to import matplotlib for plotting: %s", exc)
            return

        try:
            from tempfile import NamedTemporaryFile

            plt.figure(figsize=(10, 4))
            plt.plot(audio_sample)
            plt.title("Recorded Audio Sample")
            plt.xlabel("Sample Index")
            plt.ylabel("Amplitude")
            plt.grid(True)
            plt.tight_layout()
            with NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                plt.savefig(tmp.name)
                LOGGER.info("Audio plot saved to %s", tmp.name)
            plt.close()
        except Exception as exc:  # pragma: no cover - plotting is optional
            LOGGER.warning("Failed to plot audio sample: %s", exc)

    def _start_sweeping_wiggle(
        self,
        *,
        center_x: float,
        center_y: float,
        focus_target: int | None,
    ) -> None:
        self._wiggle.start_sweeping(
            center_x=center_x, center_y=center_y, focus_target=focus_target
        )

    def _stop_sweeping_wiggle(
        self,
        *,
        return_to_center: bool,
        center_x: float | None = None,
        center_y: float | None = None,
        focus_target: int | None = None,
    ) -> None:
        self._wiggle.stop_sweeping(
            return_to_center=return_to_center,
            center_x=center_x,
            center_y=center_y,
            focus_target=focus_target,
        )

    # Signal analysis delegates to SampleAnalyzer. Thin wrappers preserve the
    # historical ``Tensiometer`` method API used by tests and the measure loop.
    @property
    def _last_pitch_triplet_accepted(self) -> bool | None:
        return self._analyzer.last_pitch_triplet_accepted

    @staticmethod
    def _sample_rms(audio_sample: Any) -> float:
        return SampleAnalyzer.sample_rms(audio_sample)

    def _triangle_reference_rms(self, expected_frequency: float | None) -> float:
        return self._analyzer.triangle_reference_rms(expected_frequency)

    def _amplitude_confidence(
        self,
        audio_sample: Any,
        expected_frequency: float | None,
    ) -> float:
        return self._analyzer.amplitude_confidence(audio_sample, expected_frequency)

    def _is_audio_worth_analyzing(self, audio_sample: Any) -> bool:
        return self._analyzer.is_audio_worth_analyzing(audio_sample)

    def _estimate_sample_pitch(
        self,
        audio_sample: Any,
        expected_frequency: float | None,
    ) -> tuple[Any | None, float, float, bool]:
        return self._analyzer.estimate_sample_pitch(audio_sample, expected_frequency)

    def _sample_harmonic_features(
        self,
        audio_sample: Any,
        frequency: float,
        expected_frequency: float | None,
    ) -> HarmonicSampleFeatures:
        return self._analyzer.sample_harmonic_features(
            audio_sample, frequency, expected_frequency
        )

    def _learn_harmonic_trigger(
        self,
        features: HarmonicSampleFeatures,
        accepted_by_triplet: bool | None,
    ) -> None:
        self._analyzer.learn_harmonic_trigger(features, accepted_by_triplet)

    def measure_calibrate(self, wire_number: int) -> Optional[TensionResult]:
        target = None
        if self.config.layer in ["U", "V"]:
            target = self.wire_position_provider.get_pose(
                self.config,
                int(wire_number),
                self._get_focus_position(),
            )
            if target is None:
                LOGGER.warning("No planned position found for wire %s.", wire_number)
                return None
            x, y = float(target.x), float(target.y)
            self.goto_xy_func(x, y)
        else:
            x, y = self.get_current_xy_position()
            self.goto_xy_func(x, y)

        with self.repository.run_scope(), self.measurement_session():
            return self.goto_collect_wire_data(
                wire_number=wire_number,
                wire_x=x,
                wire_y=y,
                zone=target.zone if target is not None else None,
            )

    def measure_auto(self) -> None:
        """Measure all missing wires in the current layer/side.

        All layers go through the Python ``measure_list`` path. It strums the
        wire continuously while audio acquisition runs in a background thread,
        which is the only capture path that works reliably on the instrument
        (the Rust cpal capture backend contends with the audio device and
        stalls). The ETA monitor below wraps ``append_result`` regardless of
        which wires are measured.
        """
        from dune_tension.summaries import get_missing_wires

        wires_dict = get_missing_wires(self.config)
        wires_to_measure = list(map(int, wires_dict.get(self.config.side, [])))
        if not wires_to_measure:
            self.estimated_time_callback("0:00:00")
            LOGGER.info("All wires are already measured.")
            return

        total = len(wires_to_measure)
        self.estimated_time_callback("--")
        progress_lock = threading.Lock()
        progress_state = {"count": 0}
        start_time = self._time()
        stop_progress = threading.Event()
        original_append = self.repository.append_result

        def counting_append_result(result: TensionResult) -> None:
            try:
                original_append(result)
            finally:
                with progress_lock:
                    progress_state["count"] += 1

        def emit_eta() -> None:
            while not stop_progress.wait(2.0):
                with progress_lock:
                    count = progress_state["count"]
                if count <= 0:
                    continue
                remaining = total - count
                if remaining <= 0:
                    try:
                        self.estimated_time_callback("0:00:00")
                    except Exception:
                        LOGGER.debug("estimated_time_callback raised", exc_info=True)
                    return
                elapsed = self._time() - start_time
                avg_time = elapsed / count
                est_remaining = avg_time * remaining
                eta_text = str(timedelta(seconds=int(est_remaining)))
                try:
                    self.estimated_time_callback(eta_text)
                except Exception:
                    LOGGER.debug("estimated_time_callback raised", exc_info=True)

        self.repository.append_result = counting_append_result  # type: ignore[method-assign]
        monitor_thread = threading.Thread(
            target=emit_eta, name="tensiometer-eta-monitor", daemon=True
        )
        monitor_thread.start()
        try:
            try:
                self.measure_list(wires_to_measure, preserve_order=False)
            except KeyboardInterrupt:
                LOGGER.info("Measurement interrupted by user.")
        finally:
            stop_progress.set()
            monitor_thread.join(timeout=3.0)
            try:
                del self.repository.append_result
            except AttributeError:
                self.repository.append_result = original_append  # type: ignore[method-assign]
            if not check_stop_event(self.stop_event):
                self.estimated_time_callback("0:00:00")

    @staticmethod
    def _is_outlier_tension(
        wire_number: int,
        tension: float,
        measured_tensions: dict[int, float],
    ) -> bool:
        """Return True when ``tension`` is an outlier versus nearby measured wires.

        "Nearby" wires are those within ``_OUTLIER_WINDOW`` wire numbers of
        ``wire_number`` that have already been measured this run. The tension is
        an outlier if it differs from the neighbour mean by more than
        ``_OUTLIER_ABS_NEWTONS`` newtons, or by more than ``_OUTLIER_SIGMA``
        standard deviations of the neighbour spread (the residual metric).
        """
        neighbors = [
            value
            for number, value in measured_tensions.items()
            if number != wire_number
            and abs(number - wire_number) <= _OUTLIER_WINDOW
            and float(value) > 0.0
        ]
        if len(neighbors) < _OUTLIER_MIN_NEIGHBORS:
            return False
        mean = float(np.mean(neighbors))
        residual = abs(float(tension) - mean)
        if residual > _OUTLIER_ABS_NEWTONS:
            return True
        std = float(np.std(neighbors))
        return std > 0.0 and residual > _OUTLIER_SIGMA * std

    def measure_list(
        self, wire_list: list[int], preserve_order: bool, profile: bool = False
    ) -> None:
        ordered_wire_numbers = list(map(int, wire_list))
        planning_started = self._profile_time()
        if not preserve_order:
            ordered_targets = plan_measurement_poses(
                config=self.config,
                wire_list=ordered_wire_numbers,
                get_pose_from_file_func=self.wire_position_provider.get_pose,
                get_current_xy_func=self.get_current_xy_position,
                preserve_order=False,
                current_focus_position=self._get_focus_position(),
            )
            ordered_wire_numbers = [pose.wire_number for pose in ordered_targets]
        self._start_batch_profile(workflow="list", requested_wires=ordered_wire_numbers)
        if self._active_batch_profile is not None:
            self._active_batch_profile.planning_seconds = (
                self._profile_time() - planning_started
            )
        try:
            with self.repository.run_scope(), self.measurement_session():
                last_successful_result: TensionResult | None = None
                last_successful_wire_number: int | None = None
                measured_tensions: dict[int, float] = {}
                for wire_number in ordered_wire_numbers:
                    if check_stop_event(self.stop_event):
                        return
                    self._start_wire_profile("list", int(wire_number))
                    target_started = self._profile_time()
                    target = self._plan_batch_measurement_pose(
                        int(wire_number),
                        last_successful_result=last_successful_result,
                        last_successful_wire_number=last_successful_wire_number,
                    )
                    self._record_wire_stage(
                        "plan_measurement_pose",
                        self._profile_time() - target_started,
                    )
                    if target is None:
                        LOGGER.warning(
                            "No position data found for wire %s during list measurement.",
                            wire_number,
                        )
                        self._complete_wire_profile(skipped=True)
                        continue
                    LOGGER.info(
                        "Measuring wire %s at %s,%s focus=%s",
                        target.wire_number,
                        target.x,
                        target.y,
                        target.focus_position,
                    )
                    result = self.goto_collect_wire_data(
                        wire_number=target.wire_number,
                        wire_x=target.x,
                        wire_y=target.y,
                        focus_position=target.focus_position,
                        zone=target.zone,
                        return_to_center=False,
                    )
                    if (
                        result is not None
                        and float(result.frequency) > 0.0
                        and self._is_outlier_tension(
                            int(target.wire_number),
                            float(result.tension),
                            measured_tensions,
                        )
                    ):
                        LOGGER.warning(
                            "Wire %s tension %.2f N flagged as an outlier versus nearby "
                            "wires; remeasuring and keeping only the second measurement.",
                            target.wire_number,
                            result.tension,
                        )
                        repeat = self.goto_collect_wire_data(
                            wire_number=target.wire_number,
                            wire_x=target.x,
                            wire_y=target.y,
                            focus_position=target.focus_position,
                            zone=target.zone,
                            return_to_center=False,
                        )
                        if repeat is not None and float(repeat.frequency) > 0.0:
                            result = repeat
                    self._complete_wire_profile()
                    if result is not None and float(result.frequency) > 0.0:
                        last_successful_result = result
                        last_successful_wire_number = int(target.wire_number)
                        measured_tensions[int(target.wire_number)] = float(
                            result.tension
                        )
        finally:
            self._finish_batch_profile()

    def _collect_samples(
        self,
        wire_number: int,
        length: float,
        start_time: float,
        wire_y: float,
        wire_x: float,
        zone: int | None = None,
        return_to_center: bool = True,
    ) -> list[TensionResult] | None:
        # The optimizer loop lives in WireOptimizer. The monkeypatch-sensitive
        # globals are passed from this module's namespace so test seams (which
        # patch dune_tension.tensiometer.{acquire_audio,wire_equation,
        # tension_plausible}) continue to take effect.
        optimizer = WireOptimizer(
            self,
            WireRequest(
                wire_number=wire_number,
                length=length,
                start_time=start_time,
                wire_y=wire_y,
                wire_x=wire_x,
                zone=zone,
                return_to_center=return_to_center,
            ),
            acquire_audio=acquire_audio,
            wire_equation=wire_equation,
            tension_plausible=tension_plausible,
            check_stop_event=check_stop_event,
        )
        return optimizer.collect()

    def _merge_results(
        self,
        passing_wires: list[TensionResult],
        wire_number: int,
        wire_x: float,
        wire_y: float,
    ) -> TensionResult | None:
        if passing_wires == []:
            return None
        return max(passing_wires, key=self._sample_sort_key)

    def goto_collect_wire_data(
        self,
        wire_number: int,
        wire_x: float,
        wire_y: float,
        focus_position: int | None = None,
        zone: int | None = None,
        return_to_center: bool = True,
    ) -> Optional[TensionResult]:
        total_started = self._profile_time()
        self.motion.reset_plc()
        self._record_wire_stage(
            "reset_plc_before_move",
            self._profile_time() - total_started,
        )
        measured_zone = int(zone) if zone is not None else zone_lookup(wire_x)
        length = length_lookup(
            self.config.layer,
            wire_number,
            measured_zone,
            taped=self._is_current_side_taped(),
        )
        if np.isnan(length):
            raise ValueError("Length lookup returned NaN")

        if check_stop_event(self.stop_event):
            return None

        if self.config.layer in ["U", "V"]:
            try:
                self.wire_preview_callback(
                    int(wire_number), float(wire_x), float(wire_y)
                )
            except Exception as exc:
                LOGGER.debug(
                    "Wire preview callback failed for wire %s: %s", wire_number, exc
                )

        move_started = self._profile_time()
        succeed = self._move_to_measurement_pose(wire_x, wire_y, focus_position)
        self._record_wire_stage(
            "move_to_measurement_pose",
            self._profile_time() - move_started,
        )
        if check_stop_event(self.stop_event):
            return None
        if not succeed:
            LOGGER.warning(
                "Failed to move to wire %s position %s,%s.",
                wire_number,
                wire_x,
                wire_y,
            )
            return TensionResult.from_measurement(
                apa_name=self.config.apa_name,
                layer=self.config.layer,
                side=self.config.side,
                wire_number=wire_number,
                frequency=0.0,
                confidence=0.0,
                x=wire_x,
                y=wire_y,
                focus_position=self._get_focus_position(),
                zone=measured_zone,
                time=self._now(),
                taped=self._is_current_side_taped(),
            )
        start_time = self._time()
        collect_started = self._profile_time()
        try:
            wires_results = self._collect_samples(
                wire_number=wire_number,
                length=length,
                start_time=start_time,
                wire_y=wire_y,
                wire_x=wire_x,
                zone=measured_zone,
                return_to_center=return_to_center,
            )

        finally:
            self._record_wire_stage(
                "collect_samples",
                self._profile_time() - collect_started,
            )
            reset_started = self._profile_time()
            self.motion.reset_plc()
            self._record_wire_stage(
                "reset_plc_after_collect",
                self._profile_time() - reset_started,
            )

        if wires_results is None:
            return None

        merge_started = self._profile_time()
        result = self._merge_results(wires_results, wire_number, wire_x, wire_y)
        self._record_wire_stage(
            "merge_results",
            self._profile_time() - merge_started,
        )

        if result is None:
            if self._legacy_tension_condition_predicate is not None:
                LOGGER.warning(
                    "Measurement failed for wire number %s before satisfying legacy tension condition %r.",
                    wire_number,
                    self.legacy_tension_condition,
                )
            else:
                LOGGER.warning("Measurement failed for wire number %s.", wire_number)
            return result
        if not result.tension_pass:
            LOGGER.warning("Tension failed for wire number %s.", wire_number)
        ttf = self._time() - start_time
        LOGGER.info(
            "Result: wire %s length %.1f mm tension %.1f N frequency %.1f Hz confidence %.2f at %s,%s focus %s. Took %.2f seconds.",
            wire_number,
            length * 1000,
            result.tension,
            result.frequency,
            result.confidence,
            result.x,
            result.y,
            result.focus_position,
            ttf,
        )
        result.ttf = ttf
        result.time = self._now()
        persist_started = self._profile_time()
        self.motion.reset_plc()
        self._record_wire_stage(
            "reset_plc_before_persist",
            self._profile_time() - persist_started,
        )
        append_started = self._profile_time()
        self.repository.append_result(result)
        self._record_wire_stage("append_result", self._profile_time() - append_started)
        refresh_started = self._profile_time()
        _invoke_with_timeout(
            self.summary_refresh_callback,
            self.config,
            timeout_s=_SUMMARY_REFRESH_GUARD_S,
            label="summary_refresh_callback",
        )
        self._record_wire_stage(
            "summary_refresh",
            self._profile_time() - refresh_started,
        )
        self._record_wire_stage(
            "wire_total_wall",
            self._profile_time() - total_started,
        )

        return result

    def load_tension_summary(
        self,
    ) -> tuple[list, list] | tuple[str, list, list]:
        import os

        if not os.path.exists(self.config.data_path):
            return f"❌ File not found: {self.config.data_path}", [], []

        from dune_tension.summaries import get_expected_range, get_tension_series

        wire_range = list(get_expected_range(self.config.layer))
        if not wire_range:
            return f"⚠️ Unsupported layer {self.config.layer!r}", [], []

        tension_series = get_tension_series(self.config)
        if not tension_series["A"] and not tension_series["B"]:
            return f"⚠️ No summary measurements found in {self.config.data_path}", [], []

        nan = float("nan")
        return (
            [tension_series["A"].get(wire, nan) for wire in wire_range],
            [tension_series["B"].get(wire, nan) for wire in wire_range],
        )

    def close(self) -> None:
        """Stop any active audio streams used by the tensiometer."""
        try:
            self.repository.close()
        except Exception:
            pass
        try:
            if self._audio_store is not None:
                self._audio_store.close()
        except Exception:
            pass
        try:
            import sounddevice as sd  # Local import to avoid mandatory dependency

            sd.stop()
        except Exception:
            pass
