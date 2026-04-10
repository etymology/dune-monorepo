"""Persistent logging helpers for the tensiometer GUI process."""

from __future__ import annotations

import atexit
from datetime import datetime
from dataclasses import dataclass
import faulthandler
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import sys
import threading
import traceback
from types import FrameType
from typing import Any

from dune_tension.paths import data_path

LOGGER = logging.getLogger(__name__)
_CRASH_LOGGER_NAME = "dune_tension.gui.crash"
_ACTIVE_BINDING: "GuiCrashLoggingBinding | None" = None


@dataclass
class GuiCrashLoggingBinding:
    """Track installed process-level crash logging hooks."""

    log_path: Path
    fault_log_path: Path
    file_handler: logging.Handler
    fault_stream: Any
    previous_excepthook: Any
    previous_threading_excepthook: Any
    previous_signal_handlers: dict[int, Any]

    def flush(self) -> None:
        try:
            self.file_handler.flush()
        except Exception:
            pass
        try:
            self.fault_stream.flush()
        except Exception:
            pass

    def close(self) -> None:
        self.flush()
        root_logger = logging.getLogger()
        try:
            root_logger.removeHandler(self.file_handler)
        except Exception:
            pass
        try:
            self.file_handler.close()
        except Exception:
            pass
        try:
            self.fault_stream.close()
        except Exception:
            pass


def install_gui_crash_logging() -> GuiCrashLoggingBinding:
    """Install persistent file logging and crash hooks for the GUI process."""

    global _ACTIVE_BINDING
    if _ACTIVE_BINDING is not None:
        return _ACTIVE_BINDING

    log_dir = data_path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "tensiometer_gui.log"
    fault_log_path = log_dir / "tensiometer_gui_faults.log"

    root_logger = logging.getLogger()
    if root_logger.level in (logging.NOTSET, 0) or root_logger.level > logging.INFO:
        root_logger.setLevel(logging.INFO)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [pid=%(process)d %(threadName)s %(name)s] %(message)s"
        )
    )
    root_logger.addHandler(file_handler)

    fault_stream = fault_log_path.open("a", encoding="utf-8", buffering=1)
    _write_fault_header(fault_stream)
    try:
        faulthandler.enable(file=fault_stream, all_threads=True)
    except Exception:
        LOGGER.exception("Failed to enable faulthandler for %s", fault_log_path)

    previous_excepthook = sys.excepthook
    previous_threading_excepthook = getattr(threading, "excepthook", None)
    previous_signal_handlers: dict[int, Any] = {}

    crash_logger = logging.getLogger(_CRASH_LOGGER_NAME)

    def handle_uncaught_exception(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: Any,
        *,
        origin: str,
    ) -> None:
        crash_logger.critical(
            "Unhandled exception from %s",
            origin,
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        if _ACTIVE_BINDING is not None:
            _ACTIVE_BINDING.flush()

    def excepthook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: Any,
    ) -> None:
        handle_uncaught_exception(
            exc_type,
            exc_value,
            exc_traceback,
            origin="sys.excepthook",
        )
        if callable(previous_excepthook):
            previous_excepthook(exc_type, exc_value, exc_traceback)

    sys.excepthook = excepthook

    if previous_threading_excepthook is not None:
        def threading_excepthook(args: Any) -> None:
            thread_name = getattr(getattr(args, "thread", None), "name", "unknown")
            handle_uncaught_exception(
                args.exc_type,
                args.exc_value,
                args.exc_traceback,
                origin=f"thread {thread_name}",
            )
            previous_threading_excepthook(args)

        threading.excepthook = threading_excepthook

    for signum in _iter_supported_signal_numbers():
        previous_handler = signal.getsignal(signum)
        previous_signal_handlers[signum] = previous_handler

        def handler(_signum: int, frame: FrameType | None, *, _prev: Any = previous_handler) -> None:
            crash_logger.warning(
                "Received signal %s (%s) at %s",
                _signal_name(_signum),
                _signum,
                _format_frame(frame),
            )
            if _ACTIVE_BINDING is not None:
                _ACTIVE_BINDING.flush()
            if callable(_prev):
                _prev(_signum, frame)
                return
            if _prev == signal.SIG_IGN:
                return
            signal.signal(_signum, signal.SIG_DFL)
            os.kill(os.getpid(), _signum)

        try:
            signal.signal(signum, handler)
        except Exception:
            crash_logger.exception(
                "Failed to install signal handler for %s",
                _signal_name(signum),
            )

    def log_process_exit() -> None:
        crash_logger.info(
            "GUI process exiting cleanly. %s",
            format_process_stats(),
        )
        if _ACTIVE_BINDING is not None:
            _ACTIVE_BINDING.flush()

    atexit.register(log_process_exit)

    _ACTIVE_BINDING = GuiCrashLoggingBinding(
        log_path=log_path,
        fault_log_path=fault_log_path,
        file_handler=file_handler,
        fault_stream=fault_stream,
        previous_excepthook=previous_excepthook,
        previous_threading_excepthook=previous_threading_excepthook,
        previous_signal_handlers=previous_signal_handlers,
    )
    crash_logger.info(
        "Installed GUI crash logging. log_path=%s fault_log_path=%s pid=%s python=%s %s",
        log_path,
        fault_log_path,
        os.getpid(),
        sys.version.split()[0],
        format_process_stats(),
    )
    _ACTIVE_BINDING.flush()
    return _ACTIVE_BINDING


