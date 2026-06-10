import sys
import types
from typing import Any, cast

from _gui_test_support import (
    REPO_SRC,
    install_dune_tension_pkg_shell,
    load_module_from_path,
)


MODULE_PATH = REPO_SRC / "gui" / "_layout.py"


def _load_layout_module(monkeypatch):
    tk_stub = cast(Any, types.ModuleType("tkinter"))
    tk_stub.Misc = object
    monkeypatch.setitem(sys.modules, "tkinter", tk_stub)

    install_dune_tension_pkg_shell(monkeypatch)

    live_plots = cast(Any, types.ModuleType("dune_tension.gui.live_plots"))
    live_plots.LIVE_SUMMARY_FIGSIZE = (7.8, 3.6)
    live_plots.LIVE_WAVEFORM_FIGSIZE = (7.2, 4.6)
    monkeypatch.setitem(sys.modules, "dune_tension.gui.live_plots", live_plots)

    return load_module_from_path(monkeypatch, "gui_layout_under_test", MODULE_PATH)


class _FakeRoot:
    def __init__(self, screen_width: int = 1920, screen_height: int = 1080) -> None:
        self.columnconfigure_calls = []
        self.minsize_args = None
        self.update_calls = 0
        self.screen_width = screen_width
        self.screen_height = screen_height

    def update_idletasks(self) -> None:
        self.update_calls += 1

    def columnconfigure(self, index, **kwargs) -> None:
        self.columnconfigure_calls.append((index, kwargs))

    def minsize(self, width, height) -> None:
        self.minsize_args = (width, height)

    def winfo_screenwidth(self) -> int:
        return self.screen_width

    def winfo_screenheight(self) -> int:
        return self.screen_height


class _FakeFrame:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height

    def winfo_reqwidth(self) -> int:
        return self.width

    def winfo_reqheight(self) -> int:
        return self.height


class _FakeFixedRoot(_FakeRoot):
    def __init__(self, screen_width: int = 1920, screen_height: int = 1080) -> None:
        super().__init__(screen_width, screen_height)
        self.geometry_args: list[str] = []
        self.resizable_args: list[tuple[bool, bool]] = []
        self.full_update_calls = 0

    def geometry(self, spec: str) -> None:
        self.geometry_args.append(spec)

    def resizable(self, width: bool, height: bool) -> None:
        self.resizable_args.append((width, height))

    def update(self) -> None:
        self.full_update_calls += 1


class _FakeAllocatedFrame:
    def __init__(
        self,
        allocated_width: int,
        allocated_height: int,
        req_width: int = 0,
        req_height: int = 0,
    ) -> None:
        self.allocated_width = allocated_width
        self.allocated_height = allocated_height
        self.req_width = req_width
        self.req_height = req_height
        self.configure_kwargs: dict[str, int] = {}
        self.grid_propagate_args: list[bool] = []

    def winfo_width(self) -> int:
        return self.allocated_width

    def winfo_height(self) -> int:
        return self.allocated_height

    def winfo_reqwidth(self) -> int:
        return self.req_width

    def winfo_reqheight(self) -> int:
        return self.req_height

    def configure(self, **kwargs) -> None:
        self.configure_kwargs.update(kwargs)

    def grid_propagate(self, flag: bool) -> None:
        self.grid_propagate_args.append(flag)


def test_configure_root_minimum_size_reserves_space_for_all_columns(monkeypatch):
    layout = _load_layout_module(monkeypatch)
    root = _FakeRoot()
    main_frame = _FakeFrame(420, 700)
    plots_frame = _FakeFrame(760, 680)
    log_frame = _FakeFrame(400, 600)

    layout.configure_root_minimum_size(root, main_frame, plots_frame, log_frame)

    assert root.update_calls == 1
    assert root.columnconfigure_calls == [
        (0, {"weight": 0, "minsize": 420}),
        (1, {"weight": 1, "minsize": 780}),
        (2, {"weight": 1, "minsize": 400}),
    ]
    # 420 (main) + 780 (plots) + 400 (log) + 40 (padding) = 1640
    # max(700, 680, 600) + 20 = 720
    assert root.minsize_args == (1640, 720)


def test_configure_root_minimum_size_clamps_to_screen(monkeypatch):
    layout = _load_layout_module(monkeypatch)
    root = _FakeRoot(screen_width=1100, screen_height=680)
    main_frame = _FakeFrame(420, 700)
    plots_frame = _FakeFrame(760, 680)
    log_frame = _FakeFrame(400, 600)

    layout.configure_root_minimum_size(root, main_frame, plots_frame, log_frame)

    # 420 + 780 + 400 = 1600. screen=1100.
    # overflow = 1600 - (1100 - 30) = 1600 - 1070 = 530
    # log_reduction = min(530, 400 - 100) = 300. log_width = 100. overflow = 230
    # plots_reduction = min(230, 780 - 200) = 230. plots_width = 550. overflow = 0
    # main_width = 420.
    assert root.columnconfigure_calls == [
        (0, {"weight": 0, "minsize": 420}),
        (1, {"weight": 1, "minsize": 550}),
        (2, {"weight": 1, "minsize": 100}),
    ]
    assert root.minsize_args == (1100, 680)


def test_configure_fixed_fullscreen_pins_geometry_and_disables_resizing(monkeypatch):
    layout = _load_layout_module(monkeypatch)
    root = _FakeFixedRoot(screen_width=1920, screen_height=1080)

    layout.configure_fixed_fullscreen(root)

    assert root.geometry_args == ["1920x1080+0+0"]
    assert root.resizable_args == [(False, False)]


def test_configure_fixed_fullscreen_skips_without_screen_dimensions(monkeypatch):
    layout = _load_layout_module(monkeypatch)
    root = _FakeFixedRoot(screen_width=0, screen_height=1080)

    layout.configure_fixed_fullscreen(root)

    assert root.geometry_args == []
    assert root.resizable_args == []


def test_freeze_frame_sizes_locks_allocated_sizes(monkeypatch):
    layout = _load_layout_module(monkeypatch)
    root = _FakeFixedRoot()
    summary = _FakeAllocatedFrame(640, 480)
    waveform = _FakeAllocatedFrame(640, 320)

    layout.freeze_frame_sizes(root, summary, waveform)

    assert root.full_update_calls == 1
    assert summary.configure_kwargs == {"width": 640, "height": 480}
    assert waveform.configure_kwargs == {"width": 640, "height": 320}
    assert summary.grid_propagate_args == [False]
    assert waveform.grid_propagate_args == [False]


def test_freeze_frame_sizes_falls_back_to_requested_size(monkeypatch):
    layout = _load_layout_module(monkeypatch)
    root = _FakeFixedRoot()
    unmapped = _FakeAllocatedFrame(1, 1, req_width=600, req_height=500)

    layout.freeze_frame_sizes(root, unmapped)

    assert unmapped.configure_kwargs == {"width": 600, "height": 500}
    assert unmapped.grid_propagate_args == [False]
