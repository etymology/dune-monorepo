from pathlib import Path
import sys

import numpy as np
import pytest

_TEST_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_TEST_DIR.parents[1] / "src"))
sys.path.insert(0, str(_TEST_DIR))

from dune_tension.tensiometer import Tensiometer
from dune_tension.tension_calculation import wire_equation
from spectrum_analysis import pesto_analysis

from test_tensiometer import (
    DummyRepository,
    _make_audio_service,
    _make_motion_service,
)


def _pesto_available() -> bool:
    """Return True if any PESTO backend can plausibly run inference."""
    try:
        from dune_tension import rust_audio

        if rust_audio.should_try_rust_pesto():
            return True
    except Exception:
        pass
    try:
        from spectrum_analysis import pesto_onnx  # noqa: F401

        if pesto_analysis._check_onnx_backend_available():
            return True
    except Exception:
        pass
    return pesto_analysis._ensure_runtime_dependencies()


@pytest.mark.integration
@pytest.mark.skipif(not _pesto_available(), reason="No PESTO backend available")
def test_tensiometer_recovers_synthetic_sine_frequency_and_tension():
    f0 = 100.0
    length_m = 1.0
    sample_rate = 44100
    duration_s = 0.5

    t = np.arange(int(sample_rate * duration_s), dtype=np.float32) / sample_rate
    audio = (0.3 * np.sin(2.0 * np.pi * f0 * t)).astype(np.float32)

    tensiometer = Tensiometer(
        apa_name="APA",
        layer="X",
        side="A",
        motion=_make_motion_service(),
        audio=_make_audio_service(sample_rate=sample_rate),
        repository=DummyRepository(),
    )

    analysis, frequency, confidence = tensiometer._estimate_sample_pitch(
        audio, expected_frequency=f0
    )

    assert analysis is not None
    assert np.isfinite(frequency)
    assert frequency == pytest.approx(f0, rel=0.0025)
    assert confidence > 0.0

    expected_tension = wire_equation(length=length_m, frequency=f0)["tension"]
    measured_tension = wire_equation(length=length_m, frequency=frequency)["tension"]
    assert measured_tension == pytest.approx(expected_tension, rel=0.005)
