from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import math
import sys
import time
import types

import pytest

import dune_tension.results as results_module
import dune_tension.tensiometer as tensiometer_module
from dune_tension.results import TensionResult
from dune_tension.tensiometer import Tensiometer


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


def _make_audio_service(sample_rate: int = 8000):
    return types.SimpleNamespace(
        samplerate=sample_rate,
        noise_threshold=0.0,
        record_audio=lambda *_args, **_kwargs: ([], 0.0),
    )


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

    assert events[:2] == ["quiet", "audio"]


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
    planner_calls = []
    monkeypatch.setattr(
        tensiometer_module,
        "plan_measurement_triplets",
        lambda **kwargs: planner_calls.append(kwargs) or [(2, 2.0, 0.0), (1, 1.0, 0.0)],
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
    )
    tensiometer.goto_xy_func = lambda *_args, **_kwargs: pytest.fail(
        "measure_auto should use the shared planner output directly"
    )
    tensiometer.goto_collect_wire_data = lambda **kwargs: collected.append(kwargs)

    tensiometer.measure_auto()

    assert len(planner_calls) == 1
    assert planner_calls[0]["wire_list"] == [1, 2]
    assert eta_updates == ["0:00:10", "0:00:00"]
    assert collected == [
        {"wire_number": 2, "wire_x": 2.0, "wire_y": 0.0},
        {"wire_number": 1, "wire_x": 1.0, "wire_y": 0.0},
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


def test_optimizer_focus_step_uses_coupled_x_shift(monkeypatch):
    motion = _make_motion_service(start_x=1000.0, start_y=2000.0)
    focus_deltas = []

    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=motion,
        audio=_make_audio_service(),
        repository=DummyRepository(),
        measuring_duration=10.0,
        focus_wiggle=lambda delta: focus_deltas.append(delta),
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

    assert focus_deltas == [100, 85]
    assert motion.moves[0][0] == pytest.approx(999.7113, abs=0.02)
    assert motion.moves[0][1] == pytest.approx(2000.1, abs=0.02)
