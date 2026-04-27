import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from dune_winder.analysis.uv_tangency_analysis import (
    AVAILABLE_SENSITIVITY_IDS,
    build_uv_tangency_report,
    compare_uv_tangency_reports,
    main,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MACHINE_CALIBRATION_PATH = _REPO_ROOT / "dune_winder/config/machineCalibration.json"
_U_LAYER_CALIBRATION_PATH = _REPO_ROOT / "config/frame_geometry/U_Calibration.json"
_V_LAYER_CALIBRATION_PATH = _REPO_ROOT / "config/frame_geometry/V_Calibration.json"


class UVTangencyAnalysisTests(unittest.TestCase):
    def test_build_uv_tangency_report_returns_site_geometry_and_sensitivities(self):
        report = build_uv_tangency_report(
            "U",
            1,
            site_ids=["bottom_a_foot_end"],
            sensitivity_names=["global_x_shift", "x_from_y_skew"],
            machine_calibration_path=_MACHINE_CALIBRATION_PATH,
            layer_calibration_path=_U_LAYER_CALIBRATION_PATH,
        )

        self.assertEqual(report["layer"], "U")
        self.assertEqual(report["wrap"], 1)
        self.assertEqual(
            report["machineCalibrationPath"], str(_MACHINE_CALIBRATION_PATH)
        )
        self.assertEqual(report["layerCalibrationPath"], str(_U_LAYER_CALIBRATION_PATH))
        self.assertEqual(len(report["sites"]), 1)

        site = report["sites"][0]
        self.assertEqual(site["siteId"], "bottom_a_foot_end")
        self.assertEqual(site["offsetAxis"], "x")
        self.assertIsNotNone(site["orientation"])
        self.assertIn("commandedMachinePoint", site)
        self.assertIn("actualWirePoint", site)
        self.assertIn("machineToActualDelta", site)
        self.assertGreater(
            abs(
                float(site["actualWirePoint"]["x"])
                - float(site["commandedMachinePoint"]["x"])
            ),
            0.01,
        )
        self.assertEqual(
            set(site["sensitivities"].keys()),
            {"global_x_shift", "x_from_y_skew"},
        )

    def test_compare_uv_tangency_reports_returns_both_layers(self):
        report = compare_uv_tangency_reports(
            "U",
            1,
            compare_layer="V",
            site_ids=["top_b_foot_end"],
            sensitivity_names=["global_x_shift"],
            machine_calibration_path=_MACHINE_CALIBRATION_PATH,
            layer_calibration_path=_U_LAYER_CALIBRATION_PATH,
            compare_layer_calibration_path=_V_LAYER_CALIBRATION_PATH,
        )

        self.assertEqual(report["primary"]["layer"], "U")
        self.assertEqual(report["comparison"]["layer"], "V")
        self.assertEqual(report["primary"]["sites"][0]["siteId"], "top_b_foot_end")
        self.assertEqual(report["comparison"]["sites"][0]["siteId"], "top_b_foot_end")

    def test_cli_main_emits_json_report(self):
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "--layer",
                    "U",
                    "--wrap",
                    "1",
                    "--site",
                    "top_b_foot_end",
                    "--sensitivity",
                    "global_x_shift",
                    "--machine-calibration",
                    str(_MACHINE_CALIBRATION_PATH),
                    "--layer-calibration",
                    str(_U_LAYER_CALIBRATION_PATH),
                ]
            )

        payload = json.loads(output.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["layer"], "U")
        self.assertEqual(payload["wrap"], 1)
        self.assertEqual(payload["sites"][0]["siteId"], "top_b_foot_end")
        self.assertEqual(
            set(payload["sites"][0]["sensitivities"].keys()),
            {"global_x_shift"},
        )
        self.assertIn("global_x_shift", AVAILABLE_SENSITIVITY_IDS)


if __name__ == "__main__":
    unittest.main()
