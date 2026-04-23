from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import math
import sys
import time
import types

import numpy as np
import pytest

import dune_tension.results as results_module
import dune_tension.tensiometer as tensiometer_module
from dune_tension.results import TensionResult
from dune_tension.tensiometer import Tensiometer
from dune_tension.tensiometer_functions import PlannedWirePose


class DummyRepository:
    def __init__(self) -> None:
        self.samples: list[TensionResult] = []
        self.results: list[TensionResult] = []

    @contextmanager
    def run_scope(self):
        yield self

    def append_sample(self, result: TensionResult) -> None:
        self.samples.append(result)

    def append_result(self, result: TensionResult) -> None:
        self.results.append(result)

    def close(self) -> None:
        return None


def _make_motion_service(start_x: float = 0.0, start_y: float = 0.0):
    state = {"x": float(start_x), "y": float(start_y)}
    moves: list[tuple[float, float]] = []

    def get_xy() -> tuple[float, float]:
        return state["x"], state["y"]

    def goto_xy(x: float, y: float, **_kwargs) -> bool:
        moves.append((x, y))
        state["x"] = float(x)
        state["y"] = float(y)
        return True

    return types.SimpleNamespace(
        get_xy=get_xy,
        goto_xy=goto_xy,
        increment=lambda *_args, **_kwargs: None,
        reset_plc=lambda *_args, **_kwargs: None,
        set_speed=lambda *_args, **_kwargs: True,
        moves=moves,
        state=state,
    )


def _make_recovering_motion_service(
    results: list[bool],
    *,
    start_x: float = 0.0,
    start_y: float = 0.0,
):
    state = {"x": float(start_x), "y": float(start_y)}
    moves: list[tuple[float, float]] = []
    reset_calls = {"count": 0}
    outcomes = iter(results)

    def get_xy() -> tuple[float, float]:
        return state["x"], state["y"]

    def goto_xy(x: float, y: float, **_kwargs) -> bool:
        moves.append((x, y))
        outcome = next(outcomes, True)
        if outcome:
            state["x"] = float(x)
            state["y"] = float(y)
        return outcome

    def reset_plc(*_args, **_kwargs) -> None:
        reset_calls["count"] += 1

    return types.SimpleNamespace(
        get_xy=get_xy,
        goto_xy=goto_xy,
        increment=lambda *_args, **_kwargs: None,
        reset_plc=reset_plc,
        set_speed=lambda *_args, **_kwargs: True,
        moves=moves,
        state=state,
        reset_calls=reset_calls,
    )


def _make_audio_service(sample_rate: int = 8000):
    return types.SimpleNamespace(
        samplerate=sample_rate,
        noise_threshold=0.0,
        record_audio=lambda *_args, **_kwargs: ([], 0.0),
    )


class _StubWirePositionProvider:
    def __init__(self, poses: dict[int, PlannedWirePose]) -> None:
        self._poses = dict(poses)
        self.calls: list[tuple[int, int | None]] = []

    def get_pose(
        self,
        _config,
        wire_number: int,
        current_focus_position: int | None = None,
    ) -> PlannedWirePose | None:
        self.calls.append((int(wire_number), current_focus_position))
        return self._poses.get(int(wire_number))


def _patch_result_physics(monkeypatch) -> None:
    monkeypatch.setattr(results_module, "zone_lookup", lambda _x: 1)
    monkeypatch.setattr(
        results_module,
        "length_lookup",
        lambda _layer, _wire, _zone, taped=False: 1.0,
    )
    monkeypatch.setattr(
        results_module,
        "wire_equation",
        lambda length, frequency: {"tension": float(frequency) * 0.1, "frequency": frequency},
    )
    monkeypatch.setattr(results_module, "tension_pass", lambda _tension, _length: True)


def test_merge_results_returns_only_sample(monkeypatch):
    _patch_result_physics(monkeypatch)
    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=_make_motion_service(),
        audio=_make_audio_service(),
        repository=DummyRepository(),
    )
    sample = TensionResult.from_measurement(
        apa_name="APA",
        layer="X",
        side="A",
        wire_number=1,
        frequency=5.0,
        confidence=0.9,
        x=1.0,
        y=2.0,
        time=datetime(2026, 3, 15, 12, 0, 0),
    )

    result = tensiometer._merge_results([sample], wire_number=1, wire_x=1.5, wire_y=2.5)

    assert result is sample
    assert result.frequency == 5.0
    assert result.tension == pytest.approx(0.5)
    assert result.tension_pass is True
    assert result.zone == 1
    assert result.wire_length == pytest.approx(1.0)


def test_merge_results_returns_highest_confidence_sample(monkeypatch):
    _patch_result_physics(monkeypatch)
    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=_make_motion_service(),
        audio=_make_audio_service(),
        repository=DummyRepository(),
        samples_per_wire=3,
    )
    samples = [
        TensionResult.from_measurement(
            apa_name="APA",
            layer="X",
            side="A",
            wire_number=1,
            frequency=1.0,
            confidence=0.5,
            x=0.0,
            y=0.0,
            time=datetime(2026, 3, 15, 12, 0, 0),
        ),
        TensionResult.from_measurement(
            apa_name="APA",
            layer="X",
            side="A",
            wire_number=1,
            frequency=2.0,
            confidence=0.6,
            x=0.2,
            y=0.2,
            time=datetime(2026, 3, 15, 12, 0, 1),
        ),
        TensionResult.from_measurement(
            apa_name="APA",
            layer="X",
            side="A",
            wire_number=1,
            frequency=3.0,
            confidence=0.7,
            x=0.4,
            y=0.4,
            time=datetime(2026, 3, 15, 12, 0, 2),
        ),
    ]

    result = tensiometer._merge_results(samples, wire_number=1, wire_x=2.0, wire_y=3.0)

    assert result is samples[-1]
    assert result.frequency == 3.0
    assert result.tension == pytest.approx(0.3)
    assert result.confidence == pytest.approx(0.7)
    assert result.x == pytest.approx(0.4)
    assert result.y == pytest.approx(0.4)


