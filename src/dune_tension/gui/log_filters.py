"""Shared filters for tensiometer GUI logging."""

from __future__ import annotations

import logging

IGNORED_MESSAGE_FRAGMENTS: tuple[str, ...] = ()


class IgnoredMessageFilter(logging.Filter):
    """Drop known noisy records from GUI-facing log handlers."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not any(fragment in message for fragment in IGNORED_MESSAGE_FRAGMENTS)
