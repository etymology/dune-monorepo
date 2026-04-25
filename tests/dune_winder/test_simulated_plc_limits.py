import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from dune_winder.io.devices.simulated_plc import SimulatedPLC


def test_simulated_plc_update_limits_reflected_in_status():
    plc = SimulatedPLC()
    plc.update_limits(zFront=164.65, zBack=269.35, limitTop=1234.5)
    status = plc.get_status()

    assert status["mode"] == "SIM"
    assert status["limits"]["zFront"] == 164.65
    assert status["limits"]["zBack"] == 269.35
    assert status["limits"]["limitTop"] == 1234.5
