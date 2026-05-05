import threading
from typing import Optional
from dune_tension.tensiometer import Tensiometer


class GlobalState:
    """Thread-safe state manager for hardware orchestration and telemetry."""

    def __init__(self):
        self._lock = threading.Lock()
        self.tensiometer: Optional[Tensiometer] = None
        self.active_wire: Optional[int] = None
        self.progress: float = 0.0
        self.is_running: bool = False
        self.logs: list[str] = []
        self.position: dict[str, float] = {"x": 0.0, "y": 0.0, "focus": 0.0}
        self.last_audio_analysis: Optional[dict] = None
        self.all_measurements: list[dict] = []

    def update_tensiometer(self, tensiometer: Tensiometer):
        with self._lock:
            self.tensiometer = tensiometer

    def clear_measurements(self):
        with self._lock:
            self.all_measurements = []

    def add_measurement(self, result_dict: dict):
        with self._lock:
            self.all_measurements.append(result_dict)

    def set_running(self, status: bool):
        with self._lock:
            self.is_running = status

    def update_position(self, x: float, y: float, focus: float):
        with self._lock:
            self.position = {"x": x, "y": y, "focus": focus}

    def update_audio(self, analysis: dict):
        with self._lock:
            self.last_audio_analysis = analysis

    def append_log(self, message: str):
        with self._lock:
            self.logs.append(message)
            if len(self.logs) > 1000:
                self.logs.pop(0)


state = GlobalState()
