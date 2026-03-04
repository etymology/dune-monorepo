###############################################################################
# Name: Camera.py
# Uses: Interface to vision system.
# Date: 2016-12-16
# Author(s):
#   Andrew Que <aque@bb7.com>
# NOTES:
#   Uses Cognex camera and custom PLC trigger/capture setup.  The PLC provides
# two interfaces for using the camera.  The first is a method to setup camera
# triggering at regular intervals in X/Y.  The second is a FIFO that
# accumulates capture data.  These two systems must be implemented in the PLC
# for maximum speed.
###############################################################################
from dune_winder.io.Devices.PLC import PLC


class Camera:
  # The dimensions of a captured frame from the camera.
  FRAME_WIDTH = 640
  FRAME_HEIGHT = 480

  # ---------------------------------------------------------------------
  def __init__(self, plc):
    """
    Constructor.

    Args:
      plcLogic: Instance of PLC_Logic.
    """

    # PLC tags for pin capture.
    self.cameraTrigger = PLC.Tag(plc, "CAM_F_TRIGGER", tagType="BOOL")
    self.cameraTriggerEnable = PLC.Tag(plc, "CAM_F_EN", tagType="BOOL")

    self.cameraDeltaEnable = PLC.Tag(plc, "EN_POS_TRIGGERS", tagType="BOOL")
    self.cameraX_Delta = PLC.Tag(plc, "X_DELTA", tagType="REAL")
    self.cameraY_Delta = PLC.Tag(plc, "Y_DELTA", tagType="REAL")

    self.cameraFIFO_MotorX = PLC.Tag(plc, "FIFO_Data[0]", tagType="REAL")
    self.cameraFIFO_MotorY = PLC.Tag(plc, "FIFO_Data[1]", tagType="REAL")
    self.cameraFIFO_Status = PLC.Tag(plc, "FIFO_Data[2]", tagType="REAL")
    self.cameraFIFO_MatchLevel = PLC.Tag(plc, "FIFO_Data[3]", tagType="REAL")
    self.cameraFIFO_CameraX = PLC.Tag(plc, "FIFO_Data[4]", tagType="REAL")
    self.cameraFIFO_CameraY = PLC.Tag(plc, "FIFO_Data[5]", tagType="REAL")
    self.cameraFIFO_Clock = PLC.Tag(plc, "READ_FIFOS", tagType="BOOL")

    # Direct to camera tags.
    # attributes = PLC.Tag.Attributes()
    # attributes.isPolled = True
    # self.cameraResultStatus = PLC.Tag( plc, "Cam_F:I.InspectionResults[0]", attributes, tagType="REAL" )
    # self.cameraResultScore  = PLC.Tag( plc, "Cam_F:I.InspectionResults[1]", attributes, tagType="REAL" )
    # self.cameraResultX      = PLC.Tag( plc, "Cam_F:I.InspectionResults[2]", attributes, tagType="REAL" )
    # self.cameraResultY      = PLC.Tag( plc, "Cam_F:I.InspectionResults[3]", attributes, tagType="REAL" )

    # Data from camera FIFO.
    self.captureFIFO = []

    # Callback to run during enable/disabling of triggering.
    self._callback = None

    self._startingFlush = True

  # ---------------------------------------------------------------------
  def setCallback(self, callback):
    """
    Set a callback to run during enable/disabling of triggering.

    Args:
      callback: The callback to run.

    Notes:
      Callback is passed a single parameter, True if trigger was being enabled,
      False if trigger is being disabled.
    """

    self._callback = callback

  # ---------------------------------------------------------------------
  def poll(self):
    """
    Update FIFO registers.
    Call periodically after a trigger has been setup.

    Returns:
      True if there was data in the FIFO, False if FIFO was empty.
    """

    # Clock FIFO.
    self.cameraFIFO_Clock.set(1)

    # Any data in FIFO?
    self.cameraFIFO_Status.poll()

    isData = False
    if self.cameraFIFO_Status.get() > 0:
      isData = True

      # Update remaining FIFO values.
      # $$$FUTURE - Do a block read.
      self.cameraFIFO_MotorX.poll()
      self.cameraFIFO_MotorY.poll()
      self.cameraFIFO_MatchLevel.poll()
      self.cameraFIFO_CameraX.poll()
      self.cameraFIFO_CameraY.poll()

      # Place all FIFO values in capture FIFO.
      self.captureFIFO.append(
        {
          "MotorX": self.cameraFIFO_MotorX.get(),
          "MotorY": self.cameraFIFO_MotorY.get(),
          "Status": self.cameraFIFO_Status.get(),
          "MatchLevel": self.cameraFIFO_MatchLevel.get(),
          "CameraX": self.cameraFIFO_CameraX.get(),
          "CameraY": self.cameraFIFO_CameraY.get(),
        }
      )

    return isData

  # ---------------------------------------------------------------------
  def reset(self):
    """
    Reset all scan results.
    """
    self.captureFIFO = []
    self.cameraDeltaEnable.set(0)
    self.cameraTriggerEnable.set(0)

  # ---------------------------------------------------------------------
  def setManualTrigger(self, isEnabled):
    """
    Start/stop manual triggering.

    Args:
      isEnabled: True to enable manual triggering, False to stop.

    Notes:
      The PLC logic will continuously trigger the camera at regular periods
      when enabled.
    """
    self.cameraTriggerEnable.set(1)
    self.cameraTrigger.set(isEnabled)

  # ---------------------------------------------------------------------
  def startScan(self, deltaX, deltaY):
    """
    Begin a pin scan.
    Call stopped before any motion begins.

    Args:
      deltaX: Distance in X to trigger camera.
      deltaY: Distance in Y to trigger camera.

    Notes:
      Typically either deltaX or deltaY is 0 with one one delta being used
      for a scan.  Deltas account for direction by being positive or negative.
    """

    # Flush capture FIFO.
    self.captureFIFO = []

    self.cameraTriggerEnable.set(1)
    self.cameraX_Delta.set(deltaX)
    self.cameraY_Delta.set(deltaY)
    self.cameraDeltaEnable.set(1)

    self._startingFlush = True

    if self._callback:
      self._callback(True)

  # ---------------------------------------------------------------------
  def endScan(self):
    """
    Finish a pin scan.
    Disables PLC camera trigger logic.
    """
    self.cameraDeltaEnable.set(0)
    self.cameraTriggerEnable.set(0)

    if self._callback:
      self._callback(False)
