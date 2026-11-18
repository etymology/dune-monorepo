"""Web proxy widgets replacing Tkinter widgets for the web GUI."""

from __future__ import annotations

import threading
from typing import Any


class WebVar:
    """Proxy for tk.StringVar / tk.BooleanVar backed by a shared state dict."""

    def __init__(self, state: dict, key: str, default: Any) -> None:
        self._state = state
        self._key = key
        state[key] = default

    def get(self) -> Any:
        return self._state[self._key]

    def set(self, value: Any) -> None:
        self._state[self._key] = value

    def trace_add(self, mode: str, callback: Any) -> None:
        pass


class WebEntry:
    """Proxy for tk.Entry backed by a shared state dict."""

    def __init__(self, state: dict, key: str, default: str = "") -> None:
        self._state = state
        self._key = key
        state[key] = str(default)

    def get(self) -> str:
        return str(self._state.get(self._key, ""))

    def delete(self, first: Any, last: Any = None) -> None:
        self._state[self._key] = ""

    def insert(self, index: Any, value: Any) -> None:
        self._state[self._key] = str(value)

    def configure(self, **kwargs: Any) -> None:
        pass


class WebScale:
    """Proxy for tk.Scale backed by a shared state dict."""

    def __init__(
        self, state: dict, key: str, default: Any, from_: int, to: int
    ) -> None:
        self._state = state
        self._key = key
        self._from = from_
        self._to = to
        self._command: Any = None
        state[key] = default

    def get(self) -> Any:
        return self._state[self._key]

    def set(self, value: Any) -> None:
        self._state[self._key] = value
        if self._command is not None:
            try:
                self._command(value)
            except Exception:
                pass

    def cget(self, option: str) -> Any:
        if option == "length":
            return 200
        return None

    def __getitem__(self, key: str) -> Any:
        if key == "from":
            return self._from
        if key == "to":
            return self._to
        return None

    def configure(self, **kwargs: Any) -> None:
        if "command" in kwargs:
            self._command = kwargs["command"]


class _WebMenuProxy:
    """Proxy for the inner tk.Menu of an OptionMenu."""

    def __init__(self, state: dict, options_key: str, var: WebVar) -> None:
        self._state = state
        self._options_key = options_key
        self._var = var
        state.setdefault(options_key, [])

    def delete(self, first: Any, last: Any = None) -> None:
        self._state[self._options_key] = []

    def add_command(self, label: str = "", command: Any = None, **kwargs: Any) -> None:
        value = self._extract_value(command, label)
        options: list = self._state.get(self._options_key, [])
        options.append({"label": label, "value": value})
        self._state[self._options_key] = options

    @staticmethod
    def _extract_value(command: Any, label: str) -> str:
        if command is None:
            return label
        # tk._setit stores value as name-mangled _setit__value
        v = getattr(command, "_setit__value", None)
        if isinstance(v, str):
            return v
        # fallback: look for a string cell in a function closure
        closure = getattr(command, "__closure__", None)
        if closure:
            for cell in closure:
                try:
                    contents = cell.cell_contents
                    if isinstance(contents, str):
                        return contents
                except ValueError:
                    continue
        return label


class WebOptionMenu:
    """Proxy for tk.OptionMenu."""

    def __init__(self, var: WebVar, state: dict, options_key: str) -> None:
        self._var = var
        self._menu = _WebMenuProxy(state, options_key, var)

    def __getitem__(self, key: str) -> Any:
        if key == "menu":
            return self._menu
        return None

    def configure(self, **kwargs: Any) -> None:
        pass


class WebWidget:
    """Stub for Tk frames, buttons, labels, canvas, etc."""

    def configure(self, **kwargs: Any) -> None:
        pass

    def grid(self, **kwargs: Any) -> None:
        pass

    def grid_remove(self) -> None:
        pass

    def grid_forget(self) -> None:
        pass

    def winfo_width(self) -> int:
        return 600

    def winfo_height(self) -> int:
        return 400

    def get_tk_widget(self) -> "WebWidget":
        return self


