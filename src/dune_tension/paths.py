from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "dune_tension"
DATA_ROOT = PACKAGE_ROOT / "data"
AUDIO_ROOT = PACKAGE_ROOT / "audio"


def package_path(*parts: str) -> Path:
    return PACKAGE_ROOT.joinpath(*parts)


def data_path(*parts: str) -> Path:
    return DATA_ROOT.joinpath(*parts)


def audio_path(*parts: str) -> Path:
    return AUDIO_ROOT.joinpath(*parts)


def tension_data_db_path() -> Path:
    return data_path("tension_data", "tension_data.db")


def streaming_runs_root() -> Path:
    return data_path("streaming_runs")
