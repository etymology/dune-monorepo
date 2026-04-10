# Monoroutine Import Notes

This export assumes the controller-level tags and hardware configuration already exist on the PLC.
Only the Monoroutine program-scoped tags need to be created/imported alongside the routine text.

## Included Scan Order

1. `Safety/main`
2. `MainProgram/main`
3. `PID_Tension_Servo/main`
4. `Initialize/main`
5. `Ready_State_1/main`
6. `MoveXY_State_2_3/main`
7. `MoveZ_State_4_5/main`
8. `Latch_UnLatch_State_6_7_8/main`
9. `UnServo_9/main`
10. `Error_State_10/main`
11. `EOT_Trip_11/main`
12. `xz_move/main`
13. `yz_move/main`
14. `HMI_Stop_Request_14/main`
15. `motionQueue/main`

## Omitted Or Flattened

- `Camera/main` is empty and was omitted.
- `MoveXY_State_2_3/xy_speed_regulator` was flattened into `MoveXY_State_2_3/main`.
- `motionQueue` helper routines were flattened into `motionQueue/main`.
- `motionQueue/CircleCenterForSeg` was not emitted separately because the checked-in routine is a no-op.

## Renamed Routine-Level Tags

### PID_Tension_Servo

- `oneshotob` -> `PTS_oneshotob`
- `oneshotsb` -> `PTS_oneshotsb`

### Initialize

- `OutBit` -> `INIT_OutBit`
- `SetBit` -> `INIT_SetBit`
- `Z_AXIS_STAT` -> `INIT_Z_AXIS_STAT`

### Ready_State_1

- `OutBit` -> `RS1_OutBit`
- `SetBit` -> `RS1_SetBit`

### MoveXY_State_2_3

- `IssueNextPulse` -> `MXY_IssueNextPulse`
- `X_AXIS_STAT` -> `MXY_X_AXIS_STAT`
- `Y_AXIS_STAT` -> `MXY_Y_AXIS_STAT`
- `eot_triggered` -> `MXY_eot_triggered`
- `oneshotob` -> `MXY_oneshotob`
- `oneshotsb` -> `MXY_oneshotsb`
- `prepare_to_move` -> `MXY_prepare_to_move`
- `wait_for_axes_mso` -> `MXY_wait_for_axes_mso`
- `x_axis_mso` -> `MXY_x_axis_mso`
- `y_axis_mso` -> `MXY_y_axis_mso`

### MoveZ_State_4_5

- `oneshotob` -> `MZ_oneshotob`
- `oneshotsb` -> `MZ_oneshotsb`
- `prepare_to_move` -> `MZ_prepare_to_move`
- `wait_for_axes_mso` -> `MZ_wait_for_axes_mso`

### Latch_UnLatch_State_6_7_8

- `oneshotob` -> `LAT_oneshotob`
- `oneshotsb` -> `LAT_oneshotsb`

### UnServo_9

- `X_AXIS_STAT` -> `US9_X_AXIS_STAT`
- `Y_AXIS_STAT` -> `US9_Y_AXIS_STAT`
- `Z_AXIS_STAT` -> `US9_Z_AXIS_STAT`
- `oneshotob` -> `US9_oneshotob`
- `oneshotsb` -> `US9_oneshotsb`

### Error_State_10

- `X_AXIS_STAT` -> `ERR10_X_AXIS_STAT`
- `Y_AXIS_STAT` -> `ERR10_Y_AXIS_STAT`
- `Z_AXIS_STAT` -> `ERR10_Z_AXIS_STAT`
- `oneshotob` -> `ERR10_oneshotob`
- `oneshotsb` -> `ERR10_oneshotsb`

### EOT_Trip_11

- `oneshotob` -> `EOT11_oneshotob`
- `oneshotsb` -> `EOT11_oneshotsb`

### xz_move

- `xy_stop` -> `XZ_xy_stop`

### yz_move

- `STATE13_IND` -> `YZ_STATE13_IND`
- `xy_stop` -> `YZ_xy_stop`

### motionQueue

- `IssueNextPulse` -> `MQ_IssueNextPulse`
- `STATE13_IND` -> `MQ_STATE13_IND`
- `eot_triggered` -> `MQ_eot_triggered`
- `x_axis_mso` -> `MQ_x_axis_mso`
- `y_axis_mso` -> `MQ_y_axis_mso`
