"""Derive paste-dialect (.rll) routine text from studio_copy.rllscrap.

The checked-in ``pasteable.rll`` files are retired (the ACD-export +
rung_lang pipeline replaced the paste loop), but the ``plc_ladder``
parser/runtime and their tests consume the paste dialect. This helper
produces that text in memory, exactly like ``LadderSimulatedPLC`` does.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dune_winder.convert_plc_rllscrap import resolve_timer_counter_args
from dune_winder.paths import PLC_ROOT
from dune_winder.plc_ladder import load_plc_metadata
from dune_winder.plc_rung_transform import transform_text

__all__ = ["PLC_ROOT", "iter_paste_routine_dirs", "paste_text"]


@lru_cache(maxsize=1)
def _metadata():
    return load_plc_metadata(PLC_ROOT)


def paste_text(program: str, routine_dir: str) -> str:
    """Paste-dialect text for ``winder/plc/<program>/<routine_dir>/``."""
    path = PLC_ROOT / program / routine_dir / "studio_copy.rllscrap"
    transformed = transform_text(path.read_text(encoding="utf-8"))
    return resolve_timer_counter_args(transformed, _metadata(), program)


def iter_paste_routine_dirs() -> list[Path]:
    return sorted(p.parent for p in PLC_ROOT.rglob("studio_copy.rllscrap"))
