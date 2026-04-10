"""Tk-safe logging support for the tensiometer GUI."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from queue import Empty, SimpleQueue
from typing import Any

LOGGER_NAMES = ("dune_tension", "spectrum_analysis")


class NamespaceLogFilter(logging.Filter):
    """Restrict GUI log display to selected logger namespaces."""

    def __init__(self, namespaces: tuple[str, ...]) -> None:
        super().__init__()
        self.namespaces = tuple(namespaces)

    def filter(self, record: logging.LogRecord) -> bool:
        name = record.name
        return any(
            name == namespace or name.startswith(f"{namespace}.")
            for namespace in self.namespaces
        )


class TkTextLogHandler(logging.Handler):
    """Queue log records and append them to a Tk text widget on the UI thread."""

    def __init__(
        self,
        root: Any,
        text_widget: Any,
        *,
        poll_interval_ms: int = 100,
        max_lines: int = 1000,
    ) -> None:
        super().__init__(level=logging.INFO)
        self.root = root
        self.text_widget = text_widget
        self.poll_interval_ms = int(max(1, poll_interval_ms))
        self.max_lines = int(max(1, max_lines))
        self._queue: SimpleQueue[str] = SimpleQueue()
        self._after_id: Any | None = None
        self._closed = False
        self._schedule_drain()

    def emit(self, record: logging.LogRecord) -> None:
        if self._closed:
            return
        try:
            message = self.format(record)
        except Exception:
            self.handleError(record)
            return
        self._queue.put(message)

    def close(self) -> None:
        self._closed = True
        try:
            after_cancel = getattr(self.root, "after_cancel", None)
            if self._after_id is not None and callable(after_cancel):
                after_cancel(self._after_id)
        except Exception:
            pass
        self._after_id = None
        super().close()

    def _schedule_drain(self) -> None:
        if self._closed:
            return
        try:
            self._after_id = self.root.after(self.poll_interval_ms, self._drain_queue)
        except Exception:
            self._after_id = None

    def _drain_queue(self) -> None:
        if self._closed:
            return

        messages: list[str] = []
        while True:
            try:
                messages.append(self._queue.get_nowait())
            except Empty:
                break

        if messages:
            self._append_messages(messages)

        self._schedule_drain()

    def _append_messages(self, messages: list[str]) -> None:
        configure = getattr(self.text_widget, "configure", None)
        insert = getattr(self.text_widget, "insert", None)
        if not callable(insert):
            return

        try:
            if callable(configure):
                configure(state="normal")
            for message in messages:
                insert("end", f"{message}\n")
            self._trim_lines()
            see = getattr(self.text_widget, "see", None)
            if callable(see):
                see("end")
        finally:
            try:
                if callable(configure):
                    configure(state="disabled")
            except Exception:
                pass

    def _trim_lines(self) -> None:
        index = getattr(self.text_widget, "index", None)
        delete = getattr(self.text_widget, "delete", None)
        if not callable(index) or not callable(delete):
            return

        try:
            end_index = str(index("end-1c"))
            line_count = int(end_index.split(".", 1)[0])
        except Exception:
            return

        overflow = line_count - self.max_lines
        if overflow > 0:
            try:
                delete("1.0", f"{overflow + 1}.0")
            except Exception:
                pass


@dataclass
class GuiLogBinding:
    """Track logger state so GUI logging can be detached cleanly."""

    handler: TkTextLogHandler

    def close(self) -> None:
        try:
            logging.getLogger().removeHandler(self.handler)
        except Exception:
            pass
        self.handler.close()


def configure_gui_logging(root: Any, text_widget: Any) -> GuiLogBinding | None:
    """Attach a text-backed handler to the GUI-relevant logger namespaces."""

    if text_widget is None:
        return None

    handler = TkTextLogHandler(root, text_widget)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s", "%H:%M:%S")
    )
    handler.addFilter(NamespaceLogFilter(LOGGER_NAMES))

    root_logger = logging.getLogger()
    if root_logger.level in (logging.NOTSET, 0) or root_logger.level > logging.INFO:
        root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)

    return GuiLogBinding(handler=handler)
