"""Canonical APA naming for the tensiometer GUI and downstream consumers.

Every APA written by new code uses the form ``APA-<LOC>-<NNN>`` where
``LOC`` is ``US`` or ``UK`` and ``NNN`` is a zero-padded number from
``001`` to ``152``. Historical free-text names already in the database
remain readable but are no longer producible from the GUI.
"""

from __future__ import annotations

import re

LOCATIONS: tuple[str, ...] = ("US", "UK")
NUMBERS = range(1, 153)
NUMBER_LABELS: tuple[str, ...] = tuple(f"{n:03d}" for n in NUMBERS)

_CANONICAL_RE = re.compile(r"\AAPA-(US|UK)-(\d{3})\Z")


def compose(location: str, number: int) -> str:
    """Return the canonical name for ``(location, number)``."""

    if location not in LOCATIONS:
        raise ValueError(f"unknown APA location: {location!r}")
    if number not in NUMBERS:
        raise ValueError(f"APA number out of range 1..152: {number!r}")
    return f"APA-{location}-{number:03d}"


def parse(name: str) -> tuple[str, int] | None:
    """Return ``(location, number)`` if ``name`` is canonical, else ``None``."""

    match = _CANONICAL_RE.match(name)
    if match is None:
        return None
    number = int(match.group(2))
    if number not in NUMBERS:
        return None
    return match.group(1), number


def is_canonical(name: str) -> bool:
    return parse(name) is not None


def all_canonical_names() -> list[str]:
    """Every valid canonical APA name, sorted."""

    return sorted(compose(loc, n) for loc in LOCATIONS for n in NUMBERS)
