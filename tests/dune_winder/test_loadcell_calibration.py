import tempfile
import unittest
from collections import namedtuple
from pathlib import Path

from dune_winder.machine.calibration import loadcell

_Tag = namedtuple("Tag", "tag value type error")


class FakePLC:
    """Minimal stand-in for the ControlLogix PLC device.

    Mirrors ``ControllogixPLC.read`` which takes a list of tag names and returns
    a list of tag results, one per requested name.
    """

    def __init__(self, values=None):
        self.values = dict(values or {})
        self.writes = []

    def read(self, tags):
        names = [tags] if isinstance(tags, str) else list(tags)
        results = []
        for name in names:
            if name in self.values:
                results.append(_Tag(name, self.values[name], "REAL", None))
            else:
                results.append(_Tag(name, None, None, "Tag doesn't exist"))
        return results

    def write(self, tag, data=None, typeName=None):
        name, value = tag
        self.writes.append((name, value, typeName))
        self.values[name] = value
        return [tag]


class SequencePLC:
    """Returns a scripted sequence of tension_tag readings."""

    def __init__(self, sequence):
        self.sequence = list(sequence)
        self.index = 0

    def read(self, tags):
        names = [tags] if isinstance(tags, str) else list(tags)
        value = self.sequence[min(self.index, len(self.sequence) - 1)]
        self.index += 1
        return [_Tag(name, value, "REAL", None) for name in names]


def _quartic(coeffs, x):
    a0, a1, a2, a3, a4 = coeffs
    return a0 + a1 * x + a2 * x**2 + a3 * x**3 + a4 * x**4


class FitPolynomialTest(unittest.TestCase):
    def test_returns_none_with_too_few_points(self):
        self.assertIsNone(loadcell.fit_polynomial([1.0], [1.0], 4, False))
        self.assertIsNone(loadcell.fit_polynomial([], [], 4, True))

    def test_free_intercept_recovers_quartic(self):
        coeffs = (0.5, 2.0, -0.1, 0.02, -0.001)
        xs = [float(i) for i in range(11)]
        ys = [_quartic(coeffs, x) for x in xs]

        fit = loadcell.fit_polynomial(xs, ys, max_degree=4, fix_intercept=False)

        self.assertIsNotNone(fit)
        self.assertNotIn("error", fit)
        self.assertEqual(fit["degree"], 4)
        self.assertLess(fit["rmsNewtons"], 1e-6)
        self.assertAlmostEqual(fit["coefficients"]["a0"], 0.5, places=4)
        self.assertEqual(fit["pointCount"], 11)

    def test_fixed_intercept_pins_a0_to_zero(self):
        coeffs = (0.0, 1.5, 0.05, -0.01, 0.0005)
        xs = [float(i) for i in range(1, 9)]
        ys = [_quartic(coeffs, x) for x in xs]

        fit = loadcell.fit_polynomial(xs, ys, max_degree=4, fix_intercept=True)

        self.assertIsNotNone(fit)
        self.assertEqual(fit["coefficients"]["a0"], 0.0)
        self.assertTrue(fit["fixIntercept"])
        self.assertLess(fit["rmsNewtons"], 1e-6)

    def test_two_points_fit_linear_even_when_quartic_allowed(self):
        # A dead-zone line: y = -1.5 + 2*x (does not pass through origin).
        xs = [2.0, 8.0]
        ys = [2.5, 14.5]

        fit = loadcell.fit_polynomial(xs, ys, max_degree=4, fix_intercept=False)

        self.assertIsNotNone(fit)
        self.assertEqual(fit["degree"], 1)
        self.assertAlmostEqual(fit["coefficients"]["a0"], -1.5, places=6)
        self.assertAlmostEqual(fit["coefficients"]["a1"], 2.0, places=6)
        # Unused high-order terms are zero-filled for the PLC.
        self.assertEqual(fit["coefficients"]["a2"], 0.0)
        self.assertEqual(fit["coefficients"]["a3"], 0.0)
        self.assertEqual(fit["coefficients"]["a4"], 0.0)

    def test_max_degree_caps_below_sample_support(self):
        xs = [float(i) for i in range(8)]
        ys = [1.0 + 2.0 * x for x in xs]

        fit = loadcell.fit_polynomial(xs, ys, max_degree=2, fix_intercept=False)

        self.assertEqual(fit["degree"], 2)
        self.assertEqual(fit["maxDegree"], 2)

    def test_effective_degree(self):
        self.assertEqual(loadcell.effective_degree(2, 4, False), 1)
        self.assertEqual(loadcell.effective_degree(3, 4, False), 2)
        self.assertEqual(loadcell.effective_degree(5, 4, False), 4)
        self.assertEqual(loadcell.effective_degree(10, 2, False), 2)
        self.assertEqual(loadcell.effective_degree(1, 4, False), 0)
        # fixed intercept needs one fewer point for the same degree.
        self.assertEqual(loadcell.effective_degree(1, 4, True), 1)


