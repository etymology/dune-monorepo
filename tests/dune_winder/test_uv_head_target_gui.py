from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

from dune_winder.uv_head_target import (
    LineEquation,
    Point2D,
    Point3D,
    RectBounds,
    UvHeadTargetError,
    UvTangentViewRequest,
    UvTangentViewResult,
)


MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dune_winder"
    / "uv_head_target_gui.py"
)


class _FakeVar:
    def __init__(self, master=None, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _FakeCanvas:
    def __init__(self, *args, **kwargs):
        self.calls = []

    def delete(self, *args):
        self.calls.append(("delete", args))

    def create_oval(self, *args, **kwargs):
        self.calls.append(("create_oval", args, kwargs))

    def create_text(self, *args, **kwargs):
        self.calls.append(("create_text", args, kwargs))

    def create_rectangle(self, *args, **kwargs):
        self.calls.append(("create_rectangle", args, kwargs))

    def create_line(self, *args, **kwargs):
        self.calls.append(("create_line", args, kwargs))

    def winfo_width(self):
        return 900

    def winfo_height(self):
        return 700

    def grid(self, *args, **kwargs):
        return None


class _FakeWidget:
    instances: list[_FakeWidget] = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        _FakeWidget.instances.append(self)

    def grid(self, *args, **kwargs):
        return None

    def columnconfigure(self, *args, **kwargs):
        return None

    def rowconfigure(self, *args, **kwargs):
        return None


def _load_gui_module(monkeypatch):
    _FakeWidget.instances = []
    tk_stub = types.ModuleType("tkinter")
    tk_stub.Misc = object
    tk_stub.StringVar = _FakeVar
    tk_stub.Canvas = _FakeCanvas
    tk_stub.Tk = object
    tk_stub.Frame = _FakeWidget
    tk_stub.Label = _FakeWidget
    tk_stub.OptionMenu = _FakeWidget
    tk_stub.Entry = _FakeWidget
    tk_stub.Button = _FakeWidget
    monkeypatch.setitem(sys.modules, "tkinter", tk_stub)

    module_name = "uv_head_target_gui_under_test"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


def _sample_result() -> UvTangentViewResult:
    request = UvTangentViewRequest("U", "B1201", "A2001")
    return UvTangentViewResult(
        request=request,
        pin_a_point=Point3D(0.0, 0.0, 145.0),
        pin_b_point=Point3D(10.0, 5.0, 145.0),
        tangent_point_a=Point2D(1.0, 3.0),
        tangent_point_b=Point2D(11.0, 8.0),
        line_equation=LineEquation(slope=0.5, intercept=2.5, is_vertical=False),
        clipped_segment_start=Point2D(-5.0, 0.0),
        clipped_segment_end=Point2D(25.0, 15.0),
        outbound_intercept=Point2D(25.0, 15.0),
        transfer_bounds=RectBounds(left=-5.0, top=20.0, right=25.0, bottom=-10.0),
        apa_bounds=RectBounds(left=-2.0, top=18.0, right=22.0, bottom=-3.0),
        apa_pin_points=(
            Point2D(-2.0, -3.0),
            Point2D(0.0, 0.0),
            Point2D(4.0, 2.5),
            Point2D(10.0, 5.0),
            Point2D(14.0, 7.5),
            Point2D(22.0, 18.0),
        ),
        apa_pin_points_by_name=(
            ("B1200", Point2D(-2.0, -3.0)),
            ("B1201", Point2D(0.0, 0.0)),
            ("B1202", Point2D(4.0, 2.5)),
            ("A2000", Point2D(10.0, 5.0)),
            ("A2001", Point2D(14.0, 7.5)),
            ("A2002", Point2D(22.0, 18.0)),
        ),
        pin_radius=1.2,
        tangent_selection_rule="Prefer higher outbound intercept Y, then higher X.",
        anchor_side="B",
        anchor_face="bottom",
        anchor_tangent_sides=("plus", "minus"),
        wrapped_side="A",
        wrapped_face="foot",
        wrap_sides=("plus", "plus"),
        runtime_orientation_token="RB",
        runtime_tangent_point=Point2D(2.0, 1.0),
        runtime_target_point=Point2D(20.0, 12.0),
        runtime_line_equation=LineEquation(
            slope=0.611111, intercept=-0.222222, is_vertical=False
        ),
        runtime_clipped_segment_start=Point2D(-5.0, -3.277777),
        runtime_clipped_segment_end=Point2D(25.0, 15.055555),
        runtime_outbound_intercept=Point2D(25.0, 15.055555),
        arm_head_center=Point2D(18.0, 11.5),
        arm_left_endpoint=Point2D(12.0, 11.5),
        arm_right_endpoint=Point2D(24.0, 11.5),
        roller_centers=(
            Point2D(12.0, 10.0),
            Point2D(12.0, 13.0),
            Point2D(24.0, 10.0),
            Point2D(24.0, 13.0),
        ),
        arm_corrected_outbound_point=Point2D(23.0, 14.0),
        arm_corrected_head_center=Point2D(23.0, 14.0),
        arm_corrected_selected_roller_index=3,
        arm_corrected_quadrant="NE",
        arm_corrected_available=True,
        arm_corrected_error=None,
        head_arm_length=6.0,
        head_roller_radius=1.0,
        head_roller_gap=1.0,
        matches_runtime_line=False,
        validation_error=None,
    )


def _sample_alternating_result() -> UvTangentViewResult:
    request = UvTangentViewRequest("U", "B1201", "A1201")
    return UvTangentViewResult(
        request=request,
        pin_a_point=Point3D(7127.6, 44.6, 270.0),
        pin_b_point=Point3D(7127.6, 2343.6, 145.0),
        tangent_point_a=Point2D(0.0, 44.0),
        tangent_point_b=Point2D(417.7, 2344.0),
        line_equation=LineEquation(slope=5.505631, intercept=44.0, is_vertical=False),
        clipped_segment_start=Point2D(0.0, 5014.5),
        clipped_segment_end=Point2D(417.7, -2676.1),
        outbound_intercept=Point2D(417.7, -2676.1),
        transfer_bounds=RectBounds(left=-5.0, top=20.0, right=25.0, bottom=-10.0),
        apa_bounds=RectBounds(left=-2.0, top=18.0, right=22.0, bottom=-3.0),
        apa_pin_points=(Point2D(-2.0, -3.0), Point2D(0.0, 0.0)),
        apa_pin_points_by_name=(
            ("B1201", Point2D(0.0, 0.0)),
            ("A1201", Point2D(1.0, 1.0)),
        ),
        pin_radius=1.2,
        tangent_selection_rule="Project alternating-side wrap in yz and extend to z planes.",
        anchor_side="B",
        anchor_face="foot",
        anchor_tangent_sides=("minus", "minus"),
        wrapped_side="A",
        wrapped_face="foot",
        wrap_sides=("plus", "plus"),
        runtime_orientation_token="LT",
        runtime_tangent_point=Point2D(2.0, 1.0),
        runtime_target_point=Point2D(20.0, 12.0),
        runtime_line_equation=LineEquation(
            slope=0.611111, intercept=-0.222222, is_vertical=False
        ),
        runtime_clipped_segment_start=Point2D(-5.0, -3.277777),
        runtime_clipped_segment_end=Point2D(25.0, 15.055555),
        runtime_outbound_intercept=Point2D(25.0, 15.055555),
        arm_corrected_outbound_point=None,
        arm_corrected_head_center=None,
        arm_corrected_selected_roller_index=None,
        arm_corrected_quadrant=None,
        arm_corrected_available=False,
        arm_corrected_error=None,
        alternating_plane="yz",
        alternating_face="foot",
        alternating_anchor_center=Point2D(270.0, 44.6),
        alternating_wrapped_center=Point2D(145.0, 2343.6),
        alternating_anchor_segment_start=Point2D(270.0, 43.4),
        alternating_anchor_segment_end=Point2D(270.0, 45.8),
        alternating_wrapped_segment_start=Point2D(145.0, 2342.4),
        alternating_wrapped_segment_end=Point2D(145.0, 2344.8),
        alternating_anchor_contact=Point2D(270.0, 43.4),
        alternating_wrapped_contact=Point2D(145.0, 2344.8),
        alternating_wrap_line_start=Point2D(0.0, 5014.5),
        alternating_wrap_line_end=Point2D(417.7, -2676.1),
        alternating_g109_projection=Point2D(270.0, 44.6),
        alternating_g103_projection=Point2D(210.0, 1000.0),
        alternating_g108_projection=None,
        z_retracted=0.0,
        z_extended=417.7,
        matches_runtime_line=False,
        validation_error=None,
    )


def test_build_request_from_form(monkeypatch):
    gui = _load_gui_module(monkeypatch)
    form = gui._FormState(
        mode_var=_FakeVar(value="Pins"),
        layer_var=_FakeVar(value="V"),
        command_var=_FakeVar(value=""),
        pin_a_var=_FakeVar(value="A1"),
        pin_b_var=_FakeVar(value="A2"),
        wrap_var=_FakeVar(value="1"),
        segment_var=_FakeVar(value="1"),
        derived_pins_var=_FakeVar(value=""),
        error_var=_FakeVar(value=""),
        summary_var=_FakeVar(value=""),
        canvas=_FakeCanvas(),
        pin_a_zoom_canvas=_FakeCanvas(),
        pin_b_zoom_canvas=_FakeCanvas(),
        outbound_zoom_canvas=_FakeCanvas(),
    )

    request = gui.build_request_from_form(form)

    assert request == UvTangentViewRequest("V", "A1", "A2")


def test_calculate_and_render_updates_summary_and_canvas(monkeypatch):
    gui = _load_gui_module(monkeypatch)
    result = _sample_result()
    seen = []
    form = gui._FormState(
        mode_var=_FakeVar(value="Pins"),
        layer_var=_FakeVar(value="U"),
        command_var=_FakeVar(value=""),
        pin_a_var=_FakeVar(value="B1201"),
        pin_b_var=_FakeVar(value="A2001"),
        wrap_var=_FakeVar(value="1"),
        segment_var=_FakeVar(value="1"),
        derived_pins_var=_FakeVar(value=""),
        error_var=_FakeVar(value=""),
        summary_var=_FakeVar(value=""),
        canvas=_FakeCanvas(),
        pin_a_zoom_canvas=_FakeCanvas(),
        pin_b_zoom_canvas=_FakeCanvas(),
        outbound_zoom_canvas=_FakeCanvas(),
    )

    def compute_fn(request):
        seen.append(request)
        return result

    returned = gui.calculate_and_render(form, compute_fn=compute_fn)

    assert returned == result
    assert seen == [UvTangentViewRequest("U", "B1201", "A2001")]
    assert "Line: y = 0.500000x + 2.500" in form.summary_var.get()
    assert "Outbound transfer intercept: (25.000, 15.000)" in form.summary_var.get()
    assert "Anchor pin B1201" in form.summary_var.get()
    assert "Target pin A2001" in form.summary_var.get()
    assert "Wrapped side/face: A / foot" in form.summary_var.get()
    assert "Wrapped tangent sides: x=plus, y=plus" in form.summary_var.get()
    assert "Runtime orientation: RB" in form.summary_var.get()
    assert "Runtime comparison: different lines" in form.summary_var.get()
    assert "G108 target: (20.000, 12.000)" in form.summary_var.get()
    assert "Outbound minus G108 target: (5.000, 3.000)" in form.summary_var.get()
    assert "Arm-corrected outbound: (23.000, 14.000)" in form.summary_var.get()
    assert form.error_var.get() == ""
    assert any(call[0] == "create_line" for call in form.canvas.calls)
    assert any(call[0] == "create_rectangle" for call in form.canvas.calls)
    assert any(
        call[0] == "create_text" and call[2].get("text") == "g108 target"
        for call in form.canvas.calls
        if len(call) > 2
    )
    assert not any(
        call[0] == "create_text" and call[2].get("text") == form.summary_var.get()
        for call in form.canvas.calls
        if len(call) > 2
    )
    assert any(call[0] == "create_oval" for call in form.pin_a_zoom_canvas.calls)
    assert any(call[0] == "create_oval" for call in form.pin_b_zoom_canvas.calls)
    assert any(call[0] == "create_line" for call in form.pin_a_zoom_canvas.calls)
    assert any(call[0] == "create_line" for call in form.pin_b_zoom_canvas.calls)
    assert any(
        call[0] == "create_line" and call[1][0] > call[1][2]
        for call in form.pin_a_zoom_canvas.calls
        if len(call) > 1 and len(call[1]) >= 4
    )
    assert any(
        call[0] == "create_line" and call[1][0] > call[1][2]
        for call in form.pin_b_zoom_canvas.calls
        if len(call) > 1 and len(call[1]) >= 4
    )
    assert any(
        call[0] == "create_text" and call[2].get("text") == "+x"
        for call in form.pin_a_zoom_canvas.calls
        if len(call) > 2
    )
    assert any(
        call[0] == "create_text" and call[2].get("text") == "-x"
        for call in form.pin_a_zoom_canvas.calls
        if len(call) > 2
    )
    assert any(
        call[0] == "create_text" and call[2].get("text") == "+y"
        for call in form.pin_a_zoom_canvas.calls
        if len(call) > 2
    )
    assert any(
        call[0] == "create_text" and call[2].get("text") == "+x"
        for call in form.pin_b_zoom_canvas.calls
        if len(call) > 2
    )
    assert any(
        call[0] == "create_text" and call[2].get("text") == "-x"
        for call in form.pin_b_zoom_canvas.calls
        if len(call) > 2
    )
    assert any(
        call[0] == "create_text" and call[2].get("text") == "+y"
        for call in form.pin_b_zoom_canvas.calls
        if len(call) > 2
    )
    assert any(
        call[0] == "create_rectangle" and call[2].get("dash") == (4, 4)
        for call in form.outbound_zoom_canvas.calls
        if len(call) > 2
    )
    assert any(
        call[0] == "create_text" and "Outbound:" in call[2].get("text", "")
        for call in form.outbound_zoom_canvas.calls
        if len(call) > 2
    )
    assert any(
        call[0] == "create_text" and "Arm-corrected:" in call[2].get("text", "")
        for call in form.outbound_zoom_canvas.calls
        if len(call) > 2
    )
    assert any(
        call[0] == "create_text" and "G108 target:" in call[2].get("text", "")
        for call in form.outbound_zoom_canvas.calls
        if len(call) > 2
    )
    assert any(
        call[0] == "create_text" and "Outbound - G108:" in call[2].get("text", "")
        for call in form.outbound_zoom_canvas.calls
        if len(call) > 2
    )
    assert any(
        call[0] == "create_text" and call[2].get("text") == "used roller"
        for call in form.outbound_zoom_canvas.calls
        if len(call) > 2
    )
    assert any(
        call[0] == "create_text" and call[2].get("text") == "wire head"
        for call in form.outbound_zoom_canvas.calls
        if len(call) > 2
    )
    assert not any(
        call[0] == "create_text" and "touch" in call[2].get("text", "").lower()
        for call in form.pin_a_zoom_canvas.calls + form.pin_b_zoom_canvas.calls
        if len(call) > 2
    )
    assert (
        sum(1 for call in form.outbound_zoom_canvas.calls if call[0] == "create_oval")
        >= 6
    )
    assert (
        sum(1 for call in form.outbound_zoom_canvas.calls if call[0] == "create_line")
        >= 5
    )


def test_calculate_and_render_surfaces_validation_error(monkeypatch):
    gui = _load_gui_module(monkeypatch)
    form = gui._FormState(
        mode_var=_FakeVar(value="Pins"),
        layer_var=_FakeVar(value="U"),
        command_var=_FakeVar(value=""),
        pin_a_var=_FakeVar(value="bad"),
        pin_b_var=_FakeVar(value="B2"),
        wrap_var=_FakeVar(value="1"),
        segment_var=_FakeVar(value="1"),
        derived_pins_var=_FakeVar(value=""),
        error_var=_FakeVar(value=""),
        summary_var=_FakeVar(value="summary"),
        canvas=_FakeCanvas(),
        pin_a_zoom_canvas=_FakeCanvas(),
        pin_b_zoom_canvas=_FakeCanvas(),
        outbound_zoom_canvas=_FakeCanvas(),
    )

    returned = gui.calculate_and_render(
        form,
        compute_fn=lambda _request: (_ for _ in ()).throw(
            UvHeadTargetError("bad pins")
        ),
    )

    assert returned is None
    assert form.error_var.get() == "bad pins"
    assert form.summary_var.get() == ""
    assert form.canvas.calls[0][0] == "delete"
    assert form.pin_a_zoom_canvas.calls[0][0] == "delete"
    assert form.pin_b_zoom_canvas.calls[0][0] == "delete"
    assert form.outbound_zoom_canvas.calls[0][0] == "delete"


def test_segments_for_layer_tracks_full_wrap_sequence(monkeypatch):
    gui = _load_gui_module(monkeypatch)

    segments = gui._segments_for_layer("U")

    assert segments[0].anchor_pin == "B1201"
    assert segments[0].wrapped_pin == "B2001"
    assert segments[1].anchor_pin == "B2001"
    assert segments[1].wrapped_pin == "A801"
    assert segments[4].anchor_pin == "B401"
    assert segments[4].wrapped_pin == "B400"
    assert len([segment for segment in segments if segment.wrap_number == 1]) == 12


def test_segments_for_v_layer_track_full_wrap_sequence(monkeypatch):
    gui = _load_gui_module(monkeypatch)

    segments = gui._segments_for_layer("V")

    assert segments[0].anchor_pin == "B400"
    assert segments[0].wrapped_pin == "B1999"
    assert segments[1].anchor_pin == "B1999"
    assert segments[1].wrapped_pin == "A800"
    assert segments[4].anchor_pin == "B1200"
    assert segments[4].wrapped_pin == "B1199"
    assert segments[8].anchor_pin == "B2000"
    assert segments[8].wrapped_pin == "B399"
    assert len([segment for segment in segments if segment.wrap_number == 1]) == 12


def test_build_request_from_wrap_segment_includes_alternating_side_segments(
    monkeypatch,
):
    gui = _load_gui_module(monkeypatch)
    form = gui._FormState(
        mode_var=_FakeVar(value="Wrap/Segment"),
        layer_var=_FakeVar(value="U"),
        command_var=_FakeVar(value=""),
        pin_a_var=_FakeVar(value=""),
        pin_b_var=_FakeVar(value=""),
        wrap_var=_FakeVar(value="1"),
        segment_var=_FakeVar(value="2"),
        derived_pins_var=_FakeVar(value=""),
        error_var=_FakeVar(value=""),
        summary_var=_FakeVar(value=""),
        canvas=_FakeCanvas(),
        pin_a_zoom_canvas=_FakeCanvas(),
        pin_b_zoom_canvas=_FakeCanvas(),
        outbound_zoom_canvas=_FakeCanvas(),
    )

    request = gui.build_request_from_form(form)

    assert request == UvTangentViewRequest("U", "B2001", "A801", g103_adjacent_pin=None)


def test_build_request_from_wrap_segment_preserves_adjacent_pin_for_recipe_transfer(
    monkeypatch,
):
    gui = _load_gui_module(monkeypatch)
    form = gui._FormState(
        mode_var=_FakeVar(value="Wrap/Segment"),
        layer_var=_FakeVar(value="U"),
        command_var=_FakeVar(value=""),
        pin_a_var=_FakeVar(value=""),
        pin_b_var=_FakeVar(value=""),
        wrap_var=_FakeVar(value="1"),
        segment_var=_FakeVar(value="5"),
        derived_pins_var=_FakeVar(value=""),
        error_var=_FakeVar(value=""),
        summary_var=_FakeVar(value=""),
        canvas=_FakeCanvas(),
        pin_a_zoom_canvas=_FakeCanvas(),
        pin_b_zoom_canvas=_FakeCanvas(),
        outbound_zoom_canvas=_FakeCanvas(),
    )

    request = gui.build_request_from_form(form)

    assert request == UvTangentViewRequest(
        "U", "B401", "B400", g103_adjacent_pin="B399"
    )


def test_build_request_from_v_wrap_segment_includes_alternating_side_segments(
    monkeypatch,
):
    gui = _load_gui_module(monkeypatch)
    form = gui._FormState(
        mode_var=_FakeVar(value="Wrap/Segment"),
        layer_var=_FakeVar(value="V"),
        command_var=_FakeVar(value=""),
        pin_a_var=_FakeVar(value=""),
        pin_b_var=_FakeVar(value=""),
        wrap_var=_FakeVar(value="1"),
        segment_var=_FakeVar(value="2"),
        derived_pins_var=_FakeVar(value=""),
        error_var=_FakeVar(value=""),
        summary_var=_FakeVar(value=""),
        canvas=_FakeCanvas(),
        pin_a_zoom_canvas=_FakeCanvas(),
        pin_b_zoom_canvas=_FakeCanvas(),
        outbound_zoom_canvas=_FakeCanvas(),
    )

    request = gui.build_request_from_form(form)

    assert request == UvTangentViewRequest("V", "B1999", "A800", g103_adjacent_pin=None)


def test_build_request_from_v_wrap_segment_preserves_adjacent_pin_for_recipe_transfer(
    monkeypatch,
):
    gui = _load_gui_module(monkeypatch)
    form = gui._FormState(
        mode_var=_FakeVar(value="Wrap/Segment"),
        layer_var=_FakeVar(value="V"),
        command_var=_FakeVar(value=""),
        pin_a_var=_FakeVar(value=""),
        pin_b_var=_FakeVar(value=""),
        wrap_var=_FakeVar(value="1"),
        segment_var=_FakeVar(value="5"),
        derived_pins_var=_FakeVar(value=""),
        error_var=_FakeVar(value=""),
        summary_var=_FakeVar(value=""),
        canvas=_FakeCanvas(),
        pin_a_zoom_canvas=_FakeCanvas(),
        pin_b_zoom_canvas=_FakeCanvas(),
        outbound_zoom_canvas=_FakeCanvas(),
    )

    request = gui.build_request_from_form(form)

    assert request == UvTangentViewRequest(
        "V", "B1200", "B1199", g103_adjacent_pin="B1198"
    )


def test_build_request_from_wrap_segment_preserves_adjacent_pin_on_wrap_5_and_11(
    monkeypatch,
):
    gui = _load_gui_module(monkeypatch)
    form_5 = gui._FormState(
        mode_var=_FakeVar(value="Wrap/Segment"),
        layer_var=_FakeVar(value="U"),
        command_var=_FakeVar(value=""),
        pin_a_var=_FakeVar(value=""),
        pin_b_var=_FakeVar(value=""),
        wrap_var=_FakeVar(value="5"),
        segment_var=_FakeVar(value="5"),
        derived_pins_var=_FakeVar(value=""),
        error_var=_FakeVar(value=""),
        summary_var=_FakeVar(value=""),
        canvas=_FakeCanvas(),
        pin_a_zoom_canvas=_FakeCanvas(),
        pin_b_zoom_canvas=_FakeCanvas(),
        outbound_zoom_canvas=_FakeCanvas(),
    )
    form_11 = gui._FormState(
        mode_var=_FakeVar(value="Wrap/Segment"),
        layer_var=_FakeVar(value="U"),
        command_var=_FakeVar(value=""),
        pin_a_var=_FakeVar(value=""),
        pin_b_var=_FakeVar(value=""),
        wrap_var=_FakeVar(value="11"),
        segment_var=_FakeVar(value="5"),
        derived_pins_var=_FakeVar(value=""),
        error_var=_FakeVar(value=""),
        summary_var=_FakeVar(value=""),
        canvas=_FakeCanvas(),
        pin_a_zoom_canvas=_FakeCanvas(),
        pin_b_zoom_canvas=_FakeCanvas(),
        outbound_zoom_canvas=_FakeCanvas(),
    )

    assert gui.build_request_from_form(form_5) == UvTangentViewRequest(
        "U", "B405", "B396", g103_adjacent_pin="B395"
    )
    assert gui.build_request_from_form(form_11) == UvTangentViewRequest(
        "U", "B411", "B390", g103_adjacent_pin="B389"
    )


def test_outbound_zoom_draws_used_roller_and_wire_head(monkeypatch):
    gui = _load_gui_module(monkeypatch)
    result = _sample_result()
    canvas = _FakeCanvas()

    gui._draw_outbound_zoom(canvas, result)

    assert any(
        call[0] == "create_text" and call[2].get("text") == "used roller"
        for call in canvas.calls
        if len(call) > 2
    )
    assert any(
        call[0] == "create_text" and call[2].get("text") == "wire head"
        for call in canvas.calls
        if len(call) > 2
    )


def test_calculate_and_render_draws_alternating_side_view(monkeypatch):
    gui = _load_gui_module(monkeypatch)
    result = _sample_alternating_result()
    form = gui._FormState(
        mode_var=_FakeVar(value="Pins"),
        layer_var=_FakeVar(value="U"),
        command_var=_FakeVar(value=""),
        pin_a_var=_FakeVar(value="B1201"),
        pin_b_var=_FakeVar(value="A1201"),
        wrap_var=_FakeVar(value="1"),
        segment_var=_FakeVar(value="1"),
        derived_pins_var=_FakeVar(value=""),
        error_var=_FakeVar(value=""),
        summary_var=_FakeVar(value=""),
        canvas=_FakeCanvas(),
        pin_a_zoom_canvas=_FakeCanvas(),
        pin_b_zoom_canvas=_FakeCanvas(),
        outbound_zoom_canvas=_FakeCanvas(),
    )

    returned = gui.calculate_and_render(form, compute_fn=lambda _request: result)

    assert returned == result
    assert "View plane: yz" in form.summary_var.get()
    assert "Machine zRetracted/zExtended: 0.000 / 417.700" in form.summary_var.get()
    assert any(call[0] == "create_line" for call in form.canvas.calls)
    assert any(
        call[0] == "create_text" and "alternating-side view" in call[2].get("text", "")
        for call in form.canvas.calls
        if len(call) > 2
    )
    assert any(
        call[0] == "create_text" and "See main canvas" in call[2].get("text", "")
        for call in form.pin_a_zoom_canvas.calls
        if len(call) > 2
    )
