from __future__ import annotations

from pathlib import Path
import pytest
import unittest

from dune_winder.paths import PLC_ROOT
from dune_winder.plc_generated.hmi_stop_request_14 import emit_rll


@pytest.mark.ladder_sim
class HMIStopRequestGenerationTests(unittest.TestCase):
    def test_generated_rll_matches_checked_in_pasteable(self):
        expected_path = PLC_ROOT / "HMI_Stop_Request_14" / "main" / "pasteable.rll"
        self.assertEqual(expected_path.read_text(encoding="utf-8"), emit_rll())


if __name__ == "__main__":
    unittest.main()
