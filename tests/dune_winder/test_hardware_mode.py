"""Behavior tests for HardwareMode — the root state that manages PLC bring-up."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from dune_winder.core.hardware_mode import HardwareMode
from dune_winder.library.state_machine import StateMachine


# Sentinel state ids used by the fake parent state machine.
_HARDWARE_STATE = 0
_STOP_STATE = 1


def _make_io(
    *,
    plc_not_functional: bool = False,
    plc_logic_error: bool = False,
    error_code: int = 0,
    error_string: str = "OK",
    x_ok: bool = True,
    y_ok: bool = True,
    z_ok: bool = True,
    fully_functional: bool = True,
):
    plc = MagicMock()
    plc.isNotFunctional.return_value = plc_not_functional
    plc.initialize = MagicMock()

    plc_logic = MagicMock()
    plc_logic.isError.return_value = plc_logic_error
    plc_logic.getErrorCode.return_value = error_code
    plc_logic.getErrorCodeString.return_value = error_string
    plc_logic.setupLimits = MagicMock()

    return SimpleNamespace(
        plc=plc,
        plcLogic=plc_logic,
        xAxis=MagicMock(isFunctional=lambda: x_ok),
        yAxis=MagicMock(isFunctional=lambda: y_ok),
        zAxis=MagicMock(isFunctional=lambda: z_ok),
        isFunctional=lambda: fully_functional,
    )


def _make_state_machine_with_stop_target() -> StateMachine:
    sm = StateMachine(name="HardwareModeTests")
    # update() may try to changeState to STOP — install a no-op state so
    # the transition succeeds without invoking real Stop logic.
    stop_state = MagicMock()
    stop_state.enter.return_value = False
    stop_state.exit.return_value = False
    sm.states[_STOP_STATE] = stop_state
    sm.States = SimpleNamespace(STOP=_STOP_STATE)
    return sm


def test_hardware_mode_initial_flags_are_set():
    sm = _make_state_machine_with_stop_target()
    log = MagicMock()
    io = _make_io()

    mode = HardwareMode(sm, _HARDWARE_STATE, io, log)

    assert mode.isPLC_Working is True
    assert mode.isStateClear is True
    assert mode.isX_AxisWorking is True
    assert mode.isY_AxisWorking is True
    assert mode.isZ_AxisWorking is True


def test_enter_logs_error_when_plc_logic_reports_error():
    sm = _make_state_machine_with_stop_target()
    log = MagicMock()
    io = _make_io(plc_logic_error=True, error_code=42, error_string="LIMIT")

    mode = HardwareMode(sm, _HARDWARE_STATE, io, log)
    assert mode.enter() is False  # never returns True
    log.add.assert_called_once()
    args = log.add.call_args[0]
    assert args[1] == "HARD_ERROR"
    assert "LIMIT" in args[2]
    assert "42" in args[2]


def test_enter_does_not_log_when_plc_clear():
    sm = _make_state_machine_with_stop_target()
    log = MagicMock()
    io = _make_io()
    mode = HardwareMode(sm, _HARDWARE_STATE, io, log)
    mode.enter()
    log.add.assert_not_called()


def test_exit_calls_setup_limits():
    sm = _make_state_machine_with_stop_target()
    log = MagicMock()
    io = _make_io()
    mode = HardwareMode(sm, _HARDWARE_STATE, io, log)
    assert mode.exit() is False
    io.plcLogic.setupLimits.assert_called_once()


def test_update_initializes_plc_when_not_functional_and_logs_first_failure():
    sm = _make_state_machine_with_stop_target()
    log = MagicMock()
    io = _make_io(plc_not_functional=True, fully_functional=False)
    mode = HardwareMode(sm, _HARDWARE_STATE, io, log)

    mode.update()

    io.plc.initialize.assert_called_once()
    assert mode.isPLC_Working is False
    log.add.assert_called_with(
        "HardwareMode", "HARD_ERROR", "Unable to communicate to PLC"
    )


def test_update_does_not_relog_plc_failure_on_subsequent_calls():
    sm = _make_state_machine_with_stop_target()
    log = MagicMock()
    io = _make_io(plc_not_functional=True, fully_functional=False)
    mode = HardwareMode(sm, _HARDWARE_STATE, io, log)

    mode.update()
    mode.update()

    # Only one HARD_ERROR for the PLC failure across two updates.
    plc_failure_calls = [
        call
        for call in log.add.call_args_list
        if call[0][2] == "Unable to communicate to PLC"
    ]
    assert len(plc_failure_calls) == 1


def test_update_logs_recovery_when_plc_returns():
    sm = _make_state_machine_with_stop_target()
    log = MagicMock()
    io = _make_io(plc_not_functional=True, fully_functional=False)
    mode = HardwareMode(sm, _HARDWARE_STATE, io, log)
    mode.update()  # first failure
    log.reset_mock()

    # PLC comes back online but full functionality still pending.
    io.plc.isNotFunctional.return_value = False
    io.isFunctional = lambda: False
    mode.update()

    recovery_calls = [
        call
        for call in log.add.call_args_list
        if "Communications to PLC established." in call[0][2]
    ]
    assert recovery_calls
    assert mode.isPLC_Working is True


def test_update_logs_axis_fault_then_clear():
    sm = _make_state_machine_with_stop_target()
    log = MagicMock()
    io = _make_io(x_ok=False, fully_functional=False)
    mode = HardwareMode(sm, _HARDWARE_STATE, io, log)

    mode.update()
    assert mode.isX_AxisWorking is False
    fault_messages = [c[0][2] for c in log.add.call_args_list]
    assert "Fault on x-axis." in fault_messages

    log.reset_mock()
    io.xAxis.isFunctional = lambda: True
    mode.update()
    cleared = [c[0][2] for c in log.add.call_args_list]
    assert "X-axis fault clear." in cleared
    assert mode.isX_AxisWorking is True


def test_update_transitions_to_stop_when_fully_functional():
    sm = _make_state_machine_with_stop_target()
    log = MagicMock()
    io = _make_io(fully_functional=True)
    mode = HardwareMode(sm, _HARDWARE_STATE, io, log)

    mode.update()

    # Stop state's enter() must have been invoked.
    sm.states[_STOP_STATE].enter.assert_called_once()
