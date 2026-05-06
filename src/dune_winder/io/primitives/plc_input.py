###############################################################################
# Name: PLC_Input.py
# Uses: Digital input from a PLC, backed by the TagBus.
###############################################################################

from typing import Any

from dune_winder.io.devices.tag_bus_registry import tag_bus_for
from dune_winder.io.primitives.digital_input import DigitalInput


class PLC_Input(DigitalInput):
    input_instances: list["PLC_Input"] = []

    def __init__(
        self, name, plc, tagName=None, bit=0, defaultState=False, tagType="DINT"
    ):
        """
        Args:
          name: Name of input.
          plc: Legacy PLC subclass *or* a TagBus.
          tagName: PLC tag name. Defaults to `name` when None.
          bit: Bit index inside the tag.
          defaultState: Value returned before the bus has seen the wire.
          tagType: Reserved for the future native driver; ignored here since
            the schema declares the CIP type for each tag.
        """
        DigitalInput.__init__(self, name)
        PLC_Input.input_instances.append(self)

        if tagName is None:
            tagName = name

        self._bus = tag_bus_for(plc)
        self._tagName = tagName
        self._bit = bit
        self._defaultState = bool(defaultState)
        self._tagType = tagType

    def _doGet(self) -> bool:
        snap = self._bus.snapshot(self._tagName)
        if snap is None or snap.source == "default":
            return self._defaultState
        value = snap.value
        if value is None:
            return self._defaultState
        try:
            value = int(value)
        except (TypeError, ValueError):
            return self._defaultState
        return bool((value >> self._bit) & 0x01)

    # Backward-compat shim for any caller that still pokes at `_tag.getName()`.
    @property
    def _tag(self) -> Any:
        bus = self._bus
        name = self._tagName

        class _Ref:
            def getName(self) -> str:
                return name

            def get(self):
                snap = bus.snapshot(name)
                if snap is None or snap.source == "default":
                    return None
                return snap.value

        return _Ref()
