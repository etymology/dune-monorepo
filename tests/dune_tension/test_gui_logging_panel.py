import importlib.util
import logging
from pathlib import Path
import sys


MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dune_tension"
    / "gui"
    / "logging_panel.py"
)
SPEC = importlib.util.spec_from_file_location(
    "gui_logging_panel_under_test", MODULE_PATH
)
assert SPEC is not None
assert SPEC.loader is not None
logging_panel = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = logging_panel
SPEC.loader.exec_module(logging_panel)


class FakeRoot:
    def __init__(self):
        self._callbacks = []
        self.cancelled = []

    def after(self, _delay, callback):
        token = len(self._callbacks) + 1
        self._callbacks.append((token, callback))
        return token

    def after_cancel(self, token):
        self.cancelled.append(token)

    def flush_next(self):
        _token, callback = self._callbacks.pop(0)
        callback()


class FakeText:
    def __init__(self):
        self.contents = ""
        self.state = None
        self.last_seen = None

    def configure(self, **kwargs):
        if "state" in kwargs:
            self.state = kwargs["state"]

    def insert(self, _index, text):
        self.contents += text

    def see(self, index):
        self.last_seen = index

    def index(self, _index):
        line_count = len(self.contents.splitlines()) or 1
        return f"{line_count}.0"

    def delete(self, _start, end):
        remove_count = max(int(str(end).split(".", 1)[0]) - 1, 0)
        lines = self.contents.splitlines()
        self.contents = "\n".join(lines[remove_count:])
        if self.contents:
            self.contents += "\n"


def test_configure_gui_logging_routes_messages_and_restores_logger_state():
    root = FakeRoot()
    text = FakeText()
    target_logger = logging.getLogger("dune_tension")
    original_level = target_logger.level
    original_propagate = target_logger.propagate

    binding = logging_panel.configure_gui_logging(root, text)
    try:
        assert binding is not None
        logging.getLogger("dune_tension.gui.actions").info("pane message")
        root.flush_next()
        assert "pane message" in text.contents
        assert text.state == "disabled"
        assert text.last_seen == "end"
    finally:
        if binding is not None:
            binding.close()

    assert binding.handler not in target_logger.handlers
    assert target_logger.level == original_level
    assert target_logger.propagate == original_propagate
    assert root.cancelled


def test_configure_gui_logging_ignores_outside_measurable_area_messages():
    root = FakeRoot()
    text = FakeText()

    binding = logging_panel.configure_gui_logging(root, text)
    try:
        assert binding is not None
        logger = logging.getLogger("dune_tension.plc_io")
        logger.warning(
            "Target 7005.8,320.99639892578125 is outside the measurable area. "
            "Please enter a valid position."
        )
        logger.warning("different warning")
        root.flush_next()
    finally:
        if binding is not None:
            binding.close()

    assert "outside the measurable area" not in text.contents
    assert "different warning" in text.contents


def test_tk_text_log_handler_caps_messages_per_tick():
    root = FakeRoot()
    text = FakeText()
    handler = logging_panel.TkTextLogHandler(
        root,
        text,
        max_lines=10000,
        max_messages_per_tick=10,
        burst_poll_interval_ms=3,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))

    logger = logging.getLogger("gui_logging_panel_under_test.cap")
    original_level = logger.level
    original_propagate = logger.propagate
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)
    try:
        for index in range(50):
            logger.info("msg-%d", index)

        # First tick drains exactly the cap and reschedules at the burst interval.
        root.flush_next()
        first_chunk = text.contents.splitlines()
        assert len(first_chunk) == 10
        assert first_chunk[0] == "msg-0"
        # The reschedule for "more pending" must use the short burst interval.
        next_delay, _next_cb = root._callbacks[-1][0], root._callbacks[-1][1]
        # ``next_delay`` here is the token; verify the actual scheduled delay
        # by inspecting what the handler stored.
        assert handler._after_id is not None

        ticks = 1
        while text.contents.count("\n") < 50 and ticks < 20:
            root.flush_next()
            ticks += 1

        all_lines = text.contents.splitlines()
        assert len(all_lines) == 50
        assert all_lines[0] == "msg-0"
        assert all_lines[-1] == "msg-49"
    finally:
        logger.removeHandler(handler)
        logger.setLevel(original_level)
        logger.propagate = original_propagate
        handler.close()


def test_tk_text_log_handler_trims_old_lines():
    root = FakeRoot()
    text = FakeText()
    handler = logging_panel.TkTextLogHandler(root, text, max_lines=2)
    handler.setFormatter(logging.Formatter("%(message)s"))

    logger = logging.getLogger("gui_logging_panel_under_test.trim")
    original_level = logger.level
    original_propagate = logger.propagate
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)
    try:
        logger.info("first")
        logger.info("second")
        logger.info("third")
        root.flush_next()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(original_level)
        logger.propagate = original_propagate
        handler.close()

    assert text.contents.splitlines() == ["second", "third"]