def test_collect_samples_stops_when_confidence_threshold_is_met(monkeypatch):
    _patch_result_physics(monkeypatch)
    repository = DummyRepository()

    monkeypatch.setattr(tensiometer_module, "acquire_audio", lambda **_kwargs: [1.0])
    monkeypatch.setattr(
        tensiometer_module,
        "wire_equation",
        lambda *, length, frequency=None: {
            "frequency": 5.0,
            "tension": 0.5 if frequency is not None else 0.0,
        },
    )
    monkeypatch.setattr(tensiometer_module, "tension_plausible", lambda _tension: True)
    monkeypatch.setattr(
        tensiometer_module,
        "estimate_pitch_from_audio",
        lambda *_args: (5.0, 0.95),
    )

    def _raise_analysis(*_args, **_kwargs):
        raise RuntimeError("fallback to simple pitch estimate")

    monkeypatch.setattr(tensiometer_module, "analyze_audio_with_pesto", _raise_analysis)

    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=_make_motion_service(start_x=1.0, start_y=2.0),
        audio=_make_audio_service(),
        repository=repository,
        samples_per_wire=5,
        confidence_threshold=0.9,
        measuring_duration=1.0,
        datetime_provider=lambda: datetime(2026, 3, 15, 12, 0, 0),
    )
    tensiometer.strum_func = lambda: None
    tensiometer.focus_wiggle_func = lambda _delta: None

    samples = tensiometer._collect_samples(
        wire_number=1,
        length=1.0,
        start_time=time.time(),
        wire_y=2.0,
        wire_x=1.0,
    )

    assert len(repository.samples) == 1
    assert len(samples) == 1
    assert samples[0].confidence == pytest.approx(0.95)


def test_collect_samples_keeps_sampling_until_legacy_tension_condition_matches(
    monkeypatch,
):
    _patch_result_physics(monkeypatch)
    repository = DummyRepository()
    frequencies = iter([50.0, 70.0])

    monkeypatch.setattr(tensiometer_module, "acquire_audio", lambda **_kwargs: [1.0])
    monkeypatch.setattr(
        tensiometer_module,
        "estimate_pitch_from_audio",
        lambda *_args: (next(frequencies), 0.95),
    )

    def _raise_analysis(*_args, **_kwargs):
        raise RuntimeError("fallback to simple pitch estimate")

    monkeypatch.setattr(tensiometer_module, "analyze_audio_with_pesto", _raise_analysis)

    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=_make_motion_service(start_x=1.0, start_y=2.0),
        audio=_make_audio_service(),
        repository=repository,
        confidence_threshold=0.9,
        measuring_duration=1.0,
        legacy_tension_condition="t > 6",
        datetime_provider=lambda: datetime(2026, 3, 15, 12, 0, 0),
    )
    tensiometer.strum_func = lambda: None

    samples = tensiometer._collect_samples(
        wire_number=1,
        length=1.0,
        start_time=time.time(),
        wire_y=2.0,
        wire_x=1.0,
    )

    assert len(repository.samples) == 2
    assert samples is not None
    assert len(samples) == 1
    assert samples[0].frequency == pytest.approx(70.0)
    assert samples[0].tension == pytest.approx(7.0)


def test_collect_samples_waits_for_quiet_before_audio(monkeypatch):
    _patch_result_physics(monkeypatch)
    repository = DummyRepository()
    events: list[str] = []

    def _acquire_audio(**_kwargs):
        events.append("audio")
        return [1.0]

    monkeypatch.setattr(tensiometer_module, "acquire_audio", _acquire_audio)
    monkeypatch.setattr(
        tensiometer_module,
        "wire_equation",
        lambda *, length, frequency=None: {
            "frequency": 5.0,
            "tension": 0.5 if frequency is not None else 0.0,
        },
    )
    monkeypatch.setattr(tensiometer_module, "tension_plausible", lambda _tension: True)
    monkeypatch.setattr(
        tensiometer_module,
        "estimate_pitch_from_audio",
        lambda *_args: (5.0, 0.95),
    )
    monkeypatch.setattr(
        tensiometer_module,
        "analyze_audio_with_pesto",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("fallback")),
    )

    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=_make_motion_service(start_x=1.0, start_y=2.0),
        audio=_make_audio_service(),
        repository=repository,
        confidence_threshold=0.9,
        measuring_duration=1.0,
        quiet_waiter=lambda: events.append("quiet"),
        datetime_provider=lambda: datetime(2026, 3, 15, 12, 0, 0),
    )
    tensiometer.strum_func = lambda: None

    tensiometer._collect_samples(
        wire_number=1,
        length=1.0,
        start_time=time.time(),
        wire_y=2.0,
        wire_x=1.0,
    )

    assert events[0] == "audio"


def test_move_to_measurement_pose_uses_manual_focus_in_legacy_mode() -> None:
    motion = _make_motion_service(start_x=1.0, start_y=2.0)
    focus_moves: list[int] = []
    focus_state = {"value": 4300}

    def _focus_wiggle(delta: int) -> None:
        focus_state["value"] += int(delta)
        focus_moves.append(int(delta))

    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=motion,
        audio=_make_audio_service(),
        repository=DummyRepository(),
        focus_wiggle=_focus_wiggle,
        focus_position_getter=lambda: focus_state["value"],
        use_manual_focus=True,
        manual_focus_target=5000,
    )

    moved = tensiometer._move_to_measurement_pose(4.0, 5.0, focus_target=6100)

    assert moved is True
    assert focus_moves == [700]
    assert focus_state["value"] == 5000
    assert motion.moves[-1] == (4.0, 5.0)


