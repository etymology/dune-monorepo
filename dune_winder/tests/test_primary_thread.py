import threading
import unittest

from dune_winder.threads.PrimaryThread import PrimaryThread


class FakeLog:
  def __init__(self):
    self.entries = []

  def add(self, *args):
    self.entries.append(args)


class DummyPrimaryThread(PrimaryThread):
  def __init__(self, log):
    PrimaryThread.__init__(self, "DummyPrimaryThread", log)

  def body(self):
    return None


class PrimaryThreadTests(unittest.TestCase):
  def setUp(self):
    self._originalInstances = list(PrimaryThread.thread_instances)
    self._originalIsRunning = PrimaryThread.isRunning
    self._originalStopContext = PrimaryThread.getStopContext()

    PrimaryThread.thread_instances = []
    PrimaryThread.isRunning = False
    with PrimaryThread._stopContextLock:
      PrimaryThread._stopContext = None

  def tearDown(self):
    PrimaryThread.thread_instances = self._originalInstances
    PrimaryThread.isRunning = self._originalIsRunning
    with PrimaryThread._stopContextLock:
      PrimaryThread._stopContext = self._originalStopContext

  def test_stop_all_threads_records_reason_and_details(self):
    log = FakeLog()
    DummyPrimaryThread(log)

    PrimaryThread.stopAllThreads("unit_test", ["detail"])

    context = PrimaryThread.getStopContext()
    self.assertEqual(context["reason"], "unit_test")
    self.assertEqual(context["thread"], threading.current_thread().name)
    self.assertEqual(context["details"], ["detail"])
    self.assertTrue(context["stack"])
    self.assertTrue(
      any(entry[1] == "THREADS_STOP" for entry in log.entries),
      "Expected shutdown log entry.",
    )

  def test_run_logs_when_body_returns_while_running(self):
    log = FakeLog()
    thread = DummyPrimaryThread(log)
    PrimaryThread.isRunning = True

    thread.run()

    entryTypes = [entry[1] for entry in log.entries]
    self.assertIn("THREAD_START", entryTypes)
    self.assertIn("THREAD_EXIT", entryTypes)
    self.assertTrue(
      any(
        "returned while shutdown had not been requested" in entry[2]
        for entry in log.entries
        if len(entry) > 2
      )
    )
