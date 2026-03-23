
# rung 0
from math import sqrt
if STATE==2:
    NEXTSTATE=1
# rung 1
# XIO main_xy_move.IP CMP STATE=3 BST XIC tension_stable_timer.DN NXB XIO check_tension_stable NXB XIO TENSION_CONTROL_OK BND BST BST XIO Z_RETRACTED NXB GEQ Z_axis.ActualPosition MAX_TOLERABLE_Z BND CPT ERROR_CODE 3001 CPT NEXTSTATE 10 NXB XIC Z_RETRACTED XIO APA_IS_VERTICAL CPT ERROR_CODE 3005 CPT NEXTSTATE 10 BND 
if not main_xy_move.IP:
    if STATE==3:
        if tension_stable_timer.DN or not check_tension_stable or not TENSION_CONTROL_OK:
            if not Z_RETRACTED or Z_axis.ActualPosition >= MAX_TOLERABLE_Z:
                ERROR_CODE = 3001
                NEXTSTATE = 10
            elif Z_RETRACTED and not APA_IS_VERTICAL:
                    ERROR_CODE = 3005
                    NEXTSTATE = 10

# BST XIC TENSION_CONTROL_OK XIC speed_regulator_switch JSR xy_speed_regulator 0 NXB BST XIO TENSION_CONTROL_OK NXB XIC TENSION_CONTROL_OK XIO speed_regulator_switch BND XIC trigger_xy_move MCLM X_Y main_xy_move 0 X_POSITION XY_SPEED_REQ "Units per sec" XY_ACCELERATION "Units per sec2" XY_DECELERATION "Units per sec2" S-Curve 500 500 "Units per sec3" 0 Disabled Programmed 50 0 None 0 0 BND 
if TENSION_CONTROL_OK and speed_regulator_switch:
    xy_speed_regulator()
elif not tension_control_ok or not speed_regulator_switch:
    if trigger_xy_move:
        MCLM(motion_control = X_Y main_xy_move, motion_type = absolute, target=POSITION,speed= XY_SPEED_REQ, speed_units= "Units per sec", accel= XY_ACCELERATION, accel_units= "Units per sec2" ,decel = XY_DECELERATION, decel_units= "Units per sec2",velocity_profile= S-Curve, accel_jerk = 500,decel_jerk= 500, jerk_units= "Units per sec3" ,termination_type = 0, merge=Disabled, merge_speed=Programmed, lock_position = 50, lock_direction=None, event_distance=0, calculated_data=0)

# XIC eot_triggered MCS X_Y eot_stop_instruction All Yes 10000 "Units per sec2" Yes 1000 "Units per sec3" CPT NEXTSTATE 11 CPT MOVE_TYPE 0 OTU eot_triggered 
if eot_triggered:
    MCS(motion_control = X_Y, instruction = eot_stop_instruction, stop_type = All, change_decel = Yes, decel= 10000, decel_units= "Units per sec2", change_jerk= Yes, jerk= 1000, jerk_units= "Units per sec3")
    NEXTSTATE = 11
    MOVE_TYPE = 0
    eot_triggered = False

# XIC trigger_z_move XIC STATE5_IND BST XIO Z_FIXED_LATCHED MAM Z_axis z_axis_main_move 0 Z_POSITION Z_SPEED "Units per sec" Z_ACCELERATION "Units per sec2" Z_DECELLERATION "Units per sec2" S-Curve z_accel_jerk z_decel_jerk "Units per sec3" Disabled Programmed 0 None 0 0 NXB XIC Z_FIXED_LATCHED MAM Z_axis z_axis_main_move 0 Z_POSITION 1000 "Units per sec" 10000 "Units per sec2" 10000 "Units per sec2" S-Curve 10000 10000 "Units per sec3" Disabled Programmed 0 None 0 0 BND OTU trigger_z_move 
if trigger_z_move and STATE5_IND:
    if not Z_FIXED_LATCHED:
        MAM(motion_control = Z_axis, motion_type = absolute, target=Z_POSITION, speed= Z_SPEED, speed_units= "Units per sec", accel= Z_ACCELERATION, accel_units= "Units per sec2" ,decel = Z_DECELLERATION, decel_units= "Units per sec2",velocity_profile= S-Curve, accel_jerk = z_accel_jerk,decel_jerk= z_decel_jerk, jerk_units= "Units per sec3" ,termination_type = 0, merge=Disabled, merge_speed=Programmed, lock_position=0, lock_direction=None, event_distance=0, calculated_data=0)
    elif Z_FIXED_LATCHED:
        MAM(motion_control = Z_axis, motion_type = absolute, target=1000, speed= 10000, speed_units= "Units per sec", accel= 10000, accel_units= "Units per sec2" ,decel = 10000, decel_units= "Units per sec2",velocity_profile= S-Curve, accel_jerk = 10000,decel_jerk= 10000, jerk_units= "Units per sec3" ,termination_type = 0, merge=Disabled, merge_speed=Programmed, lock_position=0, lock_direction=None, event_distance=0, calculated_data=0)
    trigger_z_move = False