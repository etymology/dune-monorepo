from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

from dune_winder.uv_head_target import UvHeadTargetError, UvHeadTargetRequest, UvHeadTargetResult, Point2D, Point3D, TransferBounds


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
  def __init__(self, *args, **kwargs):
    pass

  def grid(self, *args, **kwargs):
    return None

  def columnconfigure(self, *args, **kwargs):
    return None

  def rowconfigure(self, *args, **kwargs):
    return None


def _load_gui_module(monkeypatch):
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


def _sample_result() -> UvHeadTargetResult:
  request = UvHeadTargetRequest("U", "B1201", "B2002", "B2003", "front")
  return UvHeadTargetResult(
    request=request,
    orientation_token="RT",
    anchor_pin_point=Point3D(0.0, 0.0, 1.0),
    near_pin_point=Point3D(10.0, 5.0, 1.0),
    target_pair_pin_point=Point3D(12.0, 7.0, 1.0),
    midpoint_point=Point3D(11.0, 6.0, 1.0),
    transfer_point=Point2D(15.0, 8.0),
    effective_anchor_point=Point3D(1.0, 0.5, 1.0),
    final_head_point=Point3D(18.0, 9.0, 145.0),
    final_wire_point=Point3D(17.5, 8.8, 140.0),
    transfer_bounds=TransferBounds(left=-5.0, top=20.0, right=25.0, bottom=-10.0),
    pin_radius=1.2,
    head_arm_length=100.0,
    head_roller_radius=10.0,
    head_roller_gap=2.0,
    validation_error=None,
  )


def test_build_request_from_form(monkeypatch):
  gui = _load_gui_module(monkeypatch)
  form = gui._FormState(
    layer_var=_FakeVar(value="V"),
    head_z_mode_var=_FakeVar(value="back"),
    anchor_pin_var=_FakeVar(value="F1"),
    near_pin_var=_FakeVar(value="F2"),
    target_pair_pin_var=_FakeVar(value="F3"),
    error_var=_FakeVar(value=""),
    summary_var=_FakeVar(value=""),
    canvas=_FakeCanvas(),
  )

  request = gui.build_request_from_form(form)

  assert request == UvHeadTargetRequest("V", "F1", "F2", "F3", "back")


def test_calculate_and_render_updates_summary_and_canvas(monkeypatch):
  gui = _load_gui_module(monkeypatch)
  result = _sample_result()
  seen = []
  form = gui._FormState(
    layer_var=_FakeVar(value="U"),
    head_z_mode_var=_FakeVar(value="front"),
    anchor_pin_var=_FakeVar(value="B1201"),
    near_pin_var=_FakeVar(value="B2002"),
    target_pair_pin_var=_FakeVar(value="B2003"),
    error_var=_FakeVar(value=""),
    summary_var=_FakeVar(value=""),
    canvas=_FakeCanvas(),
  )

  def compute_fn(request):
    seen.append(request)
    return result

  returned = gui.calculate_and_render(form, compute_fn=compute_fn)

  assert returned == result
  assert seen == [UvHeadTargetRequest("U", "B1201", "B2002", "B2003", "front")]
  assert "Orientation: RT" in form.summary_var.get()
  assert form.error_var.get() == ""
  assert any(call[0] == "create_line" for call in form.canvas.calls)


def test_calculate_and_render_surfaces_validation_error(monkeypatch):
  gui = _load_gui_module(monkeypatch)
  form = gui._FormState(
    layer_var=_FakeVar(value="U"),
    head_z_mode_var=_FakeVar(value="front"),
    anchor_pin_var=_FakeVar(value="bad"),
    near_pin_var=_FakeVar(value="B2"),
    target_pair_pin_var=_FakeVar(value="B3"),
    error_var=_FakeVar(value=""),
    summary_var=_FakeVar(value="summary"),
    canvas=_FakeCanvas(),
  )

  returned = gui.calculate_and_render(
    form,
    compute_fn=lambda _request: (_ for _ in ()).throw(UvHeadTargetError("bad pins")),
  )

  assert returned is None
  assert form.error_var.get() == "bad pins"
  assert form.summary_var.get() == ""
  assert form.canvas.calls[0][0] == "delete"