def test_default_quiet_waiter_requires_one_second_of_silence(monkeypatch):
    chunk_size = 128
    quiet_chunk = np.full(chunk_size, 0.05, dtype=np.float32)
    noisy_chunk = np.full(chunk_size, 0.2, dtype=np.float32)
    chunks = [quiet_chunk] * 7 + [noisy_chunk] + [quiet_chunk] * 8
    created_sources: list[object] = []

    class FakeMicSource:
        def __init__(self, sample_rate: int, requested_chunk_size: int) -> None:
            assert sample_rate == 1000
            assert requested_chunk_size == chunk_size
            self.read_count = 0
            self.started = False
            self.stopped = False
            created_sources.append(self)

        def start(self) -> None:
            self.started = True

        def read(self) -> np.ndarray:
            chunk = chunks[min(self.read_count, len(chunks) - 1)]
            self.read_count += 1
            return chunk

        def stop(self) -> None:
            self.stopped = True

    monkeypatch.setitem(
        sys.modules,
        "spectrum_analysis.audio_sources",
        types.SimpleNamespace(MicSource=FakeMicSource),
    )

    runtime_bundle = types.SimpleNamespace(
        strum=lambda: None,
        servo_controller=types.SimpleNamespace(focus_position=0),
        audio=_make_audio_service(sample_rate=1000),
        motion=_make_motion_service(),
        build_repository=lambda _path: DummyRepository(),
        wire_position_provider=None,
    )
    runtime_bundle.audio.noise_threshold = 0.1

    tensiometer = tensiometer_module.build_tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        runtime_bundle=runtime_bundle,
    )

    tensiometer.quiet_waiter()

    assert len(created_sources) == 1
    source = created_sources[0]
    assert source.started is True
    assert source.stopped is True
    assert source.read_count == 16


def test_triangle_reference_rms_uses_full_recording_duration() -> None:
    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=_make_motion_service(),
        audio=_make_audio_service(),
        repository=DummyRepository(),
        record_duration=1.0,
    )

    rms = tensiometer._triangle_reference_rms(100.0)

    assert rms == pytest.approx(1.0 / math.sqrt(3.0), rel=0.01)


def test_amplitude_confidence_falls_back_to_raw_rms_when_reference_invalid() -> None:
    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=_make_motion_service(),
        audio=_make_audio_service(),
        repository=DummyRepository(),
        confidence_source="signal_amplitude",
    )

    confidence = tensiometer._amplitude_confidence([1.0, -1.0], float("nan"))

    assert confidence == pytest.approx(1.0)


def test_amplitude_mode_skips_pesto_until_threshold_then_analyzes_once(monkeypatch):
    _patch_result_physics(monkeypatch)
    repository = DummyRepository()
    low_sample = [0.1, -0.1, 0.1, -0.1]
    high_sample = [0.8, -0.8, 0.8, -0.8]
    captures = iter([low_sample, high_sample])
    analyses: list[object] = []

    monkeypatch.setattr(
        tensiometer_module,
        "acquire_audio",
        lambda **_kwargs: next(captures, None),
    )
    monkeypatch.setattr(
        tensiometer_module,
        "wire_equation",
        lambda *, length, frequency=None: {
            "frequency": 5.0,
            "tension": 0.5 if frequency is not None else 0.0,
        },
    )
    monkeypatch.setattr(tensiometer_module, "tension_plausible", lambda _tension: True)

    def _analyze(*_args, **_kwargs):
        analyses.append(object())
        marker = analyses[-1]
        return types.SimpleNamespace(frequency=5.0, confidence=0.99, marker=marker)

    monkeypatch.setattr(tensiometer_module, "analyze_audio_with_pesto", _analyze)

    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=_make_motion_service(start_x=1.0, start_y=2.0),
        audio=_make_audio_service(),
        repository=repository,
        confidence_source="signal_amplitude",
        confidence_threshold=0.9,
        record_duration=1.0,
        measuring_duration=1.0,
        datetime_provider=lambda: datetime(2026, 3, 15, 12, 0, 0),
    )
    tensiometer.strum_func = lambda: None
    published: list[tuple[list[float], object | None]] = []
    tensiometer.audio_sample_callback = (
        lambda sample, _samplerate, analysis: published.append((list(sample), analysis))
    )

    samples = tensiometer._collect_samples(
        wire_number=1,
        length=1.0,
        start_time=time.time(),
        wire_y=2.0,
        wire_x=1.0,
    )

    assert len(analyses) == 1
    assert samples is not None
    assert len(samples) == 1
    assert len(repository.samples) == 1
    assert repository.samples[0].confidence > 0.9
    assert published[0] == (low_sample, None)
    assert published[1][0] == high_sample
    assert published[1][1] is not None


