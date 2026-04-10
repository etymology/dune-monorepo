"""Transport layer for communicating with the PLC via the dune_winder desktop PC."""

import logging
import os
import time
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)

DEFAULT_DESKTOP_SERVER_URL = "http://192.168.137.1:8080"

HTTP_CONNECT_TIMEOUT = 5
HTTP_READ_TIMEOUT = 5.0
POLL_INTERVAL = 0.1
READY_STATE = "StopMode"
_UNSUPPORTED_MOTION_TAGS = frozenset(
    {
        "STATE",
        "MOVE_TYPE",
        "X_POSITION",
        "Y_POSITION",
        "XY_SPEED",
    }
)

_SESSION: Any = None


def get_desktop_server_url() -> str:
    """Return the configured desktop PC server URL."""
    return os.getenv("DESKTOP_SERVER_URL", DEFAULT_DESKTOP_SERVER_URL).strip()


def _get_session() -> Any:
    global _SESSION
    if _SESSION is None and hasattr(requests, "Session"):
        _SESSION = requests.Session()
    return _SESSION


def _post_command(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """POST a command to the desktop PC's dune_winder API."""
    url = f"{get_desktop_server_url()}/api/v2/command"
    payload = {"name": name, "args": args}
    session = _get_session()
    try:
        if session is not None:
            resp = session.post(
                url, json=payload, timeout=(HTTP_CONNECT_TIMEOUT, HTTP_READ_TIMEOUT)
            )
        else:
            resp = requests.post(
                url, json=payload, timeout=(HTTP_CONNECT_TIMEOUT, HTTP_READ_TIMEOUT)
            )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        return {
            "ok": False,
            "data": None,
            "error": {"code": "REQUEST_FAILED", "message": str(exc)},
        }


def desktop_get_xy() -> tuple[float, float] | None:
    """Return (x, y) position in mm from the desktop PC, or None on error."""
    result = _post_command("process.get_ui_snapshot", {})
    if not result.get("ok"):
        LOGGER.warning("desktop_get_xy failed: %s", result.get("error"))
        return None
    try:
        axes = result["data"]["axes"]
        return float(axes["x"]["position"]), float(axes["y"]["position"])
    except (KeyError, TypeError) as exc:
        LOGGER.warning("desktop_get_xy parse error: %s", exc)
        return None


def desktop_is_ready() -> bool:
    """Return True if the desktop PC's control state machine is in StopMode."""
    result = _post_command("process.get_control_state_name", {})
    return bool(result.get("ok")) and result.get("data") == READY_STATE


def desktop_acknowledge_error() -> bool:
    """Mirror dune_winder's Reset PLC button via process.acknowledge_error."""
    result = _post_command("process.acknowledge_error", {})
    if not result.get("ok"):
        LOGGER.warning("desktop_acknowledge_error failed: %s", result.get("error"))
        return False
    return True


def desktop_seek_xy(
    x: float,
    y: float,
    speed: float,
    move_timeout: float,
    idle_timeout: float = 20.0,
    wait_for_completion: bool = True,
) -> bool:
    """Wait for ready, issue manual_seek_xy, then optionally wait for StopMode."""
    def _wait_for_ready(timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if desktop_is_ready():
                return True
            time.sleep(POLL_INTERVAL)
        return False

    if not _wait_for_ready(idle_timeout):
        LOGGER.warning(
            "desktop_seek_xy: timed out waiting for ready state before move to %s,%s",
            x,
            y,
        )
        if not desktop_acknowledge_error():
            return False
        if not _wait_for_ready(idle_timeout):
            LOGGER.warning(
                "desktop_seek_xy: PLC reset did not restore ready state before move to %s,%s",
                x,
                y,
            )
            return False

    result = _post_command(
        "process.manual_seek_xy", {"x": x, "y": y, "velocity": speed}
    )
    # manualSeekXY returns isError: data=True means rejected, data=False means accepted
    if not result.get("ok") or result.get("data") is True:
        LOGGER.warning(
            "desktop_seek_xy rejected for %s,%s: %s",
            x,
            y,
            result.get("error") or result.get("data"),
        )
        return False

    if not wait_for_completion:
        return True

    deadline = time.monotonic() + move_timeout
    while time.monotonic() < deadline:
        if desktop_is_ready():
            return True
        time.sleep(POLL_INTERVAL)

    LOGGER.warning("desktop_seek_xy timed out waiting for move completion")
    desktop_acknowledge_error()
    return False


def desktop_read_tag(tag_name: str) -> Any:
    """Read a PLC tag through the desktop PC's dune_winder API."""
    result = _post_command("plc.read_tag", {"tag": tag_name})
    if not result.get("ok"):
        error = result.get("error", {})
        message = error.get("message", str(error)) if isinstance(error, dict) else str(error)
        return {"error": f"desktop_read_tag({tag_name}): {message}"}
    return result.get("data")


def desktop_write_tag(tag_name: str, value: Any) -> dict[str, Any]:
    """Write a PLC tag through the desktop PC's dune_winder API."""
    normalized_tag = str(tag_name).strip().upper()
    if normalized_tag in _UNSUPPORTED_MOTION_TAGS:
        return {
            "error": (
                f"desktop_write_tag({tag_name}): low-level motion tag writes are "
                "not supported in desktop mode; use process.manual_seek_xy instead"
            )
        }

    result = _post_command("plc.write_tag", {"tag": tag_name, "value": value})
    if not result.get("ok"):
        error = result.get("error", {})
        message = error.get("message", str(error)) if isinstance(error, dict) else str(error)
        return {"error": f"desktop_write_tag({tag_name}): {message}"}
    return result.get("data", {"tag": tag_name, "value": value})


def desktop_is_server_active() -> bool:
    """Return True if the desktop PC's dune_winder server is reachable."""
    url = get_desktop_server_url()
    session = _get_session()
    try:
        if session is not None:
            resp = session.get(url, timeout=(HTTP_CONNECT_TIMEOUT, 0.75))
        else:
            resp = requests.get(url, timeout=(HTTP_CONNECT_TIMEOUT, 0.75))
        return 200 <= resp.status_code < 500
    except Exception as exc:
        LOGGER.warning("desktop_is_server_active error: %s", exc)
        return False
