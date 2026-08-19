import unittest

from dune_winder.core.motion_service import MotionService


class _Log:
    def __init__(self):
        self.entries = []

    def add(self, source, code, message, data=None):
        self.entries.append((source, code, message, data))


class _Workspace:
    def __init__(self, layer):
        self._layer = layer

    def getLayer(self):
        return self._layer


class _HeadCompensation:
    def __init__(self, machineCalibration=None):
        self._machineCalibration = machineCalibration


class _MachineCalibration:
    def __init__(self, cameraWireOffsetX, cameraWireOffsetY):
        self.cameraWireOffsetX = cameraWireOffsetX
        self.cameraWireOffsetY = cameraWireOffsetY


def _build_service(layer, machineCalibration=None):
    """
    Build a MotionService stub exercising only seekPinNominal's dependencies:
    the workspace layer, the head compensation's machine calibration, the log,
    and manualSeekXY (recorded rather than dispatched).
    """
    service = object.__new__(MotionService)
    service._log = _Log()
    service._headCompensation = _HeadCompensation(machineCalibration)
    service._workspaceGetter = lambda: _Workspace(layer) if layer else None

    seeks = []

    def recordSeek(xPosition=None, yPosition=None, velocity=None):
        seeks.append((xPosition, yPosition, velocity))
        return False

    service.manualSeekXY = recordSeek
    return service, seeks


class SeekPinNominalTests(unittest.TestCase):
    def test_uv_nominal_seek_uses_measured_apa_best_fit_anchor(self):
        for layer, expected in (
            ("U", (562.3, 2457.1)),
            ("V", (565.5, 2456.1)),
        ):
            with self.subTest(layer=layer):
                service, seeks = _build_service(layer)

                isError = service.seekPinNominal("B1", 100.0)

                self.assertFalse(isError)
                self.assertEqual(len(seeks), 1)
                self.assertAlmostEqual(seeks[0][0], expected[0])
                self.assertAlmostEqual(seeks[0][1], expected[1])
                self.assertAlmostEqual(seeks[0][2], 100.0)

    def test_uv_nominal_seek_keeps_b_family_above_a_family(self):
        # Guards the A/B convention: the legacy nominal grid had these flipped,
        # putting B1 at the bottom of the APA and A1 at the top.
        service, seeks = _build_service("U")

        self.assertFalse(service.seekPinNominal("A1", 100.0))
        self.assertFalse(service.seekPinNominal("B1", 100.0))

        self.assertAlmostEqual(seeks[0][1], 163.7844, places=3)
        self.assertLess(seeks[0][1], seeks[1][1])

    def test_nominal_seek_subtracts_camera_wire_offset(self):
        service, seeks = _build_service(
            "U", _MachineCalibration(cameraWireOffsetX=3.5, cameraWireOffsetY=-2.25)
        )

        self.assertFalse(service.seekPinNominal("B1", 100.0))

        self.assertAlmostEqual(seeks[0][0], 562.3 - 3.5)
        self.assertAlmostEqual(seeks[0][1], 2457.1 + 2.25)

    def test_gx_nominal_seek_positions_are_unchanged(self):
        service, seeks = _build_service("G")

        self.assertFalse(service.seekPinNominal("B1", 100.0))

        self.assertAlmostEqual(seeks[0][0], 573.11)
        self.assertAlmostEqual(seeks[0][1], 167.721)

    def test_unknown_pin_is_refused_without_seeking(self):
        service, seeks = _build_service("U")

        isError = service.seekPinNominal("B9999", 100.0)

        self.assertTrue(isError)
        self.assertEqual(seeks, [])
        self.assertTrue(
            any("does not exist" in entry[2] for entry in service._log.entries)
        )

    def test_missing_workspace_is_refused_without_seeking(self):
        service, seeks = _build_service(None)

        isError = service.seekPinNominal("B1", 100.0)

        self.assertTrue(isError)
        self.assertEqual(seeks, [])


if __name__ == "__main__":
    unittest.main()