def test_amplitude_mode_timeout_analyzes_only_best_pending_sample(monkeypatch):
    _patch_result_physics(monkeypatch)
    repository = DummyRepository()
    weaker_sample = [0.05, -0.05, 0.05, -0.05]
    stronger_sample = [0.15, -0.15, 0.15, -0.15]
    captures = iter([weaker_sample, stronger_sample])
    analysis = types.SimpleNamespace(frequency=5.0, confidence=0.8)

    monkeypatch.setattr(
        tensiometer_module,
        "acquire_audio",
        lambda **_kwargs: next(captures, None),
    )
    monkeypatch.setattr(
        tensiometer_module,
        "wire_equation",
        lambda *, length, frequency=None: {
            "frequency": 5.0,
            "tension": 0.5 if frequency is not None else 0.0,
        },
    )
    monkeypatch.setattr(tensiometer_module, "tension_plausible", lambda _tension: True)
    analyze_calls = []
    monkeypatch.setattr(
        tensiometer_module,
        "analyze_audio_with_pesto",
        lambda *_args, **_kwargs: analyze_calls.append(True) or analysis,
    )

    times = iter([0.0, 0.01, 0.02, 0.03, 0.2])
    published: list[tuple[list[float], object | None]] = []
    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=_make_motion_service(start_x=1.0, start_y=2.0),
        audio=_make_audio_service(),
        repository=repository,
        confidence_source="signal_amplitude",
        confidence_threshold=0.9,
        record_duration=1.0,
        measuring_duration=0.05,
        time_provider=lambda: next(times),
        datetime_provider=lambda: datetime(2026, 3, 15, 12, 0, 0),
        audio_sample_callback=lambda sample, _samplerate, payload: published.append(
            (list(sample), payload)
        ),
    )
    tensiometer.strum_func = lambda: None

    samples = tensiometer._collect_samples(
        wire_number=1,
        length=1.0,
        start_time=0.0,
        wire_y=2.0,
        wire_x=1.0,
    )

    assert len(analyze_calls) == 1
    assert samples is not None
    assert len(samples) == 1
    assert len(repository.samples) == 1
    assert repository.samples[0].confidence == pytest.approx(
        tensiometer._amplitude_confidence(stronger_sample, 5.0)
    )
    assert published[0] == (weaker_sample, None)
    assert published[1] == (stronger_sample, analysis)


def test_amplitude_mode_continues_after_implausible_threshold_sample(monkeypatch):
    _patch_result_physics(monkeypatch)
    repository = DummyRepository()
    captures = iter(
        [
            [0.8, -0.8, 0.8, -0.8],
            [0.9, -0.9, 0.9, -0.9],
        ]
    )
    plausibility = iter([False, True])
    analyze_calls = []

    monkeypatch.setattr(
        tensiometer_module,
        "acquire_audio",
        lambda **_kwargs: next(captures, None),
    )
    monkeypatch.setattr(
        tensiometer_module,
        "wire_equation",
        lambda *, length, frequency=None: {
            "frequency": 5.0,
            "tension": 0.5 if frequency is not None else 0.0,
        },
    )
    monkeypatch.setattr(
        tensiometer_module,
        "tension_plausible",
        lambda _tension: next(plausibility),
    )
    monkeypatch.setattr(
        tensiometer_module,
        "analyze_audio_with_pesto",
        lambda *_args, **_kwargs: analyze_calls.append(True)
        or types.SimpleNamespace(frequency=5.0, confidence=0.99),
    )

    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=_make_motion_service(start_x=1.0, start_y=2.0),
        audio=_make_audio_service(),
        repository=repository,
        confidence_source="signal_amplitude",
        confidence_threshold=0.9,
        record_duration=1.0,
        measuring_duration=1.0,
        datetime_provider=lambda: datetime(2026, 3, 15, 12, 0, 0),
    )
    tensiometer.strum_func = lambda: None

    samples = tensiometer._collect_samples(
        wire_number=1,
        length=1.0,
        start_time=time.time(),
        wire_y=2.0,
        wire_x=1.0,
    )

    assert len(analyze_calls) == 2
    assert samples is not None
    assert len(samples) == 1
    assert len(repository.samples) == 2


def test_measure_auto_reports_estimated_time(monkeypatch):
    eta_updates = []
    summaries_stub = types.ModuleType("dune_tension.summaries")
    summaries_stub.get_missing_wires = lambda _cfg: {"A": [1, 2]}
    monkeypatch.setitem(sys.modules, "dune_tension.summaries", summaries_stub)
    provider = _StubWirePositionProvider(
        {
            1: PlannedWirePose(1, 1.0, 0.0, 4300),
            2: PlannedWirePose(2, 2.0, 0.0, 4200),
        }
    )

    collected = []
    times = iter([100.0, 110.0])
    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=_make_motion_service(),
        audio=_make_audio_service(),
        repository=DummyRepository(),
        estimated_time_callback=eta_updates.append,
        time_provider=lambda: next(times),
        wire_position_provider=provider,
    )
    tensiometer.goto_collect_wire_data = lambda **kwargs: collected.append(kwargs) or None

    tensiometer.measure_auto()

    assert eta_updates == ["0:00:10", "0:00:00"]
    assert provider.calls == [(1, 0), (2, 0)]
    assert collected == [
        {
            "wire_number": 1,
            "wire_x": 1.0,
            "wire_y": 0.0,
            "focus_position": 4300,
            "zone": None,
        },
        {
            "wire_number": 2,
            "wire_x": 2.0,
            "wire_y": 0.0,
            "focus_position": 4200,
            "zone": None,
        },
    ]


