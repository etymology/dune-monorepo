from dune_winder.plc_ladder.imperative import bind_scan_context

from math import atan, cos, fmod, sin, sqrt, trunc

from dune_winder.plc_ladder.codegen_support import (
    ADD,
    BRANCH,
    CMP,
    COP,
    CPT,
    CTU,
    EQU,
    FFL,
    FFU,
    FLL,
    GEQ,
    GRT,
    JMP,
    LBL,
    LEQ,
    LES,
    LIM,
    MAFR,
    MAM,
    MAS,
    MCCD,
    MCCM,
    MCLM,
    MCS,
    MOD,
    MOV,
    MSF,
    MSO,
    NEQ,
    NOP,
    ONS,
    OTE,
    OTL,
    OTU,
    PID,
    RES,
    ROUTINE,
    RUNG,
    TON,
    TRN,
    XIC,
    XIO,
)


__ladder_routine__ = ROUTINE(
    name="main",
    program="Monoroutine",
    source_path="dune_winder/plc_monoroutine/Monoroutine/main/manual-edit.rll",
    rungs=(
        RUNG(
            XIC("Local:1:I.Pt00.Data"),
            OTE("MACHINE_SW_STAT[1]"),
            OTE("Z_RETRACTED_1A"),
        ),
        RUNG(
            XIO("Local:1:I.Pt01.Data"),
            OTE("MACHINE_SW_STAT[2]"),
            OTE("Z_RETRACTED_1B"),
        ),
        RUNG(
            XIC("Local:1:I.Pt02.Data"),
            OTE("MACHINE_SW_STAT[3]"),
            OTE("Z_RETRACTED_2A"),
        ),
        RUNG(
            XIO("Local:1:I.Pt03.Data"),
            OTE("MACHINE_SW_STAT[4]"),
            OTE("Z_RETRACTED_2B"),
        ),
        RUNG(
            BRANCH([XIC("Local:1:I.Pt04.Data")], [CMP("Z_axis.ActualPosition>415")]),
            OTE("MACHINE_SW_STAT[5]"),
            OTE("Z_EXTENDED"),
        ),
        RUNG(
            XIC("Local:1:I.Pt11.Data"),
            OTE("MACHINE_SW_STAT[6]"),
            OTE("Z_STAGE_LATCHED"),
        ),
        RUNG(
            XIC("Local:2:I.Pt01.Data"),
            OTE("MACHINE_SW_STAT[7]"),
            OTE("Z_FIXED_LATCHED"),
        ),
        RUNG(
            BRANCH([XIC("Local:1:I.Pt07.Data")], [XIC("z_eot_bypass")]),
            OTE("MACHINE_SW_STAT[8]"),
            OTE("Z_EOT"),
        ),
        RUNG(
            XIO("Local:1:I.Pt10.Data"),
            OTE("MACHINE_SW_STAT[9]"),
            OTE("Z_STAGE_PRESENT"),
        ),
        RUNG(
            XIO("Local:2:I.Pt02.Data"),
            OTE("MACHINE_SW_STAT[10]"),
            OTE("Z_FIXED_PRESENT"),
        ),
        RUNG(
            XIC("Local:2:I.Pt04.Data"),
            OTE("MACHINE_SW_STAT[14]"),
            OTE("X_PARKED"),
        ),
        RUNG(
            XIC("Local:2:I.Pt00.Data"),
            OTE("MACHINE_SW_STAT[15]"),
            OTE("X_XFER_OK"),
        ),
        RUNG(
            XIC("Local:1:I.Pt13.Data"),
            OTE("MACHINE_SW_STAT[16]"),
            OTE("Y_MOUNT_XFER_OK"),
        ),
        RUNG(
            XIC("Local:1:I.Pt12.Data"),
            OTE("MACHINE_SW_STAT[17]"),
            OTE("Y_XFER_OK"),
        ),
        RUNG(
            XIC("Local:1:I.Pt06.Data"),
            OTE("MACHINE_SW_STAT[18]"),
            OTE("PLUS_Y_EOT"),
        ),
        RUNG(
            XIC("Local:2:I.Pt12.Data"),
            OTE("MACHINE_SW_STAT[19]"),
            OTE("MINUS_Y_EOT"),
        ),
        RUNG(
            XIC("Local:2:I.Pt08.Data"),
            OTE("MACHINE_SW_STAT[20]"),
            OTE("PLUS_X_EOT"),
        ),
        RUNG(
            XIC("Local:2:I.Pt10.Data"),
            OTE("MACHINE_SW_STAT[21]"),
            OTE("MINUS_X_EOT"),
        ),
        RUNG(
            XIC("Local:2:I.Pt14.Data"),
            OTE("MACHINE_SW_STAT[22]"),
            OTE("APA_IS_VERTICAL"),
        ),
        RUNG(
            BRANCH(
                [XIO("DUNEW2PLC2:1:I.Pt02Data")],
                [XIO("DUNEW2PLC2:1:I.Pt03Data")],
                [XIO("DUNEW2PLC2:1:I.Pt04Data")],
            ),
            OTE("MACHINE_SW_STAT[23]"),
        ),
        RUNG(
            XIC("DUNEW2PLC2:1:I.Pt00Data"),
            XIC("DUNEW2PLC2:1:I.Pt01Data"),
            OTE("MACHINE_SW_STAT[25]"),
        ),
        RUNG(
            XIC("Local:6:I.Pt00.Data"),
            OTE("MACHINE_SW_STAT[26]"),
            OTE("FRAME_LOC_HD_TOP"),
        ),
        RUNG(
            XIC("Local:6:I.Pt01.Data"),
            OTE("MACHINE_SW_STAT[27]"),
            OTE("FRAME_LOC_HD_MID"),
        ),
        RUNG(
            XIC("Local:6:I.Pt02.Data"),
            OTE("MACHINE_SW_STAT[28]"),
            OTE("FRAME_LOC_HD_BTM"),
        ),
        RUNG(
            XIC("Local:6:I.Pt03.Data"),
            OTE("MACHINE_SW_STAT[29]"),
            OTE("FRAME_LOC_FT_TOP"),
        ),
        RUNG(
            XIC("Local:6:I.Pt04.Data"),
            OTE("MACHINE_SW_STAT[30]"),
            OTE("FRAME_LOC_FT_MID"),
        ),
        RUNG(
            XIC("Local:6:I.Pt05.Data"),
            OTE("MACHINE_SW_STAT[31]"),
            OTE("FRAME_LOC_FT_BTM"),
        ),
        RUNG(
            XIO("DUNEW2PLC2:1:I.Pt06Data"),
            OTE("speed_regulator_switch"),
        ),
        RUNG(
            BRANCH([XIC("Z_RETRACTED_1A")], [XIC("Z_RETRACTED_2A")]),
            XIC("Z_RETRACTED_1B"),
            XIC("Z_RETRACTED_2B"),
            OTE("Z_RETRACTED"),
        ),
        RUNG(
            XIC("Z_EOT"),
            XIC("PLUS_Y_EOT"),
            XIC("MINUS_Y_EOT"),
            XIC("PLUS_X_EOT"),
            XIC("MINUS_X_EOT"),
            OTE("ALL_EOT_GOOD"),
        ),
        RUNG(
            LIM("80", "Y_axis.ActualPosition", "450"),
            OTE("support_collision_window_bttm"),
        ),
        RUNG(
            LIM("1050", "Y_axis.ActualPosition", "1550"),
            OTE("support_collision_window_mid"),
        ),
        RUNG(
            LIM("2200", "Y_axis.ActualPosition", "2650"),
            OTE("support_collision_window_top"),
        ),
        RUNG(
            XIC("Local:2:I.Pt06.Data"),
            OTE("TENSION_ON_SWITCH"),
        ),
        RUNG(
            BRANCH(
                [XIC("Local:1:I.Pt15.Data")], [GRT("tension", "wire_broken_tension")]
            ),
            OTE("wire_break_proxy"),
        ),
        RUNG(
            XIO("Safety_Tripped_S"),
            TON("T01", "5000", "0"),
        ),
        RUNG(
            XIC("Safety_Tripped_S"),
            BRANCH([OTE("Local:3:O.Pt11.Data")], [OTE("Local:3:O.Pt12.Data")]),
        ),
        RUNG(
            BRANCH(
                [XIC("blink_on.TT"), BRANCH([XIC("T01.TT")], [NEQ("ERROR_CODE", "0")])],
                [XIC("X_axis.SLSActiveStatus")],
            ),
            OTE("Local:3:O.Pt13.Data"),
        ),
        RUNG(
            XIC("blink_on.TT"),
            XIC("T01.TT"),
            OTE("Local:3:O.Pt15.Data"),
        ),
        RUNG(
            BRANCH([XIC("T01.TT")], [XIC("T01.DN")]),
            OTE("Local:3:O.Pt14.Data"),
        ),
        RUNG(
            TON("blink_on", "500", "0"),
        ),
        RUNG(
            XIC("blink_on.DN"),
            TON("blink_off", "500", "0"),
        ),
        RUNG(
            XIC("blink_off.DN"),
            RES("blink_on"),
        ),
        RUNG(
            XIC("INIT_DONE"),
            CMP("NEXTSTATE=0"),
            CPT("STATE", "0"),
        ),
        RUNG(
            XIC("INIT_DONE"),
            CMP("NEXTSTATE=1"),
            CPT("STATE", "1"),
        ),
        RUNG(
            XIC("INIT_DONE"),
            CMP("NEXTSTATE=2"),
            CPT("STATE", "2"),
        ),
        RUNG(
            XIC("INIT_DONE"),
            CMP("NEXTSTATE=3"),
            CPT("STATE", "3"),
        ),
        RUNG(
            XIC("INIT_DONE"),
            CMP("NEXTSTATE=4"),
            CPT("STATE", "4"),
        ),
        RUNG(
            XIC("INIT_DONE"),
            CMP("NEXTSTATE=5"),
            CPT("STATE", "5"),
        ),
        RUNG(
            XIC("INIT_DONE"),
            CMP("NEXTSTATE=6"),
            CPT("STATE", "6"),
        ),
        RUNG(
            XIC("INIT_DONE"),
            CMP("NEXTSTATE=7"),
            CPT("STATE", "7"),
        ),
        RUNG(
            XIC("INIT_DONE"),
            CMP("NEXTSTATE=8"),
            CPT("STATE", "8"),
        ),
        RUNG(
            XIC("INIT_DONE"),
            CMP("NEXTSTATE=9"),
            CPT("STATE", "9"),
        ),
        RUNG(
            XIC("INIT_DONE"),
            CMP("NEXTSTATE=10"),
            CPT("STATE", "10"),
        ),
        RUNG(
            XIC("INIT_DONE"),
            CMP("NEXTSTATE=11"),
            CPT("STATE", "11"),
        ),
        RUNG(
            XIC("INIT_DONE"),
            CMP("NEXTSTATE=12"),
            CPT("STATE", "12"),
        ),
        RUNG(
            XIC("INIT_DONE"),
            CMP("NEXTSTATE=13"),
            CPT("STATE", "13"),
        ),
        RUNG(
            XIC("INIT_DONE"),
            CMP("NEXTSTATE=14"),
            CPT("STATE", "14"),
        ),
        RUNG(
            XIC("Local:2:I.Pt13.Data"),
            OTE("ResetPB"),
        ),
        RUNG(
            CPT(
                "v_xyz",
                "SQR(X_axis.ActualVelocity*X_axis.ActualVelocity+Y_axis.ActualVelocity*Y_axis.ActualVelocity)+SQR(Z_axis.ActualVelocity*Z_axis.ActualVelocity)",
            ),
        ),
        RUNG(
            CPT(
                "v_xy",
                "SQR(X_axis.ActualVelocity*X_axis.ActualVelocity+Y_axis.ActualVelocity*Y_axis.ActualVelocity)",
            ),
        ),
        RUNG(
            NEQ("v_xy", "0"),
            CPT(
                "accel_xy",
                "(X_axis.ActualVelocity*X_axis.CommandAcceleration+Y_axis.ActualVelocity*Y_axis.CommandAcceleration)/v_xy",
            ),
        ),
        RUNG(
            BRANCH(
                [
                    BRANCH(
                        [XIC("Z_STAGE_LATCHED")],
                        [XIC("Z_FIXED_LATCHED"), EQU("ACTUATOR_POS", "3")],
                    ),
                    CPT("HEAD_POS", "0"),
                ],
                [
                    XIC("Z_FIXED_LATCHED"),
                    EQU("ACTUATOR_POS", "2"),
                    CPT("HEAD_POS", "3"),
                ],
                [XIO("Z_STAGE_LATCHED"), XIO("Z_FIXED_LATCHED"), CPT("HEAD_POS", "-1")],
            ),
        ),
        RUNG(
            XIC("TENSION_ON_SWITCH"),
            TON("tension_on_switch_delay_on_start", "1000", "0"),
        ),
        RUNG(
            XIC("TENSION_ON_SWITCH"),
            OTL("PTS_tension_switch_transition_oneshot_storage"),
        ),
        RUNG(
            XIO("TENSION_ON_SWITCH"),
            OTU("PTS_tension_switch_transition_oneshot_storage"),
        ),
        RUNG(
            XIC("TENSION_ON_SWITCH"),
            OTL("PTS_tension_switch_off_oneshot_storage"),
        ),
        RUNG(
            XIO("TENSION_ON_SWITCH"),
            OTU("PTS_tension_switch_off_oneshot_storage"),
        ),
        RUNG(
            XIO("wire_break_proxy"),
            TON("wire_break_debounce", "20", "0"),
        ),
        RUNG(
            XIC("TENSION_ON_SWITCH"),
            XIO("Safety_Tripped_S"),
            BRANCH(
                [XIC("wire_break_proxy")],
                [XIC("tension_on_switch_delay_on_start.TT")],
                [XIO("wire_break_debounce.DN")],
            ),
            OTE("Enable_tension_motor"),
        ),
        RUNG(
            BRANCH(
                [XIC("tension_on_switch_delay_on_start.TT")],
                [XIC("TENSION_CONTROL_OK")],
            ),
            BRANCH(
                [
                    BRANCH(
                        [XIC("wire_break_proxy")],
                        [XIO("wire_break_switch_delay_on_start.DN")],
                        [XIO("wire_break_debounce.DN")],
                    ),
                    OTE("TENSION_CONTROL_OK"),
                ],
                [TON("wire_break_switch_delay_on_start", "1000", "0")],
            ),
        ),
        RUNG(
            XIO("PID_LOOP_TIMER.DN"),
            TON("PID_LOOP_TIMER", "3", "0"),
        ),
        RUNG(
            CPT(
                "tension",
                "2.26*tension_tag-0.503*tension_tag*tension_tag+0.0694*tension_tag*tension_tag*tension_tag-0.00314*tension_tag*tension_tag*tension_tag*tension_tag",
            ),
        ),
        RUNG(
            CMP("tension_tag<=1"),
            CPT("tension", "tension_tag"),
        ),
        RUNG(
            BRANCH([XIC("PID_LOOP_TIMER.DN")], [XIC("pid_loop_timer_bypass")]),
            BRANCH(
                [
                    XIC("TENSION_CONTROL_OK"),
                    MOV("tension_setpoint", "winding_head_pid.SP"),
                ],
                [
                    XIO("TENSION_CONTROL_OK"),
                    MOV("10", "tension"),
                    MOV("0", "winding_head_pid.SP"),
                ],
                [
                    PID(
                        "winding_head_pid",
                        "tension",
                        "0",
                        "tension_motor_cv",
                        "0",
                        "0",
                        "0",
                    )
                ],
                [
                    BRANCH(
                        [XIO("TENSION_CONTROL_OK")],
                        [XIO("TENSION_ON_SWITCH")],
                        [
                            XIC("tension_on_switch_delay_on_start.TT"),
                            LES("tension_motor_cv", "neutral_cv"),
                        ],
                    ),
                    MOV("neutral_cv", "tension_motor_cv"),
                ],
                [XIC("constant_cv_out"), MOV("SetPoint_Override", "tension_motor_cv")],
                [MOV("tension_motor_cv", "cv_to_electrocraft")],
            ),
        ),
        RUNG(
            CPT("tension_motor_difference", "tension-tension_motor_cv"),
        ),
        RUNG(
            CPT(
                "current_command",
                "cv_to_electrocraft*(current_command_high-current_command_low)/pid_cv_high_limit+current_command_low",
            ),
        ),
        RUNG(
            CPT(
                "neutral_cv",
                "-current_command_low/((current_command_high-current_command_low)/(pid_cv_high_limit-pid_cv_low_limit))",
            ),
        ),
        RUNG(
            MOV("tension_stable_time", "tension_stable_timer.PRE"),
            CMP("ABS(tension-tension_setpoint)<tension_stable_tolerance"),
            TON("tension_stable_timer", "100", "0"),
        ),
        RUNG(
            GRT("tension", "max_tolerable_tension"),
            XIC("TENSION_ON_SWITCH"),
            OTE("Local:3:O.Pt15.Data"),
            TON("overtension_timer", "10", "0"),
        ),
        RUNG(
            XIC("overtension_timer.DN"),
            OTE("MORE_STATS[2]"),
            CPT("ERROR_CODE", "8002"),
            CPT("NEXTSTATE", "10"),
        ),
        RUNG(
            XIC("tension_on_switch_delay_on_start.DN"),
            XIC("wire_break_debounce.DN"),
            NEQ("ERROR_CODE", "8002"),
            CPT("NEXTSTATE", "10"),
            CPT("ERROR_CODE", "8001"),
        ),
        RUNG(
            XIO("TENSION_ON_SWITCH"),
            XIC("PTS_tension_switch_transition_oneshot_storage"),
            OTE("PTS_clear_tension_fault_oneshot"),
        ),
        RUNG(
            XIC("PTS_clear_tension_fault_oneshot"),
            BRANCH([EQU("ERROR_CODE", "8002")], [EQU("ERROR_CODE", "8001")]),
            CPT("ERROR_CODE", "0"),
        ),
        RUNG(
            EQU("MOVE_TYPE", "9"),
            XIC("INIT_SW"),
            OTU("INIT_SW"),
        ),
        RUNG(
            XIC("INIT_SW"),
            TON("TIMER", "2000", "0"),
        ),
        RUNG(
            XIO("INIT_SW"),
            CPT("MOVE_TYPE", "0"),
            OTL("INIT_SW"),
        ),
        RUNG(
            XIC("TIMER.DN"),
            XIO("INIT_SetBit[0]"),
            OTE("INIT_OutBit[0]"),
        ),
        RUNG(
            XIC("TIMER.DN"),
            OTL("INIT_SetBit[0]"),
        ),
        RUNG(
            XIO("TIMER.DN"),
            OTU("INIT_SetBit[0]"),
        ),
        RUNG(
            XIC("INIT_OutBit[0]"),
            CPT("MOVE_TYPE", "0"),
            CPT("NEXTSTATE", "1"),
            CPT("STATE", "0"),
            CPT("ERROR_CODE", "0"),
        ),
        RUNG(
            XIC("INIT_OutBit[0]"),
            OTU("LATCH_ACTUATOR_HOMED"),
        ),
        RUNG(
            XIC("INIT_SetBit[0]"),
            OTE("INIT_DONE"),
        ),
        RUNG(
            XIC("INIT_DONE"),
            CMP("STATE=0"),
            MAFR("Z_axis", "INIT_z_axis_fault_reset_status"),
        ),
        RUNG(
            XIC("INIT_z_axis_fault_reset_status.DN"),
            XIO("INIT_SetBit[1]"),
            OTE("INIT_OutBit[1]"),
        ),
        RUNG(
            XIC("INIT_z_axis_fault_reset_status.DN"),
            OTL("INIT_SetBit[1]"),
        ),
        RUNG(
            XIO("INIT_z_axis_fault_reset_status.DN"),
            OTU("INIT_SetBit[1]"),
        ),
        RUNG(
            XIC("INIT_OutBit[1]"),
            CPT("NEXTSTATE", "1"),
        ),
        RUNG(
            XIC("INIT_DONE"),
            CMP("STATE=1"),
            OTE("STATE1_IND"),
        ),
        RUNG(
            XIC("STATE1_IND"),
            XIO("trigger_axes_sb"),
            OTE("trigger_axes_ob"),
        ),
        RUNG(
            XIC("STATE1_IND"),
            OTL("trigger_axes_sb"),
        ),
        RUNG(
            XIO("STATE1_IND"),
            OTU("trigger_axes_sb"),
        ),
        RUNG(
            XIC("trigger_axes_ob"),
            XIO("dont_auto_trigger_axes_in_state_1"),
            MSO("X_axis", "x_on_mso"),
            MSO("Y_axis", "y_on_mso"),
            MSO("Z_axis", "z_on_mso"),
        ),
        RUNG(
            XIC("STATE1_IND"),
            MOV("0", "ERROR_CODE"),
        ),
        RUNG(
            XIC("STATE1_IND"),
            CMP("MOVE_TYPE=1"),
            XIO("RS1_SetBit[0]"),
            OTE("RS1_OutBit[0]"),
        ),
        RUNG(
            XIC("STATE1_IND"),
            CMP("MOVE_TYPE=1"),
            OTL("RS1_SetBit[0]"),
        ),
        RUNG(
            BRANCH([XIO("STATE1_IND")], [NEQ("MOVE_TYPE", "1")]),
            OTU("RS1_SetBit[0]"),
        ),
        RUNG(
            XIC("RS1_OutBit[0]"),
            CPT("NEXTSTATE", "2"),
        ),
        RUNG(
            XIC("STATE1_IND"),
            CMP("MOVE_TYPE=2"),
            XIO("RS1_SetBit[1]"),
            OTE("RS1_OutBit[1]"),
        ),
        RUNG(
            XIC("STATE1_IND"),
            CMP("MOVE_TYPE=2"),
            OTL("RS1_SetBit[1]"),
        ),
        RUNG(
            BRANCH([XIO("STATE1_IND")], [NEQ("MOVE_TYPE", "2")]),
            OTU("RS1_SetBit[1]"),
        ),
        RUNG(
            XIC("RS1_OutBit[1]"),
            CPT("NEXTSTATE", "3"),
        ),
        RUNG(
            XIC("STATE1_IND"),
            CMP("MOVE_TYPE=3"),
            XIO("RS1_SetBit[2]"),
            OTE("RS1_OutBit[2]"),
        ),
        RUNG(
            XIC("STATE1_IND"),
            CMP("MOVE_TYPE=3"),
            OTL("RS1_SetBit[2]"),
        ),
        RUNG(
            BRANCH([XIO("STATE1_IND")], [NEQ("MOVE_TYPE", "3")]),
            OTU("RS1_SetBit[2]"),
        ),
        RUNG(
            XIC("RS1_OutBit[2]"),
            CPT("NEXTSTATE", "4"),
        ),
        RUNG(
            XIC("STATE1_IND"),
            CMP("MOVE_TYPE=4"),
            XIO("RS1_SetBit[3]"),
            OTE("RS1_OutBit[3]"),
        ),
        RUNG(
            XIC("STATE1_IND"),
            CMP("MOVE_TYPE=4"),
            OTL("RS1_SetBit[3]"),
        ),
        RUNG(
            BRANCH([XIO("STATE1_IND")], [NEQ("MOVE_TYPE", "4")]),
            OTU("RS1_SetBit[3]"),
        ),
        RUNG(
            XIC("RS1_OutBit[3]"),
            CPT("NEXTSTATE", "5"),
        ),
        RUNG(
            XIC("STATE1_IND"),
            CMP("MOVE_TYPE=5"),
            XIO("RS1_SetBit[4]"),
            OTE("RS1_OutBit[4]"),
        ),
        RUNG(
            XIC("STATE1_IND"),
            CMP("MOVE_TYPE=5"),
            OTL("RS1_SetBit[4]"),
        ),
        RUNG(
            BRANCH([XIO("STATE1_IND")], [NEQ("MOVE_TYPE", "5")]),
            OTU("RS1_SetBit[4]"),
        ),
        RUNG(
            XIC("RS1_OutBit[4]"),
            CPT("NEXTSTATE", "6"),
        ),
        RUNG(
            XIC("STATE1_IND"),
            CMP("MOVE_TYPE=6"),
            XIO("RS1_SetBit[5]"),
            OTE("RS1_OutBit[5]"),
        ),
        RUNG(
            XIC("STATE1_IND"),
            CMP("MOVE_TYPE=6"),
            OTL("RS1_SetBit[5]"),
        ),
        RUNG(
            BRANCH([XIO("STATE1_IND")], [NEQ("MOVE_TYPE", "6")]),
            OTU("RS1_SetBit[5]"),
        ),
        RUNG(
            XIC("RS1_OutBit[5]"),
            CPT("NEXTSTATE", "7"),
        ),
        RUNG(
            XIC("STATE1_IND"),
            CMP("MOVE_TYPE=7"),
            XIO("RS1_SetBit[6]"),
            OTE("RS1_OutBit[6]"),
        ),
        RUNG(
            XIC("STATE1_IND"),
            CMP("MOVE_TYPE=7"),
            OTL("RS1_SetBit[6]"),
        ),
        RUNG(
            BRANCH([XIO("STATE1_IND")], [NEQ("MOVE_TYPE", "7")]),
            OTU("RS1_SetBit[6]"),
        ),
        RUNG(
            XIC("RS1_OutBit[6]"),
            CPT("NEXTSTATE", "8"),
        ),
        RUNG(
            XIC("STATE1_IND"),
            CMP("MOVE_TYPE=8"),
            XIO("RS1_SetBit[7]"),
            OTE("RS1_OutBit[7]"),
        ),
        RUNG(
            XIC("STATE1_IND"),
            CMP("MOVE_TYPE=8"),
            OTL("RS1_SetBit[7]"),
        ),
        RUNG(
            BRANCH([XIO("STATE1_IND")], [NEQ("MOVE_TYPE", "8")]),
            OTU("RS1_SetBit[7]"),
        ),
        RUNG(
            XIC("RS1_OutBit[7]"),
            CPT("NEXTSTATE", "9"),
        ),
        RUNG(
            XIC("STATE1_IND"),
            CMP("MOVE_TYPE=11"),
            XIO("RS1_SetBit[8]"),
            OTE("RS1_OutBit[8]"),
        ),
        RUNG(
            XIC("STATE1_IND"),
            CMP("MOVE_TYPE=11"),
            OTL("RS1_SetBit[8]"),
        ),
        RUNG(
            BRANCH([XIO("STATE1_IND")], [NEQ("MOVE_TYPE", "11")]),
            OTU("RS1_SetBit[8]"),
        ),
        RUNG(
            XIC("RS1_OutBit[8]"),
            CPT("NEXTSTATE", "14"),
        ),
        RUNG(
            CMP("STATE=2"),
            CPT("NEXTSTATE", "1"),
        ),
        RUNG(
            XIO("main_xy_move.IP"),
            CMP("STATE=3"),
            BRANCH(
                [XIC("tension_stable_timer.DN")],
                [XIO("check_tension_stable")],
                [XIO("TENSION_CONTROL_OK")],
            ),
            BRANCH(
                [
                    BRANCH(
                        [XIO("Z_RETRACTED")],
                        [GEQ("Z_axis.ActualPosition", "MAX_TOLERABLE_Z")],
                    ),
                    CPT("ERROR_CODE", "3001"),
                    CPT("NEXTSTATE", "10"),
                ],
                [
                    XIC("Z_RETRACTED"),
                    BRANCH(
                        [XIC("APA_IS_VERTICAL")],
                        [
                            XIO("APA_IS_VERTICAL"),
                            CPT("ERROR_CODE", "3005"),
                            CPT("NEXTSTATE", "10"),
                        ],
                    ),
                    OTE("STATE3_IND"),
                ],
            ),
        ),
        RUNG(
            XIC("STATE3_IND"),
            XIO("MXY_state3_entry_oneshot_storage"),
            OTE("MXY_state3_entry_oneshot"),
        ),
        RUNG(
            XIC("STATE3_IND"),
            OTL("MXY_state3_entry_oneshot_storage"),
        ),
        RUNG(
            XIO("STATE3_IND"),
            OTU("MXY_state3_entry_oneshot_storage"),
        ),
        RUNG(
            XIC("STATE3_IND"),
            BRANCH(
                [XIC("X_Y.PhysicalAxisFault"), CPT("ERROR_CODE", "3002")],
                [
                    BRANCH(
                        [XIC("X_axis.SafeTorqueOffInhibit")],
                        [XIC("Y_axis.SafeTorqueOffInhibit")],
                    ),
                    CPT("ERROR_CODE", "3004"),
                ],
            ),
            CPT("NEXTSTATE", "10"),
        ),
        RUNG(
            XIC("MXY_state3_entry_oneshot"),
            BRANCH(
                [MSO("X_axis", "MXY_x_axis_servo_on_status")],
                [MSO("Y_axis", "MXY_y_axis_servo_on_status")],
            ),
        ),
        RUNG(
            XIC("MXY_x_axis_servo_on_status.DN"),
            XIC("MXY_y_axis_servo_on_status.DN"),
            XIO("MXY_axes_servo_ready_oneshot_storage"),
            OTE("MXY_axes_servo_ready_oneshot"),
        ),
        RUNG(
            XIC("MXY_x_axis_servo_on_status.DN"),
            XIC("MXY_y_axis_servo_on_status.DN"),
            OTL("MXY_axes_servo_ready_oneshot_storage"),
        ),
        RUNG(
            BRANCH(
                [XIO("MXY_x_axis_servo_on_status.DN")],
                [XIO("MXY_y_axis_servo_on_status.DN")],
            ),
            OTU("MXY_axes_servo_ready_oneshot_storage"),
        ),
        RUNG(
            BRANCH(
                [XIC("MXY_axes_servo_ready_oneshot")],
                [
                    XIC("MXY_x_axis_servo_on_status.DN"),
                    XIC("MXY_y_axis_servo_on_status.DN"),
                    XIC("MXY_state3_entry_oneshot"),
                ],
            ),
            XIO("MXY_trigger_xy_move_oneshot_storage"),
            OTE("trigger_xy_move"),
        ),
        RUNG(
            BRANCH(
                [XIC("MXY_axes_servo_ready_oneshot")],
                [
                    XIC("MXY_x_axis_servo_on_status.DN"),
                    XIC("MXY_y_axis_servo_on_status.DN"),
                    XIC("MXY_state3_entry_oneshot"),
                ],
            ),
            OTL("MXY_trigger_xy_move_oneshot_storage"),
        ),
        RUNG(
            BRANCH(
                [XIO("MXY_axes_servo_ready_oneshot")],
                [
                    BRANCH(
                        [XIO("MXY_x_axis_servo_on_status.DN")],
                        [XIO("MXY_y_axis_servo_on_status.DN")],
                        [XIO("MXY_state3_entry_oneshot")],
                    )
                ],
            ),
            OTU("MXY_trigger_xy_move_oneshot_storage"),
        ),
        RUNG(
            XIC("trigger_xy_move"),
            MOV("X_axis.ActualPosition", "starting_x"),
            MOV("Y_axis.ActualPosition", "starting_y"),
        ),
        RUNG(
            XIC("trigger_xy_move"),
            CPT("dx", "ABS(starting_x-X_POSITION)"),
            CPT("dy", "ABS(starting_y-Y_POSITION)"),
            CPT("x_time", "v_x_max/dx"),
            CPT("y_time", "v_y_max/dy"),
            BRANCH(
                [LES("x_time", "y_time"), CPT("k", "x_time")],
                [LEQ("y_time", "x_time"), CPT("k", "y_time")],
            ),
            CPT("v_max", "k*SQR(dx*dx+dy*dy)"),
            BRANCH(
                [LES("v_max", "XY_SPEED"), CPT("XY_SPEED_REQ", "v_max")],
                [LEQ("XY_SPEED", "v_max"), CPT("XY_SPEED_REQ", "XY_SPEED")],
            ),
        ),
        RUNG(
            CPT("x_dist_to_target", "X_axis.ActualPosition-X_POSITION"),
            CPT("y_dist_to_target", "Y_axis.ActualPosition-Y_POSITION"),
            CPT(
                "xy_dist_to_target",
                "SQR(x_dist_to_target*x_dist_to_target+y_dist_to_target*y_dist_to_target)",
            ),
        ),
        RUNG(
            MOV("xy_decel_jerk", "J"),
            MOV("v_xyz", "v_0"),
            CPT("gamma", "SQR(accel_xy*accel_xy+4*J*v_0)"),
            CPT(
                "stopping_distance",
                "(accel_xy+gamma)*(accel_xy+gamma)*(accel_xy+gamma)/(6*J*J)",
            ),
        ),
        RUNG(
            CMP("xy_dist_to_target<stopping_distance*1"),
            OTE("near_ending"),
        ),
        RUNG(
            CMP("STATE=3"),
            CPT("stopping_ratio", "stopping_distance/xy_dist_to_target"),
        ),
        RUNG(
            XIC("TENSION_CONTROL_OK"),
            XIC("speed_regulator_switch"),
            XIC("trigger_xy_move"),
            MCLM(
                "X_Y",
                "main_xy_move",
                "0",
                "X_POSITION",
                "v_max",
                '"Units per sec"',
                "xy_regulated_acceleration",
                '"Units per sec2"',
                "xy_regulated_deceleration",
                '"Units per sec2"',
                "S-Curve",
                "xy_regulated_accel_jerk",
                "xy_decel_jerk",
                '"Units per sec3"',
                "0",
                "Disabled",
                "Programmed",
                "50",
                "0",
                "None",
                "0",
                "0",
            ),
        ),
        RUNG(
            XIC("TENSION_CONTROL_OK"),
            XIC("speed_regulator_switch"),
            XIC("trigger_xy_move"),
            MOV("xy_dt", "regulator_loop_timer.PRE"),
            MOV("xy_d_dt", "xy_d_timer.PRE"),
            MOV("0", "xy_i_term"),
        ),
        RUNG(
            XIC("TENSION_CONTROL_OK"),
            XIC("speed_regulator_switch"),
            XIO("regulator_loop_timer.DN"),
            TON("regulator_loop_timer", "1", "0"),
        ),
        RUNG(
            XIC("TENSION_CONTROL_OK"),
            XIC("speed_regulator_switch"),
            XIO("xy_d_timer.DN"),
            TON("xy_d_timer", "1", "0"),
        ),
        RUNG(
            XIC("TENSION_CONTROL_OK"),
            XIC("speed_regulator_switch"),
            XIC("xy_d_timer.DN"),
            CPT("d_raw", "xy_kd*(xy_error-xy_error_prev)/xy_d_dt*100"),
            CPT("xy_d_term", "xy_d_alpha*d_raw+(1-xy_d_alpha)*xy_d_term_prev"),
            MOV("xy_error", "xy_error_prev"),
            MOV("xy_d_term", "xy_d_term_prev"),
        ),
        RUNG(
            XIC("TENSION_CONTROL_OK"),
            XIC("speed_regulator_switch"),
            CPT("xy_error", "speed_tension_setpoint-tension"),
        ),
        RUNG(
            XIC("TENSION_CONTROL_OK"),
            XIC("speed_regulator_switch"),
            XIC("regulator_loop_timer.DN"),
            CPT("xy_p_term", "xy_kp*xy_error"),
        ),
        RUNG(
            XIC("TENSION_CONTROL_OK"),
            XIC("speed_regulator_switch"),
            XIC("regulator_loop_timer.DN"),
            BRANCH([LES("regulated_speed", "v_max")], [LES("xy_error", "0")]),
            BRANCH(
                [GRT("regulated_speed", "min_regulated_speed")], [GRT("xy_error", "0")]
            ),
            CPT("xy_i_term", "xy_i_term+(xy_ki*xy_error*xy_dt/1000)"),
            BRANCH(
                [LES("xy_i_term", "min_integral"), MOV("min_integral", "xy_i_term")],
                [GRT("xy_i_term", "max_integral"), MOV("max_integral", "xy_i_term")],
            ),
        ),
        RUNG(
            XIC("TENSION_CONTROL_OK"),
            XIC("speed_regulator_switch"),
            XIC("regulator_loop_timer.DN"),
            CPT("regulated_speed", "xy_default_speed+xy_p_term+xy_i_term+xy_d_term"),
            BRANCH(
                [LES("v_max", "regulated_speed"), MOV("v_max", "regulated_speed")],
                [
                    LES("regulated_speed", "min_regulated_speed"),
                    MOV("min_regulated_speed", "regulated_speed"),
                ],
            ),
        ),
        RUNG(
            BRANCH(
                [XIO("TENSION_CONTROL_OK")],
                [XIC("TENSION_CONTROL_OK"), XIO("speed_regulator_switch")],
            ),
            XIC("trigger_xy_move"),
            MCLM(
                "X_Y",
                "main_xy_move",
                "0",
                "X_POSITION",
                "XY_SPEED_REQ",
                '"Units per sec"',
                "XY_ACCELERATION",
                '"Units per sec2"',
                "XY_DECELERATION",
                '"Units per sec2"',
                "S-Curve",
                "500",
                "500",
                '"Units per sec3"',
                "0",
                "Disabled",
                "Programmed",
                "50",
                "0",
                "None",
                "0",
                "0",
            ),
        ),
        RUNG(
            XIO("speed_regulator_switch"),
            XIC("MXY_speed_regulator_disabled_oneshot_storage"),
            OTE("MXY_speed_regulator_disabled_oneshot"),
        ),
        RUNG(
            XIC("speed_regulator_switch"),
            OTL("MXY_speed_regulator_disabled_oneshot_storage"),
        ),
        RUNG(
            XIO("speed_regulator_switch"),
            OTU("MXY_speed_regulator_disabled_oneshot_storage"),
        ),
        RUNG(
            XIC("MXY_speed_regulator_disabled_oneshot"),
            XIO("near_ending"),
            MCCD(
                "X_Y",
                "MCCD_X_Y_Axis1",
                '"Coordinated Move"',
                "Yes",
                "XY_SPEED_REQ",
                '"Units per sec"',
                "Yes",
                "XY_ACCELERATION",
                '"Units per sec2"',
                "Yes",
                "XY_DECELERATION",
                '"Units per sec2"',
                "No",
                "xy_accel_jerk",
                "No",
                "xy_decel_jerk",
                '"Units per sec3"',
                '"Active Motion"',
            ),
        ),
        RUNG(
            BRANCH([XIC("main_xy_move.PC")], [XIC("main_xy_move.ER")]),
            BRANCH(
                [CMP("X_axis.ActualPosition<(X_POSITION+0.1)")],
                [XIC("STATE3_IND"), CMP("MOVE_TYPE=0"), CPT("ERROR_CODE", "3003")],
            ),
            XIO("MXY_xy_move_done_or_fault_oneshot_storage"),
            OTE("MXY_xy_move_done_or_fault_oneshot"),
        ),
        RUNG(
            BRANCH([XIC("main_xy_move.PC")], [XIC("main_xy_move.ER")]),
            BRANCH(
                [CMP("X_axis.ActualPosition<(X_POSITION+0.1)")],
                [XIC("STATE3_IND"), CMP("MOVE_TYPE=0"), CPT("ERROR_CODE", "3003")],
            ),
            OTL("MXY_xy_move_done_or_fault_oneshot_storage"),
        ),
        RUNG(
            BRANCH([XIO("main_xy_move.PC")], [XIO("main_xy_move.ER")]),
            OTU("MXY_xy_move_done_or_fault_oneshot_storage"),
        ),
        RUNG(
            XIC("main_xy_move.IP"),
            CMP("MOVE_TYPE=11"),
            CPT("NEXTSTATE", "14"),
        ),
        RUNG(
            XIC("main_xy_move.IP"),
            XIO("ALL_EOT_GOOD"),
            XIO("MXY_eot_triggered_oneshot_storage"),
            OTE("MXY_eot_triggered"),
        ),
        RUNG(
            XIC("main_xy_move.IP"),
            XIO("ALL_EOT_GOOD"),
            OTL("MXY_eot_triggered_oneshot_storage"),
        ),
        RUNG(
            BRANCH([XIO("main_xy_move.IP")], [XIC("ALL_EOT_GOOD")]),
            OTU("MXY_eot_triggered_oneshot_storage"),
        ),
        RUNG(
            XIC("MXY_eot_triggered"),
            MCS(
                "X_Y",
                "MXY_eot_stop_status",
                "All",
                "Yes",
                "10000",
                '"Units per sec2"',
                "Yes",
                "1000",
                '"Units per sec3"',
            ),
            CPT("NEXTSTATE", "11"),
            CPT("MOVE_TYPE", "0"),
        ),
        RUNG(
            XIC("MXY_eot_triggered"),
            MCS(
                "X_Y",
                "MXY_eot_stop_status",
                "All",
                "Yes",
                "10000",
                '"Units per sec2"',
                "Yes",
                "1000",
                '"Units per sec3"',
            ),
            CPT("NEXTSTATE", "11"),
            CPT("MOVE_TYPE", "0"),
        ),
        RUNG(
            XIC("MXY_xy_move_done_or_fault_oneshot"),
            CPT("MOVE_TYPE", "0"),
            CPT("NEXTSTATE", "1"),
        ),
        RUNG(
            BRANCH(
                [XIC("Z_FIXED_LATCHED"), EQU("ACTUATOR_POS", "2")],
                [XIO("Z_FIXED_LATCHED")],
            ),
            OTE("no_latch_collision"),
        ),
        RUNG(
            BRANCH([XIC("X_XFER_OK")], [XIC("Y_XFER_OK")]),
            OTE("no_apa_collision"),
        ),
        RUNG(
            BRANCH(
                [
                    XIC("X_XFER_OK"),
                    BRANCH(
                        [
                            LIM("400", "X_axis.ActualPosition", "500"),
                            BRANCH(
                                [
                                    XIC("support_collision_window_bttm"),
                                    XIO("FRAME_LOC_HD_BTM"),
                                ],
                                [
                                    XIC("support_collision_window_mid"),
                                    XIO("FRAME_LOC_HD_MID"),
                                ],
                                [
                                    XIC("support_collision_window_top"),
                                    XIO("FRAME_LOC_HD_TOP"),
                                ],
                            ),
                        ],
                        [
                            LIM("7100", "X_axis.ActualPosition", "7200"),
                            BRANCH(
                                [
                                    XIC("support_collision_window_bttm"),
                                    XIO("FRAME_LOC_FT_BTM"),
                                ],
                                [
                                    XIC("support_collision_window_mid"),
                                    XIO("FRAME_LOC_FT_MID"),
                                ],
                                [
                                    XIC("support_collision_window_top"),
                                    XIO("FRAME_LOC_FT_TOP"),
                                ],
                            ),
                        ],
                        [
                            XIO("support_collision_window_bttm"),
                            XIO("support_collision_window_mid"),
                            XIO("support_collision_window_top"),
                        ],
                    ),
                ],
                [XIC("Y_XFER_OK")],
            ),
            OTE("no_supports_collision"),
        ),
        RUNG(
            XIC("no_latch_collision"),
            XIC("no_supports_collision"),
            XIC("no_apa_collision"),
            OTE("MASTER_Z_GO"),
        ),
        RUNG(
            CMP("STATE=4"),
            MOV("1", "NEXTSTATE"),
        ),
        RUNG(
            CMP("STATE=5"),
            XIC("Z_FIXED_LATCHED"),
            XIC("LATCH_ACTUATOR_HOMED"),
            CMP("ACTUATOR_POS<>2"),
            CPT("ERROR_CODE", "5004"),
            CPT("NEXTSTATE", "10"),
        ),
        RUNG(
            CMP("STATE=5"),
            XIC("Z_axis.PhysicalAxisFault"),
            CPT("ERROR_CODE", "5002"),
            CPT("NEXTSTATE", "10"),
        ),
        RUNG(
            CMP("STATE=5"),
            XIO("MASTER_Z_GO"),
            CPT("ERROR_CODE", "5001"),
            CPT("NEXTSTATE", "10"),
        ),
        RUNG(
            CMP("STATE=5"),
            XIC("MASTER_Z_GO"),
            BRANCH(
                [XIC("tension_stable_timer.DN")],
                [XIO("check_tension_stable")],
                [XIO("TENSION_CONTROL_OK")],
                [XIC("Z_FIXED_LATCHED")],
            ),
            OTE("STATE5_IND"),
        ),
        RUNG(
            XIC("STATE5_IND"),
            XIO("Z_axis.DriveEnableStatus"),
            MSO("Z_axis", "z_axis_mso"),
        ),
        RUNG(
            XIC("STATE5_IND"),
            XIC("Z_axis.DriveEnableStatus"),
            XIO("Z_FIXED_LATCHED"),
            MAM(
                "Z_axis",
                "z_axis_main_move",
                "0",
                "Z_POSITION",
                "Z_SPEED",
                '"Units per sec"',
                "Z_ACCELERATION",
                '"Units per sec2"',
                "Z_DECELLERATION",
                '"Units per sec2"',
                "S-Curve",
                "z_accel_jerk",
                "z_decel_jerk",
                '"Units per sec3"',
                "Disabled",
                "Programmed",
                "0",
                "None",
                "0",
                "0",
            ),
        ),
        RUNG(
            XIC("STATE5_IND"),
            XIC("Z_axis.DriveEnableStatus"),
            XIC("Z_FIXED_LATCHED"),
            MAM(
                "Z_axis",
                "z_axis_fast_move",
                "0",
                "Z_POSITION",
                "1000",
                '"Units per sec"',
                "10000",
                '"Units per sec2"',
                "10000",
                '"Units per sec2"',
                "S-Curve",
                "10000",
                "10000",
                '"Units per sec3"',
                "Disabled",
                "Programmed",
                "0",
                "None",
                "0",
                "0",
            ),
        ),
        RUNG(
            XIC("Z_axis.MoveStatus"),
            CMP("MOVE_TYPE=11"),
            CPT("NEXTSTATE", "14"),
        ),
        RUNG(
            XIO("ALL_EOT_GOOD"),
            XIC("Z_axis.MoveStatus"),
            MAS(
                "Z_axis",
                "eot_stop",
                "Jog",
                "Yes",
                "2000",
                '"Units per sec2"',
                "No",
                "100",
                '"% of Time"',
            ),
        ),
        RUNG(
            XIC("eot_stop.PC"),
            CPT("ERROR_CODE", "5005"),
            CPT("NEXTSTATE", "11"),
            MOV("0", "eot_stop.FLAGS"),
        ),
        RUNG(
            CMP("STATE=5"),
            CMP("ABS(Z_axis.ActualPosition-Z_POSITION)<0.1"),
            OTE("z_move_success"),
        ),
        RUNG(
            XIC("z_move_success"),
            CPT("MOVE_TYPE", "0"),
            CPT("NEXTSTATE", "1"),
            OTU("z_move_success"),
            MOV("0", "z_axis_main_move.FLAGS"),
        ),
        RUNG(
            XIO("Local:1:I.Pt08.Data"),
            OTE("MACHINE_SW_STAT[12]"),
            OTE("LATCH_ACTUATOR_TOP"),
        ),
        RUNG(
            XIO("Local:1:I.Pt09.Data"),
            OTE("MACHINE_SW_STAT[13]"),
            OTE("LATCH_ACTUATOR_MID"),
        ),
        RUNG(
            XIC("LATCH_ACTUATOR_TOP"),
            XIO("LATCH_ACTUATOR_MID"),
            CPT("ACTUATOR_POS", "3"),
            OTE("Z_STAGE_UNLATCHED"),
        ),
        RUNG(
            XIC("LATCH_ACTUATOR_TOP"),
            XIC("LATCH_ACTUATOR_MID"),
            BRANCH(
                [TON("delay_mid_position", "100", "0")],
                [XIC("delay_mid_position.DN"), CPT("ACTUATOR_POS", "2")],
            ),
            OTE("Z_OK_TO_ENGAGE"),
        ),
        RUNG(
            XIO("LATCH_ACTUATOR_TOP"),
            XIO("LATCH_ACTUATOR_MID"),
            XIO("Z_STAGE_LATCHED"),
            CPT("ACTUATOR_POS", "0"),
        ),
        RUNG(
            XIC("Z_STAGE_LATCHED"),
            BRANCH(
                [TON("Delay_Z_Latched", "1000", "0")],
                [XIC("Delay_Z_Latched.DN"), CPT("ACTUATOR_POS", "1")],
            ),
        ),
        RUNG(
            XIC("Z_FIXED_LATCHED"),
            BRANCH(
                [TON("Delay_Fixed_Latched", "1000", "0")],
                [XIC("Delay_Fixed_Latched.DN"), OTE("Z_SAFE_TO_WITHDRAW")],
            ),
        ),
        RUNG(
            XIC("Z_STAGE_PRESENT"),
            XIC("Z_FIXED_PRESENT"),
            XIC("Z_EXTENDED"),
            OTE("ENABLE_ACTUATOR"),
        ),
        RUNG(
            CMP("STATE=6"),
            OTE("STATE6_IND"),
        ),
        RUNG(
            XIC("STATE6_IND"),
            XIO("ENABLE_ACTUATOR"),
            XIO("LAT_state6_enable_missing_oneshot_storage"),
            OTE("LAT_state6_enable_missing_oneshot"),
        ),
        RUNG(
            XIC("STATE6_IND"),
            XIO("ENABLE_ACTUATOR"),
            OTL("LAT_state6_enable_missing_oneshot_storage"),
        ),
        RUNG(
            BRANCH([XIO("STATE6_IND")], [XIC("ENABLE_ACTUATOR")]),
            OTU("LAT_state6_enable_missing_oneshot_storage"),
        ),
        RUNG(
            XIC("LAT_state6_enable_missing_oneshot"),
            CPT("ERROR_CODE", "6001"),
            CPT("NEXTSTATE", "10"),
        ),
        RUNG(
            XIC("STATE6_IND"),
            XIC("ENABLE_ACTUATOR"),
            XIO("LAT_state6_enable_present_oneshot_storage"),
            OTE("LAT_state6_enable_present_oneshot"),
        ),
        RUNG(
            XIC("STATE6_IND"),
            XIC("ENABLE_ACTUATOR"),
            OTL("LAT_state6_enable_present_oneshot_storage"),
        ),
        RUNG(
            BRANCH([XIO("STATE6_IND")], [XIO("ENABLE_ACTUATOR")]),
            OTU("LAT_state6_enable_present_oneshot_storage"),
        ),
        RUNG(
            XIC("LAT_state6_enable_present_oneshot"),
            CPT("PREV_ACT_POS", "ACTUATOR_POS"),
        ),
        RUNG(
            XIC("LAT_state6_enable_present_oneshot_storage"),
            BRANCH(
                [CMP("PREV_ACT_POS=1")],
                [CMP("PREV_ACT_POS=3")],
                [CMP("PREV_ACT_POS=2")],
                [CMP("PREV_ACT_POS=0")],
            ),
            CPT("MOVE_TYPE", "0"),
            CPT("NEXTSTATE", "1"),
        ),
        RUNG(
            XIC("LAT_state6_enable_present_oneshot_storage"),
            XIO("Latching_pulse_interval.DN"),
            TON("Latching_pulse_duration", "10", "0"),
        ),
        RUNG(
            XIO("LAT_latching_pulse_interval_holdoff_storage"),
            XIC("Latching_pulse_duration.DN"),
            TON("Latching_pulse_interval", "250", "0"),
        ),
        RUNG(
            CMP("STATE=7"),
            OTE("STATE7_IND"),
        ),
        RUNG(
            XIC("STATE7_IND"),
            XIO("LAT_state7_entry_oneshot_storage"),
            OTE("LAT_state7_entry_oneshot"),
        ),
        RUNG(
            XIC("STATE7_IND"),
            OTL("LAT_state7_entry_oneshot_storage"),
        ),
        RUNG(
            XIO("STATE7_IND"),
            OTU("LAT_state7_entry_oneshot_storage"),
        ),
        RUNG(
            XIC("LAT_state7_entry_oneshot"),
            RES("HomeCounter"),
        ),
        RUNG(
            XIC("LAT_state7_entry_oneshot_storage"),
            XIO("HomeCounter.DN"),
            XIO("HomeTimer2.TT"),
            TON("HomeTimer1", "500", "0"),
        ),
        RUNG(
            XIC("LAT_state7_entry_oneshot_storage"),
            XIO("HomeCounter.DN"),
            XIO("HomeTimer1.TT"),
            TON("HomeTimer2", "500", "0"),
        ),
        RUNG(
            XIC("LAT_state7_entry_oneshot_storage"),
            XIO("HomeCounter.DN"),
            XIC("HomeTimer1.TT"),
            CTU("HomeCounter", "100", "0"),
        ),
        RUNG(
            XIC("HomeCounter.DN"),
            XIC("sometag"),
            OTE("Local:3:O.Pt02.Data"),
        ),
        RUNG(
            XIC("HomeCounter.DN"),
            XIO("LAT_home_counter_done_oneshot_storage"),
            OTE("LAT_home_counter_done_oneshot"),
        ),
        RUNG(
            XIC("HomeCounter.DN"),
            OTL("LAT_home_counter_done_oneshot_storage"),
        ),
        RUNG(
            XIO("HomeCounter.DN"),
            OTU("LAT_home_counter_done_oneshot_storage"),
        ),
        RUNG(
            XIC("LAT_home_counter_done_oneshot"),
            XIC("Z_STAGE_LATCHED"),
            OTL("LATCH_ACTUATOR_HOMED"),
        ),
        RUNG(
            XIC("LAT_home_counter_done_oneshot"),
            XIO("Z_STAGE_LATCHED"),
            CPT("ERROR_CODE", "7002"),
            OTL("LATCH_ACTUATOR_HOMED"),
        ),
        RUNG(
            XIC("LATCH_ACTUATOR_HOMED"),
            OTE("MACHINE_SW_STAT[0]"),
        ),
        RUNG(
            XIC("LATCH_ACTUATOR_HOMED"),
            XIO("LAT_latch_actuator_homed_oneshot_storage"),
            OTE("LAT_latch_actuator_homed_oneshot"),
        ),
        RUNG(
            XIC("LATCH_ACTUATOR_HOMED"),
            OTL("LAT_latch_actuator_homed_oneshot_storage"),
        ),
        RUNG(
            XIO("LATCH_ACTUATOR_HOMED"),
            OTU("LAT_latch_actuator_homed_oneshot_storage"),
        ),
        RUNG(
            XIC("LAT_latch_actuator_homed_oneshot"),
            RES("LatchCounter3"),
        ),
        RUNG(
            XIC("LAT_latch_actuator_homed_oneshot_storage"),
            XIO("LatchCounter3.DN"),
            XIO("LatchTimer6.TT"),
            TON("LatchTimer5", "250", "0"),
        ),
        RUNG(
            XIC("LAT_latch_actuator_homed_oneshot_storage"),
            XIO("LatchCounter3.DN"),
            XIO("LatchTimer5.TT"),
            TON("LatchTimer6", "250", "0"),
        ),
        RUNG(
            XIC("LAT_latch_actuator_homed_oneshot_storage"),
            XIO("LatchCounter3.DN"),
            XIC("LatchTimer5.TT"),
            CTU("LatchCounter3", "100", "0"),
        ),
        RUNG(
            XIC("LatchCounter3.DN"),
            XIO("LAT_home_verify_done_oneshot_storage"),
            OTE("LAT_home_verify_done_oneshot"),
        ),
        RUNG(
            XIC("LatchCounter3.DN"),
            OTL("LAT_home_verify_done_oneshot_storage"),
        ),
        RUNG(
            XIO("LatchCounter3.DN"),
            OTU("LAT_home_verify_done_oneshot_storage"),
        ),
        RUNG(
            XIC("STATE7_IND"),
            XIC("LAT_home_verify_done_oneshot"),
            CPT("ERROR_CODE", "7000"),
            OTU("HomeSignal"),
            CPT("MOVE_TYPE", "0"),
            CPT("NEXTSTATE", "1"),
        ),
        RUNG(
            BRANCH([CMP("STATE=8")], [XIC("UNLOCK_LATCH_MOTOR_SHAFT")]),
            OTE("STATE8_IND"),
        ),
        RUNG(
            XIC("STATE8_IND"),
            XIC("sometag"),
            OTE("Local:3:O.Pt02.Data"),
        ),
        RUNG(
            XIC("Local:3:O.Pt02.Data"),
            CPT("ERROR_CODE", "8000"),
        ),
        RUNG(
            XIC("STATE8_IND"),
            XIO("LAT_state8_entry_oneshot_storage"),
            OTE("LAT_state8_entry_oneshot"),
        ),
        RUNG(
            XIC("STATE8_IND"),
            OTL("LAT_state8_entry_oneshot_storage"),
        ),
        RUNG(
            XIO("STATE8_IND"),
            OTU("LAT_state8_entry_oneshot_storage"),
        ),
        RUNG(
            XIC("LAT_state8_entry_oneshot"),
            OTU("LATCH_ACTUATOR_HOMED"),
        ),
        RUNG(
            XIC("LAT_state8_entry_oneshot"),
            RES("LatchCounter2"),
        ),
        RUNG(
            XIC("LAT_state8_entry_oneshot_storage"),
            XIO("LatchCounter2.DN"),
            XIO("LatchTimer4.TT"),
            TON("LatchTimer3", "250", "0"),
        ),
        RUNG(
            XIC("LAT_state8_entry_oneshot_storage"),
            XIO("LatchCounter2.DN"),
            XIO("LatchTimer3.TT"),
            TON("LatchTimer4", "250", "0"),
        ),
        RUNG(
            XIC("LAT_state8_entry_oneshot_storage"),
            XIO("LatchCounter2.DN"),
            XIC("LatchTimer3.TT"),
            CTU("LatchCounter2", "100", "0"),
        ),
        RUNG(
            XIC("STATE8_IND"),
            XIC("LatchCounter2.DN"),
            CMP("MOVE_TYPE=0"),
            CPT("NEXTSTATE", "1"),
        ),
        RUNG(
            BRANCH(
                [XIC("Latching_pulse_duration.TT")],
                [XIC("LatchTimer4.TT")],
                [XIC("HomeTimer2.TT")],
                [XIC("LatchTimer6.TT")],
            ),
            OTE("Local:3:O.Pt01.Data"),
            OTE("latching_signal"),
        ),
        RUNG(
            XIC("Z_STAGE_PRESENT"),
            OTU("gui_latch_pulse"),
        ),
        RUNG(
            XIC("Z_STAGE_PRESENT"),
            XIO("Z_FIXED_PRESENT"),
            OTE("unsafe_to_latch"),
        ),
        RUNG(
            XIC("gui_latch_pulse"),
            XIO("unsafe_to_latch"),
            OTL("Local:3:O.Pt01.Data"),
            TON("gui_latch_pulse_timer", "100", "0"),
        ),
        RUNG(
            XIC("gui_latch_pulse_timer.DN"),
            RES("gui_latch_pulse_timer"),
            OTU("gui_latch_pulse"),
        ),
        RUNG(
            BRANCH([CMP("STATE=6")], [CMP("STATE=7")]),
            XIO("LAT_latching_timeout_monitor_oneshot_storage"),
            OTE("LAT_latching_timeout_monitor_oneshot"),
        ),
        RUNG(
            BRANCH([CMP("STATE=6")], [CMP("STATE=7")]),
            OTL("LAT_latching_timeout_monitor_oneshot_storage"),
        ),
        RUNG(
            BRANCH([NEQ("STATE", "6")], [NEQ("STATE", "7")]),
            OTU("LAT_latching_timeout_monitor_oneshot_storage"),
        ),
        RUNG(
            XIC("LAT_latching_timeout_monitor_oneshot"),
            RES("LatchingTimeoutCounter"),
        ),
        RUNG(
            XIC("LAT_latching_timeout_monitor_oneshot_storage"),
            XIO("LatchingTimeoutCounter.DN"),
            XIO("TimeoutTimer2.TT"),
            TON("TimeoutTimer1", "250", "0"),
        ),
        RUNG(
            XIC("LAT_latching_timeout_monitor_oneshot_storage"),
            XIO("LatchingTimeoutCounter.DN"),
            XIO("TimeoutTimer1.TT"),
            TON("TimeoutTimer2", "250", "0"),
        ),
        RUNG(
            XIC("LAT_latching_timeout_monitor_oneshot_storage"),
            XIO("LatchingTimeoutCounter.DN"),
            XIC("TimeoutTimer1.TT"),
            CTU("LatchingTimeoutCounter", "100", "0"),
        ),
        RUNG(
            XIC("LatchingTimeoutCounter.DN"),
            XIO("LAT_latching_timeout_done_oneshot_storage"),
            OTE("LAT_latching_timeout_done_oneshot"),
        ),
        RUNG(
            XIC("LatchingTimeoutCounter.DN"),
            OTL("LAT_latching_timeout_done_oneshot_storage"),
        ),
        RUNG(
            XIO("LatchingTimeoutCounter.DN"),
            OTU("LAT_latching_timeout_done_oneshot_storage"),
        ),
        RUNG(
            XIC("LAT_latching_timeout_done_oneshot"),
            CMP("STATE=6"),
            CPT("ERROR_CODE", "6002"),
            CPT("NEXTSTATE", "10"),
        ),
        RUNG(
            XIC("INIT_DONE"),
            CMP("STATE=9"),
            OTE("STATE9_IND"),
        ),
        RUNG(
            XIC("STATE9_IND"),
            XIO("US9_state9_entry_oneshot_storage"),
            OTE("US9_state9_entry_oneshot"),
        ),
        RUNG(
            XIC("STATE9_IND"),
            OTL("US9_state9_entry_oneshot_storage"),
        ),
        RUNG(
            XIO("STATE9_IND"),
            OTU("US9_state9_entry_oneshot_storage"),
        ),
        RUNG(
            XIC("STATE9_IND"),
            XIC("US9_state9_entry_oneshot"),
            MSF("X_axis", "US9_x_axis_unservo_status"),
        ),
        RUNG(
            XIC("STATE9_IND"),
            XIC("US9_state9_entry_oneshot"),
            MSF("Y_axis", "US9_y_axis_unservo_status"),
        ),
        RUNG(
            XIC("STATE9_IND"),
            XIC("US9_state9_entry_oneshot"),
            MSF("Z_axis", "US9_z_axis_unservo_status"),
        ),
        RUNG(
            XIC("US9_x_axis_unservo_status.DN"),
            XIO("US9_x_unservo_done_oneshot_storage"),
            OTE("US9_x_unservo_done_oneshot"),
        ),
        RUNG(
            XIC("US9_x_axis_unservo_status.DN"),
            OTL("US9_x_unservo_done_oneshot_storage"),
        ),
        RUNG(
            XIO("US9_x_axis_unservo_status.DN"),
            OTU("US9_x_unservo_done_oneshot_storage"),
        ),
        RUNG(
            XIC("US9_x_unservo_done_oneshot"),
            MAFR("X_axis", "US9_x_axis_fault_reset_status"),
        ),
        RUNG(
            XIC("US9_y_axis_unservo_status.DN"),
            XIO("US9_y_unservo_done_oneshot_storage"),
            OTE("US9_y_unservo_done_oneshot"),
        ),
        RUNG(
            XIC("US9_y_axis_unservo_status.DN"),
            OTL("US9_y_unservo_done_oneshot_storage"),
        ),
        RUNG(
            XIO("US9_y_axis_unservo_status.DN"),
            OTU("US9_y_unservo_done_oneshot_storage"),
        ),
        RUNG(
            XIC("US9_y_unservo_done_oneshot"),
            MAFR("Y_axis", "US9_y_axis_fault_reset_status"),
        ),
        RUNG(
            XIC("US9_z_axis_unservo_status.DN"),
            XIO("US9_z_unservo_done_oneshot_storage"),
            OTE("US9_z_unservo_done_oneshot"),
        ),
        RUNG(
            XIC("US9_z_axis_unservo_status.DN"),
            OTL("US9_z_unservo_done_oneshot_storage"),
        ),
        RUNG(
            XIO("US9_z_axis_unservo_status.DN"),
            OTU("US9_z_unservo_done_oneshot_storage"),
        ),
        RUNG(
            XIC("US9_z_unservo_done_oneshot"),
            MAFR("Z_axis", "US9_z_axis_fault_reset_status"),
        ),
        RUNG(
            XIC("STATE9_IND"),
            XIC("US9_x_axis_fault_reset_status.DN"),
            XIC("US9_y_axis_fault_reset_status.DN"),
            XIC("US9_z_axis_fault_reset_status.DN"),
            CMP("MOVE_TYPE=0"),
            CPT("NEXTSTATE", "1"),
        ),
        RUNG(
            XIC("INIT_DONE"),
            CMP("STATE=10"),
            OTE("STATE10_IND"),
        ),
        RUNG(
            XIC("STATE10_IND"),
            XIO("ERR10_state10_entry_oneshot_storage"),
            OTE("ERR10_state10_entry_oneshot"),
        ),
        RUNG(
            XIC("STATE10_IND"),
            OTL("ERR10_state10_entry_oneshot_storage"),
        ),
        RUNG(
            XIO("STATE10_IND"),
            OTU("ERR10_state10_entry_oneshot_storage"),
        ),
        RUNG(
            XIC("ERR10_state10_entry_oneshot"),
            MCS(
                "X_Y",
                "ERR10_xy_group_stop_status",
                "All",
                "Yes",
                "1000",
                '"Units per sec2"',
                "Yes",
                "1000",
                '"Units per sec3"',
            ),
        ),
        RUNG(
            XIC("ERR10_state10_entry_oneshot"),
            MAS(
                "Z_axis",
                "ERR10_z_axis_stop_status",
                "All",
                "Yes",
                "1000",
                '"Units per sec2"',
                "No",
                "10000",
                '"% of Time"',
            ),
        ),
        RUNG(
            XIC("ERR10_xy_group_stop_status.PC"),
            XIC("ERR10_z_axis_stop_status.PC"),
            XIO("ERR10_motion_stop_done_oneshot_storage"),
            OTE("ERR10_motion_stop_done_oneshot"),
        ),
        RUNG(
            XIC("ERR10_xy_group_stop_status.PC"),
            XIC("ERR10_z_axis_stop_status.PC"),
            OTL("ERR10_motion_stop_done_oneshot_storage"),
        ),
        RUNG(
            BRANCH(
                [XIO("ERR10_xy_group_stop_status.PC")],
                [XIO("ERR10_z_axis_stop_status.PC")],
            ),
            OTU("ERR10_motion_stop_done_oneshot_storage"),
        ),
        RUNG(
            XIC("ERR10_motion_stop_done_oneshot"),
            XIC("error_servo_off"),
            MSF("X_axis", "ERR10_x_axis_unservo_status"),
        ),
        RUNG(
            XIC("ERR10_motion_stop_done_oneshot"),
            XIC("error_servo_off"),
            MSF("Y_axis", "ERR10_y_axis_unservo_status"),
        ),
        RUNG(
            XIC("ERR10_motion_stop_done_oneshot"),
            XIC("error_servo_off"),
            MSF("Z_axis", "ERR10_z_axis_unservo_status"),
        ),
        RUNG(
            XIC("ERR10_x_axis_unservo_status.DN"),
            XIC("ERR10_y_axis_unservo_status.DN"),
            XIC("ERR10_z_axis_unservo_status.DN"),
            CMP("MOVE_TYPE=0"),
            XIO("ERR10_servo_off_done_oneshot_storage"),
            OTE("ERR10_servo_off_done_oneshot"),
        ),
        RUNG(
            XIC("ERR10_x_axis_unservo_status.DN"),
            XIC("ERR10_y_axis_unservo_status.DN"),
            XIC("ERR10_z_axis_unservo_status.DN"),
            CMP("MOVE_TYPE=0"),
            OTL("ERR10_servo_off_done_oneshot_storage"),
        ),
        RUNG(
            BRANCH(
                [XIO("ERR10_x_axis_unservo_status.DN")],
                [XIO("ERR10_y_axis_unservo_status.DN")],
                [XIO("ERR10_z_axis_unservo_status.DN")],
                [NEQ("MOVE_TYPE", "0")],
            ),
            OTU("ERR10_servo_off_done_oneshot_storage"),
        ),
        RUNG(
            XIC("ERR10_servo_off_done_oneshot"),
            MAFR("Z_axis", "ERR10_z_axis_fault_reset_status"),
        ),
        RUNG(
            XIC("ERR10_z_axis_fault_reset_status.DN"),
            MAFR("Y_axis", "ERR10_y_axis_fault_reset_status"),
        ),
        RUNG(
            XIC("ERR10_y_axis_fault_reset_status.DN"),
            MAFR("X_axis", "ERR10_x_axis_fault_reset_status"),
        ),
        RUNG(
            XIC("ERR10_z_axis_unservo_status.DN"),
            XIC("ERR10_y_axis_unservo_status.DN"),
            XIC("ERR10_x_axis_unservo_status.DN"),
            CMP("MOVE_TYPE=0"),
            CMP("STATE=10"),
            CPT("ERROR_CODE", "0"),
            CPT("NEXTSTATE", "1"),
        ),
        RUNG(
            XIO("ALL_EOT_GOOD"),
            OTE("STATE11_IND"),
        ),
        RUNG(
            XIC("STATE11_IND"),
            XIO("EOT11_state11_entry_oneshot_storage"),
            OTE("EOT11_state11_entry_oneshot"),
        ),
        RUNG(
            XIC("STATE11_IND"),
            OTL("EOT11_state11_entry_oneshot_storage"),
        ),
        RUNG(
            XIO("STATE11_IND"),
            OTU("EOT11_state11_entry_oneshot_storage"),
        ),
        RUNG(
            XIC("EOT11_state11_entry_oneshot"),
            MCS(
                "X_Y",
                "EOT11_xy_group_stop_status",
                "All",
                "Yes",
                "10000",
                '"Units per sec2"',
                "Yes",
                "10000",
                '"Units per sec3"',
            ),
        ),
        RUNG(
            XIC("STATE11_IND"),
            XIC("EOT11_xy_group_stop_status.DN"),
            XIO("EOT11_axes_stopped_oneshot_storage"),
            OTE("EOT11_axes_stopped_oneshot"),
        ),
        RUNG(
            XIC("STATE11_IND"),
            XIC("EOT11_xy_group_stop_status.DN"),
            OTL("EOT11_axes_stopped_oneshot_storage"),
        ),
        RUNG(
            BRANCH([XIO("STATE11_IND")], [XIO("EOT11_xy_group_stop_status.DN")]),
            OTU("EOT11_axes_stopped_oneshot_storage"),
        ),
        RUNG(
            XIC("EOT11_axes_stopped_oneshot"),
            MSO("X_axis", "EOT11_x_axis_servo_on_status"),
            MSO("Y_axis", "EOT11_y_axis_servo_on_status"),
            MSO("Z_axis", "EOT11_z_axis_servo_on_status"),
        ),
        RUNG(
            XIC("EOT11_state11_entry_oneshot"),
            MAS(
                "X_axis",
                "EOT11_x_axis_abort_status",
                "All",
                "Yes",
                "1000",
                '"Units per sec2"',
                "Yes",
                "1000",
                '"Units per sec3"',
            ),
        ),
        RUNG(
            XIC("EOT11_state11_entry_oneshot"),
            MAS(
                "Y_axis",
                "EOT11_y_axis_abort_status",
                "All",
                "Yes",
                "1000",
                '"Units per sec2"',
                "Yes",
                "1000",
                '"Units per sec3"',
            ),
        ),
        RUNG(
            XIC("EOT11_state11_entry_oneshot"),
            MAS(
                "Z_axis",
                "EOT11_z_axis_abort_status",
                "All",
                "Yes",
                "1000",
                '"Units per sec2"',
                "Yes",
                "1000",
                '"Units per sec3"',
            ),
        ),
        RUNG(
            XIC("STATE11_IND"),
            OTE("AbortQueue"),
        ),
        RUNG(
            XIC("STATE11_IND"),
            CPT("MOVE_TYPE", "0"),
        ),
        RUNG(
            XIC("STATE11_IND"),
            XIC("EOT11_xy_group_stop_status.DN"),
            XIC("EOT11_x_axis_servo_on_status.DN"),
            XIC("EOT11_y_axis_servo_on_status.DN"),
            XIC("EOT11_z_axis_servo_on_status.DN"),
            XIO("PLUS_X_EOT"),
            XIC("MINUS_X_EOT"),
            XIO("EOT11_minus_x_recovery_move_status.IP"),
            XIO("EOT11_minus_x_recovery_oneshot_storage"),
            OTE("EOT11_minus_x_recovery_oneshot"),
        ),
        RUNG(
            XIC("STATE11_IND"),
            XIC("EOT11_xy_group_stop_status.DN"),
            XIC("EOT11_x_axis_servo_on_status.DN"),
            XIC("EOT11_y_axis_servo_on_status.DN"),
            XIC("EOT11_z_axis_servo_on_status.DN"),
            XIO("PLUS_X_EOT"),
            XIC("MINUS_X_EOT"),
            XIO("EOT11_minus_x_recovery_move_status.IP"),
            OTL("EOT11_minus_x_recovery_oneshot_storage"),
        ),
        RUNG(
            BRANCH(
                [XIO("STATE11_IND")],
                [XIO("EOT11_xy_group_stop_status.DN")],
                [XIO("EOT11_x_axis_servo_on_status.DN")],
                [XIO("EOT11_y_axis_servo_on_status.DN")],
                [XIO("EOT11_z_axis_servo_on_status.DN")],
                [XIC("PLUS_X_EOT")],
                [XIO("MINUS_X_EOT")],
                [XIC("EOT11_minus_x_recovery_move_status.IP")],
            ),
            OTU("EOT11_minus_x_recovery_oneshot_storage"),
        ),
        RUNG(
            XIC("EOT11_minus_x_recovery_oneshot"),
            MAM(
                "X_axis",
                "EOT11_minus_x_recovery_move_status",
                "1",
                "-1",
                "25",
                '"Units per sec"',
                "100",
                '"Units per sec2"',
                "100",
                '"Units per sec2"',
                "S-Curve",
                "100",
                "100",
                '"% of Time"',
                "Disabled",
                "0",
                "0",
                "0",
                "0",
                "0",
            ),
        ),
        RUNG(
            XIC("STATE11_IND"),
            XIC("EOT11_xy_group_stop_status.DN"),
            XIC("EOT11_x_axis_servo_on_status.DN"),
            XIC("EOT11_y_axis_servo_on_status.DN"),
            XIC("EOT11_z_axis_servo_on_status.DN"),
            XIO("MINUS_X_EOT"),
            XIC("PLUS_X_EOT"),
            XIO("EOT11_plus_x_recovery_move_status.IP"),
            XIO("EOT11_plus_x_recovery_oneshot_storage"),
            OTE("EOT11_plus_x_recovery_oneshot"),
        ),
        RUNG(
            XIC("STATE11_IND"),
            XIC("EOT11_xy_group_stop_status.DN"),
            XIC("EOT11_x_axis_servo_on_status.DN"),
            XIC("EOT11_y_axis_servo_on_status.DN"),
            XIC("EOT11_z_axis_servo_on_status.DN"),
            XIO("MINUS_X_EOT"),
            XIC("PLUS_X_EOT"),
            XIO("EOT11_plus_x_recovery_move_status.IP"),
            OTL("EOT11_plus_x_recovery_oneshot_storage"),
        ),
        RUNG(
            BRANCH(
                [XIO("STATE11_IND")],
                [XIO("EOT11_xy_group_stop_status.DN")],
                [XIO("EOT11_x_axis_servo_on_status.DN")],
                [XIO("EOT11_y_axis_servo_on_status.DN")],
                [XIO("EOT11_z_axis_servo_on_status.DN")],
                [XIC("MINUS_X_EOT")],
                [XIO("PLUS_X_EOT")],
                [XIC("EOT11_plus_x_recovery_move_status.IP")],
            ),
            OTU("EOT11_plus_x_recovery_oneshot_storage"),
        ),
        RUNG(
            XIC("EOT11_plus_x_recovery_oneshot"),
            MAM(
                "X_axis",
                "EOT11_plus_x_recovery_move_status",
                "1",
                "10",
                "25",
                '"Units per sec"',
                "100",
                '"Units per sec2"',
                "100",
                '"Units per sec2"',
                "S-Curve",
                "100",
                "100",
                '"% of Time"',
                "Disabled",
                "0",
                "0",
                "0",
                "0",
                "0",
            ),
        ),
        RUNG(
            XIC("STATE11_IND"),
            XIC("EOT11_xy_group_stop_status.DN"),
            XIC("EOT11_x_axis_servo_on_status.DN"),
            XIC("EOT11_y_axis_servo_on_status.DN"),
            XIC("EOT11_z_axis_servo_on_status.DN"),
            XIO("PLUS_Y_EOT"),
            XIC("MINUS_Y_EOT"),
            XIO("EOT11_minus_y_recovery_move_status.IP"),
            XIO("EOT11_minus_y_recovery_oneshot_storage"),
            OTE("EOT11_minus_y_recovery_oneshot"),
        ),
        RUNG(
            XIC("STATE11_IND"),
            XIC("EOT11_xy_group_stop_status.DN"),
            XIC("EOT11_x_axis_servo_on_status.DN"),
            XIC("EOT11_y_axis_servo_on_status.DN"),
            XIC("EOT11_z_axis_servo_on_status.DN"),
            XIO("PLUS_Y_EOT"),
            XIC("MINUS_Y_EOT"),
            XIO("EOT11_minus_y_recovery_move_status.IP"),
            OTL("EOT11_minus_y_recovery_oneshot_storage"),
        ),
        RUNG(
            BRANCH(
                [XIO("STATE11_IND")],
                [XIO("EOT11_xy_group_stop_status.DN")],
                [XIO("EOT11_x_axis_servo_on_status.DN")],
                [XIO("EOT11_y_axis_servo_on_status.DN")],
                [XIO("EOT11_z_axis_servo_on_status.DN")],
                [XIC("PLUS_Y_EOT")],
                [XIO("MINUS_Y_EOT")],
                [XIC("EOT11_minus_y_recovery_move_status.IP")],
            ),
            OTU("EOT11_minus_y_recovery_oneshot_storage"),
        ),
        RUNG(
            XIC("EOT11_minus_y_recovery_oneshot"),
            MAM(
                "Y_axis",
                "EOT11_minus_y_recovery_move_status",
                "1",
                "-1",
                "25",
                '"Units per sec"',
                "100",
                '"Units per sec2"',
                "100",
                '"Units per sec2"',
                "S-Curve",
                "100",
                "100",
                '"% of Time"',
                "Disabled",
                "0",
                "0",
                "0",
                "0",
                "0",
            ),
        ),
        RUNG(
            XIC("STATE11_IND"),
            XIC("EOT11_xy_group_stop_status.DN"),
            XIC("EOT11_x_axis_servo_on_status.DN"),
            XIC("EOT11_y_axis_servo_on_status.DN"),
            XIC("EOT11_z_axis_servo_on_status.DN"),
            XIO("MINUS_Y_EOT"),
            XIC("PLUS_Y_EOT"),
            XIO("EOT11_plus_y_recovery_move_status.IP"),
            XIO("EOT11_plus_y_recovery_oneshot_storage"),
            OTE("EOT11_plus_y_recovery_oneshot"),
        ),
        RUNG(
            XIC("STATE11_IND"),
            XIC("EOT11_xy_group_stop_status.DN"),
            XIC("EOT11_x_axis_servo_on_status.DN"),
            XIC("EOT11_y_axis_servo_on_status.DN"),
            XIC("EOT11_z_axis_servo_on_status.DN"),
            XIO("MINUS_Y_EOT"),
            XIC("PLUS_Y_EOT"),
            XIO("EOT11_plus_y_recovery_move_status.IP"),
            OTL("EOT11_plus_y_recovery_oneshot_storage"),
        ),
        RUNG(
            BRANCH(
                [XIO("STATE11_IND")],
                [XIO("EOT11_xy_group_stop_status.DN")],
                [XIO("EOT11_x_axis_servo_on_status.DN")],
                [XIO("EOT11_y_axis_servo_on_status.DN")],
                [XIO("EOT11_z_axis_servo_on_status.DN")],
                [XIC("MINUS_Y_EOT")],
                [XIO("PLUS_Y_EOT")],
                [XIC("EOT11_plus_y_recovery_move_status.IP")],
            ),
            OTU("EOT11_plus_y_recovery_oneshot_storage"),
        ),
        RUNG(
            XIC("EOT11_plus_y_recovery_oneshot"),
            MAM(
                "Y_axis",
                "EOT11_plus_y_recovery_move_status",
                "1",
                "1",
                "25",
                '"Units per sec"',
                "100",
                '"Units per sec2"',
                "100",
                '"Units per sec2"',
                "S-Curve",
                "100",
                "100",
                '"% of Time"',
                "Disabled",
                "0",
                "0",
                "0",
                "0",
                "0",
            ),
        ),
        RUNG(
            XIC("STATE11_IND"),
            XIC("EOT11_xy_group_stop_status.DN"),
            XIC("EOT11_x_axis_servo_on_status.DN"),
            XIC("EOT11_y_axis_servo_on_status.DN"),
            XIC("EOT11_z_axis_servo_on_status.DN"),
            XIO("Z_EOT"),
            XIO("EOT11_z_clearance_move_status.IP"),
            XIO("EOT11_z_clearance_move_oneshot_storage"),
            OTE("EOT11_z_clearance_move_oneshot"),
        ),
        RUNG(
            XIC("STATE11_IND"),
            XIC("EOT11_xy_group_stop_status.DN"),
            XIC("EOT11_x_axis_servo_on_status.DN"),
            XIC("EOT11_y_axis_servo_on_status.DN"),
            XIC("EOT11_z_axis_servo_on_status.DN"),
            XIO("Z_EOT"),
            XIO("EOT11_z_clearance_move_status.IP"),
            OTL("EOT11_z_clearance_move_oneshot_storage"),
        ),
        RUNG(
            BRANCH(
                [XIO("STATE11_IND")],
                [XIO("EOT11_xy_group_stop_status.DN")],
                [XIO("EOT11_x_axis_servo_on_status.DN")],
                [XIO("EOT11_y_axis_servo_on_status.DN")],
                [XIO("EOT11_z_axis_servo_on_status.DN")],
                [XIC("Z_EOT")],
                [XIC("EOT11_z_clearance_move_status.IP")],
            ),
            OTU("EOT11_z_clearance_move_oneshot_storage"),
        ),
        RUNG(
            XIC("EOT11_z_clearance_move_oneshot"),
            MAM(
                "Z_axis",
                "EOT11_z_clearance_move_status",
                "0",
                "0",
                "25",
                '"Units per sec"',
                "100",
                '"Units per sec2"',
                "100",
                '"Units per sec2"',
                "S-Curve",
                "100",
                "100",
                '"% of Time"',
                "Disabled",
                "0",
                "0",
                "0",
                "0",
                "0",
            ),
        ),
        RUNG(
            XIC("ALL_EOT_GOOD"),
            XIO("EOT11_z_clearance_move_status.IP"),
            XIO("EOT11_all_eot_good_oneshot_storage"),
            OTE("EOT11_all_eot_good_oneshot"),
        ),
        RUNG(
            XIC("ALL_EOT_GOOD"),
            XIO("EOT11_z_clearance_move_status.IP"),
            OTL("EOT11_all_eot_good_oneshot_storage"),
        ),
        RUNG(
            BRANCH([XIO("ALL_EOT_GOOD")], [XIC("EOT11_z_clearance_move_status.IP")]),
            OTU("EOT11_all_eot_good_oneshot_storage"),
        ),
        RUNG(
            XIC("EOT11_all_eot_good_oneshot"),
            MAS(
                "X_axis",
                "EOT11_x_axis_recovery_stop_a_status",
                "Move",
                "No",
                "1000",
                '"Units per sec2"',
                "Yes",
                "1000",
                '"Units per sec3"',
            ),
        ),
        RUNG(
            XIC("EOT11_all_eot_good_oneshot"),
            MAS(
                "X_axis",
                "EOT11_x_axis_recovery_stop_b_status",
                "Move",
                "No",
                "1000",
                '"Units per sec2"',
                "Yes",
                "1000",
                '"Units per sec3"',
            ),
        ),
        RUNG(
            XIC("EOT11_all_eot_good_oneshot"),
            MAS(
                "Y_axis",
                "EOT11_y_axis_recovery_stop_a_status",
                "Move",
                "No",
                "1000",
                '"Units per sec2"',
                "Yes",
                "1000",
                '"Units per sec3"',
            ),
        ),
        RUNG(
            XIC("EOT11_all_eot_good_oneshot"),
            MAS(
                "Y_axis",
                "EOT11_y_axis_recovery_stop_b_status",
                "Move",
                "No",
                "1000",
                '"Units per sec2"',
                "Yes",
                "1000",
                '"Units per sec3"',
            ),
        ),
        RUNG(
            XIC("EOT11_all_eot_good_oneshot"),
            MAS(
                "Z_axis",
                "EOT11_z_axis_recovery_stop_status",
                "Move",
                "No",
                "1000",
                '"Units per sec2"',
                "Yes",
                "1000",
                '"Units per sec3"',
            ),
        ),
        RUNG(
            XIC("EOT11_all_eot_good_oneshot"),
            CPT("ERROR_CODE", "0"),
            CPT("NEXTSTATE", "1"),
        ),
        RUNG(
            CMP("STATE=12"),
            OTE("STATE12_IND"),
        ),
        RUNG(
            XIC("STATE12_IND"),
            XIO("Y_XFER_OK"),
            CPT("ERROR_CODE", "5003"),
            CPT("MOVE_TYPE", "0"),
            CPT("NEXTSTATE", "10"),
        ),
        RUNG(
            XIC("STATE12_IND"),
            XIC("Y_XFER_OK"),
            XIO("xz_main_move.IP"),
            MCLM(
                "xz",
                "xz_main_move",
                "0",
                "xz_position_target",
                "800",
                '"Units per sec"',
                "1000",
                '"Units per sec2"',
                "1000",
                '"Units per sec2"',
                "S-Curve",
                "1000",
                "1000",
                '"Units per sec3"',
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
            ),
        ),
        RUNG(
            XIO("Y_XFER_OK"),
            XIC("xz_main_move.IP"),
            MCS(
                "X_Y",
                "XZ_xy_stop",
                "All",
                "Yes",
                "4000",
                '"Units per sec2"',
                "Yes",
                "2000",
                '"Units per sec3"',
            ),
            MCS(
                "xz",
                "xz_stop",
                "All",
                "Yes",
                "4000",
                '"Units per sec2"',
                "Yes",
                "200",
                '"Units per sec3"',
            ),
            CPT("MOVE_TYPE", "0"),
            CPT("ERROR_CODE", "5003"),
            CPT("NEXTSTATE", "10"),
        ),
        RUNG(
            XIC("STATE12_IND"),
            XIC("xz_main_move.ER"),
            CPT("MOVE_TYPE", "0"),
            CPT("ERROR_CODE", "5003"),
            CPT("NEXTSTATE", "10"),
        ),
        RUNG(
            XIC("STATE12_IND"),
            CMP("ABS(X_axis.ActualPosition-xz_position_target[0])<0.1"),
            CMP("ABS(Z_axis.ActualPosition-xz_position_target[1])<0.1"),
            CPT("MOVE_TYPE", "0"),
            CPT("NEXTSTATE", "1"),
        ),
        RUNG(
            XIC("Y_axis.MoveStatus"),
            XIO("Z_RETRACTED"),
            MAS(
                "Y_axis",
                "y_axis_stop",
                "All",
                "Yes",
                "4000",
                '"Units per sec2"',
                "Yes",
                "4000",
                '"Units per sec3"',
            ),
        ),
        RUNG(
            CMP("STATE=13"),
            OTE("YZ_STATE13_IND"),
        ),
        RUNG(
            XIC("YZ_STATE13_IND"),
            XIO("X_XFER_OK"),
            CPT("ERROR_CODE", "5003"),
            CPT("MOVE_TYPE", "0"),
            CPT("NEXTSTATE", "10"),
        ),
        RUNG(
            XIC("YZ_STATE13_IND"),
            XIC("X_XFER_OK"),
            XIO("yz_main_move.IP"),
            MCLM(
                "xz",
                "yz_main_move",
                "0",
                "xz_position_target",
                "800",
                '"Units per sec"',
                "1000",
                '"Units per sec2"',
                "1000",
                '"Units per sec2"',
                "S-Curve",
                "1000",
                "1000",
                '"Units per sec3"',
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
            ),
        ),
        RUNG(
            XIO("Y_XFER_OK"),
            XIC("yz_main_move.IP"),
            MCS(
                "X_Y",
                "YZ_xy_stop",
                "All",
                "Yes",
                "4000",
                '"Units per sec2"',
                "Yes",
                "2000",
                '"Units per sec3"',
            ),
            MCS(
                "xz",
                "yz_stop",
                "All",
                "Yes",
                "4000",
                '"Units per sec2"',
                "Yes",
                "200",
                '"Units per sec3"',
            ),
            CPT("MOVE_TYPE", "0"),
            CPT("ERROR_CODE", "5003"),
            CPT("NEXTSTATE", "10"),
        ),
        RUNG(
            XIC("YZ_STATE13_IND"),
            XIC("yz_main_move.ER"),
            CPT("MOVE_TYPE", "0"),
            CPT("ERROR_CODE", "5003"),
            CPT("NEXTSTATE", "10"),
        ),
        RUNG(
            XIC("YZ_STATE13_IND"),
            CMP("ABS(X_axis.ActualPosition-xz_position_target[0])<0.1"),
            CMP("ABS(Z_axis.ActualPosition-xz_position_target[1])<0.1"),
            CPT("MOVE_TYPE", "0"),
            CPT("NEXTSTATE", "1"),
        ),
        RUNG(
            XIC("X_axis.MoveStatus"),
            XIO("Z_RETRACTED"),
            MAS(
                "X_axis",
                "x_axis_stop",
                "All",
                "Yes",
                "4000",
                '"Units per sec2"',
                "Yes",
                "4000",
                '"Units per sec3"',
            ),
        ),
        RUNG(
            CMP("STATE=14"),
            OTE("STATE14_IND"),
        ),
        RUNG(
            XIC("STATE14_IND"),
            XIO("hmi_stop_entry_sb"),
            OTE("hmi_stop_entry_ob"),
        ),
        RUNG(
            XIC("STATE14_IND"),
            OTL("hmi_stop_entry_sb"),
        ),
        RUNG(
            XIO("STATE14_IND"),
            OTU("hmi_stop_entry_sb"),
        ),
        RUNG(
            XIC("hmi_stop_entry_ob"),
            MCS(
                "X_Y",
                "hmi_xy_stop",
                "All",
                "Yes",
                "1200",
                '"Units per sec2"',
                "Yes",
                "1200",
                '"Units per sec3"',
            ),
        ),
        RUNG(
            XIC("hmi_stop_entry_ob"),
            MCS(
                "xz",
                "hmi_xz_stop",
                "All",
                "Yes",
                "1200",
                '"Units per sec2"',
                "Yes",
                "1200",
                '"Units per sec3"',
            ),
        ),
        RUNG(
            XIC("hmi_stop_entry_ob"),
            MAS(
                "X_axis",
                "hmi_x_axis_stop",
                "All",
                "Yes",
                "1200",
                '"Units per sec2"',
                "Yes",
                "1200",
                '"Units per sec3"',
            ),
        ),
        RUNG(
            XIC("hmi_stop_entry_ob"),
            MAS(
                "Y_axis",
                "hmi_y_axis_stop",
                "All",
                "Yes",
                "1200",
                '"Units per sec2"',
                "Yes",
                "1200",
                '"Units per sec3"',
            ),
        ),
        RUNG(
            XIC("hmi_stop_entry_ob"),
            MAS(
                "Z_axis",
                "hmi_z_axis_stop",
                "All",
                "Yes",
                "1200",
                '"Units per sec2"',
                "Yes",
                "1200",
                '"Units per sec3"',
            ),
        ),
        RUNG(
            XIC("STATE14_IND"),
            OTE("AbortQueue"),
        ),
        RUNG(
            XIC("STATE14_IND"),
            CPT("MOVE_TYPE", "0"),
        ),
        RUNG(
            XIC("STATE14_IND"),
            XIC("hmi_xy_stop.DN"),
            XIC("hmi_xz_stop.DN"),
            XIC("hmi_x_axis_stop.DN"),
            XIC("hmi_y_axis_stop.DN"),
            XIC("hmi_z_axis_stop.DN"),
            XIO("CurIssued"),
            XIO("NextIssued"),
            XIO("X_Y.MovePendingStatus"),
            LEQ("QueueCount", "0"),
            CPT("NEXTSTATE", "1"),
        ),
        RUNG(
            EQU("QueueCtl.POS", "0"),
            OTE("QueueEmpty"),
        ),
        RUNG(
            GEQ("QueueCtl.POS", "32"),
            OTE("QueueFull"),
        ),
        RUNG(
            MOV("QueueCtl.POS", "QueueCount"),
        ),
        RUNG(
            CMP("MOVE_TYPE=11"),
            OTL("AbortQueue"),
            CPT("NEXTSTATE", "14"),
        ),
        RUNG(
            XIC("QueueStopRequest"),
            BRANCH(
                [XIC("CurIssued")], [XIC("NextIssued")], [XIC("X_Y.MovePendingStatus")]
            ),
            ONS("QueueStopReqONS"),
            MCS(
                "X_Y",
                "gui_stop",
                "All",
                "Yes",
                "2000",
                '"Units per sec2"',
                "Yes",
                "1000",
                '"Units per sec3"',
            ),
        ),
        RUNG(
            XIC("QueueStopRequest"),
            OTL("AbortQueue"),
        ),
        RUNG(
            BRANCH([XIC("AbortQueue")], [XIO("ALL_EOT_GOOD")]),
            OTE("AbortActive"),
        ),
        RUNG(
            NEQ("IncomingSegReqID", "LastIncomingSegReqID"),
            OTL("EnqueueReq"),
        ),
        RUNG(
            XIC("EnqueueReq"),
            XIC("IncomingSeg.Valid"),
            EQU("IncomingSeg.SegType", "1"),
            GRT("IncomingSeg.Speed", "0.0"),
            GRT("IncomingSeg.Accel", "0.0"),
            GRT("IncomingSeg.Decel", "0.0"),
            GEQ("IncomingSeg.TermType", "0"),
            LEQ("IncomingSeg.TermType", "6"),
            OTE("SegValidLine"),
        ),
        RUNG(
            XIC("EnqueueReq"),
            XIC("IncomingSeg.Valid"),
            EQU("IncomingSeg.SegType", "2"),
            GRT("IncomingSeg.Speed", "0.0"),
            GRT("IncomingSeg.Accel", "0.0"),
            GRT("IncomingSeg.Decel", "0.0"),
            GEQ("IncomingSeg.TermType", "0"),
            LEQ("IncomingSeg.TermType", "6"),
            GEQ("IncomingSeg.CircleType", "0"),
            LEQ("IncomingSeg.CircleType", "3"),
            GEQ("IncomingSeg.Direction", "0"),
            LEQ("IncomingSeg.Direction", "3"),
            OTE("SegValidArc"),
        ),
        RUNG(
            BRANCH([XIC("SegValidLine")], [XIC("SegValidArc")]),
            OTE("SegValid"),
        ),
        RUNG(
            XIC("EnqueueReq"),
            XIC("SegValid"),
            XIO("QueueFull"),
            FFL("IncomingSeg", "SegQueue[0]", "QueueCtl", "32", "0"),
        ),
        RUNG(
            XIC("EnqueueReq"),
            XIC("SegValid"),
            XIO("QueueFull"),
            MOV("IncomingSeg.Seq", "IncomingSegAck"),
        ),
        RUNG(
            XIC("EnqueueReq"),
            XIC("SegValid"),
            XIO("QueueFull"),
            MOV("IncomingSegReqID", "LastIncomingSegReqID"),
        ),
        RUNG(
            XIC("EnqueueReq"),
            OTU("EnqueueReq"),
        ),
        RUNG(
            XIC("MoveA.ER"),
            MOV("3", "FaultCode"),
        ),
        RUNG(
            XIC("MoveA.ER"),
            OTL("QueueFault"),
        ),
        RUNG(
            XIC("MoveA.ER"),
            OTL("AbortQueue"),
        ),
        RUNG(
            XIC("MoveA.ER"),
            OTU("MoveA.ER"),
        ),
        RUNG(
            XIC("MoveB.ER"),
            MOV("4", "FaultCode"),
        ),
        RUNG(
            XIC("MoveB.ER"),
            OTL("QueueFault"),
        ),
        RUNG(
            XIC("MoveB.ER"),
            OTL("AbortQueue"),
        ),
        RUNG(
            XIC("MoveB.ER"),
            OTU("MoveB.ER"),
        ),
        RUNG(
            BRANCH([XIC("QueueFault")], [XIC("MoveA.ER")], [XIC("MoveB.ER")]),
            OTE("MotionFault"),
        ),
        RUNG(
            XIC("CheckCurSeg"),
            XIC("CurSeg.Valid"),
            GRT("CurSeg.Seq", "0"),
            BRANCH([EQU("CurSeg.SegType", "1")], [EQU("CurSeg.SegType", "2")]),
            OTL("PrepCurMove"),
        ),
        RUNG(
            XIC("CheckCurSeg"),
            XIO("CurSeg.Valid"),
            MOV("1", "FaultCode"),
        ),
        RUNG(
            XIC("CheckCurSeg"),
            XIO("CurSeg.Valid"),
            OTL("QueueFault"),
        ),
        RUNG(
            XIC("CheckCurSeg"),
            XIC("CurSeg.Valid"),
            LEQ("CurSeg.Seq", "0"),
            MOV("6", "FaultCode"),
        ),
        RUNG(
            XIC("CheckCurSeg"),
            XIC("CurSeg.Valid"),
            LEQ("CurSeg.Seq", "0"),
            OTL("QueueFault"),
        ),
        RUNG(
            XIC("CheckCurSeg"),
            XIC("CurSeg.Valid"),
            GRT("CurSeg.Seq", "0"),
            BRANCH([LES("CurSeg.SegType", "1")], [GRT("CurSeg.SegType", "2")]),
            MOV("7", "FaultCode"),
        ),
        RUNG(
            XIC("CheckCurSeg"),
            XIC("CurSeg.Valid"),
            GRT("CurSeg.Seq", "0"),
            BRANCH([LES("CurSeg.SegType", "1")], [GRT("CurSeg.SegType", "2")]),
            OTL("QueueFault"),
        ),
        RUNG(
            XIC("CheckCurSeg"),
            OTU("CheckCurSeg"),
        ),
        RUNG(
            XIC("CheckNextSeg"),
            XIC("NextSeg.Valid"),
            GRT("NextSeg.Seq", "0"),
            BRANCH([EQU("NextSeg.SegType", "1")], [EQU("NextSeg.SegType", "2")]),
            OTL("PrepNextMove"),
        ),
        RUNG(
            XIC("CheckNextSeg"),
            XIO("NextSeg.Valid"),
            MOV("2", "FaultCode"),
        ),
        RUNG(
            XIC("CheckNextSeg"),
            XIO("NextSeg.Valid"),
            OTL("QueueFault"),
        ),
        RUNG(
            XIC("CheckNextSeg"),
            XIC("NextSeg.Valid"),
            LEQ("NextSeg.Seq", "0"),
            MOV("5", "FaultCode"),
        ),
        RUNG(
            XIC("CheckNextSeg"),
            XIC("NextSeg.Valid"),
            LEQ("NextSeg.Seq", "0"),
            OTL("QueueFault"),
        ),
        RUNG(
            XIC("CheckNextSeg"),
            XIC("NextSeg.Valid"),
            GRT("NextSeg.Seq", "0"),
            BRANCH([LES("NextSeg.SegType", "1")], [GRT("NextSeg.SegType", "2")]),
            MOV("8", "FaultCode"),
        ),
        RUNG(
            XIC("CheckNextSeg"),
            XIC("NextSeg.Valid"),
            GRT("NextSeg.Seq", "0"),
            BRANCH([LES("NextSeg.SegType", "1")], [GRT("NextSeg.SegType", "2")]),
            OTL("QueueFault"),
        ),
        RUNG(
            XIC("CheckNextSeg"),
            OTU("CheckNextSeg"),
        ),
        RUNG(
            XIO("CurIssued"),
            XIO("NextIssued"),
            XIO("QueueFault"),
            GEQ("QueueCtl.POS", "1"),
            MOV("QueueCtl.POS", "DINTS[5]"),
        ),
        RUNG(
            BRANCH(
                [XIC("CurIssued")],
                [XIC("NextIssued")],
                [XIC("QueueFault")],
                [LEQ("QueueCtl.POS", "0")],
            ),
            MOV("0", "DINTS[5]"),
        ),
        RUNG(
            XIO("CurIssued"),
            XIO("NextIssued"),
            XIO("QueueFault"),
            GEQ("QueueCtl.POS", "1"),
            MOV("v_x_max", "REALS[38]"),
        ),
        RUNG(
            XIO("CurIssued"),
            XIO("NextIssued"),
            XIO("QueueFault"),
            GEQ("QueueCtl.POS", "1"),
            MOV("v_y_max", "REALS[39]"),
        ),
        RUNG(
            XIO("CurIssued"),
            XIO("NextIssued"),
            XIO("QueueFault"),
            GEQ("QueueCtl.POS", "1"),
            MOV("X_axis.ActualPosition", "REALS[40]"),
        ),
        RUNG(
            XIO("CurIssued"),
            XIO("NextIssued"),
            XIO("QueueFault"),
            GEQ("QueueCtl.POS", "1"),
            MOV("Y_axis.ActualPosition", "REALS[41]"),
        ),
        RUNG(
            XIO("CurIssued"),
            XIO("NextIssued"),
            XIO("QueueFault"),
            GEQ("QueueCtl.POS", "1"),
            OTL("BOOLS[7]"),
        ),
        RUNG(
            NEQ("DINTS[5]", "0"),
            JMP("MQ_cap_lbl_else_46"),
        ),
        RUNG(
            JMP("MQ_cap_lbl_CapSegSpeed_end"),
        ),
        RUNG(
            LBL("MQ_cap_lbl_else_46"),
            BRANCH([LEQ("REALS[38]", "0.0")], [LEQ("REALS[39]", "0.0")]),
            OTL("BOOLS[901]"),
        ),
        RUNG(
            GRT("REALS[38]", "0.0"),
            GRT("REALS[39]", "0.0"),
            JMP("MQ_cap_lbl_else_48"),
        ),
        RUNG(
            OTL("BOOLS[8]"),
        ),
        RUNG(
            JMP("MQ_cap_lbl_CapSegSpeed_end"),
        ),
        RUNG(
            LBL("MQ_cap_lbl_else_48"),
            BRANCH(
                [LES("REALS[38]", "3.4028235E+38")], [LES("REALS[39]", "3.4028235E+38")]
            ),
            OTL("BOOLS[902]"),
        ),
        RUNG(
            XIC("BOOLS[902]"),
            JMP("MQ_cap_lbl_else_50"),
        ),
        RUNG(
            JMP("MQ_cap_lbl_CapSegSpeed_end"),
        ),
        RUNG(
            LBL("MQ_cap_lbl_else_50"),
            XIC("BOOLS[7]"),
            JMP("MQ_cap_lbl_else_52"),
        ),
        RUNG(
            MOV("SegQueue[0].XY[0]", "REALS[42]"),
        ),
        RUNG(
            MOV("SegQueue[0].XY[1]", "REALS[43]"),
        ),
        RUNG(
            OTL("BOOLS[9]"),
        ),
        RUNG(
            JMP("MQ_cap_lbl_end_53"),
        ),
        RUNG(
            LBL("MQ_cap_lbl_else_52"),
            MOV("REALS[40]", "REALS[42]"),
        ),
        RUNG(
            MOV("REALS[41]", "REALS[43]"),
        ),
        RUNG(
            OTU("BOOLS[9]"),
        ),
        RUNG(
            LBL("MQ_cap_lbl_end_53"),
            MOV("0", "idx_3"),
        ),
        RUNG(
            LBL("MQ_cap_lbl_loop_54"),
            GEQ("idx_3", "DINTS[5]"),
            JMP("MQ_cap_lbl_loop_end_55"),
        ),
        RUNG(
            BRANCH([NEQ("idx_3", "0")], [XIO("BOOLS[9]")]),
            OTL("BOOLS[903]"),
        ),
        RUNG(
            XIC("BOOLS[903]"),
            JMP("MQ_cap_lbl_else_56"),
        ),
        RUNG(
            LES("REALS[38]", "REALS[39]"),
            JMP("MQ_cap_lbl_min_a_58"),
        ),
        RUNG(
            MOV("REALS[39]", "REALS[44]"),
            JMP("MQ_cap_lbl_min_end_59"),
        ),
        RUNG(
            LBL("MQ_cap_lbl_min_a_58"),
            MOV("REALS[38]", "REALS[44]"),
        ),
        RUNG(
            LBL("MQ_cap_lbl_min_end_59"),
            MOV("1.0", "REALS[45]"),
        ),
        RUNG(
            MOV("1.0", "REALS[46]"),
        ),
        RUNG(
            JMP("MQ_cap_lbl_end_57"),
        ),
        RUNG(
            LBL("MQ_cap_lbl_else_56"),
            MOV("REALS[42]", "REALS[20]"),
        ),
        RUNG(
            MOV("REALS[43]", "REALS[21]"),
        ),
        RUNG(
            MOV("idx_3", "idx_2"),
        ),
        RUNG(
            NEQ("SegQueue[idx_2].SegType", "1"),
            JMP("MQ_seg_lbl_else_30"),
        ),
        RUNG(
            CPT("REALS[24]", "SegQueue[idx_2].XY[0]-REALS[20]"),
        ),
        RUNG(
            CPT("REALS[25]", "SegQueue[idx_2].XY[1]-REALS[21]"),
        ),
        RUNG(
            CPT("REALS[26]", "SQR(REALS[24]*REALS[24]+REALS[25]*REALS[25])"),
        ),
        RUNG(
            GRT("REALS[26]", "0.000000001"),
            JMP("MQ_seg_lbl_else_32"),
        ),
        RUNG(
            MOV("0.0", "REALS[22]"),
        ),
        RUNG(
            MOV("0.0", "REALS[23]"),
        ),
        RUNG(
            JMP("MQ_seg_lbl_SegTangentBounds_end"),
        ),
        RUNG(
            LBL("MQ_seg_lbl_else_32"),
            CPT("REALS[22]", "ABS(REALS[24]/REALS[26])"),
        ),
        RUNG(
            CPT("REALS[23]", "ABS(REALS[25]/REALS[26])"),
        ),
        RUNG(
            JMP("MQ_seg_lbl_SegTangentBounds_end"),
        ),
        RUNG(
            LBL("MQ_seg_lbl_else_30"),
            NEQ("SegQueue[idx_2].SegType", "2"),
            JMP("MQ_seg_lbl_else_34"),
        ),
        RUNG(
            MOV("idx_2", "idx_0"),
        ),
        RUNG(
            MOV("idx_2", "idx_1"),
        ),
        RUNG(
            NEQ("REALS[28]", "0"),
            JMP("MQ_seg_lbl_else_36"),
        ),
        RUNG(
            CPT(
                "REALS[31]",
                "SQR(REALS[20]-REALS[29]*REALS[20]-REALS[29]+REALS[21]-REALS[30]*REALS[21]-REALS[30])",
            ),
        ),
        RUNG(
            CPT(
                "REALS[32]",
                "SQR(SegQueue[idx_2].XY[0]-REALS[29]*SegQueue[idx_2].XY[0]-REALS[29]+SegQueue[idx_2].XY[1]-REALS[30]*SegQueue[idx_2].XY[1]-REALS[30])",
            ),
        ),
        RUNG(
            BRANCH(
                [LEQ("REALS[31]", "0.000000001")], [LEQ("REALS[32]", "0.000000001")]
            ),
            OTL("BOOLS[900]"),
        ),
        RUNG(
            XIC("BOOLS[900]"),
            JMP("MQ_seg_lbl_else_38"),
        ),
        RUNG(
            CPT("REALS[912]", "REALS[21]-REALS[30]"),
        ),
        RUNG(
            CPT("REALS[913]", "REALS[20]-REALS[29]"),
        ),
        RUNG(
            GRT("REALS[913]", "0.0"),
            CPT("REALS[33]", "ATN(REALS[912]/REALS[913])"),
            JMP("MQ_seg_lbl_atan2_done_40"),
        ),
        RUNG(
            LES("REALS[913]", "0.0"),
            GEQ("REALS[912]", "0.0"),
            CPT("REALS[33]", "ATN(REALS[912]/REALS[913])+3.14159265358979"),
            JMP("MQ_seg_lbl_atan2_done_40"),
        ),
        RUNG(
            LES("REALS[913]", "0.0"),
            LES("REALS[912]", "0.0"),
            CPT("REALS[33]", "ATN(REALS[912]/REALS[913])-3.14159265358979"),
            JMP("MQ_seg_lbl_atan2_done_40"),
        ),
        RUNG(
            EQU("REALS[913]", "0.0"),
            GRT("REALS[912]", "0.0"),
            MOV("1.5707963267949", "REALS[33]"),
            JMP("MQ_seg_lbl_atan2_done_40"),
        ),
        RUNG(
            EQU("REALS[913]", "0.0"),
            LES("REALS[912]", "0.0"),
            MOV("-1.5707963267949", "REALS[33]"),
            JMP("MQ_seg_lbl_atan2_done_40"),
        ),
        RUNG(
            MOV("0.0", "REALS[33]"),
        ),
        RUNG(
            LBL("MQ_seg_lbl_atan2_done_40"),
            CPT("REALS[914]", "SegQueue[idx_2].XY[1]-REALS[30]"),
        ),
        RUNG(
            CPT("REALS[915]", "SegQueue[idx_2].XY[0]-REALS[29]"),
        ),
        RUNG(
            GRT("REALS[915]", "0.0"),
            CPT("REALS[34]", "ATN(REALS[914]/REALS[915])"),
            JMP("MQ_seg_lbl_atan2_done_41"),
        ),
        RUNG(
            LES("REALS[915]", "0.0"),
            GEQ("REALS[914]", "0.0"),
            CPT("REALS[34]", "ATN(REALS[914]/REALS[915])+3.14159265358979"),
            JMP("MQ_seg_lbl_atan2_done_41"),
        ),
        RUNG(
            LES("REALS[915]", "0.0"),
            LES("REALS[914]", "0.0"),
            CPT("REALS[34]", "ATN(REALS[914]/REALS[915])-3.14159265358979"),
            JMP("MQ_seg_lbl_atan2_done_41"),
        ),
        RUNG(
            EQU("REALS[915]", "0.0"),
            GRT("REALS[914]", "0.0"),
            MOV("1.5707963267949", "REALS[34]"),
            JMP("MQ_seg_lbl_atan2_done_41"),
        ),
        RUNG(
            EQU("REALS[915]", "0.0"),
            LES("REALS[914]", "0.0"),
            MOV("-1.5707963267949", "REALS[34]"),
            JMP("MQ_seg_lbl_atan2_done_41"),
        ),
        RUNG(
            MOV("0.0", "REALS[34]"),
        ),
        RUNG(
            LBL("MQ_seg_lbl_atan2_done_41"),
            MOV("REALS[33]", "REALS[14]"),
        ),
        RUNG(
            MOV("REALS[34]", "REALS[15]"),
        ),
        RUNG(
            MOV("SegQueue[idx_2].Direction", "DINTS[4]"),
        ),
        RUNG(
            CPT("REALS[17]", "2.0*3.14159265358979"),
        ),
        RUNG(
            CPT("REALS[910]", "REALS[15]-REALS[14]"),
        ),
        RUNG(
            MOD("REALS[910]", "REALS[17]", "REALS[18]"),
        ),
        RUNG(
            CPT("REALS[911]", "REALS[14]-REALS[15]"),
        ),
        RUNG(
            MOD("REALS[911]", "REALS[17]", "REALS[19]"),
        ),
        RUNG(
            NEQ("DINTS[4]", "0"),
            JMP("MQ_arc_lbl_else_18"),
        ),
        RUNG(
            CPT("REALS[16]", "-REALS[19]"),
        ),
        RUNG(
            JMP("MQ_arc_lbl_ArcSweepRad_end"),
        ),
        RUNG(
            LBL("MQ_arc_lbl_else_18"),
            NEQ("DINTS[4]", "1"),
            JMP("MQ_arc_lbl_else_20"),
        ),
        RUNG(
            MOV("REALS[18]", "REALS[16]"),
        ),
        RUNG(
            JMP("MQ_arc_lbl_ArcSweepRad_end"),
        ),
        RUNG(
            LBL("MQ_arc_lbl_else_20"),
            NEQ("DINTS[4]", "2"),
            JMP("MQ_arc_lbl_else_22"),
        ),
        RUNG(
            CPT("REALS[16]", "-REALS[19]"),
        ),
        RUNG(
            JMP("MQ_arc_lbl_ArcSweepRad_end"),
        ),
        RUNG(
            LBL("MQ_arc_lbl_else_22"),
            NEQ("DINTS[4]", "3"),
            JMP("MQ_arc_lbl_else_24"),
        ),
        RUNG(
            MOV("REALS[18]", "REALS[16]"),
        ),
        RUNG(
            JMP("MQ_arc_lbl_ArcSweepRad_end"),
        ),
        RUNG(
            LBL("MQ_arc_lbl_else_24"),
            OTU("BOOLS[3]"),
        ),
        RUNG(
            JMP("MQ_arc_lbl_ArcSweepRad_end"),
        ),
        RUNG(
            LBL("MQ_arc_lbl_ArcSweepRad_end"),
            NOP(),
        ),
        RUNG(
            MOV("REALS[16]", "REALS[35]"),
        ),
        RUNG(
            XIC("BOOLS[3]"),
            OTL("BOOLS[6]"),
        ),
        RUNG(
            XIO("BOOLS[3]"),
            OTU("BOOLS[6]"),
        ),
        RUNG(
            XIO("BOOLS[6]"),
            JMP("MQ_seg_lbl_else_42"),
        ),
        RUNG(
            MOV("REALS[33]", "REALS[0]"),
        ),
        RUNG(
            MOV("REALS[35]", "REALS[1]"),
        ),
        RUNG(
            CPT("REALS[3]", "REALS[0]+REALS[1]"),
        ),
        RUNG(
            LES("REALS[0]", "REALS[3]"),
            JMP("MQ_sin_lbl_min_a_0"),
        ),
        RUNG(
            MOV("REALS[3]", "REALS[4]"),
            JMP("MQ_sin_lbl_min_end_1"),
        ),
        RUNG(
            LBL("MQ_sin_lbl_min_a_0"),
            MOV("REALS[0]", "REALS[4]"),
        ),
        RUNG(
            LBL("MQ_sin_lbl_min_end_1"),
            GRT("REALS[0]", "REALS[3]"),
            JMP("MQ_sin_lbl_max_a_2"),
        ),
        RUNG(
            MOV("REALS[3]", "REALS[5]"),
            JMP("MQ_sin_lbl_max_end_3"),
        ),
        RUNG(
            LBL("MQ_sin_lbl_max_a_2"),
            MOV("REALS[0]", "REALS[5]"),
        ),
        RUNG(
            LBL("MQ_sin_lbl_max_end_3"),
            CPT("REALS[900]", "ABS(SIN(REALS[0]))"),
        ),
        RUNG(
            CPT("REALS[901]", "ABS(SIN(REALS[3]))"),
        ),
        RUNG(
            GRT("REALS[900]", "REALS[901]"),
            JMP("MQ_sin_lbl_max_a_4"),
        ),
        RUNG(
            MOV("REALS[901]", "REALS[6]"),
            JMP("MQ_sin_lbl_max_end_5"),
        ),
        RUNG(
            LBL("MQ_sin_lbl_max_a_4"),
            MOV("REALS[900]", "REALS[6]"),
        ),
        RUNG(
            LBL("MQ_sin_lbl_max_end_5"),
            CPT("REALS[902]", "REALS[4]-0.5*3.14159265358979/3.14159265358979"),
        ),
        RUNG(
            TRN("REALS[902]", "DINTS[900]"),
        ),
        RUNG(
            MOV("DINTS[900]", "REALS[903]"),
        ),
        RUNG(
            GEQ("REALS[903]", "REALS[902]"),
            JMP("MQ_sin_lbl_ceil_done_6"),
        ),
        RUNG(
            ADD("DINTS[900]", "1", "DINTS[900]"),
        ),
        RUNG(
            LBL("MQ_sin_lbl_ceil_done_6"),
            MOV("DINTS[900]", "DINTS[0]"),
        ),
        RUNG(
            CPT("REALS[904]", "REALS[5]-0.5*3.14159265358979/3.14159265358979"),
        ),
        RUNG(
            TRN("REALS[904]", "DINTS[1]"),
        ),
        RUNG(
            GRT("DINTS[0]", "DINTS[1]"),
            JMP("MQ_sin_lbl_else_7"),
        ),
        RUNG(
            MOV("1.0", "REALS[2]"),
        ),
        RUNG(
            JMP("MQ_sin_lbl_MaxAbsSinSweep_end"),
        ),
        RUNG(
            LBL("MQ_sin_lbl_else_7"),
            MOV("REALS[6]", "REALS[2]"),
        ),
        RUNG(
            JMP("MQ_sin_lbl_MaxAbsSinSweep_end"),
        ),
        RUNG(
            LBL("MQ_sin_lbl_MaxAbsSinSweep_end"),
            NOP(),
        ),
        RUNG(
            MOV("REALS[2]", "REALS[36]"),
        ),
        RUNG(
            MOV("REALS[33]", "REALS[7]"),
        ),
        RUNG(
            MOV("REALS[35]", "REALS[8]"),
        ),
        RUNG(
            CPT("REALS[10]", "REALS[7]+REALS[8]"),
        ),
        RUNG(
            LES("REALS[7]", "REALS[10]"),
            JMP("MQ_cos_lbl_min_a_9"),
        ),
        RUNG(
            MOV("REALS[10]", "REALS[11]"),
            JMP("MQ_cos_lbl_min_end_10"),
        ),
        RUNG(
            LBL("MQ_cos_lbl_min_a_9"),
            MOV("REALS[7]", "REALS[11]"),
        ),
        RUNG(
            LBL("MQ_cos_lbl_min_end_10"),
            GRT("REALS[7]", "REALS[10]"),
            JMP("MQ_cos_lbl_max_a_11"),
        ),
        RUNG(
            MOV("REALS[10]", "REALS[12]"),
            JMP("MQ_cos_lbl_max_end_12"),
        ),
        RUNG(
            LBL("MQ_cos_lbl_max_a_11"),
            MOV("REALS[7]", "REALS[12]"),
        ),
        RUNG(
            LBL("MQ_cos_lbl_max_end_12"),
            CPT("REALS[905]", "ABS(COS(REALS[7]))"),
        ),
        RUNG(
            CPT("REALS[906]", "ABS(COS(REALS[10]))"),
        ),
        RUNG(
            GRT("REALS[905]", "REALS[906]"),
            JMP("MQ_cos_lbl_max_a_13"),
        ),
        RUNG(
            MOV("REALS[906]", "REALS[13]"),
            JMP("MQ_cos_lbl_max_end_14"),
        ),
        RUNG(
            LBL("MQ_cos_lbl_max_a_13"),
            MOV("REALS[905]", "REALS[13]"),
        ),
        RUNG(
            LBL("MQ_cos_lbl_max_end_14"),
            CPT("REALS[907]", "REALS[11]/3.14159265358979"),
        ),
        RUNG(
            TRN("REALS[907]", "DINTS[901]"),
        ),
        RUNG(
            MOV("DINTS[901]", "REALS[908]"),
        ),
        RUNG(
            GEQ("REALS[908]", "REALS[907]"),
            JMP("MQ_cos_lbl_ceil_done_15"),
        ),
        RUNG(
            ADD("DINTS[901]", "1", "DINTS[901]"),
        ),
        RUNG(
            LBL("MQ_cos_lbl_ceil_done_15"),
            MOV("DINTS[901]", "DINTS[2]"),
        ),
        RUNG(
            CPT("REALS[909]", "REALS[12]/3.14159265358979"),
        ),
        RUNG(
            TRN("REALS[909]", "DINTS[3]"),
        ),
        RUNG(
            GRT("DINTS[2]", "DINTS[3]"),
            JMP("MQ_cos_lbl_else_16"),
        ),
        RUNG(
            MOV("1.0", "REALS[9]"),
        ),
        RUNG(
            JMP("MQ_cos_lbl_MaxAbsCosSweep_end"),
        ),
        RUNG(
            LBL("MQ_cos_lbl_else_16"),
            MOV("REALS[13]", "REALS[9]"),
        ),
        RUNG(
            JMP("MQ_cos_lbl_MaxAbsCosSweep_end"),
        ),
        RUNG(
            LBL("MQ_cos_lbl_MaxAbsCosSweep_end"),
            NOP(),
        ),
        RUNG(
            MOV("REALS[9]", "REALS[37]"),
        ),
        RUNG(
            MOV("REALS[36]", "REALS[22]"),
        ),
        RUNG(
            MOV("REALS[37]", "REALS[23]"),
        ),
        RUNG(
            JMP("MQ_seg_lbl_SegTangentBounds_end"),
        ),
        RUNG(
            LBL("MQ_seg_lbl_else_42"),
            NOP(),
        ),
        RUNG(
            LBL("MQ_seg_lbl_else_38"),
            NOP(),
        ),
        RUNG(
            LBL("MQ_seg_lbl_else_36"),
            NOP(),
        ),
        RUNG(
            LBL("MQ_seg_lbl_else_34"),
            CPT("REALS[24]", "SegQueue[idx_2].XY[0]-REALS[20]"),
        ),
        RUNG(
            CPT("REALS[25]", "SegQueue[idx_2].XY[1]-REALS[21]"),
        ),
        RUNG(
            CPT("REALS[26]", "SQR(REALS[24]*REALS[24]+REALS[25]*REALS[25])"),
        ),
        RUNG(
            GRT("REALS[26]", "0.000000001"),
            JMP("MQ_seg_lbl_else_44"),
        ),
        RUNG(
            MOV("0.0", "REALS[22]"),
        ),
        RUNG(
            MOV("0.0", "REALS[23]"),
        ),
        RUNG(
            JMP("MQ_seg_lbl_SegTangentBounds_end"),
        ),
        RUNG(
            LBL("MQ_seg_lbl_else_44"),
            CPT("REALS[22]", "ABS(REALS[24]/REALS[26])"),
        ),
        RUNG(
            CPT("REALS[23]", "ABS(REALS[25]/REALS[26])"),
        ),
        RUNG(
            JMP("MQ_seg_lbl_SegTangentBounds_end"),
        ),
        RUNG(
            LBL("MQ_seg_lbl_SegTangentBounds_end"),
            NOP(),
        ),
        RUNG(
            MOV("REALS[22]", "REALS[45]"),
        ),
        RUNG(
            MOV("REALS[23]", "REALS[46]"),
        ),
        RUNG(
            GRT("REALS[45]", "0.000000001"),
            JMP("MQ_cap_lbl_else_60"),
        ),
        RUNG(
            MOV("3.4028235E+38", "REALS[47]"),
        ),
        RUNG(
            JMP("MQ_cap_lbl_end_61"),
        ),
        RUNG(
            LBL("MQ_cap_lbl_else_60"),
            CPT("REALS[47]", "REALS[38]/REALS[45]"),
        ),
        RUNG(
            LBL("MQ_cap_lbl_end_61"),
            GRT("REALS[46]", "0.000000001"),
            JMP("MQ_cap_lbl_else_62"),
        ),
        RUNG(
            MOV("3.4028235E+38", "REALS[48]"),
        ),
        RUNG(
            JMP("MQ_cap_lbl_end_63"),
        ),
        RUNG(
            LBL("MQ_cap_lbl_else_62"),
            CPT("REALS[48]", "REALS[39]/REALS[46]"),
        ),
        RUNG(
            LBL("MQ_cap_lbl_end_63"),
            LES("REALS[47]", "REALS[48]"),
            JMP("MQ_cap_lbl_min_a_64"),
        ),
        RUNG(
            MOV("REALS[48]", "REALS[44]"),
            JMP("MQ_cap_lbl_min_end_65"),
        ),
        RUNG(
            LBL("MQ_cap_lbl_min_a_64"),
            MOV("REALS[47]", "REALS[44]"),
        ),
        RUNG(
            LBL("MQ_cap_lbl_min_end_65"),
            NOP(),
        ),
        RUNG(
            LBL("MQ_cap_lbl_end_57"),
            LES("SegQueue[idx_3].Speed", "REALS[44]"),
            JMP("MQ_cap_lbl_min_a_66"),
        ),
        RUNG(
            MOV("REALS[44]", "REALS[49]"),
            JMP("MQ_cap_lbl_min_end_67"),
        ),
        RUNG(
            LBL("MQ_cap_lbl_min_a_66"),
            MOV("SegQueue[idx_3].Speed", "REALS[49]"),
        ),
        RUNG(
            LBL("MQ_cap_lbl_min_end_67"),
            GRT("REALS[49]", "0.0"),
            JMP("MQ_cap_lbl_else_68"),
        ),
        RUNG(
            OTL("BOOLS[8]"),
        ),
        RUNG(
            JMP("MQ_cap_lbl_CapSegSpeed_end"),
        ),
        RUNG(
            LBL("MQ_cap_lbl_else_68"),
            MOV("REALS[49]", "SegQueue[idx_3].Speed"),
        ),
        RUNG(
            MOV("SegQueue[idx_3].XY[0]", "REALS[42]"),
        ),
        RUNG(
            MOV("SegQueue[idx_3].XY[1]", "REALS[43]"),
        ),
        RUNG(
            ADD("idx_3", "1", "idx_3"),
        ),
        RUNG(
            JMP("MQ_cap_lbl_loop_54"),
        ),
        RUNG(
            LBL("MQ_cap_lbl_loop_end_55"),
            JMP("MQ_cap_lbl_CapSegSpeed_end"),
        ),
        RUNG(
            LBL("MQ_cap_lbl_CapSegSpeed_end"),
            NOP(),
        ),
        RUNG(
            XIC("StartQueuedPath"),
            BRANCH(
                [
                    BRANCH(
                        [XIO("Z_RETRACTED")],
                        [GEQ("Z_axis.ActualPosition", "MAX_TOLERABLE_Z")],
                    ),
                    CPT("ERROR_CODE", "3001"),
                    CPT("NEXTSTATE", "10"),
                ],
                [
                    XIC("Z_RETRACTED"),
                    XIO("APA_IS_VERTICAL"),
                    CPT("ERROR_CODE", "3005"),
                    CPT("NEXTSTATE", "10"),
                ],
            ),
            OTE("AbortQueue"),
            OTU("StartQueuedPath"),
        ),
        RUNG(
            XIC("StartQueuedPath"),
            XIO("CurIssued"),
            XIO("QueueFault"),
            GEQ("QueueCtl.POS", "1"),
            ONS("StartCurONS"),
            OTL("LoadCurReq"),
        ),
        RUNG(
            XIC("LoadCurReq"),
            OTU("StartQueuedPath"),
        ),
        RUNG(
            XIC("LoadCurReq"),
            FFU("SegQueue[0]", "CurSeg", "QueueCtl", "32", "0"),
        ),
        RUNG(
            XIC("LoadCurReq"),
            OTL("CheckCurSeg"),
        ),
        RUNG(
            XIC("LoadCurReq"),
            OTU("LoadCurReq"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIC("UseAasCurrent"),
            COP("CurSeg.XY[0]", "CmdA_XY[0]", "2"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIC("UseAasCurrent"),
            MOV("CurSeg.Speed", "CmdA_Speed"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIC("UseAasCurrent"),
            MOV("CurSeg.Accel", "CmdA_Accel"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIC("UseAasCurrent"),
            MOV("CurSeg.Decel", "CmdA_Decel"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIC("UseAasCurrent"),
            MOV("CurSeg.JerkAccel", "CmdA_JerkAccel"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIC("UseAasCurrent"),
            MOV("CurSeg.JerkDecel", "CmdA_JerkDecel"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIC("UseAasCurrent"),
            MOV("CurSeg.TermType", "CmdA_TermType"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIC("UseAasCurrent"),
            MOV("CurSeg.SegType", "CmdA_SegType"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIC("UseAasCurrent"),
            MOV("CurSeg.CircleType", "CmdA_CircleType"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIC("UseAasCurrent"),
            COP("CurSeg.ViaCenter[0]", "CmdA_ViaCenter[0]", "2"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIC("UseAasCurrent"),
            MOV("CurSeg.Direction", "CmdA_Direction"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIC("UseAasCurrent"),
            MOV("CurSeg.Seq", "ActiveSeq"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIO("UseAasCurrent"),
            COP("CurSeg.XY[0]", "CmdB_XY[0]", "2"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIO("UseAasCurrent"),
            MOV("CurSeg.Speed", "CmdB_Speed"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIO("UseAasCurrent"),
            MOV("CurSeg.Accel", "CmdB_Accel"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIO("UseAasCurrent"),
            MOV("CurSeg.Decel", "CmdB_Decel"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIO("UseAasCurrent"),
            MOV("CurSeg.JerkAccel", "CmdB_JerkAccel"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIO("UseAasCurrent"),
            MOV("CurSeg.JerkDecel", "CmdB_JerkDecel"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIO("UseAasCurrent"),
            MOV("CurSeg.TermType", "CmdB_TermType"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIO("UseAasCurrent"),
            MOV("CurSeg.SegType", "CmdB_SegType"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIO("UseAasCurrent"),
            MOV("CurSeg.CircleType", "CmdB_CircleType"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIO("UseAasCurrent"),
            COP("CurSeg.ViaCenter[0]", "CmdB_ViaCenter[0]", "2"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIO("UseAasCurrent"),
            MOV("CurSeg.Direction", "CmdB_Direction"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIO("UseAasCurrent"),
            MOV("CurSeg.Seq", "ActiveSeq"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIO("APA_IS_VERTICAL"),
            MOV("3005", "FaultCode"),
            CPT("ERROR_CODE", "3005"),
            CPT("NEXTSTATE", "10"),
            OTL("QueueFault"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIC("APA_IS_VERTICAL"),
            XIC("X_Y.PhysicalAxisFault"),
            MOV("3002", "FaultCode"),
            CPT("ERROR_CODE", "3002"),
            CPT("NEXTSTATE", "10"),
            OTL("QueueFault"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIC("APA_IS_VERTICAL"),
            XIO("X_Y.PhysicalAxisFault"),
            XIC("X_axis.DriveEnableStatus"),
            XIC("Y_axis.DriveEnableStatus"),
            OTL("IssueCurPulse"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            XIC("APA_IS_VERTICAL"),
            XIO("X_Y.PhysicalAxisFault"),
            BRANCH(
                [XIO("X_axis.DriveEnableStatus")], [XIO("Y_axis.DriveEnableStatus")]
            ),
            OTL("WaitCurAxisOn"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            OTU("PrepCurMove"),
        ),
        RUNG(
            XIC("WaitCurAxisOn"),
            XIO("APA_IS_VERTICAL"),
            MOV("3005", "FaultCode"),
            CPT("ERROR_CODE", "3005"),
            CPT("NEXTSTATE", "10"),
            OTL("QueueFault"),
            OTU("WaitCurAxisOn"),
        ),
        RUNG(
            XIC("WaitCurAxisOn"),
            XIC("APA_IS_VERTICAL"),
            XIC("X_Y.PhysicalAxisFault"),
            MOV("3002", "FaultCode"),
            CPT("ERROR_CODE", "3002"),
            CPT("NEXTSTATE", "10"),
            OTL("QueueFault"),
            OTU("WaitCurAxisOn"),
        ),
        RUNG(
            XIC("WaitCurAxisOn"),
            XIC("APA_IS_VERTICAL"),
            XIO("X_Y.PhysicalAxisFault"),
            MSO("X_axis", "MQ_x_axis_mso"),
            MSO("Y_axis", "MQ_y_axis_mso"),
        ),
        RUNG(
            XIC("WaitCurAxisOn"),
            XIC("APA_IS_VERTICAL"),
            XIO("X_Y.PhysicalAxisFault"),
            XIC("MQ_x_axis_mso.DN"),
            XIC("MQ_y_axis_mso.DN"),
            OTL("IssueCurPulse"),
        ),
        RUNG(
            XIC("WaitCurAxisOn"),
            XIC("APA_IS_VERTICAL"),
            XIO("X_Y.PhysicalAxisFault"),
            XIC("MQ_x_axis_mso.DN"),
            XIC("MQ_y_axis_mso.DN"),
            OTU("WaitCurAxisOn"),
        ),
        RUNG(
            XIC("PrepCurMove"),
            OTU("PrepCurMove"),
        ),
        RUNG(
            XIC("IssueCurPulse"),
            XIC("UseAasCurrent"),
            EQU("CmdA_SegType", "1"),
            MCLM(
                "X_Y",
                "MoveA",
                "0",
                "CmdA_XY[0]",
                "CmdA_Speed",
                '"Units per sec"',
                "CmdA_Accel",
                '"Units per sec2"',
                "CmdA_Decel",
                '"Units per sec2"',
                "S-Curve",
                "CmdA_JerkAccel",
                "CmdA_JerkDecel",
                '"Units per sec3"',
                "CmdA_TermType",
                "Disabled",
                "Programmed",
                "CmdTolerance",
                "0",
                "None",
                "0",
                "0",
            ),
        ),
        RUNG(
            XIC("IssueCurPulse"),
            XIC("UseAasCurrent"),
            EQU("CmdA_SegType", "2"),
            MCCM(
                "X_Y",
                "MoveA",
                "0",
                "CmdA_XY[0]",
                "CmdA_CircleType",
                "CmdA_ViaCenter[0]",
                "CmdA_Direction",
                "CmdA_Speed",
                '"Units per sec"',
                "CmdA_Accel",
                '"Units per sec2"',
                "CmdA_Decel",
                '"Units per sec2"',
                "S-Curve",
                "CmdA_JerkAccel",
                "CmdA_JerkDecel",
                '"Units per sec3"',
                "CmdA_TermType",
                "Disabled",
                "Programmed",
                "CmdTolerance",
                "0",
                "None",
                "0",
                "0",
            ),
        ),
        RUNG(
            XIC("IssueCurPulse"),
            XIO("UseAasCurrent"),
            EQU("CmdB_SegType", "1"),
            MCLM(
                "X_Y",
                "MoveB",
                "0",
                "CmdB_XY[0]",
                "CmdB_Speed",
                '"Units per sec"',
                "CmdB_Accel",
                '"Units per sec2"',
                "CmdB_Decel",
                '"Units per sec2"',
                "S-Curve",
                "CmdB_JerkAccel",
                "CmdB_JerkDecel",
                '"Units per sec3"',
                "CmdB_TermType",
                "Disabled",
                "Programmed",
                "CmdTolerance",
                "0",
                "None",
                "0",
                "0",
            ),
        ),
        RUNG(
            XIC("IssueCurPulse"),
            XIO("UseAasCurrent"),
            EQU("CmdB_SegType", "2"),
            MCCM(
                "X_Y",
                "MoveB",
                "0",
                "CmdB_XY[0]",
                "CmdB_CircleType",
                "CmdB_ViaCenter[0]",
                "CmdB_Direction",
                "CmdB_Speed",
                '"Units per sec"',
                "CmdB_Accel",
                '"Units per sec2"',
                "CmdB_Decel",
                '"Units per sec2"',
                "S-Curve",
                "CmdB_JerkAccel",
                "CmdB_JerkDecel",
                '"Units per sec3"',
                "CmdB_TermType",
                "Disabled",
                "Programmed",
                "CmdTolerance",
                "0",
                "None",
                "0",
                "0",
            ),
        ),
        RUNG(
            XIC("IssueCurPulse"),
            OTL("CurIssued"),
        ),
        RUNG(
            XIC("IssueCurPulse"),
            OTU("IssueCurPulse"),
        ),
        RUNG(
            XIC("CurIssued"),
            XIC("UseAasCurrent"),
            XIC("MoveA.IP"),
            XIO("X_Y.MovePendingStatus"),
            XIO("NextIssued"),
            XIO("QueueEmpty"),
            XIO("QueueFault"),
            ONS("StartNextA_ONS"),
            OTL("LoadNextReq"),
        ),
        RUNG(
            XIC("CurIssued"),
            XIO("UseAasCurrent"),
            XIC("MoveB.IP"),
            XIO("X_Y.MovePendingStatus"),
            XIO("NextIssued"),
            XIO("QueueEmpty"),
            XIO("QueueFault"),
            ONS("StartNextB_ONS"),
            OTL("LoadNextReq"),
        ),
        RUNG(
            XIC("LoadNextReq"),
            FFU("SegQueue[0]", "NextSeg", "QueueCtl", "32", "0"),
        ),
        RUNG(
            XIC("LoadNextReq"),
            OTL("CheckNextSeg"),
        ),
        RUNG(
            XIC("LoadNextReq"),
            OTU("LoadNextReq"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIC("UseAasCurrent"),
            COP("NextSeg.XY[0]", "CmdB_XY[0]", "2"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIC("UseAasCurrent"),
            MOV("NextSeg.Speed", "CmdB_Speed"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIC("UseAasCurrent"),
            MOV("NextSeg.Accel", "CmdB_Accel"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIC("UseAasCurrent"),
            MOV("NextSeg.Decel", "CmdB_Decel"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIC("UseAasCurrent"),
            MOV("NextSeg.JerkAccel", "CmdB_JerkAccel"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIC("UseAasCurrent"),
            MOV("NextSeg.JerkDecel", "CmdB_JerkDecel"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIC("UseAasCurrent"),
            MOV("NextSeg.TermType", "CmdB_TermType"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIC("UseAasCurrent"),
            MOV("NextSeg.SegType", "CmdB_SegType"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIC("UseAasCurrent"),
            MOV("NextSeg.CircleType", "CmdB_CircleType"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIC("UseAasCurrent"),
            COP("NextSeg.ViaCenter[0]", "CmdB_ViaCenter[0]", "2"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIC("UseAasCurrent"),
            MOV("NextSeg.Direction", "CmdB_Direction"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIC("UseAasCurrent"),
            MOV("NextSeg.Seq", "PendingSeq"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIO("UseAasCurrent"),
            COP("NextSeg.XY[0]", "CmdA_XY[0]", "2"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIO("UseAasCurrent"),
            MOV("NextSeg.Speed", "CmdA_Speed"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIO("UseAasCurrent"),
            MOV("NextSeg.Accel", "CmdA_Accel"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIO("UseAasCurrent"),
            MOV("NextSeg.Decel", "CmdA_Decel"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIO("UseAasCurrent"),
            MOV("NextSeg.JerkAccel", "CmdA_JerkAccel"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIO("UseAasCurrent"),
            MOV("NextSeg.JerkDecel", "CmdA_JerkDecel"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIO("UseAasCurrent"),
            MOV("NextSeg.TermType", "CmdA_TermType"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIO("UseAasCurrent"),
            MOV("NextSeg.SegType", "CmdA_SegType"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIO("UseAasCurrent"),
            MOV("NextSeg.CircleType", "CmdA_CircleType"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIO("UseAasCurrent"),
            COP("NextSeg.ViaCenter[0]", "CmdA_ViaCenter[0]", "2"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIO("UseAasCurrent"),
            MOV("NextSeg.Direction", "CmdA_Direction"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIO("UseAasCurrent"),
            MOV("NextSeg.Seq", "PendingSeq"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIO("APA_IS_VERTICAL"),
            MOV("3005", "FaultCode"),
            CPT("ERROR_CODE", "3005"),
            CPT("NEXTSTATE", "10"),
            OTL("QueueFault"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIC("APA_IS_VERTICAL"),
            XIC("X_Y.PhysicalAxisFault"),
            MOV("3002", "FaultCode"),
            CPT("ERROR_CODE", "3002"),
            CPT("NEXTSTATE", "10"),
            OTL("QueueFault"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIC("APA_IS_VERTICAL"),
            XIO("X_Y.PhysicalAxisFault"),
            XIC("X_axis.DriveEnableStatus"),
            XIC("Y_axis.DriveEnableStatus"),
            OTL("MQ_IssueNextPulse"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            XIC("APA_IS_VERTICAL"),
            XIO("X_Y.PhysicalAxisFault"),
            BRANCH(
                [XIO("X_axis.DriveEnableStatus")], [XIO("Y_axis.DriveEnableStatus")]
            ),
            OTL("WaitNextAxisOn"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            OTU("PrepNextMove"),
        ),
        RUNG(
            XIC("WaitNextAxisOn"),
            XIO("APA_IS_VERTICAL"),
            MOV("3005", "FaultCode"),
            CPT("ERROR_CODE", "3005"),
            CPT("NEXTSTATE", "10"),
            OTL("QueueFault"),
            OTU("WaitNextAxisOn"),
        ),
        RUNG(
            XIC("WaitNextAxisOn"),
            XIC("APA_IS_VERTICAL"),
            XIC("X_Y.PhysicalAxisFault"),
            MOV("3002", "FaultCode"),
            CPT("ERROR_CODE", "3002"),
            CPT("NEXTSTATE", "10"),
            OTL("QueueFault"),
            OTU("WaitNextAxisOn"),
        ),
        RUNG(
            XIC("WaitNextAxisOn"),
            XIC("APA_IS_VERTICAL"),
            XIO("X_Y.PhysicalAxisFault"),
            MSO("X_axis", "MQ_x_axis_mso"),
            MSO("Y_axis", "MQ_y_axis_mso"),
        ),
        RUNG(
            XIC("WaitNextAxisOn"),
            XIC("APA_IS_VERTICAL"),
            XIO("X_Y.PhysicalAxisFault"),
            XIC("MQ_x_axis_mso.DN"),
            XIC("MQ_y_axis_mso.DN"),
            OTL("MQ_IssueNextPulse"),
        ),
        RUNG(
            XIC("WaitNextAxisOn"),
            XIC("APA_IS_VERTICAL"),
            XIO("X_Y.PhysicalAxisFault"),
            XIC("MQ_x_axis_mso.DN"),
            XIC("MQ_y_axis_mso.DN"),
            OTU("WaitNextAxisOn"),
        ),
        RUNG(
            XIC("PrepNextMove"),
            OTU("PrepNextMove"),
        ),
        RUNG(
            XIC("MQ_IssueNextPulse"),
            XIC("UseAasCurrent"),
            EQU("CmdB_SegType", "1"),
            MCLM(
                "X_Y",
                "MoveB",
                "0",
                "CmdB_XY[0]",
                "CmdB_Speed",
                '"Units per sec"',
                "CmdB_Accel",
                '"Units per sec2"',
                "CmdB_Decel",
                '"Units per sec2"',
                "S-Curve",
                "CmdB_JerkAccel",
                "CmdB_JerkDecel",
                '"Units per sec3"',
                "CmdB_TermType",
                "Disabled",
                "Programmed",
                "CmdTolerance",
                "0",
                "None",
                "0",
                "0",
            ),
        ),
        RUNG(
            XIC("MQ_IssueNextPulse"),
            XIC("UseAasCurrent"),
            EQU("CmdB_SegType", "2"),
            MCCM(
                "X_Y",
                "MoveB",
                "0",
                "CmdB_XY[0]",
                "CmdB_CircleType",
                "CmdB_ViaCenter[0]",
                "CmdB_Direction",
                "CmdB_Speed",
                '"Units per sec"',
                "CmdB_Accel",
                '"Units per sec2"',
                "CmdB_Decel",
                '"Units per sec2"',
                "S-Curve",
                "CmdB_JerkAccel",
                "CmdB_JerkDecel",
                '"Units per sec3"',
                "CmdB_TermType",
                "Disabled",
                "Programmed",
                "CmdTolerance",
                "0",
                "None",
                "0",
                "0",
            ),
        ),
        RUNG(
            XIC("MQ_IssueNextPulse"),
            XIO("UseAasCurrent"),
            EQU("CmdA_SegType", "1"),
            MCLM(
                "X_Y",
                "MoveA",
                "0",
                "CmdA_XY[0]",
                "CmdA_Speed",
                '"Units per sec"',
                "CmdA_Accel",
                '"Units per sec2"',
                "CmdA_Decel",
                '"Units per sec2"',
                "S-Curve",
                "CmdA_JerkAccel",
                "CmdA_JerkDecel",
                '"Units per sec3"',
                "CmdA_TermType",
                "Disabled",
                "Programmed",
                "CmdTolerance",
                "0",
                "None",
                "0",
                "0",
            ),
        ),
        RUNG(
            XIC("MQ_IssueNextPulse"),
            XIO("UseAasCurrent"),
            EQU("CmdA_SegType", "2"),
            MCCM(
                "X_Y",
                "MoveA",
                "0",
                "CmdA_XY[0]",
                "CmdA_CircleType",
                "CmdA_ViaCenter[0]",
                "CmdA_Direction",
                "CmdA_Speed",
                '"Units per sec"',
                "CmdA_Accel",
                '"Units per sec2"',
                "CmdA_Decel",
                '"Units per sec2"',
                "S-Curve",
                "CmdA_JerkAccel",
                "CmdA_JerkDecel",
                '"Units per sec3"',
                "CmdA_TermType",
                "Disabled",
                "Programmed",
                "CmdTolerance",
                "0",
                "None",
                "0",
                "0",
            ),
        ),
        RUNG(
            XIC("MQ_IssueNextPulse"),
            OTL("NextIssued"),
        ),
        RUNG(
            XIC("MQ_IssueNextPulse"),
            OTU("MQ_IssueNextPulse"),
        ),
        RUNG(
            XIC("CurIssued"),
            XIC("NextIssued"),
            XIC("UseAasCurrent"),
            XIO("X_Y.MovePendingStatus"),
            XIC("MoveB.IP"),
            ONS("RotateONS_AtoB"),
            OTL("RotateMoves"),
        ),
        RUNG(
            XIC("CurIssued"),
            XIC("NextIssued"),
            XIO("UseAasCurrent"),
            XIO("X_Y.MovePendingStatus"),
            XIC("MoveA.IP"),
            ONS("RotateONS_BtoA"),
            OTL("RotateMoves"),
        ),
        RUNG(
            XIC("RotateMoves"),
            COP("NextSeg", "CurSeg", "1"),
        ),
        RUNG(
            XIC("RotateMoves"),
            XIC("UseAasCurrent"),
            OTL("FlipToB"),
        ),
        RUNG(
            XIC("RotateMoves"),
            XIO("UseAasCurrent"),
            OTL("FlipToA"),
        ),
        RUNG(
            XIC("FlipToB"),
            OTU("UseAasCurrent"),
        ),
        RUNG(
            XIC("FlipToA"),
            OTL("UseAasCurrent"),
        ),
        RUNG(
            XIC("RotateMoves"),
            OTU("NextIssued"),
        ),
        RUNG(
            XIC("RotateMoves"),
            MOV("PendingSeq", "ActiveSeq"),
        ),
        RUNG(
            XIC("RotateMoves"),
            MOV("0", "PendingSeq"),
        ),
        RUNG(
            XIC("RotateMoves"),
            OTU("RotateMoves"),
        ),
        RUNG(
            XIC("FlipToA"),
            OTU("FlipToA"),
        ),
        RUNG(
            XIC("FlipToB"),
            OTU("FlipToB"),
        ),
        RUNG(
            XIC("CurIssued"),
            XIO("NextIssued"),
            XIC("UseAasCurrent"),
            XIO("X_Y.MovePendingStatus"),
            XIC("MoveA.PC"),
            ONS("DoneONS_A"),
            OTU("CurIssued"),
        ),
        RUNG(
            XIC("CurIssued"),
            XIO("NextIssued"),
            XIO("UseAasCurrent"),
            XIO("X_Y.MovePendingStatus"),
            XIC("MoveB.PC"),
            ONS("DoneONS_B"),
            OTU("CurIssued"),
        ),
        RUNG(
            XIC("AbortActive"),
            RES("CurIssueAckTON"),
        ),
        RUNG(
            XIC("AbortActive"),
            RES("NextIssueAckTON"),
        ),
        RUNG(
            XIC("AbortActive"),
            RES("QueueCtl"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTU("CurIssued"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTU("NextIssued"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTU("LoadCurReq"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTU("LoadNextReq"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTU("PrepCurMove"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTU("PrepNextMove"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTU("IssueCurPulse"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTU("MQ_IssueNextPulse"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTU("WaitCurAxisOn"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTU("WaitNextAxisOn"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTU("QueueStopRequest"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTU("AbortQueue"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTU("EnqueueReq"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTU("RotateMoves"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTU("FlipToA"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTU("FlipToB"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTL("UseAasCurrent"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTU("StartQueuedPath"),
        ),
        RUNG(
            XIC("AbortActive"),
            MOV("0", "FaultCode"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTU("QueueFault"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTU("CheckCurSeg"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTU("CheckNextSeg"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTU("CurSeg.Valid"),
        ),
        RUNG(
            XIC("AbortActive"),
            MOV("0", "CurSeg.Seq"),
        ),
        RUNG(
            XIC("AbortActive"),
            OTU("NextSeg.Valid"),
        ),
        RUNG(
            XIC("AbortActive"),
            MOV("0", "NextSeg.Seq"),
        ),
        RUNG(
            XIC("AbortActive"),
            MOV("IncomingSegReqID", "LastIncomingSegReqID"),
        ),
        RUNG(
            XIC("AbortActive"),
            MOV("0", "ActiveSeq"),
        ),
        RUNG(
            XIC("AbortActive"),
            MOV("0", "PendingSeq"),
        ),
        RUNG(
            XIC("AbortActive"),
            FLL("0", "SegQueue[0]", "32"),
        ),
    ),
)


def Monoroutine_main(ctx):
    api = bind_scan_context(ctx)
    tag = api.tag
    set_tag = api.set_tag
    formula = api.formula
    ADD = api.ADD
    COP = api.COP
    CPT = api.CPT
    CTU = api.CTU
    FFL = api.FFL
    FFU = api.FFU
    FLL = api.FLL
    MAFR = api.MAFR
    MAM = api.MAM
    MAS = api.MAS
    MCCD = api.MCCD
    MCCM = api.MCCM
    MCLM = api.MCLM
    MCS = api.MCS
    MOD = api.MOD
    MOV = api.MOV
    MSF = api.MSF
    MSO = api.MSO
    NOP = api.NOP
    ONS = api.ONS
    OTL = api.OTL
    OTU = api.OTU
    PID = api.PID
    RES = api.RES
    TON = api.TON
    TRN = api.TRN

    _pc = 0
    while _pc < 764:
        if _pc == 0:
            # rung 0
            # XIC Local:1:I.Pt00.Data OTE MACHINE_SW_STAT[1] OTE Z_RETRACTED_1A
            set_tag("MACHINE_SW_STAT[1]", bool(tag("Local:1:I.Pt00.Data")))
            set_tag("Z_RETRACTED_1A", bool(tag("Local:1:I.Pt00.Data")))
            _pc = 1
            continue
        elif _pc == 1:
            # rung 1
            # XIO Local:1:I.Pt01.Data OTE MACHINE_SW_STAT[2] OTE Z_RETRACTED_1B
            set_tag("MACHINE_SW_STAT[2]", bool(not tag("Local:1:I.Pt01.Data")))
            set_tag("Z_RETRACTED_1B", bool(not tag("Local:1:I.Pt01.Data")))
            _pc = 2
            continue
        elif _pc == 2:
            # rung 2
            # XIC Local:1:I.Pt02.Data OTE MACHINE_SW_STAT[3] OTE Z_RETRACTED_2A
            set_tag("MACHINE_SW_STAT[3]", bool(tag("Local:1:I.Pt02.Data")))
            set_tag("Z_RETRACTED_2A", bool(tag("Local:1:I.Pt02.Data")))
            _pc = 3
            continue
        elif _pc == 3:
            # rung 3
            # XIO Local:1:I.Pt03.Data OTE MACHINE_SW_STAT[4] OTE Z_RETRACTED_2B
            set_tag("MACHINE_SW_STAT[4]", bool(not tag("Local:1:I.Pt03.Data")))
            set_tag("Z_RETRACTED_2B", bool(not tag("Local:1:I.Pt03.Data")))
            _pc = 4
            continue
        elif _pc == 4:
            # rung 4
            # BST XIC Local:1:I.Pt04.Data NXB CMP "Z_axis.ActualPosition>415" BND OTE MACHINE_SW_STAT[5] OTE Z_EXTENDED
            _branch_0 = bool(tag("Local:1:I.Pt04.Data"))
            _branch_2 = bool(formula("Z_axis.ActualPosition>415"))
            _branch_4 = _branch_0 or _branch_2
            set_tag("MACHINE_SW_STAT[5]", bool(_branch_4))
            set_tag("Z_EXTENDED", bool(_branch_4))
            _pc = 5
            continue
        elif _pc == 5:
            # rung 5
            # XIC Local:1:I.Pt11.Data OTE MACHINE_SW_STAT[6] OTE Z_STAGE_LATCHED
            set_tag("MACHINE_SW_STAT[6]", bool(tag("Local:1:I.Pt11.Data")))
            set_tag("Z_STAGE_LATCHED", bool(tag("Local:1:I.Pt11.Data")))
            _pc = 6
            continue
        elif _pc == 6:
            # rung 6
            # XIC Local:2:I.Pt01.Data OTE MACHINE_SW_STAT[7] OTE Z_FIXED_LATCHED
            set_tag("MACHINE_SW_STAT[7]", bool(tag("Local:2:I.Pt01.Data")))
            set_tag("Z_FIXED_LATCHED", bool(tag("Local:2:I.Pt01.Data")))
            _pc = 7
            continue
        elif _pc == 7:
            # rung 7
            # BST XIC Local:1:I.Pt07.Data NXB XIC z_eot_bypass BND OTE MACHINE_SW_STAT[8] OTE Z_EOT
            _branch_5 = bool(tag("Local:1:I.Pt07.Data"))
            _branch_7 = bool(tag("z_eot_bypass"))
            _branch_9 = _branch_5 or _branch_7
            set_tag("MACHINE_SW_STAT[8]", bool(_branch_9))
            set_tag("Z_EOT", bool(_branch_9))
            _pc = 8
            continue
        elif _pc == 8:
            # rung 8
            # XIO Local:1:I.Pt10.Data OTE MACHINE_SW_STAT[9] OTE Z_STAGE_PRESENT
            set_tag("MACHINE_SW_STAT[9]", bool(not tag("Local:1:I.Pt10.Data")))
            set_tag("Z_STAGE_PRESENT", bool(not tag("Local:1:I.Pt10.Data")))
            _pc = 9
            continue
        elif _pc == 9:
            # rung 9
            # XIO Local:2:I.Pt02.Data OTE MACHINE_SW_STAT[10] OTE Z_FIXED_PRESENT
            set_tag("MACHINE_SW_STAT[10]", bool(not tag("Local:2:I.Pt02.Data")))
            set_tag("Z_FIXED_PRESENT", bool(not tag("Local:2:I.Pt02.Data")))
            _pc = 10
            continue
        elif _pc == 10:
            # rung 10
            # XIC Local:2:I.Pt04.Data OTE MACHINE_SW_STAT[14] OTE X_PARKED
            set_tag("MACHINE_SW_STAT[14]", bool(tag("Local:2:I.Pt04.Data")))
            set_tag("X_PARKED", bool(tag("Local:2:I.Pt04.Data")))
            _pc = 11
            continue
        elif _pc == 11:
            # rung 11
            # XIC Local:2:I.Pt00.Data OTE MACHINE_SW_STAT[15] OTE X_XFER_OK
            set_tag("MACHINE_SW_STAT[15]", bool(tag("Local:2:I.Pt00.Data")))
            set_tag("X_XFER_OK", bool(tag("Local:2:I.Pt00.Data")))
            _pc = 12
            continue
        elif _pc == 12:
            # rung 12
            # XIC Local:1:I.Pt13.Data OTE MACHINE_SW_STAT[16] OTE Y_MOUNT_XFER_OK
            set_tag("MACHINE_SW_STAT[16]", bool(tag("Local:1:I.Pt13.Data")))
            set_tag("Y_MOUNT_XFER_OK", bool(tag("Local:1:I.Pt13.Data")))
            _pc = 13
            continue
        elif _pc == 13:
            # rung 13
            # XIC Local:1:I.Pt12.Data OTE MACHINE_SW_STAT[17] OTE Y_XFER_OK
            set_tag("MACHINE_SW_STAT[17]", bool(tag("Local:1:I.Pt12.Data")))
            set_tag("Y_XFER_OK", bool(tag("Local:1:I.Pt12.Data")))
            _pc = 14
            continue
        elif _pc == 14:
            # rung 14
            # XIC Local:1:I.Pt06.Data OTE MACHINE_SW_STAT[18] OTE PLUS_Y_EOT
            set_tag("MACHINE_SW_STAT[18]", bool(tag("Local:1:I.Pt06.Data")))
            set_tag("PLUS_Y_EOT", bool(tag("Local:1:I.Pt06.Data")))
            _pc = 15
            continue
        elif _pc == 15:
            # rung 15
            # XIC Local:2:I.Pt12.Data OTE MACHINE_SW_STAT[19] OTE MINUS_Y_EOT
            set_tag("MACHINE_SW_STAT[19]", bool(tag("Local:2:I.Pt12.Data")))
            set_tag("MINUS_Y_EOT", bool(tag("Local:2:I.Pt12.Data")))
            _pc = 16
            continue
        elif _pc == 16:
            # rung 16
            # XIC Local:2:I.Pt08.Data OTE MACHINE_SW_STAT[20] OTE PLUS_X_EOT
            set_tag("MACHINE_SW_STAT[20]", bool(tag("Local:2:I.Pt08.Data")))
            set_tag("PLUS_X_EOT", bool(tag("Local:2:I.Pt08.Data")))
            _pc = 17
            continue
        elif _pc == 17:
            # rung 17
            # XIC Local:2:I.Pt10.Data OTE MACHINE_SW_STAT[21] OTE MINUS_X_EOT
            set_tag("MACHINE_SW_STAT[21]", bool(tag("Local:2:I.Pt10.Data")))
            set_tag("MINUS_X_EOT", bool(tag("Local:2:I.Pt10.Data")))
            _pc = 18
            continue
        elif _pc == 18:
            # rung 18
            # XIC Local:2:I.Pt14.Data OTE MACHINE_SW_STAT[22] OTE APA_IS_VERTICAL
            set_tag("MACHINE_SW_STAT[22]", bool(tag("Local:2:I.Pt14.Data")))
            set_tag("APA_IS_VERTICAL", bool(tag("Local:2:I.Pt14.Data")))
            _pc = 19
            continue
        elif _pc == 19:
            # rung 19
            # BST XIO DUNEW2PLC2:1:I.Pt02Data NXB XIO DUNEW2PLC2:1:I.Pt03Data NXB XIO DUNEW2PLC2:1:I.Pt04Data BND OTE MACHINE_SW_STAT[23]
            _branch_10 = bool(not tag("DUNEW2PLC2:1:I.Pt02Data"))
            _branch_12 = bool(not tag("DUNEW2PLC2:1:I.Pt03Data"))
            _branch_14 = bool(not tag("DUNEW2PLC2:1:I.Pt04Data"))
            _branch_16 = _branch_10 or _branch_12 or _branch_14
            set_tag("MACHINE_SW_STAT[23]", bool(_branch_16))
            _pc = 20
            continue
        elif _pc == 20:
            # rung 20
            # XIC DUNEW2PLC2:1:I.Pt00Data XIC DUNEW2PLC2:1:I.Pt01Data OTE MACHINE_SW_STAT[25]
            set_tag(
                "MACHINE_SW_STAT[25]",
                bool(
                    (tag("DUNEW2PLC2:1:I.Pt00Data"))
                    and (tag("DUNEW2PLC2:1:I.Pt01Data"))
                ),
            )
            _pc = 21
            continue
        elif _pc == 21:
            # rung 21
            # XIC Local:6:I.Pt00.Data OTE MACHINE_SW_STAT[26] OTE FRAME_LOC_HD_TOP
            set_tag("MACHINE_SW_STAT[26]", bool(tag("Local:6:I.Pt00.Data")))
            set_tag("FRAME_LOC_HD_TOP", bool(tag("Local:6:I.Pt00.Data")))
            _pc = 22
            continue
        elif _pc == 22:
            # rung 22
            # XIC Local:6:I.Pt01.Data OTE MACHINE_SW_STAT[27] OTE FRAME_LOC_HD_MID
            set_tag("MACHINE_SW_STAT[27]", bool(tag("Local:6:I.Pt01.Data")))
            set_tag("FRAME_LOC_HD_MID", bool(tag("Local:6:I.Pt01.Data")))
            _pc = 23
            continue
        elif _pc == 23:
            # rung 23
            # XIC Local:6:I.Pt02.Data OTE MACHINE_SW_STAT[28] OTE FRAME_LOC_HD_BTM
            set_tag("MACHINE_SW_STAT[28]", bool(tag("Local:6:I.Pt02.Data")))
            set_tag("FRAME_LOC_HD_BTM", bool(tag("Local:6:I.Pt02.Data")))
            _pc = 24
            continue
        elif _pc == 24:
            # rung 24
            # XIC Local:6:I.Pt03.Data OTE MACHINE_SW_STAT[29] OTE FRAME_LOC_FT_TOP
            set_tag("MACHINE_SW_STAT[29]", bool(tag("Local:6:I.Pt03.Data")))
            set_tag("FRAME_LOC_FT_TOP", bool(tag("Local:6:I.Pt03.Data")))
            _pc = 25
            continue
        elif _pc == 25:
            # rung 25
            # XIC Local:6:I.Pt04.Data OTE MACHINE_SW_STAT[30] OTE FRAME_LOC_FT_MID
            set_tag("MACHINE_SW_STAT[30]", bool(tag("Local:6:I.Pt04.Data")))
            set_tag("FRAME_LOC_FT_MID", bool(tag("Local:6:I.Pt04.Data")))
            _pc = 26
            continue
        elif _pc == 26:
            # rung 26
            # XIC Local:6:I.Pt05.Data OTE MACHINE_SW_STAT[31] OTE FRAME_LOC_FT_BTM
            set_tag("MACHINE_SW_STAT[31]", bool(tag("Local:6:I.Pt05.Data")))
            set_tag("FRAME_LOC_FT_BTM", bool(tag("Local:6:I.Pt05.Data")))
            _pc = 27
            continue
        elif _pc == 27:
            # rung 27
            # XIO DUNEW2PLC2:1:I.Pt06Data OTE speed_regulator_switch
            set_tag("speed_regulator_switch", bool(not tag("DUNEW2PLC2:1:I.Pt06Data")))
            _pc = 28
            continue
        elif _pc == 28:
            # rung 28
            # BST XIC Z_RETRACTED_1A NXB XIC Z_RETRACTED_2A BND XIC Z_RETRACTED_1B XIC Z_RETRACTED_2B OTE Z_RETRACTED
            _branch_17 = bool(tag("Z_RETRACTED_1A"))
            _branch_19 = bool(tag("Z_RETRACTED_2A"))
            _branch_21 = _branch_17 or _branch_19
            set_tag(
                "Z_RETRACTED",
                bool(
                    (_branch_21) and (tag("Z_RETRACTED_1B")) and (tag("Z_RETRACTED_2B"))
                ),
            )
            _pc = 29
            continue
        elif _pc == 29:
            # rung 29
            # XIC Z_EOT XIC PLUS_Y_EOT XIC MINUS_Y_EOT XIC PLUS_X_EOT XIC MINUS_X_EOT OTE ALL_EOT_GOOD
            set_tag(
                "ALL_EOT_GOOD",
                bool(
                    (tag("Z_EOT"))
                    and (tag("PLUS_Y_EOT"))
                    and (tag("MINUS_Y_EOT"))
                    and (tag("PLUS_X_EOT"))
                    and (tag("MINUS_X_EOT"))
                ),
            )
            _pc = 30
            continue
        elif _pc == 30:
            # rung 30
            # LIM 80 Y_axis.ActualPosition 450 OTE support_collision_window_bttm
            set_tag(
                "support_collision_window_bttm",
                bool(80 <= tag("Y_axis.ActualPosition") <= 450),
            )
            _pc = 31
            continue
        elif _pc == 31:
            # rung 31
            # LIM 1050 Y_axis.ActualPosition 1550 OTE support_collision_window_mid
            set_tag(
                "support_collision_window_mid",
                bool(1050 <= tag("Y_axis.ActualPosition") <= 1550),
            )
            _pc = 32
            continue
        elif _pc == 32:
            # rung 32
            # LIM 2200 Y_axis.ActualPosition 2650 OTE support_collision_window_top
            set_tag(
                "support_collision_window_top",
                bool(2200 <= tag("Y_axis.ActualPosition") <= 2650),
            )
            _pc = 33
            continue
        elif _pc == 33:
            # rung 33
            # XIC Local:2:I.Pt06.Data OTE TENSION_ON_SWITCH
            set_tag("TENSION_ON_SWITCH", bool(tag("Local:2:I.Pt06.Data")))
            _pc = 34
            continue
        elif _pc == 34:
            # rung 34
            # BST XIC Local:1:I.Pt15.Data NXB GRT tension wire_broken_tension BND OTE wire_break_proxy
            _branch_22 = bool(tag("Local:1:I.Pt15.Data"))
            _branch_24 = bool(tag("tension") > tag("wire_broken_tension"))
            _branch_26 = _branch_22 or _branch_24
            set_tag("wire_break_proxy", bool(_branch_26))
            _pc = 35
            continue
        elif _pc == 35:
            # rung 35
            # XIO Safety_Tripped_S TON T01 5000 0
            TON(
                timer_tag="T01",
                preset=5000,
                accum=0,
                rung_in=not tag("Safety_Tripped_S"),
            )
            _pc = 36
            continue
        elif _pc == 36:
            # rung 36
            # XIC Safety_Tripped_S BST OTE Local:3:O.Pt11.Data NXB OTE Local:3:O.Pt12.Data BND
            set_tag("Local:3:O.Pt11.Data", bool(tag("Safety_Tripped_S")))
            _branch_27 = bool(True)
            set_tag("Local:3:O.Pt12.Data", bool(tag("Safety_Tripped_S")))
            _branch_29 = bool(True)
            _branch_31 = _branch_27 or _branch_29
            _pc = 37
            continue
        elif _pc == 37:
            # rung 37
            # BST XIC blink_on.TT BST XIC T01.TT NXB NEQ ERROR_CODE 0 BND NXB XIC X_axis.SLSActiveStatus BND OTE Local:3:O.Pt13.Data
            _branch_32 = bool(tag("T01.TT"))
            _branch_34 = bool(tag("ERROR_CODE") != 0)
            _branch_36 = _branch_32 or _branch_34
            _branch_37 = bool((tag("blink_on.TT")) and (_branch_36))
            _branch_39 = bool(tag("X_axis.SLSActiveStatus"))
            _branch_41 = _branch_37 or _branch_39
            set_tag("Local:3:O.Pt13.Data", bool(_branch_41))
            _pc = 38
            continue
        elif _pc == 38:
            # rung 38
            # XIC blink_on.TT XIC T01.TT OTE Local:3:O.Pt15.Data
            set_tag(
                "Local:3:O.Pt15.Data", bool((tag("blink_on.TT")) and (tag("T01.TT")))
            )
            _pc = 39
            continue
        elif _pc == 39:
            # rung 39
            # BST XIC T01.TT NXB XIC T01.DN BND OTE Local:3:O.Pt14.Data
            _branch_42 = bool(tag("T01.TT"))
            _branch_44 = bool(tag("T01.DN"))
            _branch_46 = _branch_42 or _branch_44
            set_tag("Local:3:O.Pt14.Data", bool(_branch_46))
            _pc = 40
            continue
        elif _pc == 40:
            # rung 40
            # TON blink_on 500 0
            TON(
                timer_tag="blink_on",
                preset=500,
                accum=0,
                rung_in=True,
            )
            _pc = 41
            continue
        elif _pc == 41:
            # rung 41
            # XIC blink_on.DN TON blink_off 500 0
            TON(
                timer_tag="blink_off",
                preset=500,
                accum=0,
                rung_in=tag("blink_on.DN"),
            )
            _pc = 42
            continue
        elif _pc == 42:
            # rung 42
            # XIC blink_off.DN RES blink_on
            if tag("blink_off.DN"):
                RES("blink_on")
            _pc = 43
            continue
        elif _pc == 43:
            # rung 43
            # XIC INIT_DONE CMP "NEXTSTATE=0" CPT STATE 0
            if tag("INIT_DONE"):
                if formula("NEXTSTATE=0"):
                    set_tag("STATE", formula("0"))
            _pc = 44
            continue
        elif _pc == 44:
            # rung 44
            # XIC INIT_DONE CMP "NEXTSTATE=1" CPT STATE 1
            if tag("INIT_DONE"):
                if formula("NEXTSTATE=1"):
                    set_tag("STATE", formula("1"))
            _pc = 45
            continue
        elif _pc == 45:
            # rung 45
            # XIC INIT_DONE CMP "NEXTSTATE=2" CPT STATE 2
            if tag("INIT_DONE"):
                if formula("NEXTSTATE=2"):
                    set_tag("STATE", formula("2"))
            _pc = 46
            continue
        elif _pc == 46:
            # rung 46
            # XIC INIT_DONE CMP "NEXTSTATE=3" CPT STATE 3
            if tag("INIT_DONE"):
                if formula("NEXTSTATE=3"):
                    set_tag("STATE", formula("3"))
            _pc = 47
            continue
        elif _pc == 47:
            # rung 47
            # XIC INIT_DONE CMP "NEXTSTATE=4" CPT STATE 4
            if tag("INIT_DONE"):
                if formula("NEXTSTATE=4"):
                    set_tag("STATE", formula("4"))
            _pc = 48
            continue
        elif _pc == 48:
            # rung 48
            # XIC INIT_DONE CMP "NEXTSTATE=5" CPT STATE 5
            if tag("INIT_DONE"):
                if formula("NEXTSTATE=5"):
                    set_tag("STATE", formula("5"))
            _pc = 49
            continue
        elif _pc == 49:
            # rung 49
            # XIC INIT_DONE CMP "NEXTSTATE=6" CPT STATE 6
            if tag("INIT_DONE"):
                if formula("NEXTSTATE=6"):
                    set_tag("STATE", formula("6"))
            _pc = 50
            continue
        elif _pc == 50:
            # rung 50
            # XIC INIT_DONE CMP "NEXTSTATE=7" CPT STATE 7
            if tag("INIT_DONE"):
                if formula("NEXTSTATE=7"):
                    set_tag("STATE", formula("7"))
            _pc = 51
            continue
        elif _pc == 51:
            # rung 51
            # XIC INIT_DONE CMP "NEXTSTATE=8" CPT STATE 8
            if tag("INIT_DONE"):
                if formula("NEXTSTATE=8"):
                    set_tag("STATE", formula("8"))
            _pc = 52
            continue
        elif _pc == 52:
            # rung 52
            # XIC INIT_DONE CMP "NEXTSTATE=9" CPT STATE 9
            if tag("INIT_DONE"):
                if formula("NEXTSTATE=9"):
                    set_tag("STATE", formula("9"))
            _pc = 53
            continue
        elif _pc == 53:
            # rung 53
            # XIC INIT_DONE CMP "NEXTSTATE=10" CPT STATE 10
            if tag("INIT_DONE"):
                if formula("NEXTSTATE=10"):
                    set_tag("STATE", formula("10"))
            _pc = 54
            continue
        elif _pc == 54:
            # rung 54
            # XIC INIT_DONE CMP "NEXTSTATE=11" CPT STATE 11
            if tag("INIT_DONE"):
                if formula("NEXTSTATE=11"):
                    set_tag("STATE", formula("11"))
            _pc = 55
            continue
        elif _pc == 55:
            # rung 55
            # XIC INIT_DONE CMP "NEXTSTATE=12" CPT STATE 12
            if tag("INIT_DONE"):
                if formula("NEXTSTATE=12"):
                    set_tag("STATE", formula("12"))
            _pc = 56
            continue
        elif _pc == 56:
            # rung 56
            # XIC INIT_DONE CMP "NEXTSTATE=13" CPT STATE 13
            if tag("INIT_DONE"):
                if formula("NEXTSTATE=13"):
                    set_tag("STATE", formula("13"))
            _pc = 57
            continue
        elif _pc == 57:
            # rung 57
            # XIC INIT_DONE CMP "NEXTSTATE=14" CPT STATE 14
            if tag("INIT_DONE"):
                if formula("NEXTSTATE=14"):
                    set_tag("STATE", formula("14"))
            _pc = 58
            continue
        elif _pc == 58:
            # rung 58
            # XIC Local:2:I.Pt13.Data OTE ResetPB
            set_tag("ResetPB", bool(tag("Local:2:I.Pt13.Data")))
            _pc = 59
            continue
        elif _pc == 59:
            # rung 59
            # CPT v_xyz SQR(X_axis.ActualVelocity*X_axis.ActualVelocity+Y_axis.ActualVelocity*Y_axis.ActualVelocity)+SQR(Z_axis.ActualVelocity*Z_axis.ActualVelocity)
            set_tag(
                "v_xyz",
                formula(
                    "SQR(X_axis.ActualVelocity*X_axis.ActualVelocity+Y_axis.ActualVelocity*Y_axis.ActualVelocity)+SQR(Z_axis.ActualVelocity*Z_axis.ActualVelocity)"
                ),
            )
            _pc = 60
            continue
        elif _pc == 60:
            # rung 60
            # CPT v_xy SQR(X_axis.ActualVelocity*X_axis.ActualVelocity+Y_axis.ActualVelocity*Y_axis.ActualVelocity)
            set_tag(
                "v_xy",
                formula(
                    "SQR(X_axis.ActualVelocity*X_axis.ActualVelocity+Y_axis.ActualVelocity*Y_axis.ActualVelocity)"
                ),
            )
            _pc = 61
            continue
        elif _pc == 61:
            # rung 61
            # NEQ v_xy 0 CPT accel_xy (X_axis.ActualVelocity*X_axis.CommandAcceleration+Y_axis.ActualVelocity*Y_axis.CommandAcceleration)/v_xy
            if tag("v_xy") != 0:
                set_tag(
                    "accel_xy",
                    formula(
                        "(X_axis.ActualVelocity*X_axis.CommandAcceleration+Y_axis.ActualVelocity*Y_axis.CommandAcceleration)/v_xy"
                    ),
                )
            _pc = 62
            continue
        elif _pc == 62:
            # rung 62
            # BST BST XIC Z_STAGE_LATCHED NXB XIC Z_FIXED_LATCHED EQU ACTUATOR_POS 3 BND CPT HEAD_POS 0 NXB XIC Z_FIXED_LATCHED EQU ACTUATOR_POS 2 CPT HEAD_POS 3 NXB XIO Z_STAGE_LATCHED XIO Z_FIXED_LATCHED CPT HEAD_POS -1 BND
            _branch_47 = bool(tag("Z_STAGE_LATCHED"))
            _branch_49 = bool((tag("Z_FIXED_LATCHED")) and (tag("ACTUATOR_POS") == 3))
            _branch_51 = _branch_47 or _branch_49
            if _branch_51:
                set_tag("HEAD_POS", formula("0"))
            _branch_52 = bool(_branch_51)
            if tag("Z_FIXED_LATCHED"):
                if tag("ACTUATOR_POS") == 2:
                    set_tag("HEAD_POS", formula("3"))
            _branch_54 = bool((tag("Z_FIXED_LATCHED")) and (tag("ACTUATOR_POS") == 2))
            if not tag("Z_STAGE_LATCHED"):
                if not tag("Z_FIXED_LATCHED"):
                    set_tag("HEAD_POS", formula("-1"))
            _branch_56 = bool(
                (not tag("Z_STAGE_LATCHED")) and (not tag("Z_FIXED_LATCHED"))
            )
            _branch_58 = _branch_52 or _branch_54 or _branch_56
            _pc = 63
            continue
        elif _pc == 63:
            # rung 63
            # XIC TENSION_ON_SWITCH TON tension_on_switch_delay_on_start 1000 0
            TON(
                timer_tag="tension_on_switch_delay_on_start",
                preset=1000,
                accum=0,
                rung_in=tag("TENSION_ON_SWITCH"),
            )
            _pc = 64
            continue
        elif _pc == 64:
            # rung 64
            # XIC TENSION_ON_SWITCH OTL PTS_tension_switch_transition_oneshot_storage
            if tag("TENSION_ON_SWITCH"):
                set_tag("PTS_tension_switch_transition_oneshot_storage", True)
            _pc = 65
            continue
        elif _pc == 65:
            # rung 65
            # XIO TENSION_ON_SWITCH OTU PTS_tension_switch_transition_oneshot_storage
            if not tag("TENSION_ON_SWITCH"):
                set_tag("PTS_tension_switch_transition_oneshot_storage", False)
            _pc = 66
            continue
        elif _pc == 66:
            # rung 66
            # XIC TENSION_ON_SWITCH OTL PTS_tension_switch_off_oneshot_storage
            if tag("TENSION_ON_SWITCH"):
                set_tag("PTS_tension_switch_off_oneshot_storage", True)
            _pc = 67
            continue
        elif _pc == 67:
            # rung 67
            # XIO TENSION_ON_SWITCH OTU PTS_tension_switch_off_oneshot_storage
            if not tag("TENSION_ON_SWITCH"):
                set_tag("PTS_tension_switch_off_oneshot_storage", False)
            _pc = 68
            continue
        elif _pc == 68:
            # rung 68
            # XIO wire_break_proxy TON wire_break_debounce 20 0
            TON(
                timer_tag="wire_break_debounce",
                preset=20,
                accum=0,
                rung_in=not tag("wire_break_proxy"),
            )
            _pc = 69
            continue
        elif _pc == 69:
            # rung 69
            # XIC TENSION_ON_SWITCH XIO Safety_Tripped_S BST XIC wire_break_proxy NXB XIC tension_on_switch_delay_on_start.TT NXB XIO wire_break_debounce.DN BND OTE Enable_tension_motor
            _branch_59 = bool(tag("wire_break_proxy"))
            _branch_61 = bool(tag("tension_on_switch_delay_on_start.TT"))
            _branch_63 = bool(not tag("wire_break_debounce.DN"))
            _branch_65 = _branch_59 or _branch_61 or _branch_63
            set_tag(
                "Enable_tension_motor",
                bool(
                    (tag("TENSION_ON_SWITCH"))
                    and (not tag("Safety_Tripped_S"))
                    and (_branch_65)
                ),
            )
            _pc = 70
            continue
        elif _pc == 70:
            # rung 70
            # BST XIC tension_on_switch_delay_on_start.TT NXB XIC TENSION_CONTROL_OK BND BST BST XIC wire_break_proxy NXB XIO wire_break_switch_delay_on_start.DN NXB XIO wire_break_debounce.DN BND OTE TENSION_CONTROL_OK NXB TON wire_break_switch_delay_on_start 1000 0 BND
            _branch_66 = bool(tag("tension_on_switch_delay_on_start.TT"))
            _branch_68 = bool(tag("TENSION_CONTROL_OK"))
            _branch_70 = _branch_66 or _branch_68
            _branch_71 = bool(tag("wire_break_proxy"))
            _branch_73 = bool(not tag("wire_break_switch_delay_on_start.DN"))
            _branch_75 = bool(not tag("wire_break_debounce.DN"))
            _branch_77 = _branch_71 or _branch_73 or _branch_75
            set_tag("TENSION_CONTROL_OK", bool((_branch_70) and (_branch_77)))
            _branch_78 = bool(_branch_77)
            TON(
                timer_tag="wire_break_switch_delay_on_start",
                preset=1000,
                accum=0,
                rung_in=_branch_70,
            )
            _branch_80 = bool(True)
            _branch_82 = _branch_78 or _branch_80
            _pc = 71
            continue
        elif _pc == 71:
            # rung 71
            # XIO PID_LOOP_TIMER.DN TON PID_LOOP_TIMER 3 0
            TON(
                timer_tag="PID_LOOP_TIMER",
                preset=3,
                accum=0,
                rung_in=not tag("PID_LOOP_TIMER.DN"),
            )
            _pc = 72
            continue
        elif _pc == 72:
            # rung 72
            # CPT tension 2.26*tension_tag-0.503*tension_tag*tension_tag+0.0694*tension_tag*tension_tag*tension_tag-0.00314*tension_tag*tension_tag*tension_tag*tension_tag
            set_tag(
                "tension",
                formula(
                    "2.26*tension_tag-0.503*tension_tag*tension_tag+0.0694*tension_tag*tension_tag*tension_tag-0.00314*tension_tag*tension_tag*tension_tag*tension_tag"
                ),
            )
            _pc = 73
            continue
        elif _pc == 73:
            # rung 73
            # CMP "tension_tag<=1" CPT tension tension_tag
            if formula("tension_tag<=1"):
                set_tag("tension", formula("tension_tag"))
            _pc = 74
            continue
        elif _pc == 74:
            # rung 74
            # BST XIC PID_LOOP_TIMER.DN NXB XIC pid_loop_timer_bypass BND BST XIC TENSION_CONTROL_OK MOV tension_setpoint winding_head_pid.SP NXB XIO TENSION_CONTROL_OK MOV 10 tension MOV 0 winding_head_pid.SP NXB PID winding_head_pid tension 0 tension_motor_cv 0 0 0 NXB BST XIO TENSION_CONTROL_OK NXB XIO TENSION_ON_SWITCH NXB XIC tension_on_switch_delay_on_start.TT LES tension_motor_cv neutral_cv BND MOV neutral_cv tension_motor_cv NXB XIC constant_cv_out MOV SetPoint_Override tension_motor_cv NXB MOV tension_motor_cv cv_to_electrocraft BND
            _branch_83 = bool(tag("PID_LOOP_TIMER.DN"))
            _branch_85 = bool(tag("pid_loop_timer_bypass"))
            _branch_87 = _branch_83 or _branch_85
            if _branch_87:
                if tag("TENSION_CONTROL_OK"):
                    set_tag("winding_head_pid.SP", tag("tension_setpoint"))
            _branch_88 = bool(tag("TENSION_CONTROL_OK"))
            if _branch_87:
                if not tag("TENSION_CONTROL_OK"):
                    set_tag("tension", 10)
            if _branch_87:
                if not tag("TENSION_CONTROL_OK"):
                    set_tag("winding_head_pid.SP", 0)
            _branch_90 = bool(not tag("TENSION_CONTROL_OK"))
            if _branch_87:
                PID(
                    control_block="winding_head_pid",
                    process_variable="tension",
                    tieback="0",
                    control_variable="tension_motor_cv",
                    feedforward="0",
                    alarm_disable="0",
                    hold="0",
                )
            _branch_92 = bool(True)
            _branch_94 = bool(not tag("TENSION_CONTROL_OK"))
            _branch_96 = bool(not tag("TENSION_ON_SWITCH"))
            _branch_98 = bool(
                (tag("tension_on_switch_delay_on_start.TT"))
                and (tag("tension_motor_cv") < tag("neutral_cv"))
            )
            _branch_100 = _branch_94 or _branch_96 or _branch_98
            if _branch_87:
                if _branch_100:
                    set_tag("tension_motor_cv", tag("neutral_cv"))
            _branch_101 = bool(_branch_100)
            if _branch_87:
                if tag("constant_cv_out"):
                    set_tag("tension_motor_cv", tag("SetPoint_Override"))
            _branch_103 = bool(tag("constant_cv_out"))
            if _branch_87:
                set_tag("cv_to_electrocraft", tag("tension_motor_cv"))
            _branch_105 = bool(True)
            _branch_107 = (
                _branch_88
                or _branch_90
                or _branch_92
                or _branch_101
                or _branch_103
                or _branch_105
            )
            _pc = 75
            continue
        elif _pc == 75:
            # rung 75
            # CPT tension_motor_difference tension-tension_motor_cv
            set_tag("tension_motor_difference", formula("tension-tension_motor_cv"))
            _pc = 76
            continue
        elif _pc == 76:
            # rung 76
            # CPT current_command cv_to_electrocraft*(current_command_high-current_command_low)/pid_cv_high_limit+current_command_low
            set_tag(
                "current_command",
                formula(
                    "cv_to_electrocraft*(current_command_high-current_command_low)/pid_cv_high_limit+current_command_low"
                ),
            )
            _pc = 77
            continue
        elif _pc == 77:
            # rung 77
            # CPT neutral_cv -current_command_low/((current_command_high-current_command_low)/(pid_cv_high_limit-pid_cv_low_limit))
            set_tag(
                "neutral_cv",
                formula(
                    "-current_command_low/((current_command_high-current_command_low)/(pid_cv_high_limit-pid_cv_low_limit))"
                ),
            )
            _pc = 78
            continue
        elif _pc == 78:
            # rung 78
            # MOV tension_stable_time tension_stable_timer.PRE CMP "ABS(tension-tension_setpoint)<tension_stable_tolerance" TON tension_stable_timer 100 0
            set_tag("tension_stable_timer.PRE", tag("tension_stable_time"))
            TON(
                timer_tag="tension_stable_timer",
                preset=100,
                accum=0,
                rung_in=formula(
                    "ABS(tension-tension_setpoint)<tension_stable_tolerance"
                ),
            )
            _pc = 79
            continue
        elif _pc == 79:
            # rung 79
            # GRT tension max_tolerable_tension XIC TENSION_ON_SWITCH OTE Local:3:O.Pt15.Data TON overtension_timer 10 0
            set_tag(
                "Local:3:O.Pt15.Data",
                bool(
                    (tag("tension") > tag("max_tolerable_tension"))
                    and (tag("TENSION_ON_SWITCH"))
                ),
            )
            TON(
                timer_tag="overtension_timer",
                preset=10,
                accum=0,
                rung_in=(tag("tension") > tag("max_tolerable_tension"))
                and (tag("TENSION_ON_SWITCH")),
            )
            _pc = 80
            continue
        elif _pc == 80:
            # rung 80
            # XIC overtension_timer.DN OTE MORE_STATS[2] CPT ERROR_CODE 8002 CPT NEXTSTATE 10
            set_tag("MORE_STATS[2]", bool(tag("overtension_timer.DN")))
            if tag("overtension_timer.DN"):
                set_tag("ERROR_CODE", formula("8002"))
            if tag("overtension_timer.DN"):
                set_tag("NEXTSTATE", formula("10"))
            _pc = 81
            continue
        elif _pc == 81:
            # rung 81
            # XIC tension_on_switch_delay_on_start.DN XIC wire_break_debounce.DN NEQ ERROR_CODE 8002 CPT NEXTSTATE 10 CPT ERROR_CODE 8001
            if tag("tension_on_switch_delay_on_start.DN"):
                if tag("wire_break_debounce.DN"):
                    if tag("ERROR_CODE") != 8002:
                        set_tag("NEXTSTATE", formula("10"))
            if tag("tension_on_switch_delay_on_start.DN"):
                if tag("wire_break_debounce.DN"):
                    if tag("ERROR_CODE") != 8002:
                        set_tag("ERROR_CODE", formula("8001"))
            _pc = 82
            continue
        elif _pc == 82:
            # rung 82
            # XIO TENSION_ON_SWITCH XIC PTS_tension_switch_transition_oneshot_storage OTE PTS_clear_tension_fault_oneshot
            set_tag(
                "PTS_clear_tension_fault_oneshot",
                bool(
                    (not tag("TENSION_ON_SWITCH"))
                    and (tag("PTS_tension_switch_transition_oneshot_storage"))
                ),
            )
            _pc = 83
            continue
        elif _pc == 83:
            # rung 83
            # XIC PTS_clear_tension_fault_oneshot BST EQU ERROR_CODE 8002 NXB EQU ERROR_CODE 8001 BND CPT ERROR_CODE 0
            _branch_108 = bool(tag("ERROR_CODE") == 8002)
            _branch_110 = bool(tag("ERROR_CODE") == 8001)
            _branch_112 = _branch_108 or _branch_110
            if tag("PTS_clear_tension_fault_oneshot"):
                if _branch_112:
                    set_tag("ERROR_CODE", formula("0"))
            _pc = 84
            continue
        elif _pc == 84:
            # rung 84
            # EQU MOVE_TYPE 9 XIC INIT_SW OTU INIT_SW
            if tag("MOVE_TYPE") == 9:
                if tag("INIT_SW"):
                    set_tag("INIT_SW", False)
            _pc = 85
            continue
        elif _pc == 85:
            # rung 85
            # XIC INIT_SW TON TIMER 2000 0
            TON(
                timer_tag="TIMER",
                preset=2000,
                accum=0,
                rung_in=tag("INIT_SW"),
            )
            _pc = 86
            continue
        elif _pc == 86:
            # rung 86
            # XIO INIT_SW CPT MOVE_TYPE 0 OTL INIT_SW
            if not tag("INIT_SW"):
                set_tag("MOVE_TYPE", formula("0"))
            if not tag("INIT_SW"):
                set_tag("INIT_SW", True)
            _pc = 87
            continue
        elif _pc == 87:
            # rung 87
            # XIC TIMER.DN XIO INIT_SetBit[0] OTE INIT_OutBit[0]
            set_tag(
                "INIT_OutBit[0]",
                bool((tag("TIMER.DN")) and (not tag("INIT_SetBit[0]"))),
            )
            _pc = 88
            continue
        elif _pc == 88:
            # rung 88
            # XIC TIMER.DN OTL INIT_SetBit[0]
            if tag("TIMER.DN"):
                set_tag("INIT_SetBit[0]", True)
            _pc = 89
            continue
        elif _pc == 89:
            # rung 89
            # XIO TIMER.DN OTU INIT_SetBit[0]
            if not tag("TIMER.DN"):
                set_tag("INIT_SetBit[0]", False)
            _pc = 90
            continue
        elif _pc == 90:
            # rung 90
            # XIC INIT_OutBit[0] CPT MOVE_TYPE 0 CPT NEXTSTATE 1 CPT STATE 0 CPT ERROR_CODE 0
            if tag("INIT_OutBit[0]"):
                set_tag("MOVE_TYPE", formula("0"))
            if tag("INIT_OutBit[0]"):
                set_tag("NEXTSTATE", formula("1"))
            if tag("INIT_OutBit[0]"):
                set_tag("STATE", formula("0"))
            if tag("INIT_OutBit[0]"):
                set_tag("ERROR_CODE", formula("0"))
            _pc = 91
            continue
        elif _pc == 91:
            # rung 91
            # XIC INIT_OutBit[0] OTU LATCH_ACTUATOR_HOMED
            if tag("INIT_OutBit[0]"):
                set_tag("LATCH_ACTUATOR_HOMED", False)
            _pc = 92
            continue
        elif _pc == 92:
            # rung 92
            # XIC INIT_SetBit[0] OTE INIT_DONE
            set_tag("INIT_DONE", bool(tag("INIT_SetBit[0]")))
            _pc = 93
            continue
        elif _pc == 93:
            # rung 93
            # XIC INIT_DONE CMP "STATE=0" MAFR Z_axis INIT_z_axis_fault_reset_status
            if tag("INIT_DONE"):
                if formula("STATE=0"):
                    MAFR(
                        axis="Z_axis",
                        motion_control="INIT_z_axis_fault_reset_status",
                    )
            _pc = 94
            continue
        elif _pc == 94:
            # rung 94
            # XIC INIT_z_axis_fault_reset_status.DN XIO INIT_SetBit[1] OTE INIT_OutBit[1]
            set_tag(
                "INIT_OutBit[1]",
                bool(
                    (tag("INIT_z_axis_fault_reset_status.DN"))
                    and (not tag("INIT_SetBit[1]"))
                ),
            )
            _pc = 95
            continue
        elif _pc == 95:
            # rung 95
            # XIC INIT_z_axis_fault_reset_status.DN OTL INIT_SetBit[1]
            if tag("INIT_z_axis_fault_reset_status.DN"):
                set_tag("INIT_SetBit[1]", True)
            _pc = 96
            continue
        elif _pc == 96:
            # rung 96
            # XIO INIT_z_axis_fault_reset_status.DN OTU INIT_SetBit[1]
            if not tag("INIT_z_axis_fault_reset_status.DN"):
                set_tag("INIT_SetBit[1]", False)
            _pc = 97
            continue
        elif _pc == 97:
            # rung 97
            # XIC INIT_OutBit[1] CPT NEXTSTATE 1
            if tag("INIT_OutBit[1]"):
                set_tag("NEXTSTATE", formula("1"))
            _pc = 98
            continue
        elif _pc == 98:
            # rung 98
            # XIC INIT_DONE CMP "STATE=1" OTE STATE1_IND
            set_tag("STATE1_IND", bool((tag("INIT_DONE")) and (formula("STATE=1"))))
            _pc = 99
            continue
        elif _pc == 99:
            # rung 99
            # XIC STATE1_IND XIO trigger_axes_sb OTE trigger_axes_ob
            set_tag(
                "trigger_axes_ob",
                bool((tag("STATE1_IND")) and (not tag("trigger_axes_sb"))),
            )
            _pc = 100
            continue
        elif _pc == 100:
            # rung 100
            # XIC STATE1_IND OTL trigger_axes_sb
            if tag("STATE1_IND"):
                set_tag("trigger_axes_sb", True)
            _pc = 101
            continue
        elif _pc == 101:
            # rung 101
            # XIO STATE1_IND OTU trigger_axes_sb
            if not tag("STATE1_IND"):
                set_tag("trigger_axes_sb", False)
            _pc = 102
            continue
        elif _pc == 102:
            # rung 102
            # XIC trigger_axes_ob XIO dont_auto_trigger_axes_in_state_1 MSO X_axis x_on_mso MSO Y_axis y_on_mso MSO Z_axis z_on_mso
            if tag("trigger_axes_ob"):
                if not tag("dont_auto_trigger_axes_in_state_1"):
                    MSO(
                        axis="X_axis",
                        motion_control="x_on_mso",
                    )
            if tag("trigger_axes_ob"):
                if not tag("dont_auto_trigger_axes_in_state_1"):
                    MSO(
                        axis="Y_axis",
                        motion_control="y_on_mso",
                    )
            if tag("trigger_axes_ob"):
                if not tag("dont_auto_trigger_axes_in_state_1"):
                    MSO(
                        axis="Z_axis",
                        motion_control="z_on_mso",
                    )
            _pc = 103
            continue
        elif _pc == 103:
            # rung 103
            # XIC STATE1_IND MOV 0 ERROR_CODE
            if tag("STATE1_IND"):
                set_tag("ERROR_CODE", 0)
            _pc = 104
            continue
        elif _pc == 104:
            # rung 104
            # XIC STATE1_IND CMP "MOVE_TYPE=1" XIO RS1_SetBit[0] OTE RS1_OutBit[0]
            set_tag(
                "RS1_OutBit[0]",
                bool(
                    (tag("STATE1_IND"))
                    and (formula("MOVE_TYPE=1"))
                    and (not tag("RS1_SetBit[0]"))
                ),
            )
            _pc = 105
            continue
        elif _pc == 105:
            # rung 105
            # XIC STATE1_IND CMP "MOVE_TYPE=1" OTL RS1_SetBit[0]
            if tag("STATE1_IND"):
                if formula("MOVE_TYPE=1"):
                    set_tag("RS1_SetBit[0]", True)
            _pc = 106
            continue
        elif _pc == 106:
            # rung 106
            # BST XIO STATE1_IND NXB NEQ MOVE_TYPE 1 BND OTU RS1_SetBit[0]
            _branch_113 = bool(not tag("STATE1_IND"))
            _branch_115 = bool(tag("MOVE_TYPE") != 1)
            _branch_117 = _branch_113 or _branch_115
            if _branch_117:
                set_tag("RS1_SetBit[0]", False)
            _pc = 107
            continue
        elif _pc == 107:
            # rung 107
            # XIC RS1_OutBit[0] CPT NEXTSTATE 2
            if tag("RS1_OutBit[0]"):
                set_tag("NEXTSTATE", formula("2"))
            _pc = 108
            continue
        elif _pc == 108:
            # rung 108
            # XIC STATE1_IND CMP "MOVE_TYPE=2" XIO RS1_SetBit[1] OTE RS1_OutBit[1]
            set_tag(
                "RS1_OutBit[1]",
                bool(
                    (tag("STATE1_IND"))
                    and (formula("MOVE_TYPE=2"))
                    and (not tag("RS1_SetBit[1]"))
                ),
            )
            _pc = 109
            continue
        elif _pc == 109:
            # rung 109
            # XIC STATE1_IND CMP "MOVE_TYPE=2" OTL RS1_SetBit[1]
            if tag("STATE1_IND"):
                if formula("MOVE_TYPE=2"):
                    set_tag("RS1_SetBit[1]", True)
            _pc = 110
            continue
        elif _pc == 110:
            # rung 110
            # BST XIO STATE1_IND NXB NEQ MOVE_TYPE 2 BND OTU RS1_SetBit[1]
            _branch_118 = bool(not tag("STATE1_IND"))
            _branch_120 = bool(tag("MOVE_TYPE") != 2)
            _branch_122 = _branch_118 or _branch_120
            if _branch_122:
                set_tag("RS1_SetBit[1]", False)
            _pc = 111
            continue
        elif _pc == 111:
            # rung 111
            # XIC RS1_OutBit[1] CPT NEXTSTATE 3
            if tag("RS1_OutBit[1]"):
                set_tag("NEXTSTATE", formula("3"))
            _pc = 112
            continue
        elif _pc == 112:
            # rung 112
            # XIC STATE1_IND CMP "MOVE_TYPE=3" XIO RS1_SetBit[2] OTE RS1_OutBit[2]
            set_tag(
                "RS1_OutBit[2]",
                bool(
                    (tag("STATE1_IND"))
                    and (formula("MOVE_TYPE=3"))
                    and (not tag("RS1_SetBit[2]"))
                ),
            )
            _pc = 113
            continue
        elif _pc == 113:
            # rung 113
            # XIC STATE1_IND CMP "MOVE_TYPE=3" OTL RS1_SetBit[2]
            if tag("STATE1_IND"):
                if formula("MOVE_TYPE=3"):
                    set_tag("RS1_SetBit[2]", True)
            _pc = 114
            continue
        elif _pc == 114:
            # rung 114
            # BST XIO STATE1_IND NXB NEQ MOVE_TYPE 3 BND OTU RS1_SetBit[2]
            _branch_123 = bool(not tag("STATE1_IND"))
            _branch_125 = bool(tag("MOVE_TYPE") != 3)
            _branch_127 = _branch_123 or _branch_125
            if _branch_127:
                set_tag("RS1_SetBit[2]", False)
            _pc = 115
            continue
        elif _pc == 115:
            # rung 115
            # XIC RS1_OutBit[2] CPT NEXTSTATE 4
            if tag("RS1_OutBit[2]"):
                set_tag("NEXTSTATE", formula("4"))
            _pc = 116
            continue
        elif _pc == 116:
            # rung 116
            # XIC STATE1_IND CMP "MOVE_TYPE=4" XIO RS1_SetBit[3] OTE RS1_OutBit[3]
            set_tag(
                "RS1_OutBit[3]",
                bool(
                    (tag("STATE1_IND"))
                    and (formula("MOVE_TYPE=4"))
                    and (not tag("RS1_SetBit[3]"))
                ),
            )
            _pc = 117
            continue
        elif _pc == 117:
            # rung 117
            # XIC STATE1_IND CMP "MOVE_TYPE=4" OTL RS1_SetBit[3]
            if tag("STATE1_IND"):
                if formula("MOVE_TYPE=4"):
                    set_tag("RS1_SetBit[3]", True)
            _pc = 118
            continue
        elif _pc == 118:
            # rung 118
            # BST XIO STATE1_IND NXB NEQ MOVE_TYPE 4 BND OTU RS1_SetBit[3]
            _branch_128 = bool(not tag("STATE1_IND"))
            _branch_130 = bool(tag("MOVE_TYPE") != 4)
            _branch_132 = _branch_128 or _branch_130
            if _branch_132:
                set_tag("RS1_SetBit[3]", False)
            _pc = 119
            continue
        elif _pc == 119:
            # rung 119
            # XIC RS1_OutBit[3] CPT NEXTSTATE 5
            if tag("RS1_OutBit[3]"):
                set_tag("NEXTSTATE", formula("5"))
            _pc = 120
            continue
        elif _pc == 120:
            # rung 120
            # XIC STATE1_IND CMP "MOVE_TYPE=5" XIO RS1_SetBit[4] OTE RS1_OutBit[4]
            set_tag(
                "RS1_OutBit[4]",
                bool(
                    (tag("STATE1_IND"))
                    and (formula("MOVE_TYPE=5"))
                    and (not tag("RS1_SetBit[4]"))
                ),
            )
            _pc = 121
            continue
        elif _pc == 121:
            # rung 121
            # XIC STATE1_IND CMP "MOVE_TYPE=5" OTL RS1_SetBit[4]
            if tag("STATE1_IND"):
                if formula("MOVE_TYPE=5"):
                    set_tag("RS1_SetBit[4]", True)
            _pc = 122
            continue
        elif _pc == 122:
            # rung 122
            # BST XIO STATE1_IND NXB NEQ MOVE_TYPE 5 BND OTU RS1_SetBit[4]
            _branch_133 = bool(not tag("STATE1_IND"))
            _branch_135 = bool(tag("MOVE_TYPE") != 5)
            _branch_137 = _branch_133 or _branch_135
            if _branch_137:
                set_tag("RS1_SetBit[4]", False)
            _pc = 123
            continue
        elif _pc == 123:
            # rung 123
            # XIC RS1_OutBit[4] CPT NEXTSTATE 6
            if tag("RS1_OutBit[4]"):
                set_tag("NEXTSTATE", formula("6"))
            _pc = 124
            continue
        elif _pc == 124:
            # rung 124
            # XIC STATE1_IND CMP "MOVE_TYPE=6" XIO RS1_SetBit[5] OTE RS1_OutBit[5]
            set_tag(
                "RS1_OutBit[5]",
                bool(
                    (tag("STATE1_IND"))
                    and (formula("MOVE_TYPE=6"))
                    and (not tag("RS1_SetBit[5]"))
                ),
            )
            _pc = 125
            continue
        elif _pc == 125:
            # rung 125
            # XIC STATE1_IND CMP "MOVE_TYPE=6" OTL RS1_SetBit[5]
            if tag("STATE1_IND"):
                if formula("MOVE_TYPE=6"):
                    set_tag("RS1_SetBit[5]", True)
            _pc = 126
            continue
        elif _pc == 126:
            # rung 126
            # BST XIO STATE1_IND NXB NEQ MOVE_TYPE 6 BND OTU RS1_SetBit[5]
            _branch_138 = bool(not tag("STATE1_IND"))
            _branch_140 = bool(tag("MOVE_TYPE") != 6)
            _branch_142 = _branch_138 or _branch_140
            if _branch_142:
                set_tag("RS1_SetBit[5]", False)
            _pc = 127
            continue
        elif _pc == 127:
            # rung 127
            # XIC RS1_OutBit[5] CPT NEXTSTATE 7
            if tag("RS1_OutBit[5]"):
                set_tag("NEXTSTATE", formula("7"))
            _pc = 128
            continue
        elif _pc == 128:
            # rung 128
            # XIC STATE1_IND CMP "MOVE_TYPE=7" XIO RS1_SetBit[6] OTE RS1_OutBit[6]
            set_tag(
                "RS1_OutBit[6]",
                bool(
                    (tag("STATE1_IND"))
                    and (formula("MOVE_TYPE=7"))
                    and (not tag("RS1_SetBit[6]"))
                ),
            )
            _pc = 129
            continue
        elif _pc == 129:
            # rung 129
            # XIC STATE1_IND CMP "MOVE_TYPE=7" OTL RS1_SetBit[6]
            if tag("STATE1_IND"):
                if formula("MOVE_TYPE=7"):
                    set_tag("RS1_SetBit[6]", True)
            _pc = 130
            continue
        elif _pc == 130:
            # rung 130
            # BST XIO STATE1_IND NXB NEQ MOVE_TYPE 7 BND OTU RS1_SetBit[6]
            _branch_143 = bool(not tag("STATE1_IND"))
            _branch_145 = bool(tag("MOVE_TYPE") != 7)
            _branch_147 = _branch_143 or _branch_145
            if _branch_147:
                set_tag("RS1_SetBit[6]", False)
            _pc = 131
            continue
        elif _pc == 131:
            # rung 131
            # XIC RS1_OutBit[6] CPT NEXTSTATE 8
            if tag("RS1_OutBit[6]"):
                set_tag("NEXTSTATE", formula("8"))
            _pc = 132
            continue
        elif _pc == 132:
            # rung 132
            # XIC STATE1_IND CMP "MOVE_TYPE=8" XIO RS1_SetBit[7] OTE RS1_OutBit[7]
            set_tag(
                "RS1_OutBit[7]",
                bool(
                    (tag("STATE1_IND"))
                    and (formula("MOVE_TYPE=8"))
                    and (not tag("RS1_SetBit[7]"))
                ),
            )
            _pc = 133
            continue
        elif _pc == 133:
            # rung 133
            # XIC STATE1_IND CMP "MOVE_TYPE=8" OTL RS1_SetBit[7]
            if tag("STATE1_IND"):
                if formula("MOVE_TYPE=8"):
                    set_tag("RS1_SetBit[7]", True)
            _pc = 134
            continue
        elif _pc == 134:
            # rung 134
            # BST XIO STATE1_IND NXB NEQ MOVE_TYPE 8 BND OTU RS1_SetBit[7]
            _branch_148 = bool(not tag("STATE1_IND"))
            _branch_150 = bool(tag("MOVE_TYPE") != 8)
            _branch_152 = _branch_148 or _branch_150
            if _branch_152:
                set_tag("RS1_SetBit[7]", False)
            _pc = 135
            continue
        elif _pc == 135:
            # rung 135
            # XIC RS1_OutBit[7] CPT NEXTSTATE 9
            if tag("RS1_OutBit[7]"):
                set_tag("NEXTSTATE", formula("9"))
            _pc = 136
            continue
        elif _pc == 136:
            # rung 136
            # XIC STATE1_IND CMP "MOVE_TYPE=11" XIO RS1_SetBit[8] OTE RS1_OutBit[8]
            set_tag(
                "RS1_OutBit[8]",
                bool(
                    (tag("STATE1_IND"))
                    and (formula("MOVE_TYPE=11"))
                    and (not tag("RS1_SetBit[8]"))
                ),
            )
            _pc = 137
            continue
        elif _pc == 137:
            # rung 137
            # XIC STATE1_IND CMP "MOVE_TYPE=11" OTL RS1_SetBit[8]
            if tag("STATE1_IND"):
                if formula("MOVE_TYPE=11"):
                    set_tag("RS1_SetBit[8]", True)
            _pc = 138
            continue
        elif _pc == 138:
            # rung 138
            # BST XIO STATE1_IND NXB NEQ MOVE_TYPE 11 BND OTU RS1_SetBit[8]
            _branch_153 = bool(not tag("STATE1_IND"))
            _branch_155 = bool(tag("MOVE_TYPE") != 11)
            _branch_157 = _branch_153 or _branch_155
            if _branch_157:
                set_tag("RS1_SetBit[8]", False)
            _pc = 139
            continue
        elif _pc == 139:
            # rung 139
            # XIC RS1_OutBit[8] CPT NEXTSTATE 14
            if tag("RS1_OutBit[8]"):
                set_tag("NEXTSTATE", formula("14"))
            _pc = 140
            continue
        elif _pc == 140:
            # rung 140
            # CMP "STATE=2" CPT NEXTSTATE 1
            if formula("STATE=2"):
                set_tag("NEXTSTATE", formula("1"))
            _pc = 141
            continue
        elif _pc == 141:
            # rung 141
            # XIO main_xy_move.IP CMP "STATE=3" BST XIC tension_stable_timer.DN NXB XIO check_tension_stable NXB XIO TENSION_CONTROL_OK BND BST BST XIO Z_RETRACTED NXB GEQ Z_axis.ActualPosition MAX_TOLERABLE_Z BND CPT ERROR_CODE 3001 CPT NEXTSTATE 10 NXB XIC Z_RETRACTED BST XIC APA_IS_VERTICAL NXB XIO APA_IS_VERTICAL CPT ERROR_CODE 3005 CPT NEXTSTATE 10 BND OTE STATE3_IND BND
            _branch_158 = bool(tag("tension_stable_timer.DN"))
            _branch_160 = bool(not tag("check_tension_stable"))
            _branch_162 = bool(not tag("TENSION_CONTROL_OK"))
            _branch_164 = _branch_158 or _branch_160 or _branch_162
            _branch_165 = bool(not tag("Z_RETRACTED"))
            _branch_167 = bool(tag("Z_axis.ActualPosition") >= tag("MAX_TOLERABLE_Z"))
            _branch_169 = _branch_165 or _branch_167
            if not tag("main_xy_move.IP"):
                if formula("STATE=3"):
                    if _branch_164:
                        if _branch_169:
                            set_tag("ERROR_CODE", formula("3001"))
            if not tag("main_xy_move.IP"):
                if formula("STATE=3"):
                    if _branch_164:
                        if _branch_169:
                            set_tag("NEXTSTATE", formula("10"))
            _branch_170 = bool(_branch_169)
            _branch_172 = bool(tag("APA_IS_VERTICAL"))
            if not tag("main_xy_move.IP"):
                if formula("STATE=3"):
                    if _branch_164:
                        if tag("Z_RETRACTED"):
                            if not tag("APA_IS_VERTICAL"):
                                set_tag("ERROR_CODE", formula("3005"))
            if not tag("main_xy_move.IP"):
                if formula("STATE=3"):
                    if _branch_164:
                        if tag("Z_RETRACTED"):
                            if not tag("APA_IS_VERTICAL"):
                                set_tag("NEXTSTATE", formula("10"))
            _branch_174 = bool(not tag("APA_IS_VERTICAL"))
            _branch_176 = _branch_172 or _branch_174
            set_tag(
                "STATE3_IND",
                bool(
                    (not tag("main_xy_move.IP"))
                    and (formula("STATE=3"))
                    and (_branch_164)
                    and (tag("Z_RETRACTED"))
                    and (_branch_176)
                ),
            )
            _branch_177 = bool((tag("Z_RETRACTED")) and (_branch_176))
            _branch_179 = _branch_170 or _branch_177
            _pc = 142
            continue
        elif _pc == 142:
            # rung 142
            # XIC STATE3_IND XIO MXY_state3_entry_oneshot_storage OTE MXY_state3_entry_oneshot
            set_tag(
                "MXY_state3_entry_oneshot",
                bool(
                    (tag("STATE3_IND"))
                    and (not tag("MXY_state3_entry_oneshot_storage"))
                ),
            )
            _pc = 143
            continue
        elif _pc == 143:
            # rung 143
            # XIC STATE3_IND OTL MXY_state3_entry_oneshot_storage
            if tag("STATE3_IND"):
                set_tag("MXY_state3_entry_oneshot_storage", True)
            _pc = 144
            continue
        elif _pc == 144:
            # rung 144
            # XIO STATE3_IND OTU MXY_state3_entry_oneshot_storage
            if not tag("STATE3_IND"):
                set_tag("MXY_state3_entry_oneshot_storage", False)
            _pc = 145
            continue
        elif _pc == 145:
            # rung 145
            # XIC STATE3_IND BST XIC X_Y.PhysicalAxisFault CPT ERROR_CODE 3002 NXB BST XIC X_axis.SafeTorqueOffInhibit NXB XIC Y_axis.SafeTorqueOffInhibit BND CPT ERROR_CODE 3004 BND CPT NEXTSTATE 10
            if tag("STATE3_IND"):
                if tag("X_Y.PhysicalAxisFault"):
                    set_tag("ERROR_CODE", formula("3002"))
            _branch_180 = bool(tag("X_Y.PhysicalAxisFault"))
            _branch_182 = bool(tag("X_axis.SafeTorqueOffInhibit"))
            _branch_184 = bool(tag("Y_axis.SafeTorqueOffInhibit"))
            _branch_186 = _branch_182 or _branch_184
            if tag("STATE3_IND"):
                if _branch_186:
                    set_tag("ERROR_CODE", formula("3004"))
            _branch_187 = bool(_branch_186)
            _branch_189 = _branch_180 or _branch_187
            if tag("STATE3_IND"):
                if _branch_189:
                    set_tag("NEXTSTATE", formula("10"))
            _pc = 146
            continue
        elif _pc == 146:
            # rung 146
            # XIC MXY_state3_entry_oneshot BST MSO X_axis MXY_x_axis_servo_on_status NXB MSO Y_axis MXY_y_axis_servo_on_status BND
            if tag("MXY_state3_entry_oneshot"):
                MSO(
                    axis="X_axis",
                    motion_control="MXY_x_axis_servo_on_status",
                )
            _branch_190 = bool(True)
            if tag("MXY_state3_entry_oneshot"):
                MSO(
                    axis="Y_axis",
                    motion_control="MXY_y_axis_servo_on_status",
                )
            _branch_192 = bool(True)
            _branch_194 = _branch_190 or _branch_192
            _pc = 147
            continue
        elif _pc == 147:
            # rung 147
            # XIC MXY_x_axis_servo_on_status.DN XIC MXY_y_axis_servo_on_status.DN XIO MXY_axes_servo_ready_oneshot_storage OTE MXY_axes_servo_ready_oneshot
            set_tag(
                "MXY_axes_servo_ready_oneshot",
                bool(
                    (tag("MXY_x_axis_servo_on_status.DN"))
                    and (tag("MXY_y_axis_servo_on_status.DN"))
                    and (not tag("MXY_axes_servo_ready_oneshot_storage"))
                ),
            )
            _pc = 148
            continue
        elif _pc == 148:
            # rung 148
            # XIC MXY_x_axis_servo_on_status.DN XIC MXY_y_axis_servo_on_status.DN OTL MXY_axes_servo_ready_oneshot_storage
            if tag("MXY_x_axis_servo_on_status.DN"):
                if tag("MXY_y_axis_servo_on_status.DN"):
                    set_tag("MXY_axes_servo_ready_oneshot_storage", True)
            _pc = 149
            continue
        elif _pc == 149:
            # rung 149
            # BST XIO MXY_x_axis_servo_on_status.DN NXB XIO MXY_y_axis_servo_on_status.DN BND OTU MXY_axes_servo_ready_oneshot_storage
            _branch_195 = bool(not tag("MXY_x_axis_servo_on_status.DN"))
            _branch_197 = bool(not tag("MXY_y_axis_servo_on_status.DN"))
            _branch_199 = _branch_195 or _branch_197
            if _branch_199:
                set_tag("MXY_axes_servo_ready_oneshot_storage", False)
            _pc = 150
            continue
        elif _pc == 150:
            # rung 150
            # BST XIC MXY_axes_servo_ready_oneshot NXB XIC MXY_x_axis_servo_on_status.DN XIC MXY_y_axis_servo_on_status.DN XIC MXY_state3_entry_oneshot BND XIO MXY_trigger_xy_move_oneshot_storage OTE trigger_xy_move
            _branch_200 = bool(tag("MXY_axes_servo_ready_oneshot"))
            _branch_202 = bool(
                (tag("MXY_x_axis_servo_on_status.DN"))
                and (tag("MXY_y_axis_servo_on_status.DN"))
                and (tag("MXY_state3_entry_oneshot"))
            )
            _branch_204 = _branch_200 or _branch_202
            set_tag(
                "trigger_xy_move",
                bool(
                    (_branch_204) and (not tag("MXY_trigger_xy_move_oneshot_storage"))
                ),
            )
            _pc = 151
            continue
        elif _pc == 151:
            # rung 151
            # BST XIC MXY_axes_servo_ready_oneshot NXB XIC MXY_x_axis_servo_on_status.DN XIC MXY_y_axis_servo_on_status.DN XIC MXY_state3_entry_oneshot BND OTL MXY_trigger_xy_move_oneshot_storage
            _branch_205 = bool(tag("MXY_axes_servo_ready_oneshot"))
            _branch_207 = bool(
                (tag("MXY_x_axis_servo_on_status.DN"))
                and (tag("MXY_y_axis_servo_on_status.DN"))
                and (tag("MXY_state3_entry_oneshot"))
            )
            _branch_209 = _branch_205 or _branch_207
            if _branch_209:
                set_tag("MXY_trigger_xy_move_oneshot_storage", True)
            _pc = 152
            continue
        elif _pc == 152:
            # rung 152
            # BST XIO MXY_axes_servo_ready_oneshot NXB BST XIO MXY_x_axis_servo_on_status.DN NXB XIO MXY_y_axis_servo_on_status.DN NXB XIO MXY_state3_entry_oneshot BND BND OTU MXY_trigger_xy_move_oneshot_storage
            _branch_210 = bool(not tag("MXY_axes_servo_ready_oneshot"))
            _branch_212 = bool(not tag("MXY_x_axis_servo_on_status.DN"))
            _branch_214 = bool(not tag("MXY_y_axis_servo_on_status.DN"))
            _branch_216 = bool(not tag("MXY_state3_entry_oneshot"))
            _branch_218 = _branch_212 or _branch_214 or _branch_216
            _branch_219 = bool(_branch_218)
            _branch_221 = _branch_210 or _branch_219
            if _branch_221:
                set_tag("MXY_trigger_xy_move_oneshot_storage", False)
            _pc = 153
            continue
        elif _pc == 153:
            # rung 153
            # XIC trigger_xy_move MOV X_axis.ActualPosition starting_x MOV Y_axis.ActualPosition starting_y
            if tag("trigger_xy_move"):
                set_tag("starting_x", tag("X_axis.ActualPosition"))
            if tag("trigger_xy_move"):
                set_tag("starting_y", tag("Y_axis.ActualPosition"))
            _pc = 154
            continue
        elif _pc == 154:
            # rung 154
            # XIC trigger_xy_move CPT dx ABS(starting_x-X_POSITION) CPT dy ABS(starting_y-Y_POSITION) CPT x_time v_x_max/dx CPT y_time v_y_max/dy BST LES x_time y_time CPT k x_time NXB LEQ y_time x_time CPT k y_time BND CPT v_max k*SQR(dx*dx+dy*dy) BST LES v_max XY_SPEED CPT XY_SPEED_REQ v_max NXB LEQ XY_SPEED v_max CPT XY_SPEED_REQ XY_SPEED BND
            if tag("trigger_xy_move"):
                set_tag("dx", formula("ABS(starting_x-X_POSITION)"))
            if tag("trigger_xy_move"):
                set_tag("dy", formula("ABS(starting_y-Y_POSITION)"))
            if tag("trigger_xy_move"):
                set_tag("x_time", formula("v_x_max/dx"))
            if tag("trigger_xy_move"):
                set_tag("y_time", formula("v_y_max/dy"))
            if tag("trigger_xy_move"):
                if tag("x_time") < tag("y_time"):
                    set_tag("k", formula("x_time"))
            _branch_222 = bool(tag("x_time") < tag("y_time"))
            if tag("trigger_xy_move"):
                if tag("y_time") <= tag("x_time"):
                    set_tag("k", formula("y_time"))
            _branch_224 = bool(tag("y_time") <= tag("x_time"))
            _branch_226 = _branch_222 or _branch_224
            if tag("trigger_xy_move"):
                if _branch_226:
                    set_tag("v_max", formula("k*SQR(dx*dx+dy*dy)"))
            if tag("trigger_xy_move"):
                if _branch_226:
                    if tag("v_max") < tag("XY_SPEED"):
                        set_tag("XY_SPEED_REQ", formula("v_max"))
            _branch_227 = bool(tag("v_max") < tag("XY_SPEED"))
            if tag("trigger_xy_move"):
                if _branch_226:
                    if tag("XY_SPEED") <= tag("v_max"):
                        set_tag("XY_SPEED_REQ", formula("XY_SPEED"))
            _branch_229 = bool(tag("XY_SPEED") <= tag("v_max"))
            _branch_231 = _branch_227 or _branch_229
            _pc = 155
            continue
        elif _pc == 155:
            # rung 155
            # CPT x_dist_to_target X_axis.ActualPosition-X_POSITION CPT y_dist_to_target Y_axis.ActualPosition-Y_POSITION CPT xy_dist_to_target SQR(x_dist_to_target*x_dist_to_target+y_dist_to_target*y_dist_to_target)
            set_tag("x_dist_to_target", formula("X_axis.ActualPosition-X_POSITION"))
            set_tag("y_dist_to_target", formula("Y_axis.ActualPosition-Y_POSITION"))
            set_tag(
                "xy_dist_to_target",
                formula(
                    "SQR(x_dist_to_target*x_dist_to_target+y_dist_to_target*y_dist_to_target)"
                ),
            )
            _pc = 156
            continue
        elif _pc == 156:
            # rung 156
            # MOV xy_decel_jerk J MOV v_xyz v_0 CPT gamma SQR(accel_xy*accel_xy+4*J*v_0) CPT stopping_distance (accel_xy+gamma)*(accel_xy+gamma)*(accel_xy+gamma)/(6*J*J)
            set_tag("J", tag("xy_decel_jerk"))
            set_tag("v_0", tag("v_xyz"))
            set_tag("gamma", formula("SQR(accel_xy*accel_xy+4*J*v_0)"))
            set_tag(
                "stopping_distance",
                formula("(accel_xy+gamma)*(accel_xy+gamma)*(accel_xy+gamma)/(6*J*J)"),
            )
            _pc = 157
            continue
        elif _pc == 157:
            # rung 157
            # CMP "xy_dist_to_target<stopping_distance*1" OTE near_ending
            set_tag(
                "near_ending", bool(formula("xy_dist_to_target<stopping_distance*1"))
            )
            _pc = 158
            continue
        elif _pc == 158:
            # rung 158
            # CMP "STATE=3" CPT stopping_ratio stopping_distance/xy_dist_to_target
            if formula("STATE=3"):
                set_tag(
                    "stopping_ratio", formula("stopping_distance/xy_dist_to_target")
                )
            _pc = 159
            continue
        elif _pc == 159:
            # rung 159
            # XIC TENSION_CONTROL_OK XIC speed_regulator_switch XIC trigger_xy_move MCLM X_Y main_xy_move 0 X_POSITION v_max "Units per sec" xy_regulated_acceleration "Units per sec2" xy_regulated_deceleration "Units per sec2" S-Curve xy_regulated_accel_jerk xy_decel_jerk "Units per sec3" 0 Disabled Programmed 50 0 None 0 0
            MCLM(
                coordinate_system="X_Y",
                motion_control="main_xy_move",
                move_type=0,
                target="X_POSITION",
                speed="v_max",
                speed_units="Units per sec",
                accel="xy_regulated_acceleration",
                accel_units="Units per sec2",
                decel="xy_regulated_deceleration",
                decel_units="Units per sec2",
                profile="S-Curve",
                accel_jerk="xy_regulated_accel_jerk",
                decel_jerk="xy_decel_jerk",
                jerk_units="Units per sec3",
                termination_type=0,
                merge="Disabled",
                merge_speed="Programmed",
                command_tolerance=50,
                lock_position=0,
                lock_direction="None",
                event_distance=0,
                calculated_data=0,
                rung_in=(tag("TENSION_CONTROL_OK"))
                and (tag("speed_regulator_switch"))
                and (tag("trigger_xy_move")),
            )
            _pc = 160
            continue
        elif _pc == 160:
            # rung 160
            # XIC TENSION_CONTROL_OK XIC speed_regulator_switch XIC trigger_xy_move MOV xy_dt regulator_loop_timer.PRE MOV xy_d_dt xy_d_timer.PRE MOV 0 xy_i_term
            if tag("TENSION_CONTROL_OK"):
                if tag("speed_regulator_switch"):
                    if tag("trigger_xy_move"):
                        set_tag("regulator_loop_timer.PRE", tag("xy_dt"))
            if tag("TENSION_CONTROL_OK"):
                if tag("speed_regulator_switch"):
                    if tag("trigger_xy_move"):
                        set_tag("xy_d_timer.PRE", tag("xy_d_dt"))
            if tag("TENSION_CONTROL_OK"):
                if tag("speed_regulator_switch"):
                    if tag("trigger_xy_move"):
                        set_tag("xy_i_term", 0)
            _pc = 161
            continue
        elif _pc == 161:
            # rung 161
            # XIC TENSION_CONTROL_OK XIC speed_regulator_switch XIO regulator_loop_timer.DN TON regulator_loop_timer 1 0
            TON(
                timer_tag="regulator_loop_timer",
                preset=1,
                accum=0,
                rung_in=(tag("TENSION_CONTROL_OK"))
                and (tag("speed_regulator_switch"))
                and (not tag("regulator_loop_timer.DN")),
            )
            _pc = 162
            continue
        elif _pc == 162:
            # rung 162
            # XIC TENSION_CONTROL_OK XIC speed_regulator_switch XIO xy_d_timer.DN TON xy_d_timer 1 0
            TON(
                timer_tag="xy_d_timer",
                preset=1,
                accum=0,
                rung_in=(tag("TENSION_CONTROL_OK"))
                and (tag("speed_regulator_switch"))
                and (not tag("xy_d_timer.DN")),
            )
            _pc = 163
            continue
        elif _pc == 163:
            # rung 163
            # XIC TENSION_CONTROL_OK XIC speed_regulator_switch XIC xy_d_timer.DN CPT d_raw xy_kd*(xy_error-xy_error_prev)/xy_d_dt*100 CPT xy_d_term xy_d_alpha*d_raw+(1-xy_d_alpha)*xy_d_term_prev MOV xy_error xy_error_prev MOV xy_d_term xy_d_term_prev
            if tag("TENSION_CONTROL_OK"):
                if tag("speed_regulator_switch"):
                    if tag("xy_d_timer.DN"):
                        set_tag(
                            "d_raw",
                            formula("xy_kd*(xy_error-xy_error_prev)/xy_d_dt*100"),
                        )
            if tag("TENSION_CONTROL_OK"):
                if tag("speed_regulator_switch"):
                    if tag("xy_d_timer.DN"):
                        set_tag(
                            "xy_d_term",
                            formula("xy_d_alpha*d_raw+(1-xy_d_alpha)*xy_d_term_prev"),
                        )
            if tag("TENSION_CONTROL_OK"):
                if tag("speed_regulator_switch"):
                    if tag("xy_d_timer.DN"):
                        set_tag("xy_error_prev", tag("xy_error"))
            if tag("TENSION_CONTROL_OK"):
                if tag("speed_regulator_switch"):
                    if tag("xy_d_timer.DN"):
                        set_tag("xy_d_term_prev", tag("xy_d_term"))
            _pc = 164
            continue
        elif _pc == 164:
            # rung 164
            # XIC TENSION_CONTROL_OK XIC speed_regulator_switch CPT xy_error speed_tension_setpoint-tension
            if tag("TENSION_CONTROL_OK"):
                if tag("speed_regulator_switch"):
                    set_tag("xy_error", formula("speed_tension_setpoint-tension"))
            _pc = 165
            continue
        elif _pc == 165:
            # rung 165
            # XIC TENSION_CONTROL_OK XIC speed_regulator_switch XIC regulator_loop_timer.DN CPT xy_p_term xy_kp*xy_error
            if tag("TENSION_CONTROL_OK"):
                if tag("speed_regulator_switch"):
                    if tag("regulator_loop_timer.DN"):
                        set_tag("xy_p_term", formula("xy_kp*xy_error"))
            _pc = 166
            continue
        elif _pc == 166:
            # rung 166
            # XIC TENSION_CONTROL_OK XIC speed_regulator_switch XIC regulator_loop_timer.DN BST LES regulated_speed v_max NXB LES xy_error 0 BND BST GRT regulated_speed min_regulated_speed NXB GRT xy_error 0 BND CPT xy_i_term xy_i_term+(xy_ki*xy_error*xy_dt/1000) BST LES xy_i_term min_integral MOV min_integral xy_i_term NXB GRT xy_i_term max_integral MOV max_integral xy_i_term BND
            _branch_232 = bool(tag("regulated_speed") < tag("v_max"))
            _branch_234 = bool(tag("xy_error") < 0)
            _branch_236 = _branch_232 or _branch_234
            _branch_237 = bool(tag("regulated_speed") > tag("min_regulated_speed"))
            _branch_239 = bool(tag("xy_error") > 0)
            _branch_241 = _branch_237 or _branch_239
            if tag("TENSION_CONTROL_OK"):
                if tag("speed_regulator_switch"):
                    if tag("regulator_loop_timer.DN"):
                        if _branch_236:
                            if _branch_241:
                                set_tag(
                                    "xy_i_term",
                                    formula("xy_i_term+(xy_ki*xy_error*xy_dt/1000)"),
                                )
            if tag("TENSION_CONTROL_OK"):
                if tag("speed_regulator_switch"):
                    if tag("regulator_loop_timer.DN"):
                        if _branch_236:
                            if _branch_241:
                                if tag("xy_i_term") < tag("min_integral"):
                                    set_tag("xy_i_term", tag("min_integral"))
            _branch_242 = bool(tag("xy_i_term") < tag("min_integral"))
            if tag("TENSION_CONTROL_OK"):
                if tag("speed_regulator_switch"):
                    if tag("regulator_loop_timer.DN"):
                        if _branch_236:
                            if _branch_241:
                                if tag("xy_i_term") > tag("max_integral"):
                                    set_tag("xy_i_term", tag("max_integral"))
            _branch_244 = bool(tag("xy_i_term") > tag("max_integral"))
            _branch_246 = _branch_242 or _branch_244
            _pc = 167
            continue
        elif _pc == 167:
            # rung 167
            # XIC TENSION_CONTROL_OK XIC speed_regulator_switch XIC regulator_loop_timer.DN CPT regulated_speed xy_default_speed+xy_p_term+xy_i_term+xy_d_term BST LES v_max regulated_speed MOV v_max regulated_speed NXB LES regulated_speed min_regulated_speed MOV min_regulated_speed regulated_speed BND
            if tag("TENSION_CONTROL_OK"):
                if tag("speed_regulator_switch"):
                    if tag("regulator_loop_timer.DN"):
                        set_tag(
                            "regulated_speed",
                            formula("xy_default_speed+xy_p_term+xy_i_term+xy_d_term"),
                        )
            if tag("TENSION_CONTROL_OK"):
                if tag("speed_regulator_switch"):
                    if tag("regulator_loop_timer.DN"):
                        if tag("v_max") < tag("regulated_speed"):
                            set_tag("regulated_speed", tag("v_max"))
            _branch_247 = bool(tag("v_max") < tag("regulated_speed"))
            if tag("TENSION_CONTROL_OK"):
                if tag("speed_regulator_switch"):
                    if tag("regulator_loop_timer.DN"):
                        if tag("regulated_speed") < tag("min_regulated_speed"):
                            set_tag("regulated_speed", tag("min_regulated_speed"))
            _branch_249 = bool(tag("regulated_speed") < tag("min_regulated_speed"))
            _branch_251 = _branch_247 or _branch_249
            _pc = 168
            continue
        elif _pc == 168:
            # rung 168
            # BST XIO TENSION_CONTROL_OK NXB XIC TENSION_CONTROL_OK XIO speed_regulator_switch BND XIC trigger_xy_move MCLM X_Y main_xy_move 0 X_POSITION XY_SPEED_REQ "Units per sec" XY_ACCELERATION "Units per sec2" XY_DECELERATION "Units per sec2" S-Curve 500 500 "Units per sec3" 0 Disabled Programmed 50 0 None 0 0
            _branch_252 = bool(not tag("TENSION_CONTROL_OK"))
            _branch_254 = bool(
                (tag("TENSION_CONTROL_OK")) and (not tag("speed_regulator_switch"))
            )
            _branch_256 = _branch_252 or _branch_254
            MCLM(
                coordinate_system="X_Y",
                motion_control="main_xy_move",
                move_type=0,
                target="X_POSITION",
                speed="XY_SPEED_REQ",
                speed_units="Units per sec",
                accel="XY_ACCELERATION",
                accel_units="Units per sec2",
                decel="XY_DECELERATION",
                decel_units="Units per sec2",
                profile="S-Curve",
                accel_jerk=500,
                decel_jerk=500,
                jerk_units="Units per sec3",
                termination_type=0,
                merge="Disabled",
                merge_speed="Programmed",
                command_tolerance=50,
                lock_position=0,
                lock_direction="None",
                event_distance=0,
                calculated_data=0,
                rung_in=(_branch_256) and (tag("trigger_xy_move")),
            )
            _pc = 169
            continue
        elif _pc == 169:
            # rung 169
            # XIO speed_regulator_switch XIC MXY_speed_regulator_disabled_oneshot_storage OTE MXY_speed_regulator_disabled_oneshot
            set_tag(
                "MXY_speed_regulator_disabled_oneshot",
                bool(
                    (not tag("speed_regulator_switch"))
                    and (tag("MXY_speed_regulator_disabled_oneshot_storage"))
                ),
            )
            _pc = 170
            continue
        elif _pc == 170:
            # rung 170
            # XIC speed_regulator_switch OTL MXY_speed_regulator_disabled_oneshot_storage
            if tag("speed_regulator_switch"):
                set_tag("MXY_speed_regulator_disabled_oneshot_storage", True)
            _pc = 171
            continue
        elif _pc == 171:
            # rung 171
            # XIO speed_regulator_switch OTU MXY_speed_regulator_disabled_oneshot_storage
            if not tag("speed_regulator_switch"):
                set_tag("MXY_speed_regulator_disabled_oneshot_storage", False)
            _pc = 172
            continue
        elif _pc == 172:
            # rung 172
            # XIC MXY_speed_regulator_disabled_oneshot XIO near_ending MCCD X_Y MCCD_X_Y_Axis1 "Coordinated Move" Yes XY_SPEED_REQ "Units per sec" Yes XY_ACCELERATION "Units per sec2" Yes XY_DECELERATION "Units per sec2" No xy_accel_jerk No xy_decel_jerk "Units per sec3" "Active Motion"
            if tag("MXY_speed_regulator_disabled_oneshot"):
                if not tag("near_ending"):
                    MCCD(
                        coordinate_system="X_Y",
                        motion_control="MCCD_X_Y_Axis1",
                        scope="Coordinated Move",
                        speed_enable="Yes",
                        speed="XY_SPEED_REQ",
                        speed_units="Units per sec",
                        accel_enable="Yes",
                        accel="XY_ACCELERATION",
                        accel_units="Units per sec2",
                        decel_enable="Yes",
                        decel="XY_DECELERATION",
                        decel_units="Units per sec2",
                        accel_jerk_enable="No",
                        accel_jerk="xy_accel_jerk",
                        decel_jerk_enable="No",
                        decel_jerk="xy_decel_jerk",
                        jerk_units="Units per sec3",
                        apply_to="Active Motion",
                    )
            _pc = 173
            continue
        elif _pc == 173:
            # rung 173
            # BST XIC main_xy_move.PC NXB XIC main_xy_move.ER BND BST CMP "X_axis.ActualPosition<(X_POSITION+0.1)" NXB XIC STATE3_IND CMP "MOVE_TYPE=0" CPT ERROR_CODE 3003 BND XIO MXY_xy_move_done_or_fault_oneshot_storage OTE MXY_xy_move_done_or_fault_oneshot
            _branch_257 = bool(tag("main_xy_move.PC"))
            _branch_259 = bool(tag("main_xy_move.ER"))
            _branch_261 = _branch_257 or _branch_259
            _branch_262 = bool(formula("X_axis.ActualPosition<(X_POSITION+0.1)"))
            if _branch_261:
                if tag("STATE3_IND"):
                    if formula("MOVE_TYPE=0"):
                        set_tag("ERROR_CODE", formula("3003"))
            _branch_264 = bool((tag("STATE3_IND")) and (formula("MOVE_TYPE=0")))
            _branch_266 = _branch_262 or _branch_264
            set_tag(
                "MXY_xy_move_done_or_fault_oneshot",
                bool(
                    (_branch_261)
                    and (_branch_266)
                    and (not tag("MXY_xy_move_done_or_fault_oneshot_storage"))
                ),
            )
            _pc = 174
            continue
        elif _pc == 174:
            # rung 174
            # BST XIC main_xy_move.PC NXB XIC main_xy_move.ER BND BST CMP "X_axis.ActualPosition<(X_POSITION+0.1)" NXB XIC STATE3_IND CMP "MOVE_TYPE=0" CPT ERROR_CODE 3003 BND OTL MXY_xy_move_done_or_fault_oneshot_storage
            _branch_267 = bool(tag("main_xy_move.PC"))
            _branch_269 = bool(tag("main_xy_move.ER"))
            _branch_271 = _branch_267 or _branch_269
            _branch_272 = bool(formula("X_axis.ActualPosition<(X_POSITION+0.1)"))
            if _branch_271:
                if tag("STATE3_IND"):
                    if formula("MOVE_TYPE=0"):
                        set_tag("ERROR_CODE", formula("3003"))
            _branch_274 = bool((tag("STATE3_IND")) and (formula("MOVE_TYPE=0")))
            _branch_276 = _branch_272 or _branch_274
            if _branch_271:
                if _branch_276:
                    set_tag("MXY_xy_move_done_or_fault_oneshot_storage", True)
            _pc = 175
            continue
        elif _pc == 175:
            # rung 175
            # BST XIO main_xy_move.PC NXB XIO main_xy_move.ER BND OTU MXY_xy_move_done_or_fault_oneshot_storage
            _branch_277 = bool(not tag("main_xy_move.PC"))
            _branch_279 = bool(not tag("main_xy_move.ER"))
            _branch_281 = _branch_277 or _branch_279
            if _branch_281:
                set_tag("MXY_xy_move_done_or_fault_oneshot_storage", False)
            _pc = 176
            continue
        elif _pc == 176:
            # rung 176
            # XIC main_xy_move.IP CMP "MOVE_TYPE=11" CPT NEXTSTATE 14
            if tag("main_xy_move.IP"):
                if formula("MOVE_TYPE=11"):
                    set_tag("NEXTSTATE", formula("14"))
            _pc = 177
            continue
        elif _pc == 177:
            # rung 177
            # XIC main_xy_move.IP XIO ALL_EOT_GOOD XIO MXY_eot_triggered_oneshot_storage OTE MXY_eot_triggered
            set_tag(
                "MXY_eot_triggered",
                bool(
                    (tag("main_xy_move.IP"))
                    and (not tag("ALL_EOT_GOOD"))
                    and (not tag("MXY_eot_triggered_oneshot_storage"))
                ),
            )
            _pc = 178
            continue
        elif _pc == 178:
            # rung 178
            # XIC main_xy_move.IP XIO ALL_EOT_GOOD OTL MXY_eot_triggered_oneshot_storage
            if tag("main_xy_move.IP"):
                if not tag("ALL_EOT_GOOD"):
                    set_tag("MXY_eot_triggered_oneshot_storage", True)
            _pc = 179
            continue
        elif _pc == 179:
            # rung 179
            # BST XIO main_xy_move.IP NXB XIC ALL_EOT_GOOD BND OTU MXY_eot_triggered_oneshot_storage
            _branch_282 = bool(not tag("main_xy_move.IP"))
            _branch_284 = bool(tag("ALL_EOT_GOOD"))
            _branch_286 = _branch_282 or _branch_284
            if _branch_286:
                set_tag("MXY_eot_triggered_oneshot_storage", False)
            _pc = 180
            continue
        elif _pc == 180:
            # rung 180
            # XIC MXY_eot_triggered MCS X_Y MXY_eot_stop_status All Yes 10000 "Units per sec2" Yes 1000 "Units per sec3" CPT NEXTSTATE 11 CPT MOVE_TYPE 0
            if tag("MXY_eot_triggered"):
                MCS(
                    coordinate_system="X_Y",
                    motion_control="MXY_eot_stop_status",
                    stop_type="All",
                    change_decel="Yes",
                    decel=10000,
                    decel_units="Units per sec2",
                    change_jerk="Yes",
                    jerk=1000,
                    jerk_units="Units per sec3",
                )
            if tag("MXY_eot_triggered"):
                set_tag("NEXTSTATE", formula("11"))
            if tag("MXY_eot_triggered"):
                set_tag("MOVE_TYPE", formula("0"))
            _pc = 181
            continue
        elif _pc == 181:
            # rung 181
            # XIC MXY_eot_triggered MCS X_Y MXY_eot_stop_status All Yes 10000 "Units per sec2" Yes 1000 "Units per sec3" CPT NEXTSTATE 11 CPT MOVE_TYPE 0
            if tag("MXY_eot_triggered"):
                MCS(
                    coordinate_system="X_Y",
                    motion_control="MXY_eot_stop_status",
                    stop_type="All",
                    change_decel="Yes",
                    decel=10000,
                    decel_units="Units per sec2",
                    change_jerk="Yes",
                    jerk=1000,
                    jerk_units="Units per sec3",
                )
            if tag("MXY_eot_triggered"):
                set_tag("NEXTSTATE", formula("11"))
            if tag("MXY_eot_triggered"):
                set_tag("MOVE_TYPE", formula("0"))
            _pc = 182
            continue
        elif _pc == 182:
            # rung 182
            # XIC MXY_xy_move_done_or_fault_oneshot CPT MOVE_TYPE 0 CPT NEXTSTATE 1
            if tag("MXY_xy_move_done_or_fault_oneshot"):
                set_tag("MOVE_TYPE", formula("0"))
            if tag("MXY_xy_move_done_or_fault_oneshot"):
                set_tag("NEXTSTATE", formula("1"))
            _pc = 183
            continue
        elif _pc == 183:
            # rung 183
            # BST XIC Z_FIXED_LATCHED EQU ACTUATOR_POS 2 NXB XIO Z_FIXED_LATCHED BND OTE no_latch_collision
            _branch_287 = bool((tag("Z_FIXED_LATCHED")) and (tag("ACTUATOR_POS") == 2))
            _branch_289 = bool(not tag("Z_FIXED_LATCHED"))
            _branch_291 = _branch_287 or _branch_289
            set_tag("no_latch_collision", bool(_branch_291))
            _pc = 184
            continue
        elif _pc == 184:
            # rung 184
            # BST XIC X_XFER_OK NXB XIC Y_XFER_OK BND OTE no_apa_collision
            _branch_292 = bool(tag("X_XFER_OK"))
            _branch_294 = bool(tag("Y_XFER_OK"))
            _branch_296 = _branch_292 or _branch_294
            set_tag("no_apa_collision", bool(_branch_296))
            _pc = 185
            continue
        elif _pc == 185:
            # rung 185
            # BST XIC X_XFER_OK BST LIM 400 X_axis.ActualPosition 500 BST XIC support_collision_window_bttm XIO FRAME_LOC_HD_BTM NXB XIC support_collision_window_mid XIO FRAME_LOC_HD_MID NXB XIC support_collision_window_top XIO FRAME_LOC_HD_TOP BND NXB LIM 7100 X_axis.ActualPosition 7200 BST XIC support_collision_window_bttm XIO FRAME_LOC_FT_BTM NXB XIC support_collision_window_mid XIO FRAME_LOC_FT_MID NXB XIC support_collision_window_top XIO FRAME_LOC_FT_TOP BND NXB XIO support_collision_window_bttm XIO support_collision_window_mid XIO support_collision_window_top BND NXB XIC Y_XFER_OK BND OTE no_supports_collision
            _branch_297 = bool(
                (tag("support_collision_window_bttm")) and (not tag("FRAME_LOC_HD_BTM"))
            )
            _branch_299 = bool(
                (tag("support_collision_window_mid")) and (not tag("FRAME_LOC_HD_MID"))
            )
            _branch_301 = bool(
                (tag("support_collision_window_top")) and (not tag("FRAME_LOC_HD_TOP"))
            )
            _branch_303 = _branch_297 or _branch_299 or _branch_301
            _branch_304 = bool(
                (400 <= tag("X_axis.ActualPosition") <= 500) and (_branch_303)
            )
            _branch_306 = bool(
                (tag("support_collision_window_bttm")) and (not tag("FRAME_LOC_FT_BTM"))
            )
            _branch_308 = bool(
                (tag("support_collision_window_mid")) and (not tag("FRAME_LOC_FT_MID"))
            )
            _branch_310 = bool(
                (tag("support_collision_window_top")) and (not tag("FRAME_LOC_FT_TOP"))
            )
            _branch_312 = _branch_306 or _branch_308 or _branch_310
            _branch_313 = bool(
                (7100 <= tag("X_axis.ActualPosition") <= 7200) and (_branch_312)
            )
            _branch_315 = bool(
                (not tag("support_collision_window_bttm"))
                and (not tag("support_collision_window_mid"))
                and (not tag("support_collision_window_top"))
            )
            _branch_317 = _branch_304 or _branch_313 or _branch_315
            _branch_318 = bool((tag("X_XFER_OK")) and (_branch_317))
            _branch_320 = bool(tag("Y_XFER_OK"))
            _branch_322 = _branch_318 or _branch_320
            set_tag("no_supports_collision", bool(_branch_322))
            _pc = 186
            continue
        elif _pc == 186:
            # rung 186
            # XIC no_latch_collision XIC no_supports_collision XIC no_apa_collision OTE MASTER_Z_GO
            set_tag(
                "MASTER_Z_GO",
                bool(
                    (tag("no_latch_collision"))
                    and (tag("no_supports_collision"))
                    and (tag("no_apa_collision"))
                ),
            )
            _pc = 187
            continue
        elif _pc == 187:
            # rung 187
            # CMP "STATE=4" MOV 1 NEXTSTATE
            if formula("STATE=4"):
                set_tag("NEXTSTATE", 1)
            _pc = 188
            continue
        elif _pc == 188:
            # rung 188
            # CMP "STATE=5" XIC Z_FIXED_LATCHED XIC LATCH_ACTUATOR_HOMED CMP "ACTUATOR_POS<>2" CPT ERROR_CODE 5004 CPT NEXTSTATE 10
            if formula("STATE=5"):
                if tag("Z_FIXED_LATCHED"):
                    if tag("LATCH_ACTUATOR_HOMED"):
                        if formula("ACTUATOR_POS<>2"):
                            set_tag("ERROR_CODE", formula("5004"))
            if formula("STATE=5"):
                if tag("Z_FIXED_LATCHED"):
                    if tag("LATCH_ACTUATOR_HOMED"):
                        if formula("ACTUATOR_POS<>2"):
                            set_tag("NEXTSTATE", formula("10"))
            _pc = 189
            continue
        elif _pc == 189:
            # rung 189
            # CMP "STATE=5" XIC Z_axis.PhysicalAxisFault CPT ERROR_CODE 5002 CPT NEXTSTATE 10
            if formula("STATE=5"):
                if tag("Z_axis.PhysicalAxisFault"):
                    set_tag("ERROR_CODE", formula("5002"))
            if formula("STATE=5"):
                if tag("Z_axis.PhysicalAxisFault"):
                    set_tag("NEXTSTATE", formula("10"))
            _pc = 190
            continue
        elif _pc == 190:
            # rung 190
            # CMP "STATE=5" XIO MASTER_Z_GO CPT ERROR_CODE 5001 CPT NEXTSTATE 10
            if formula("STATE=5"):
                if not tag("MASTER_Z_GO"):
                    set_tag("ERROR_CODE", formula("5001"))
            if formula("STATE=5"):
                if not tag("MASTER_Z_GO"):
                    set_tag("NEXTSTATE", formula("10"))
            _pc = 191
            continue
        elif _pc == 191:
            # rung 191
            # CMP "STATE=5" XIC MASTER_Z_GO BST XIC tension_stable_timer.DN NXB XIO check_tension_stable NXB XIO TENSION_CONTROL_OK NXB XIC Z_FIXED_LATCHED BND OTE STATE5_IND
            _branch_323 = bool(tag("tension_stable_timer.DN"))
            _branch_325 = bool(not tag("check_tension_stable"))
            _branch_327 = bool(not tag("TENSION_CONTROL_OK"))
            _branch_329 = bool(tag("Z_FIXED_LATCHED"))
            _branch_331 = _branch_323 or _branch_325 or _branch_327 or _branch_329
            set_tag(
                "STATE5_IND",
                bool((formula("STATE=5")) and (tag("MASTER_Z_GO")) and (_branch_331)),
            )
            _pc = 192
            continue
        elif _pc == 192:
            # rung 192
            # XIC STATE5_IND XIO Z_axis.DriveEnableStatus MSO Z_axis z_axis_mso
            if tag("STATE5_IND"):
                if not tag("Z_axis.DriveEnableStatus"):
                    MSO(
                        axis="Z_axis",
                        motion_control="z_axis_mso",
                    )
            _pc = 193
            continue
        elif _pc == 193:
            # rung 193
            # XIC STATE5_IND XIC Z_axis.DriveEnableStatus XIO Z_FIXED_LATCHED MAM Z_axis z_axis_main_move 0 Z_POSITION Z_SPEED "Units per sec" Z_ACCELERATION "Units per sec2" Z_DECELLERATION "Units per sec2" S-Curve z_accel_jerk z_decel_jerk "Units per sec3" Disabled Programmed 0 None 0 0
            MAM(
                axis="Z_axis",
                motion_control="z_axis_main_move",
                move_type=0,
                target="Z_POSITION",
                speed="Z_SPEED",
                speed_units="Units per sec",
                accel="Z_ACCELERATION",
                accel_units="Units per sec2",
                decel="Z_DECELLERATION",
                decel_units="Units per sec2",
                profile="S-Curve",
                accel_jerk="z_accel_jerk",
                decel_jerk="z_decel_jerk",
                jerk_units="Units per sec3",
                merge="Disabled",
                merge_speed="Programmed",
                lock_position=0,
                lock_direction="None",
                event_distance=0,
                calculated_data=0,
                rung_in=(tag("STATE5_IND"))
                and (tag("Z_axis.DriveEnableStatus"))
                and (not tag("Z_FIXED_LATCHED")),
            )
            _pc = 194
            continue
        elif _pc == 194:
            # rung 194
            # XIC STATE5_IND XIC Z_axis.DriveEnableStatus XIC Z_FIXED_LATCHED MAM Z_axis z_axis_fast_move 0 Z_POSITION 1000 "Units per sec" 10000 "Units per sec2" 10000 "Units per sec2" S-Curve 10000 10000 "Units per sec3" Disabled Programmed 0 None 0 0
            MAM(
                axis="Z_axis",
                motion_control="z_axis_fast_move",
                move_type=0,
                target="Z_POSITION",
                speed=1000,
                speed_units="Units per sec",
                accel=10000,
                accel_units="Units per sec2",
                decel=10000,
                decel_units="Units per sec2",
                profile="S-Curve",
                accel_jerk=10000,
                decel_jerk=10000,
                jerk_units="Units per sec3",
                merge="Disabled",
                merge_speed="Programmed",
                lock_position=0,
                lock_direction="None",
                event_distance=0,
                calculated_data=0,
                rung_in=(tag("STATE5_IND"))
                and (tag("Z_axis.DriveEnableStatus"))
                and (tag("Z_FIXED_LATCHED")),
            )
            _pc = 195
            continue
        elif _pc == 195:
            # rung 195
            # XIC Z_axis.MoveStatus CMP "MOVE_TYPE=11" CPT NEXTSTATE 14
            if tag("Z_axis.MoveStatus"):
                if formula("MOVE_TYPE=11"):
                    set_tag("NEXTSTATE", formula("14"))
            _pc = 196
            continue
        elif _pc == 196:
            # rung 196
            # XIO ALL_EOT_GOOD XIC Z_axis.MoveStatus MAS Z_axis eot_stop Jog Yes 2000 "Units per sec2" No 100 "% of Time"
            if not tag("ALL_EOT_GOOD"):
                if tag("Z_axis.MoveStatus"):
                    MAS(
                        axis="Z_axis",
                        motion_control="eot_stop",
                        stop_type="Jog",
                        change_decel="Yes",
                        decel=2000,
                        decel_units="Units per sec2",
                        change_jerk="No",
                        jerk=100,
                        jerk_units="Units per sec3",
                    )
            _pc = 197
            continue
        elif _pc == 197:
            # rung 197
            # XIC eot_stop.PC CPT ERROR_CODE 5005 CPT NEXTSTATE 11 MOV 0 eot_stop.FLAGS
            if tag("eot_stop.PC"):
                set_tag("ERROR_CODE", formula("5005"))
            if tag("eot_stop.PC"):
                set_tag("NEXTSTATE", formula("11"))
            if tag("eot_stop.PC"):
                set_tag("eot_stop.FLAGS", 0)
            _pc = 198
            continue
        elif _pc == 198:
            # rung 198
            # CMP "STATE=5" CMP "ABS(Z_axis.ActualPosition-Z_POSITION)<0.1" OTE z_move_success
            set_tag(
                "z_move_success",
                bool(
                    (formula("STATE=5"))
                    and (formula("ABS(Z_axis.ActualPosition-Z_POSITION)<0.1"))
                ),
            )
            _pc = 199
            continue
        elif _pc == 199:
            # rung 199
            # XIC z_move_success CPT MOVE_TYPE 0 CPT NEXTSTATE 1 OTU z_move_success MOV 0 z_axis_main_move.FLAGS
            if tag("z_move_success"):
                set_tag("MOVE_TYPE", formula("0"))
            if tag("z_move_success"):
                set_tag("NEXTSTATE", formula("1"))
            if tag("z_move_success"):
                set_tag("z_move_success", False)
            if tag("z_move_success"):
                set_tag("z_axis_main_move.FLAGS", 0)
            _pc = 200
            continue
        elif _pc == 200:
            # rung 200
            # XIO Local:1:I.Pt08.Data OTE MACHINE_SW_STAT[12] OTE LATCH_ACTUATOR_TOP
            set_tag("MACHINE_SW_STAT[12]", bool(not tag("Local:1:I.Pt08.Data")))
            set_tag("LATCH_ACTUATOR_TOP", bool(not tag("Local:1:I.Pt08.Data")))
            _pc = 201
            continue
        elif _pc == 201:
            # rung 201
            # XIO Local:1:I.Pt09.Data OTE MACHINE_SW_STAT[13] OTE LATCH_ACTUATOR_MID
            set_tag("MACHINE_SW_STAT[13]", bool(not tag("Local:1:I.Pt09.Data")))
            set_tag("LATCH_ACTUATOR_MID", bool(not tag("Local:1:I.Pt09.Data")))
            _pc = 202
            continue
        elif _pc == 202:
            # rung 202
            # XIC LATCH_ACTUATOR_TOP XIO LATCH_ACTUATOR_MID CPT ACTUATOR_POS 3 OTE Z_STAGE_UNLATCHED
            if tag("LATCH_ACTUATOR_TOP"):
                if not tag("LATCH_ACTUATOR_MID"):
                    set_tag("ACTUATOR_POS", formula("3"))
            set_tag(
                "Z_STAGE_UNLATCHED",
                bool((tag("LATCH_ACTUATOR_TOP")) and (not tag("LATCH_ACTUATOR_MID"))),
            )
            _pc = 203
            continue
        elif _pc == 203:
            # rung 203
            # XIC LATCH_ACTUATOR_TOP XIC LATCH_ACTUATOR_MID BST TON delay_mid_position 100 0 NXB XIC delay_mid_position.DN CPT ACTUATOR_POS 2 BND OTE Z_OK_TO_ENGAGE
            TON(
                timer_tag="delay_mid_position",
                preset=100,
                accum=0,
                rung_in=(tag("LATCH_ACTUATOR_TOP")) and (tag("LATCH_ACTUATOR_MID")),
            )
            _branch_332 = bool(True)
            if tag("LATCH_ACTUATOR_TOP"):
                if tag("LATCH_ACTUATOR_MID"):
                    if tag("delay_mid_position.DN"):
                        set_tag("ACTUATOR_POS", formula("2"))
            _branch_334 = bool(tag("delay_mid_position.DN"))
            _branch_336 = _branch_332 or _branch_334
            set_tag(
                "Z_OK_TO_ENGAGE",
                bool(
                    (tag("LATCH_ACTUATOR_TOP"))
                    and (tag("LATCH_ACTUATOR_MID"))
                    and (_branch_336)
                ),
            )
            _pc = 204
            continue
        elif _pc == 204:
            # rung 204
            # XIO LATCH_ACTUATOR_TOP XIO LATCH_ACTUATOR_MID XIO Z_STAGE_LATCHED CPT ACTUATOR_POS 0
            if not tag("LATCH_ACTUATOR_TOP"):
                if not tag("LATCH_ACTUATOR_MID"):
                    if not tag("Z_STAGE_LATCHED"):
                        set_tag("ACTUATOR_POS", formula("0"))
            _pc = 205
            continue
        elif _pc == 205:
            # rung 205
            # XIC Z_STAGE_LATCHED BST TON Delay_Z_Latched 1000 0 NXB XIC Delay_Z_Latched.DN CPT ACTUATOR_POS 1 BND
            TON(
                timer_tag="Delay_Z_Latched",
                preset=1000,
                accum=0,
                rung_in=tag("Z_STAGE_LATCHED"),
            )
            _branch_337 = bool(True)
            if tag("Z_STAGE_LATCHED"):
                if tag("Delay_Z_Latched.DN"):
                    set_tag("ACTUATOR_POS", formula("1"))
            _branch_339 = bool(tag("Delay_Z_Latched.DN"))
            _branch_341 = _branch_337 or _branch_339
            _pc = 206
            continue
        elif _pc == 206:
            # rung 206
            # XIC Z_FIXED_LATCHED BST TON Delay_Fixed_Latched 1000 0 NXB XIC Delay_Fixed_Latched.DN OTE Z_SAFE_TO_WITHDRAW BND
            TON(
                timer_tag="Delay_Fixed_Latched",
                preset=1000,
                accum=0,
                rung_in=tag("Z_FIXED_LATCHED"),
            )
            _branch_342 = bool(True)
            set_tag(
                "Z_SAFE_TO_WITHDRAW",
                bool((tag("Z_FIXED_LATCHED")) and (tag("Delay_Fixed_Latched.DN"))),
            )
            _branch_344 = bool(tag("Delay_Fixed_Latched.DN"))
            _branch_346 = _branch_342 or _branch_344
            _pc = 207
            continue
        elif _pc == 207:
            # rung 207
            # XIC Z_STAGE_PRESENT XIC Z_FIXED_PRESENT XIC Z_EXTENDED OTE ENABLE_ACTUATOR
            set_tag(
                "ENABLE_ACTUATOR",
                bool(
                    (tag("Z_STAGE_PRESENT"))
                    and (tag("Z_FIXED_PRESENT"))
                    and (tag("Z_EXTENDED"))
                ),
            )
            _pc = 208
            continue
        elif _pc == 208:
            # rung 208
            # CMP "STATE=6" OTE STATE6_IND
            set_tag("STATE6_IND", bool(formula("STATE=6")))
            _pc = 209
            continue
        elif _pc == 209:
            # rung 209
            # XIC STATE6_IND XIO ENABLE_ACTUATOR XIO LAT_state6_enable_missing_oneshot_storage OTE LAT_state6_enable_missing_oneshot
            set_tag(
                "LAT_state6_enable_missing_oneshot",
                bool(
                    (tag("STATE6_IND"))
                    and (not tag("ENABLE_ACTUATOR"))
                    and (not tag("LAT_state6_enable_missing_oneshot_storage"))
                ),
            )
            _pc = 210
            continue
        elif _pc == 210:
            # rung 210
            # XIC STATE6_IND XIO ENABLE_ACTUATOR OTL LAT_state6_enable_missing_oneshot_storage
            if tag("STATE6_IND"):
                if not tag("ENABLE_ACTUATOR"):
                    set_tag("LAT_state6_enable_missing_oneshot_storage", True)
            _pc = 211
            continue
        elif _pc == 211:
            # rung 211
            # BST XIO STATE6_IND NXB XIC ENABLE_ACTUATOR BND OTU LAT_state6_enable_missing_oneshot_storage
            _branch_347 = bool(not tag("STATE6_IND"))
            _branch_349 = bool(tag("ENABLE_ACTUATOR"))
            _branch_351 = _branch_347 or _branch_349
            if _branch_351:
                set_tag("LAT_state6_enable_missing_oneshot_storage", False)
            _pc = 212
            continue
        elif _pc == 212:
            # rung 212
            # XIC LAT_state6_enable_missing_oneshot CPT ERROR_CODE 6001 CPT NEXTSTATE 10
            if tag("LAT_state6_enable_missing_oneshot"):
                set_tag("ERROR_CODE", formula("6001"))
            if tag("LAT_state6_enable_missing_oneshot"):
                set_tag("NEXTSTATE", formula("10"))
            _pc = 213
            continue
        elif _pc == 213:
            # rung 213
            # XIC STATE6_IND XIC ENABLE_ACTUATOR XIO LAT_state6_enable_present_oneshot_storage OTE LAT_state6_enable_present_oneshot
            set_tag(
                "LAT_state6_enable_present_oneshot",
                bool(
                    (tag("STATE6_IND"))
                    and (tag("ENABLE_ACTUATOR"))
                    and (not tag("LAT_state6_enable_present_oneshot_storage"))
                ),
            )
            _pc = 214
            continue
        elif _pc == 214:
            # rung 214
            # XIC STATE6_IND XIC ENABLE_ACTUATOR OTL LAT_state6_enable_present_oneshot_storage
            if tag("STATE6_IND"):
                if tag("ENABLE_ACTUATOR"):
                    set_tag("LAT_state6_enable_present_oneshot_storage", True)
            _pc = 215
            continue
        elif _pc == 215:
            # rung 215
            # BST XIO STATE6_IND NXB XIO ENABLE_ACTUATOR BND OTU LAT_state6_enable_present_oneshot_storage
            _branch_352 = bool(not tag("STATE6_IND"))
            _branch_354 = bool(not tag("ENABLE_ACTUATOR"))
            _branch_356 = _branch_352 or _branch_354
            if _branch_356:
                set_tag("LAT_state6_enable_present_oneshot_storage", False)
            _pc = 216
            continue
        elif _pc == 216:
            # rung 216
            # XIC LAT_state6_enable_present_oneshot CPT PREV_ACT_POS ACTUATOR_POS
            if tag("LAT_state6_enable_present_oneshot"):
                set_tag("PREV_ACT_POS", formula("ACTUATOR_POS"))
            _pc = 217
            continue
        elif _pc == 217:
            # rung 217
            # XIC LAT_state6_enable_present_oneshot_storage BST CMP "PREV_ACT_POS=1" NXB CMP "PREV_ACT_POS=3" NXB CMP "PREV_ACT_POS=2" NXB CMP "PREV_ACT_POS=0" BND CPT MOVE_TYPE 0 CPT NEXTSTATE 1
            _branch_357 = bool(formula("PREV_ACT_POS=1"))
            _branch_359 = bool(formula("PREV_ACT_POS=3"))
            _branch_361 = bool(formula("PREV_ACT_POS=2"))
            _branch_363 = bool(formula("PREV_ACT_POS=0"))
            _branch_365 = _branch_357 or _branch_359 or _branch_361 or _branch_363
            if tag("LAT_state6_enable_present_oneshot_storage"):
                if _branch_365:
                    set_tag("MOVE_TYPE", formula("0"))
            if tag("LAT_state6_enable_present_oneshot_storage"):
                if _branch_365:
                    set_tag("NEXTSTATE", formula("1"))
            _pc = 218
            continue
        elif _pc == 218:
            # rung 218
            # XIC LAT_state6_enable_present_oneshot_storage XIO Latching_pulse_interval.DN TON Latching_pulse_duration 10 0
            TON(
                timer_tag="Latching_pulse_duration",
                preset=10,
                accum=0,
                rung_in=(tag("LAT_state6_enable_present_oneshot_storage"))
                and (not tag("Latching_pulse_interval.DN")),
            )
            _pc = 219
            continue
        elif _pc == 219:
            # rung 219
            # XIO LAT_latching_pulse_interval_holdoff_storage XIC Latching_pulse_duration.DN TON Latching_pulse_interval 250 0
            TON(
                timer_tag="Latching_pulse_interval",
                preset=250,
                accum=0,
                rung_in=(not tag("LAT_latching_pulse_interval_holdoff_storage"))
                and (tag("Latching_pulse_duration.DN")),
            )
            _pc = 220
            continue
        elif _pc == 220:
            # rung 220
            # CMP "STATE=7" OTE STATE7_IND
            set_tag("STATE7_IND", bool(formula("STATE=7")))
            _pc = 221
            continue
        elif _pc == 221:
            # rung 221
            # XIC STATE7_IND XIO LAT_state7_entry_oneshot_storage OTE LAT_state7_entry_oneshot
            set_tag(
                "LAT_state7_entry_oneshot",
                bool(
                    (tag("STATE7_IND"))
                    and (not tag("LAT_state7_entry_oneshot_storage"))
                ),
            )
            _pc = 222
            continue
        elif _pc == 222:
            # rung 222
            # XIC STATE7_IND OTL LAT_state7_entry_oneshot_storage
            if tag("STATE7_IND"):
                set_tag("LAT_state7_entry_oneshot_storage", True)
            _pc = 223
            continue
        elif _pc == 223:
            # rung 223
            # XIO STATE7_IND OTU LAT_state7_entry_oneshot_storage
            if not tag("STATE7_IND"):
                set_tag("LAT_state7_entry_oneshot_storage", False)
            _pc = 224
            continue
        elif _pc == 224:
            # rung 224
            # XIC LAT_state7_entry_oneshot RES HomeCounter
            if tag("LAT_state7_entry_oneshot"):
                RES("HomeCounter")
            _pc = 225
            continue
        elif _pc == 225:
            # rung 225
            # XIC LAT_state7_entry_oneshot_storage XIO HomeCounter.DN XIO HomeTimer2.TT TON HomeTimer1 500 0
            TON(
                timer_tag="HomeTimer1",
                preset=500,
                accum=0,
                rung_in=(tag("LAT_state7_entry_oneshot_storage"))
                and (not tag("HomeCounter.DN"))
                and (not tag("HomeTimer2.TT")),
            )
            _pc = 226
            continue
        elif _pc == 226:
            # rung 226
            # XIC LAT_state7_entry_oneshot_storage XIO HomeCounter.DN XIO HomeTimer1.TT TON HomeTimer2 500 0
            TON(
                timer_tag="HomeTimer2",
                preset=500,
                accum=0,
                rung_in=(tag("LAT_state7_entry_oneshot_storage"))
                and (not tag("HomeCounter.DN"))
                and (not tag("HomeTimer1.TT")),
            )
            _pc = 227
            continue
        elif _pc == 227:
            # rung 227
            # XIC LAT_state7_entry_oneshot_storage XIO HomeCounter.DN XIC HomeTimer1.TT CTU HomeCounter 100 0
            if tag("LAT_state7_entry_oneshot_storage"):
                if not tag("HomeCounter.DN"):
                    if tag("HomeTimer1.TT"):
                        CTU(
                            tag("HomeCounter"),
                            100,
                            0,
                        )
            _pc = 228
            continue
        elif _pc == 228:
            # rung 228
            # XIC HomeCounter.DN XIC sometag OTE Local:3:O.Pt02.Data
            set_tag(
                "Local:3:O.Pt02.Data",
                bool((tag("HomeCounter.DN")) and (tag("sometag"))),
            )
            _pc = 229
            continue
        elif _pc == 229:
            # rung 229
            # XIC HomeCounter.DN XIO LAT_home_counter_done_oneshot_storage OTE LAT_home_counter_done_oneshot
            set_tag(
                "LAT_home_counter_done_oneshot",
                bool(
                    (tag("HomeCounter.DN"))
                    and (not tag("LAT_home_counter_done_oneshot_storage"))
                ),
            )
            _pc = 230
            continue
        elif _pc == 230:
            # rung 230
            # XIC HomeCounter.DN OTL LAT_home_counter_done_oneshot_storage
            if tag("HomeCounter.DN"):
                set_tag("LAT_home_counter_done_oneshot_storage", True)
            _pc = 231
            continue
        elif _pc == 231:
            # rung 231
            # XIO HomeCounter.DN OTU LAT_home_counter_done_oneshot_storage
            if not tag("HomeCounter.DN"):
                set_tag("LAT_home_counter_done_oneshot_storage", False)
            _pc = 232
            continue
        elif _pc == 232:
            # rung 232
            # XIC LAT_home_counter_done_oneshot XIC Z_STAGE_LATCHED OTL LATCH_ACTUATOR_HOMED
            if tag("LAT_home_counter_done_oneshot"):
                if tag("Z_STAGE_LATCHED"):
                    set_tag("LATCH_ACTUATOR_HOMED", True)
            _pc = 233
            continue
        elif _pc == 233:
            # rung 233
            # XIC LAT_home_counter_done_oneshot XIO Z_STAGE_LATCHED CPT ERROR_CODE 7002 OTL LATCH_ACTUATOR_HOMED
            if tag("LAT_home_counter_done_oneshot"):
                if not tag("Z_STAGE_LATCHED"):
                    set_tag("ERROR_CODE", formula("7002"))
            if tag("LAT_home_counter_done_oneshot"):
                if not tag("Z_STAGE_LATCHED"):
                    set_tag("LATCH_ACTUATOR_HOMED", True)
            _pc = 234
            continue
        elif _pc == 234:
            # rung 234
            # XIC LATCH_ACTUATOR_HOMED OTE MACHINE_SW_STAT[0]
            set_tag("MACHINE_SW_STAT[0]", bool(tag("LATCH_ACTUATOR_HOMED")))
            _pc = 235
            continue
        elif _pc == 235:
            # rung 235
            # XIC LATCH_ACTUATOR_HOMED XIO LAT_latch_actuator_homed_oneshot_storage OTE LAT_latch_actuator_homed_oneshot
            set_tag(
                "LAT_latch_actuator_homed_oneshot",
                bool(
                    (tag("LATCH_ACTUATOR_HOMED"))
                    and (not tag("LAT_latch_actuator_homed_oneshot_storage"))
                ),
            )
            _pc = 236
            continue
        elif _pc == 236:
            # rung 236
            # XIC LATCH_ACTUATOR_HOMED OTL LAT_latch_actuator_homed_oneshot_storage
            if tag("LATCH_ACTUATOR_HOMED"):
                set_tag("LAT_latch_actuator_homed_oneshot_storage", True)
            _pc = 237
            continue
        elif _pc == 237:
            # rung 237
            # XIO LATCH_ACTUATOR_HOMED OTU LAT_latch_actuator_homed_oneshot_storage
            if not tag("LATCH_ACTUATOR_HOMED"):
                set_tag("LAT_latch_actuator_homed_oneshot_storage", False)
            _pc = 238
            continue
        elif _pc == 238:
            # rung 238
            # XIC LAT_latch_actuator_homed_oneshot RES LatchCounter3
            if tag("LAT_latch_actuator_homed_oneshot"):
                RES("LatchCounter3")
            _pc = 239
            continue
        elif _pc == 239:
            # rung 239
            # XIC LAT_latch_actuator_homed_oneshot_storage XIO LatchCounter3.DN XIO LatchTimer6.TT TON LatchTimer5 250 0
            TON(
                timer_tag="LatchTimer5",
                preset=250,
                accum=0,
                rung_in=(tag("LAT_latch_actuator_homed_oneshot_storage"))
                and (not tag("LatchCounter3.DN"))
                and (not tag("LatchTimer6.TT")),
            )
            _pc = 240
            continue
        elif _pc == 240:
            # rung 240
            # XIC LAT_latch_actuator_homed_oneshot_storage XIO LatchCounter3.DN XIO LatchTimer5.TT TON LatchTimer6 250 0
            TON(
                timer_tag="LatchTimer6",
                preset=250,
                accum=0,
                rung_in=(tag("LAT_latch_actuator_homed_oneshot_storage"))
                and (not tag("LatchCounter3.DN"))
                and (not tag("LatchTimer5.TT")),
            )
            _pc = 241
            continue
        elif _pc == 241:
            # rung 241
            # XIC LAT_latch_actuator_homed_oneshot_storage XIO LatchCounter3.DN XIC LatchTimer5.TT CTU LatchCounter3 100 0
            if tag("LAT_latch_actuator_homed_oneshot_storage"):
                if not tag("LatchCounter3.DN"):
                    if tag("LatchTimer5.TT"):
                        CTU(
                            tag("LatchCounter3"),
                            100,
                            0,
                        )
            _pc = 242
            continue
        elif _pc == 242:
            # rung 242
            # XIC LatchCounter3.DN XIO LAT_home_verify_done_oneshot_storage OTE LAT_home_verify_done_oneshot
            set_tag(
                "LAT_home_verify_done_oneshot",
                bool(
                    (tag("LatchCounter3.DN"))
                    and (not tag("LAT_home_verify_done_oneshot_storage"))
                ),
            )
            _pc = 243
            continue
        elif _pc == 243:
            # rung 243
            # XIC LatchCounter3.DN OTL LAT_home_verify_done_oneshot_storage
            if tag("LatchCounter3.DN"):
                set_tag("LAT_home_verify_done_oneshot_storage", True)
            _pc = 244
            continue
        elif _pc == 244:
            # rung 244
            # XIO LatchCounter3.DN OTU LAT_home_verify_done_oneshot_storage
            if not tag("LatchCounter3.DN"):
                set_tag("LAT_home_verify_done_oneshot_storage", False)
            _pc = 245
            continue
        elif _pc == 245:
            # rung 245
            # XIC STATE7_IND XIC LAT_home_verify_done_oneshot CPT ERROR_CODE 7000 OTU HomeSignal CPT MOVE_TYPE 0 CPT NEXTSTATE 1
            if tag("STATE7_IND"):
                if tag("LAT_home_verify_done_oneshot"):
                    set_tag("ERROR_CODE", formula("7000"))
            if tag("STATE7_IND"):
                if tag("LAT_home_verify_done_oneshot"):
                    set_tag("HomeSignal", False)
            if tag("STATE7_IND"):
                if tag("LAT_home_verify_done_oneshot"):
                    set_tag("MOVE_TYPE", formula("0"))
            if tag("STATE7_IND"):
                if tag("LAT_home_verify_done_oneshot"):
                    set_tag("NEXTSTATE", formula("1"))
            _pc = 246
            continue
        elif _pc == 246:
            # rung 246
            # BST CMP "STATE=8" NXB XIC UNLOCK_LATCH_MOTOR_SHAFT BND OTE STATE8_IND
            _branch_366 = bool(formula("STATE=8"))
            _branch_368 = bool(tag("UNLOCK_LATCH_MOTOR_SHAFT"))
            _branch_370 = _branch_366 or _branch_368
            set_tag("STATE8_IND", bool(_branch_370))
            _pc = 247
            continue
        elif _pc == 247:
            # rung 247
            # XIC STATE8_IND XIC sometag OTE Local:3:O.Pt02.Data
            set_tag(
                "Local:3:O.Pt02.Data", bool((tag("STATE8_IND")) and (tag("sometag")))
            )
            _pc = 248
            continue
        elif _pc == 248:
            # rung 248
            # XIC Local:3:O.Pt02.Data CPT ERROR_CODE 8000
            if tag("Local:3:O.Pt02.Data"):
                set_tag("ERROR_CODE", formula("8000"))
            _pc = 249
            continue
        elif _pc == 249:
            # rung 249
            # XIC STATE8_IND XIO LAT_state8_entry_oneshot_storage OTE LAT_state8_entry_oneshot
            set_tag(
                "LAT_state8_entry_oneshot",
                bool(
                    (tag("STATE8_IND"))
                    and (not tag("LAT_state8_entry_oneshot_storage"))
                ),
            )
            _pc = 250
            continue
        elif _pc == 250:
            # rung 250
            # XIC STATE8_IND OTL LAT_state8_entry_oneshot_storage
            if tag("STATE8_IND"):
                set_tag("LAT_state8_entry_oneshot_storage", True)
            _pc = 251
            continue
        elif _pc == 251:
            # rung 251
            # XIO STATE8_IND OTU LAT_state8_entry_oneshot_storage
            if not tag("STATE8_IND"):
                set_tag("LAT_state8_entry_oneshot_storage", False)
            _pc = 252
            continue
        elif _pc == 252:
            # rung 252
            # XIC LAT_state8_entry_oneshot OTU LATCH_ACTUATOR_HOMED
            if tag("LAT_state8_entry_oneshot"):
                set_tag("LATCH_ACTUATOR_HOMED", False)
            _pc = 253
            continue
        elif _pc == 253:
            # rung 253
            # XIC LAT_state8_entry_oneshot RES LatchCounter2
            if tag("LAT_state8_entry_oneshot"):
                RES("LatchCounter2")
            _pc = 254
            continue
        elif _pc == 254:
            # rung 254
            # XIC LAT_state8_entry_oneshot_storage XIO LatchCounter2.DN XIO LatchTimer4.TT TON LatchTimer3 250 0
            TON(
                timer_tag="LatchTimer3",
                preset=250,
                accum=0,
                rung_in=(tag("LAT_state8_entry_oneshot_storage"))
                and (not tag("LatchCounter2.DN"))
                and (not tag("LatchTimer4.TT")),
            )
            _pc = 255
            continue
        elif _pc == 255:
            # rung 255
            # XIC LAT_state8_entry_oneshot_storage XIO LatchCounter2.DN XIO LatchTimer3.TT TON LatchTimer4 250 0
            TON(
                timer_tag="LatchTimer4",
                preset=250,
                accum=0,
                rung_in=(tag("LAT_state8_entry_oneshot_storage"))
                and (not tag("LatchCounter2.DN"))
                and (not tag("LatchTimer3.TT")),
            )
            _pc = 256
            continue
        elif _pc == 256:
            # rung 256
            # XIC LAT_state8_entry_oneshot_storage XIO LatchCounter2.DN XIC LatchTimer3.TT CTU LatchCounter2 100 0
            if tag("LAT_state8_entry_oneshot_storage"):
                if not tag("LatchCounter2.DN"):
                    if tag("LatchTimer3.TT"):
                        CTU(
                            tag("LatchCounter2"),
                            100,
                            0,
                        )
            _pc = 257
            continue
        elif _pc == 257:
            # rung 257
            # XIC STATE8_IND XIC LatchCounter2.DN CMP "MOVE_TYPE=0" CPT NEXTSTATE 1
            if tag("STATE8_IND"):
                if tag("LatchCounter2.DN"):
                    if formula("MOVE_TYPE=0"):
                        set_tag("NEXTSTATE", formula("1"))
            _pc = 258
            continue
        elif _pc == 258:
            # rung 258
            # BST XIC Latching_pulse_duration.TT NXB XIC LatchTimer4.TT NXB XIC HomeTimer2.TT NXB XIC LatchTimer6.TT BND OTE Local:3:O.Pt01.Data OTE latching_signal
            _branch_371 = bool(tag("Latching_pulse_duration.TT"))
            _branch_373 = bool(tag("LatchTimer4.TT"))
            _branch_375 = bool(tag("HomeTimer2.TT"))
            _branch_377 = bool(tag("LatchTimer6.TT"))
            _branch_379 = _branch_371 or _branch_373 or _branch_375 or _branch_377
            set_tag("Local:3:O.Pt01.Data", bool(_branch_379))
            set_tag("latching_signal", bool(_branch_379))
            _pc = 259
            continue
        elif _pc == 259:
            # rung 259
            # XIC Z_STAGE_PRESENT OTU gui_latch_pulse
            if tag("Z_STAGE_PRESENT"):
                set_tag("gui_latch_pulse", False)
            _pc = 260
            continue
        elif _pc == 260:
            # rung 260
            # XIC Z_STAGE_PRESENT XIO Z_FIXED_PRESENT OTE unsafe_to_latch
            set_tag(
                "unsafe_to_latch",
                bool((tag("Z_STAGE_PRESENT")) and (not tag("Z_FIXED_PRESENT"))),
            )
            _pc = 261
            continue
        elif _pc == 261:
            # rung 261
            # XIC gui_latch_pulse XIO unsafe_to_latch OTL Local:3:O.Pt01.Data TON gui_latch_pulse_timer 100 0
            if tag("gui_latch_pulse"):
                if not tag("unsafe_to_latch"):
                    set_tag("Local:3:O.Pt01.Data", True)
            TON(
                timer_tag="gui_latch_pulse_timer",
                preset=100,
                accum=0,
                rung_in=(tag("gui_latch_pulse")) and (not tag("unsafe_to_latch")),
            )
            _pc = 262
            continue
        elif _pc == 262:
            # rung 262
            # XIC gui_latch_pulse_timer.DN RES gui_latch_pulse_timer OTU gui_latch_pulse
            if tag("gui_latch_pulse_timer.DN"):
                RES("gui_latch_pulse_timer")
            if tag("gui_latch_pulse_timer.DN"):
                set_tag("gui_latch_pulse", False)
            _pc = 263
            continue
        elif _pc == 263:
            # rung 263
            # BST CMP "STATE=6" NXB CMP "STATE=7" BND XIO LAT_latching_timeout_monitor_oneshot_storage OTE LAT_latching_timeout_monitor_oneshot
            _branch_380 = bool(formula("STATE=6"))
            _branch_382 = bool(formula("STATE=7"))
            _branch_384 = _branch_380 or _branch_382
            set_tag(
                "LAT_latching_timeout_monitor_oneshot",
                bool(
                    (_branch_384)
                    and (not tag("LAT_latching_timeout_monitor_oneshot_storage"))
                ),
            )
            _pc = 264
            continue
        elif _pc == 264:
            # rung 264
            # BST CMP "STATE=6" NXB CMP "STATE=7" BND OTL LAT_latching_timeout_monitor_oneshot_storage
            _branch_385 = bool(formula("STATE=6"))
            _branch_387 = bool(formula("STATE=7"))
            _branch_389 = _branch_385 or _branch_387
            if _branch_389:
                set_tag("LAT_latching_timeout_monitor_oneshot_storage", True)
            _pc = 265
            continue
        elif _pc == 265:
            # rung 265
            # BST NEQ STATE 6 NXB NEQ STATE 7 BND OTU LAT_latching_timeout_monitor_oneshot_storage
            _branch_390 = bool(tag("STATE") != 6)
            _branch_392 = bool(tag("STATE") != 7)
            _branch_394 = _branch_390 or _branch_392
            if _branch_394:
                set_tag("LAT_latching_timeout_monitor_oneshot_storage", False)
            _pc = 266
            continue
        elif _pc == 266:
            # rung 266
            # XIC LAT_latching_timeout_monitor_oneshot RES LatchingTimeoutCounter
            if tag("LAT_latching_timeout_monitor_oneshot"):
                RES("LatchingTimeoutCounter")
            _pc = 267
            continue
        elif _pc == 267:
            # rung 267
            # XIC LAT_latching_timeout_monitor_oneshot_storage XIO LatchingTimeoutCounter.DN XIO TimeoutTimer2.TT TON TimeoutTimer1 250 0
            TON(
                timer_tag="TimeoutTimer1",
                preset=250,
                accum=0,
                rung_in=(tag("LAT_latching_timeout_monitor_oneshot_storage"))
                and (not tag("LatchingTimeoutCounter.DN"))
                and (not tag("TimeoutTimer2.TT")),
            )
            _pc = 268
            continue
        elif _pc == 268:
            # rung 268
            # XIC LAT_latching_timeout_monitor_oneshot_storage XIO LatchingTimeoutCounter.DN XIO TimeoutTimer1.TT TON TimeoutTimer2 250 0
            TON(
                timer_tag="TimeoutTimer2",
                preset=250,
                accum=0,
                rung_in=(tag("LAT_latching_timeout_monitor_oneshot_storage"))
                and (not tag("LatchingTimeoutCounter.DN"))
                and (not tag("TimeoutTimer1.TT")),
            )
            _pc = 269
            continue
        elif _pc == 269:
            # rung 269
            # XIC LAT_latching_timeout_monitor_oneshot_storage XIO LatchingTimeoutCounter.DN XIC TimeoutTimer1.TT CTU LatchingTimeoutCounter 100 0
            if tag("LAT_latching_timeout_monitor_oneshot_storage"):
                if not tag("LatchingTimeoutCounter.DN"):
                    if tag("TimeoutTimer1.TT"):
                        CTU(
                            tag("LatchingTimeoutCounter"),
                            100,
                            0,
                        )
            _pc = 270
            continue
        elif _pc == 270:
            # rung 270
            # XIC LatchingTimeoutCounter.DN XIO LAT_latching_timeout_done_oneshot_storage OTE LAT_latching_timeout_done_oneshot
            set_tag(
                "LAT_latching_timeout_done_oneshot",
                bool(
                    (tag("LatchingTimeoutCounter.DN"))
                    and (not tag("LAT_latching_timeout_done_oneshot_storage"))
                ),
            )
            _pc = 271
            continue
        elif _pc == 271:
            # rung 271
            # XIC LatchingTimeoutCounter.DN OTL LAT_latching_timeout_done_oneshot_storage
            if tag("LatchingTimeoutCounter.DN"):
                set_tag("LAT_latching_timeout_done_oneshot_storage", True)
            _pc = 272
            continue
        elif _pc == 272:
            # rung 272
            # XIO LatchingTimeoutCounter.DN OTU LAT_latching_timeout_done_oneshot_storage
            if not tag("LatchingTimeoutCounter.DN"):
                set_tag("LAT_latching_timeout_done_oneshot_storage", False)
            _pc = 273
            continue
        elif _pc == 273:
            # rung 273
            # XIC LAT_latching_timeout_done_oneshot CMP "STATE=6" CPT ERROR_CODE 6002 CPT NEXTSTATE 10
            if tag("LAT_latching_timeout_done_oneshot"):
                if formula("STATE=6"):
                    set_tag("ERROR_CODE", formula("6002"))
            if tag("LAT_latching_timeout_done_oneshot"):
                if formula("STATE=6"):
                    set_tag("NEXTSTATE", formula("10"))
            _pc = 274
            continue
        elif _pc == 274:
            # rung 274
            # XIC INIT_DONE CMP "STATE=9" OTE STATE9_IND
            set_tag("STATE9_IND", bool((tag("INIT_DONE")) and (formula("STATE=9"))))
            _pc = 275
            continue
        elif _pc == 275:
            # rung 275
            # XIC STATE9_IND XIO US9_state9_entry_oneshot_storage OTE US9_state9_entry_oneshot
            set_tag(
                "US9_state9_entry_oneshot",
                bool(
                    (tag("STATE9_IND"))
                    and (not tag("US9_state9_entry_oneshot_storage"))
                ),
            )
            _pc = 276
            continue
        elif _pc == 276:
            # rung 276
            # XIC STATE9_IND OTL US9_state9_entry_oneshot_storage
            if tag("STATE9_IND"):
                set_tag("US9_state9_entry_oneshot_storage", True)
            _pc = 277
            continue
        elif _pc == 277:
            # rung 277
            # XIO STATE9_IND OTU US9_state9_entry_oneshot_storage
            if not tag("STATE9_IND"):
                set_tag("US9_state9_entry_oneshot_storage", False)
            _pc = 278
            continue
        elif _pc == 278:
            # rung 278
            # XIC STATE9_IND XIC US9_state9_entry_oneshot MSF X_axis US9_x_axis_unservo_status
            if tag("STATE9_IND"):
                if tag("US9_state9_entry_oneshot"):
                    MSF(
                        axis="X_axis",
                        motion_control="US9_x_axis_unservo_status",
                    )
            _pc = 279
            continue
        elif _pc == 279:
            # rung 279
            # XIC STATE9_IND XIC US9_state9_entry_oneshot MSF Y_axis US9_y_axis_unservo_status
            if tag("STATE9_IND"):
                if tag("US9_state9_entry_oneshot"):
                    MSF(
                        axis="Y_axis",
                        motion_control="US9_y_axis_unservo_status",
                    )
            _pc = 280
            continue
        elif _pc == 280:
            # rung 280
            # XIC STATE9_IND XIC US9_state9_entry_oneshot MSF Z_axis US9_z_axis_unservo_status
            if tag("STATE9_IND"):
                if tag("US9_state9_entry_oneshot"):
                    MSF(
                        axis="Z_axis",
                        motion_control="US9_z_axis_unservo_status",
                    )
            _pc = 281
            continue
        elif _pc == 281:
            # rung 281
            # XIC US9_x_axis_unservo_status.DN XIO US9_x_unservo_done_oneshot_storage OTE US9_x_unservo_done_oneshot
            set_tag(
                "US9_x_unservo_done_oneshot",
                bool(
                    (tag("US9_x_axis_unservo_status.DN"))
                    and (not tag("US9_x_unservo_done_oneshot_storage"))
                ),
            )
            _pc = 282
            continue
        elif _pc == 282:
            # rung 282
            # XIC US9_x_axis_unservo_status.DN OTL US9_x_unservo_done_oneshot_storage
            if tag("US9_x_axis_unservo_status.DN"):
                set_tag("US9_x_unservo_done_oneshot_storage", True)
            _pc = 283
            continue
        elif _pc == 283:
            # rung 283
            # XIO US9_x_axis_unservo_status.DN OTU US9_x_unservo_done_oneshot_storage
            if not tag("US9_x_axis_unservo_status.DN"):
                set_tag("US9_x_unservo_done_oneshot_storage", False)
            _pc = 284
            continue
        elif _pc == 284:
            # rung 284
            # XIC US9_x_unservo_done_oneshot MAFR X_axis US9_x_axis_fault_reset_status
            if tag("US9_x_unservo_done_oneshot"):
                MAFR(
                    axis="X_axis",
                    motion_control="US9_x_axis_fault_reset_status",
                )
            _pc = 285
            continue
        elif _pc == 285:
            # rung 285
            # XIC US9_y_axis_unservo_status.DN XIO US9_y_unservo_done_oneshot_storage OTE US9_y_unservo_done_oneshot
            set_tag(
                "US9_y_unservo_done_oneshot",
                bool(
                    (tag("US9_y_axis_unservo_status.DN"))
                    and (not tag("US9_y_unservo_done_oneshot_storage"))
                ),
            )
            _pc = 286
            continue
        elif _pc == 286:
            # rung 286
            # XIC US9_y_axis_unservo_status.DN OTL US9_y_unservo_done_oneshot_storage
            if tag("US9_y_axis_unservo_status.DN"):
                set_tag("US9_y_unservo_done_oneshot_storage", True)
            _pc = 287
            continue
        elif _pc == 287:
            # rung 287
            # XIO US9_y_axis_unservo_status.DN OTU US9_y_unservo_done_oneshot_storage
            if not tag("US9_y_axis_unservo_status.DN"):
                set_tag("US9_y_unservo_done_oneshot_storage", False)
            _pc = 288
            continue
        elif _pc == 288:
            # rung 288
            # XIC US9_y_unservo_done_oneshot MAFR Y_axis US9_y_axis_fault_reset_status
            if tag("US9_y_unservo_done_oneshot"):
                MAFR(
                    axis="Y_axis",
                    motion_control="US9_y_axis_fault_reset_status",
                )
            _pc = 289
            continue
        elif _pc == 289:
            # rung 289
            # XIC US9_z_axis_unservo_status.DN XIO US9_z_unservo_done_oneshot_storage OTE US9_z_unservo_done_oneshot
            set_tag(
                "US9_z_unservo_done_oneshot",
                bool(
                    (tag("US9_z_axis_unservo_status.DN"))
                    and (not tag("US9_z_unservo_done_oneshot_storage"))
                ),
            )
            _pc = 290
            continue
        elif _pc == 290:
            # rung 290
            # XIC US9_z_axis_unservo_status.DN OTL US9_z_unservo_done_oneshot_storage
            if tag("US9_z_axis_unservo_status.DN"):
                set_tag("US9_z_unservo_done_oneshot_storage", True)
            _pc = 291
            continue
        elif _pc == 291:
            # rung 291
            # XIO US9_z_axis_unservo_status.DN OTU US9_z_unservo_done_oneshot_storage
            if not tag("US9_z_axis_unservo_status.DN"):
                set_tag("US9_z_unservo_done_oneshot_storage", False)
            _pc = 292
            continue
        elif _pc == 292:
            # rung 292
            # XIC US9_z_unservo_done_oneshot MAFR Z_axis US9_z_axis_fault_reset_status
            if tag("US9_z_unservo_done_oneshot"):
                MAFR(
                    axis="Z_axis",
                    motion_control="US9_z_axis_fault_reset_status",
                )
            _pc = 293
            continue
        elif _pc == 293:
            # rung 293
            # XIC STATE9_IND XIC US9_x_axis_fault_reset_status.DN XIC US9_y_axis_fault_reset_status.DN XIC US9_z_axis_fault_reset_status.DN CMP "MOVE_TYPE=0" CPT NEXTSTATE 1
            if tag("STATE9_IND"):
                if tag("US9_x_axis_fault_reset_status.DN"):
                    if tag("US9_y_axis_fault_reset_status.DN"):
                        if tag("US9_z_axis_fault_reset_status.DN"):
                            if formula("MOVE_TYPE=0"):
                                set_tag("NEXTSTATE", formula("1"))
            _pc = 294
            continue
        elif _pc == 294:
            # rung 294
            # XIC INIT_DONE CMP "STATE=10" OTE STATE10_IND
            set_tag("STATE10_IND", bool((tag("INIT_DONE")) and (formula("STATE=10"))))
            _pc = 295
            continue
        elif _pc == 295:
            # rung 295
            # XIC STATE10_IND XIO ERR10_state10_entry_oneshot_storage OTE ERR10_state10_entry_oneshot
            set_tag(
                "ERR10_state10_entry_oneshot",
                bool(
                    (tag("STATE10_IND"))
                    and (not tag("ERR10_state10_entry_oneshot_storage"))
                ),
            )
            _pc = 296
            continue
        elif _pc == 296:
            # rung 296
            # XIC STATE10_IND OTL ERR10_state10_entry_oneshot_storage
            if tag("STATE10_IND"):
                set_tag("ERR10_state10_entry_oneshot_storage", True)
            _pc = 297
            continue
        elif _pc == 297:
            # rung 297
            # XIO STATE10_IND OTU ERR10_state10_entry_oneshot_storage
            if not tag("STATE10_IND"):
                set_tag("ERR10_state10_entry_oneshot_storage", False)
            _pc = 298
            continue
        elif _pc == 298:
            # rung 298
            # XIC ERR10_state10_entry_oneshot MCS X_Y ERR10_xy_group_stop_status All Yes 1000 "Units per sec2" Yes 1000 "Units per sec3"
            if tag("ERR10_state10_entry_oneshot"):
                MCS(
                    coordinate_system="X_Y",
                    motion_control="ERR10_xy_group_stop_status",
                    stop_type="All",
                    change_decel="Yes",
                    decel=1000,
                    decel_units="Units per sec2",
                    change_jerk="Yes",
                    jerk=1000,
                    jerk_units="Units per sec3",
                )
            _pc = 299
            continue
        elif _pc == 299:
            # rung 299
            # XIC ERR10_state10_entry_oneshot MAS Z_axis ERR10_z_axis_stop_status All Yes 1000 "Units per sec2" No 10000 "% of Time"
            if tag("ERR10_state10_entry_oneshot"):
                MAS(
                    axis="Z_axis",
                    motion_control="ERR10_z_axis_stop_status",
                    stop_type="All",
                    change_decel="Yes",
                    decel=1000,
                    decel_units="Units per sec2",
                    change_jerk="No",
                    jerk=10000,
                    jerk_units="Units per sec3",
                )
            _pc = 300
            continue
        elif _pc == 300:
            # rung 300
            # XIC ERR10_xy_group_stop_status.PC XIC ERR10_z_axis_stop_status.PC XIO ERR10_motion_stop_done_oneshot_storage OTE ERR10_motion_stop_done_oneshot
            set_tag(
                "ERR10_motion_stop_done_oneshot",
                bool(
                    (tag("ERR10_xy_group_stop_status.PC"))
                    and (tag("ERR10_z_axis_stop_status.PC"))
                    and (not tag("ERR10_motion_stop_done_oneshot_storage"))
                ),
            )
            _pc = 301
            continue
        elif _pc == 301:
            # rung 301
            # XIC ERR10_xy_group_stop_status.PC XIC ERR10_z_axis_stop_status.PC OTL ERR10_motion_stop_done_oneshot_storage
            if tag("ERR10_xy_group_stop_status.PC"):
                if tag("ERR10_z_axis_stop_status.PC"):
                    set_tag("ERR10_motion_stop_done_oneshot_storage", True)
            _pc = 302
            continue
        elif _pc == 302:
            # rung 302
            # BST XIO ERR10_xy_group_stop_status.PC NXB XIO ERR10_z_axis_stop_status.PC BND OTU ERR10_motion_stop_done_oneshot_storage
            _branch_395 = bool(not tag("ERR10_xy_group_stop_status.PC"))
            _branch_397 = bool(not tag("ERR10_z_axis_stop_status.PC"))
            _branch_399 = _branch_395 or _branch_397
            if _branch_399:
                set_tag("ERR10_motion_stop_done_oneshot_storage", False)
            _pc = 303
            continue
        elif _pc == 303:
            # rung 303
            # XIC ERR10_motion_stop_done_oneshot XIC error_servo_off MSF X_axis ERR10_x_axis_unservo_status
            if tag("ERR10_motion_stop_done_oneshot"):
                if tag("error_servo_off"):
                    MSF(
                        axis="X_axis",
                        motion_control="ERR10_x_axis_unservo_status",
                    )
            _pc = 304
            continue
        elif _pc == 304:
            # rung 304
            # XIC ERR10_motion_stop_done_oneshot XIC error_servo_off MSF Y_axis ERR10_y_axis_unservo_status
            if tag("ERR10_motion_stop_done_oneshot"):
                if tag("error_servo_off"):
                    MSF(
                        axis="Y_axis",
                        motion_control="ERR10_y_axis_unservo_status",
                    )
            _pc = 305
            continue
        elif _pc == 305:
            # rung 305
            # XIC ERR10_motion_stop_done_oneshot XIC error_servo_off MSF Z_axis ERR10_z_axis_unservo_status
            if tag("ERR10_motion_stop_done_oneshot"):
                if tag("error_servo_off"):
                    MSF(
                        axis="Z_axis",
                        motion_control="ERR10_z_axis_unservo_status",
                    )
            _pc = 306
            continue
        elif _pc == 306:
            # rung 306
            # XIC ERR10_x_axis_unservo_status.DN XIC ERR10_y_axis_unservo_status.DN XIC ERR10_z_axis_unservo_status.DN CMP "MOVE_TYPE=0" XIO ERR10_servo_off_done_oneshot_storage OTE ERR10_servo_off_done_oneshot
            set_tag(
                "ERR10_servo_off_done_oneshot",
                bool(
                    (tag("ERR10_x_axis_unservo_status.DN"))
                    and (tag("ERR10_y_axis_unservo_status.DN"))
                    and (tag("ERR10_z_axis_unservo_status.DN"))
                    and (formula("MOVE_TYPE=0"))
                    and (not tag("ERR10_servo_off_done_oneshot_storage"))
                ),
            )
            _pc = 307
            continue
        elif _pc == 307:
            # rung 307
            # XIC ERR10_x_axis_unservo_status.DN XIC ERR10_y_axis_unservo_status.DN XIC ERR10_z_axis_unservo_status.DN CMP "MOVE_TYPE=0" OTL ERR10_servo_off_done_oneshot_storage
            if tag("ERR10_x_axis_unservo_status.DN"):
                if tag("ERR10_y_axis_unservo_status.DN"):
                    if tag("ERR10_z_axis_unservo_status.DN"):
                        if formula("MOVE_TYPE=0"):
                            set_tag("ERR10_servo_off_done_oneshot_storage", True)
            _pc = 308
            continue
        elif _pc == 308:
            # rung 308
            # BST XIO ERR10_x_axis_unservo_status.DN NXB XIO ERR10_y_axis_unservo_status.DN NXB XIO ERR10_z_axis_unservo_status.DN NXB NEQ MOVE_TYPE 0 BND OTU ERR10_servo_off_done_oneshot_storage
            _branch_400 = bool(not tag("ERR10_x_axis_unservo_status.DN"))
            _branch_402 = bool(not tag("ERR10_y_axis_unservo_status.DN"))
            _branch_404 = bool(not tag("ERR10_z_axis_unservo_status.DN"))
            _branch_406 = bool(tag("MOVE_TYPE") != 0)
            _branch_408 = _branch_400 or _branch_402 or _branch_404 or _branch_406
            if _branch_408:
                set_tag("ERR10_servo_off_done_oneshot_storage", False)
            _pc = 309
            continue
        elif _pc == 309:
            # rung 309
            # XIC ERR10_servo_off_done_oneshot MAFR Z_axis ERR10_z_axis_fault_reset_status
            if tag("ERR10_servo_off_done_oneshot"):
                MAFR(
                    axis="Z_axis",
                    motion_control="ERR10_z_axis_fault_reset_status",
                )
            _pc = 310
            continue
        elif _pc == 310:
            # rung 310
            # XIC ERR10_z_axis_fault_reset_status.DN MAFR Y_axis ERR10_y_axis_fault_reset_status
            if tag("ERR10_z_axis_fault_reset_status.DN"):
                MAFR(
                    axis="Y_axis",
                    motion_control="ERR10_y_axis_fault_reset_status",
                )
            _pc = 311
            continue
        elif _pc == 311:
            # rung 311
            # XIC ERR10_y_axis_fault_reset_status.DN MAFR X_axis ERR10_x_axis_fault_reset_status
            if tag("ERR10_y_axis_fault_reset_status.DN"):
                MAFR(
                    axis="X_axis",
                    motion_control="ERR10_x_axis_fault_reset_status",
                )
            _pc = 312
            continue
        elif _pc == 312:
            # rung 312
            # XIC ERR10_z_axis_unservo_status.DN XIC ERR10_y_axis_unservo_status.DN XIC ERR10_x_axis_unservo_status.DN CMP "MOVE_TYPE=0" CMP "STATE=10" CPT ERROR_CODE 0 CPT NEXTSTATE 1
            if tag("ERR10_z_axis_unservo_status.DN"):
                if tag("ERR10_y_axis_unservo_status.DN"):
                    if tag("ERR10_x_axis_unservo_status.DN"):
                        if formula("MOVE_TYPE=0"):
                            if formula("STATE=10"):
                                set_tag("ERROR_CODE", formula("0"))
            if tag("ERR10_z_axis_unservo_status.DN"):
                if tag("ERR10_y_axis_unservo_status.DN"):
                    if tag("ERR10_x_axis_unservo_status.DN"):
                        if formula("MOVE_TYPE=0"):
                            if formula("STATE=10"):
                                set_tag("NEXTSTATE", formula("1"))
            _pc = 313
            continue
        elif _pc == 313:
            # rung 313
            # XIO ALL_EOT_GOOD OTE STATE11_IND
            set_tag("STATE11_IND", bool(not tag("ALL_EOT_GOOD")))
            _pc = 314
            continue
        elif _pc == 314:
            # rung 314
            # XIC STATE11_IND XIO EOT11_state11_entry_oneshot_storage OTE EOT11_state11_entry_oneshot
            set_tag(
                "EOT11_state11_entry_oneshot",
                bool(
                    (tag("STATE11_IND"))
                    and (not tag("EOT11_state11_entry_oneshot_storage"))
                ),
            )
            _pc = 315
            continue
        elif _pc == 315:
            # rung 315
            # XIC STATE11_IND OTL EOT11_state11_entry_oneshot_storage
            if tag("STATE11_IND"):
                set_tag("EOT11_state11_entry_oneshot_storage", True)
            _pc = 316
            continue
        elif _pc == 316:
            # rung 316
            # XIO STATE11_IND OTU EOT11_state11_entry_oneshot_storage
            if not tag("STATE11_IND"):
                set_tag("EOT11_state11_entry_oneshot_storage", False)
            _pc = 317
            continue
        elif _pc == 317:
            # rung 317
            # XIC EOT11_state11_entry_oneshot MCS X_Y EOT11_xy_group_stop_status All Yes 10000 "Units per sec2" Yes 10000 "Units per sec3"
            if tag("EOT11_state11_entry_oneshot"):
                MCS(
                    coordinate_system="X_Y",
                    motion_control="EOT11_xy_group_stop_status",
                    stop_type="All",
                    change_decel="Yes",
                    decel=10000,
                    decel_units="Units per sec2",
                    change_jerk="Yes",
                    jerk=10000,
                    jerk_units="Units per sec3",
                )
            _pc = 318
            continue
        elif _pc == 318:
            # rung 318
            # XIC STATE11_IND XIC EOT11_xy_group_stop_status.DN XIO EOT11_axes_stopped_oneshot_storage OTE EOT11_axes_stopped_oneshot
            set_tag(
                "EOT11_axes_stopped_oneshot",
                bool(
                    (tag("STATE11_IND"))
                    and (tag("EOT11_xy_group_stop_status.DN"))
                    and (not tag("EOT11_axes_stopped_oneshot_storage"))
                ),
            )
            _pc = 319
            continue
        elif _pc == 319:
            # rung 319
            # XIC STATE11_IND XIC EOT11_xy_group_stop_status.DN OTL EOT11_axes_stopped_oneshot_storage
            if tag("STATE11_IND"):
                if tag("EOT11_xy_group_stop_status.DN"):
                    set_tag("EOT11_axes_stopped_oneshot_storage", True)
            _pc = 320
            continue
        elif _pc == 320:
            # rung 320
            # BST XIO STATE11_IND NXB XIO EOT11_xy_group_stop_status.DN BND OTU EOT11_axes_stopped_oneshot_storage
            _branch_409 = bool(not tag("STATE11_IND"))
            _branch_411 = bool(not tag("EOT11_xy_group_stop_status.DN"))
            _branch_413 = _branch_409 or _branch_411
            if _branch_413:
                set_tag("EOT11_axes_stopped_oneshot_storage", False)
            _pc = 321
            continue
        elif _pc == 321:
            # rung 321
            # XIC EOT11_axes_stopped_oneshot MSO X_axis EOT11_x_axis_servo_on_status MSO Y_axis EOT11_y_axis_servo_on_status MSO Z_axis EOT11_z_axis_servo_on_status
            if tag("EOT11_axes_stopped_oneshot"):
                MSO(
                    axis="X_axis",
                    motion_control="EOT11_x_axis_servo_on_status",
                )
            if tag("EOT11_axes_stopped_oneshot"):
                MSO(
                    axis="Y_axis",
                    motion_control="EOT11_y_axis_servo_on_status",
                )
            if tag("EOT11_axes_stopped_oneshot"):
                MSO(
                    axis="Z_axis",
                    motion_control="EOT11_z_axis_servo_on_status",
                )
            _pc = 322
            continue
        elif _pc == 322:
            # rung 322
            # XIC EOT11_state11_entry_oneshot MAS X_axis EOT11_x_axis_abort_status All Yes 1000 "Units per sec2" Yes 1000 "Units per sec3"
            if tag("EOT11_state11_entry_oneshot"):
                MAS(
                    axis="X_axis",
                    motion_control="EOT11_x_axis_abort_status",
                    stop_type="All",
                    change_decel="Yes",
                    decel=1000,
                    decel_units="Units per sec2",
                    change_jerk="Yes",
                    jerk=1000,
                    jerk_units="Units per sec3",
                )
            _pc = 323
            continue
        elif _pc == 323:
            # rung 323
            # XIC EOT11_state11_entry_oneshot MAS Y_axis EOT11_y_axis_abort_status All Yes 1000 "Units per sec2" Yes 1000 "Units per sec3"
            if tag("EOT11_state11_entry_oneshot"):
                MAS(
                    axis="Y_axis",
                    motion_control="EOT11_y_axis_abort_status",
                    stop_type="All",
                    change_decel="Yes",
                    decel=1000,
                    decel_units="Units per sec2",
                    change_jerk="Yes",
                    jerk=1000,
                    jerk_units="Units per sec3",
                )
            _pc = 324
            continue
        elif _pc == 324:
            # rung 324
            # XIC EOT11_state11_entry_oneshot MAS Z_axis EOT11_z_axis_abort_status All Yes 1000 "Units per sec2" Yes 1000 "Units per sec3"
            if tag("EOT11_state11_entry_oneshot"):
                MAS(
                    axis="Z_axis",
                    motion_control="EOT11_z_axis_abort_status",
                    stop_type="All",
                    change_decel="Yes",
                    decel=1000,
                    decel_units="Units per sec2",
                    change_jerk="Yes",
                    jerk=1000,
                    jerk_units="Units per sec3",
                )
            _pc = 325
            continue
        elif _pc == 325:
            # rung 325
            # XIC STATE11_IND OTE AbortQueue
            set_tag("AbortQueue", bool(tag("STATE11_IND")))
            _pc = 326
            continue
        elif _pc == 326:
            # rung 326
            # XIC STATE11_IND CPT MOVE_TYPE 0
            if tag("STATE11_IND"):
                set_tag("MOVE_TYPE", formula("0"))
            _pc = 327
            continue
        elif _pc == 327:
            # rung 327
            # XIC STATE11_IND XIC EOT11_xy_group_stop_status.DN XIC EOT11_x_axis_servo_on_status.DN XIC EOT11_y_axis_servo_on_status.DN XIC EOT11_z_axis_servo_on_status.DN XIO PLUS_X_EOT XIC MINUS_X_EOT XIO EOT11_minus_x_recovery_move_status.IP XIO EOT11_minus_x_recovery_oneshot_storage OTE EOT11_minus_x_recovery_oneshot
            set_tag(
                "EOT11_minus_x_recovery_oneshot",
                bool(
                    (tag("STATE11_IND"))
                    and (tag("EOT11_xy_group_stop_status.DN"))
                    and (tag("EOT11_x_axis_servo_on_status.DN"))
                    and (tag("EOT11_y_axis_servo_on_status.DN"))
                    and (tag("EOT11_z_axis_servo_on_status.DN"))
                    and (not tag("PLUS_X_EOT"))
                    and (tag("MINUS_X_EOT"))
                    and (not tag("EOT11_minus_x_recovery_move_status.IP"))
                    and (not tag("EOT11_minus_x_recovery_oneshot_storage"))
                ),
            )
            _pc = 328
            continue
        elif _pc == 328:
            # rung 328
            # XIC STATE11_IND XIC EOT11_xy_group_stop_status.DN XIC EOT11_x_axis_servo_on_status.DN XIC EOT11_y_axis_servo_on_status.DN XIC EOT11_z_axis_servo_on_status.DN XIO PLUS_X_EOT XIC MINUS_X_EOT XIO EOT11_minus_x_recovery_move_status.IP OTL EOT11_minus_x_recovery_oneshot_storage
            if tag("STATE11_IND"):
                if tag("EOT11_xy_group_stop_status.DN"):
                    if tag("EOT11_x_axis_servo_on_status.DN"):
                        if tag("EOT11_y_axis_servo_on_status.DN"):
                            if tag("EOT11_z_axis_servo_on_status.DN"):
                                if not tag("PLUS_X_EOT"):
                                    if tag("MINUS_X_EOT"):
                                        if not tag(
                                            "EOT11_minus_x_recovery_move_status.IP"
                                        ):
                                            set_tag(
                                                "EOT11_minus_x_recovery_oneshot_storage",
                                                True,
                                            )
            _pc = 329
            continue
        elif _pc == 329:
            # rung 329
            # BST XIO STATE11_IND NXB XIO EOT11_xy_group_stop_status.DN NXB XIO EOT11_x_axis_servo_on_status.DN NXB XIO EOT11_y_axis_servo_on_status.DN NXB XIO EOT11_z_axis_servo_on_status.DN NXB XIC PLUS_X_EOT NXB XIO MINUS_X_EOT NXB XIC EOT11_minus_x_recovery_move_status.IP BND OTU EOT11_minus_x_recovery_oneshot_storage
            _branch_414 = bool(not tag("STATE11_IND"))
            _branch_416 = bool(not tag("EOT11_xy_group_stop_status.DN"))
            _branch_418 = bool(not tag("EOT11_x_axis_servo_on_status.DN"))
            _branch_420 = bool(not tag("EOT11_y_axis_servo_on_status.DN"))
            _branch_422 = bool(not tag("EOT11_z_axis_servo_on_status.DN"))
            _branch_424 = bool(tag("PLUS_X_EOT"))
            _branch_426 = bool(not tag("MINUS_X_EOT"))
            _branch_428 = bool(tag("EOT11_minus_x_recovery_move_status.IP"))
            _branch_430 = (
                _branch_414
                or _branch_416
                or _branch_418
                or _branch_420
                or _branch_422
                or _branch_424
                or _branch_426
                or _branch_428
            )
            if _branch_430:
                set_tag("EOT11_minus_x_recovery_oneshot_storage", False)
            _pc = 330
            continue
        elif _pc == 330:
            # rung 330
            # XIC EOT11_minus_x_recovery_oneshot MAM X_axis EOT11_minus_x_recovery_move_status 1 -1 25 "Units per sec" 100 "Units per sec2" 100 "Units per sec2" S-Curve 100 100 "% of Time" Disabled 0 0 0 0 0
            MAM(
                axis="X_axis",
                motion_control="EOT11_minus_x_recovery_move_status",
                move_type=1,
                target=-1,
                speed=25,
                speed_units="Units per sec",
                accel=100,
                accel_units="Units per sec2",
                decel=100,
                decel_units="Units per sec2",
                profile="S-Curve",
                accel_jerk=100,
                decel_jerk=100,
                jerk_units="Units per sec3",
                merge="Disabled",
                merge_speed=0,
                lock_position=0,
                lock_direction="None",
                event_distance=0,
                calculated_data=0,
                rung_in=tag("EOT11_minus_x_recovery_oneshot"),
            )
            _pc = 331
            continue
        elif _pc == 331:
            # rung 331
            # XIC STATE11_IND XIC EOT11_xy_group_stop_status.DN XIC EOT11_x_axis_servo_on_status.DN XIC EOT11_y_axis_servo_on_status.DN XIC EOT11_z_axis_servo_on_status.DN XIO MINUS_X_EOT XIC PLUS_X_EOT XIO EOT11_plus_x_recovery_move_status.IP XIO EOT11_plus_x_recovery_oneshot_storage OTE EOT11_plus_x_recovery_oneshot
            set_tag(
                "EOT11_plus_x_recovery_oneshot",
                bool(
                    (tag("STATE11_IND"))
                    and (tag("EOT11_xy_group_stop_status.DN"))
                    and (tag("EOT11_x_axis_servo_on_status.DN"))
                    and (tag("EOT11_y_axis_servo_on_status.DN"))
                    and (tag("EOT11_z_axis_servo_on_status.DN"))
                    and (not tag("MINUS_X_EOT"))
                    and (tag("PLUS_X_EOT"))
                    and (not tag("EOT11_plus_x_recovery_move_status.IP"))
                    and (not tag("EOT11_plus_x_recovery_oneshot_storage"))
                ),
            )
            _pc = 332
            continue
        elif _pc == 332:
            # rung 332
            # XIC STATE11_IND XIC EOT11_xy_group_stop_status.DN XIC EOT11_x_axis_servo_on_status.DN XIC EOT11_y_axis_servo_on_status.DN XIC EOT11_z_axis_servo_on_status.DN XIO MINUS_X_EOT XIC PLUS_X_EOT XIO EOT11_plus_x_recovery_move_status.IP OTL EOT11_plus_x_recovery_oneshot_storage
            if tag("STATE11_IND"):
                if tag("EOT11_xy_group_stop_status.DN"):
                    if tag("EOT11_x_axis_servo_on_status.DN"):
                        if tag("EOT11_y_axis_servo_on_status.DN"):
                            if tag("EOT11_z_axis_servo_on_status.DN"):
                                if not tag("MINUS_X_EOT"):
                                    if tag("PLUS_X_EOT"):
                                        if not tag(
                                            "EOT11_plus_x_recovery_move_status.IP"
                                        ):
                                            set_tag(
                                                "EOT11_plus_x_recovery_oneshot_storage",
                                                True,
                                            )
            _pc = 333
            continue
        elif _pc == 333:
            # rung 333
            # BST XIO STATE11_IND NXB XIO EOT11_xy_group_stop_status.DN NXB XIO EOT11_x_axis_servo_on_status.DN NXB XIO EOT11_y_axis_servo_on_status.DN NXB XIO EOT11_z_axis_servo_on_status.DN NXB XIC MINUS_X_EOT NXB XIO PLUS_X_EOT NXB XIC EOT11_plus_x_recovery_move_status.IP BND OTU EOT11_plus_x_recovery_oneshot_storage
            _branch_431 = bool(not tag("STATE11_IND"))
            _branch_433 = bool(not tag("EOT11_xy_group_stop_status.DN"))
            _branch_435 = bool(not tag("EOT11_x_axis_servo_on_status.DN"))
            _branch_437 = bool(not tag("EOT11_y_axis_servo_on_status.DN"))
            _branch_439 = bool(not tag("EOT11_z_axis_servo_on_status.DN"))
            _branch_441 = bool(tag("MINUS_X_EOT"))
            _branch_443 = bool(not tag("PLUS_X_EOT"))
            _branch_445 = bool(tag("EOT11_plus_x_recovery_move_status.IP"))
            _branch_447 = (
                _branch_431
                or _branch_433
                or _branch_435
                or _branch_437
                or _branch_439
                or _branch_441
                or _branch_443
                or _branch_445
            )
            if _branch_447:
                set_tag("EOT11_plus_x_recovery_oneshot_storage", False)
            _pc = 334
            continue
        elif _pc == 334:
            # rung 334
            # XIC EOT11_plus_x_recovery_oneshot MAM X_axis EOT11_plus_x_recovery_move_status 1 10 25 "Units per sec" 100 "Units per sec2" 100 "Units per sec2" S-Curve 100 100 "% of Time" Disabled 0 0 0 0 0
            MAM(
                axis="X_axis",
                motion_control="EOT11_plus_x_recovery_move_status",
                move_type=1,
                target=10,
                speed=25,
                speed_units="Units per sec",
                accel=100,
                accel_units="Units per sec2",
                decel=100,
                decel_units="Units per sec2",
                profile="S-Curve",
                accel_jerk=100,
                decel_jerk=100,
                jerk_units="Units per sec3",
                merge="Disabled",
                merge_speed=0,
                lock_position=0,
                lock_direction="None",
                event_distance=0,
                calculated_data=0,
                rung_in=tag("EOT11_plus_x_recovery_oneshot"),
            )
            _pc = 335
            continue
        elif _pc == 335:
            # rung 335
            # XIC STATE11_IND XIC EOT11_xy_group_stop_status.DN XIC EOT11_x_axis_servo_on_status.DN XIC EOT11_y_axis_servo_on_status.DN XIC EOT11_z_axis_servo_on_status.DN XIO PLUS_Y_EOT XIC MINUS_Y_EOT XIO EOT11_minus_y_recovery_move_status.IP XIO EOT11_minus_y_recovery_oneshot_storage OTE EOT11_minus_y_recovery_oneshot
            set_tag(
                "EOT11_minus_y_recovery_oneshot",
                bool(
                    (tag("STATE11_IND"))
                    and (tag("EOT11_xy_group_stop_status.DN"))
                    and (tag("EOT11_x_axis_servo_on_status.DN"))
                    and (tag("EOT11_y_axis_servo_on_status.DN"))
                    and (tag("EOT11_z_axis_servo_on_status.DN"))
                    and (not tag("PLUS_Y_EOT"))
                    and (tag("MINUS_Y_EOT"))
                    and (not tag("EOT11_minus_y_recovery_move_status.IP"))
                    and (not tag("EOT11_minus_y_recovery_oneshot_storage"))
                ),
            )
            _pc = 336
            continue
        elif _pc == 336:
            # rung 336
            # XIC STATE11_IND XIC EOT11_xy_group_stop_status.DN XIC EOT11_x_axis_servo_on_status.DN XIC EOT11_y_axis_servo_on_status.DN XIC EOT11_z_axis_servo_on_status.DN XIO PLUS_Y_EOT XIC MINUS_Y_EOT XIO EOT11_minus_y_recovery_move_status.IP OTL EOT11_minus_y_recovery_oneshot_storage
            if tag("STATE11_IND"):
                if tag("EOT11_xy_group_stop_status.DN"):
                    if tag("EOT11_x_axis_servo_on_status.DN"):
                        if tag("EOT11_y_axis_servo_on_status.DN"):
                            if tag("EOT11_z_axis_servo_on_status.DN"):
                                if not tag("PLUS_Y_EOT"):
                                    if tag("MINUS_Y_EOT"):
                                        if not tag(
                                            "EOT11_minus_y_recovery_move_status.IP"
                                        ):
                                            set_tag(
                                                "EOT11_minus_y_recovery_oneshot_storage",
                                                True,
                                            )
            _pc = 337
            continue
        elif _pc == 337:
            # rung 337
            # BST XIO STATE11_IND NXB XIO EOT11_xy_group_stop_status.DN NXB XIO EOT11_x_axis_servo_on_status.DN NXB XIO EOT11_y_axis_servo_on_status.DN NXB XIO EOT11_z_axis_servo_on_status.DN NXB XIC PLUS_Y_EOT NXB XIO MINUS_Y_EOT NXB XIC EOT11_minus_y_recovery_move_status.IP BND OTU EOT11_minus_y_recovery_oneshot_storage
            _branch_448 = bool(not tag("STATE11_IND"))
            _branch_450 = bool(not tag("EOT11_xy_group_stop_status.DN"))
            _branch_452 = bool(not tag("EOT11_x_axis_servo_on_status.DN"))
            _branch_454 = bool(not tag("EOT11_y_axis_servo_on_status.DN"))
            _branch_456 = bool(not tag("EOT11_z_axis_servo_on_status.DN"))
            _branch_458 = bool(tag("PLUS_Y_EOT"))
            _branch_460 = bool(not tag("MINUS_Y_EOT"))
            _branch_462 = bool(tag("EOT11_minus_y_recovery_move_status.IP"))
            _branch_464 = (
                _branch_448
                or _branch_450
                or _branch_452
                or _branch_454
                or _branch_456
                or _branch_458
                or _branch_460
                or _branch_462
            )
            if _branch_464:
                set_tag("EOT11_minus_y_recovery_oneshot_storage", False)
            _pc = 338
            continue
        elif _pc == 338:
            # rung 338
            # XIC EOT11_minus_y_recovery_oneshot MAM Y_axis EOT11_minus_y_recovery_move_status 1 -1 25 "Units per sec" 100 "Units per sec2" 100 "Units per sec2" S-Curve 100 100 "% of Time" Disabled 0 0 0 0 0
            MAM(
                axis="Y_axis",
                motion_control="EOT11_minus_y_recovery_move_status",
                move_type=1,
                target=-1,
                speed=25,
                speed_units="Units per sec",
                accel=100,
                accel_units="Units per sec2",
                decel=100,
                decel_units="Units per sec2",
                profile="S-Curve",
                accel_jerk=100,
                decel_jerk=100,
                jerk_units="Units per sec3",
                merge="Disabled",
                merge_speed=0,
                lock_position=0,
                lock_direction="None",
                event_distance=0,
                calculated_data=0,
                rung_in=tag("EOT11_minus_y_recovery_oneshot"),
            )
            _pc = 339
            continue
        elif _pc == 339:
            # rung 339
            # XIC STATE11_IND XIC EOT11_xy_group_stop_status.DN XIC EOT11_x_axis_servo_on_status.DN XIC EOT11_y_axis_servo_on_status.DN XIC EOT11_z_axis_servo_on_status.DN XIO MINUS_Y_EOT XIC PLUS_Y_EOT XIO EOT11_plus_y_recovery_move_status.IP XIO EOT11_plus_y_recovery_oneshot_storage OTE EOT11_plus_y_recovery_oneshot
            set_tag(
                "EOT11_plus_y_recovery_oneshot",
                bool(
                    (tag("STATE11_IND"))
                    and (tag("EOT11_xy_group_stop_status.DN"))
                    and (tag("EOT11_x_axis_servo_on_status.DN"))
                    and (tag("EOT11_y_axis_servo_on_status.DN"))
                    and (tag("EOT11_z_axis_servo_on_status.DN"))
                    and (not tag("MINUS_Y_EOT"))
                    and (tag("PLUS_Y_EOT"))
                    and (not tag("EOT11_plus_y_recovery_move_status.IP"))
                    and (not tag("EOT11_plus_y_recovery_oneshot_storage"))
                ),
            )
            _pc = 340
            continue
        elif _pc == 340:
            # rung 340
            # XIC STATE11_IND XIC EOT11_xy_group_stop_status.DN XIC EOT11_x_axis_servo_on_status.DN XIC EOT11_y_axis_servo_on_status.DN XIC EOT11_z_axis_servo_on_status.DN XIO MINUS_Y_EOT XIC PLUS_Y_EOT XIO EOT11_plus_y_recovery_move_status.IP OTL EOT11_plus_y_recovery_oneshot_storage
            if tag("STATE11_IND"):
                if tag("EOT11_xy_group_stop_status.DN"):
                    if tag("EOT11_x_axis_servo_on_status.DN"):
                        if tag("EOT11_y_axis_servo_on_status.DN"):
                            if tag("EOT11_z_axis_servo_on_status.DN"):
                                if not tag("MINUS_Y_EOT"):
                                    if tag("PLUS_Y_EOT"):
                                        if not tag(
                                            "EOT11_plus_y_recovery_move_status.IP"
                                        ):
                                            set_tag(
                                                "EOT11_plus_y_recovery_oneshot_storage",
                                                True,
                                            )
            _pc = 341
            continue
        elif _pc == 341:
            # rung 341
            # BST XIO STATE11_IND NXB XIO EOT11_xy_group_stop_status.DN NXB XIO EOT11_x_axis_servo_on_status.DN NXB XIO EOT11_y_axis_servo_on_status.DN NXB XIO EOT11_z_axis_servo_on_status.DN NXB XIC MINUS_Y_EOT NXB XIO PLUS_Y_EOT NXB XIC EOT11_plus_y_recovery_move_status.IP BND OTU EOT11_plus_y_recovery_oneshot_storage
            _branch_465 = bool(not tag("STATE11_IND"))
            _branch_467 = bool(not tag("EOT11_xy_group_stop_status.DN"))
            _branch_469 = bool(not tag("EOT11_x_axis_servo_on_status.DN"))
            _branch_471 = bool(not tag("EOT11_y_axis_servo_on_status.DN"))
            _branch_473 = bool(not tag("EOT11_z_axis_servo_on_status.DN"))
            _branch_475 = bool(tag("MINUS_Y_EOT"))
            _branch_477 = bool(not tag("PLUS_Y_EOT"))
            _branch_479 = bool(tag("EOT11_plus_y_recovery_move_status.IP"))
            _branch_481 = (
                _branch_465
                or _branch_467
                or _branch_469
                or _branch_471
                or _branch_473
                or _branch_475
                or _branch_477
                or _branch_479
            )
            if _branch_481:
                set_tag("EOT11_plus_y_recovery_oneshot_storage", False)
            _pc = 342
            continue
        elif _pc == 342:
            # rung 342
            # XIC EOT11_plus_y_recovery_oneshot MAM Y_axis EOT11_plus_y_recovery_move_status 1 1 25 "Units per sec" 100 "Units per sec2" 100 "Units per sec2" S-Curve 100 100 "% of Time" Disabled 0 0 0 0 0
            MAM(
                axis="Y_axis",
                motion_control="EOT11_plus_y_recovery_move_status",
                move_type=1,
                target=1,
                speed=25,
                speed_units="Units per sec",
                accel=100,
                accel_units="Units per sec2",
                decel=100,
                decel_units="Units per sec2",
                profile="S-Curve",
                accel_jerk=100,
                decel_jerk=100,
                jerk_units="Units per sec3",
                merge="Disabled",
                merge_speed=0,
                lock_position=0,
                lock_direction="None",
                event_distance=0,
                calculated_data=0,
                rung_in=tag("EOT11_plus_y_recovery_oneshot"),
            )
            _pc = 343
            continue
        elif _pc == 343:
            # rung 343
            # XIC STATE11_IND XIC EOT11_xy_group_stop_status.DN XIC EOT11_x_axis_servo_on_status.DN XIC EOT11_y_axis_servo_on_status.DN XIC EOT11_z_axis_servo_on_status.DN XIO Z_EOT XIO EOT11_z_clearance_move_status.IP XIO EOT11_z_clearance_move_oneshot_storage OTE EOT11_z_clearance_move_oneshot
            set_tag(
                "EOT11_z_clearance_move_oneshot",
                bool(
                    (tag("STATE11_IND"))
                    and (tag("EOT11_xy_group_stop_status.DN"))
                    and (tag("EOT11_x_axis_servo_on_status.DN"))
                    and (tag("EOT11_y_axis_servo_on_status.DN"))
                    and (tag("EOT11_z_axis_servo_on_status.DN"))
                    and (not tag("Z_EOT"))
                    and (not tag("EOT11_z_clearance_move_status.IP"))
                    and (not tag("EOT11_z_clearance_move_oneshot_storage"))
                ),
            )
            _pc = 344
            continue
        elif _pc == 344:
            # rung 344
            # XIC STATE11_IND XIC EOT11_xy_group_stop_status.DN XIC EOT11_x_axis_servo_on_status.DN XIC EOT11_y_axis_servo_on_status.DN XIC EOT11_z_axis_servo_on_status.DN XIO Z_EOT XIO EOT11_z_clearance_move_status.IP OTL EOT11_z_clearance_move_oneshot_storage
            if tag("STATE11_IND"):
                if tag("EOT11_xy_group_stop_status.DN"):
                    if tag("EOT11_x_axis_servo_on_status.DN"):
                        if tag("EOT11_y_axis_servo_on_status.DN"):
                            if tag("EOT11_z_axis_servo_on_status.DN"):
                                if not tag("Z_EOT"):
                                    if not tag("EOT11_z_clearance_move_status.IP"):
                                        set_tag(
                                            "EOT11_z_clearance_move_oneshot_storage",
                                            True,
                                        )
            _pc = 345
            continue
        elif _pc == 345:
            # rung 345
            # BST XIO STATE11_IND NXB XIO EOT11_xy_group_stop_status.DN NXB XIO EOT11_x_axis_servo_on_status.DN NXB XIO EOT11_y_axis_servo_on_status.DN NXB XIO EOT11_z_axis_servo_on_status.DN NXB XIC Z_EOT NXB XIC EOT11_z_clearance_move_status.IP BND OTU EOT11_z_clearance_move_oneshot_storage
            _branch_482 = bool(not tag("STATE11_IND"))
            _branch_484 = bool(not tag("EOT11_xy_group_stop_status.DN"))
            _branch_486 = bool(not tag("EOT11_x_axis_servo_on_status.DN"))
            _branch_488 = bool(not tag("EOT11_y_axis_servo_on_status.DN"))
            _branch_490 = bool(not tag("EOT11_z_axis_servo_on_status.DN"))
            _branch_492 = bool(tag("Z_EOT"))
            _branch_494 = bool(tag("EOT11_z_clearance_move_status.IP"))
            _branch_496 = (
                _branch_482
                or _branch_484
                or _branch_486
                or _branch_488
                or _branch_490
                or _branch_492
                or _branch_494
            )
            if _branch_496:
                set_tag("EOT11_z_clearance_move_oneshot_storage", False)
            _pc = 346
            continue
        elif _pc == 346:
            # rung 346
            # XIC EOT11_z_clearance_move_oneshot MAM Z_axis EOT11_z_clearance_move_status 0 0 25 "Units per sec" 100 "Units per sec2" 100 "Units per sec2" S-Curve 100 100 "% of Time" Disabled 0 0 0 0 0
            MAM(
                axis="Z_axis",
                motion_control="EOT11_z_clearance_move_status",
                move_type=0,
                target=0,
                speed=25,
                speed_units="Units per sec",
                accel=100,
                accel_units="Units per sec2",
                decel=100,
                decel_units="Units per sec2",
                profile="S-Curve",
                accel_jerk=100,
                decel_jerk=100,
                jerk_units="Units per sec3",
                merge="Disabled",
                merge_speed=0,
                lock_position=0,
                lock_direction="None",
                event_distance=0,
                calculated_data=0,
                rung_in=tag("EOT11_z_clearance_move_oneshot"),
            )
            _pc = 347
            continue
        elif _pc == 347:
            # rung 347
            # XIC ALL_EOT_GOOD XIO EOT11_z_clearance_move_status.IP XIO EOT11_all_eot_good_oneshot_storage OTE EOT11_all_eot_good_oneshot
            set_tag(
                "EOT11_all_eot_good_oneshot",
                bool(
                    (tag("ALL_EOT_GOOD"))
                    and (not tag("EOT11_z_clearance_move_status.IP"))
                    and (not tag("EOT11_all_eot_good_oneshot_storage"))
                ),
            )
            _pc = 348
            continue
        elif _pc == 348:
            # rung 348
            # XIC ALL_EOT_GOOD XIO EOT11_z_clearance_move_status.IP OTL EOT11_all_eot_good_oneshot_storage
            if tag("ALL_EOT_GOOD"):
                if not tag("EOT11_z_clearance_move_status.IP"):
                    set_tag("EOT11_all_eot_good_oneshot_storage", True)
            _pc = 349
            continue
        elif _pc == 349:
            # rung 349
            # BST XIO ALL_EOT_GOOD NXB XIC EOT11_z_clearance_move_status.IP BND OTU EOT11_all_eot_good_oneshot_storage
            _branch_497 = bool(not tag("ALL_EOT_GOOD"))
            _branch_499 = bool(tag("EOT11_z_clearance_move_status.IP"))
            _branch_501 = _branch_497 or _branch_499
            if _branch_501:
                set_tag("EOT11_all_eot_good_oneshot_storage", False)
            _pc = 350
            continue
        elif _pc == 350:
            # rung 350
            # XIC EOT11_all_eot_good_oneshot MAS X_axis EOT11_x_axis_recovery_stop_a_status Move No 1000 "Units per sec2" Yes 1000 "Units per sec3"
            if tag("EOT11_all_eot_good_oneshot"):
                MAS(
                    axis="X_axis",
                    motion_control="EOT11_x_axis_recovery_stop_a_status",
                    stop_type="Move",
                    change_decel="No",
                    decel=1000,
                    decel_units="Units per sec2",
                    change_jerk="Yes",
                    jerk=1000,
                    jerk_units="Units per sec3",
                )
            _pc = 351
            continue
        elif _pc == 351:
            # rung 351
            # XIC EOT11_all_eot_good_oneshot MAS X_axis EOT11_x_axis_recovery_stop_b_status Move No 1000 "Units per sec2" Yes 1000 "Units per sec3"
            if tag("EOT11_all_eot_good_oneshot"):
                MAS(
                    axis="X_axis",
                    motion_control="EOT11_x_axis_recovery_stop_b_status",
                    stop_type="Move",
                    change_decel="No",
                    decel=1000,
                    decel_units="Units per sec2",
                    change_jerk="Yes",
                    jerk=1000,
                    jerk_units="Units per sec3",
                )
            _pc = 352
            continue
        elif _pc == 352:
            # rung 352
            # XIC EOT11_all_eot_good_oneshot MAS Y_axis EOT11_y_axis_recovery_stop_a_status Move No 1000 "Units per sec2" Yes 1000 "Units per sec3"
            if tag("EOT11_all_eot_good_oneshot"):
                MAS(
                    axis="Y_axis",
                    motion_control="EOT11_y_axis_recovery_stop_a_status",
                    stop_type="Move",
                    change_decel="No",
                    decel=1000,
                    decel_units="Units per sec2",
                    change_jerk="Yes",
                    jerk=1000,
                    jerk_units="Units per sec3",
                )
            _pc = 353
            continue
        elif _pc == 353:
            # rung 353
            # XIC EOT11_all_eot_good_oneshot MAS Y_axis EOT11_y_axis_recovery_stop_b_status Move No 1000 "Units per sec2" Yes 1000 "Units per sec3"
            if tag("EOT11_all_eot_good_oneshot"):
                MAS(
                    axis="Y_axis",
                    motion_control="EOT11_y_axis_recovery_stop_b_status",
                    stop_type="Move",
                    change_decel="No",
                    decel=1000,
                    decel_units="Units per sec2",
                    change_jerk="Yes",
                    jerk=1000,
                    jerk_units="Units per sec3",
                )
            _pc = 354
            continue
        elif _pc == 354:
            # rung 354
            # XIC EOT11_all_eot_good_oneshot MAS Z_axis EOT11_z_axis_recovery_stop_status Move No 1000 "Units per sec2" Yes 1000 "Units per sec3"
            if tag("EOT11_all_eot_good_oneshot"):
                MAS(
                    axis="Z_axis",
                    motion_control="EOT11_z_axis_recovery_stop_status",
                    stop_type="Move",
                    change_decel="No",
                    decel=1000,
                    decel_units="Units per sec2",
                    change_jerk="Yes",
                    jerk=1000,
                    jerk_units="Units per sec3",
                )
            _pc = 355
            continue
        elif _pc == 355:
            # rung 355
            # XIC EOT11_all_eot_good_oneshot CPT ERROR_CODE 0 CPT NEXTSTATE 1
            if tag("EOT11_all_eot_good_oneshot"):
                set_tag("ERROR_CODE", formula("0"))
            if tag("EOT11_all_eot_good_oneshot"):
                set_tag("NEXTSTATE", formula("1"))
            _pc = 356
            continue
        elif _pc == 356:
            # rung 356
            # CMP "STATE=12" OTE STATE12_IND
            set_tag("STATE12_IND", bool(formula("STATE=12")))
            _pc = 357
            continue
        elif _pc == 357:
            # rung 357
            # XIC STATE12_IND XIO Y_XFER_OK CPT ERROR_CODE 5003 CPT MOVE_TYPE 0 CPT NEXTSTATE 10
            if tag("STATE12_IND"):
                if not tag("Y_XFER_OK"):
                    set_tag("ERROR_CODE", formula("5003"))
            if tag("STATE12_IND"):
                if not tag("Y_XFER_OK"):
                    set_tag("MOVE_TYPE", formula("0"))
            if tag("STATE12_IND"):
                if not tag("Y_XFER_OK"):
                    set_tag("NEXTSTATE", formula("10"))
            _pc = 358
            continue
        elif _pc == 358:
            # rung 358
            # XIC STATE12_IND XIC Y_XFER_OK XIO xz_main_move.IP MCLM xz xz_main_move 0 xz_position_target 800 "Units per sec" 1000 "Units per sec2" 1000 "Units per sec2" S-Curve 1000 1000 "Units per sec3" 0 0 0 0 0 0 0 0
            MCLM(
                coordinate_system="xz",
                motion_control="xz_main_move",
                move_type=0,
                target="xz_position_target",
                speed=800,
                speed_units="Units per sec",
                accel=1000,
                accel_units="Units per sec2",
                decel=1000,
                decel_units="Units per sec2",
                profile="S-Curve",
                accel_jerk=1000,
                decel_jerk=1000,
                jerk_units="Units per sec3",
                termination_type=0,
                merge="0",
                merge_speed=0,
                command_tolerance=0,
                lock_position=0,
                lock_direction="None",
                event_distance=0,
                calculated_data=0,
                rung_in=(tag("STATE12_IND"))
                and (tag("Y_XFER_OK"))
                and (not tag("xz_main_move.IP")),
            )
            _pc = 359
            continue
        elif _pc == 359:
            # rung 359
            # XIO Y_XFER_OK XIC xz_main_move.IP MCS X_Y XZ_xy_stop All Yes 4000 "Units per sec2" Yes 2000 "Units per sec3" MCS xz xz_stop All Yes 4000 "Units per sec2" Yes 200 "Units per sec3" CPT MOVE_TYPE 0 CPT ERROR_CODE 5003 CPT NEXTSTATE 10
            if not tag("Y_XFER_OK"):
                if tag("xz_main_move.IP"):
                    MCS(
                        coordinate_system="X_Y",
                        motion_control="XZ_xy_stop",
                        stop_type="All",
                        change_decel="Yes",
                        decel=4000,
                        decel_units="Units per sec2",
                        change_jerk="Yes",
                        jerk=2000,
                        jerk_units="Units per sec3",
                    )
            if not tag("Y_XFER_OK"):
                if tag("xz_main_move.IP"):
                    MCS(
                        coordinate_system="xz",
                        motion_control="xz_stop",
                        stop_type="All",
                        change_decel="Yes",
                        decel=4000,
                        decel_units="Units per sec2",
                        change_jerk="Yes",
                        jerk=200,
                        jerk_units="Units per sec3",
                    )
            if not tag("Y_XFER_OK"):
                if tag("xz_main_move.IP"):
                    set_tag("MOVE_TYPE", formula("0"))
            if not tag("Y_XFER_OK"):
                if tag("xz_main_move.IP"):
                    set_tag("ERROR_CODE", formula("5003"))
            if not tag("Y_XFER_OK"):
                if tag("xz_main_move.IP"):
                    set_tag("NEXTSTATE", formula("10"))
            _pc = 360
            continue
        elif _pc == 360:
            # rung 360
            # XIC STATE12_IND XIC xz_main_move.ER CPT MOVE_TYPE 0 CPT ERROR_CODE 5003 CPT NEXTSTATE 10
            if tag("STATE12_IND"):
                if tag("xz_main_move.ER"):
                    set_tag("MOVE_TYPE", formula("0"))
            if tag("STATE12_IND"):
                if tag("xz_main_move.ER"):
                    set_tag("ERROR_CODE", formula("5003"))
            if tag("STATE12_IND"):
                if tag("xz_main_move.ER"):
                    set_tag("NEXTSTATE", formula("10"))
            _pc = 361
            continue
        elif _pc == 361:
            # rung 361
            # XIC STATE12_IND CMP "ABS(X_axis.ActualPosition-xz_position_target[0])<0.1" CMP "ABS(Z_axis.ActualPosition-xz_position_target[1])<0.1" CPT MOVE_TYPE 0 CPT NEXTSTATE 1
            if tag("STATE12_IND"):
                if formula("ABS(X_axis.ActualPosition-xz_position_target[0])<0.1"):
                    if formula("ABS(Z_axis.ActualPosition-xz_position_target[1])<0.1"):
                        set_tag("MOVE_TYPE", formula("0"))
            if tag("STATE12_IND"):
                if formula("ABS(X_axis.ActualPosition-xz_position_target[0])<0.1"):
                    if formula("ABS(Z_axis.ActualPosition-xz_position_target[1])<0.1"):
                        set_tag("NEXTSTATE", formula("1"))
            _pc = 362
            continue
        elif _pc == 362:
            # rung 362
            # XIC Y_axis.MoveStatus XIO Z_RETRACTED MAS Y_axis y_axis_stop All Yes 4000 "Units per sec2" Yes 4000 "Units per sec3"
            if tag("Y_axis.MoveStatus"):
                if not tag("Z_RETRACTED"):
                    MAS(
                        axis="Y_axis",
                        motion_control="y_axis_stop",
                        stop_type="All",
                        change_decel="Yes",
                        decel=4000,
                        decel_units="Units per sec2",
                        change_jerk="Yes",
                        jerk=4000,
                        jerk_units="Units per sec3",
                    )
            _pc = 363
            continue
        elif _pc == 363:
            # rung 363
            # CMP "STATE=13" OTE YZ_STATE13_IND
            set_tag("YZ_STATE13_IND", bool(formula("STATE=13")))
            _pc = 364
            continue
        elif _pc == 364:
            # rung 364
            # XIC YZ_STATE13_IND XIO X_XFER_OK CPT ERROR_CODE 5003 CPT MOVE_TYPE 0 CPT NEXTSTATE 10
            if tag("YZ_STATE13_IND"):
                if not tag("X_XFER_OK"):
                    set_tag("ERROR_CODE", formula("5003"))
            if tag("YZ_STATE13_IND"):
                if not tag("X_XFER_OK"):
                    set_tag("MOVE_TYPE", formula("0"))
            if tag("YZ_STATE13_IND"):
                if not tag("X_XFER_OK"):
                    set_tag("NEXTSTATE", formula("10"))
            _pc = 365
            continue
        elif _pc == 365:
            # rung 365
            # XIC YZ_STATE13_IND XIC X_XFER_OK XIO yz_main_move.IP MCLM xz yz_main_move 0 xz_position_target 800 "Units per sec" 1000 "Units per sec2" 1000 "Units per sec2" S-Curve 1000 1000 "Units per sec3" 0 0 0 0 0 0 0 0
            MCLM(
                coordinate_system="xz",
                motion_control="yz_main_move",
                move_type=0,
                target="xz_position_target",
                speed=800,
                speed_units="Units per sec",
                accel=1000,
                accel_units="Units per sec2",
                decel=1000,
                decel_units="Units per sec2",
                profile="S-Curve",
                accel_jerk=1000,
                decel_jerk=1000,
                jerk_units="Units per sec3",
                termination_type=0,
                merge="0",
                merge_speed=0,
                command_tolerance=0,
                lock_position=0,
                lock_direction="None",
                event_distance=0,
                calculated_data=0,
                rung_in=(tag("YZ_STATE13_IND"))
                and (tag("X_XFER_OK"))
                and (not tag("yz_main_move.IP")),
            )
            _pc = 366
            continue
        elif _pc == 366:
            # rung 366
            # XIO Y_XFER_OK XIC yz_main_move.IP MCS X_Y YZ_xy_stop All Yes 4000 "Units per sec2" Yes 2000 "Units per sec3" MCS xz yz_stop All Yes 4000 "Units per sec2" Yes 200 "Units per sec3" CPT MOVE_TYPE 0 CPT ERROR_CODE 5003 CPT NEXTSTATE 10
            if not tag("Y_XFER_OK"):
                if tag("yz_main_move.IP"):
                    MCS(
                        coordinate_system="X_Y",
                        motion_control="YZ_xy_stop",
                        stop_type="All",
                        change_decel="Yes",
                        decel=4000,
                        decel_units="Units per sec2",
                        change_jerk="Yes",
                        jerk=2000,
                        jerk_units="Units per sec3",
                    )
            if not tag("Y_XFER_OK"):
                if tag("yz_main_move.IP"):
                    MCS(
                        coordinate_system="xz",
                        motion_control="yz_stop",
                        stop_type="All",
                        change_decel="Yes",
                        decel=4000,
                        decel_units="Units per sec2",
                        change_jerk="Yes",
                        jerk=200,
                        jerk_units="Units per sec3",
                    )
            if not tag("Y_XFER_OK"):
                if tag("yz_main_move.IP"):
                    set_tag("MOVE_TYPE", formula("0"))
            if not tag("Y_XFER_OK"):
                if tag("yz_main_move.IP"):
                    set_tag("ERROR_CODE", formula("5003"))
            if not tag("Y_XFER_OK"):
                if tag("yz_main_move.IP"):
                    set_tag("NEXTSTATE", formula("10"))
            _pc = 367
            continue
        elif _pc == 367:
            # rung 367
            # XIC YZ_STATE13_IND XIC yz_main_move.ER CPT MOVE_TYPE 0 CPT ERROR_CODE 5003 CPT NEXTSTATE 10
            if tag("YZ_STATE13_IND"):
                if tag("yz_main_move.ER"):
                    set_tag("MOVE_TYPE", formula("0"))
            if tag("YZ_STATE13_IND"):
                if tag("yz_main_move.ER"):
                    set_tag("ERROR_CODE", formula("5003"))
            if tag("YZ_STATE13_IND"):
                if tag("yz_main_move.ER"):
                    set_tag("NEXTSTATE", formula("10"))
            _pc = 368
            continue
        elif _pc == 368:
            # rung 368
            # XIC YZ_STATE13_IND CMP "ABS(X_axis.ActualPosition-xz_position_target[0])<0.1" CMP "ABS(Z_axis.ActualPosition-xz_position_target[1])<0.1" CPT MOVE_TYPE 0 CPT NEXTSTATE 1
            if tag("YZ_STATE13_IND"):
                if formula("ABS(X_axis.ActualPosition-xz_position_target[0])<0.1"):
                    if formula("ABS(Z_axis.ActualPosition-xz_position_target[1])<0.1"):
                        set_tag("MOVE_TYPE", formula("0"))
            if tag("YZ_STATE13_IND"):
                if formula("ABS(X_axis.ActualPosition-xz_position_target[0])<0.1"):
                    if formula("ABS(Z_axis.ActualPosition-xz_position_target[1])<0.1"):
                        set_tag("NEXTSTATE", formula("1"))
            _pc = 369
            continue
        elif _pc == 369:
            # rung 369
            # XIC X_axis.MoveStatus XIO Z_RETRACTED MAS X_axis x_axis_stop All Yes 4000 "Units per sec2" Yes 4000 "Units per sec3"
            if tag("X_axis.MoveStatus"):
                if not tag("Z_RETRACTED"):
                    MAS(
                        axis="X_axis",
                        motion_control="x_axis_stop",
                        stop_type="All",
                        change_decel="Yes",
                        decel=4000,
                        decel_units="Units per sec2",
                        change_jerk="Yes",
                        jerk=4000,
                        jerk_units="Units per sec3",
                    )
            _pc = 370
            continue
        elif _pc == 370:
            # rung 370
            # CMP "STATE=14" OTE STATE14_IND
            set_tag("STATE14_IND", bool(formula("STATE=14")))
            _pc = 371
            continue
        elif _pc == 371:
            # rung 371
            # XIC STATE14_IND XIO hmi_stop_entry_sb OTE hmi_stop_entry_ob
            set_tag(
                "hmi_stop_entry_ob",
                bool((tag("STATE14_IND")) and (not tag("hmi_stop_entry_sb"))),
            )
            _pc = 372
            continue
        elif _pc == 372:
            # rung 372
            # XIC STATE14_IND OTL hmi_stop_entry_sb
            if tag("STATE14_IND"):
                set_tag("hmi_stop_entry_sb", True)
            _pc = 373
            continue
        elif _pc == 373:
            # rung 373
            # XIO STATE14_IND OTU hmi_stop_entry_sb
            if not tag("STATE14_IND"):
                set_tag("hmi_stop_entry_sb", False)
            _pc = 374
            continue
        elif _pc == 374:
            # rung 374
            # XIC hmi_stop_entry_ob MCS X_Y hmi_xy_stop All Yes 1200 "Units per sec2" Yes 1200 "Units per sec3"
            if tag("hmi_stop_entry_ob"):
                MCS(
                    coordinate_system="X_Y",
                    motion_control="hmi_xy_stop",
                    stop_type="All",
                    change_decel="Yes",
                    decel=1200,
                    decel_units="Units per sec2",
                    change_jerk="Yes",
                    jerk=1200,
                    jerk_units="Units per sec3",
                )
            _pc = 375
            continue
        elif _pc == 375:
            # rung 375
            # XIC hmi_stop_entry_ob MCS xz hmi_xz_stop All Yes 1200 "Units per sec2" Yes 1200 "Units per sec3"
            if tag("hmi_stop_entry_ob"):
                MCS(
                    coordinate_system="xz",
                    motion_control="hmi_xz_stop",
                    stop_type="All",
                    change_decel="Yes",
                    decel=1200,
                    decel_units="Units per sec2",
                    change_jerk="Yes",
                    jerk=1200,
                    jerk_units="Units per sec3",
                )
            _pc = 376
            continue
        elif _pc == 376:
            # rung 376
            # XIC hmi_stop_entry_ob MAS X_axis hmi_x_axis_stop All Yes 1200 "Units per sec2" Yes 1200 "Units per sec3"
            if tag("hmi_stop_entry_ob"):
                MAS(
                    axis="X_axis",
                    motion_control="hmi_x_axis_stop",
                    stop_type="All",
                    change_decel="Yes",
                    decel=1200,
                    decel_units="Units per sec2",
                    change_jerk="Yes",
                    jerk=1200,
                    jerk_units="Units per sec3",
                )
            _pc = 377
            continue
        elif _pc == 377:
            # rung 377
            # XIC hmi_stop_entry_ob MAS Y_axis hmi_y_axis_stop All Yes 1200 "Units per sec2" Yes 1200 "Units per sec3"
            if tag("hmi_stop_entry_ob"):
                MAS(
                    axis="Y_axis",
                    motion_control="hmi_y_axis_stop",
                    stop_type="All",
                    change_decel="Yes",
                    decel=1200,
                    decel_units="Units per sec2",
                    change_jerk="Yes",
                    jerk=1200,
                    jerk_units="Units per sec3",
                )
            _pc = 378
            continue
        elif _pc == 378:
            # rung 378
            # XIC hmi_stop_entry_ob MAS Z_axis hmi_z_axis_stop All Yes 1200 "Units per sec2" Yes 1200 "Units per sec3"
            if tag("hmi_stop_entry_ob"):
                MAS(
                    axis="Z_axis",
                    motion_control="hmi_z_axis_stop",
                    stop_type="All",
                    change_decel="Yes",
                    decel=1200,
                    decel_units="Units per sec2",
                    change_jerk="Yes",
                    jerk=1200,
                    jerk_units="Units per sec3",
                )
            _pc = 379
            continue
        elif _pc == 379:
            # rung 379
            # XIC STATE14_IND OTE AbortQueue
            set_tag("AbortQueue", bool(tag("STATE14_IND")))
            _pc = 380
            continue
        elif _pc == 380:
            # rung 380
            # XIC STATE14_IND CPT MOVE_TYPE 0
            if tag("STATE14_IND"):
                set_tag("MOVE_TYPE", formula("0"))
            _pc = 381
            continue
        elif _pc == 381:
            # rung 381
            # XIC STATE14_IND XIC hmi_xy_stop.DN XIC hmi_xz_stop.DN XIC hmi_x_axis_stop.DN XIC hmi_y_axis_stop.DN XIC hmi_z_axis_stop.DN XIO CurIssued XIO NextIssued XIO X_Y.MovePendingStatus LEQ QueueCount 0 CPT NEXTSTATE 1
            if tag("STATE14_IND"):
                if tag("hmi_xy_stop.DN"):
                    if tag("hmi_xz_stop.DN"):
                        if tag("hmi_x_axis_stop.DN"):
                            if tag("hmi_y_axis_stop.DN"):
                                if tag("hmi_z_axis_stop.DN"):
                                    if not tag("CurIssued"):
                                        if not tag("NextIssued"):
                                            if not tag("X_Y.MovePendingStatus"):
                                                if tag("QueueCount") <= 0:
                                                    set_tag("NEXTSTATE", formula("1"))
            _pc = 382
            continue
        elif _pc == 382:
            # rung 382
            # EQU QueueCtl.POS 0 OTE QueueEmpty
            set_tag("QueueEmpty", bool(tag("QueueCtl.POS") == 0))
            _pc = 383
            continue
        elif _pc == 383:
            # rung 383
            # GEQ QueueCtl.POS 32 OTE QueueFull
            set_tag("QueueFull", bool(tag("QueueCtl.POS") >= 32))
            _pc = 384
            continue
        elif _pc == 384:
            # rung 384
            # MOV QueueCtl.POS QueueCount
            set_tag("QueueCount", tag("QueueCtl.POS"))
            _pc = 385
            continue
        elif _pc == 385:
            # rung 385
            # CMP "MOVE_TYPE=11" OTL AbortQueue CPT NEXTSTATE 14
            if formula("MOVE_TYPE=11"):
                set_tag("AbortQueue", True)
            if formula("MOVE_TYPE=11"):
                set_tag("NEXTSTATE", formula("14"))
            _pc = 386
            continue
        elif _pc == 386:
            # rung 386
            # XIC QueueStopRequest BST XIC CurIssued NXB XIC NextIssued NXB XIC X_Y.MovePendingStatus BND ONS QueueStopReqONS MCS X_Y gui_stop All Yes 2000 "Units per sec2" Yes 1000 "Units per sec3"
            _branch_502 = bool(tag("CurIssued"))
            _branch_504 = bool(tag("NextIssued"))
            _branch_506 = bool(tag("X_Y.MovePendingStatus"))
            _branch_508 = _branch_502 or _branch_504 or _branch_506
            _pulse_509 = ONS(
                storage_bit="QueueStopReqONS",
                rung_in=(tag("QueueStopRequest")) and (_branch_508),
            )
            if _pulse_509:
                MCS(
                    coordinate_system="X_Y",
                    motion_control="gui_stop",
                    stop_type="All",
                    change_decel="Yes",
                    decel=2000,
                    decel_units="Units per sec2",
                    change_jerk="Yes",
                    jerk=1000,
                    jerk_units="Units per sec3",
                )
            _pc = 387
            continue
        elif _pc == 387:
            # rung 387
            # XIC QueueStopRequest OTL AbortQueue
            if tag("QueueStopRequest"):
                set_tag("AbortQueue", True)
            _pc = 388
            continue
        elif _pc == 388:
            # rung 388
            # BST XIC AbortQueue NXB XIO ALL_EOT_GOOD BND OTE AbortActive
            _branch_510 = bool(tag("AbortQueue"))
            _branch_512 = bool(not tag("ALL_EOT_GOOD"))
            _branch_514 = _branch_510 or _branch_512
            set_tag("AbortActive", bool(_branch_514))
            _pc = 389
            continue
        elif _pc == 389:
            # rung 389
            # NEQ IncomingSegReqID LastIncomingSegReqID OTL EnqueueReq
            if tag("IncomingSegReqID") != tag("LastIncomingSegReqID"):
                set_tag("EnqueueReq", True)
            _pc = 390
            continue
        elif _pc == 390:
            # rung 390
            # XIC EnqueueReq XIC IncomingSeg.Valid EQU IncomingSeg.SegType 1 GRT IncomingSeg.Speed 0.0 GRT IncomingSeg.Accel 0.0 GRT IncomingSeg.Decel 0.0 GEQ IncomingSeg.TermType 0 LEQ IncomingSeg.TermType 6 OTE SegValidLine
            set_tag(
                "SegValidLine",
                bool(
                    (tag("EnqueueReq"))
                    and (tag("IncomingSeg.Valid"))
                    and (tag("IncomingSeg.SegType") == 1)
                    and (tag("IncomingSeg.Speed") > 0.0)
                    and (tag("IncomingSeg.Accel") > 0.0)
                    and (tag("IncomingSeg.Decel") > 0.0)
                    and (tag("IncomingSeg.TermType") >= 0)
                    and (tag("IncomingSeg.TermType") <= 6)
                ),
            )
            _pc = 391
            continue
        elif _pc == 391:
            # rung 391
            # XIC EnqueueReq XIC IncomingSeg.Valid EQU IncomingSeg.SegType 2 GRT IncomingSeg.Speed 0.0 GRT IncomingSeg.Accel 0.0 GRT IncomingSeg.Decel 0.0 GEQ IncomingSeg.TermType 0 LEQ IncomingSeg.TermType 6 GEQ IncomingSeg.CircleType 0 LEQ IncomingSeg.CircleType 3 GEQ IncomingSeg.Direction 0 LEQ IncomingSeg.Direction 3 OTE SegValidArc
            set_tag(
                "SegValidArc",
                bool(
                    (tag("EnqueueReq"))
                    and (tag("IncomingSeg.Valid"))
                    and (tag("IncomingSeg.SegType") == 2)
                    and (tag("IncomingSeg.Speed") > 0.0)
                    and (tag("IncomingSeg.Accel") > 0.0)
                    and (tag("IncomingSeg.Decel") > 0.0)
                    and (tag("IncomingSeg.TermType") >= 0)
                    and (tag("IncomingSeg.TermType") <= 6)
                    and (tag("IncomingSeg.CircleType") >= 0)
                    and (tag("IncomingSeg.CircleType") <= 3)
                    and (tag("IncomingSeg.Direction") >= 0)
                    and (tag("IncomingSeg.Direction") <= 3)
                ),
            )
            _pc = 392
            continue
        elif _pc == 392:
            # rung 392
            # BST XIC SegValidLine NXB XIC SegValidArc BND OTE SegValid
            _branch_515 = bool(tag("SegValidLine"))
            _branch_517 = bool(tag("SegValidArc"))
            _branch_519 = _branch_515 or _branch_517
            set_tag("SegValid", bool(_branch_519))
            _pc = 393
            continue
        elif _pc == 393:
            # rung 393
            # XIC EnqueueReq XIC SegValid XIO QueueFull FFL IncomingSeg SegQueue[0] QueueCtl 32 0
            FFL(
                source="IncomingSeg",
                array="SegQueue[0]",
                control="QueueCtl",
                length=32,
                position=0,
                rung_in=(tag("EnqueueReq"))
                and (tag("SegValid"))
                and (not tag("QueueFull")),
            )
            _pc = 394
            continue
        elif _pc == 394:
            # rung 394
            # XIC EnqueueReq XIC SegValid XIO QueueFull MOV IncomingSeg.Seq IncomingSegAck
            if tag("EnqueueReq"):
                if tag("SegValid"):
                    if not tag("QueueFull"):
                        set_tag("IncomingSegAck", tag("IncomingSeg.Seq"))
            _pc = 395
            continue
        elif _pc == 395:
            # rung 395
            # XIC EnqueueReq XIC SegValid XIO QueueFull MOV IncomingSegReqID LastIncomingSegReqID
            if tag("EnqueueReq"):
                if tag("SegValid"):
                    if not tag("QueueFull"):
                        set_tag("LastIncomingSegReqID", tag("IncomingSegReqID"))
            _pc = 396
            continue
        elif _pc == 396:
            # rung 396
            # XIC EnqueueReq OTU EnqueueReq
            if tag("EnqueueReq"):
                set_tag("EnqueueReq", False)
            _pc = 397
            continue
        elif _pc == 397:
            # rung 397
            # XIC MoveA.ER MOV 3 FaultCode
            if tag("MoveA.ER"):
                set_tag("FaultCode", 3)
            _pc = 398
            continue
        elif _pc == 398:
            # rung 398
            # XIC MoveA.ER OTL QueueFault
            if tag("MoveA.ER"):
                set_tag("QueueFault", True)
            _pc = 399
            continue
        elif _pc == 399:
            # rung 399
            # XIC MoveA.ER OTL AbortQueue
            if tag("MoveA.ER"):
                set_tag("AbortQueue", True)
            _pc = 400
            continue
        elif _pc == 400:
            # rung 400
            # XIC MoveA.ER OTU MoveA.ER
            if tag("MoveA.ER"):
                set_tag("MoveA.ER", False)
            _pc = 401
            continue
        elif _pc == 401:
            # rung 401
            # XIC MoveB.ER MOV 4 FaultCode
            if tag("MoveB.ER"):
                set_tag("FaultCode", 4)
            _pc = 402
            continue
        elif _pc == 402:
            # rung 402
            # XIC MoveB.ER OTL QueueFault
            if tag("MoveB.ER"):
                set_tag("QueueFault", True)
            _pc = 403
            continue
        elif _pc == 403:
            # rung 403
            # XIC MoveB.ER OTL AbortQueue
            if tag("MoveB.ER"):
                set_tag("AbortQueue", True)
            _pc = 404
            continue
        elif _pc == 404:
            # rung 404
            # XIC MoveB.ER OTU MoveB.ER
            if tag("MoveB.ER"):
                set_tag("MoveB.ER", False)
            _pc = 405
            continue
        elif _pc == 405:
            # rung 405
            # BST XIC QueueFault NXB XIC MoveA.ER NXB XIC MoveB.ER BND OTE MotionFault
            _branch_520 = bool(tag("QueueFault"))
            _branch_522 = bool(tag("MoveA.ER"))
            _branch_524 = bool(tag("MoveB.ER"))
            _branch_526 = _branch_520 or _branch_522 or _branch_524
            set_tag("MotionFault", bool(_branch_526))
            _pc = 406
            continue
        elif _pc == 406:
            # rung 406
            # XIC CheckCurSeg XIC CurSeg.Valid GRT CurSeg.Seq 0 BST EQU CurSeg.SegType 1 NXB EQU CurSeg.SegType 2 BND OTL PrepCurMove
            _branch_527 = bool(tag("CurSeg.SegType") == 1)
            _branch_529 = bool(tag("CurSeg.SegType") == 2)
            _branch_531 = _branch_527 or _branch_529
            if tag("CheckCurSeg"):
                if tag("CurSeg.Valid"):
                    if tag("CurSeg.Seq") > 0:
                        if _branch_531:
                            set_tag("PrepCurMove", True)
            _pc = 407
            continue
        elif _pc == 407:
            # rung 407
            # XIC CheckCurSeg XIO CurSeg.Valid MOV 1 FaultCode
            if tag("CheckCurSeg"):
                if not tag("CurSeg.Valid"):
                    set_tag("FaultCode", 1)
            _pc = 408
            continue
        elif _pc == 408:
            # rung 408
            # XIC CheckCurSeg XIO CurSeg.Valid OTL QueueFault
            if tag("CheckCurSeg"):
                if not tag("CurSeg.Valid"):
                    set_tag("QueueFault", True)
            _pc = 409
            continue
        elif _pc == 409:
            # rung 409
            # XIC CheckCurSeg XIC CurSeg.Valid LEQ CurSeg.Seq 0 MOV 6 FaultCode
            if tag("CheckCurSeg"):
                if tag("CurSeg.Valid"):
                    if tag("CurSeg.Seq") <= 0:
                        set_tag("FaultCode", 6)
            _pc = 410
            continue
        elif _pc == 410:
            # rung 410
            # XIC CheckCurSeg XIC CurSeg.Valid LEQ CurSeg.Seq 0 OTL QueueFault
            if tag("CheckCurSeg"):
                if tag("CurSeg.Valid"):
                    if tag("CurSeg.Seq") <= 0:
                        set_tag("QueueFault", True)
            _pc = 411
            continue
        elif _pc == 411:
            # rung 411
            # XIC CheckCurSeg XIC CurSeg.Valid GRT CurSeg.Seq 0 BST LES CurSeg.SegType 1 NXB GRT CurSeg.SegType 2 BND MOV 7 FaultCode
            _branch_532 = bool(tag("CurSeg.SegType") < 1)
            _branch_534 = bool(tag("CurSeg.SegType") > 2)
            _branch_536 = _branch_532 or _branch_534
            if tag("CheckCurSeg"):
                if tag("CurSeg.Valid"):
                    if tag("CurSeg.Seq") > 0:
                        if _branch_536:
                            set_tag("FaultCode", 7)
            _pc = 412
            continue
        elif _pc == 412:
            # rung 412
            # XIC CheckCurSeg XIC CurSeg.Valid GRT CurSeg.Seq 0 BST LES CurSeg.SegType 1 NXB GRT CurSeg.SegType 2 BND OTL QueueFault
            _branch_537 = bool(tag("CurSeg.SegType") < 1)
            _branch_539 = bool(tag("CurSeg.SegType") > 2)
            _branch_541 = _branch_537 or _branch_539
            if tag("CheckCurSeg"):
                if tag("CurSeg.Valid"):
                    if tag("CurSeg.Seq") > 0:
                        if _branch_541:
                            set_tag("QueueFault", True)
            _pc = 413
            continue
        elif _pc == 413:
            # rung 413
            # XIC CheckCurSeg OTU CheckCurSeg
            if tag("CheckCurSeg"):
                set_tag("CheckCurSeg", False)
            _pc = 414
            continue
        elif _pc == 414:
            # rung 414
            # XIC CheckNextSeg XIC NextSeg.Valid GRT NextSeg.Seq 0 BST EQU NextSeg.SegType 1 NXB EQU NextSeg.SegType 2 BND OTL PrepNextMove
            _branch_542 = bool(tag("NextSeg.SegType") == 1)
            _branch_544 = bool(tag("NextSeg.SegType") == 2)
            _branch_546 = _branch_542 or _branch_544
            if tag("CheckNextSeg"):
                if tag("NextSeg.Valid"):
                    if tag("NextSeg.Seq") > 0:
                        if _branch_546:
                            set_tag("PrepNextMove", True)
            _pc = 415
            continue
        elif _pc == 415:
            # rung 415
            # XIC CheckNextSeg XIO NextSeg.Valid MOV 2 FaultCode
            if tag("CheckNextSeg"):
                if not tag("NextSeg.Valid"):
                    set_tag("FaultCode", 2)
            _pc = 416
            continue
        elif _pc == 416:
            # rung 416
            # XIC CheckNextSeg XIO NextSeg.Valid OTL QueueFault
            if tag("CheckNextSeg"):
                if not tag("NextSeg.Valid"):
                    set_tag("QueueFault", True)
            _pc = 417
            continue
        elif _pc == 417:
            # rung 417
            # XIC CheckNextSeg XIC NextSeg.Valid LEQ NextSeg.Seq 0 MOV 5 FaultCode
            if tag("CheckNextSeg"):
                if tag("NextSeg.Valid"):
                    if tag("NextSeg.Seq") <= 0:
                        set_tag("FaultCode", 5)
            _pc = 418
            continue
        elif _pc == 418:
            # rung 418
            # XIC CheckNextSeg XIC NextSeg.Valid LEQ NextSeg.Seq 0 OTL QueueFault
            if tag("CheckNextSeg"):
                if tag("NextSeg.Valid"):
                    if tag("NextSeg.Seq") <= 0:
                        set_tag("QueueFault", True)
            _pc = 419
            continue
        elif _pc == 419:
            # rung 419
            # XIC CheckNextSeg XIC NextSeg.Valid GRT NextSeg.Seq 0 BST LES NextSeg.SegType 1 NXB GRT NextSeg.SegType 2 BND MOV 8 FaultCode
            _branch_547 = bool(tag("NextSeg.SegType") < 1)
            _branch_549 = bool(tag("NextSeg.SegType") > 2)
            _branch_551 = _branch_547 or _branch_549
            if tag("CheckNextSeg"):
                if tag("NextSeg.Valid"):
                    if tag("NextSeg.Seq") > 0:
                        if _branch_551:
                            set_tag("FaultCode", 8)
            _pc = 420
            continue
        elif _pc == 420:
            # rung 420
            # XIC CheckNextSeg XIC NextSeg.Valid GRT NextSeg.Seq 0 BST LES NextSeg.SegType 1 NXB GRT NextSeg.SegType 2 BND OTL QueueFault
            _branch_552 = bool(tag("NextSeg.SegType") < 1)
            _branch_554 = bool(tag("NextSeg.SegType") > 2)
            _branch_556 = _branch_552 or _branch_554
            if tag("CheckNextSeg"):
                if tag("NextSeg.Valid"):
                    if tag("NextSeg.Seq") > 0:
                        if _branch_556:
                            set_tag("QueueFault", True)
            _pc = 421
            continue
        elif _pc == 421:
            # rung 421
            # XIC CheckNextSeg OTU CheckNextSeg
            if tag("CheckNextSeg"):
                set_tag("CheckNextSeg", False)
            _pc = 422
            continue
        elif _pc == 422:
            # rung 422
            # XIO CurIssued XIO NextIssued XIO QueueFault GEQ QueueCtl.POS 1 MOV QueueCtl.POS DINTS[5]
            if not tag("CurIssued"):
                if not tag("NextIssued"):
                    if not tag("QueueFault"):
                        if tag("QueueCtl.POS") >= 1:
                            set_tag("DINTS[5]", tag("QueueCtl.POS"))
            _pc = 423
            continue
        elif _pc == 423:
            # rung 423
            # BST XIC CurIssued NXB XIC NextIssued NXB XIC QueueFault NXB LEQ QueueCtl.POS 0 BND MOV 0 DINTS[5]
            _branch_557 = bool(tag("CurIssued"))
            _branch_559 = bool(tag("NextIssued"))
            _branch_561 = bool(tag("QueueFault"))
            _branch_563 = bool(tag("QueueCtl.POS") <= 0)
            _branch_565 = _branch_557 or _branch_559 or _branch_561 or _branch_563
            if _branch_565:
                set_tag("DINTS[5]", 0)
            _pc = 424
            continue
        elif _pc == 424:
            # rung 424
            # XIO CurIssued XIO NextIssued XIO QueueFault GEQ QueueCtl.POS 1 MOV v_x_max REALS[38]
            if not tag("CurIssued"):
                if not tag("NextIssued"):
                    if not tag("QueueFault"):
                        if tag("QueueCtl.POS") >= 1:
                            set_tag("REALS[38]", tag("v_x_max"))
            _pc = 425
            continue
        elif _pc == 425:
            # rung 425
            # XIO CurIssued XIO NextIssued XIO QueueFault GEQ QueueCtl.POS 1 MOV v_y_max REALS[39]
            if not tag("CurIssued"):
                if not tag("NextIssued"):
                    if not tag("QueueFault"):
                        if tag("QueueCtl.POS") >= 1:
                            set_tag("REALS[39]", tag("v_y_max"))
            _pc = 426
            continue
        elif _pc == 426:
            # rung 426
            # XIO CurIssued XIO NextIssued XIO QueueFault GEQ QueueCtl.POS 1 MOV X_axis.ActualPosition REALS[40]
            if not tag("CurIssued"):
                if not tag("NextIssued"):
                    if not tag("QueueFault"):
                        if tag("QueueCtl.POS") >= 1:
                            set_tag("REALS[40]", tag("X_axis.ActualPosition"))
            _pc = 427
            continue
        elif _pc == 427:
            # rung 427
            # XIO CurIssued XIO NextIssued XIO QueueFault GEQ QueueCtl.POS 1 MOV Y_axis.ActualPosition REALS[41]
            if not tag("CurIssued"):
                if not tag("NextIssued"):
                    if not tag("QueueFault"):
                        if tag("QueueCtl.POS") >= 1:
                            set_tag("REALS[41]", tag("Y_axis.ActualPosition"))
            _pc = 428
            continue
        elif _pc == 428:
            # rung 428
            # XIO CurIssued XIO NextIssued XIO QueueFault GEQ QueueCtl.POS 1 OTL BOOLS[7]
            if not tag("CurIssued"):
                if not tag("NextIssued"):
                    if not tag("QueueFault"):
                        if tag("QueueCtl.POS") >= 1:
                            set_tag("BOOLS[7]", True)
            _pc = 429
            continue
        elif _pc == 429:
            # rung 429
            # NEQ DINTS[5] 0 JMP MQ_cap_lbl_else_46
            if tag("DINTS[5]") != 0:
                _pc = 431
                continue
            _pc = 430
            continue
        elif _pc == 430:
            # rung 430
            # JMP MQ_cap_lbl_CapSegSpeed_end
            _pc = 622
            continue
            _pc = 431
            continue
        elif _pc == 431:
            # rung 431
            # LBL MQ_cap_lbl_else_46 BST LEQ REALS[38] 0.0 NXB LEQ REALS[39] 0.0 BND OTL BOOLS[901]
            _branch_566 = bool(tag("REALS[38]") <= 0.0)
            _branch_568 = bool(tag("REALS[39]") <= 0.0)
            _branch_570 = _branch_566 or _branch_568
            if _branch_570:
                set_tag("BOOLS[901]", True)
            _pc = 432
            continue
        elif _pc == 432:
            # rung 432
            # GRT REALS[38] 0.0 GRT REALS[39] 0.0 JMP MQ_cap_lbl_else_48
            if tag("REALS[38]") > 0.0:
                if tag("REALS[39]") > 0.0:
                    _pc = 435
                    continue
            _pc = 433
            continue
        elif _pc == 433:
            # rung 433
            # OTL BOOLS[8]
            set_tag("BOOLS[8]", True)
            _pc = 434
            continue
        elif _pc == 434:
            # rung 434
            # JMP MQ_cap_lbl_CapSegSpeed_end
            _pc = 622
            continue
            _pc = 435
            continue
        elif _pc == 435:
            # rung 435
            # LBL MQ_cap_lbl_else_48 BST LES REALS[38] 3.4028235E+38 NXB LES REALS[39] 3.4028235E+38 BND OTL BOOLS[902]
            _branch_571 = bool(tag("REALS[38]") < 3.4028235e38)
            _branch_573 = bool(tag("REALS[39]") < 3.4028235e38)
            _branch_575 = _branch_571 or _branch_573
            if _branch_575:
                set_tag("BOOLS[902]", True)
            _pc = 436
            continue
        elif _pc == 436:
            # rung 436
            # XIC BOOLS[902] JMP MQ_cap_lbl_else_50
            if tag("BOOLS[902]"):
                _pc = 438
                continue
            _pc = 437
            continue
        elif _pc == 437:
            # rung 437
            # JMP MQ_cap_lbl_CapSegSpeed_end
            _pc = 622
            continue
            _pc = 438
            continue
        elif _pc == 438:
            # rung 438
            # LBL MQ_cap_lbl_else_50 XIC BOOLS[7] JMP MQ_cap_lbl_else_52
            if tag("BOOLS[7]"):
                _pc = 443
                continue
            _pc = 439
            continue
        elif _pc == 439:
            # rung 439
            # MOV SegQueue[0].XY[0] REALS[42]
            set_tag("REALS[42]", tag("SegQueue[0].XY[0]"))
            _pc = 440
            continue
        elif _pc == 440:
            # rung 440
            # MOV SegQueue[0].XY[1] REALS[43]
            set_tag("REALS[43]", tag("SegQueue[0].XY[1]"))
            _pc = 441
            continue
        elif _pc == 441:
            # rung 441
            # OTL BOOLS[9]
            set_tag("BOOLS[9]", True)
            _pc = 442
            continue
        elif _pc == 442:
            # rung 442
            # JMP MQ_cap_lbl_end_53
            _pc = 446
            continue
            _pc = 443
            continue
        elif _pc == 443:
            # rung 443
            # LBL MQ_cap_lbl_else_52 MOV REALS[40] REALS[42]
            set_tag("REALS[42]", tag("REALS[40]"))
            _pc = 444
            continue
        elif _pc == 444:
            # rung 444
            # MOV REALS[41] REALS[43]
            set_tag("REALS[43]", tag("REALS[41]"))
            _pc = 445
            continue
        elif _pc == 445:
            # rung 445
            # OTU BOOLS[9]
            set_tag("BOOLS[9]", False)
            _pc = 446
            continue
        elif _pc == 446:
            # rung 446
            # LBL MQ_cap_lbl_end_53 MOV 0 idx_3
            set_tag("idx_3", 0)
            _pc = 447
            continue
        elif _pc == 447:
            # rung 447
            # LBL MQ_cap_lbl_loop_54 GEQ idx_3 DINTS[5] JMP MQ_cap_lbl_loop_end_55
            if tag("idx_3") >= tag("DINTS[5]"):
                _pc = 621
                continue
            _pc = 448
            continue
        elif _pc == 448:
            # rung 448
            # BST NEQ idx_3 0 NXB XIO BOOLS[9] BND OTL BOOLS[903]
            _branch_576 = bool(tag("idx_3") != 0)
            _branch_578 = bool(not tag("BOOLS[9]"))
            _branch_580 = _branch_576 or _branch_578
            if _branch_580:
                set_tag("BOOLS[903]", True)
            _pc = 449
            continue
        elif _pc == 449:
            # rung 449
            # XIC BOOLS[903] JMP MQ_cap_lbl_else_56
            if tag("BOOLS[903]"):
                _pc = 456
                continue
            _pc = 450
            continue
        elif _pc == 450:
            # rung 450
            # LES REALS[38] REALS[39] JMP MQ_cap_lbl_min_a_58
            if tag("REALS[38]") < tag("REALS[39]"):
                _pc = 452
                continue
            _pc = 451
            continue
        elif _pc == 451:
            # rung 451
            # MOV REALS[39] REALS[44] JMP MQ_cap_lbl_min_end_59
            set_tag("REALS[44]", tag("REALS[39]"))
            _pc = 453
            continue
            _pc = 452
            continue
        elif _pc == 452:
            # rung 452
            # LBL MQ_cap_lbl_min_a_58 MOV REALS[38] REALS[44]
            set_tag("REALS[44]", tag("REALS[38]"))
            _pc = 453
            continue
        elif _pc == 453:
            # rung 453
            # LBL MQ_cap_lbl_min_end_59 MOV 1.0 REALS[45]
            set_tag("REALS[45]", 1.0)
            _pc = 454
            continue
        elif _pc == 454:
            # rung 454
            # MOV 1.0 REALS[46]
            set_tag("REALS[46]", 1.0)
            _pc = 455
            continue
        elif _pc == 455:
            # rung 455
            # JMP MQ_cap_lbl_end_57
            _pc = 610
            continue
            _pc = 456
            continue
        elif _pc == 456:
            # rung 456
            # LBL MQ_cap_lbl_else_56 MOV REALS[42] REALS[20]
            set_tag("REALS[20]", tag("REALS[42]"))
            _pc = 457
            continue
        elif _pc == 457:
            # rung 457
            # MOV REALS[43] REALS[21]
            set_tag("REALS[21]", tag("REALS[43]"))
            _pc = 458
            continue
        elif _pc == 458:
            # rung 458
            # MOV idx_3 idx_2
            set_tag("idx_2", tag("idx_3"))
            _pc = 459
            continue
        elif _pc == 459:
            # rung 459
            # NEQ SegQueue[idx_2].SegType 1 JMP MQ_seg_lbl_else_30
            if tag("SegQueue[idx_2].SegType") != 1:
                _pc = 470
                continue
            _pc = 460
            continue
        elif _pc == 460:
            # rung 460
            # CPT REALS[24] SegQueue[idx_2].XY[0]-REALS[20]
            set_tag("REALS[24]", formula("SegQueue[idx_2].XY[0]-REALS[20]"))
            _pc = 461
            continue
        elif _pc == 461:
            # rung 461
            # CPT REALS[25] SegQueue[idx_2].XY[1]-REALS[21]
            set_tag("REALS[25]", formula("SegQueue[idx_2].XY[1]-REALS[21]"))
            _pc = 462
            continue
        elif _pc == 462:
            # rung 462
            # CPT REALS[26] SQR(REALS[24]*REALS[24]+REALS[25]*REALS[25])
            set_tag(
                "REALS[26]", formula("SQR(REALS[24]*REALS[24]+REALS[25]*REALS[25])")
            )
            _pc = 463
            continue
        elif _pc == 463:
            # rung 463
            # GRT REALS[26] 0.000000001 JMP MQ_seg_lbl_else_32
            if tag("REALS[26]") > 0.000000001:
                _pc = 467
                continue
            _pc = 464
            continue
        elif _pc == 464:
            # rung 464
            # MOV 0.0 REALS[22]
            set_tag("REALS[22]", 0.0)
            _pc = 465
            continue
        elif _pc == 465:
            # rung 465
            # MOV 0.0 REALS[23]
            set_tag("REALS[23]", 0.0)
            _pc = 466
            continue
        elif _pc == 466:
            # rung 466
            # JMP MQ_seg_lbl_SegTangentBounds_end
            _pc = 595
            continue
            _pc = 467
            continue
        elif _pc == 467:
            # rung 467
            # LBL MQ_seg_lbl_else_32 CPT REALS[22] ABS(REALS[24]/REALS[26])
            set_tag("REALS[22]", formula("ABS(REALS[24]/REALS[26])"))
            _pc = 468
            continue
        elif _pc == 468:
            # rung 468
            # CPT REALS[23] ABS(REALS[25]/REALS[26])
            set_tag("REALS[23]", formula("ABS(REALS[25]/REALS[26])"))
            _pc = 469
            continue
        elif _pc == 469:
            # rung 469
            # JMP MQ_seg_lbl_SegTangentBounds_end
            _pc = 595
            continue
            _pc = 470
            continue
        elif _pc == 470:
            # rung 470
            # LBL MQ_seg_lbl_else_30 NEQ SegQueue[idx_2].SegType 2 JMP MQ_seg_lbl_else_34
            if tag("SegQueue[idx_2].SegType") != 2:
                _pc = 585
                continue
            _pc = 471
            continue
        elif _pc == 471:
            # rung 471
            # MOV idx_2 idx_0
            set_tag("idx_0", tag("idx_2"))
            _pc = 472
            continue
        elif _pc == 472:
            # rung 472
            # MOV idx_2 idx_1
            set_tag("idx_1", tag("idx_2"))
            _pc = 473
            continue
        elif _pc == 473:
            # rung 473
            # NEQ REALS[28] 0 JMP MQ_seg_lbl_else_36
            if tag("REALS[28]") != 0:
                _pc = 584
                continue
            _pc = 474
            continue
        elif _pc == 474:
            # rung 474
            # CPT REALS[31] SQR(REALS[20]-REALS[29]*REALS[20]-REALS[29]+REALS[21]-REALS[30]*REALS[21]-REALS[30])
            set_tag(
                "REALS[31]",
                formula(
                    "SQR(REALS[20]-REALS[29]*REALS[20]-REALS[29]+REALS[21]-REALS[30]*REALS[21]-REALS[30])"
                ),
            )
            _pc = 475
            continue
        elif _pc == 475:
            # rung 475
            # CPT REALS[32] SQR(SegQueue[idx_2].XY[0]-REALS[29]*SegQueue[idx_2].XY[0]-REALS[29]+SegQueue[idx_2].XY[1]-REALS[30]*SegQueue[idx_2].XY[1]-REALS[30])
            set_tag(
                "REALS[32]",
                formula(
                    "SQR(SegQueue[idx_2].XY[0]-REALS[29]*SegQueue[idx_2].XY[0]-REALS[29]+SegQueue[idx_2].XY[1]-REALS[30]*SegQueue[idx_2].XY[1]-REALS[30])"
                ),
            )
            _pc = 476
            continue
        elif _pc == 476:
            # rung 476
            # BST LEQ REALS[31] 0.000000001 NXB LEQ REALS[32] 0.000000001 BND OTL BOOLS[900]
            _branch_581 = bool(tag("REALS[31]") <= 0.000000001)
            _branch_583 = bool(tag("REALS[32]") <= 0.000000001)
            _branch_585 = _branch_581 or _branch_583
            if _branch_585:
                set_tag("BOOLS[900]", True)
            _pc = 477
            continue
        elif _pc == 477:
            # rung 477
            # XIC BOOLS[900] JMP MQ_seg_lbl_else_38
            if tag("BOOLS[900]"):
                _pc = 583
                continue
            _pc = 478
            continue
        elif _pc == 478:
            # rung 478
            # CPT REALS[912] REALS[21]-REALS[30]
            set_tag("REALS[912]", formula("REALS[21]-REALS[30]"))
            _pc = 479
            continue
        elif _pc == 479:
            # rung 479
            # CPT REALS[913] REALS[20]-REALS[29]
            set_tag("REALS[913]", formula("REALS[20]-REALS[29]"))
            _pc = 480
            continue
        elif _pc == 480:
            # rung 480
            # GRT REALS[913] 0.0 CPT REALS[33] ATN(REALS[912]/REALS[913]) JMP MQ_seg_lbl_atan2_done_40
            if tag("REALS[913]") > 0.0:
                set_tag("REALS[33]", formula("ATN(REALS[912]/REALS[913])"))
            if tag("REALS[913]") > 0.0:
                _pc = 486
                continue
            _pc = 481
            continue
        elif _pc == 481:
            # rung 481
            # LES REALS[913] 0.0 GEQ REALS[912] 0.0 CPT REALS[33] ATN(REALS[912]/REALS[913])+3.14159265358979 JMP MQ_seg_lbl_atan2_done_40
            if tag("REALS[913]") < 0.0:
                if tag("REALS[912]") >= 0.0:
                    set_tag(
                        "REALS[33]",
                        formula("ATN(REALS[912]/REALS[913])+3.14159265358979"),
                    )
            if tag("REALS[913]") < 0.0:
                if tag("REALS[912]") >= 0.0:
                    _pc = 486
                    continue
            _pc = 482
            continue
        elif _pc == 482:
            # rung 482
            # LES REALS[913] 0.0 LES REALS[912] 0.0 CPT REALS[33] ATN(REALS[912]/REALS[913])-3.14159265358979 JMP MQ_seg_lbl_atan2_done_40
            if tag("REALS[913]") < 0.0:
                if tag("REALS[912]") < 0.0:
                    set_tag(
                        "REALS[33]",
                        formula("ATN(REALS[912]/REALS[913])-3.14159265358979"),
                    )
            if tag("REALS[913]") < 0.0:
                if tag("REALS[912]") < 0.0:
                    _pc = 486
                    continue
            _pc = 483
            continue
        elif _pc == 483:
            # rung 483
            # EQU REALS[913] 0.0 GRT REALS[912] 0.0 MOV 1.5707963267949 REALS[33] JMP MQ_seg_lbl_atan2_done_40
            if tag("REALS[913]") == 0.0:
                if tag("REALS[912]") > 0.0:
                    set_tag("REALS[33]", 1.5707963267949)
            if tag("REALS[913]") == 0.0:
                if tag("REALS[912]") > 0.0:
                    _pc = 486
                    continue
            _pc = 484
            continue
        elif _pc == 484:
            # rung 484
            # EQU REALS[913] 0.0 LES REALS[912] 0.0 MOV -1.5707963267949 REALS[33] JMP MQ_seg_lbl_atan2_done_40
            if tag("REALS[913]") == 0.0:
                if tag("REALS[912]") < 0.0:
                    set_tag("REALS[33]", -1.5707963267949)
            if tag("REALS[913]") == 0.0:
                if tag("REALS[912]") < 0.0:
                    _pc = 486
                    continue
            _pc = 485
            continue
        elif _pc == 485:
            # rung 485
            # MOV 0.0 REALS[33]
            set_tag("REALS[33]", 0.0)
            _pc = 486
            continue
        elif _pc == 486:
            # rung 486
            # LBL MQ_seg_lbl_atan2_done_40 CPT REALS[914] SegQueue[idx_2].XY[1]-REALS[30]
            set_tag("REALS[914]", formula("SegQueue[idx_2].XY[1]-REALS[30]"))
            _pc = 487
            continue
        elif _pc == 487:
            # rung 487
            # CPT REALS[915] SegQueue[idx_2].XY[0]-REALS[29]
            set_tag("REALS[915]", formula("SegQueue[idx_2].XY[0]-REALS[29]"))
            _pc = 488
            continue
        elif _pc == 488:
            # rung 488
            # GRT REALS[915] 0.0 CPT REALS[34] ATN(REALS[914]/REALS[915]) JMP MQ_seg_lbl_atan2_done_41
            if tag("REALS[915]") > 0.0:
                set_tag("REALS[34]", formula("ATN(REALS[914]/REALS[915])"))
            if tag("REALS[915]") > 0.0:
                _pc = 494
                continue
            _pc = 489
            continue
        elif _pc == 489:
            # rung 489
            # LES REALS[915] 0.0 GEQ REALS[914] 0.0 CPT REALS[34] ATN(REALS[914]/REALS[915])+3.14159265358979 JMP MQ_seg_lbl_atan2_done_41
            if tag("REALS[915]") < 0.0:
                if tag("REALS[914]") >= 0.0:
                    set_tag(
                        "REALS[34]",
                        formula("ATN(REALS[914]/REALS[915])+3.14159265358979"),
                    )
            if tag("REALS[915]") < 0.0:
                if tag("REALS[914]") >= 0.0:
                    _pc = 494
                    continue
            _pc = 490
            continue
        elif _pc == 490:
            # rung 490
            # LES REALS[915] 0.0 LES REALS[914] 0.0 CPT REALS[34] ATN(REALS[914]/REALS[915])-3.14159265358979 JMP MQ_seg_lbl_atan2_done_41
            if tag("REALS[915]") < 0.0:
                if tag("REALS[914]") < 0.0:
                    set_tag(
                        "REALS[34]",
                        formula("ATN(REALS[914]/REALS[915])-3.14159265358979"),
                    )
            if tag("REALS[915]") < 0.0:
                if tag("REALS[914]") < 0.0:
                    _pc = 494
                    continue
            _pc = 491
            continue
        elif _pc == 491:
            # rung 491
            # EQU REALS[915] 0.0 GRT REALS[914] 0.0 MOV 1.5707963267949 REALS[34] JMP MQ_seg_lbl_atan2_done_41
            if tag("REALS[915]") == 0.0:
                if tag("REALS[914]") > 0.0:
                    set_tag("REALS[34]", 1.5707963267949)
            if tag("REALS[915]") == 0.0:
                if tag("REALS[914]") > 0.0:
                    _pc = 494
                    continue
            _pc = 492
            continue
        elif _pc == 492:
            # rung 492
            # EQU REALS[915] 0.0 LES REALS[914] 0.0 MOV -1.5707963267949 REALS[34] JMP MQ_seg_lbl_atan2_done_41
            if tag("REALS[915]") == 0.0:
                if tag("REALS[914]") < 0.0:
                    set_tag("REALS[34]", -1.5707963267949)
            if tag("REALS[915]") == 0.0:
                if tag("REALS[914]") < 0.0:
                    _pc = 494
                    continue
            _pc = 493
            continue
        elif _pc == 493:
            # rung 493
            # MOV 0.0 REALS[34]
            set_tag("REALS[34]", 0.0)
            _pc = 494
            continue
        elif _pc == 494:
            # rung 494
            # LBL MQ_seg_lbl_atan2_done_41 MOV REALS[33] REALS[14]
            set_tag("REALS[14]", tag("REALS[33]"))
            _pc = 495
            continue
        elif _pc == 495:
            # rung 495
            # MOV REALS[34] REALS[15]
            set_tag("REALS[15]", tag("REALS[34]"))
            _pc = 496
            continue
        elif _pc == 496:
            # rung 496
            # MOV SegQueue[idx_2].Direction DINTS[4]
            set_tag("DINTS[4]", tag("SegQueue[idx_2].Direction"))
            _pc = 497
            continue
        elif _pc == 497:
            # rung 497
            # CPT REALS[17] 2.0*3.14159265358979
            set_tag("REALS[17]", formula("2.0*3.14159265358979"))
            _pc = 498
            continue
        elif _pc == 498:
            # rung 498
            # CPT REALS[910] REALS[15]-REALS[14]
            set_tag("REALS[910]", formula("REALS[15]-REALS[14]"))
            _pc = 499
            continue
        elif _pc == 499:
            # rung 499
            # MOD REALS[910] REALS[17] REALS[18]
            set_tag("REALS[18]", fmod(tag("REALS[910]"), tag("REALS[17]")))
            _pc = 500
            continue
        elif _pc == 500:
            # rung 500
            # CPT REALS[911] REALS[14]-REALS[15]
            set_tag("REALS[911]", formula("REALS[14]-REALS[15]"))
            _pc = 501
            continue
        elif _pc == 501:
            # rung 501
            # MOD REALS[911] REALS[17] REALS[19]
            set_tag("REALS[19]", fmod(tag("REALS[911]"), tag("REALS[17]")))
            _pc = 502
            continue
        elif _pc == 502:
            # rung 502
            # NEQ DINTS[4] 0 JMP MQ_arc_lbl_else_18
            if tag("DINTS[4]") != 0:
                _pc = 505
                continue
            _pc = 503
            continue
        elif _pc == 503:
            # rung 503
            # CPT REALS[16] -REALS[19]
            set_tag("REALS[16]", formula("-REALS[19]"))
            _pc = 504
            continue
        elif _pc == 504:
            # rung 504
            # JMP MQ_arc_lbl_ArcSweepRad_end
            _pc = 516
            continue
            _pc = 505
            continue
        elif _pc == 505:
            # rung 505
            # LBL MQ_arc_lbl_else_18 NEQ DINTS[4] 1 JMP MQ_arc_lbl_else_20
            if tag("DINTS[4]") != 1:
                _pc = 508
                continue
            _pc = 506
            continue
        elif _pc == 506:
            # rung 506
            # MOV REALS[18] REALS[16]
            set_tag("REALS[16]", tag("REALS[18]"))
            _pc = 507
            continue
        elif _pc == 507:
            # rung 507
            # JMP MQ_arc_lbl_ArcSweepRad_end
            _pc = 516
            continue
            _pc = 508
            continue
        elif _pc == 508:
            # rung 508
            # LBL MQ_arc_lbl_else_20 NEQ DINTS[4] 2 JMP MQ_arc_lbl_else_22
            if tag("DINTS[4]") != 2:
                _pc = 511
                continue
            _pc = 509
            continue
        elif _pc == 509:
            # rung 509
            # CPT REALS[16] -REALS[19]
            set_tag("REALS[16]", formula("-REALS[19]"))
            _pc = 510
            continue
        elif _pc == 510:
            # rung 510
            # JMP MQ_arc_lbl_ArcSweepRad_end
            _pc = 516
            continue
            _pc = 511
            continue
        elif _pc == 511:
            # rung 511
            # LBL MQ_arc_lbl_else_22 NEQ DINTS[4] 3 JMP MQ_arc_lbl_else_24
            if tag("DINTS[4]") != 3:
                _pc = 514
                continue
            _pc = 512
            continue
        elif _pc == 512:
            # rung 512
            # MOV REALS[18] REALS[16]
            set_tag("REALS[16]", tag("REALS[18]"))
            _pc = 513
            continue
        elif _pc == 513:
            # rung 513
            # JMP MQ_arc_lbl_ArcSweepRad_end
            _pc = 516
            continue
            _pc = 514
            continue
        elif _pc == 514:
            # rung 514
            # LBL MQ_arc_lbl_else_24 OTU BOOLS[3]
            set_tag("BOOLS[3]", False)
            _pc = 515
            continue
        elif _pc == 515:
            # rung 515
            # JMP MQ_arc_lbl_ArcSweepRad_end
            _pc = 516
            continue
            _pc = 516
            continue
        elif _pc == 516:
            # rung 516
            # LBL MQ_arc_lbl_ArcSweepRad_end NOP
            NOP()
            _pc = 517
            continue
        elif _pc == 517:
            # rung 517
            # MOV REALS[16] REALS[35]
            set_tag("REALS[35]", tag("REALS[16]"))
            _pc = 518
            continue
        elif _pc == 518:
            # rung 518
            # XIC BOOLS[3] OTL BOOLS[6]
            if tag("BOOLS[3]"):
                set_tag("BOOLS[6]", True)
            _pc = 519
            continue
        elif _pc == 519:
            # rung 519
            # XIO BOOLS[3] OTU BOOLS[6]
            if not tag("BOOLS[3]"):
                set_tag("BOOLS[6]", False)
            _pc = 520
            continue
        elif _pc == 520:
            # rung 520
            # XIO BOOLS[6] JMP MQ_seg_lbl_else_42
            if not tag("BOOLS[6]"):
                _pc = 582
                continue
            _pc = 521
            continue
        elif _pc == 521:
            # rung 521
            # MOV REALS[33] REALS[0]
            set_tag("REALS[0]", tag("REALS[33]"))
            _pc = 522
            continue
        elif _pc == 522:
            # rung 522
            # MOV REALS[35] REALS[1]
            set_tag("REALS[1]", tag("REALS[35]"))
            _pc = 523
            continue
        elif _pc == 523:
            # rung 523
            # CPT REALS[3] REALS[0]+REALS[1]
            set_tag("REALS[3]", formula("REALS[0]+REALS[1]"))
            _pc = 524
            continue
        elif _pc == 524:
            # rung 524
            # LES REALS[0] REALS[3] JMP MQ_sin_lbl_min_a_0
            if tag("REALS[0]") < tag("REALS[3]"):
                _pc = 526
                continue
            _pc = 525
            continue
        elif _pc == 525:
            # rung 525
            # MOV REALS[3] REALS[4] JMP MQ_sin_lbl_min_end_1
            set_tag("REALS[4]", tag("REALS[3]"))
            _pc = 527
            continue
            _pc = 526
            continue
        elif _pc == 526:
            # rung 526
            # LBL MQ_sin_lbl_min_a_0 MOV REALS[0] REALS[4]
            set_tag("REALS[4]", tag("REALS[0]"))
            _pc = 527
            continue
        elif _pc == 527:
            # rung 527
            # LBL MQ_sin_lbl_min_end_1 GRT REALS[0] REALS[3] JMP MQ_sin_lbl_max_a_2
            if tag("REALS[0]") > tag("REALS[3]"):
                _pc = 529
                continue
            _pc = 528
            continue
        elif _pc == 528:
            # rung 528
            # MOV REALS[3] REALS[5] JMP MQ_sin_lbl_max_end_3
            set_tag("REALS[5]", tag("REALS[3]"))
            _pc = 530
            continue
            _pc = 529
            continue
        elif _pc == 529:
            # rung 529
            # LBL MQ_sin_lbl_max_a_2 MOV REALS[0] REALS[5]
            set_tag("REALS[5]", tag("REALS[0]"))
            _pc = 530
            continue
        elif _pc == 530:
            # rung 530
            # LBL MQ_sin_lbl_max_end_3 CPT REALS[900] ABS(SIN(REALS[0]))
            set_tag("REALS[900]", formula("ABS(SIN(REALS[0]))"))
            _pc = 531
            continue
        elif _pc == 531:
            # rung 531
            # CPT REALS[901] ABS(SIN(REALS[3]))
            set_tag("REALS[901]", formula("ABS(SIN(REALS[3]))"))
            _pc = 532
            continue
        elif _pc == 532:
            # rung 532
            # GRT REALS[900] REALS[901] JMP MQ_sin_lbl_max_a_4
            if tag("REALS[900]") > tag("REALS[901]"):
                _pc = 534
                continue
            _pc = 533
            continue
        elif _pc == 533:
            # rung 533
            # MOV REALS[901] REALS[6] JMP MQ_sin_lbl_max_end_5
            set_tag("REALS[6]", tag("REALS[901]"))
            _pc = 535
            continue
            _pc = 534
            continue
        elif _pc == 534:
            # rung 534
            # LBL MQ_sin_lbl_max_a_4 MOV REALS[900] REALS[6]
            set_tag("REALS[6]", tag("REALS[900]"))
            _pc = 535
            continue
        elif _pc == 535:
            # rung 535
            # LBL MQ_sin_lbl_max_end_5 CPT REALS[902] REALS[4]-0.5*3.14159265358979/3.14159265358979
            set_tag(
                "REALS[902]", formula("REALS[4]-0.5*3.14159265358979/3.14159265358979")
            )
            _pc = 536
            continue
        elif _pc == 536:
            # rung 536
            # TRN REALS[902] DINTS[900]
            set_tag("DINTS[900]", trunc(tag("REALS[902]")))
            _pc = 537
            continue
        elif _pc == 537:
            # rung 537
            # MOV DINTS[900] REALS[903]
            set_tag("REALS[903]", tag("DINTS[900]"))
            _pc = 538
            continue
        elif _pc == 538:
            # rung 538
            # GEQ REALS[903] REALS[902] JMP MQ_sin_lbl_ceil_done_6
            if tag("REALS[903]") >= tag("REALS[902]"):
                _pc = 540
                continue
            _pc = 539
            continue
        elif _pc == 539:
            # rung 539
            # ADD DINTS[900] 1 DINTS[900]
            set_tag("DINTS[900]", tag("DINTS[900]") + 1)
            _pc = 540
            continue
        elif _pc == 540:
            # rung 540
            # LBL MQ_sin_lbl_ceil_done_6 MOV DINTS[900] DINTS[0]
            set_tag("DINTS[0]", tag("DINTS[900]"))
            _pc = 541
            continue
        elif _pc == 541:
            # rung 541
            # CPT REALS[904] REALS[5]-0.5*3.14159265358979/3.14159265358979
            set_tag(
                "REALS[904]", formula("REALS[5]-0.5*3.14159265358979/3.14159265358979")
            )
            _pc = 542
            continue
        elif _pc == 542:
            # rung 542
            # TRN REALS[904] DINTS[1]
            set_tag("DINTS[1]", trunc(tag("REALS[904]")))
            _pc = 543
            continue
        elif _pc == 543:
            # rung 543
            # GRT DINTS[0] DINTS[1] JMP MQ_sin_lbl_else_7
            if tag("DINTS[0]") > tag("DINTS[1]"):
                _pc = 546
                continue
            _pc = 544
            continue
        elif _pc == 544:
            # rung 544
            # MOV 1.0 REALS[2]
            set_tag("REALS[2]", 1.0)
            _pc = 545
            continue
        elif _pc == 545:
            # rung 545
            # JMP MQ_sin_lbl_MaxAbsSinSweep_end
            _pc = 548
            continue
            _pc = 546
            continue
        elif _pc == 546:
            # rung 546
            # LBL MQ_sin_lbl_else_7 MOV REALS[6] REALS[2]
            set_tag("REALS[2]", tag("REALS[6]"))
            _pc = 547
            continue
        elif _pc == 547:
            # rung 547
            # JMP MQ_sin_lbl_MaxAbsSinSweep_end
            _pc = 548
            continue
            _pc = 548
            continue
        elif _pc == 548:
            # rung 548
            # LBL MQ_sin_lbl_MaxAbsSinSweep_end NOP
            NOP()
            _pc = 549
            continue
        elif _pc == 549:
            # rung 549
            # MOV REALS[2] REALS[36]
            set_tag("REALS[36]", tag("REALS[2]"))
            _pc = 550
            continue
        elif _pc == 550:
            # rung 550
            # MOV REALS[33] REALS[7]
            set_tag("REALS[7]", tag("REALS[33]"))
            _pc = 551
            continue
        elif _pc == 551:
            # rung 551
            # MOV REALS[35] REALS[8]
            set_tag("REALS[8]", tag("REALS[35]"))
            _pc = 552
            continue
        elif _pc == 552:
            # rung 552
            # CPT REALS[10] REALS[7]+REALS[8]
            set_tag("REALS[10]", formula("REALS[7]+REALS[8]"))
            _pc = 553
            continue
        elif _pc == 553:
            # rung 553
            # LES REALS[7] REALS[10] JMP MQ_cos_lbl_min_a_9
            if tag("REALS[7]") < tag("REALS[10]"):
                _pc = 555
                continue
            _pc = 554
            continue
        elif _pc == 554:
            # rung 554
            # MOV REALS[10] REALS[11] JMP MQ_cos_lbl_min_end_10
            set_tag("REALS[11]", tag("REALS[10]"))
            _pc = 556
            continue
            _pc = 555
            continue
        elif _pc == 555:
            # rung 555
            # LBL MQ_cos_lbl_min_a_9 MOV REALS[7] REALS[11]
            set_tag("REALS[11]", tag("REALS[7]"))
            _pc = 556
            continue
        elif _pc == 556:
            # rung 556
            # LBL MQ_cos_lbl_min_end_10 GRT REALS[7] REALS[10] JMP MQ_cos_lbl_max_a_11
            if tag("REALS[7]") > tag("REALS[10]"):
                _pc = 558
                continue
            _pc = 557
            continue
        elif _pc == 557:
            # rung 557
            # MOV REALS[10] REALS[12] JMP MQ_cos_lbl_max_end_12
            set_tag("REALS[12]", tag("REALS[10]"))
            _pc = 559
            continue
            _pc = 558
            continue
        elif _pc == 558:
            # rung 558
            # LBL MQ_cos_lbl_max_a_11 MOV REALS[7] REALS[12]
            set_tag("REALS[12]", tag("REALS[7]"))
            _pc = 559
            continue
        elif _pc == 559:
            # rung 559
            # LBL MQ_cos_lbl_max_end_12 CPT REALS[905] ABS(COS(REALS[7]))
            set_tag("REALS[905]", formula("ABS(COS(REALS[7]))"))
            _pc = 560
            continue
        elif _pc == 560:
            # rung 560
            # CPT REALS[906] ABS(COS(REALS[10]))
            set_tag("REALS[906]", formula("ABS(COS(REALS[10]))"))
            _pc = 561
            continue
        elif _pc == 561:
            # rung 561
            # GRT REALS[905] REALS[906] JMP MQ_cos_lbl_max_a_13
            if tag("REALS[905]") > tag("REALS[906]"):
                _pc = 563
                continue
            _pc = 562
            continue
        elif _pc == 562:
            # rung 562
            # MOV REALS[906] REALS[13] JMP MQ_cos_lbl_max_end_14
            set_tag("REALS[13]", tag("REALS[906]"))
            _pc = 564
            continue
            _pc = 563
            continue
        elif _pc == 563:
            # rung 563
            # LBL MQ_cos_lbl_max_a_13 MOV REALS[905] REALS[13]
            set_tag("REALS[13]", tag("REALS[905]"))
            _pc = 564
            continue
        elif _pc == 564:
            # rung 564
            # LBL MQ_cos_lbl_max_end_14 CPT REALS[907] REALS[11]/3.14159265358979
            set_tag("REALS[907]", formula("REALS[11]/3.14159265358979"))
            _pc = 565
            continue
        elif _pc == 565:
            # rung 565
            # TRN REALS[907] DINTS[901]
            set_tag("DINTS[901]", trunc(tag("REALS[907]")))
            _pc = 566
            continue
        elif _pc == 566:
            # rung 566
            # MOV DINTS[901] REALS[908]
            set_tag("REALS[908]", tag("DINTS[901]"))
            _pc = 567
            continue
        elif _pc == 567:
            # rung 567
            # GEQ REALS[908] REALS[907] JMP MQ_cos_lbl_ceil_done_15
            if tag("REALS[908]") >= tag("REALS[907]"):
                _pc = 569
                continue
            _pc = 568
            continue
        elif _pc == 568:
            # rung 568
            # ADD DINTS[901] 1 DINTS[901]
            set_tag("DINTS[901]", tag("DINTS[901]") + 1)
            _pc = 569
            continue
        elif _pc == 569:
            # rung 569
            # LBL MQ_cos_lbl_ceil_done_15 MOV DINTS[901] DINTS[2]
            set_tag("DINTS[2]", tag("DINTS[901]"))
            _pc = 570
            continue
        elif _pc == 570:
            # rung 570
            # CPT REALS[909] REALS[12]/3.14159265358979
            set_tag("REALS[909]", formula("REALS[12]/3.14159265358979"))
            _pc = 571
            continue
        elif _pc == 571:
            # rung 571
            # TRN REALS[909] DINTS[3]
            set_tag("DINTS[3]", trunc(tag("REALS[909]")))
            _pc = 572
            continue
        elif _pc == 572:
            # rung 572
            # GRT DINTS[2] DINTS[3] JMP MQ_cos_lbl_else_16
            if tag("DINTS[2]") > tag("DINTS[3]"):
                _pc = 575
                continue
            _pc = 573
            continue
        elif _pc == 573:
            # rung 573
            # MOV 1.0 REALS[9]
            set_tag("REALS[9]", 1.0)
            _pc = 574
            continue
        elif _pc == 574:
            # rung 574
            # JMP MQ_cos_lbl_MaxAbsCosSweep_end
            _pc = 577
            continue
            _pc = 575
            continue
        elif _pc == 575:
            # rung 575
            # LBL MQ_cos_lbl_else_16 MOV REALS[13] REALS[9]
            set_tag("REALS[9]", tag("REALS[13]"))
            _pc = 576
            continue
        elif _pc == 576:
            # rung 576
            # JMP MQ_cos_lbl_MaxAbsCosSweep_end
            _pc = 577
            continue
            _pc = 577
            continue
        elif _pc == 577:
            # rung 577
            # LBL MQ_cos_lbl_MaxAbsCosSweep_end NOP
            NOP()
            _pc = 578
            continue
        elif _pc == 578:
            # rung 578
            # MOV REALS[9] REALS[37]
            set_tag("REALS[37]", tag("REALS[9]"))
            _pc = 579
            continue
        elif _pc == 579:
            # rung 579
            # MOV REALS[36] REALS[22]
            set_tag("REALS[22]", tag("REALS[36]"))
            _pc = 580
            continue
        elif _pc == 580:
            # rung 580
            # MOV REALS[37] REALS[23]
            set_tag("REALS[23]", tag("REALS[37]"))
            _pc = 581
            continue
        elif _pc == 581:
            # rung 581
            # JMP MQ_seg_lbl_SegTangentBounds_end
            _pc = 595
            continue
            _pc = 582
            continue
        elif _pc == 582:
            # rung 582
            # LBL MQ_seg_lbl_else_42 NOP
            NOP()
            _pc = 583
            continue
        elif _pc == 583:
            # rung 583
            # LBL MQ_seg_lbl_else_38 NOP
            NOP()
            _pc = 584
            continue
        elif _pc == 584:
            # rung 584
            # LBL MQ_seg_lbl_else_36 NOP
            NOP()
            _pc = 585
            continue
        elif _pc == 585:
            # rung 585
            # LBL MQ_seg_lbl_else_34 CPT REALS[24] SegQueue[idx_2].XY[0]-REALS[20]
            set_tag("REALS[24]", formula("SegQueue[idx_2].XY[0]-REALS[20]"))
            _pc = 586
            continue
        elif _pc == 586:
            # rung 586
            # CPT REALS[25] SegQueue[idx_2].XY[1]-REALS[21]
            set_tag("REALS[25]", formula("SegQueue[idx_2].XY[1]-REALS[21]"))
            _pc = 587
            continue
        elif _pc == 587:
            # rung 587
            # CPT REALS[26] SQR(REALS[24]*REALS[24]+REALS[25]*REALS[25])
            set_tag(
                "REALS[26]", formula("SQR(REALS[24]*REALS[24]+REALS[25]*REALS[25])")
            )
            _pc = 588
            continue
        elif _pc == 588:
            # rung 588
            # GRT REALS[26] 0.000000001 JMP MQ_seg_lbl_else_44
            if tag("REALS[26]") > 0.000000001:
                _pc = 592
                continue
            _pc = 589
            continue
        elif _pc == 589:
            # rung 589
            # MOV 0.0 REALS[22]
            set_tag("REALS[22]", 0.0)
            _pc = 590
            continue
        elif _pc == 590:
            # rung 590
            # MOV 0.0 REALS[23]
            set_tag("REALS[23]", 0.0)
            _pc = 591
            continue
        elif _pc == 591:
            # rung 591
            # JMP MQ_seg_lbl_SegTangentBounds_end
            _pc = 595
            continue
            _pc = 592
            continue
        elif _pc == 592:
            # rung 592
            # LBL MQ_seg_lbl_else_44 CPT REALS[22] ABS(REALS[24]/REALS[26])
            set_tag("REALS[22]", formula("ABS(REALS[24]/REALS[26])"))
            _pc = 593
            continue
        elif _pc == 593:
            # rung 593
            # CPT REALS[23] ABS(REALS[25]/REALS[26])
            set_tag("REALS[23]", formula("ABS(REALS[25]/REALS[26])"))
            _pc = 594
            continue
        elif _pc == 594:
            # rung 594
            # JMP MQ_seg_lbl_SegTangentBounds_end
            _pc = 595
            continue
            _pc = 595
            continue
        elif _pc == 595:
            # rung 595
            # LBL MQ_seg_lbl_SegTangentBounds_end NOP
            NOP()
            _pc = 596
            continue
        elif _pc == 596:
            # rung 596
            # MOV REALS[22] REALS[45]
            set_tag("REALS[45]", tag("REALS[22]"))
            _pc = 597
            continue
        elif _pc == 597:
            # rung 597
            # MOV REALS[23] REALS[46]
            set_tag("REALS[46]", tag("REALS[23]"))
            _pc = 598
            continue
        elif _pc == 598:
            # rung 598
            # GRT REALS[45] 0.000000001 JMP MQ_cap_lbl_else_60
            if tag("REALS[45]") > 0.000000001:
                _pc = 601
                continue
            _pc = 599
            continue
        elif _pc == 599:
            # rung 599
            # MOV 3.4028235E+38 REALS[47]
            set_tag("REALS[47]", 3.4028235e38)
            _pc = 600
            continue
        elif _pc == 600:
            # rung 600
            # JMP MQ_cap_lbl_end_61
            _pc = 602
            continue
            _pc = 601
            continue
        elif _pc == 601:
            # rung 601
            # LBL MQ_cap_lbl_else_60 CPT REALS[47] REALS[38]/REALS[45]
            set_tag("REALS[47]", formula("REALS[38]/REALS[45]"))
            _pc = 602
            continue
        elif _pc == 602:
            # rung 602
            # LBL MQ_cap_lbl_end_61 GRT REALS[46] 0.000000001 JMP MQ_cap_lbl_else_62
            if tag("REALS[46]") > 0.000000001:
                _pc = 605
                continue
            _pc = 603
            continue
        elif _pc == 603:
            # rung 603
            # MOV 3.4028235E+38 REALS[48]
            set_tag("REALS[48]", 3.4028235e38)
            _pc = 604
            continue
        elif _pc == 604:
            # rung 604
            # JMP MQ_cap_lbl_end_63
            _pc = 606
            continue
            _pc = 605
            continue
        elif _pc == 605:
            # rung 605
            # LBL MQ_cap_lbl_else_62 CPT REALS[48] REALS[39]/REALS[46]
            set_tag("REALS[48]", formula("REALS[39]/REALS[46]"))
            _pc = 606
            continue
        elif _pc == 606:
            # rung 606
            # LBL MQ_cap_lbl_end_63 LES REALS[47] REALS[48] JMP MQ_cap_lbl_min_a_64
            if tag("REALS[47]") < tag("REALS[48]"):
                _pc = 608
                continue
            _pc = 607
            continue
        elif _pc == 607:
            # rung 607
            # MOV REALS[48] REALS[44] JMP MQ_cap_lbl_min_end_65
            set_tag("REALS[44]", tag("REALS[48]"))
            _pc = 609
            continue
            _pc = 608
            continue
        elif _pc == 608:
            # rung 608
            # LBL MQ_cap_lbl_min_a_64 MOV REALS[47] REALS[44]
            set_tag("REALS[44]", tag("REALS[47]"))
            _pc = 609
            continue
        elif _pc == 609:
            # rung 609
            # LBL MQ_cap_lbl_min_end_65 NOP
            NOP()
            _pc = 610
            continue
        elif _pc == 610:
            # rung 610
            # LBL MQ_cap_lbl_end_57 LES SegQueue[idx_3].Speed REALS[44] JMP MQ_cap_lbl_min_a_66
            if tag("SegQueue[idx_3].Speed") < tag("REALS[44]"):
                _pc = 612
                continue
            _pc = 611
            continue
        elif _pc == 611:
            # rung 611
            # MOV REALS[44] REALS[49] JMP MQ_cap_lbl_min_end_67
            set_tag("REALS[49]", tag("REALS[44]"))
            _pc = 613
            continue
            _pc = 612
            continue
        elif _pc == 612:
            # rung 612
            # LBL MQ_cap_lbl_min_a_66 MOV SegQueue[idx_3].Speed REALS[49]
            set_tag("REALS[49]", tag("SegQueue[idx_3].Speed"))
            _pc = 613
            continue
        elif _pc == 613:
            # rung 613
            # LBL MQ_cap_lbl_min_end_67 GRT REALS[49] 0.0 JMP MQ_cap_lbl_else_68
            if tag("REALS[49]") > 0.0:
                _pc = 616
                continue
            _pc = 614
            continue
        elif _pc == 614:
            # rung 614
            # OTL BOOLS[8]
            set_tag("BOOLS[8]", True)
            _pc = 615
            continue
        elif _pc == 615:
            # rung 615
            # JMP MQ_cap_lbl_CapSegSpeed_end
            _pc = 622
            continue
            _pc = 616
            continue
        elif _pc == 616:
            # rung 616
            # LBL MQ_cap_lbl_else_68 MOV REALS[49] SegQueue[idx_3].Speed
            set_tag("SegQueue[idx_3].Speed", tag("REALS[49]"))
            _pc = 617
            continue
        elif _pc == 617:
            # rung 617
            # MOV SegQueue[idx_3].XY[0] REALS[42]
            set_tag("REALS[42]", tag("SegQueue[idx_3].XY[0]"))
            _pc = 618
            continue
        elif _pc == 618:
            # rung 618
            # MOV SegQueue[idx_3].XY[1] REALS[43]
            set_tag("REALS[43]", tag("SegQueue[idx_3].XY[1]"))
            _pc = 619
            continue
        elif _pc == 619:
            # rung 619
            # ADD idx_3 1 idx_3
            set_tag("idx_3", tag("idx_3") + 1)
            _pc = 620
            continue
        elif _pc == 620:
            # rung 620
            # JMP MQ_cap_lbl_loop_54
            _pc = 447
            continue
            _pc = 621
            continue
        elif _pc == 621:
            # rung 621
            # LBL MQ_cap_lbl_loop_end_55 JMP MQ_cap_lbl_CapSegSpeed_end
            _pc = 622
            continue
            _pc = 622
            continue
        elif _pc == 622:
            # rung 622
            # LBL MQ_cap_lbl_CapSegSpeed_end NOP
            NOP()
            _pc = 623
            continue
        elif _pc == 623:
            # rung 623
            # XIC StartQueuedPath BST BST XIO Z_RETRACTED NXB GEQ Z_axis.ActualPosition MAX_TOLERABLE_Z BND CPT ERROR_CODE 3001 CPT NEXTSTATE 10 NXB XIC Z_RETRACTED XIO APA_IS_VERTICAL CPT ERROR_CODE 3005 CPT NEXTSTATE 10 BND OTE AbortQueue OTU StartQueuedPath
            _branch_586 = bool(not tag("Z_RETRACTED"))
            _branch_588 = bool(tag("Z_axis.ActualPosition") >= tag("MAX_TOLERABLE_Z"))
            _branch_590 = _branch_586 or _branch_588
            if tag("StartQueuedPath"):
                if _branch_590:
                    set_tag("ERROR_CODE", formula("3001"))
            if tag("StartQueuedPath"):
                if _branch_590:
                    set_tag("NEXTSTATE", formula("10"))
            _branch_591 = bool(_branch_590)
            if tag("StartQueuedPath"):
                if tag("Z_RETRACTED"):
                    if not tag("APA_IS_VERTICAL"):
                        set_tag("ERROR_CODE", formula("3005"))
            if tag("StartQueuedPath"):
                if tag("Z_RETRACTED"):
                    if not tag("APA_IS_VERTICAL"):
                        set_tag("NEXTSTATE", formula("10"))
            _branch_593 = bool((tag("Z_RETRACTED")) and (not tag("APA_IS_VERTICAL")))
            _branch_595 = _branch_591 or _branch_593
            set_tag("AbortQueue", bool((tag("StartQueuedPath")) and (_branch_595)))
            if tag("StartQueuedPath"):
                if _branch_595:
                    set_tag("StartQueuedPath", False)
            _pc = 624
            continue
        elif _pc == 624:
            # rung 624
            # XIC StartQueuedPath XIO CurIssued XIO QueueFault GEQ QueueCtl.POS 1 ONS StartCurONS OTL LoadCurReq
            _pulse_596 = ONS(
                storage_bit="StartCurONS",
                rung_in=(tag("StartQueuedPath"))
                and (not tag("CurIssued"))
                and (not tag("QueueFault"))
                and (tag("QueueCtl.POS") >= 1),
            )
            if _pulse_596:
                set_tag("LoadCurReq", True)
            _pc = 625
            continue
        elif _pc == 625:
            # rung 625
            # XIC LoadCurReq OTU StartQueuedPath
            if tag("LoadCurReq"):
                set_tag("StartQueuedPath", False)
            _pc = 626
            continue
        elif _pc == 626:
            # rung 626
            # XIC LoadCurReq FFU SegQueue[0] CurSeg QueueCtl 32 0
            FFU(
                array="SegQueue[0]",
                dest="CurSeg",
                control="QueueCtl",
                length=32,
                position=0,
                rung_in=tag("LoadCurReq"),
            )
            _pc = 627
            continue
        elif _pc == 627:
            # rung 627
            # XIC LoadCurReq OTL CheckCurSeg
            if tag("LoadCurReq"):
                set_tag("CheckCurSeg", True)
            _pc = 628
            continue
        elif _pc == 628:
            # rung 628
            # XIC LoadCurReq OTU LoadCurReq
            if tag("LoadCurReq"):
                set_tag("LoadCurReq", False)
            _pc = 629
            continue
        elif _pc == 629:
            # rung 629
            # XIC PrepCurMove XIC UseAasCurrent COP CurSeg.XY[0] CmdA_XY[0] 2
            if tag("PrepCurMove"):
                if tag("UseAasCurrent"):
                    COP(
                        source="CurSeg.XY[0]",
                        dest="CmdA_XY[0]",
                        length=2,
                    )
            _pc = 630
            continue
        elif _pc == 630:
            # rung 630
            # XIC PrepCurMove XIC UseAasCurrent MOV CurSeg.Speed CmdA_Speed
            if tag("PrepCurMove"):
                if tag("UseAasCurrent"):
                    set_tag("CmdA_Speed", tag("CurSeg.Speed"))
            _pc = 631
            continue
        elif _pc == 631:
            # rung 631
            # XIC PrepCurMove XIC UseAasCurrent MOV CurSeg.Accel CmdA_Accel
            if tag("PrepCurMove"):
                if tag("UseAasCurrent"):
                    set_tag("CmdA_Accel", tag("CurSeg.Accel"))
            _pc = 632
            continue
        elif _pc == 632:
            # rung 632
            # XIC PrepCurMove XIC UseAasCurrent MOV CurSeg.Decel CmdA_Decel
            if tag("PrepCurMove"):
                if tag("UseAasCurrent"):
                    set_tag("CmdA_Decel", tag("CurSeg.Decel"))
            _pc = 633
            continue
        elif _pc == 633:
            # rung 633
            # XIC PrepCurMove XIC UseAasCurrent MOV CurSeg.JerkAccel CmdA_JerkAccel
            if tag("PrepCurMove"):
                if tag("UseAasCurrent"):
                    set_tag("CmdA_JerkAccel", tag("CurSeg.JerkAccel"))
            _pc = 634
            continue
        elif _pc == 634:
            # rung 634
            # XIC PrepCurMove XIC UseAasCurrent MOV CurSeg.JerkDecel CmdA_JerkDecel
            if tag("PrepCurMove"):
                if tag("UseAasCurrent"):
                    set_tag("CmdA_JerkDecel", tag("CurSeg.JerkDecel"))
            _pc = 635
            continue
        elif _pc == 635:
            # rung 635
            # XIC PrepCurMove XIC UseAasCurrent MOV CurSeg.TermType CmdA_TermType
            if tag("PrepCurMove"):
                if tag("UseAasCurrent"):
                    set_tag("CmdA_TermType", tag("CurSeg.TermType"))
            _pc = 636
            continue
        elif _pc == 636:
            # rung 636
            # XIC PrepCurMove XIC UseAasCurrent MOV CurSeg.SegType CmdA_SegType
            if tag("PrepCurMove"):
                if tag("UseAasCurrent"):
                    set_tag("CmdA_SegType", tag("CurSeg.SegType"))
            _pc = 637
            continue
        elif _pc == 637:
            # rung 637
            # XIC PrepCurMove XIC UseAasCurrent MOV CurSeg.CircleType CmdA_CircleType
            if tag("PrepCurMove"):
                if tag("UseAasCurrent"):
                    set_tag("CmdA_CircleType", tag("CurSeg.CircleType"))
            _pc = 638
            continue
        elif _pc == 638:
            # rung 638
            # XIC PrepCurMove XIC UseAasCurrent COP CurSeg.ViaCenter[0] CmdA_ViaCenter[0] 2
            if tag("PrepCurMove"):
                if tag("UseAasCurrent"):
                    COP(
                        source="CurSeg.ViaCenter[0]",
                        dest="CmdA_ViaCenter[0]",
                        length=2,
                    )
            _pc = 639
            continue
        elif _pc == 639:
            # rung 639
            # XIC PrepCurMove XIC UseAasCurrent MOV CurSeg.Direction CmdA_Direction
            if tag("PrepCurMove"):
                if tag("UseAasCurrent"):
                    set_tag("CmdA_Direction", tag("CurSeg.Direction"))
            _pc = 640
            continue
        elif _pc == 640:
            # rung 640
            # XIC PrepCurMove XIC UseAasCurrent MOV CurSeg.Seq ActiveSeq
            if tag("PrepCurMove"):
                if tag("UseAasCurrent"):
                    set_tag("ActiveSeq", tag("CurSeg.Seq"))
            _pc = 641
            continue
        elif _pc == 641:
            # rung 641
            # XIC PrepCurMove XIO UseAasCurrent COP CurSeg.XY[0] CmdB_XY[0] 2
            if tag("PrepCurMove"):
                if not tag("UseAasCurrent"):
                    COP(
                        source="CurSeg.XY[0]",
                        dest="CmdB_XY[0]",
                        length=2,
                    )
            _pc = 642
            continue
        elif _pc == 642:
            # rung 642
            # XIC PrepCurMove XIO UseAasCurrent MOV CurSeg.Speed CmdB_Speed
            if tag("PrepCurMove"):
                if not tag("UseAasCurrent"):
                    set_tag("CmdB_Speed", tag("CurSeg.Speed"))
            _pc = 643
            continue
        elif _pc == 643:
            # rung 643
            # XIC PrepCurMove XIO UseAasCurrent MOV CurSeg.Accel CmdB_Accel
            if tag("PrepCurMove"):
                if not tag("UseAasCurrent"):
                    set_tag("CmdB_Accel", tag("CurSeg.Accel"))
            _pc = 644
            continue
        elif _pc == 644:
            # rung 644
            # XIC PrepCurMove XIO UseAasCurrent MOV CurSeg.Decel CmdB_Decel
            if tag("PrepCurMove"):
                if not tag("UseAasCurrent"):
                    set_tag("CmdB_Decel", tag("CurSeg.Decel"))
            _pc = 645
            continue
        elif _pc == 645:
            # rung 645
            # XIC PrepCurMove XIO UseAasCurrent MOV CurSeg.JerkAccel CmdB_JerkAccel
            if tag("PrepCurMove"):
                if not tag("UseAasCurrent"):
                    set_tag("CmdB_JerkAccel", tag("CurSeg.JerkAccel"))
            _pc = 646
            continue
        elif _pc == 646:
            # rung 646
            # XIC PrepCurMove XIO UseAasCurrent MOV CurSeg.JerkDecel CmdB_JerkDecel
            if tag("PrepCurMove"):
                if not tag("UseAasCurrent"):
                    set_tag("CmdB_JerkDecel", tag("CurSeg.JerkDecel"))
            _pc = 647
            continue
        elif _pc == 647:
            # rung 647
            # XIC PrepCurMove XIO UseAasCurrent MOV CurSeg.TermType CmdB_TermType
            if tag("PrepCurMove"):
                if not tag("UseAasCurrent"):
                    set_tag("CmdB_TermType", tag("CurSeg.TermType"))
            _pc = 648
            continue
        elif _pc == 648:
            # rung 648
            # XIC PrepCurMove XIO UseAasCurrent MOV CurSeg.SegType CmdB_SegType
            if tag("PrepCurMove"):
                if not tag("UseAasCurrent"):
                    set_tag("CmdB_SegType", tag("CurSeg.SegType"))
            _pc = 649
            continue
        elif _pc == 649:
            # rung 649
            # XIC PrepCurMove XIO UseAasCurrent MOV CurSeg.CircleType CmdB_CircleType
            if tag("PrepCurMove"):
                if not tag("UseAasCurrent"):
                    set_tag("CmdB_CircleType", tag("CurSeg.CircleType"))
            _pc = 650
            continue
        elif _pc == 650:
            # rung 650
            # XIC PrepCurMove XIO UseAasCurrent COP CurSeg.ViaCenter[0] CmdB_ViaCenter[0] 2
            if tag("PrepCurMove"):
                if not tag("UseAasCurrent"):
                    COP(
                        source="CurSeg.ViaCenter[0]",
                        dest="CmdB_ViaCenter[0]",
                        length=2,
                    )
            _pc = 651
            continue
        elif _pc == 651:
            # rung 651
            # XIC PrepCurMove XIO UseAasCurrent MOV CurSeg.Direction CmdB_Direction
            if tag("PrepCurMove"):
                if not tag("UseAasCurrent"):
                    set_tag("CmdB_Direction", tag("CurSeg.Direction"))
            _pc = 652
            continue
        elif _pc == 652:
            # rung 652
            # XIC PrepCurMove XIO UseAasCurrent MOV CurSeg.Seq ActiveSeq
            if tag("PrepCurMove"):
                if not tag("UseAasCurrent"):
                    set_tag("ActiveSeq", tag("CurSeg.Seq"))
            _pc = 653
            continue
        elif _pc == 653:
            # rung 653
            # XIC PrepCurMove XIO APA_IS_VERTICAL MOV 3005 FaultCode CPT ERROR_CODE 3005 CPT NEXTSTATE 10 OTL QueueFault
            if tag("PrepCurMove"):
                if not tag("APA_IS_VERTICAL"):
                    set_tag("FaultCode", 3005)
            if tag("PrepCurMove"):
                if not tag("APA_IS_VERTICAL"):
                    set_tag("ERROR_CODE", formula("3005"))
            if tag("PrepCurMove"):
                if not tag("APA_IS_VERTICAL"):
                    set_tag("NEXTSTATE", formula("10"))
            if tag("PrepCurMove"):
                if not tag("APA_IS_VERTICAL"):
                    set_tag("QueueFault", True)
            _pc = 654
            continue
        elif _pc == 654:
            # rung 654
            # XIC PrepCurMove XIC APA_IS_VERTICAL XIC X_Y.PhysicalAxisFault MOV 3002 FaultCode CPT ERROR_CODE 3002 CPT NEXTSTATE 10 OTL QueueFault
            if tag("PrepCurMove"):
                if tag("APA_IS_VERTICAL"):
                    if tag("X_Y.PhysicalAxisFault"):
                        set_tag("FaultCode", 3002)
            if tag("PrepCurMove"):
                if tag("APA_IS_VERTICAL"):
                    if tag("X_Y.PhysicalAxisFault"):
                        set_tag("ERROR_CODE", formula("3002"))
            if tag("PrepCurMove"):
                if tag("APA_IS_VERTICAL"):
                    if tag("X_Y.PhysicalAxisFault"):
                        set_tag("NEXTSTATE", formula("10"))
            if tag("PrepCurMove"):
                if tag("APA_IS_VERTICAL"):
                    if tag("X_Y.PhysicalAxisFault"):
                        set_tag("QueueFault", True)
            _pc = 655
            continue
        elif _pc == 655:
            # rung 655
            # XIC PrepCurMove XIC APA_IS_VERTICAL XIO X_Y.PhysicalAxisFault XIC X_axis.DriveEnableStatus XIC Y_axis.DriveEnableStatus OTL IssueCurPulse
            if tag("PrepCurMove"):
                if tag("APA_IS_VERTICAL"):
                    if not tag("X_Y.PhysicalAxisFault"):
                        if tag("X_axis.DriveEnableStatus"):
                            if tag("Y_axis.DriveEnableStatus"):
                                set_tag("IssueCurPulse", True)
            _pc = 656
            continue
        elif _pc == 656:
            # rung 656
            # XIC PrepCurMove XIC APA_IS_VERTICAL XIO X_Y.PhysicalAxisFault BST XIO X_axis.DriveEnableStatus NXB XIO Y_axis.DriveEnableStatus BND OTL WaitCurAxisOn
            _branch_597 = bool(not tag("X_axis.DriveEnableStatus"))
            _branch_599 = bool(not tag("Y_axis.DriveEnableStatus"))
            _branch_601 = _branch_597 or _branch_599
            if tag("PrepCurMove"):
                if tag("APA_IS_VERTICAL"):
                    if not tag("X_Y.PhysicalAxisFault"):
                        if _branch_601:
                            set_tag("WaitCurAxisOn", True)
            _pc = 657
            continue
        elif _pc == 657:
            # rung 657
            # XIC PrepCurMove OTU PrepCurMove
            if tag("PrepCurMove"):
                set_tag("PrepCurMove", False)
            _pc = 658
            continue
        elif _pc == 658:
            # rung 658
            # XIC WaitCurAxisOn XIO APA_IS_VERTICAL MOV 3005 FaultCode CPT ERROR_CODE 3005 CPT NEXTSTATE 10 OTL QueueFault OTU WaitCurAxisOn
            if tag("WaitCurAxisOn"):
                if not tag("APA_IS_VERTICAL"):
                    set_tag("FaultCode", 3005)
            if tag("WaitCurAxisOn"):
                if not tag("APA_IS_VERTICAL"):
                    set_tag("ERROR_CODE", formula("3005"))
            if tag("WaitCurAxisOn"):
                if not tag("APA_IS_VERTICAL"):
                    set_tag("NEXTSTATE", formula("10"))
            if tag("WaitCurAxisOn"):
                if not tag("APA_IS_VERTICAL"):
                    set_tag("QueueFault", True)
            if tag("WaitCurAxisOn"):
                if not tag("APA_IS_VERTICAL"):
                    set_tag("WaitCurAxisOn", False)
            _pc = 659
            continue
        elif _pc == 659:
            # rung 659
            # XIC WaitCurAxisOn XIC APA_IS_VERTICAL XIC X_Y.PhysicalAxisFault MOV 3002 FaultCode CPT ERROR_CODE 3002 CPT NEXTSTATE 10 OTL QueueFault OTU WaitCurAxisOn
            if tag("WaitCurAxisOn"):
                if tag("APA_IS_VERTICAL"):
                    if tag("X_Y.PhysicalAxisFault"):
                        set_tag("FaultCode", 3002)
            if tag("WaitCurAxisOn"):
                if tag("APA_IS_VERTICAL"):
                    if tag("X_Y.PhysicalAxisFault"):
                        set_tag("ERROR_CODE", formula("3002"))
            if tag("WaitCurAxisOn"):
                if tag("APA_IS_VERTICAL"):
                    if tag("X_Y.PhysicalAxisFault"):
                        set_tag("NEXTSTATE", formula("10"))
            if tag("WaitCurAxisOn"):
                if tag("APA_IS_VERTICAL"):
                    if tag("X_Y.PhysicalAxisFault"):
                        set_tag("QueueFault", True)
            if tag("WaitCurAxisOn"):
                if tag("APA_IS_VERTICAL"):
                    if tag("X_Y.PhysicalAxisFault"):
                        set_tag("WaitCurAxisOn", False)
            _pc = 660
            continue
        elif _pc == 660:
            # rung 660
            # XIC WaitCurAxisOn XIC APA_IS_VERTICAL XIO X_Y.PhysicalAxisFault MSO X_axis MQ_x_axis_mso MSO Y_axis MQ_y_axis_mso
            if tag("WaitCurAxisOn"):
                if tag("APA_IS_VERTICAL"):
                    if not tag("X_Y.PhysicalAxisFault"):
                        MSO(
                            axis="X_axis",
                            motion_control="MQ_x_axis_mso",
                        )
            if tag("WaitCurAxisOn"):
                if tag("APA_IS_VERTICAL"):
                    if not tag("X_Y.PhysicalAxisFault"):
                        MSO(
                            axis="Y_axis",
                            motion_control="MQ_y_axis_mso",
                        )
            _pc = 661
            continue
        elif _pc == 661:
            # rung 661
            # XIC WaitCurAxisOn XIC APA_IS_VERTICAL XIO X_Y.PhysicalAxisFault XIC MQ_x_axis_mso.DN XIC MQ_y_axis_mso.DN OTL IssueCurPulse
            if tag("WaitCurAxisOn"):
                if tag("APA_IS_VERTICAL"):
                    if not tag("X_Y.PhysicalAxisFault"):
                        if tag("MQ_x_axis_mso.DN"):
                            if tag("MQ_y_axis_mso.DN"):
                                set_tag("IssueCurPulse", True)
            _pc = 662
            continue
        elif _pc == 662:
            # rung 662
            # XIC WaitCurAxisOn XIC APA_IS_VERTICAL XIO X_Y.PhysicalAxisFault XIC MQ_x_axis_mso.DN XIC MQ_y_axis_mso.DN OTU WaitCurAxisOn
            if tag("WaitCurAxisOn"):
                if tag("APA_IS_VERTICAL"):
                    if not tag("X_Y.PhysicalAxisFault"):
                        if tag("MQ_x_axis_mso.DN"):
                            if tag("MQ_y_axis_mso.DN"):
                                set_tag("WaitCurAxisOn", False)
            _pc = 663
            continue
        elif _pc == 663:
            # rung 663
            # XIC PrepCurMove OTU PrepCurMove
            if tag("PrepCurMove"):
                set_tag("PrepCurMove", False)
            _pc = 664
            continue
        elif _pc == 664:
            # rung 664
            # XIC IssueCurPulse XIC UseAasCurrent EQU CmdA_SegType 1 MCLM X_Y MoveA 0 CmdA_XY[0] CmdA_Speed "Units per sec" CmdA_Accel "Units per sec2" CmdA_Decel "Units per sec2" S-Curve CmdA_JerkAccel CmdA_JerkDecel "Units per sec3" CmdA_TermType Disabled Programmed CmdTolerance 0 None 0 0
            MCLM(
                coordinate_system="X_Y",
                motion_control="MoveA",
                move_type=0,
                target="CmdA_XY[0]",
                speed="CmdA_Speed",
                speed_units="Units per sec",
                accel="CmdA_Accel",
                accel_units="Units per sec2",
                decel="CmdA_Decel",
                decel_units="Units per sec2",
                profile="S-Curve",
                accel_jerk="CmdA_JerkAccel",
                decel_jerk="CmdA_JerkDecel",
                jerk_units="Units per sec3",
                termination_type="CmdA_TermType",
                merge="Disabled",
                merge_speed="Programmed",
                command_tolerance="CmdTolerance",
                lock_position=0,
                lock_direction="None",
                event_distance=0,
                calculated_data=0,
                rung_in=(tag("IssueCurPulse"))
                and (tag("UseAasCurrent"))
                and (tag("CmdA_SegType") == 1),
            )
            _pc = 665
            continue
        elif _pc == 665:
            # rung 665
            # XIC IssueCurPulse XIC UseAasCurrent EQU CmdA_SegType 2 MCCM X_Y MoveA 0 CmdA_XY[0] CmdA_CircleType CmdA_ViaCenter[0] CmdA_Direction CmdA_Speed "Units per sec" CmdA_Accel "Units per sec2" CmdA_Decel "Units per sec2" S-Curve CmdA_JerkAccel CmdA_JerkDecel "Units per sec3" CmdA_TermType Disabled Programmed CmdTolerance 0 None 0 0
            MCCM(
                coordinate_system="X_Y",
                motion_control="MoveA",
                move_type=0,
                end_position="CmdA_XY[0]",
                circle_type="CmdA_CircleType",
                via_or_center="CmdA_ViaCenter[0]",
                direction="CmdA_Direction",
                speed="CmdA_Speed",
                speed_units="Units per sec",
                accel="CmdA_Accel",
                accel_units="Units per sec2",
                decel="CmdA_Decel",
                decel_units="Units per sec2",
                profile="S-Curve",
                accel_jerk="CmdA_JerkAccel",
                decel_jerk="CmdA_JerkDecel",
                jerk_units="Units per sec3",
                termination_type="CmdA_TermType",
                merge="Disabled",
                merge_speed="Programmed",
                command_tolerance="CmdTolerance",
                lock_position=0,
                lock_direction="None",
                event_distance=0,
                calculated_data=0,
                rung_in=(tag("IssueCurPulse"))
                and (tag("UseAasCurrent"))
                and (tag("CmdA_SegType") == 2),
            )
            _pc = 666
            continue
        elif _pc == 666:
            # rung 666
            # XIC IssueCurPulse XIO UseAasCurrent EQU CmdB_SegType 1 MCLM X_Y MoveB 0 CmdB_XY[0] CmdB_Speed "Units per sec" CmdB_Accel "Units per sec2" CmdB_Decel "Units per sec2" S-Curve CmdB_JerkAccel CmdB_JerkDecel "Units per sec3" CmdB_TermType Disabled Programmed CmdTolerance 0 None 0 0
            MCLM(
                coordinate_system="X_Y",
                motion_control="MoveB",
                move_type=0,
                target="CmdB_XY[0]",
                speed="CmdB_Speed",
                speed_units="Units per sec",
                accel="CmdB_Accel",
                accel_units="Units per sec2",
                decel="CmdB_Decel",
                decel_units="Units per sec2",
                profile="S-Curve",
                accel_jerk="CmdB_JerkAccel",
                decel_jerk="CmdB_JerkDecel",
                jerk_units="Units per sec3",
                termination_type="CmdB_TermType",
                merge="Disabled",
                merge_speed="Programmed",
                command_tolerance="CmdTolerance",
                lock_position=0,
                lock_direction="None",
                event_distance=0,
                calculated_data=0,
                rung_in=(tag("IssueCurPulse"))
                and (not tag("UseAasCurrent"))
                and (tag("CmdB_SegType") == 1),
            )
            _pc = 667
            continue
        elif _pc == 667:
            # rung 667
            # XIC IssueCurPulse XIO UseAasCurrent EQU CmdB_SegType 2 MCCM X_Y MoveB 0 CmdB_XY[0] CmdB_CircleType CmdB_ViaCenter[0] CmdB_Direction CmdB_Speed "Units per sec" CmdB_Accel "Units per sec2" CmdB_Decel "Units per sec2" S-Curve CmdB_JerkAccel CmdB_JerkDecel "Units per sec3" CmdB_TermType Disabled Programmed CmdTolerance 0 None 0 0
            MCCM(
                coordinate_system="X_Y",
                motion_control="MoveB",
                move_type=0,
                end_position="CmdB_XY[0]",
                circle_type="CmdB_CircleType",
                via_or_center="CmdB_ViaCenter[0]",
                direction="CmdB_Direction",
                speed="CmdB_Speed",
                speed_units="Units per sec",
                accel="CmdB_Accel",
                accel_units="Units per sec2",
                decel="CmdB_Decel",
                decel_units="Units per sec2",
                profile="S-Curve",
                accel_jerk="CmdB_JerkAccel",
                decel_jerk="CmdB_JerkDecel",
                jerk_units="Units per sec3",
                termination_type="CmdB_TermType",
                merge="Disabled",
                merge_speed="Programmed",
                command_tolerance="CmdTolerance",
                lock_position=0,
                lock_direction="None",
                event_distance=0,
                calculated_data=0,
                rung_in=(tag("IssueCurPulse"))
                and (not tag("UseAasCurrent"))
                and (tag("CmdB_SegType") == 2),
            )
            _pc = 668
            continue
        elif _pc == 668:
            # rung 668
            # XIC IssueCurPulse OTL CurIssued
            if tag("IssueCurPulse"):
                set_tag("CurIssued", True)
            _pc = 669
            continue
        elif _pc == 669:
            # rung 669
            # XIC IssueCurPulse OTU IssueCurPulse
            if tag("IssueCurPulse"):
                set_tag("IssueCurPulse", False)
            _pc = 670
            continue
        elif _pc == 670:
            # rung 670
            # XIC CurIssued XIC UseAasCurrent XIC MoveA.IP XIO X_Y.MovePendingStatus XIO NextIssued XIO QueueEmpty XIO QueueFault ONS StartNextA_ONS OTL LoadNextReq
            _pulse_602 = ONS(
                storage_bit="StartNextA_ONS",
                rung_in=(tag("CurIssued"))
                and (tag("UseAasCurrent"))
                and (tag("MoveA.IP"))
                and (not tag("X_Y.MovePendingStatus"))
                and (not tag("NextIssued"))
                and (not tag("QueueEmpty"))
                and (not tag("QueueFault")),
            )
            if _pulse_602:
                set_tag("LoadNextReq", True)
            _pc = 671
            continue
        elif _pc == 671:
            # rung 671
            # XIC CurIssued XIO UseAasCurrent XIC MoveB.IP XIO X_Y.MovePendingStatus XIO NextIssued XIO QueueEmpty XIO QueueFault ONS StartNextB_ONS OTL LoadNextReq
            _pulse_603 = ONS(
                storage_bit="StartNextB_ONS",
                rung_in=(tag("CurIssued"))
                and (not tag("UseAasCurrent"))
                and (tag("MoveB.IP"))
                and (not tag("X_Y.MovePendingStatus"))
                and (not tag("NextIssued"))
                and (not tag("QueueEmpty"))
                and (not tag("QueueFault")),
            )
            if _pulse_603:
                set_tag("LoadNextReq", True)
            _pc = 672
            continue
        elif _pc == 672:
            # rung 672
            # XIC LoadNextReq FFU SegQueue[0] NextSeg QueueCtl 32 0
            FFU(
                array="SegQueue[0]",
                dest="NextSeg",
                control="QueueCtl",
                length=32,
                position=0,
                rung_in=tag("LoadNextReq"),
            )
            _pc = 673
            continue
        elif _pc == 673:
            # rung 673
            # XIC LoadNextReq OTL CheckNextSeg
            if tag("LoadNextReq"):
                set_tag("CheckNextSeg", True)
            _pc = 674
            continue
        elif _pc == 674:
            # rung 674
            # XIC LoadNextReq OTU LoadNextReq
            if tag("LoadNextReq"):
                set_tag("LoadNextReq", False)
            _pc = 675
            continue
        elif _pc == 675:
            # rung 675
            # XIC PrepNextMove XIC UseAasCurrent COP NextSeg.XY[0] CmdB_XY[0] 2
            if tag("PrepNextMove"):
                if tag("UseAasCurrent"):
                    COP(
                        source="NextSeg.XY[0]",
                        dest="CmdB_XY[0]",
                        length=2,
                    )
            _pc = 676
            continue
        elif _pc == 676:
            # rung 676
            # XIC PrepNextMove XIC UseAasCurrent MOV NextSeg.Speed CmdB_Speed
            if tag("PrepNextMove"):
                if tag("UseAasCurrent"):
                    set_tag("CmdB_Speed", tag("NextSeg.Speed"))
            _pc = 677
            continue
        elif _pc == 677:
            # rung 677
            # XIC PrepNextMove XIC UseAasCurrent MOV NextSeg.Accel CmdB_Accel
            if tag("PrepNextMove"):
                if tag("UseAasCurrent"):
                    set_tag("CmdB_Accel", tag("NextSeg.Accel"))
            _pc = 678
            continue
        elif _pc == 678:
            # rung 678
            # XIC PrepNextMove XIC UseAasCurrent MOV NextSeg.Decel CmdB_Decel
            if tag("PrepNextMove"):
                if tag("UseAasCurrent"):
                    set_tag("CmdB_Decel", tag("NextSeg.Decel"))
            _pc = 679
            continue
        elif _pc == 679:
            # rung 679
            # XIC PrepNextMove XIC UseAasCurrent MOV NextSeg.JerkAccel CmdB_JerkAccel
            if tag("PrepNextMove"):
                if tag("UseAasCurrent"):
                    set_tag("CmdB_JerkAccel", tag("NextSeg.JerkAccel"))
            _pc = 680
            continue
        elif _pc == 680:
            # rung 680
            # XIC PrepNextMove XIC UseAasCurrent MOV NextSeg.JerkDecel CmdB_JerkDecel
            if tag("PrepNextMove"):
                if tag("UseAasCurrent"):
                    set_tag("CmdB_JerkDecel", tag("NextSeg.JerkDecel"))
            _pc = 681
            continue
        elif _pc == 681:
            # rung 681
            # XIC PrepNextMove XIC UseAasCurrent MOV NextSeg.TermType CmdB_TermType
            if tag("PrepNextMove"):
                if tag("UseAasCurrent"):
                    set_tag("CmdB_TermType", tag("NextSeg.TermType"))
            _pc = 682
            continue
        elif _pc == 682:
            # rung 682
            # XIC PrepNextMove XIC UseAasCurrent MOV NextSeg.SegType CmdB_SegType
            if tag("PrepNextMove"):
                if tag("UseAasCurrent"):
                    set_tag("CmdB_SegType", tag("NextSeg.SegType"))
            _pc = 683
            continue
        elif _pc == 683:
            # rung 683
            # XIC PrepNextMove XIC UseAasCurrent MOV NextSeg.CircleType CmdB_CircleType
            if tag("PrepNextMove"):
                if tag("UseAasCurrent"):
                    set_tag("CmdB_CircleType", tag("NextSeg.CircleType"))
            _pc = 684
            continue
        elif _pc == 684:
            # rung 684
            # XIC PrepNextMove XIC UseAasCurrent COP NextSeg.ViaCenter[0] CmdB_ViaCenter[0] 2
            if tag("PrepNextMove"):
                if tag("UseAasCurrent"):
                    COP(
                        source="NextSeg.ViaCenter[0]",
                        dest="CmdB_ViaCenter[0]",
                        length=2,
                    )
            _pc = 685
            continue
        elif _pc == 685:
            # rung 685
            # XIC PrepNextMove XIC UseAasCurrent MOV NextSeg.Direction CmdB_Direction
            if tag("PrepNextMove"):
                if tag("UseAasCurrent"):
                    set_tag("CmdB_Direction", tag("NextSeg.Direction"))
            _pc = 686
            continue
        elif _pc == 686:
            # rung 686
            # XIC PrepNextMove XIC UseAasCurrent MOV NextSeg.Seq PendingSeq
            if tag("PrepNextMove"):
                if tag("UseAasCurrent"):
                    set_tag("PendingSeq", tag("NextSeg.Seq"))
            _pc = 687
            continue
        elif _pc == 687:
            # rung 687
            # XIC PrepNextMove XIO UseAasCurrent COP NextSeg.XY[0] CmdA_XY[0] 2
            if tag("PrepNextMove"):
                if not tag("UseAasCurrent"):
                    COP(
                        source="NextSeg.XY[0]",
                        dest="CmdA_XY[0]",
                        length=2,
                    )
            _pc = 688
            continue
        elif _pc == 688:
            # rung 688
            # XIC PrepNextMove XIO UseAasCurrent MOV NextSeg.Speed CmdA_Speed
            if tag("PrepNextMove"):
                if not tag("UseAasCurrent"):
                    set_tag("CmdA_Speed", tag("NextSeg.Speed"))
            _pc = 689
            continue
        elif _pc == 689:
            # rung 689
            # XIC PrepNextMove XIO UseAasCurrent MOV NextSeg.Accel CmdA_Accel
            if tag("PrepNextMove"):
                if not tag("UseAasCurrent"):
                    set_tag("CmdA_Accel", tag("NextSeg.Accel"))
            _pc = 690
            continue
        elif _pc == 690:
            # rung 690
            # XIC PrepNextMove XIO UseAasCurrent MOV NextSeg.Decel CmdA_Decel
            if tag("PrepNextMove"):
                if not tag("UseAasCurrent"):
                    set_tag("CmdA_Decel", tag("NextSeg.Decel"))
            _pc = 691
            continue
        elif _pc == 691:
            # rung 691
            # XIC PrepNextMove XIO UseAasCurrent MOV NextSeg.JerkAccel CmdA_JerkAccel
            if tag("PrepNextMove"):
                if not tag("UseAasCurrent"):
                    set_tag("CmdA_JerkAccel", tag("NextSeg.JerkAccel"))
            _pc = 692
            continue
        elif _pc == 692:
            # rung 692
            # XIC PrepNextMove XIO UseAasCurrent MOV NextSeg.JerkDecel CmdA_JerkDecel
            if tag("PrepNextMove"):
                if not tag("UseAasCurrent"):
                    set_tag("CmdA_JerkDecel", tag("NextSeg.JerkDecel"))
            _pc = 693
            continue
        elif _pc == 693:
            # rung 693
            # XIC PrepNextMove XIO UseAasCurrent MOV NextSeg.TermType CmdA_TermType
            if tag("PrepNextMove"):
                if not tag("UseAasCurrent"):
                    set_tag("CmdA_TermType", tag("NextSeg.TermType"))
            _pc = 694
            continue
        elif _pc == 694:
            # rung 694
            # XIC PrepNextMove XIO UseAasCurrent MOV NextSeg.SegType CmdA_SegType
            if tag("PrepNextMove"):
                if not tag("UseAasCurrent"):
                    set_tag("CmdA_SegType", tag("NextSeg.SegType"))
            _pc = 695
            continue
        elif _pc == 695:
            # rung 695
            # XIC PrepNextMove XIO UseAasCurrent MOV NextSeg.CircleType CmdA_CircleType
            if tag("PrepNextMove"):
                if not tag("UseAasCurrent"):
                    set_tag("CmdA_CircleType", tag("NextSeg.CircleType"))
            _pc = 696
            continue
        elif _pc == 696:
            # rung 696
            # XIC PrepNextMove XIO UseAasCurrent COP NextSeg.ViaCenter[0] CmdA_ViaCenter[0] 2
            if tag("PrepNextMove"):
                if not tag("UseAasCurrent"):
                    COP(
                        source="NextSeg.ViaCenter[0]",
                        dest="CmdA_ViaCenter[0]",
                        length=2,
                    )
            _pc = 697
            continue
        elif _pc == 697:
            # rung 697
            # XIC PrepNextMove XIO UseAasCurrent MOV NextSeg.Direction CmdA_Direction
            if tag("PrepNextMove"):
                if not tag("UseAasCurrent"):
                    set_tag("CmdA_Direction", tag("NextSeg.Direction"))
            _pc = 698
            continue
        elif _pc == 698:
            # rung 698
            # XIC PrepNextMove XIO UseAasCurrent MOV NextSeg.Seq PendingSeq
            if tag("PrepNextMove"):
                if not tag("UseAasCurrent"):
                    set_tag("PendingSeq", tag("NextSeg.Seq"))
            _pc = 699
            continue
        elif _pc == 699:
            # rung 699
            # XIC PrepNextMove XIO APA_IS_VERTICAL MOV 3005 FaultCode CPT ERROR_CODE 3005 CPT NEXTSTATE 10 OTL QueueFault
            if tag("PrepNextMove"):
                if not tag("APA_IS_VERTICAL"):
                    set_tag("FaultCode", 3005)
            if tag("PrepNextMove"):
                if not tag("APA_IS_VERTICAL"):
                    set_tag("ERROR_CODE", formula("3005"))
            if tag("PrepNextMove"):
                if not tag("APA_IS_VERTICAL"):
                    set_tag("NEXTSTATE", formula("10"))
            if tag("PrepNextMove"):
                if not tag("APA_IS_VERTICAL"):
                    set_tag("QueueFault", True)
            _pc = 700
            continue
        elif _pc == 700:
            # rung 700
            # XIC PrepNextMove XIC APA_IS_VERTICAL XIC X_Y.PhysicalAxisFault MOV 3002 FaultCode CPT ERROR_CODE 3002 CPT NEXTSTATE 10 OTL QueueFault
            if tag("PrepNextMove"):
                if tag("APA_IS_VERTICAL"):
                    if tag("X_Y.PhysicalAxisFault"):
                        set_tag("FaultCode", 3002)
            if tag("PrepNextMove"):
                if tag("APA_IS_VERTICAL"):
                    if tag("X_Y.PhysicalAxisFault"):
                        set_tag("ERROR_CODE", formula("3002"))
            if tag("PrepNextMove"):
                if tag("APA_IS_VERTICAL"):
                    if tag("X_Y.PhysicalAxisFault"):
                        set_tag("NEXTSTATE", formula("10"))
            if tag("PrepNextMove"):
                if tag("APA_IS_VERTICAL"):
                    if tag("X_Y.PhysicalAxisFault"):
                        set_tag("QueueFault", True)
            _pc = 701
            continue
        elif _pc == 701:
            # rung 701
            # XIC PrepNextMove XIC APA_IS_VERTICAL XIO X_Y.PhysicalAxisFault XIC X_axis.DriveEnableStatus XIC Y_axis.DriveEnableStatus OTL MQ_IssueNextPulse
            if tag("PrepNextMove"):
                if tag("APA_IS_VERTICAL"):
                    if not tag("X_Y.PhysicalAxisFault"):
                        if tag("X_axis.DriveEnableStatus"):
                            if tag("Y_axis.DriveEnableStatus"):
                                set_tag("MQ_IssueNextPulse", True)
            _pc = 702
            continue
        elif _pc == 702:
            # rung 702
            # XIC PrepNextMove XIC APA_IS_VERTICAL XIO X_Y.PhysicalAxisFault BST XIO X_axis.DriveEnableStatus NXB XIO Y_axis.DriveEnableStatus BND OTL WaitNextAxisOn
            _branch_604 = bool(not tag("X_axis.DriveEnableStatus"))
            _branch_606 = bool(not tag("Y_axis.DriveEnableStatus"))
            _branch_608 = _branch_604 or _branch_606
            if tag("PrepNextMove"):
                if tag("APA_IS_VERTICAL"):
                    if not tag("X_Y.PhysicalAxisFault"):
                        if _branch_608:
                            set_tag("WaitNextAxisOn", True)
            _pc = 703
            continue
        elif _pc == 703:
            # rung 703
            # XIC PrepNextMove OTU PrepNextMove
            if tag("PrepNextMove"):
                set_tag("PrepNextMove", False)
            _pc = 704
            continue
        elif _pc == 704:
            # rung 704
            # XIC WaitNextAxisOn XIO APA_IS_VERTICAL MOV 3005 FaultCode CPT ERROR_CODE 3005 CPT NEXTSTATE 10 OTL QueueFault OTU WaitNextAxisOn
            if tag("WaitNextAxisOn"):
                if not tag("APA_IS_VERTICAL"):
                    set_tag("FaultCode", 3005)
            if tag("WaitNextAxisOn"):
                if not tag("APA_IS_VERTICAL"):
                    set_tag("ERROR_CODE", formula("3005"))
            if tag("WaitNextAxisOn"):
                if not tag("APA_IS_VERTICAL"):
                    set_tag("NEXTSTATE", formula("10"))
            if tag("WaitNextAxisOn"):
                if not tag("APA_IS_VERTICAL"):
                    set_tag("QueueFault", True)
            if tag("WaitNextAxisOn"):
                if not tag("APA_IS_VERTICAL"):
                    set_tag("WaitNextAxisOn", False)
            _pc = 705
            continue
        elif _pc == 705:
            # rung 705
            # XIC WaitNextAxisOn XIC APA_IS_VERTICAL XIC X_Y.PhysicalAxisFault MOV 3002 FaultCode CPT ERROR_CODE 3002 CPT NEXTSTATE 10 OTL QueueFault OTU WaitNextAxisOn
            if tag("WaitNextAxisOn"):
                if tag("APA_IS_VERTICAL"):
                    if tag("X_Y.PhysicalAxisFault"):
                        set_tag("FaultCode", 3002)
            if tag("WaitNextAxisOn"):
                if tag("APA_IS_VERTICAL"):
                    if tag("X_Y.PhysicalAxisFault"):
                        set_tag("ERROR_CODE", formula("3002"))
            if tag("WaitNextAxisOn"):
                if tag("APA_IS_VERTICAL"):
                    if tag("X_Y.PhysicalAxisFault"):
                        set_tag("NEXTSTATE", formula("10"))
            if tag("WaitNextAxisOn"):
                if tag("APA_IS_VERTICAL"):
                    if tag("X_Y.PhysicalAxisFault"):
                        set_tag("QueueFault", True)
            if tag("WaitNextAxisOn"):
                if tag("APA_IS_VERTICAL"):
                    if tag("X_Y.PhysicalAxisFault"):
                        set_tag("WaitNextAxisOn", False)
            _pc = 706
            continue
        elif _pc == 706:
            # rung 706
            # XIC WaitNextAxisOn XIC APA_IS_VERTICAL XIO X_Y.PhysicalAxisFault MSO X_axis MQ_x_axis_mso MSO Y_axis MQ_y_axis_mso
            if tag("WaitNextAxisOn"):
                if tag("APA_IS_VERTICAL"):
                    if not tag("X_Y.PhysicalAxisFault"):
                        MSO(
                            axis="X_axis",
                            motion_control="MQ_x_axis_mso",
                        )
            if tag("WaitNextAxisOn"):
                if tag("APA_IS_VERTICAL"):
                    if not tag("X_Y.PhysicalAxisFault"):
                        MSO(
                            axis="Y_axis",
                            motion_control="MQ_y_axis_mso",
                        )
            _pc = 707
            continue
        elif _pc == 707:
            # rung 707
            # XIC WaitNextAxisOn XIC APA_IS_VERTICAL XIO X_Y.PhysicalAxisFault XIC MQ_x_axis_mso.DN XIC MQ_y_axis_mso.DN OTL MQ_IssueNextPulse
            if tag("WaitNextAxisOn"):
                if tag("APA_IS_VERTICAL"):
                    if not tag("X_Y.PhysicalAxisFault"):
                        if tag("MQ_x_axis_mso.DN"):
                            if tag("MQ_y_axis_mso.DN"):
                                set_tag("MQ_IssueNextPulse", True)
            _pc = 708
            continue
        elif _pc == 708:
            # rung 708
            # XIC WaitNextAxisOn XIC APA_IS_VERTICAL XIO X_Y.PhysicalAxisFault XIC MQ_x_axis_mso.DN XIC MQ_y_axis_mso.DN OTU WaitNextAxisOn
            if tag("WaitNextAxisOn"):
                if tag("APA_IS_VERTICAL"):
                    if not tag("X_Y.PhysicalAxisFault"):
                        if tag("MQ_x_axis_mso.DN"):
                            if tag("MQ_y_axis_mso.DN"):
                                set_tag("WaitNextAxisOn", False)
            _pc = 709
            continue
        elif _pc == 709:
            # rung 709
            # XIC PrepNextMove OTU PrepNextMove
            if tag("PrepNextMove"):
                set_tag("PrepNextMove", False)
            _pc = 710
            continue
        elif _pc == 710:
            # rung 710
            # XIC MQ_IssueNextPulse XIC UseAasCurrent EQU CmdB_SegType 1 MCLM X_Y MoveB 0 CmdB_XY[0] CmdB_Speed "Units per sec" CmdB_Accel "Units per sec2" CmdB_Decel "Units per sec2" S-Curve CmdB_JerkAccel CmdB_JerkDecel "Units per sec3" CmdB_TermType Disabled Programmed CmdTolerance 0 None 0 0
            MCLM(
                coordinate_system="X_Y",
                motion_control="MoveB",
                move_type=0,
                target="CmdB_XY[0]",
                speed="CmdB_Speed",
                speed_units="Units per sec",
                accel="CmdB_Accel",
                accel_units="Units per sec2",
                decel="CmdB_Decel",
                decel_units="Units per sec2",
                profile="S-Curve",
                accel_jerk="CmdB_JerkAccel",
                decel_jerk="CmdB_JerkDecel",
                jerk_units="Units per sec3",
                termination_type="CmdB_TermType",
                merge="Disabled",
                merge_speed="Programmed",
                command_tolerance="CmdTolerance",
                lock_position=0,
                lock_direction="None",
                event_distance=0,
                calculated_data=0,
                rung_in=(tag("MQ_IssueNextPulse"))
                and (tag("UseAasCurrent"))
                and (tag("CmdB_SegType") == 1),
            )
            _pc = 711
            continue
        elif _pc == 711:
            # rung 711
            # XIC MQ_IssueNextPulse XIC UseAasCurrent EQU CmdB_SegType 2 MCCM X_Y MoveB 0 CmdB_XY[0] CmdB_CircleType CmdB_ViaCenter[0] CmdB_Direction CmdB_Speed "Units per sec" CmdB_Accel "Units per sec2" CmdB_Decel "Units per sec2" S-Curve CmdB_JerkAccel CmdB_JerkDecel "Units per sec3" CmdB_TermType Disabled Programmed CmdTolerance 0 None 0 0
            MCCM(
                coordinate_system="X_Y",
                motion_control="MoveB",
                move_type=0,
                end_position="CmdB_XY[0]",
                circle_type="CmdB_CircleType",
                via_or_center="CmdB_ViaCenter[0]",
                direction="CmdB_Direction",
                speed="CmdB_Speed",
                speed_units="Units per sec",
                accel="CmdB_Accel",
                accel_units="Units per sec2",
                decel="CmdB_Decel",
                decel_units="Units per sec2",
                profile="S-Curve",
                accel_jerk="CmdB_JerkAccel",
                decel_jerk="CmdB_JerkDecel",
                jerk_units="Units per sec3",
                termination_type="CmdB_TermType",
                merge="Disabled",
                merge_speed="Programmed",
                command_tolerance="CmdTolerance",
                lock_position=0,
                lock_direction="None",
                event_distance=0,
                calculated_data=0,
                rung_in=(tag("MQ_IssueNextPulse"))
                and (tag("UseAasCurrent"))
                and (tag("CmdB_SegType") == 2),
            )
            _pc = 712
            continue
        elif _pc == 712:
            # rung 712
            # XIC MQ_IssueNextPulse XIO UseAasCurrent EQU CmdA_SegType 1 MCLM X_Y MoveA 0 CmdA_XY[0] CmdA_Speed "Units per sec" CmdA_Accel "Units per sec2" CmdA_Decel "Units per sec2" S-Curve CmdA_JerkAccel CmdA_JerkDecel "Units per sec3" CmdA_TermType Disabled Programmed CmdTolerance 0 None 0 0
            MCLM(
                coordinate_system="X_Y",
                motion_control="MoveA",
                move_type=0,
                target="CmdA_XY[0]",
                speed="CmdA_Speed",
                speed_units="Units per sec",
                accel="CmdA_Accel",
                accel_units="Units per sec2",
                decel="CmdA_Decel",
                decel_units="Units per sec2",
                profile="S-Curve",
                accel_jerk="CmdA_JerkAccel",
                decel_jerk="CmdA_JerkDecel",
                jerk_units="Units per sec3",
                termination_type="CmdA_TermType",
                merge="Disabled",
                merge_speed="Programmed",
                command_tolerance="CmdTolerance",
                lock_position=0,
                lock_direction="None",
                event_distance=0,
                calculated_data=0,
                rung_in=(tag("MQ_IssueNextPulse"))
                and (not tag("UseAasCurrent"))
                and (tag("CmdA_SegType") == 1),
            )
            _pc = 713
            continue
        elif _pc == 713:
            # rung 713
            # XIC MQ_IssueNextPulse XIO UseAasCurrent EQU CmdA_SegType 2 MCCM X_Y MoveA 0 CmdA_XY[0] CmdA_CircleType CmdA_ViaCenter[0] CmdA_Direction CmdA_Speed "Units per sec" CmdA_Accel "Units per sec2" CmdA_Decel "Units per sec2" S-Curve CmdA_JerkAccel CmdA_JerkDecel "Units per sec3" CmdA_TermType Disabled Programmed CmdTolerance 0 None 0 0
            MCCM(
                coordinate_system="X_Y",
                motion_control="MoveA",
                move_type=0,
                end_position="CmdA_XY[0]",
                circle_type="CmdA_CircleType",
                via_or_center="CmdA_ViaCenter[0]",
                direction="CmdA_Direction",
                speed="CmdA_Speed",
                speed_units="Units per sec",
                accel="CmdA_Accel",
                accel_units="Units per sec2",
                decel="CmdA_Decel",
                decel_units="Units per sec2",
                profile="S-Curve",
                accel_jerk="CmdA_JerkAccel",
                decel_jerk="CmdA_JerkDecel",
                jerk_units="Units per sec3",
                termination_type="CmdA_TermType",
                merge="Disabled",
                merge_speed="Programmed",
                command_tolerance="CmdTolerance",
                lock_position=0,
                lock_direction="None",
                event_distance=0,
                calculated_data=0,
                rung_in=(tag("MQ_IssueNextPulse"))
                and (not tag("UseAasCurrent"))
                and (tag("CmdA_SegType") == 2),
            )
            _pc = 714
            continue
        elif _pc == 714:
            # rung 714
            # XIC MQ_IssueNextPulse OTL NextIssued
            if tag("MQ_IssueNextPulse"):
                set_tag("NextIssued", True)
            _pc = 715
            continue
        elif _pc == 715:
            # rung 715
            # XIC MQ_IssueNextPulse OTU MQ_IssueNextPulse
            if tag("MQ_IssueNextPulse"):
                set_tag("MQ_IssueNextPulse", False)
            _pc = 716
            continue
        elif _pc == 716:
            # rung 716
            # XIC CurIssued XIC NextIssued XIC UseAasCurrent XIO X_Y.MovePendingStatus XIC MoveB.IP ONS RotateONS_AtoB OTL RotateMoves
            _pulse_609 = ONS(
                storage_bit="RotateONS_AtoB",
                rung_in=(tag("CurIssued"))
                and (tag("NextIssued"))
                and (tag("UseAasCurrent"))
                and (not tag("X_Y.MovePendingStatus"))
                and (tag("MoveB.IP")),
            )
            if _pulse_609:
                set_tag("RotateMoves", True)
            _pc = 717
            continue
        elif _pc == 717:
            # rung 717
            # XIC CurIssued XIC NextIssued XIO UseAasCurrent XIO X_Y.MovePendingStatus XIC MoveA.IP ONS RotateONS_BtoA OTL RotateMoves
            _pulse_610 = ONS(
                storage_bit="RotateONS_BtoA",
                rung_in=(tag("CurIssued"))
                and (tag("NextIssued"))
                and (not tag("UseAasCurrent"))
                and (not tag("X_Y.MovePendingStatus"))
                and (tag("MoveA.IP")),
            )
            if _pulse_610:
                set_tag("RotateMoves", True)
            _pc = 718
            continue
        elif _pc == 718:
            # rung 718
            # XIC RotateMoves COP NextSeg CurSeg 1
            if tag("RotateMoves"):
                COP(
                    source="NextSeg",
                    dest="CurSeg",
                    length=1,
                )
            _pc = 719
            continue
        elif _pc == 719:
            # rung 719
            # XIC RotateMoves XIC UseAasCurrent OTL FlipToB
            if tag("RotateMoves"):
                if tag("UseAasCurrent"):
                    set_tag("FlipToB", True)
            _pc = 720
            continue
        elif _pc == 720:
            # rung 720
            # XIC RotateMoves XIO UseAasCurrent OTL FlipToA
            if tag("RotateMoves"):
                if not tag("UseAasCurrent"):
                    set_tag("FlipToA", True)
            _pc = 721
            continue
        elif _pc == 721:
            # rung 721
            # XIC FlipToB OTU UseAasCurrent
            if tag("FlipToB"):
                set_tag("UseAasCurrent", False)
            _pc = 722
            continue
        elif _pc == 722:
            # rung 722
            # XIC FlipToA OTL UseAasCurrent
            if tag("FlipToA"):
                set_tag("UseAasCurrent", True)
            _pc = 723
            continue
        elif _pc == 723:
            # rung 723
            # XIC RotateMoves OTU NextIssued
            if tag("RotateMoves"):
                set_tag("NextIssued", False)
            _pc = 724
            continue
        elif _pc == 724:
            # rung 724
            # XIC RotateMoves MOV PendingSeq ActiveSeq
            if tag("RotateMoves"):
                set_tag("ActiveSeq", tag("PendingSeq"))
            _pc = 725
            continue
        elif _pc == 725:
            # rung 725
            # XIC RotateMoves MOV 0 PendingSeq
            if tag("RotateMoves"):
                set_tag("PendingSeq", 0)
            _pc = 726
            continue
        elif _pc == 726:
            # rung 726
            # XIC RotateMoves OTU RotateMoves
            if tag("RotateMoves"):
                set_tag("RotateMoves", False)
            _pc = 727
            continue
        elif _pc == 727:
            # rung 727
            # XIC FlipToA OTU FlipToA
            if tag("FlipToA"):
                set_tag("FlipToA", False)
            _pc = 728
            continue
        elif _pc == 728:
            # rung 728
            # XIC FlipToB OTU FlipToB
            if tag("FlipToB"):
                set_tag("FlipToB", False)
            _pc = 729
            continue
        elif _pc == 729:
            # rung 729
            # XIC CurIssued XIO NextIssued XIC UseAasCurrent XIO X_Y.MovePendingStatus XIC MoveA.PC ONS DoneONS_A OTU CurIssued
            _pulse_611 = ONS(
                storage_bit="DoneONS_A",
                rung_in=(tag("CurIssued"))
                and (not tag("NextIssued"))
                and (tag("UseAasCurrent"))
                and (not tag("X_Y.MovePendingStatus"))
                and (tag("MoveA.PC")),
            )
            if _pulse_611:
                set_tag("CurIssued", False)
            _pc = 730
            continue
        elif _pc == 730:
            # rung 730
            # XIC CurIssued XIO NextIssued XIO UseAasCurrent XIO X_Y.MovePendingStatus XIC MoveB.PC ONS DoneONS_B OTU CurIssued
            _pulse_612 = ONS(
                storage_bit="DoneONS_B",
                rung_in=(tag("CurIssued"))
                and (not tag("NextIssued"))
                and (not tag("UseAasCurrent"))
                and (not tag("X_Y.MovePendingStatus"))
                and (tag("MoveB.PC")),
            )
            if _pulse_612:
                set_tag("CurIssued", False)
            _pc = 731
            continue
        elif _pc == 731:
            # rung 731
            # XIC AbortActive RES CurIssueAckTON
            if tag("AbortActive"):
                RES("CurIssueAckTON")
            _pc = 732
            continue
        elif _pc == 732:
            # rung 732
            # XIC AbortActive RES NextIssueAckTON
            if tag("AbortActive"):
                RES("NextIssueAckTON")
            _pc = 733
            continue
        elif _pc == 733:
            # rung 733
            # XIC AbortActive RES QueueCtl
            if tag("AbortActive"):
                RES("QueueCtl")
            _pc = 734
            continue
        elif _pc == 734:
            # rung 734
            # XIC AbortActive OTU CurIssued
            if tag("AbortActive"):
                set_tag("CurIssued", False)
            _pc = 735
            continue
        elif _pc == 735:
            # rung 735
            # XIC AbortActive OTU NextIssued
            if tag("AbortActive"):
                set_tag("NextIssued", False)
            _pc = 736
            continue
        elif _pc == 736:
            # rung 736
            # XIC AbortActive OTU LoadCurReq
            if tag("AbortActive"):
                set_tag("LoadCurReq", False)
            _pc = 737
            continue
        elif _pc == 737:
            # rung 737
            # XIC AbortActive OTU LoadNextReq
            if tag("AbortActive"):
                set_tag("LoadNextReq", False)
            _pc = 738
            continue
        elif _pc == 738:
            # rung 738
            # XIC AbortActive OTU PrepCurMove
            if tag("AbortActive"):
                set_tag("PrepCurMove", False)
            _pc = 739
            continue
        elif _pc == 739:
            # rung 739
            # XIC AbortActive OTU PrepNextMove
            if tag("AbortActive"):
                set_tag("PrepNextMove", False)
            _pc = 740
            continue
        elif _pc == 740:
            # rung 740
            # XIC AbortActive OTU IssueCurPulse
            if tag("AbortActive"):
                set_tag("IssueCurPulse", False)
            _pc = 741
            continue
        elif _pc == 741:
            # rung 741
            # XIC AbortActive OTU MQ_IssueNextPulse
            if tag("AbortActive"):
                set_tag("MQ_IssueNextPulse", False)
            _pc = 742
            continue
        elif _pc == 742:
            # rung 742
            # XIC AbortActive OTU WaitCurAxisOn
            if tag("AbortActive"):
                set_tag("WaitCurAxisOn", False)
            _pc = 743
            continue
        elif _pc == 743:
            # rung 743
            # XIC AbortActive OTU WaitNextAxisOn
            if tag("AbortActive"):
                set_tag("WaitNextAxisOn", False)
            _pc = 744
            continue
        elif _pc == 744:
            # rung 744
            # XIC AbortActive OTU QueueStopRequest
            if tag("AbortActive"):
                set_tag("QueueStopRequest", False)
            _pc = 745
            continue
        elif _pc == 745:
            # rung 745
            # XIC AbortActive OTU AbortQueue
            if tag("AbortActive"):
                set_tag("AbortQueue", False)
            _pc = 746
            continue
        elif _pc == 746:
            # rung 746
            # XIC AbortActive OTU EnqueueReq
            if tag("AbortActive"):
                set_tag("EnqueueReq", False)
            _pc = 747
            continue
        elif _pc == 747:
            # rung 747
            # XIC AbortActive OTU RotateMoves
            if tag("AbortActive"):
                set_tag("RotateMoves", False)
            _pc = 748
            continue
        elif _pc == 748:
            # rung 748
            # XIC AbortActive OTU FlipToA
            if tag("AbortActive"):
                set_tag("FlipToA", False)
            _pc = 749
            continue
        elif _pc == 749:
            # rung 749
            # XIC AbortActive OTU FlipToB
            if tag("AbortActive"):
                set_tag("FlipToB", False)
            _pc = 750
            continue
        elif _pc == 750:
            # rung 750
            # XIC AbortActive OTL UseAasCurrent
            if tag("AbortActive"):
                set_tag("UseAasCurrent", True)
            _pc = 751
            continue
        elif _pc == 751:
            # rung 751
            # XIC AbortActive OTU StartQueuedPath
            if tag("AbortActive"):
                set_tag("StartQueuedPath", False)
            _pc = 752
            continue
        elif _pc == 752:
            # rung 752
            # XIC AbortActive MOV 0 FaultCode
            if tag("AbortActive"):
                set_tag("FaultCode", 0)
            _pc = 753
            continue
        elif _pc == 753:
            # rung 753
            # XIC AbortActive OTU QueueFault
            if tag("AbortActive"):
                set_tag("QueueFault", False)
            _pc = 754
            continue
        elif _pc == 754:
            # rung 754
            # XIC AbortActive OTU CheckCurSeg
            if tag("AbortActive"):
                set_tag("CheckCurSeg", False)
            _pc = 755
            continue
        elif _pc == 755:
            # rung 755
            # XIC AbortActive OTU CheckNextSeg
            if tag("AbortActive"):
                set_tag("CheckNextSeg", False)
            _pc = 756
            continue
        elif _pc == 756:
            # rung 756
            # XIC AbortActive OTU CurSeg.Valid
            if tag("AbortActive"):
                set_tag("CurSeg.Valid", False)
            _pc = 757
            continue
        elif _pc == 757:
            # rung 757
            # XIC AbortActive MOV 0 CurSeg.Seq
            if tag("AbortActive"):
                set_tag("CurSeg.Seq", 0)
            _pc = 758
            continue
        elif _pc == 758:
            # rung 758
            # XIC AbortActive OTU NextSeg.Valid
            if tag("AbortActive"):
                set_tag("NextSeg.Valid", False)
            _pc = 759
            continue
        elif _pc == 759:
            # rung 759
            # XIC AbortActive MOV 0 NextSeg.Seq
            if tag("AbortActive"):
                set_tag("NextSeg.Seq", 0)
            _pc = 760
            continue
        elif _pc == 760:
            # rung 760
            # XIC AbortActive MOV IncomingSegReqID LastIncomingSegReqID
            if tag("AbortActive"):
                set_tag("LastIncomingSegReqID", tag("IncomingSegReqID"))
            _pc = 761
            continue
        elif _pc == 761:
            # rung 761
            # XIC AbortActive MOV 0 ActiveSeq
            if tag("AbortActive"):
                set_tag("ActiveSeq", 0)
            _pc = 762
            continue
        elif _pc == 762:
            # rung 762
            # XIC AbortActive MOV 0 PendingSeq
            if tag("AbortActive"):
                set_tag("PendingSeq", 0)
            _pc = 763
            continue
        elif _pc == 763:
            # rung 763
            # XIC AbortActive FLL 0 SegQueue[0] 32
            if tag("AbortActive"):
                FLL(
                    value=0,
                    dest="SegQueue[0]",
                    length=32,
                )
            break
        else:
            break