class CaptureStableTensionTest(unittest.TestCase):
    def test_settles_on_steady_readings(self):
        plc = SequencePLC([10.01, 9.99, 10.0, 10.0, 10.0, 10.0])
        result = loadcell.capture_stable_tension(
            plc,
            window=3,
            interval=0,
            tolerance=0.05,
            timeout=5,
            sleep=lambda *_: None,
        )
        self.assertTrue(result["settled"])
        self.assertAlmostEqual(result["tensionTag"], 10.0, places=2)

    def test_reports_unsettled_on_timeout(self):
        clock = iter([0.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0])
        plc = SequencePLC([0.0, 5.0, 0.0, 5.0, 0.0, 5.0, 0.0, 5.0])
        result = loadcell.capture_stable_tension(
            plc,
            window=3,
            interval=0,
            tolerance=0.01,
            timeout=3,
            sleep=lambda *_: None,
            monotonic=lambda: next(clock),
        )
        self.assertFalse(result["settled"])
        self.assertIn("tensionTag", result)


class PLCCoefficientTest(unittest.TestCase):
    def test_read_and_write_round_trip(self):
        plc = FakePLC(
            {
                "Program:tension_pid.a0": 0.0,
                "Program:tension_pid.a1": 2.0,
                "Program:tension_pid.a2": -0.1,
                "Program:tension_pid.a3": 0.0,
                "Program:tension_pid.a4": 0.0,
            }
        )
        read = loadcell.read_plc_coefficients(plc)
        self.assertTrue(read["available"])
        self.assertAlmostEqual(read["coefficients"]["a1"], 2.0)

        loadcell.write_plc_coefficients(
            plc, {"a0": 1.0, "a1": 2.0, "a2": 3.0, "a3": 4.0, "a4": 5.0}
        )
        self.assertEqual(plc.values["Program:tension_pid.a4"], 5.0)
        self.assertTrue(all(w[2] == "REAL" for w in plc.writes))

    def test_missing_tag_marks_unavailable(self):
        read = loadcell.read_plc_coefficients(FakePLC({}))
        self.assertFalse(read["available"])

    def test_write_without_plc_raises(self):
        with self.assertRaises(RuntimeError):
            loadcell.write_plc_coefficients(
                None, {"a0": 0, "a1": 0, "a2": 0, "a3": 0, "a4": 0}
            )


class StorageTest(unittest.TestCase):
    def test_round_trips_through_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "loadcell_calibration.json"
            cal = loadcell.LoadcellCalibration(path)
            cal.set_fix_intercept(True)
            cal.set_max_degree(3)
            cal.add_sample(500.0, 12.3)
            sample = cal.add_sample(1000.0, 24.6)

            reloaded = loadcell.LoadcellCalibration(path)
            self.assertEqual(len(reloaded.samples), 2)
            self.assertTrue(reloaded.fix_intercept)
            self.assertEqual(reloaded.max_degree, 3)

            # next id stays ahead of loaded ids.
            new_sample = reloaded.add_sample(250.0, 6.1)
            self.assertGreater(new_sample.id, sample.id)

    def test_delete_and_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            cal = loadcell.LoadcellCalibration(Path(tmp) / "cal.json")
            first = cal.add_sample(100.0, 2.0)
            cal.add_sample(200.0, 4.0)
            self.assertTrue(cal.delete_sample(first.id))
            self.assertFalse(cal.delete_sample(9999))
            self.assertEqual(len(cal.samples), 1)
            cal.clear()
            self.assertEqual(len(cal.samples), 0)

    def test_newtons_conversion(self):
        with tempfile.TemporaryDirectory() as tmp:
            cal = loadcell.LoadcellCalibration(Path(tmp) / "cal.json")
            sample = cal.add_sample(1000.0, 5.0)
            self.assertAlmostEqual(sample.newtons, loadcell.GRAVITY, places=6)


if __name__ == "__main__":
    unittest.main()
