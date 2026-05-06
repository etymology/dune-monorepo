###############################################################################
# Name: PLC_Logic.py
# Uses: Interface for PLC ladder dispatch, backed by the TagBus.
###############################################################################

from typing import Any

from dune_winder.io.devices.tag_bus_registry import tag_bus_for
from dune_winder.io.primitives.multi_axis_motor import MultiAxisMotor
from dune_winder.io.primitives.plc_motor import PLC_Motor
from dune_winder.queued_motion.plc_interface import QueuedMotionPLCInterface


_FRESH_MS = 50
_TIMEOUT_MS = 250

# RESULT outcome codes published by the PLC handshake.
_RESULT_IDLE = 0
_RESULT_ACCEPTED = 1
_RESULT_REJECTED = 2
_RESULT_COMPLETED = 3
_RESULT_FAULTED = 4

# STATE_FAULT_FLAGS bit definitions. Mirrors the ladder.
FAULT_INTERLOCK = 0x01
FAULT_AXIS = 0x02
FAULT_EOT = 0x04
FAULT_SAFETY = 0x08
FAULT_TENSION = 0x10
FAULT_LATCH_TIMEOUT = 0x20
FAULT_REQUEST_OUT_OF_RANGE = 0x40


def _value_or(snap: Any, default):
    if snap is None or snap.source == "default":
        return default
    return snap.value


class _MachineSwStatBit:
    """`.get()` shim returning bit `bit_index` of `MACHINE_SW_STAT[slot]`.

    The legacy ladder publishes one boolean per slot in bit 0; we keep the
    bit index parametric to match `PLC_Input`'s contract.
    """

    def __init__(self, bus, slot: int, bit: int = 0):
        self._bus = bus
        self._tag = f"MACHINE_SW_STAT[{slot}]"
        self._bit = bit

    def get(self) -> bool:
        snap = self._bus.snapshot(self._tag)
        if snap is None or snap.source == "default":
            return False
        try:
            return bool((int(snap.value) >> self._bit) & 0x01)
        except (TypeError, ValueError):
            return False


class _BusGetShim:
    """`.get()` shim over a single bus tag with a typed default."""

    def __init__(self, bus, name: str, default):
        self._bus = bus
        self._name = name
        self._default = default

    def get(self):
        snap = self._bus.snapshot(self._name)
        if snap is None or snap.source == "default":
            return self._default
        return snap.value


