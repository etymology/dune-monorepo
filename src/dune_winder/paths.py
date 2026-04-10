from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "dune_winder"
PACKAGE_ROOT = REPO_ROOT / "dune_winder"
WEB_ROOT = PACKAGE_ROOT / "web"
PLC_ROOT = PACKAGE_ROOT / "plc"
MONOROUTINE_PLC_ROOT = PACKAGE_ROOT / "plc_monoroutine"
CONFIGURATION_PATH = PACKAGE_ROOT / "configuration.toml"
CONTROL_VERSION_PATH = PACKAGE_ROOT / "version.xml"
UI_VERSION_PATH = WEB_ROOT / "version.xml"


def project_path(*parts: str) -> Path:
  return PACKAGE_ROOT.joinpath(*parts)


def web_path(*parts: str) -> Path:
  return WEB_ROOT.joinpath(*parts)


def plc_path(*parts: str) -> Path:
  return PLC_ROOT.joinpath(*parts)