def test_measure_auto_steps_from_last_successful_measurement(monkeypatch):
    eta_updates = []
    summaries_stub = types.ModuleType("dune_tension.summaries")
    summaries_stub.get_missing_wires = lambda _cfg: {"A": [10, 12]}
    monkeypatch.setitem(sys.modules, "dune_tension.summaries", summaries_stub)

    provider = _StubWirePositionProvider(
        {
            10: PlannedWirePose(10, 100.0, 200.0, 4300),
            12: PlannedWirePose(12, 300.0, 999.0, 5200),
        }
    )

    measured_result = TensionResult.from_measurement(
        apa_name="APA",
        layer="X",
        side="A",
        wire_number=10,
        frequency=80.0,
        confidence=0.95,
        x=2500.0,
        y=1500.0,
        focus_position=4350,
        time=datetime(2026, 3, 15, 12, 0, 0),
    )
    collected: list[dict[str, object]] = []
    times = iter([100.0, 110.0])
    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=_make_motion_service(),
        audio=_make_audio_service(),
        repository=DummyRepository(),
        estimated_time_callback=eta_updates.append,
        time_provider=lambda: next(times),
        wire_position_provider=provider,
    )

    def _collect(**kwargs):
        collected.append(kwargs)
        if kwargs["wire_number"] == 10:
            return measured_result
        return None

    tensiometer.goto_collect_wire_data = _collect

    tensiometer.measure_auto()

    assert provider.calls == [(10, 0)]
    assert eta_updates == ["0:00:10", "0:00:00"]
    assert collected == [
        {
            "wire_number": 10,
            "wire_x": 100.0,
            "wire_y": 200.0,
            "focus_position": 4300,
            "zone": None,
        },
        {
            "wire_number": 12,
            "wire_x": 2500.0,
            "wire_y": 1509.5833333333333,
            "focus_position": 4350,
            "zone": None,
        },
    ]


def test_measure_list_steps_from_last_successful_measurement(monkeypatch):
    provider = _StubWirePositionProvider(
        {
            10: PlannedWirePose(10, 100.0, 200.0, 4300),
            12: PlannedWirePose(12, 300.0, 999.0, 5200),
        }
    )

    measured_result = TensionResult.from_measurement(
        apa_name="APA",
        layer="X",
        side="A",
        wire_number=10,
        frequency=80.0,
        confidence=0.95,
        x=2500.0,
        y=1500.0,
        focus_position=4350,
        time=datetime(2026, 3, 15, 12, 0, 0),
    )
    collected: list[dict[str, object]] = []
    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=_make_motion_service(),
        audio=_make_audio_service(),
        repository=DummyRepository(),
        wire_position_provider=provider,
    )

    def _collect(**kwargs):
        collected.append(kwargs)
        if kwargs["wire_number"] == 10:
            return measured_result
        return None

    tensiometer.goto_collect_wire_data = _collect

    tensiometer.measure_list([10, 12], preserve_order=True)

    assert provider.calls == [(10, 0)]
    assert collected == [
        {
            "wire_number": 10,
            "wire_x": 100.0,
            "wire_y": 200.0,
            "focus_position": 4300,
            "zone": None,
        },
        {
            "wire_number": 12,
            "wire_x": 2500.0,
            "wire_y": 1509.5833333333333,
            "focus_position": 4350,
            "zone": None,
        },
    ]


def test_measure_list_logs_timing_profile_summary(caplog):
    provider = _StubWirePositionProvider(
        {
            10: PlannedWirePose(10, 100.0, 200.0, 4300),
            12: PlannedWirePose(12, 300.0, 250.0, 4200),
        }
    )
    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=_make_motion_service(),
        audio=_make_audio_service(),
        repository=DummyRepository(),
        wire_position_provider=provider,
    )

    def _collect(**kwargs):
        tensiometer._record_wire_stage("wire_total_wall", 1.25)
        return TensionResult.from_measurement(
            apa_name="APA",
            layer="X",
            side="A",
            wire_number=int(kwargs["wire_number"]),
            frequency=80.0,
            confidence=0.95,
            x=float(kwargs["wire_x"]),
            y=float(kwargs["wire_y"]),
            focus_position=int(kwargs["focus_position"]),
            time=datetime(2026, 3, 15, 12, 0, 0),
        )

    tensiometer.goto_collect_wire_data = _collect

    with caplog.at_level("INFO"):
        tensiometer.measure_list([10, 12], preserve_order=True)

    assert "Timing profile summary for list measurement" in caplog.text
    assert "avg_wire=1.25s" in caplog.text


def test_measure_auto_uv_uses_provider_pose_for_every_wire(monkeypatch):
    summaries_stub = types.ModuleType("dune_tension.summaries")
    summaries_stub.get_missing_wires = lambda _cfg: {"A": [10, 12]}
    monkeypatch.setitem(sys.modules, "dune_tension.summaries", summaries_stub)

    provider = _StubWirePositionProvider(
        {
            10: PlannedWirePose(10, 100.0, 200.0, 4300),
            12: PlannedWirePose(12, 300.0, 999.0, 5200),
        }
    )

    measured_result = TensionResult.from_measurement(
        apa_name="APA",
        layer="U",
        side="A",
        wire_number=10,
        frequency=80.0,
        confidence=0.95,
        x=2500.0,
        y=1500.0,
        focus_position=4350,
        time=datetime(2026, 3, 15, 12, 0, 0),
    )
    collected: list[dict[str, object]] = []
    times = iter([100.0, 110.0])
    tensiometer = Tensiometer(
        apa_name="APA",
        layer="U",
        side="A",
        motion=_make_motion_service(),
        audio=_make_audio_service(),
        repository=DummyRepository(),
        estimated_time_callback=lambda _value: None,
        time_provider=lambda: next(times),
        wire_position_provider=provider,
    )

    def _collect(**kwargs):
        collected.append(kwargs)
        if kwargs["wire_number"] == 10:
            return measured_result
        return None

    tensiometer.goto_collect_wire_data = _collect

    tensiometer.measure_auto()

    assert provider.calls == [(10, 0), (12, 0)]
    assert collected == [
        {
            "wire_number": 10,
            "wire_x": 100.0,
            "wire_y": 200.0,
            "focus_position": 4300,
            "zone": None,
        },
        {
            "wire_number": 12,
            "wire_x": 300.0,
            "wire_y": 999.0,
            "focus_position": 5200,
            "zone": None,
        },
    ]


