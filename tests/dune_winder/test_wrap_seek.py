import unittest

from dune_winder.core.process import Process
from dune_winder.core.winder_workspace import WinderWorkspace


class FakeRecipe:
    def __init__(self, period, lines):
        self._period = period
        self._lines = lines

    def getDetectedPeriod(self):
        return self._period

    def getLines(self):
        return self._lines


class FakeWorkspace:
    def __init__(self, line):
        self.line = line
        self.wraps = []
        self.forecastWraps = []

    def getWrapSeekLine(self, wrap):
        self.wraps.append(wrap)
        return self.line

    def getWrapForecastLine(self, wrap):
        self.forecastWraps.append(wrap)
        return self.line


class WrapSeekTests(unittest.TestCase):
    def test_get_wrap_seek_line_uses_latest_prior_head_restart_before_wrap_start(self):
        workspace = object.__new__(WinderWorkspace)
        workspace._layer = None
        workspace._recipe = FakeRecipe(
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

        self.assertEqual(workspace.getWrapSeekLine(2), 2)

    def test_get_wrap_seek_line_prefers_latest_prior_head_restart_marker(self):
        lines = [
            "N1 preamble\n",
            "N2 (1,1) start wrap 1\n",
            "N3 (1,2 HEAD RESTART) early restart\n",
            "N4 (1,3) move\n",
            "N5 (HEAD RESTART) later restart\n",
            "N6 (2,1) start wrap 2\n",
        ]

        workspace = object.__new__(WinderWorkspace)
        workspace._layer = None
        workspace._recipe = FakeRecipe(30, lines)

        self.assertEqual(workspace.getWrapSeekLine(2), 3)

    def test_get_wrap_seek_line_starts_first_wrap_at_beginning_even_with_restart_marker(
        self,
    ):
        lines = [
            "N1 preamble\n",
            "N2 (1,1) start wrap 1\n",
            "N3 (1,2) move\n",
            "N4 (HEAD RESTART) later in wrap 1\n",
            "N5 (2,1) start wrap 2\n",
        ]

        workspace = object.__new__(WinderWorkspace)
        workspace._layer = None
        workspace._recipe = FakeRecipe(9, lines)

        self.assertEqual(workspace.getWrapSeekLine(1), -1)

    def test_get_wrap_seek_line_rejects_invalid_wrap_numbers(self):
        workspace = object.__new__(WinderWorkspace)
        workspace._layer = None
        workspace._recipe = FakeRecipe(46, ["N1\n"] * 100)

        self.assertIsNone(workspace.getWrapSeekLine(0))
        self.assertIsNone(workspace.getWrapSeekLine("bad"))

    def test_get_wrap_seek_line_returns_none_when_wrap_start_marker_is_missing(self):
        workspace = object.__new__(WinderWorkspace)
        workspace._layer = None
        workspace._recipe = FakeRecipe(
            46,
            [
                "N1 preamble\n",
                "N2 (1,1) start wrap 1\n",
                "N3 (HEAD RESTART)\n",
                "N4 (1,2) move\n",
            ],
        )

        self.assertIsNone(workspace.getWrapSeekLine(2))

    def test_get_wrap_seek_line_targets_head_b_corner_line_when_present(self):
        lines = [
            "N1 preamble\n",
            "N2 (1,1) start wrap 1\n",
            "N3 (1,2) move\n",
            "N4 (1,3) move\n",
            "N5 (2,1) start wrap 2\n",
            "N6 (2,2) move\n",
            "N7 (2,10) (HEAD RESTART) (Head B corner)\n",
            "N8 (2,11) move\n",
        ]

        workspace = object.__new__(WinderWorkspace)
        workspace._layer = None
        workspace._recipe = FakeRecipe(8, lines)

        self.assertEqual(workspace.getWrapSeekLine(2), 5)


class WrapForecastLineTests(unittest.TestCase):
    def _workspace(self, lines):
        workspace = object.__new__(WinderWorkspace)
        workspace._layer = None
        workspace._recipe = FakeRecipe(18, lines)
        return workspace

    def test_returns_wind_log_number_of_last_labeled_line_for_wrap(self):
        # WindMode logs each line as its zero-based program index + 2, which is
        # one greater than its one-based getLines() index.  The last "(2,*)"
        # label is at one-based index 6, so the forecast line is 7.
        lines = [
            "N1 preamble\n",
            "N2 (1,1) start wrap 1\n",
            "N3 (1,2) move\n",
            "N4 (2,1) start wrap 2\n",
            "N5 (2,2) move\n",
            "N6 (2,3) ~increment(0,-50)\n",
            "N7 (3,1) start wrap 3\n",
        ]
        workspace = self._workspace(lines)

        self.assertEqual(workspace.getWrapForecastLine(2), 7)
        self.assertEqual(workspace.getWrapForecastLine(3), 8)

    def test_ignores_non_label_parentheses_for_other_wraps(self):
        # "(0,-50)" must not be mistaken for a wrap-0 label.
        lines = [
            "N1 (5,1) move ~increment(0,-50)\n",
            "N2 (5,2) move ~anchorToTarget(A1,A2,offset=(1,0))\n",
        ]
        workspace = self._workspace(lines)

        self.assertEqual(workspace.getWrapForecastLine(5), 3)
        self.assertIsNone(workspace.getWrapForecastLine(0))

    def test_returns_none_when_wrap_label_is_missing(self):
        workspace = self._workspace(["N1 (1,1) move\n", "N2 (1,2) move\n"])

        self.assertIsNone(workspace.getWrapForecastLine(2))

    def test_rejects_invalid_wrap_numbers(self):
        workspace = self._workspace(["N1 (1,1) move\n"])

        self.assertIsNone(workspace.getWrapForecastLine(0))
        self.assertIsNone(workspace.getWrapForecastLine("bad"))


class ProcessWrapSeekTests(unittest.TestCase):
    def test_get_wrap_seek_line_proxies_to_loaded_workspace(self):
        process = object.__new__(Process)
        process.workspace = FakeWorkspace(79)

        self.assertEqual(process.getWrapSeekLine(2), 79)
        self.assertEqual(process.workspace.wraps, [2])

    def test_get_wrap_seek_line_returns_none_without_loaded_workspace(self):
        process = object.__new__(Process)
        process.workspace = None

        self.assertIsNone(process.getWrapSeekLine(2))

    def test_get_wrap_forecast_line_proxies_to_loaded_workspace(self):
        process = object.__new__(Process)
        process.workspace = FakeWorkspace(58)

        self.assertEqual(process.getWrapForecastLine(4), 58)
        self.assertEqual(process.workspace.forecastWraps, [4])

    def test_get_wrap_forecast_line_returns_none_without_loaded_workspace(self):
        process = object.__new__(Process)
        process.workspace = None

        self.assertIsNone(process.getWrapForecastLine(2))


if __name__ == "__main__":
    unittest.main()
