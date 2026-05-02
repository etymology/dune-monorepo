"""PLC_Motor on top of the new TagBus, against the legacy SimulatedPLC.

Confirms the migrated Motor preserves its public behaviour: position seeks
land in the underlying PLC; readbacks reflect the PLC state.
"""

from __future__ import annotations

import pytest

pytest.importorskip("dune_plc_bus")

from dune_winder.io.devices.simulated_plc import SimulatedPLC
from dune_winder.io.primitives.plc_motor import PLC_Motor


@pytest.fixture()
def plc():
    p = SimulatedPLC()
    p.initialize()
    return p


def test_motor_set_desired_position_writes_to_plc(plc):
    motor = PLC_Motor("zAxis", plc, "Z")
    motor.setDesiredPosition(42.0)
    assert plc.get_tag("Z_POSITION") == pytest.approx(42.0)
    assert motor.getDesiredPosition() == pytest.approx(42.0)


def test_motor_set_velocity_split_into_speed_and_dir(plc):
    motor = PLC_Motor("xAxis", plc, "X")
    motor.setVelocity(-2.5)
    assert plc.get_tag("X_SPEED") == pytest.approx(2.5)
    assert plc.get_tag("X_DIR") == 1


def test_motor_get_position_reads_axis_actual(plc):
    from dune_winder.io.devices.tag_bus_registry import tag_bus_for

    plc.set_tag("Y_axis.ActualPosition", 11.0)
    motor = PLC_Motor("yAxis", plc, "Y")
    # Drive a fresh read into the cache, then snapshot.
    bus = tag_bus_for(plc)
    bus.read_fresh("Y_axis.ActualPosition", within_ms=50, timeout_ms=500)
    pos = motor.getPosition()
    assert pos == pytest.approx(11.0)


def test_motor_is_functional_default_false_until_polled(plc):
    """Until the bus has seen Z_axis.ModuleFault, the motor reports faulted.

    Matches the legacy `defaultValue=True` for the fault tag.
    """
    from dune_winder.io.devices.tag_bus_registry import tag_bus_for

    motor = PLC_Motor("zAxis", plc, "Z")
    # Before any read, snapshot is Default → assumed faulted.
    assert motor.isFunctional() is False
    # After driving a fetch, the simulator reports not faulted.
    bus = tag_bus_for(plc)
    bus.read_fresh("Z_axis.ModuleFault", within_ms=50, timeout_ms=500)
    assert motor.isFunctional() is True