def test_measure_list_uv_uses_provider_pose_for_every_wire():
    provider = _StubWirePositionProvider(
        {
            10: PlannedWirePose(10, 100.0, 200.0, 4300),
            12: PlannedWirePose(12, 300.0, 999.0, 5200),
        }
    )

    measured_result = TensionResult.from_measurement(
        apa_name="APA",
        layer="V",
        side="B",
        wire_number=10,
        frequency=80.0,
        confidence=0.95,
        x=2500.0,
        y=1500.0,
        focus_position=4350,
        time=datetime(2026, 3, 15, 12, 0, 0),
    )
    collected: list[dict[str, object]] = []
    tensiometer = Tensiometer(
        apa_name="APA",
        layer="V",
        side="B",
        motion=_make_motion_service(),
        audio=_make_audio_service(),
        repository=DummyRepository(),
        wire_position_provider=provider,
    )

    def _collect(**kwargs):
        collected.append(kwargs)
        if kwargs["wire_number"] == 10:
            return measured_result
        return None

    tensiometer.goto_collect_wire_data = _collect

    tensiometer.measure_list([10, 12], preserve_order=True)

    assert provider.calls == [(10, 0), (12, 0)]
    assert collected == [
        {
            "wire_number": 10,
            "wire_x": 100.0,
            "wire_y": 200.0,
            "focus_position": 4300,
            "zone": None,
        },
        {
            "wire_number": 12,
            "wire_x": 300.0,
            "wire_y": 999.0,
            "focus_position": 5200,
            "zone": None,
        },
    ]


def test_load_tension_summary_uses_sqlite_backed_summary_series(tmp_path, monkeypatch):
    db_path = tmp_path / "tension_data.db"
    db_path.write_text("")
    summaries_stub = types.ModuleType("dune_tension.summaries")
    summaries_stub.get_expected_range = lambda _layer: range(1, 4)
    summaries_stub.get_tension_series = (
        lambda _config: {"A": {1: 1.0, 3: 3.0}, "B": {1: 2.0}}
    )
    monkeypatch.setitem(sys.modules, "dune_tension.summaries", summaries_stub)

    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=_make_motion_service(),
        audio=_make_audio_service(),
        repository=DummyRepository(),
    )
    tensiometer.config.data_path = str(db_path)
    a, b = tensiometer.load_tension_summary()

    assert a[0] == 1.0
    assert a[1] != a[1]
    assert a[2] == 3.0
    assert b[0] == 2.0
    assert b[1] != b[1]
    assert b[2] != b[2]


def test_load_tension_summary_missing(tmp_path):
    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=_make_motion_service(),
        audio=_make_audio_service(),
        repository=DummyRepository(),
    )
    tensiometer.config.data_path = str(tmp_path / "missing.db")
    msg, a, b = tensiometer.load_tension_summary()
    assert "File not found" in msg
    assert a == []
    assert b == []


def test_load_tension_summary_reports_missing_summary_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "empty.db"
    db_path.write_text("")
    summaries_stub = types.ModuleType("dune_tension.summaries")
    summaries_stub.get_expected_range = lambda _layer: range(1, 3)
    summaries_stub.get_tension_series = lambda _config: {"A": {}, "B": {}}
    monkeypatch.setitem(sys.modules, "dune_tension.summaries", summaries_stub)

    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=_make_motion_service(),
        audio=_make_audio_service(),
        repository=DummyRepository(),
    )
    tensiometer.config.data_path = str(db_path)
    msg, a, b = tensiometer.load_tension_summary()
    assert "No summary measurements found" in msg
    assert a == []
    assert b == []


def test_wiggle_start_stop():
    motion = _make_motion_service(start_x=1.0, start_y=2.0)
    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=motion,
        audio=_make_audio_service(),
        repository=DummyRepository(),
        gauss_func=lambda mean, _sigma: mean,
    )

    tensiometer.start_wiggle()
    time.sleep(0.05)
    tensiometer.stop_wiggle()

    assert len(motion.moves) >= 1
    assert motion.moves[0] == (1.0, 2.0)


def test_focus_wiggle_compensates_x_side_a():
    focus_deltas = []
    motion = _make_motion_service(start_x=1000.0, start_y=2000.0)
    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=motion,
        audio=_make_audio_service(),
        repository=DummyRepository(),
        focus_wiggle=lambda delta: focus_deltas.append(delta),
    )

    tensiometer._apply_focus_wiggle_with_x_compensation(400.0)

    assert focus_deltas == [400]
    assert motion.moves == [(998.8, 2000.0)]


def test_focus_wiggle_compensates_x_side_b():
    focus_deltas = []
    motion = _make_motion_service(start_x=1000.0, start_y=2000.0)
    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="B",
        motion=motion,
        audio=_make_audio_service(),
        repository=DummyRepository(),
        focus_wiggle=lambda delta: focus_deltas.append(delta),
    )

    tensiometer._apply_focus_wiggle_with_x_compensation(400.0)

    assert focus_deltas == [400]
    assert motion.moves == [(1001.2, 2000.0)]


def test_focus_wiggle_without_callback_does_not_adjust_x():
    motion = _make_motion_service(start_x=1000.0, start_y=2000.0)
    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=motion,
        audio=_make_audio_service(),
        repository=DummyRepository(),
    )

    tensiometer._apply_focus_wiggle_with_x_compensation(400.0)

    assert motion.moves == []