class PLC_Logic:
    class States:
        INIT = 0
        READY = 1
        XY_JOG = 2
        XY_SEEK = 3
        Z_JOG = 4
        Z_SEEK = 5
        LATCHING = 6
        LATCH_HOMEING = 7
        LATCH_RELEASE = 8
        UNSERVO = 9
        ERROR = 10
        EOT = 11
        XZ_SEEK = 12
        YZ_SEEK = 13
        HMI_STOP = 14

    _DIRECT_STATE_REQUESTS = {
        States.XY_SEEK,
        States.Z_SEEK,
        States.LATCHING,
        States.UNSERVO,
        States.EOT,
        States.XZ_SEEK,
        States.YZ_SEEK,
        States.HMI_STOP,
    }

    class MoveTypes:
        RESET = 0
        JOG_XY = 1
        SEEK_XY = 2
        JOG_Z = 3
        SEEK_Z = 4
        LATCH = 5
        HOME_LATCH = 6
        LATCH_UNLOCK = 7
        UNSERVO = 8
        PLC_INIT = 9
        SEEK_XZ = 10
        HMI_STOP_REQUEST = 11

    class LatchPosition:
        FULL_UP = 0
        PARTIAL_UP = 1
        DOWN = 2

    ERROR_CODES = {
        0: "None",
        1001: "Rotation lock missing",
        2001: "XY Jog, Z is extended",
        2002: "Physical X or Y axis fault",
        3001: "XY Seek, Z is extended",
        3002: "Physical X or Y axis fault",
        3003: "Motion complete, but position is incorrect",
        3004: "Emergency stop - STO active",
        4001: "Z Jog, Master Z Transfer Enable Not Ready",
        4002: "Physical Z axis fault",
        4003: "Latch not in position 2 when retrieving winder head",
        5001: "Z Seek, Master Z Transfer Enable Not Ready",
        5002: "Physical Z axis fault",
        5003: "Motion complete, but position is incorrect",
        5004: "Latch not in position 2 when retrieving winder head",
        6000: "Latching State Successful",
        6001: "Latching State, Z Stage not present OR Z Fixed not Present OR Z Not Extended",
        6002: "Latching State, Latch did not move to next position",
        7000: "Homing Latch State Successful",
        7001: "Homing Latch State, Z Stage Not Present",
        7002: "Homing Latch State, Latch did not move to home position",
        8000: "Unlock Latch Motor Successful",
        8001: "Wire broke",
        8002: "Wire over-tensioned",
    }

    def __init__(self, plc, xyAxis: MultiAxisMotor, zAxis: PLC_Motor):
        """
        Args:
          plc: A legacy PLC subclass *or* a TagBus.
          xyAxis: Coordinated X/Y motor.
          zAxis: Z motor.
        """
        self._plc = plc  # kept for QueuedMotionPLCInterface
        self._bus = tag_bus_for(plc)
        self._xyAxis = xyAxis
        self._zAxis = zAxis
        self._latchPosition = 0
        self._velocity = 0.0
        self._maxAcceleration = 0
        self._maxDeceleration = 0
        self._lastIssuedRequestId = 0
        self.queuedMotion = QueuedMotionPLCInterface(plc)
        # Bit-extracting `.get()` shims over MACHINE_SW_STAT slots that the
        # legacy ladder publishes one-bit-per-DINT. Head reads these directly.
        self._zStageLatchedBit = _MachineSwStatBit(self._bus, 6)
        self._zFixedLatchedBit = _MachineSwStatBit(self._bus, 7)
        self._zStagePresentBit = _MachineSwStatBit(self._bus, 9)
        self._zFixedPresentBit = _MachineSwStatBit(self._bus, 10)
        self._actuatorPosition = _BusGetShim(self._bus, "ACTUATOR_POS", 0)

    # ---------------------------------------------------------------------
    # State queries
    # ---------------------------------------------------------------------
    def isReady(self) -> bool:
        # Prefer the handshake RESULT once we've actually issued a request and
        # the PLC has acknowledged. Until then (or against transitional
        # firmware that hasn't yet wired the new tags), fall back to the legacy
        # `STATE == READY ∧ STATE_REQUEST == 0` check.
        ack = int(_value_or(self._bus.snapshot("STATE_REQUEST_ACK"), 0))
        state = int(_value_or(self._bus.snapshot("STATE"), 0))
        if self._lastIssuedRequestId > 0 and ack == self._lastIssuedRequestId:
            result = int(_value_or(self._bus.snapshot("STATE_REQUEST_RESULT"), 0))
            return (
                result in (_RESULT_IDLE, _RESULT_COMPLETED)
                and state == self.States.READY
            )
        req = int(_value_or(self._bus.snapshot("STATE_REQUEST"), 0))
        return state == self.States.READY and req == 0

    # ---------------------------------------------------------------------
    # Handshake diagnostics. Public so Head._updateG206 and ControlStateMachine
    # can detect transient ERROR bounces and rejected requests.
    # ---------------------------------------------------------------------
    def getStateRequestResult(self) -> int:
        return int(_value_or(self._bus.snapshot("STATE_REQUEST_RESULT"), 0))

    def getStateFaultFlags(self) -> int:
        return int(_value_or(self._bus.snapshot("STATE_FAULT_FLAGS"), 0))

    def getStateEntryCounter(self) -> int:
        return int(_value_or(self._bus.snapshot("STATE_ENTRY_COUNTER"), 0))

    def getLastState(self) -> int:
        return int(_value_or(self._bus.snapshot("LAST_STATE"), 0))

    def getStateRequestAck(self) -> int:
        return int(_value_or(self._bus.snapshot("STATE_REQUEST_ACK"), 0))

    def getLastRequestId(self) -> int:
        return self._lastIssuedRequestId

    def isError(self) -> bool:
        return _value_or(self._bus.snapshot("STATE"), 0) == self.States.ERROR

    def getState(self):
        snap = self._bus.read_fresh("STATE", _FRESH_MS, _TIMEOUT_MS)
        return snap.value

    def getMoveType(self):
        return _value_or(self._bus.snapshot("MOVE_TYPE"), 0)

    def getStateRequest(self):
        return _value_or(self._bus.snapshot("STATE_REQUEST"), 0)

    # ---------------------------------------------------------------------
    # State requests
    # ---------------------------------------------------------------------
    def stopSeek(self):
        self._requestState(self.States.HMI_STOP)

    def recoverEOT(self):
        self._requestState(self.States.EOT)

    def servoDisable(self):
        self._requestState(self.States.UNSERVO)

    def _requestState(self, state):
        requested = int(state)
        if requested not in self._DIRECT_STATE_REQUESTS:
            raise ValueError("Unsupported STATE_REQUEST target: " + str(requested))
        # Bump the handshake ID so the ladder can correlate ACK/RESULT to this
        # specific request. Writes go out as separate bus calls; the simulator
        # and ladder both tolerate either order because the ID write only
        # rearms ACK/RESULT/FLAGS — dispatch fires on the STATE_REQUEST write.
        self._lastIssuedRequestId += 1
        self._bus.write("STATE_REQUEST_ID", self._lastIssuedRequestId)
        self._bus.write("STATE_REQUEST", requested)

    def _pulseMoveType(self, moveType):
        # The PLC READY-state ladder uses one-shots on `MOVE_TYPE = N`; pulsing
        # through RESET guarantees a fresh false→true transition.
        self._bus.write("MOVE_TYPE", int(self.MoveTypes.RESET))
        self._bus.write("MOVE_TYPE", int(moveType))

    # ---------------------------------------------------------------------
    # Motion commands
    # ---------------------------------------------------------------------
    def setXY_Position(self, x, y, velocity=None, acceleration=None, deceleration=None):
        if velocity is not None:
            self._velocity = velocity
        if acceleration is not None:
            self._bus.write("XY_ACCELERATION", float(acceleration))
        if deceleration is not None:
            self._bus.write("XY_DECELERATION", float(deceleration))
        self._bus.write("XY_SPEED", float(self._velocity))
        self._xyAxis.setDesiredPosition([x, y])
        self._requestState(self.States.XY_SEEK)

    def jogXY(self, xVelocity, yVelocity, acceleration=None, deceleration=None):
        if acceleration is not None:
            self._bus.write("XY_ACCELERATION", float(acceleration))
        if deceleration is not None:
            self._bus.write("XY_DECELERATION", float(deceleration))
        self._xyAxis.setVelocity([xVelocity, yVelocity])
        self._bus.write("MOVE_TYPE", int(self.MoveTypes.JOG_XY))

    def setZ_Position(self, position, velocity=None):
        if velocity is not None:
            self._velocity = velocity
        self._zAxis.setVelocity(self._velocity)
        self._zAxis.setDesiredPosition(position)
        self._requestState(self.States.Z_SEEK)

    def setXZ_Position(self, x, z, velocity=None):
        del velocity
        snap = self._bus.read_fresh("Y_XFER_OK", _FRESH_MS, _TIMEOUT_MS)
        if not bool(snap.value):
            raise ValueError("Y_Transfer_OK must be true before issuing an XZ move.")
        self._bus.write("xz_position_target", [float(x), float(z)])
        self._requestState(self.States.XZ_SEEK)

    def setYZ_Position(self, y, z, velocity=None):
        del velocity
        snap = self._bus.read_fresh("X_XFER_OK", _FRESH_MS, _TIMEOUT_MS)
        if not bool(snap.value):
            raise ValueError("X_Transfer_OK must be true before issuing a YZ move.")
        self._bus.write("yz_position_target", [float(y), float(z)])
        self._requestState(self.States.YZ_SEEK)

    def jogZ(self, velocity):
        self._zAxis.setVelocity(velocity)
        self._pulseMoveType(self.MoveTypes.JOG_Z)

    # ---------------------------------------------------------------------
    # Latch / transfer
    # ---------------------------------------------------------------------
    def getLatchPosition(self):
        return _value_or(self._bus.snapshot("ACTUATOR_POS"), 0)

    def getHeadPosition(self):
        return _value_or(self._bus.snapshot("ACTUATOR_POS"), 0)

    def canMoveLatch(self) -> bool:
        snap = self._bus.read_fresh("ENABLE_ACTUATOR", _FRESH_MS, _TIMEOUT_MS)
        return bool(snap.value)

    def move_latch(self) -> bool:
        if not self.canMoveLatch():
            return False
        self._requestState(self.States.LATCHING)
        return True

    def getTransferStateNow(self) -> dict:
        names = [
            "MACHINE_SW_STAT[9]",  # stagePresent
            "MACHINE_SW_STAT[10]",  # fixedPresent
            "MACHINE_SW_STAT[6]",  # stageLatched
            "MACHINE_SW_STAT[7]",  # fixedLatched
            "MACHINE_SW_STAT[5]",  # zExtended
            "ENABLE_ACTUATOR",
            "ACTUATOR_POS",
            "Z_axis.ActualPosition",
        ]
        snapshots = self._bus.read_many_fresh(names)
        values: dict[str, Any] = {}
        for name in names:
            snap = snapshots.get(name)
            values[name] = snap.value if snap is not None else 0
        return {
            "stagePresent": bool(values["MACHINE_SW_STAT[9]"]),
            "fixedPresent": bool(values["MACHINE_SW_STAT[10]"]),
            "stageLatched": bool(values["MACHINE_SW_STAT[6]"]),
            "fixedLatched": bool(values["MACHINE_SW_STAT[7]"]),
            "zExtended": bool(values["MACHINE_SW_STAT[5]"]),
            "enableActuator": bool(values["ENABLE_ACTUATOR"]),
            "actuatorPos": int(values["ACTUATOR_POS"]),
            "zPosition": float(values["Z_axis.ActualPosition"]),
        }

    # ---------------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------------
    def reset(self):
        self._bus.write("ERROR_CODE", 0)
        self._bus.write("STATE_REQUEST", 0)

    def PLC_init(self):
        self._bus.write("MOVE_TYPE", int(self.MoveTypes.PLC_INIT))

    def latchHome(self):
        raise NotImplementedError(
            "Latch home is not supported by the checked-in PLC STATE_REQUEST contract."
        )

    def latchUnlock(self):
        raise NotImplementedError(
            "Latch unlock is not supported by the checked-in PLC STATE_REQUEST contract."
        )

    def poll(self):
        # Bus owns its own poll thread; nothing to do here.
        pass

    # ---------------------------------------------------------------------
    # Limits
    # ---------------------------------------------------------------------
    def maxVelocity(self, maxVelocity=None):
        if maxVelocity is not None:
            self._velocity = maxVelocity
        self._bus.write("XY_SPEED", float(self._velocity))
        return self._velocity

    def maxAcceleration(self, maxAcceleration=None):
        if maxAcceleration is not None:
            self._maxAcceleration = maxAcceleration
        self._bus.write("XY_ACCELERATION", float(self._maxAcceleration))
        self._bus.write("Z_ACCELERATION", float(self._maxAcceleration))
        return self._maxAcceleration

    def maxDeceleration(self, maxDeceleration=None):
        if maxDeceleration is not None:
            self._maxDeceleration = maxDeceleration
        self._bus.write("XY_DECELERATION", float(self._maxDeceleration))
        self._bus.write("Z_DECELLERATION", float(self._maxDeceleration))
        return self._maxDeceleration

    def setupLimits(self, maxVelocity=None, maxAcceleration=None, maxDeceleration=None):
        if maxVelocity is not None:
            self._velocity = maxVelocity
        if maxAcceleration is not None:
            self._maxAcceleration = maxAcceleration
        if maxDeceleration is not None:
            self._maxDeceleration = maxDeceleration
        self._bus.write("XY_SPEED", float(self._velocity))
        self._bus.write("XY_ACCELERATION", float(self._maxAcceleration))
        self._bus.write("XY_DECELERATION", float(self._maxDeceleration))
        self._bus.write("Z_ACCELERATION", float(self._maxAcceleration))
        self._bus.write("Z_DECELLERATION", float(self._maxDeceleration))

    # ---------------------------------------------------------------------
    # Errors
    # ---------------------------------------------------------------------
    # Mapping from (state_we_left, fault_flag_bit) → legacy ERROR_CODE. Lets
    # us reconstruct the operator-facing string from the new bitfield without
    # rewriting the ERROR_CODES dict. Falls back to the raw ERROR_CODE tag
    # when the handshake tags are zero (transitional firmware).
    _FAULT_TO_LEGACY_CODE = {
        (States.XY_SEEK, FAULT_INTERLOCK): 3001,
        (States.XY_SEEK, FAULT_AXIS): 3002,
        (States.Z_SEEK, FAULT_INTERLOCK): 5001,
        (States.Z_SEEK, FAULT_AXIS): 5002,
        (States.XZ_SEEK, FAULT_INTERLOCK): 5001,
        (States.YZ_SEEK, FAULT_INTERLOCK): 5001,
        (States.LATCHING, FAULT_INTERLOCK): 6001,
        (States.LATCHING, FAULT_LATCH_TIMEOUT): 6002,
    }

    def getErrorCode(self):
        flags = int(_value_or(self._bus.snapshot("STATE_FAULT_FLAGS"), 0))
        if flags:
            lastState = int(_value_or(self._bus.snapshot("LAST_STATE"), 0))
            for bit in (
                FAULT_INTERLOCK,
                FAULT_AXIS,
                FAULT_EOT,
                FAULT_SAFETY,
                FAULT_TENSION,
                FAULT_LATCH_TIMEOUT,
                FAULT_REQUEST_OUT_OF_RANGE,
            ):
                if flags & bit:
                    code = self._FAULT_TO_LEGACY_CODE.get((lastState, bit))
                    if code is not None:
                        return code
        return _value_or(self._bus.snapshot("ERROR_CODE"), 0)

    def getErrorCodeString(self) -> str:
        code = self.getErrorCode()
        return self.ERROR_CODES.get(code, "Unknown " + str(code))
