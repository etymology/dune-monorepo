import unittest

from dune_winder.core.AnodePlaneArray import AnodePlaneArray
from dune_winder.core.Process import Process


class FakeRecipe:
  def __init__(self, period, lines):
    self._period = period
    self._lines = lines

  def getDetectedPeriod(self):
    return self._period

  def getLines(self):
    return self._lines


class FakeAPA:
  def __init__(self, line):
    self.line = line
    self.wraps = []

  def getWrapSeekLine(self, wrap):
    self.wraps.append(wrap)
    return self.line


class WrapSeekTests(unittest.TestCase):
  def test_get_wrap_seek_line_uses_latest_prior_head_restart_before_wrap_start(self):
    apa = object.__new__(AnodePlaneArray)
    apa._recipe = FakeRecipe(
      11,
      [
        "N1 setup\n",
        "N2 (1,1) start wrap 1\n",
        "N3 (1,2) move\n",
        "N4 (HEAD RESTART) stable restart\n",
        "N5 (1,4) move\n",
        "N6 (2,1) start wrap 2\n",
      ],
    )

    self.assertEqual(apa.getWrapSeekLine(2), 2)

  def test_get_wrap_seek_line_prefers_latest_prior_head_restart_marker(self):
    lines = [
      "N1 preamble\n",
      "N2 (1,1) start wrap 1\n",
      "N3 (1,2 HEAD RESTART) early restart\n",
      "N4 (1,3) move\n",
      "N5 (HEAD RESTART) later restart\n",
      "N6 (2,1) start wrap 2\n",
    ]

    apa = object.__new__(AnodePlaneArray)
    apa._recipe = FakeRecipe(30, lines)

    self.assertEqual(apa.getWrapSeekLine(2), 3)

  def test_get_wrap_seek_line_starts_first_wrap_at_beginning_even_with_restart_marker(self):
    lines = [
      "N1 preamble\n",
      "N2 (1,1) start wrap 1\n",
      "N3 (1,2) move\n",
      "N4 (HEAD RESTART) later in wrap 1\n",
      "N5 (2,1) start wrap 2\n",
    ]

    apa = object.__new__(AnodePlaneArray)
    apa._recipe = FakeRecipe(9, lines)

    self.assertEqual(apa.getWrapSeekLine(1), -1)

  def test_get_wrap_seek_line_rejects_invalid_wrap_numbers(self):
    apa = object.__new__(AnodePlaneArray)
    apa._recipe = FakeRecipe(46, ["N1\n"] * 100)

    self.assertIsNone(apa.getWrapSeekLine(0))
    self.assertIsNone(apa.getWrapSeekLine("bad"))

  def test_get_wrap_seek_line_returns_none_when_wrap_start_marker_is_missing(self):
    apa = object.__new__(AnodePlaneArray)
    apa._recipe = FakeRecipe(
      46,
      [
        "N1 preamble\n",
        "N2 (1,1) start wrap 1\n",
        "N3 (HEAD RESTART)\n",
        "N4 (1,2) move\n",
      ],
    )

    self.assertIsNone(apa.getWrapSeekLine(2))


class ProcessWrapSeekTests(unittest.TestCase):
  def test_get_wrap_seek_line_proxies_to_loaded_apa(self):
    process = object.__new__(Process)
    process.apa = FakeAPA(79)

    self.assertEqual(process.getWrapSeekLine(2), 79)
    self.assertEqual(process.apa.wraps, [2])

  def test_get_wrap_seek_line_returns_none_without_loaded_apa(self):
    process = object.__new__(Process)
    process.apa = None

    self.assertIsNone(process.getWrapSeekLine(2))


if __name__ == "__main__":
  unittest.main()