def test_goto_collect_wire_data_applies_planned_focus_before_xy_move(monkeypatch):
    _patch_result_physics(monkeypatch)
    motion = _make_motion_service(start_x=10.0, start_y=2.0)
    focus_state = {"value": 4000}
    focus_deltas = []

    def _focus_wiggle(delta: int) -> None:
        focus_deltas.append(delta)
        focus_state["value"] += int(delta)

    result = TensionResult.from_measurement(
        apa_name="APA",
        layer="X",
        side="A",
        wire_number=1,
        frequency=80.0,
        confidence=0.95,
        x=11.0,
        y=2.0,
        focus_position=4200,
        time=datetime(2026, 3, 15, 12, 0, 0),
    )

    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=motion,
        audio=_make_audio_service(),
        repository=DummyRepository(),
        focus_wiggle=_focus_wiggle,
        focus_position_getter=lambda: focus_state["value"],
        focus_range_getter=lambda: (4000, 8000),
    )
    tensiometer._collect_samples = lambda **_kwargs: [result]
    tensiometer.repository.append_result = lambda _saved: None

    measured = tensiometer.goto_collect_wire_data(
        wire_number=1,
        wire_x=11.0,
        wire_y=2.0,
        focus_position=4200,
    )

    assert measured is result
    assert focus_deltas == [200]
    assert motion.moves == [(9.4, 2.0), (11.0, 2.0)]


def test_goto_collect_wire_data_resets_plc_and_retries_failed_measurement_move(monkeypatch):
    _patch_result_physics(monkeypatch)
    motion = _make_recovering_motion_service([False, True], start_x=10.0, start_y=2.0)
    result = TensionResult.from_measurement(
        apa_name="APA",
        layer="X",
        side="A",
        wire_number=1,
        frequency=80.0,
        confidence=0.95,
        x=11.0,
        y=2.0,
        focus_position=4200,
        time=datetime(2026, 3, 15, 12, 0, 0),
    )

    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=motion,
        audio=_make_audio_service(),
        repository=DummyRepository(),
    )
    tensiometer._collect_samples = lambda **_kwargs: [result]
    tensiometer.repository.append_result = lambda _saved: None

    measured = tensiometer.goto_collect_wire_data(
        wire_number=1,
        wire_x=11.0,
        wire_y=2.0,
    )

    assert measured is result
    assert motion.moves == [(11.0, 2.0), (11.0, 2.0)]
    assert motion.reset_calls["count"] == 4


def test_goto_collect_wire_data_records_profile_stage_timings(monkeypatch):
    _patch_result_physics(monkeypatch)
    motion = _make_motion_service(start_x=10.0, start_y=2.0)
    result = TensionResult.from_measurement(
        apa_name="APA",
        layer="X",
        side="A",
        wire_number=1,
        frequency=80.0,
        confidence=0.95,
        x=11.0,
        y=2.0,
        focus_position=4200,
        time=datetime(2026, 3, 15, 12, 0, 0),
    )
    times = iter([100.0 + 0.1 * index for index in range(20)])
    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=motion,
        audio=_make_audio_service(),
        repository=DummyRepository(),
        time_provider=lambda: next(times),
    )
    tensiometer._collect_samples = lambda **_kwargs: [result]
    tensiometer.repository.append_result = lambda _saved: None
    tensiometer.summary_refresh_callback = lambda _config: None
    tensiometer._start_batch_profile(workflow="list", requested_wires=[1])
    tensiometer._start_wire_profile("list", 1)

    measured = tensiometer.goto_collect_wire_data(
        wire_number=1,
        wire_x=11.0,
        wire_y=2.0,
    )

    profile = tensiometer._active_wire_profile

    assert measured is result
    assert profile is not None
    assert profile.stage_seconds["move_to_measurement_pose"] > 0.0
    assert profile.stage_seconds["collect_samples"] > 0.0
    assert profile.stage_seconds["append_result"] > 0.0
    assert profile.stage_seconds["summary_refresh"] > 0.0
    assert profile.stage_seconds["wire_total_wall"] > 0.0


def test_goto_collect_wire_data_invokes_wire_preview_for_uv(monkeypatch):
    _patch_result_physics(monkeypatch)
    monkeypatch.setattr(
        tensiometer_module,
        "length_lookup",
        lambda _layer, _wire_number, _zone, taped=False: 1.0,
    )
    motion = _make_motion_service(start_x=10.0, start_y=2.0)
    preview_calls = []
    result = TensionResult.from_measurement(
        apa_name="APA",
        layer="U",
        side="A",
        wire_number=1151,
        frequency=80.0,
        confidence=0.95,
        x=11.0,
        y=2.0,
        focus_position=4200,
        time=datetime(2026, 3, 15, 12, 0, 0),
    )
    tensiometer = Tensiometer(
        apa_name="APA",
        layer="U",
        side="A",
        motion=motion,
        audio=_make_audio_service(),
        repository=DummyRepository(),
        wire_preview_callback=lambda wire_number, wire_x, wire_y: preview_calls.append(
            (wire_number, wire_x, wire_y)
        ),
    )
    tensiometer._collect_samples = lambda **_kwargs: [result]
    tensiometer.repository.append_result = lambda _saved: None
    tensiometer.summary_refresh_callback = lambda _config: None

    measured = tensiometer.goto_collect_wire_data(
        wire_number=1151,
        wire_x=11.0,
        wire_y=2.0,
    )

    assert measured is result
    assert preview_calls == [(1151, 11.0, 2.0)]


