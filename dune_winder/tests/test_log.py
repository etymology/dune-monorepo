import os
import tempfile
import unittest

from dune_winder.library.log import Log


class FakeTimeSource:
  def __init__(self):
    self.value = 0

  def get(self):
    self.value += 1
    return self.value


class LogTests(unittest.TestCase):
  def test_get_all_tail_reads_last_lines_without_header(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      logPath = os.path.join(rootDirectory, "log.csv")
      log = Log(FakeTimeSource(), logPath, localEcho=False)

      log.add("ModuleA", "INFO", "First")
      log.add("ModuleB", "WARN", "Second")
      log.add("ModuleC", "ERROR", "Third")

      result = log.getAll(2)
      log.detach(logPath)

      self.assertEqual(len(result), 2)
      self.assertTrue(result[0].endswith("\tModuleB\tWARN\tSecond"))
      self.assertTrue(result[1].endswith("\tModuleC\tERROR\tThird"))

  def test_get_all_tail_returns_no_header_when_log_has_no_entries(self):
    with tempfile.TemporaryDirectory() as rootDirectory:
      logPath = os.path.join(rootDirectory, "log.csv")
      log = Log(FakeTimeSource(), logPath, localEcho=False)

      result = log.getAll(50)
      log.detach(logPath)

      self.assertEqual(result, [])
