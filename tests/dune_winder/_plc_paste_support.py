"""Derive paste-dialect (.rll) routine text from the exported L5X.

The checked-in ``pasteable.rll`` files are retired (the ACD-export +
rung_lang pipeline replaced the paste loop), but the ``plc_ladder``
parser/runtime and their tests consume the paste dialect. This helper
produces that text in memory from each routine's ``*_Routine_RLL.L5X``
(the source of truth), exactly like ``LadderSimulatedPLC`` does.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dune_winder.paths import PLC_ROOT
from dune_winder.plc_l5x import routine_paren_text
from dune_winder.plc_ladder import load_plc_metadata
from dune_winder.plc_rung_transform import resolve_timer_counter_args, transform_text

__all__ = ["PLC_ROOT", "iter_paste_routine_dirs", "l5x_path", "paste_text"]


@lru_cache(maxsize=1)
def _metadata():
    return load_plc_metadata(PLC_ROOT)


def l5x_path(program: str, routine_dir: str) -> Path:
    """The exported L5X for ``winder/plc/<program>/<routine_dir>/``.

    The ``main/`` directory holds the program's main routine, whose L5X is
    named for its real routine name (usually, but not always, ``main``).
    """
    if routine_dir == "main":
        routine = _metadata().programs[program].main_routine_name or "main"
    else:
        routine = routine_dir
    return PLC_ROOT / program / f"{routine}_Routine_RLL.L5X"


def paste_text(program: str, routine_dir: str) -> str:
    """Paste-dialect text for ``winder/plc/<program>/<routine_dir>/``."""
    transformed = transform_text(routine_paren_text(l5x_path(program, routine_dir)))
    return resolve_timer_counter_args(transformed, _metadata(), program)


def iter_paste_routine_dirs() -> list[Path]:
    return sorted(p.parent for p in PLC_ROOT.rglob("*.rung"))
