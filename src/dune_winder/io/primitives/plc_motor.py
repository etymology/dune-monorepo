###############################################################################
# Name: PLC_Motor.py
# Uses: Motor on a PLC, backed by the TagBus.
###############################################################################

import time
from typing import Any, List

from dune_winder.io.devices.tag_bus_registry import tag_bus_for
from dune_winder.io.primitives.motor import Motor

# Reads that gate motion decisions (position, velocity, movement, fault) need a
# fresh value; the bus may have a slightly stale snapshot from its tier poll.
_FRESH_WITHIN_MS = 50
_READ_TIMEOUT_MS = 250


def _snapshot_or(bus: Any, name: str, default):
    snap = bus.snapshot(name)
    if snap is None or snap.source == "default":
        return default
    return snap.value


class _BusReadShim:
    """`.get()` shim over a single bus tag with a typed default."""

    def __init__(self, bus: Any, name: str, default):
        self._bus = bus
        self._name = name
        self._default = default

    def get(self):
        return _snapshot_or(self._bus, self._name, self._default)


class PLC_Motor(Motor):
    instances: List["PLC_Motor"] = []

    def __init__(self, name, plc, tagBase):
        """
        Args:
          name: Name of motor.
          plc: A legacy PLC subclass *or* a TagBus.
          tagBase: All tags will start with this prepended ('X', 'Y', 'Z').
        """
        Motor.__init__(self, name)
        PLC_Motor.instances.append(self)

        self._bus = tag_bus_for(plc)
        self._tagBase = tagBase

        self._target_tag = f"{tagBase}_POSITION"
        self._jog_speed_tag = f"{tagBase}_SPEED"
        self._jog_dir_tag = f"{tagBase}_DIR"
        self._position_tag = f"{tagBase}_axis.ActualPosition"
        self._velocity_tag = f"{tagBase}_axis.ActualVelocity"
        self._acceleration_tag = f"{tagBase}_axis.CommandAcceleration"
        self._movement_tag = f"{tagBase}_axis.CoordinatedMotionStatus"
        self._faulted_tag = f"{tagBase}_axis.ModuleFault"

        self._seekStartPosition = 0

        # `.get()`-shaped shim for legacy callers (e.g. Head) that read the
        # axis position via the tag handle rather than `getPosition()`.
        self._position = _BusReadShim(self._bus, self._position_tag, 0.0)

    # ---------------------------------------------------------------------
    def isFunctional(self):
        # Default to faulted (matches the legacy `defaultValue=True` for the
        # fault tag) until we've actually seen the wire.
        faulted = _snapshot_or(self._bus, self._faulted_tag, True)
        return not bool(faulted)

    # ---------------------------------------------------------------------
    def setDesiredPosition(self, position):
        self._seekStartPosition = self.getPosition()
        self._bus.write(self._target_tag, float(position))

    # ---------------------------------------------------------------------
    def getSeekStartPosition(self):
        return self._seekStartPosition

    # ---------------------------------------------------------------------
    def getDesiredPosition(self):
        return _snapshot_or(self._bus, self._target_tag, 0.0)

    # ---------------------------------------------------------------------
    def isSeeking(self):
        return bool(_snapshot_or(self._bus, self._movement_tag, False))

    # ---------------------------------------------------------------------
    def setEnable(self, isEnabled):
        pass

    # ---------------------------------------------------------------------
    def seekWait(self):
        while self.isSeeking():
            time.sleep(0.01)

    # ---------------------------------------------------------------------
    def getPosition(self):
        return _snapshot_or(self._bus, self._position_tag, 0.0)

    # ---------------------------------------------------------------------
    def setMaxVelocity(self, maxVelocity):
        self._bus.write(self._jog_speed_tag, float(maxVelocity))

    # ---------------------------------------------------------------------
    def getMaxVelocity(self):
        return None

    # ---------------------------------------------------------------------
    def getVelocity(self):
        return _snapshot_or(self._bus, self._velocity_tag, 0.0)

    # ---------------------------------------------------------------------
    def setVelocity(self, velocity):
        direction = 0
        if velocity < 0:
            direction = 1
            velocity = -velocity

        self._bus.write(self._jog_speed_tag, float(velocity))
        self._bus.write(self._jog_dir_tag, int(direction))

    # ---------------------------------------------------------------------
    def setMaxAcceleration(self, maxAcceleration):
        pass

    # ---------------------------------------------------------------------
    def getMaxAcceleration(self):
        pass

    # ---------------------------------------------------------------------
    def getAcceleration(self):
        return _snapshot_or(self._bus, self._acceleration_tag, 0.0)

    # ---------------------------------------------------------------------
    def poll(self):
        # Bus owns its own poll thread; nothing to do here.
        pass
