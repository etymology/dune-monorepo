###############################################################################
# Name: BaseIO.py
# Uses: Base map of I/O used by all hardware with only PLC undefined.
# Date: 2016-04-21
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from dune_winder.io.Types.plc_input import PLC_Input
from dune_winder.io.Types.plc_motor import PLC_Motor

from dune_winder.io.Systems.multi_axis_motor import MultiAxisMotor
from dune_winder.io.Systems.plc_logic import PLC_Logic
from dune_winder.io.Systems.head import Head
from dune_winder.io.Systems.camera import Camera
from dune_winder.io.Devices.plc import PLC


class BaseIO:
  # ---------------------------------------------------------------------
  def isFunctional(self):
    """
    Check to see that all hardware is functional.

    Returns:
      True if all hardware is functional, False for any error.
    """
    result = True
    result &= not self.plc.isNotFunctional()
    result &= self.xAxis.isFunctional()
    result &= self.yAxis.isFunctional()
    result &= self.zAxis.isFunctional()
    result &= not self.plcLogic.isError()

    return result

  # ---------------------------------------------------------------------
  def pollInputs(self):
    """
    Update inputs.  Call periodically.
    """

    # Run each callback in list.
    # (Allows I/O to sign up to have a periodic update callback.)
    for callback in self.pollCallbacks:
      callback()

  # ---------------------------------------------------------------------
  def __init__(self, plc: PLC):
    """
    Constructor.
    """

    # List of callbacks that update I/O.
    self.pollCallbacks = []

    # Use the PLC passed in.
    self.plc = plc

    # Individual axises.
    self.xAxis = PLC_Motor("xAxis", self.plc, "X")
    self.yAxis = PLC_Motor("yAxis", self.plc, "Y")
    self.zAxis = PLC_Motor("zAxis", self.plc, "Z")

    # X/Y treated together.
    self.xyAxis = MultiAxisMotor("xyAxis", [self.xAxis, self.yAxis])

    # PLC logic system, including its polling.
    self.plcLogic = PLC_Logic(self.plc, self.xyAxis, self.zAxis)
    self.pollCallbacks.append(self.plcLogic.poll)
    self.head = Head(self.plcLogic)

    # Camera pin location capture control.
    self.camera = Camera(self.plc)

    #
    # Inputs
    # NOTE: Most of these inputs do not exist on the test hardware fixture.
    #

    # Z-Stage sensors.
    self.Latch_Homed = PLC_Input(
      "Latch_Homed", self.plc, "MACHINE_SW_STAT[0]", 0
    )  # LATCH_ACTUATOR_HOMED
    self.Z_Retracted_1A = PLC_Input(
      "Z_Retracted_1A", self.plc, "MACHINE_SW_STAT[1]", 0
    )  # Z_RETRACTED_1A
    self.Z_Retracted_2B = PLC_Input(
      "Z_Retracted_2B", self.plc, "MACHINE_SW_STAT[2]", 0
    )  # Z_RETRACTED_1B
    self.Z_Retracted_2A = PLC_Input(
      "Z_Retracted_2A", self.plc, "MACHINE_SW_STAT[3]", 0
    )  # Z_RETRACTED_2A
    self.Z_Retracted_2B = PLC_Input(
      "Z_Retracted_2B", self.plc, "MACHINE_SW_STAT[4]", 0
    )  # Z_RETRACTED_2B
    self.Z_Extended = PLC_Input(
      "Z_Extended", self.plc, "MACHINE_SW_STAT[5]", 0
    )  # Z_EXTENDED
    self.Z_Stage_Latched = PLC_Input(
      "Z_Stage_Latched", self.plc, "MACHINE_SW_STAT[6]", 0
    )  # Z_STAGE_LATCHED
    self.Z_Fixed_Latched = PLC_Input(
      "Z_Fixed_Latched", self.plc, "MACHINE_SW_STAT[7]", 0
    )  # Z_FIXED_LATCHED
    self.Z_End_of_Travel = PLC_Input(
      "Z_End_of_Travel", self.plc, "MACHINE_SW_STAT[8]", 0
    )  # Z_EOT
    self.Z_Stage_Present = PLC_Input(
      "Z_Stage_Present", self.plc, "MACHINE_SW_STAT[9]", 0
    )  # Z_STAGE_PRESENT
    self.Z_Fixed_Present = PLC_Input(
      "Z_Fixed_Present", self.plc, "MACHINE_SW_STAT[10]", 0
    )  # Z_FIXED_PRESENT
    self.Z_Spring_Comp = PLC_Input(
      "Z_Spring_Comp", self.plc, "MACHINE_SW_STAT[11]", 0
    )  #
    self.Latch_Actuator_Top = PLC_Input(
      "Latch_Actuator_Top", self.plc, "MACHINE_SW_STAT[12]", 0
    )  # LATCH_ACTUATOR_TOP
    self.Latch_Actuator_Mid = PLC_Input(
      "Latch_Actuator_Mid", self.plc, "MACHINE_SW_STAT[13]", 0
    )  # LATCH_ACTUATOR_MID

    self.X_Park_OK = PLC_Input(
      "X_Park_OK", self.plc, "MACHINE_SW_STAT[14]", 0
    )  # X_PARK_OK
    self.X_Transfer_OK = PLC_Input(
      "X_Transfer_OK", self.plc, "MACHINE_SW_STAT[15]", 0
    )  # X_XFER_OK
    self.Y_Mount_Transfer_OK = PLC_Input(
      "Y_Mount_Transfer_OK", self.plc, "MACHINE_SW_STAT[16]", 0
    )  # Y_MOUNT_XFER_OK
    self.Y_Transfer_OK = PLC_Input(
      "Y_Transfer_OK", self.plc, "MACHINE_SW_STAT[17]", 0
    )  # Y_XFER_OK
    self.endOfTravel_Yp = PLC_Input(
      "endOfTravel_Yp", self.plc, "MACHINE_SW_STAT[18]", 0
    )  # PLUS_Y_EOT
    self.endOfTravel_Ym = PLC_Input(
      "endOfTravel_Ym", self.plc, "MACHINE_SW_STAT[19]", 0
    )  # MINUS_Y_EOT
    self.endOfTravel_Xp = PLC_Input(
      "endOfTravel_Xp", self.plc, "MACHINE_SW_STAT[20]", 0
    )  # PLUS_X_EOT
    self.endOfTravel_Xm = PLC_Input(
      "endOfTravel_Xm", self.plc, "MACHINE_SW_STAT[21]", 0
    )  # MINUS_X_EOT
    self.Rotation_Lock_key = PLC_Input(
      "Rotation_Lock_key", self.plc, "MACHINE_SW_STAT[22]", 0
    )  # ROT_LOCK_KEY
    self.estop = PLC_Input("estop", self.plc, "MACHINE_SW_STAT[23]", 0, False)
    self.park = PLC_Input("park", self.plc, "MACHINE_SW_STAT[24]", 0, False)

    self.Light_Curtain = PLC_Input(
      "Light_Curtain", self.plc, "MACHINE_SW_STAT[25]", 0
    )  # LIGHT_CURTAIN
    self.FrameLockHeadTop = PLC_Input(
      "FrameLockHeadTop", self.plc, "MACHINE_SW_STAT[26]", 0
    )  # FrameLockHeadTop
    self.FrameLockHeadMid = PLC_Input(
      "FrameLockHeadMid", self.plc, "MACHINE_SW_STAT[27]", 0
    )  # FrameLockHeadMid
    self.FrameLockHeadBtm = PLC_Input(
      "FrameLockHeadBtm", self.plc, "MACHINE_SW_STAT[28]", 0
    )  # FrameLockHeadBtm

    self.FrameLockFootTop = PLC_Input(
      "FrameLockFootTop", self.plc, "MACHINE_SW_STAT[29]", 0
    )  # FrameLockFootTop
    self.FrameLockFootMid = PLC_Input(
      "FrameLockFootMid", self.plc, "MACHINE_SW_STAT[30]", 0
    )  # FrameLockFootMid
    self.FrameLockFootBtm = PLC_Input(
      "FrameLockFootBtm", self.plc, "MACHINE_SW_STAT[31]", 0
    )  # FrameLockFootBtm

    self.Gate_Key = PLC_Input("Gate_Key", self.plc, "MORE_STATS_S[0]", 0)  # Gate Key


#    self.Tension_10N         = PLC_Input( "Tension_10N",         self.plc, "MORE_STATS",     2 ) # Tension_10N


# end class
