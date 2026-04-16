"""Analysis helpers for replaying and inspecting winding geometry."""

from importlib import import_module

__all__ = [
  "AVAILABLE_SITE_IDS",
  "AVAILABLE_SENSITIVITY_IDS",
  "build_uv_tangency_report",
  "compare_uv_tangency_reports",
]


def __getattr__(name):
  if name not in __all__:
    raise AttributeError(name)

  module = import_module(".uv_tangency_analysis", __name__)
  return getattr(module, name)
