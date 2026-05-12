"""Tests for the legacy IO_Log file writer."""

from __future__ import annotations

import os
from pathlib import Path

from dune_winder.core.io_log import IO_Log


def test_io_log_creates_parent_directory(tmp_path: Path):
    log_path = tmp_path / "deep" / "nested" / "io.log"
    IO_Log(str(log_path))
    assert log_path.exists()


def test_io_log_writes_header_on_new_file(tmp_path: Path):
    log_path = tmp_path / "io.log"
    log = IO_Log(str(log_path))
    log_close(log)

    contents = log_path.read_text().splitlines()
    assert len(contents) == 1
    header = contents[0]
    assert header.startswith("Time\tLoop time\t")


def test_io_log_appends_without_rewriting_header(tmp_path: Path):
    log_path = tmp_path / "io.log"
    first = IO_Log(str(log_path))
    log_close(first)

    second = IO_Log(str(log_path))
    second.log("2025-01-01T00:00:00", 12)
    log_close(second)

    lines = log_path.read_text().splitlines()
    # Header line + one data row, with no second header inserted by the second open.
    assert len(lines) == 2
    assert lines[0].startswith("Time\t")
    assert lines[1].startswith("2025-01-01T00:00:00\t12\t")


def test_io_log_log_writes_timestamp_and_loop_time(tmp_path: Path):
    log_path = tmp_path / "io.log"
    log = IO_Log(str(log_path))
    log.log("ts", 7)
    log_close(log)

    rows = log_path.read_text().splitlines()
    # Header + one row.
    assert len(rows) == 2
    assert rows[1].startswith("ts\t7\t")


def log_close(log: IO_Log) -> None:
    """IO_Log keeps the file handle open; explicitly close so the OS flushes."""
    log._outputFile.close()
