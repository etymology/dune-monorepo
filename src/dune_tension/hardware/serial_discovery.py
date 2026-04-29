"""Shared serial-port discovery helpers for dune_tension hardware."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from serial.tools import list_ports


def build_candidate_ports(
    *,
    preferred_port: str | None = None,
    name_substrings: Sequence[str] = (),
    vendor_id: str | None = None,
    product_id: str | None = None,
) -> list[str]:
    """Return serial ports ordered from most to least likely to match."""

    normalized_names = tuple(_normalize(term) for term in name_substrings if term)
    normalized_vendor = _normalize_hex(vendor_id)
    normalized_product = _normalize_hex(product_id)

    candidates: list[str] = []
    matched_by_name: list[str] = []
    matched_by_ids: list[str] = []
    fallback_ports: list[str] = []

    if preferred_port:
        candidates.append(preferred_port)

    for port in list_ports.comports():
        device = getattr(port, "device", None)
        if not device:
            continue

        metadata = _port_metadata_blob(port)
        name_match = any(term in metadata for term in normalized_names)
        id_match = _matches_usb_ids(
            port, vendor_id=normalized_vendor, product_id=normalized_product
        )

        if name_match:
            matched_by_name.append(device)
        elif id_match:
            matched_by_ids.append(device)
        else:
            fallback_ports.append(device)

    for bucket in (matched_by_name, matched_by_ids, fallback_ports):
        for candidate in bucket:
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


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
