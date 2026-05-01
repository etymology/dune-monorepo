import unittest
from unittest.mock import MagicMock
import numpy as np
from dataclasses import dataclass
import dune_tension_core


@dataclass
class MockConfig:
    apa_name: str = "APA1"
    layer: str = "U"
    side: str = "A"
    dx: float = 0.5
    dy: float = 0.1
    wire_min: int = 1
    wire_max: int = 1151
    flipped: bool = False
    samples_per_wire: int = 1
    confidence_threshold: float = 0.7
    confidence_source: str = "neural_net"
    save_audio: bool = False
    spoof: bool = True
    plot_audio: bool = False
    record_duration: float = 0.5
    measuring_duration: float = 0.1
    data_path: str = "test.db"


class TestRustSurface(unittest.TestCase):
    def setUp(self):
        self.config = MockConfig()
        self.motion_service = MagicMock()
        self.motion_service.reset_plc = MagicMock()

        self.repository = MagicMock()
        self.repository.run_scope.return_value.__enter__.return_value = self.repository

        self.audio_service = MagicMock()
        self.audio_service.samplerate = 44100
        self.audio_service.noise_threshold = 0.01

        def mock_pesto(audio, rate, expected):
            class Result:
                frequency = expected
                confidence = 0.9

            return Result()

        self.pesto_func = mock_pesto
        self.strum_func = MagicMock()

    def test_tensiometer_initialization(self):
        t = dune_tension_core.Tensiometer(
            config=self.config,
            motion_service=self.motion_service,
            goto_xy_func=lambda x, y: True,
            get_current_xy_position=lambda: (0.0, 0.0),
            focus_wiggle_func=lambda x: None,
            focus_position_getter=lambda: 5000,
            focus_range_getter=lambda: (4000, 8000),
            repository=self.repository,
            audio_service=self.audio_service,
            strum_func=self.strum_func,
            pesto_func=self.pesto_func,
            harmonic_comb_config=MagicMock(),
        )
        self.assertIsNotNone(t)

    def test_refine_position(self):
        t = dune_tension_core.Tensiometer()
        # Test basic refinement logic
        x, y = t.refine_position(1500.0, 500.0, 0.5, 0.1)
        self.assertIsInstance(x, float)
        self.assertIsInstance(y, float)

    def test_zone_lookup(self):
        t = dune_tension_core.Tensiometer()
        # Test zone lookup for a known X position
        zone = t.zone_lookup(100.0)
        self.assertIsInstance(zone, int)


if __name__ == "__main__":
    unittest.main()