class _LaserOffsetFrameWidget(WebWidget):
    """WebWidget that tracks visibility in the shared state."""

    def __init__(self, state: dict) -> None:
        self._state = state
        state["laser_offset_frame_visible"] = False

    def grid(self, **kwargs: Any) -> None:
        self._state["laser_offset_frame_visible"] = True

    def grid_remove(self) -> None:
        self._state["laser_offset_frame_visible"] = False

    def grid_forget(self) -> None:
        self._state["laser_offset_frame_visible"] = False


class WebRoot:
    """Proxy for tk.Misc root window; .after dispatches via threading.Timer."""

    def after(self, delay_ms: int, func: Any = None) -> Any:
        if func is None:
            return None
        if delay_ms == 0:
            try:
                func()
            except Exception:
                pass
            return None
        timer = threading.Timer(delay_ms / 1000.0, _safe_call, args=(func,))
        timer.daemon = True
        timer.start()
        return timer

    def after_cancel(self, timer: Any) -> None:
        if timer is not None and hasattr(timer, "cancel"):
            try:
                timer.cancel()
            except Exception:
                pass


def _safe_call(func: Any) -> None:
    try:
        func()
    except Exception:
        pass


def build_web_widgets(state: dict) -> Any:
    """Construct GUIWidgets proxies backed by the shared state dict."""
    from dune_tension import apa_naming
    from dune_tension.config import MEASUREMENT_WIGGLE_CONFIG
    from dune_tension.gui.context import GUIWidgets

    apa_location_var = WebVar(state, "apa_location", "US")
    apa_number_var = WebVar(state, "apa_number", apa_naming.NUMBER_LABELS[0])
    measurement_mode_var = WebVar(state, "measurement_mode", "legacy")
    layer_var = WebVar(state, "layer", "X")
    side_var = WebVar(state, "side", "A")
    flipped_var = WebVar(state, "flipped", False)
    a_taped_var = WebVar(state, "a_taped", False)
    b_taped_var = WebVar(state, "b_taped", False)

    entry_wire = WebEntry(state, "wire_number", "")
    entry_wire_list = WebEntry(state, "wire_list", "")
    entry_confidence = WebEntry(state, "confidence_threshold", "0.5")
    confidence_source_var = WebVar(state, "confidence_source", "Neural Net")
    use_harmonic_comb_trigger_var = WebVar(state, "use_harmonic_comb_trigger", True)
    entry_record_duration = WebEntry(state, "record_duration", "1")
    entry_measuring_duration = WebEntry(state, "measuring_duration", "10")
    entry_wiggle_y_sigma = WebEntry(
        state, "wiggle_y_sigma_mm", str(MEASUREMENT_WIGGLE_CONFIG.y_sigma_mm)
    )
    sweeping_wiggle_var = WebVar(state, "sweeping_wiggle", False)
    entry_sweeping_wiggle_span_mm = WebEntry(state, "sweeping_wiggle_span_mm", "1.0")
    entry_focus_wiggle_sigma = WebEntry(
        state,
        "focus_wiggle_sigma",
        str(MEASUREMENT_WIGGLE_CONFIG.focus_sigma_quarter_us),
    )
    use_manual_focus_var = WebVar(state, "use_manual_focus", False)
    skip_measured_var = WebVar(state, "skip_measured", False)
    entry_wire_zone = WebEntry(state, "wire_zone", "")
    skip_measured_zone_var = WebVar(state, "skip_measured_zone", False)
    entry_clear_range = WebEntry(state, "clear_range", "")
    entry_condition = WebEntry(state, "condition", "")
    entry_legacy_tension_condition = WebEntry(state, "legacy_tension_condition", "")
    entry_times_sigma = WebEntry(state, "times_sigma", "2.0")
    entry_set_tension = WebEntry(state, "set_tension", "")
    focus_slider = WebScale(state, "focus_target", 4000, from_=4000, to=8000)
    disable_x_compensation_var = WebVar(state, "disable_x_compensation", False)
    entry_xy = WebEntry(state, "xy_text", "")

    stream_segment_var = WebVar(state, "stream_segment", "Idle")
    stream_comb_var = WebVar(state, "stream_comb", "0.00")
    stream_focus_var = WebVar(state, "stream_focus", "--")
    stream_pitch_backlog_var = WebVar(state, "stream_pitch_backlog", "0")
    stream_rescue_queue_var = WebVar(state, "stream_rescue_queue", "0")

    laser_offset_frame = _LaserOffsetFrameWidget(state)
    laser_offset_pin_var = WebVar(state, "laser_offset_pin", "")
    laser_offset_pin_menu = WebOptionMenu(
        laser_offset_pin_var, state, "_laser_offset_pin_options"
    )
    laser_offset_readout_var = WebVar(state, "laser_offset_readout", "Side A: not set")

    btn_seek_pin = WebWidget()
    btn_move_laser_to_pin = WebWidget()
    btn_capture_laser_offset = WebWidget()

    return GUIWidgets(
        apa_location_var=apa_location_var,  # type: ignore[arg-type]
        apa_number_var=apa_number_var,  # type: ignore[arg-type]
        measurement_mode_var=measurement_mode_var,  # type: ignore[arg-type]
        layer_var=layer_var,  # type: ignore[arg-type]
        side_var=side_var,  # type: ignore[arg-type]
        flipped_var=flipped_var,  # type: ignore[arg-type]
        a_taped_var=a_taped_var,  # type: ignore[arg-type]
        b_taped_var=b_taped_var,  # type: ignore[arg-type]
        entry_wire=entry_wire,  # type: ignore[arg-type]
        entry_wire_list=entry_wire_list,  # type: ignore[arg-type]
        entry_confidence=entry_confidence,  # type: ignore[arg-type]
        confidence_source_var=confidence_source_var,  # type: ignore[arg-type]
        use_harmonic_comb_trigger_var=use_harmonic_comb_trigger_var,  # type: ignore[arg-type]
        entry_record_duration=entry_record_duration,  # type: ignore[arg-type]
        entry_measuring_duration=entry_measuring_duration,  # type: ignore[arg-type]
        entry_wiggle_y_sigma=entry_wiggle_y_sigma,  # type: ignore[arg-type]
        sweeping_wiggle_var=sweeping_wiggle_var,  # type: ignore[arg-type]
        entry_sweeping_wiggle_span_mm=entry_sweeping_wiggle_span_mm,  # type: ignore[arg-type]
        entry_focus_wiggle_sigma=entry_focus_wiggle_sigma,  # type: ignore[arg-type]
        use_manual_focus_var=use_manual_focus_var,  # type: ignore[arg-type]
        skip_measured_var=skip_measured_var,  # type: ignore[arg-type]
        entry_wire_zone=entry_wire_zone,  # type: ignore[arg-type]
        skip_measured_zone_var=skip_measured_zone_var,  # type: ignore[arg-type]
        entry_clear_range=entry_clear_range,  # type: ignore[arg-type]
        entry_condition=entry_condition,  # type: ignore[arg-type]
        entry_legacy_tension_condition=entry_legacy_tension_condition,  # type: ignore[arg-type]
        entry_times_sigma=entry_times_sigma,  # type: ignore[arg-type]
        entry_set_tension=entry_set_tension,  # type: ignore[arg-type]
        focus_slider=focus_slider,  # type: ignore[arg-type]
        disable_x_compensation_var=disable_x_compensation_var,  # type: ignore[arg-type]
        entry_xy=entry_xy,  # type: ignore[arg-type]
        stream_segment_var=stream_segment_var,  # type: ignore[arg-type]
        stream_comb_var=stream_comb_var,  # type: ignore[arg-type]
        stream_focus_var=stream_focus_var,  # type: ignore[arg-type]
        stream_pitch_backlog_var=stream_pitch_backlog_var,  # type: ignore[arg-type]
        stream_rescue_queue_var=stream_rescue_queue_var,  # type: ignore[arg-type]
        laser_offset_frame=laser_offset_frame,
        laser_offset_pin_var=laser_offset_pin_var,  # type: ignore[arg-type]
        laser_offset_pin_menu=laser_offset_pin_menu,
        laser_offset_readout_var=laser_offset_readout_var,  # type: ignore[arg-type]
        btn_seek_pin=btn_seek_pin,
        btn_move_laser_to_pin=btn_move_laser_to_pin,
        btn_capture_laser_offset=btn_capture_laser_offset,
    )
