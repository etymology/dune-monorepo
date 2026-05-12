"""Behavior tests for the Camera I/O controller."""

from __future__ import annotations

from dune_winder.io.controllers.camera import Camera
from dune_winder.io.devices.simulated_plc import SimulatedPLC


def _make_camera() -> Camera:
    return Camera(SimulatedPLC())


def test_camera_constructs_with_expected_tags():
    camera = _make_camera()
    # All interface tags expected by the rest of the system are present.
    assert camera.cameraTrigger.getName() == "CAM_F_TRIGGER"
    assert camera.cameraTriggerEnable.getName() == "CAM_F_EN"
    assert camera.cameraDeltaEnable.getName() == "EN_POS_TRIGGERS"
    assert camera.cameraX_Delta.getName() == "X_DELTA"
    assert camera.cameraY_Delta.getName() == "Y_DELTA"
    assert camera.cameraFIFO_Clock.getName() == "READ_FIFOS"
    assert camera.captureFIFO == []


def test_reset_clears_capture_fifo_and_disables_triggers():
    camera = _make_camera()
    camera.captureFIFO.append({"MotorX": 1.0})
    camera.cameraDeltaEnable.set(1)
    camera.cameraTriggerEnable.set(1)

    camera.reset()

    assert camera.captureFIFO == []
    assert camera.cameraDeltaEnable.get() == 0
    assert camera.cameraTriggerEnable.get() == 0


def test_set_manual_trigger_enables_pipeline():
    camera = _make_camera()
    camera.setManualTrigger(True)
    assert camera.cameraTriggerEnable.get() == 1
    assert camera.cameraTrigger.get() is True


def test_start_scan_invokes_callback_with_true_and_records_deltas():
    camera = _make_camera()
    callback_calls: list[bool] = []
    camera.setCallback(lambda enabled: callback_calls.append(enabled))

    camera.startScan(deltaX=2.5, deltaY=0.0)

    assert callback_calls == [True]
    assert camera.cameraTriggerEnable.get() == 1
    assert camera.cameraDeltaEnable.get() == 1
    assert camera.cameraX_Delta.get() == 2.5
    assert camera.cameraY_Delta.get() == 0.0
    assert camera.captureFIFO == []
    assert camera._startingFlush is True


def test_end_scan_invokes_callback_with_false_and_disables_triggers():
    camera = _make_camera()
    callback_calls: list[bool] = []
    camera.setCallback(lambda enabled: callback_calls.append(enabled))

    camera.startScan(deltaX=1.0, deltaY=0.0)
    callback_calls.clear()
    camera.endScan()

    assert callback_calls == [False]
    assert camera.cameraDeltaEnable.get() == 0
    assert camera.cameraTriggerEnable.get() == 0


def test_poll_returns_false_when_fifo_empty():
    camera = _make_camera()
    # SimulatedPLC's default FIFO_Data[2] (Status) starts at 0 → no data.
    assert camera.poll() is False


def test_poll_returns_true_and_records_when_fifo_has_data():
    plc = SimulatedPLC()
    camera = Camera(plc)

    # Inject a non-zero status so poll() observes data on the FIFO.
    plc.write(("FIFO_Data[2]", 1.0), typeName="REAL")
    plc.write(("FIFO_Data[0]", 100.0), typeName="REAL")
    plc.write(("FIFO_Data[1]", 200.0), typeName="REAL")
    plc.write(("FIFO_Data[3]", 0.95), typeName="REAL")
    plc.write(("FIFO_Data[4]", 320.0), typeName="REAL")
    plc.write(("FIFO_Data[5]", 240.0), typeName="REAL")

    assert camera.poll() is True
    assert len(camera.captureFIFO) == 1
    record = camera.captureFIFO[0]
    assert record["MotorX"] == 100.0
    assert record["MotorY"] == 200.0
    assert record["Status"] == 1.0
    assert record["MatchLevel"] == 0.95
    assert record["CameraX"] == 320.0
    assert record["CameraY"] == 240.0
