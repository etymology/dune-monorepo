import ast
import threading
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import math
from typing import Any, ContextManager, Optional, Callable
import time
import numpy as np
from random import gauss

from dune_tension.audio_store import AudioRecordingMeta, AudioStore
from dune_tension.config import MEASUREMENT_WIGGLE_CONFIG
from dune_tension.geometry import zone_lookup, length_lookup, refine_position
from dune_tension.results import TensionResult
from dune_tension.services import (
    AudioCaptureService,
    MotionService,
    ResultRepository,
    RuntimeBundle,
    build_runtime_bundle,
    resolve_runtime_options,
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
from dune_tension.plc_io import is_in_measurable_area

LOGGER = logging.getLogger(__name__)
FOCUS_MM_PER_QUARTER_US = 20.0 / 4000.0
FOCUS_X_MM_PER_QUARTER_US = FOCUS_MM_PER_QUARTER_US / math.sqrt(3.0)
_STRUM_LOOP_INTERVAL_SECONDS = 0.2
_SUMMARY_REFRESH_GUARD_S = 0.5


def _invoke_with_timeout(
    callback: Callable[..., Any],
    *args: Any,
    timeout_s: float,
    label: str,
) -> None:
    """Run ``callback`` in a daemon thread; return after ``timeout_s`` seconds.

    The thread keeps running on its own if the callback hasn't returned; we
    just stop waiting. This guarantees the wire loop never blocks on a
    misbehaving callback (e.g. a plot dispatch that has wedged).
    """

    def _runner() -> None:
        try:
            callback(*args)
        except Exception as exc:  # noqa: BLE001 — callback is user code
            LOGGER.debug("%s raised: %s", label, exc)

    thread = threading.Thread(
        target=_runner, name=f"timeout-guard-{label}", daemon=True
    )
    thread.start()
    thread.join(timeout=timeout_s)
    if thread.is_alive():
        LOGGER.warning(
            "%s exceeded %.2fs wall-clock guard; continuing measurement",
            label,
            timeout_s,
        )


def _compile_legacy_tension_condition(expr: str) -> Callable[[float], bool]:
    """Compile a safe tension-only expression that references ``t``."""

    allowed_nodes = (
        ast.Expression,
        ast.BoolOp,
        ast.BinOp,
        ast.UnaryOp,
        ast.Compare,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.And,
        ast.Or,
        ast.Not,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Pow,
        ast.Mod,
        ast.USub,
        ast.UAdd,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
    )

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid syntax: {exc.msg}") from exc

    uses_t = False
    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            raise ValueError(f"disallowed expression node: {type(node).__name__}")
        if isinstance(node, ast.Name):
            if node.id != "t":
                raise ValueError(
                    "only the variable 't' is allowed in legacy tension conditions"
                )
            uses_t = True

    if not uses_t:
        raise ValueError("legacy tension conditions must reference the variable 't'")

    code = compile(tree, "<legacy-tension-condition>", "eval")

    def predicate(tension: float) -> bool:
        result = eval(code, {"__builtins__": {}}, {"t": float(tension)})
        return bool(result)

    return predicate


def _default_harmonic_comb_config() -> Any:
    from spectrum_analysis.comb_trigger import HarmonicCombConfig

    return HarmonicCombConfig()


@dataclass(frozen=True)
class AudioAcquisitionConfig:
    """Minimal runtime config passed into ``acquire_audio``."""

    sample_rate: int
    max_record_seconds: float
    expected_f0: float | None
    snr_threshold_db: float
    trigger_mode: str
    min_frequency: float = 30.0
    max_frequency: float = 2000.0
    min_oscillations_per_window: float = 10.0
    min_window_overlap: float = 0.5
    idle_timeout: float = 0.2
    input_mode: str = "mic"
    input_audio_path: str | None = None
    comb_trigger: Any = field(default_factory=_default_harmonic_comb_config)
    recording_started_callback: Callable[[], None] | None = None
    stop_event: threading.Event | None = None
    discard_leading_seconds: float = 0.0


@dataclass(frozen=True)
class DeferredPitchSample:
    """Captured sample metadata retained for deferred pitch analysis."""

    audio_sample: Any
    x: float
    y: float
    focus_position: int | None
    confidence: float


@dataclass(frozen=True)
class HarmonicSampleFeatures:
    """Comb features measured on a captured sample."""

    harmonicity: float = 0.0
    spectral_flatness: float = 1.0
    valid: bool = False


@dataclass
class WireMeasurementProfile:
    """Timing breakdown for one wire inside a list/auto batch run."""

    workflow: str
    wire_number: int
    started_at: float
    stage_seconds: dict[str, float] = field(default_factory=dict)

    def add(self, stage: str, elapsed: float) -> None:
        self.stage_seconds[stage] = self.stage_seconds.get(stage, 0.0) + max(
            0.0,
            float(elapsed),
        )

    @property
    def total_seconds(self) -> float:
        if "wire_total_wall" in self.stage_seconds:
            return max(0.0, float(self.stage_seconds["wire_total_wall"]))
        return max(0.0, float(sum(self.stage_seconds.values())))


@dataclass
class BatchMeasurementProfile:
    """Aggregate timing for a list/auto wire measurement batch."""

    workflow: str
    requested_wires: list[int]
    started_at: float
    planning_seconds: float = 0.0
    wire_profiles: list[WireMeasurementProfile] = field(default_factory=list)
    skipped_wires: list[int] = field(default_factory=list)

    def complete_wire(self, profile: WireMeasurementProfile | None) -> None:
        if profile is not None:
            self.wire_profiles.append(profile)

    @property
    def total_seconds(self) -> float:
        return max(
            0.0,
            float(
                sum(p.total_seconds for p in self.wire_profiles) + self.planning_seconds
            ),
        )


def acquire_audio(*args, **kwargs):
    """Lazily import the runtime audio acquisition helper."""

    from spectrum_analysis.audio_processing import acquire_audio as _acquire_audio

    return _acquire_audio(*args, **kwargs)


def estimate_pitch_from_audio(*args, **kwargs):
    """Lazily import the runtime PESTO pitch estimator."""

    from spectrum_analysis.pesto_analysis import (
        estimate_pitch_from_audio as _estimate_pitch_from_audio,
    )

    return _estimate_pitch_from_audio(*args, **kwargs)


def analyze_audio_with_pesto(*args, **kwargs):
    """Lazily import the runtime PESTO diagnostics helper."""

    from spectrum_analysis.pesto_analysis import (
        analyze_audio_with_pesto as _analyze_audio_with_pesto,
    )

    return _analyze_audio_with_pesto(*args, **kwargs)


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
        self._last_pitch_triplet_accepted: bool | None = None

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

        # State tracking for winder wiggle thread
        self._wiggle_event: threading.Event | None = None
        self._wiggle_thread: threading.Thread | None = None
        self._sweeping_wiggle_event: threading.Event | None = None
        self._sweeping_wiggle_thread: threading.Thread | None = None
        self._active_batch_profile: BatchMeasurementProfile | None = None
        self._active_wire_profile: WireMeasurementProfile | None = None

    def _start_batch_profile(
        self,
        *,
        workflow: str,
        requested_wires: list[int],
    ) -> BatchMeasurementProfile:
        profile = BatchMeasurementProfile(
            workflow=workflow,
            requested_wires=list(map(int, requested_wires)),
            started_at=self._profile_time(),
        )
        self._active_batch_profile = profile
        LOGGER.info(
            "Timing profile started for %s measurement of %s wire(s): %s",
            workflow,
            len(profile.requested_wires),
            profile.requested_wires,
        )
        return profile

    def _finish_batch_profile(self) -> None:
        profile = self._active_batch_profile
        self._active_batch_profile = None
        self._active_wire_profile = None
        if profile is None:
            return
        measured_wires = len(profile.wire_profiles)
        total_wire_seconds = sum(p.total_seconds for p in profile.wire_profiles)
        avg_wire_seconds = (
            total_wire_seconds / measured_wires if measured_wires else 0.0
        )
        aggregate_stages: dict[str, float] = {}
        for wire_profile in profile.wire_profiles:
            for stage, elapsed in wire_profile.stage_seconds.items():
                aggregate_stages[stage] = aggregate_stages.get(stage, 0.0) + elapsed
        stage_summary = (
            ", ".join(
                f"{stage}={elapsed:.2f}s"
                for stage, elapsed in sorted(
                    aggregate_stages.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
            )
            or "none"
        )
        LOGGER.info(
            "Timing profile summary for %s measurement: requested=%s measured=%s skipped=%s planning=%.2fs avg_wire=%.2fs total=%.2fs stage_totals=[%s]",
            profile.workflow,
            len(profile.requested_wires),
            measured_wires,
            profile.skipped_wires,
            profile.planning_seconds,
            avg_wire_seconds,
            profile.total_seconds,
            stage_summary,
        )

    def _start_wire_profile(self, workflow: str, wire_number: int) -> None:

        if self._active_batch_profile is None:
            self._active_wire_profile = None
            return
        self._active_wire_profile = WireMeasurementProfile(
            workflow=workflow,
            wire_number=int(wire_number),
            started_at=self._profile_time(),
        )

    def _record_wire_stage(self, stage: str, elapsed: float) -> None:
        if self._active_wire_profile is not None:
            self._active_wire_profile.add(stage, elapsed)

    def _complete_wire_profile(self, *, skipped: bool = False) -> None:
        profile = self._active_wire_profile
        self._active_wire_profile = None
        if self._active_batch_profile is None or profile is None:
            return
        if skipped:
            self._active_batch_profile.skipped_wires.append(profile.wire_number)
            return
        self._active_batch_profile.complete_wire(profile)
        stage_summary = (
            ", ".join(
                f"{stage}={elapsed:.2f}s"
                for stage, elapsed in sorted(
                    profile.stage_seconds.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
            )
            or "none"
        )
        LOGGER.info(
            "Timing profile for %s wire %s: total=%.2fs stages=[%s]",
            profile.workflow,
            profile.wire_number,
            profile.total_seconds,
            stage_summary,
        )

    def _focus_wiggle_x_sign(self) -> float:
        """Return focus/X coupling sign: A is negative, B is positive."""

        return -1.0 if str(self.config.side).upper() == "A" else 1.0

    def _focus_to_x_delta_mm(self, delta_focus_units: float) -> float:
        """Convert a focus delta in quarter-us to the coupled X delta in mm."""

        return (
            self._focus_wiggle_x_sign()
            * float(delta_focus_units)
            * FOCUS_X_MM_PER_QUARTER_US
        )

    def _get_focus_position(self) -> int:
        """Return the latest commanded focus position in quarter-us units."""

        try:
            return int(self.focus_position_getter())
        except Exception:
            return 0

    def _apply_focus_wiggle_with_x_compensation(
        self, delta_focus: float
    ) -> float | None:
        """Apply focus wiggle and X compensation for equivalent travel in mm."""

        if not self._has_focus_wiggle_callback:
            return None

        commanded_delta = int(float(delta_focus))
        self.focus_wiggle_func(commanded_delta)
        if commanded_delta == 0:
            return None

        delta_x_mm = self._focus_to_x_delta_mm(commanded_delta)
        try:
            cur_x, cur_y = self.get_current_xy_position()
        except Exception as exc:
            LOGGER.warning("Unable to read XY for focus wiggle compensation: %s", exc)
            return None

        new_x = round(cur_x + delta_x_mm, 1)
        try:
            moved = self.goto_xy_func(new_x, cur_y)
        except Exception as exc:
            LOGGER.warning("Focus wiggle compensation move failed: %s", exc)
            return None
        if moved is False:
            LOGGER.warning(
                "Focus wiggle compensation move to %s,%s failed.",
                new_x,
                cur_y,
            )
            return None

        try:
            compensated_x, _ = self.get_current_xy_position()
            return float(compensated_x)
        except Exception:
            return new_x

    def _get_focus_bounds(self) -> tuple[int, int]:
        try:
            bounds = self.focus_range_getter()
        except Exception:
            bounds = None
        if not bounds or len(bounds) != 2:
            return (4000, 8000)
        low, high = int(bounds[0]), int(bounds[1])
        if low > high:
            return (4000, 8000)
        return (low, high)

    def _clamp_focus_position(self, focus_position: int) -> int:
        low, high = self._get_focus_bounds()
        return max(low, min(high, int(focus_position)))

    def _active_focus_target(self, focus_target: int | None = None) -> int | None:
        if self.use_manual_focus:
            if self.manual_focus_target is None:
                return self._clamp_focus_position(self._get_focus_position())
            return self._clamp_focus_position(self.manual_focus_target)
        if focus_target is None:
            return None
        return self._clamp_focus_position(int(focus_target))

    def _goto_xy_with_reset_recovery(
        self,
        x_target: float,
        y_target: float,
        *,
        context: str,
        **move_kwargs: Any,
    ) -> bool:
        """Attempt an XY move, resetting the PLC and retrying once on failure."""

        try:
            moved = self.goto_xy_func(x_target, y_target, **move_kwargs)
        except Exception as exc:
            LOGGER.warning(
                "%s move to %s,%s raised %s", context, x_target, y_target, exc
            )
            moved = False

        if moved is not False:
            return True

        LOGGER.warning(
            "%s move to %s,%s failed. Resetting PLC and retrying once.",
            context,
            x_target,
            y_target,
        )
        try:
            self.motion.reset_plc()
        except Exception as exc:
            LOGGER.warning("PLC reset after failed move raised %s", exc)

        try:
            retry = self.goto_xy_func(x_target, y_target, **move_kwargs)
        except Exception as exc:
            LOGGER.warning(
                "%s retry after PLC reset raised %s for move to %s,%s",
                context,
                exc,
                x_target,
                y_target,
            )
            return False

        if retry is False:
            LOGGER.warning(
                "%s retry after PLC reset still failed for move to %s,%s.",
                context,
                x_target,
                y_target,
            )
            return False
        return True

    def _move_to_measurement_pose(
        self,
        x_target: float,
        y_target: float,
        focus_target: int | None = None,
    ) -> bool:
        clamped_focus = self._active_focus_target(focus_target)
        if clamped_focus is not None:
            current_focus = self._get_focus_position()
            delta_focus = clamped_focus - current_focus
            if delta_focus != 0:
                self._apply_focus_wiggle_with_x_compensation(delta_focus)
        return self._goto_xy_with_reset_recovery(
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

        if self.config.layer in ["V", "U"]:
            refined = refine_position(
                target_x, target_y, self.config.dx, self.config.dy
            )
            if refined is not None:
                target_x, target_y = refined

        if not is_in_measurable_area(target_x, target_y):
            LOGGER.warning(
                "Auto-step pose %s,%s for wire %s is outside the measurable area; falling back to provider.",
                target_x,
                target_y,
                wire_number,
            )
            return self.wire_position_provider.get_pose(
                self.config,
                wire_number,
                self._get_focus_position(),
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
        if self._wiggle_event and self._wiggle_event.is_set():
            return

        self._wiggle_event = threading.Event()
        self._wiggle_event.set()

        start_x, start_y = self.get_current_xy_position()
        # Wiggle by roughly half the wire pitch to avoid hitting adjacent wires
        wiggle_width = MEASUREMENT_WIGGLE_CONFIG.background_y_sigma_mm

        def _run() -> None:
            while self._wiggle_event and self._wiggle_event.is_set():
                self.goto_xy_func(
                    start_x,
                    self._gauss(start_y, wiggle_width),
                    speed=MEASUREMENT_WIGGLE_CONFIG.background_speed,
                )
                if self._wiggle_event is not None and not self._wiggle_event.is_set():
                    break
                time.sleep(MEASUREMENT_WIGGLE_CONFIG.background_interval_seconds)

        self._wiggle_thread = threading.Thread(target=_run, daemon=True)
        self._wiggle_thread.start()

    def stop_wiggle(self) -> None:
        """Stop the background winder wiggle thread."""
        if not self._wiggle_event:
            return
        self.motion.set_speed()
        self._wiggle_event.clear()
        if self._wiggle_thread:
            self._wiggle_thread.join(timeout=0.1)
        self._wiggle_event = None
        self._wiggle_thread = None
        self.motion.reset_plc()

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
        if not self.sweeping_wiggle or self.sweeping_wiggle_span_mm <= 0.0:
            return
        self._stop_sweeping_wiggle(return_to_center=False)

        stop_event = threading.Event()
        stop_event.set()
        self._sweeping_wiggle_event = stop_event

        low_y = float(center_y - self.sweeping_wiggle_span_mm)
        high_y = float(center_y + self.sweeping_wiggle_span_mm)
        record_duration = max(float(self.config.record_duration), 1e-6)
        sweep_speed_mm_s = max(
            (float(self.sweeping_wiggle_span_mm)),
            1e-3,
        )

        def _run() -> None:
            target_y = high_y
            while stop_event.is_set():
                if check_stop_event(
                    self.stop_event, "tension measurement interrupted!"
                ):
                    break
                if not self._goto_xy_with_reset_recovery(
                    center_x,
                    target_y,
                    context="Sweeping wiggle",
                    speed=sweep_speed_mm_s,
                ):
                    break
                target_y = low_y if abs(target_y - high_y) < 1e-9 else high_y

        self._sweeping_wiggle_thread = threading.Thread(target=_run, daemon=True)
        self._sweeping_wiggle_thread.start()

    def _stop_sweeping_wiggle(
        self,
        *,
        return_to_center: bool,
        center_x: float | None = None,
        center_y: float | None = None,
        focus_target: int | None = None,
    ) -> None:
        stop_event = self._sweeping_wiggle_event
        if stop_event is not None:
            stop_event.clear()
        if self._sweeping_wiggle_thread is not None:
            self._sweeping_wiggle_thread.join(timeout=1.0)
        self._sweeping_wiggle_event = None
        self._sweeping_wiggle_thread = None
        self.motion.set_speed()
        if return_to_center and center_x is not None and center_y is not None:
            self._move_to_measurement_pose(center_x, center_y, focus_target)

    @staticmethod
    def _sample_rms(audio_sample: Any) -> float:
        """Return the RMS amplitude of an audio sample."""

        audio_array = np.asarray(audio_sample, dtype=np.float32).reshape(-1)
        if audio_array.size == 0:
            return 0.0
        try:
            from dune_tension import rust_audio

            if rust_audio.should_use_audio_backend():
                return rust_audio.rms(audio_array)
        except Exception:
            import os

            if os.environ.get("DUNE_AUDIO_BACKEND", "").strip().lower() == "rust":
                raise
        audio_float = audio_array.astype(np.float64, copy=False)
        return float(np.sqrt(np.mean(np.square(audio_float))))

    def _triangle_reference_rms(self, expected_frequency: float | None) -> float:
        """Return the RMS of a unit-peak triangle wave over the full record window."""

        try:
            sample_rate = int(self.samplerate)
            duration = float(self.config.record_duration)
            if expected_frequency is None:
                return float("nan")
            frequency = float(expected_frequency)
        except (TypeError, ValueError):
            return float("nan")

        if sample_rate <= 0 or not np.isfinite(duration) or duration <= 0.0:
            return float("nan")
        if not np.isfinite(frequency) or frequency <= 0.0:
            return float("nan")
        try:
            from dune_tension import rust_audio

            if rust_audio.should_use_audio_backend():
                return rust_audio.triangle_reference_rms(
                    sample_rate,
                    duration,
                    frequency,
                )
        except Exception:
            import os

            if os.environ.get("DUNE_AUDIO_BACKEND", "").strip().lower() == "rust":
                raise

        sample_count = max(int(round(duration * sample_rate)), 1)
        times = np.arange(sample_count, dtype=np.float64) / float(sample_rate)
        phase = np.mod(times * frequency, 1.0)
        triangle_wave = 1.0 - 4.0 * np.abs(phase - 0.5)
        return float(np.sqrt(np.mean(np.square(triangle_wave))))

    def _amplitude_confidence(
        self,
        audio_sample: Any,
        expected_frequency: float | None,
    ) -> float:
        """Return amplitude confidence normalized to the expected triangle-wave RMS."""

        measured_rms = self._sample_rms(audio_sample)
        reference_rms = self._triangle_reference_rms(expected_frequency)
        if not np.isfinite(reference_rms) or reference_rms <= 0.0:
            return measured_rms
        return measured_rms / reference_rms

    def _is_audio_worth_analyzing(self, audio_sample: Any) -> bool:
        """Return True if the sample has enough signal to justify NN analysis."""

        measured_rms = self._sample_rms(audio_sample)
        if self.noise_threshold > 0.0 and measured_rms < self.noise_threshold * 1.5:
            return False

        return True

    def _estimate_sample_pitch(
        self,
        audio_sample: Any,
        expected_frequency: float | None,
    ) -> tuple[Any | None, float, float]:
        """Estimate pitch using PESTO, gated by ACF and FFT corroboration.

        Acceptance is determined by whether the NN frequency is corroborated by
        a notable autocorrelation peak (within ±15 %) and a notable FFT peak
        (within ±10 %).  Neither peak has to be the global maximum.  When
        corroborated, confidence is raised to at least the configured threshold
        so the measurement loop accepts the sample immediately.  When not
        corroborated, confidence is zeroed so the loop continues searching —
        regardless of what PESTO reported.
        """
        from spectrum_analysis.pitch_validation import nn_pitch_is_corroborated

        self._last_pitch_triplet_accepted = None
        analysis = None

        if not self._is_audio_worth_analyzing(audio_sample):
            return None, 0.0, 0.0

        require_corroboration = False
        try:
            analysis = analyze_audio_with_pesto(
                audio_sample,
                self.samplerate,
                expected_frequency=expected_frequency,
                include_activations=True,
            )
            frequency, confidence = analysis.frequency, analysis.confidence
            require_corroboration = True
        except Exception:
            frequency, confidence = estimate_pitch_from_audio(
                audio_sample,
                self.samplerate,
                expected_frequency,
            )

        if require_corroboration and np.isfinite(frequency) and frequency > 0.0:
            corroborated = nn_pitch_is_corroborated(
                np.asarray(audio_sample, dtype=np.float64),
                self.samplerate,
                float(frequency),
            )
            if corroborated:
                self._last_pitch_triplet_accepted = True
                # ACF and FFT agree: accept regardless of NN confidence.
                confidence = max(
                    float(confidence), float(self.config.confidence_threshold)
                )
                LOGGER.debug(
                    "NN pitch %.1f Hz corroborated by ACF/FFT; confidence=%.2f.",
                    frequency,
                    confidence,
                )
            else:
                LOGGER.debug(
                    "NN pitch %.1f Hz not corroborated by ACF/FFT; rejecting sample.",
                    frequency,
                )
                self._last_pitch_triplet_accepted = False
                confidence = 0.0

        return analysis, float(frequency), float(confidence)

    def _sample_harmonic_features(
        self,
        audio_sample: Any,
        frequency: float,
        expected_frequency: float | None,
    ) -> HarmonicSampleFeatures:
        """Measure comb features on a captured sample for trigger learning."""

        comb_cfg = self._harmonic_comb_config
        frame_size = max(1, int(getattr(comb_cfg, "frame_size", 2048)))
        harmonicity_audio = np.asarray(audio_sample, dtype=np.float32).reshape(-1)
        if harmonicity_audio.size < frame_size:
            return HarmonicSampleFeatures()

        frame = harmonicity_audio[:frame_size]
        f0 = None
        if expected_frequency is not None:
            expected = float(expected_frequency)
            if np.isfinite(expected) and expected > 0.0:
                f0 = expected
        if f0 is None and np.isfinite(frequency) and frequency > 0.0:
            f0 = float(frequency)
        if f0 is None:
            return HarmonicSampleFeatures()

        from spectrum_analysis.comb_trigger import harmonic_comb_response

        window = np.hanning(frame_size).astype(np.float32)
        freq_bins = np.fft.rfftfreq(frame_size, d=1.0 / self.samplerate)
        candidates = np.array([float(f0)], dtype=np.float64)
        weights = comb_cfg.harmonic_weights()
        harmonicity, spectral_flatness, valid = harmonic_comb_response(
            frame,
            self.samplerate,
            window,
            freq_bins,
            candidates,
            weights,
            int(comb_cfg.min_harmonics),
        )
        return HarmonicSampleFeatures(
            harmonicity=float(harmonicity),
            spectral_flatness=float(spectral_flatness),
            valid=bool(valid),
        )

    def _learn_harmonic_trigger(
        self,
        features: HarmonicSampleFeatures,
        accepted_by_triplet: bool | None,
    ) -> None:
        """Adapt comb trigger parameters from downstream pitch acceptance."""

        if accepted_by_triplet is None or not features.valid:
            return
        learner = self._harmonic_trigger_learner
        if learner is None:
            return
        try:
            from spectrum_analysis.comb_trigger import HarmonicCombTriggerObservation

            learner.observe(
                HarmonicCombTriggerObservation(
                    harmonicity=features.harmonicity,
                    spectral_flatness=features.spectral_flatness,
                    accepted_by_triplet=bool(accepted_by_triplet),
                )
            )
        except Exception as exc:
            LOGGER.debug("Harmonic trigger learning skipped: %s", exc)

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

        U/V layers go through the Rust core; X/G layers fall back to the
        Python ``measure_list`` path because the Rust planner has no
        database-snapshot lookup for vertical wires and would otherwise
        skip every wire.
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
            if self.config.layer in ("X", "G"):
                try:
                    self.measure_list(wires_to_measure, preserve_order=False)
                except KeyboardInterrupt:
                    LOGGER.info("Measurement interrupted by user.")
            else:
                import dune_tension_core

                def pesto_wrapper(audio, samplerate, expected_frequency):
                    return analyze_audio_with_pesto(
                        audio,
                        samplerate,
                        expected_frequency=expected_frequency,
                        include_activations=False,
                    )

                core = dune_tension_core.Tensiometer(
                    config=self.config,
                    motion_service=self.motion,
                    goto_xy_func=self._goto_xy_with_reset_recovery,
                    get_current_xy_position=self.get_current_xy_position,
                    focus_wiggle_func=self._apply_focus_wiggle_with_x_compensation,
                    focus_position_getter=self.focus_position_getter,
                    focus_range_getter=self.focus_range_getter,
                    use_manual_focus=self.use_manual_focus,
                    manual_focus_target=self.manual_focus_target,
                    stop_event=self.stop_event,
                    repository=self.repository,
                    audio_service=self.audio,
                    strum_func=self.strum_func,
                    pesto_func=pesto_wrapper,
                    harmonic_comb_config=self._harmonic_comb_config,
                )

                try:
                    with self.measurement_session():
                        core.measure_auto()
                except KeyboardInterrupt:
                    LOGGER.info("Measurement interrupted by user.")
                except Exception as exc:
                    LOGGER.exception("Rust measurement core failed: %s", exc)
        finally:
            stop_progress.set()
            monitor_thread.join(timeout=3.0)
            try:
                del self.repository.append_result
            except AttributeError:
                self.repository.append_result = original_append  # type: ignore[method-assign]
            if not check_stop_event(self.stop_event):
                self.estimated_time_callback("0:00:00")

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
                    self._complete_wire_profile()
                    if result is not None and float(result.frequency) > 0.0:
                        last_successful_result = result
                        last_successful_wire_number = int(target.wire_number)
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
        expected_frequency = wire_equation(length=length)["frequency"]
        amplitude_mode = self.config.confidence_source == "signal_amplitude"
        measuring_timeout = self.config.measuring_duration
        candidate_wires: list[TensionResult] = []
        measured_zone = int(zone) if zone is not None else None

        recording_started_event = threading.Event()

        def on_recording_started() -> None:
            recording_started_event.set()
            self._record_wire_stage(
                "wait_for_audio_trigger", self._profile_time() - strum_started
            )

        audio_acquisition_config = AudioAcquisitionConfig(
            sample_rate=self.samplerate,
            max_record_seconds=self.config.record_duration,
            expected_f0=expected_frequency,
            snr_threshold_db=self.snr,
            trigger_mode=("harmonic_comb" if self.use_harmonic_comb_trigger else "snr"),
            comb_trigger=self._harmonic_comb_config,
            recording_started_callback=on_recording_started,
            stop_event=self.stop_event,
        )

        x_step_mm = max(
            0.1,
            min(
                length * MEASUREMENT_WIGGLE_CONFIG.xy_sigma_per_meter,
                MEASUREMENT_WIGGLE_CONFIG.xy_sigma_cap_mm,
            ),
        )
        y_step_mm = max(0.05, float(self.wiggle_y_sigma_mm))
        focus_step_quarter_us = max(10, int(abs(self.focus_wiggle_sigma_quarter_us)))

        min_x_step_mm = 0.1
        min_y_step_mm = 0.05
        min_focus_step_quarter_us = 5

        best_confidence = -1.0
        best_x = float(wire_x)
        best_y = float(wire_y)
        initial_focus = self._active_focus_target()
        best_focus = (
            self._get_focus_position() if initial_focus is None else int(initial_focus)
        )
        axis_index = 0
        threshold_reached = False
        pending_best_sample: DeferredPitchSample | None = None
        legacy_tension_condition_active = (
            self._legacy_tension_condition_predicate is not None
        )

        def _legacy_tension_condition_ok(tension: float) -> bool:
            predicate = self._legacy_tension_condition_predicate
            if predicate is None:
                return True
            return bool(predicate(tension))

        def _publish_audio_sample(audio_sample: Any, analysis: Any | None) -> None:
            try:
                self.audio_sample_callback(audio_sample, self.samplerate, analysis)
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
                wire_equation(length=length, frequency=frequency),
                confidence,
                amplitude,
                harmonicity,
            )
            return TensionResult.from_measurement(
                apa_name=self.config.apa_name,
                layer=self.config.layer,
                side=self.config.side,
                wire_number=wire_number,
                frequency=frequency,
                confidence=confidence,
                x=x,
                y=y,
                focus_position=focus_position,
                zone=zone,
                time=self._now(),
                taped=self._is_current_side_taped(),
                amplitude=amplitude,
                harmonicity=harmonicity,
            )

        def _analyze_sample(
            sample: DeferredPitchSample,
        ) -> TensionResult:
            analysis, frequency, _nn_confidence = self._estimate_sample_pitch(
                sample.audio_sample,
                expected_frequency,
            )
            _publish_audio_sample(sample.audio_sample, analysis)

            features = self._sample_harmonic_features(
                sample.audio_sample,
                frequency,
                expected_frequency,
            )
            self._learn_harmonic_trigger(
                features,
                self._last_pitch_triplet_accepted,
            )

            wire_result = _build_wire_result(
                confidence=sample.confidence,
                frequency=frequency,
                x=sample.x,
                y=sample.y,
                focus_position=sample.focus_position,
                zone=measured_zone,
                amplitude=self._sample_rms(sample.audio_sample),
                harmonicity=features.harmonicity,
            )
            self.repository.append_sample(wire_result)
            return wire_result

        def _move_to_pose(x_target: float, y_target: float, focus_target: int) -> None:
            diagonal_geometry = (
                abs(float(self.config.dx)) > 1e-9 and abs(float(self.config.dy)) > 1e-9
            )
            y_per_x = (
                (-float(self.config.dy) / float(self.config.dx))
                if diagonal_geometry
                else 0.0
            )
            clamped_focus = self._active_focus_target(focus_target)
            if clamped_focus is None:
                clamped_focus = self._clamp_focus_position(int(focus_target))
            current_focus = self._get_focus_position()
            delta_focus = int(clamped_focus - current_focus)
            if delta_focus != 0:
                prior_x: float | None = None
                try:
                    prior_x, _prior_y = self.get_current_xy_position()
                except Exception:
                    prior_x = None

                compensated_x = self._apply_focus_wiggle_with_x_compensation(
                    delta_focus
                )
                focus_x_delta = self._focus_to_x_delta_mm(delta_focus)
                if compensated_x is not None and prior_x is not None:
                    focus_x_delta = float(compensated_x) - float(prior_x)

                if not self.use_manual_focus:
                    x_target = float(x_target + focus_x_delta)
                    if diagonal_geometry:
                        y_target = float(y_target + (focus_x_delta * y_per_x))
            if not self._goto_xy_with_reset_recovery(
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
                abs(float(self.config.dx)) > 1e-9 and abs(float(self.config.dy)) > 1e-9
            )
            y_per_x = (
                (-float(self.config.dy) / float(self.config.dx))
                if diagonal_geometry
                else 0.0
            )

            target_x = float(self._gauss(best_x, x_step_mm))
            if diagonal_geometry:
                target_y = float(best_y + ((target_x - best_x) * y_per_x))
            else:
                target_y = float(self._gauss(best_y, y_step_mm))
            target_focus = int(best_focus)

            if (
                self._has_focus_wiggle_callback
                and not self.use_manual_focus
                and focus_step_quarter_us > 0
            ):
                target_focus = self._clamp_focus_position(
                    int(round(self._gauss(best_focus, focus_step_quarter_us)))
                )

            axis_index += 1
            if axis_index >= 2:
                axis_index = 0
                x_step_mm = max(min_x_step_mm, x_step_mm * 0.85)
                y_step_mm = max(min_y_step_mm, y_step_mm * 0.85)
                if self._has_focus_wiggle_callback and not self.use_manual_focus:
                    focus_step_quarter_us = max(
                        min_focus_step_quarter_us,
                        int(focus_step_quarter_us * 0.85),
                    )

            return float(target_x), float(target_y), int(target_focus)

        if self.sweeping_wiggle and self.sweeping_wiggle_span_mm > 0.0:
            self._start_sweeping_wiggle(
                center_x=float(wire_x),
                center_y=float(wire_y),
                focus_target=best_focus,
            )

        try:
            while (self._time() - start_time) < measuring_timeout:
                if check_stop_event(
                    self.stop_event, "tension measurement interrupted!"
                ):
                    return None
                x, y = self.get_current_xy_position()

                # Strum on a regular interval while audio acquisition runs in
                # a background thread, stopping as soon as the audio trigger
                # callback fires (or the thread completes).
                strum_started = self._profile_time()
                recording_started_event.clear()
                acquired_audio: list[Any] = []
                acquired_exc: list[BaseException] = []

                def _audio_worker() -> None:
                    try:
                        sample = acquire_audio(
                            cfg=audio_acquisition_config,
                            noise_rms=self.noise_threshold / 3,
                            timeout=max(float(self.config.record_duration), 0.0),
                        )
                        acquired_audio.append(sample)
                    except BaseException as exc:
                        acquired_exc.append(exc)

                acquire_started = self._profile_time()
                audio_thread = threading.Thread(target=_audio_worker, daemon=True)
                audio_thread.start()

                while audio_thread.is_alive() and not recording_started_event.is_set():
                    self.strum_func()
                    if recording_started_event.wait(
                        timeout=_STRUM_LOOP_INTERVAL_SECONDS
                    ):
                        break

                audio_thread.join()
                self._record_wire_stage("strum", self._profile_time() - strum_started)
                self._record_wire_stage(
                    "acquire_audio",
                    self._profile_time() - acquire_started,
                )
                if acquired_exc:
                    raise acquired_exc[0]
                audio_sample = acquired_audio[0] if acquired_audio else None

                if audio_sample is not None:
                    focus_position = self._get_focus_position()
                    if self._audio_store is not None:
                        _rec_meta = AudioRecordingMeta(
                            apa_name=self.config.apa_name,
                            layer=self.config.layer,
                            side=self.config.side,
                            wire_number=wire_number,
                            x_mm=float(x),
                            y_mm=float(y),
                            focus_position=focus_position,
                            zone=measured_zone,
                            wire_length_m=float(length),
                            timestamp=self._now(),
                        )
                        self._audio_store.save(audio_sample, self.samplerate, _rec_meta)
                    if amplitude_mode:
                        analyze_started = self._profile_time()
                        confidence = self._amplitude_confidence(
                            audio_sample,
                            expected_frequency,
                        )
                        self._record_wire_stage(
                            "analyze_audio",
                            self._profile_time() - analyze_started,
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

                        if confidence >= self.config.confidence_threshold:
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
                                    self.legacy_tension_condition,
                                )
                            if tension_plausible(wire_result.tension) and condition_ok:
                                candidate_wires.append(wire_result)
                                break
                        elif is_new_best:
                            _flush_pending_skipped_sample()
                            pending_best_sample = current_sample
                        else:
                            _publish_audio_sample(audio_sample, None)
                    else:
                        analyze_started = self._profile_time()
                        analysis, frequency, confidence = self._estimate_sample_pitch(
                            audio_sample,
                            expected_frequency,
                        )
                        self._record_wire_stage(
                            "analyze_audio",
                            self._profile_time() - analyze_started,
                        )
                        _publish_audio_sample(audio_sample, analysis)
                        features = self._sample_harmonic_features(
                            audio_sample,
                            frequency,
                            expected_frequency,
                        )
                        self._learn_harmonic_trigger(
                            features,
                            self._last_pitch_triplet_accepted,
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
                        self.repository.append_sample(wire_result)

                        condition_ok = _legacy_tension_condition_ok(wire_result.tension)
                        if not condition_ok and legacy_tension_condition_active:
                            LOGGER.info(
                                "Sample of wire %s tension %.2f did not satisfy legacy tension condition %r; continuing.",
                                wire_number,
                                wire_result.tension,
                                self.legacy_tension_condition,
                            )
                        if tension_plausible(wire_result.tension) and condition_ok:
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
                            if (
                                wire_result.confidence
                                >= self.config.confidence_threshold
                            ):
                                break
                else:
                    LOGGER.info("Sample of wire %s: no audio detected.", wire_number)
                if (self._time() - start_time) >= measuring_timeout:
                    break

                if self.sweeping_wiggle and self.sweeping_wiggle_span_mm > 0.0:
                    continue

                target_x, target_y, target_focus = _next_pose()
                LOGGER.info(
                    "Optimizer next pose: x=%s y=%s focus=%s",
                    target_x,
                    target_y,
                    target_focus,
                )
                optimizer_move_started = self._profile_time()
                try:
                    _move_to_pose(target_x, target_y, target_focus)
                except RuntimeError as exc:
                    self._record_wire_stage(
                        "optimizer_move",
                        self._profile_time() - optimizer_move_started,
                    )
                    LOGGER.warning("%s", exc)
                    break
                self._record_wire_stage(
                    "optimizer_move",
                    self._profile_time() - optimizer_move_started,
                )
        finally:
            self._stop_sweeping_wiggle(
                return_to_center=return_to_center
                and bool(self.sweeping_wiggle and self.sweeping_wiggle_span_mm > 0.0),
                center_x=float(wire_x),
                center_y=float(wire_y),
                focus_target=best_focus,
            )

        if amplitude_mode and pending_best_sample is not None:
            if threshold_reached and not legacy_tension_condition_active:
                _flush_pending_skipped_sample()
            else:
                wire_result = _analyze_sample(pending_best_sample)
                pending_best_sample = None
                if tension_plausible(
                    wire_result.tension
                ) and _legacy_tension_condition_ok(wire_result.tension):
                    candidate_wires.append(wire_result)
        else:
            _flush_pending_skipped_sample()
        return candidate_wires

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