def test_collect_samples_resets_plc_and_retries_optimizer_move(monkeypatch):
    motion = _make_recovering_motion_service([False, True], start_x=1000.0, start_y=2000.0)
    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=motion,
        audio=_make_audio_service(),
        repository=DummyRepository(),
        measuring_duration=10.0,
        gauss_func=lambda mean, sigma: mean + sigma,
        focus_range_getter=lambda: (0, 10000),
    )
    tensiometer.strum_func = lambda: None

    monkeypatch.setattr(tensiometer_module, "acquire_audio", lambda **_kwargs: None)
    monkeypatch.setattr(
        tensiometer_module,
        "wire_equation",
        lambda *, length, frequency=None: {
            "frequency": 80.0 if frequency is None else float(frequency),
            "tension": 6.0,
        },
    )

    stop_checks = {"count": 0}

    def _check_stop(_event, _msg=""):
        stop_checks["count"] += 1
        return stop_checks["count"] >= 2

    monkeypatch.setattr(tensiometer_module, "check_stop_event", _check_stop)

    tensiometer._collect_samples(
        wire_number=1,
        length=1.0,
        start_time=time.time(),
        wire_y=2000.0,
        wire_x=1000.0,
    )

    assert len(motion.moves) == 2
    assert motion.moves[0][0] == pytest.approx(1010.0, abs=0.02)
    assert motion.moves[0][1] == pytest.approx(2000.1, abs=0.02)
    assert motion.moves[1][0] == pytest.approx(1010.0, abs=0.02)
    assert motion.moves[1][1] == pytest.approx(2000.1, abs=0.02)
    assert motion.reset_calls["count"] == 1


def test_optimizer_focus_step_uses_coupled_x_shift(monkeypatch):
    motion = _make_motion_service(start_x=1000.0, start_y=2000.0)
    focus_deltas = []
    focus_state = {"value": 0}

    def _focus_wiggle(delta: int) -> None:
        focus_deltas.append(delta)
        focus_state["value"] += int(delta)

    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=motion,
        audio=_make_audio_service(),
        repository=DummyRepository(),
        measuring_duration=10.0,
        focus_wiggle=_focus_wiggle,
        focus_position_getter=lambda: focus_state["value"],
        focus_range_getter=lambda: (-8000, 8000),
        gauss_func=lambda mean, sigma: mean + sigma,
    )
    tensiometer.strum_func = lambda: None

    monkeypatch.setattr(tensiometer_module, "acquire_audio", lambda **_kwargs: None)
    monkeypatch.setattr(
        tensiometer_module,
        "wire_equation",
        lambda *, length, frequency=None: {
            "frequency": 80.0 if frequency is None else float(frequency),
            "tension": 6.0,
        },
    )

    stop_checks = {"count": 0}

    def _check_stop(_event, _msg=""):
        stop_checks["count"] += 1
        return stop_checks["count"] >= 3

    monkeypatch.setattr(tensiometer_module, "check_stop_event", _check_stop)

    tensiometer._collect_samples(
        wire_number=1,
        length=1.0,
        start_time=time.time(),
        wire_y=2000.0,
        wire_x=1000.0,
    )

    assert focus_deltas == [100]
    assert motion.moves[0][0] == pytest.approx(999.7113, abs=0.02)
    assert motion.moves[0][1] == pytest.approx(2000.0, abs=0.02)
    assert motion.moves[1][0] == pytest.approx(1009.7113, abs=0.02)
    assert motion.moves[1][1] == pytest.approx(2000.1, abs=0.02)


def test_optimizer_manual_focus_moves_along_wire_diagonal(monkeypatch):
    motion = _make_motion_service(start_x=1000.0, start_y=2000.0)
    tensiometer = Tensiometer(
        apa_name="APA",
        layer="U",
        side="B",
        motion=motion,
        audio=_make_audio_service(),
        repository=DummyRepository(),
        measuring_duration=10.0,
        use_manual_focus=True,
        gauss_func=lambda mean, sigma: mean + sigma,
    )
    tensiometer.strum_func = lambda: None

    monkeypatch.setattr(tensiometer_module, "acquire_audio", lambda **_kwargs: None)
    monkeypatch.setattr(
        tensiometer_module,
        "wire_equation",
        lambda *, length, frequency=None: {
            "frequency": 80.0 if frequency is None else float(frequency),
            "tension": 6.0,
        },
    )

    stop_checks = {"count": 0}

    def _check_stop(_event, _msg=""):
        stop_checks["count"] += 1
        return stop_checks["count"] >= 2

    monkeypatch.setattr(tensiometer_module, "check_stop_event", _check_stop)

    tensiometer._collect_samples(
        wire_number=1,
        length=1.0,
        start_time=time.time(),
        wire_y=2000.0,
        wire_x=1000.0,
    )

    assert motion.moves[0][0] == pytest.approx(1010.0, abs=0.02)
    assert motion.moves[0][1] == pytest.approx(1992.8125, abs=0.02)


def test_optimizer_reposition_does_not_wait_for_move_completion(monkeypatch):
    motion = _make_motion_service(start_x=1000.0, start_y=2000.0)
    move_kwargs: list[dict[str, object]] = []

    def goto_xy(x: float, y: float, **kwargs) -> bool:
        move_kwargs.append(dict(kwargs))
        motion.moves.append((x, y))
        motion.state["x"] = float(x)
        motion.state["y"] = float(y)
        return True

    motion.goto_xy = goto_xy

    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=motion,
        audio=_make_audio_service(),
        repository=DummyRepository(),
        measuring_duration=10.0,
        gauss_func=lambda mean, sigma: mean + sigma,
    )
    tensiometer.strum_func = lambda: None

    monkeypatch.setattr(tensiometer_module, "acquire_audio", lambda **_kwargs: None)
    monkeypatch.setattr(
        tensiometer_module,
        "wire_equation",
        lambda *, length, frequency=None: {
            "frequency": 80.0 if frequency is None else float(frequency),
            "tension": 6.0,
        },
    )

    stop_checks = {"count": 0}

    def _check_stop(_event, _msg=""):
        stop_checks["count"] += 1
        return stop_checks["count"] >= 2

    monkeypatch.setattr(tensiometer_module, "check_stop_event", _check_stop)

    tensiometer._collect_samples(
        wire_number=1,
        length=1.0,
        start_time=time.time(),
        wire_y=2000.0,
        wire_x=1000.0,
    )

    assert move_kwargs == [{"wait_for_completion": False}]