def install_tk_exception_logging(root: Any) -> None:
    """Log uncaught Tk callback exceptions through the persistent crash logger."""

    crash_logger = logging.getLogger(_CRASH_LOGGER_NAME)
    previous_handler = getattr(root, "report_callback_exception", None)

    def report_callback_exception(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: Any,
    ) -> None:
        crash_logger.error(
            "Unhandled Tk callback exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        if _ACTIVE_BINDING is not None:
            _ACTIVE_BINDING.flush()
        if callable(previous_handler):
            previous_handler(exc_type, exc_value, exc_traceback)

    root.report_callback_exception = report_callback_exception


def format_process_stats() -> str:
    """Return a compact one-line process snapshot for crash breadcrumbs."""

    parts = [
        f"threads={threading.active_count()}",
    ]

    memory = _linux_memory_stats()
    if memory:
        parts.append(memory)

    return " ".join(parts)


def _iter_supported_signal_numbers() -> tuple[int, ...]:
    signal_names = ("SIGINT", "SIGTERM", "SIGHUP", "SIGQUIT")
    return tuple(
        getattr(signal, name)
        for name in signal_names
        if hasattr(signal, name)
    )


def _signal_name(signum: int) -> str:
    try:
        return signal.Signals(signum).name
    except Exception:
        return f"signal-{signum}"


def _format_frame(frame: FrameType | None) -> str:
    if frame is None:
        return "unknown-frame"
    stack = traceback.extract_stack(frame, limit=1)
    if not stack:
        return "unknown-frame"
    leaf = stack[-1]
    return f"{leaf.filename}:{leaf.lineno} in {leaf.name}"


def _linux_memory_stats() -> str:
    status_path = Path("/proc/self/status")
    if not status_path.exists():
        return ""

    wanted = {"VmRSS", "VmHWM", "VmSize"}
    parts: list[str] = []
    try:
        for line in status_path.read_text(encoding="utf-8").splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            if key in wanted:
                parts.append(f"{key.lower()}={value.strip()}")
    except Exception:
        return ""
    return " ".join(parts)


def _write_fault_header(stream: Any) -> None:
    try:
        stream.write(
            f"\n[{datetime.now().isoformat(timespec='seconds')}] "
            f"starting fault capture pid={os.getpid()} argv={' '.join(sys.argv)}\n"
        )
    except Exception:
        pass
