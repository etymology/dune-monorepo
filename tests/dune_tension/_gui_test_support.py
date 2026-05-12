"""Shared helpers for GUI tests that load modules in isolation.

The GUI modules under `dune_tension.gui` import `tkinter` and a variety of
sibling packages at module top-level. Tests load each module via
`importlib.spec_from_file_location` against a stripped-down `dune_tension`
package shell so that real imports (and Tk) don't run. These helpers wrap the
shared boilerplate; per-test stubs (tkinter attrs, sibling modules) stay in
the test file because they vary by module under test.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any, cast


REPO_SRC = Path(__file__).resolve().parents[2] / "src" / "dune_tension"


def install_dune_tension_pkg_shell(monkeypatch) -> tuple[Any, Any]:
    """Install empty `dune_tension` and `dune_tension.gui` packages."""
    dune_pkg = cast(Any, types.ModuleType("dune_tension"))
    dune_pkg.__path__ = []
    gui_pkg = cast(Any, types.ModuleType("dune_tension.gui"))
    gui_pkg.__path__ = []
    monkeypatch.setitem(sys.modules, "dune_tension", dune_pkg)
    monkeypatch.setitem(sys.modules, "dune_tension.gui", gui_pkg)
    return dune_pkg, gui_pkg


def load_module_from_path(monkeypatch, module_name: str, source_path: Path) -> Any:
    """Load a module from `source_path` under `module_name` and register it."""
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module
