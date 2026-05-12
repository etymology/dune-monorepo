"""Shared serial-port discovery helpers for dune_tension hardware."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any

try:
    from serial.tools import list_ports as _serial_list_ports
except Exception:  # pragma: no cover - exercised by dummy-controller test stubs
    _serial_list_ports = None


def build_candidate_ports(
    *,
    preferred_port: str | None = None,
    name_substrings: Sequence[str] = (),
    vendor_id: str | None = None,
    product_id: str | None = None,
    prefer_interface_number: int | None = None,
) -> list[str]:
    """Return serial ports ordered from most to least likely to match.

    ``prefer_interface_number`` lets callers tie-break between multiple CDC
    interfaces of a composite USB device (e.g. the Pololu Maestro exposes
    interface 0 as a command port and interface 2 as a TTL passthrough — both
    look identical in description metadata).
    """

    normalized_names = tuple(_normalize(term) for term in name_substrings if term)
    normalized_vendor = _normalize_hex(vendor_id)
    normalized_product = _normalize_hex(product_id)

    candidates: list[str] = []
    matched_by_name: list[tuple[int, int, str]] = []
    matched_by_ids: list[tuple[int, int, str]] = []
    fallback_ports: list[str] = []

    if preferred_port:
        candidates.append(preferred_port)

    for index, port in enumerate(_iter_comports()):
        device = getattr(port, "device", None)
        if not device:
            continue

        metadata = _port_metadata_blob(port)
        name_match = any(term in metadata for term in normalized_names)
        id_match = _matches_usb_ids(
            port, vendor_id=normalized_vendor, product_id=normalized_product
        )

        interface_priority = 0
        if prefer_interface_number is not None:
            interface_number = _port_interface_number(port)
            interface_priority = (
                0 if interface_number == prefer_interface_number else 1
            )

        if name_match:
            matched_by_name.append((interface_priority, index, device))
        elif id_match:
            matched_by_ids.append((interface_priority, index, device))
        else:
            fallback_ports.append(device)

    matched_by_name.sort()
    matched_by_ids.sort()

    for bucket in (
        [device for _, _, device in matched_by_name],
        [device for _, _, device in matched_by_ids],
        fallback_ports,
    ):
        for candidate in bucket:
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _port_interface_number(port: object) -> int | None:
    """Extract the USB interface number from a port, or ``None`` if unknown."""

    # On Linux, ``port.location`` is typically ``"3-7.4:1.0"`` where the digit
    # after the last ``.`` is the interface number.
    for source in (
        getattr(port, "location", None),
        getattr(port, "hwid", None),
    ):
        if not source:
            continue
        match = re.search(r":\d+\.(\d+)\b", str(source))
        if match:
            return int(match.group(1))
    return None


def _iter_comports() -> Iterable[Any]:
    if _serial_list_ports is None:
        return ()
    return _serial_list_ports.comports()


def is_serial_permission_error(exc: Exception) -> bool:
    """Return whether *exc* represents a serial-port permission failure."""

    errno = getattr(exc, "errno", None)
    if errno == 13:
        return True

    context = (
        str(exc),
        str(getattr(exc, "__cause__", "")),
        str(getattr(exc, "__context__", "")),
    )
    return any("permission denied" in value.lower() for value in context if value)


def _port_metadata_blob(port: object) -> str:
    values: list[str] = []
    for field_name in (
        "device",
        "name",
        "description",
        "product",
        "manufacturer",
        "interface",
        "hwid",
        "serial_number",
        "location",
    ):
        value = getattr(port, field_name, None)
        if value:
            values.append(str(value))
    return _normalize(" ".join(values))


def _matches_usb_ids(
    port: object, *, vendor_id: str | None, product_id: str | None
) -> bool:
    if vendor_id is None and product_id is None:
        return False

    port_vid = _normalize_hex(getattr(port, "vid", None))
    port_pid = _normalize_hex(getattr(port, "pid", None))
    if vendor_id is not None and port_vid != vendor_id:
        return False
    if product_id is not None and port_pid != product_id:
        return False
    if port_vid is not None or port_pid is not None:
        return True

    hwid = _normalize(getattr(port, "hwid", ""))
    if vendor_id is not None and vendor_id.lower() not in hwid:
        return False
    if product_id is not None and product_id.lower() not in hwid:
        return False
    return bool(hwid)


def _normalize(value: object) -> str:
    return str(value).strip().lower()


def _normalize_hex(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, int):
        return f"{value:04x}"

    normalized = _normalize(value)
    if normalized.startswith("0x"):
        normalized = normalized[2:]
    normalized = normalized.replace("-", "").replace(":", "")
    return normalized or None
