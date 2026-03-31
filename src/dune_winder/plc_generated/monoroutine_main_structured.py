from dune_winder.plc_ladder.codegen_support import ADD, BRANCH, CMP, COP, CPT, CTU, EQU, FFL, FFU, FLL, GEQ, GRT, JMP, LBL, LEQ, LES, LIM, MAFR, MAM, MAS, MCCD, MCCM, MCLM, MCS, MOD, MOV, MSF, MSO, NEQ, NOP, ONS, OTE, OTL, OTU, PID, RES, ROUTINE, RUNG, TON, TRN, XIC, XIO


Monoroutine_main = ROUTINE(
  name='main',
  program='Monoroutine',
  source_path='dune_winder/plc_monoroutine/Monoroutine/main/manual-edit.rll',
  rungs=(
    RUNG(
      XIC('Local:1:I.Pt00.Data'),
      OTE('MACHINE_SW_STAT[1]'),
      OTE('Z_RETRACTED_1A'),
    ),
    RUNG(
      XIO('Local:1:I.Pt01.Data'),
      OTE('MACHINE_SW_STAT[2]'),
      OTE('Z_RETRACTED_1B'),
    ),
    RUNG(
      XIC('Local:1:I.Pt02.Data'),
      OTE('MACHINE_SW_STAT[3]'),
      OTE('Z_RETRACTED_2A'),
    ),
    RUNG(
      XIO('Local:1:I.Pt03.Data'),
      OTE('MACHINE_SW_STAT[4]'),
      OTE('Z_RETRACTED_2B'),
    ),
    RUNG(
      BRANCH([XIC('Local:1:I.Pt04.Data')], [CMP('Z_axis.ActualPosition>415')]),
      OTE('MACHINE_SW_STAT[5]'),
      OTE('Z_EXTENDED'),
    ),
    RUNG(
      XIC('Local:1:I.Pt11.Data'),
      OTE('MACHINE_SW_STAT[6]'),
      OTE('Z_STAGE_LATCHED'),
    ),
    RUNG(
      XIC('Local:2:I.Pt01.Data'),
      OTE('MACHINE_SW_STAT[7]'),
      OTE('Z_FIXED_LATCHED'),
    ),
    RUNG(
      BRANCH([XIC('Local:1:I.Pt07.Data')], [XIC('z_eot_bypass')]),
      OTE('MACHINE_SW_STAT[8]'),
      OTE('Z_EOT'),
    ),
    RUNG(
      XIO('Local:1:I.Pt10.Data'),
      OTE('MACHINE_SW_STAT[9]'),
      OTE('Z_STAGE_PRESENT'),
    ),
    RUNG(
      XIO('Local:2:I.Pt02.Data'),
      OTE('MACHINE_SW_STAT[10]'),
      OTE('Z_FIXED_PRESENT'),
    ),
    RUNG(
      XIC('Local:2:I.Pt04.Data'),
      OTE('MACHINE_SW_STAT[14]'),
      OTE('X_PARKED'),
    ),
    RUNG(
      XIC('Local:2:I.Pt00.Data'),
      OTE('MACHINE_SW_STAT[15]'),
      OTE('X_XFER_OK'),
    ),
    RUNG(
      XIC('Local:1:I.Pt13.Data'),
      OTE('MACHINE_SW_STAT[16]'),
      OTE('Y_MOUNT_XFER_OK'),
    ),
    RUNG(
      XIC('Local:1:I.Pt12.Data'),
      OTE('MACHINE_SW_STAT[17]'),
      OTE('Y_XFER_OK'),
    ),
    RUNG(
      XIC('Local:1:I.Pt06.Data'),
      OTE('MACHINE_SW_STAT[18]'),
      OTE('PLUS_Y_EOT'),
    ),
    RUNG(
      XIC('Local:2:I.Pt12.Data'),
      OTE('MACHINE_SW_STAT[19]'),
      OTE('MINUS_Y_EOT'),
    ),
    RUNG(
      XIC('Local:2:I.Pt08.Data'),
      OTE('MACHINE_SW_STAT[20]'),
      OTE('PLUS_X_EOT'),
    ),
    RUNG(
      XIC('Local:2:I.Pt10.Data'),
      OTE('MACHINE_SW_STAT[21]'),
      OTE('MINUS_X_EOT'),
    ),
    RUNG(
      XIC('Local:2:I.Pt14.Data'),
      OTE('MACHINE_SW_STAT[22]'),
      OTE('APA_IS_VERTICAL'),
    ),
    RUNG(
      BRANCH([XIO('DUNEW2PLC2:1:I.Pt02Data')], [XIO('DUNEW2PLC2:1:I.Pt03Data')], [XIO('DUNEW2PLC2:1:I.Pt04Data')]),
      OTE('MACHINE_SW_STAT[23]'),
    ),
    RUNG(
      XIC('DUNEW2PLC2:1:I.Pt00Data'),
      XIC('DUNEW2PLC2:1:I.Pt01Data'),
      OTE('MACHINE_SW_STAT[25]'),
    ),
    RUNG(
      XIC('Local:6:I.Pt00.Data'),
      OTE('MACHINE_SW_STAT[26]'),
      OTE('FRAME_LOC_HD_TOP'),
    ),
    RUNG(
      XIC('Local:6:I.Pt01.Data'),
      OTE('MACHINE_SW_STAT[27]'),
      OTE('FRAME_LOC_HD_MID'),
    ),
    RUNG(
      XIC('Local:6:I.Pt02.Data'),
      OTE('MACHINE_SW_STAT[28]'),
      OTE('FRAME_LOC_HD_BTM'),
    ),
    RUNG(
      XIC('Local:6:I.Pt03.Data'),
      OTE('MACHINE_SW_STAT[29]'),
      OTE('FRAME_LOC_FT_TOP'),
    ),
    RUNG(
      XIC('Local:6:I.Pt04.Data'),
      OTE('MACHINE_SW_STAT[30]'),
      OTE('FRAME_LOC_FT_MID'),
    ),
    RUNG(
      XIC('Local:6:I.Pt05.Data'),
      OTE('MACHINE_SW_STAT[31]'),
      OTE('FRAME_LOC_FT_BTM'),
    ),
    RUNG(
      XIO('DUNEW2PLC2:1:I.Pt06Data'),
      OTE('speed_regulator_switch'),
    ),
    RUNG(
      BRANCH([XIC('Z_RETRACTED_1A')], [XIC('Z_RETRACTED_2A')]),
      XIC('Z_RETRACTED_1B'),
      XIC('Z_RETRACTED_2B'),
      OTE('Z_RETRACTED'),
    ),
    RUNG(
      XIC('Z_EOT'),
      XIC('PLUS_Y_EOT'),
      XIC('MINUS_Y_EOT'),
      XIC('PLUS_X_EOT'),
      XIC('MINUS_X_EOT'),
      OTE('ALL_EOT_GOOD'),
    ),
    RUNG(
      LIM('80', 'Y_axis.ActualPosition', '450'),
      OTE('support_collision_window_bttm'),
    ),
    RUNG(
      LIM('1050', 'Y_axis.ActualPosition', '1550'),
      OTE('support_collision_window_mid'),
    ),
    RUNG(
      LIM('2200', 'Y_axis.ActualPosition', '2650'),
      OTE('support_collision_window_top'),
    ),
    RUNG(
      XIC('Local:2:I.Pt06.Data'),
      OTE('TENSION_ON_SWITCH'),
    ),
    RUNG(
      BRANCH([XIC('Local:1:I.Pt15.Data')], [GRT('tension', 'wire_broken_tension')]),
      OTE('wire_break_proxy'),
    ),
    RUNG(
      XIO('Safety_Tripped_S'),
      TON('T01', '5000', '0'),
    ),
    RUNG(
      XIC('Safety_Tripped_S'),
      BRANCH([OTE('Local:3:O.Pt11.Data')], [OTE('Local:3:O.Pt12.Data')]),
    ),
    RUNG(
      BRANCH([XIC('blink_on.TT'), BRANCH([XIC('T01.TT')], [NEQ('ERROR_CODE', '0')])], [XIC('X_axis.SLSActiveStatus')]),
      OTE('Local:3:O.Pt13.Data'),
    ),
    RUNG(
      XIC('blink_on.TT'),
      XIC('T01.TT'),
      OTE('Local:3:O.Pt15.Data'),
    ),
    RUNG(
      BRANCH([XIC('T01.TT')], [XIC('T01.DN')]),
      OTE('Local:3:O.Pt14.Data'),
    ),
    RUNG(
      TON('blink_on', '500', '0'),
    ),
    RUNG(
      XIC('blink_on.DN'),
      TON('blink_off', '500', '0'),
    ),
    RUNG(
      XIC('blink_off.DN'),
      RES('blink_on'),
    ),
    RUNG(
      XIC('INIT_DONE'),
      CMP('NEXTSTATE=0'),
      CPT('STATE', '0'),
    ),
    RUNG(
      XIC('INIT_DONE'),
      CMP('NEXTSTATE=1'),
      CPT('STATE', '1'),
    ),
    RUNG(
      XIC('INIT_DONE'),
      CMP('NEXTSTATE=2'),
      CPT('STATE', '2'),
    ),
    RUNG(
      XIC('INIT_DONE'),
      CMP('NEXTSTATE=3'),
      CPT('STATE', '3'),
    ),
    RUNG(
      XIC('INIT_DONE'),
      CMP('NEXTSTATE=4'),
      CPT('STATE', '4'),
    ),
    RUNG(
      XIC('INIT_DONE'),
      CMP('NEXTSTATE=5'),
      CPT('STATE', '5'),
    ),
    RUNG(
      XIC('INIT_DONE'),
      CMP('NEXTSTATE=6'),
      CPT('STATE', '6'),
    ),
    RUNG(
      XIC('INIT_DONE'),
      CMP('NEXTSTATE=7'),
      CPT('STATE', '7'),
    ),
    RUNG(
      XIC('INIT_DONE'),
      CMP('NEXTSTATE=8'),
      CPT('STATE', '8'),
    ),
    RUNG(
      XIC('INIT_DONE'),
      CMP('NEXTSTATE=9'),
      CPT('STATE', '9'),
    ),
    RUNG(
      XIC('INIT_DONE'),
      CMP('NEXTSTATE=10'),
      CPT('STATE', '10'),
    ),
    RUNG(
      XIC('INIT_DONE'),
      CMP('NEXTSTATE=11'),
      CPT('STATE', '11'),
    ),
    RUNG(
      XIC('INIT_DONE'),
      CMP('NEXTSTATE=12'),
      CPT('STATE', '12'),
    ),
    RUNG(
      XIC('INIT_DONE'),
      CMP('NEXTSTATE=13'),
      CPT('STATE', '13'),
    ),
    RUNG(
      XIC('INIT_DONE'),
      CMP('NEXTSTATE=14'),
      CPT('STATE', '14'),
    ),
    RUNG(
      XIC('Local:2:I.Pt13.Data'),
      OTE('ResetPB'),
    ),
    RUNG(
      CPT('v_xyz', 'SQR(X_axis.ActualVelocity*X_axis.ActualVelocity+Y_axis.ActualVelocity*Y_axis.ActualVelocity)+SQR(Z_axis.ActualVelocity*Z_axis.ActualVelocity)'),
    ),
    RUNG(
      CPT('v_xy', 'SQR(X_axis.ActualVelocity*X_axis.ActualVelocity+Y_axis.ActualVelocity*Y_axis.ActualVelocity)'),
    ),
    RUNG(
      NEQ('v_xy', '0'),
      CPT('accel_xy', '(X_axis.ActualVelocity*X_axis.CommandAcceleration+Y_axis.ActualVelocity*Y_axis.CommandAcceleration)/v_xy'),
    ),
    RUNG(
      BRANCH([BRANCH([XIC('Z_STAGE_LATCHED')], [XIC('Z_FIXED_LATCHED'), EQU('ACTUATOR_POS', '3')]), CPT('HEAD_POS', '0')], [XIC('Z_FIXED_LATCHED'), EQU('ACTUATOR_POS', '2'), CPT('HEAD_POS', '3')], [XIO('Z_STAGE_LATCHED'), XIO('Z_FIXED_LATCHED'), CPT('HEAD_POS', '-1')]),
    ),
    RUNG(
      XIC('TENSION_ON_SWITCH'),
      TON('tension_on_switch_delay_on_start', '1000', '0'),
    ),
    RUNG(
      XIC('TENSION_ON_SWITCH'),
      OTL('PTS_tension_switch_transition_oneshot_storage'),
    ),
    RUNG(
      XIO('TENSION_ON_SWITCH'),
      OTU('PTS_tension_switch_transition_oneshot_storage'),
    ),
    RUNG(
      XIC('TENSION_ON_SWITCH'),
      OTL('PTS_tension_switch_off_oneshot_storage'),
    ),
    RUNG(
      XIO('TENSION_ON_SWITCH'),
      OTU('PTS_tension_switch_off_oneshot_storage'),
    ),
    RUNG(
      XIO('wire_break_proxy'),
      TON('wire_break_debounce', '20', '0'),
    ),
    RUNG(
      XIC('TENSION_ON_SWITCH'),
      XIO('Safety_Tripped_S'),
      BRANCH([XIC('wire_break_proxy')], [XIC('tension_on_switch_delay_on_start.TT')], [XIO('wire_break_debounce.DN')]),
      OTE('Enable_tension_motor'),
    ),
    RUNG(
      BRANCH([XIC('tension_on_switch_delay_on_start.TT')], [XIC('TENSION_CONTROL_OK')]),
      BRANCH([BRANCH([XIC('wire_break_proxy')], [XIO('wire_break_switch_delay_on_start.DN')], [XIO('wire_break_debounce.DN')]), OTE('TENSION_CONTROL_OK')], [TON('wire_break_switch_delay_on_start', '1000', '0')]),
    ),
    RUNG(
      XIO('PID_LOOP_TIMER.DN'),
      TON('PID_LOOP_TIMER', '3', '0'),
    ),
    RUNG(
      CPT('tension', '2.26*tension_tag-0.503*tension_tag*tension_tag+0.0694*tension_tag*tension_tag*tension_tag-0.00314*tension_tag*tension_tag*tension_tag*tension_tag'),
    ),
    RUNG(
      CMP('tension_tag<=1'),
      CPT('tension', 'tension_tag'),
    ),
    RUNG(
      BRANCH([XIC('PID_LOOP_TIMER.DN')], [XIC('pid_loop_timer_bypass')]),
      BRANCH([XIC('TENSION_CONTROL_OK'), MOV('tension_setpoint', 'winding_head_pid.SP')], [XIO('TENSION_CONTROL_OK'), MOV('10', 'tension'), MOV('0', 'winding_head_pid.SP')], [PID('winding_head_pid', 'tension', '0', 'tension_motor_cv', '0', '0', '0')], [BRANCH([XIO('TENSION_CONTROL_OK')], [XIO('TENSION_ON_SWITCH')], [XIC('tension_on_switch_delay_on_start.TT'), LES('tension_motor_cv', 'neutral_cv')]), MOV('neutral_cv', 'tension_motor_cv')], [XIC('constant_cv_out'), MOV('SetPoint_Override', 'tension_motor_cv')], [MOV('tension_motor_cv', 'cv_to_electrocraft')]),
    ),
    RUNG(
      CPT('tension_motor_difference', 'tension-tension_motor_cv'),
    ),
    RUNG(
      CPT('current_command', 'cv_to_electrocraft*(current_command_high-current_command_low)/pid_cv_high_limit+current_command_low'),
    ),
    RUNG(
      CPT('neutral_cv', '-current_command_low/((current_command_high-current_command_low)/(pid_cv_high_limit-pid_cv_low_limit))'),
    ),
    RUNG(
      MOV('tension_stable_time', 'tension_stable_timer.PRE'),
      CMP('ABS(tension-tension_setpoint)<tension_stable_tolerance'),
      TON('tension_stable_timer', '100', '0'),
    ),
    RUNG(
      GRT('tension', 'max_tolerable_tension'),
      XIC('TENSION_ON_SWITCH'),
      OTE('Local:3:O.Pt15.Data'),
      TON('overtension_timer', '10', '0'),
    ),
    RUNG(
      XIC('overtension_timer.DN'),
      OTE('MORE_STATS[2]'),
      CPT('ERROR_CODE', '8002'),
      CPT('NEXTSTATE', '10'),
    ),
    RUNG(
      XIC('tension_on_switch_delay_on_start.DN'),
      XIC('wire_break_debounce.DN'),
      NEQ('ERROR_CODE', '8002'),
      CPT('NEXTSTATE', '10'),
      CPT('ERROR_CODE', '8001'),
    ),
    RUNG(
      XIO('TENSION_ON_SWITCH'),
      XIC('PTS_tension_switch_transition_oneshot_storage'),
      OTE('PTS_clear_tension_fault_oneshot'),
    ),
    RUNG(
      XIC('PTS_clear_tension_fault_oneshot'),
      BRANCH([EQU('ERROR_CODE', '8002')], [EQU('ERROR_CODE', '8001')]),
      CPT('ERROR_CODE', '0'),
    ),
    RUNG(
      EQU('MOVE_TYPE', '9'),
      XIC('INIT_SW'),
      OTU('INIT_SW'),
    ),
    RUNG(
      XIC('INIT_SW'),
      TON('TIMER', '2000', '0'),
    ),
    RUNG(
      XIO('INIT_SW'),
      CPT('MOVE_TYPE', '0'),
      OTL('INIT_SW'),
    ),
    RUNG(
      XIC('TIMER.DN'),
      XIO('INIT_SetBit[0]'),
      OTE('INIT_OutBit[0]'),
    ),
    RUNG(
      XIC('TIMER.DN'),
      OTL('INIT_SetBit[0]'),
    ),
    RUNG(
      XIO('TIMER.DN'),
      OTU('INIT_SetBit[0]'),
    ),
    RUNG(
      XIC('INIT_OutBit[0]'),
      CPT('MOVE_TYPE', '0'),
      CPT('NEXTSTATE', '1'),
      CPT('STATE', '0'),
      CPT('ERROR_CODE', '0'),
    ),
    RUNG(
      XIC('INIT_OutBit[0]'),
      OTU('LATCH_ACTUATOR_HOMED'),
    ),
    RUNG(
      XIC('INIT_SetBit[0]'),
      OTE('INIT_DONE'),
    ),
    RUNG(
      XIC('INIT_DONE'),
      CMP('STATE=0'),
      MAFR('Z_axis', 'INIT_z_axis_fault_reset_status'),
    ),
    RUNG(
      XIC('INIT_z_axis_fault_reset_status.DN'),
      XIO('INIT_SetBit[1]'),
      OTE('INIT_OutBit[1]'),
    ),
    RUNG(
      XIC('INIT_z_axis_fault_reset_status.DN'),
      OTL('INIT_SetBit[1]'),
    ),
    RUNG(
      XIO('INIT_z_axis_fault_reset_status.DN'),
      OTU('INIT_SetBit[1]'),
    ),
    RUNG(
      XIC('INIT_OutBit[1]'),
      CPT('NEXTSTATE', '1'),
    ),
    RUNG(
      XIC('INIT_DONE'),
      CMP('STATE=1'),
      OTE('STATE1_IND'),
    ),
    RUNG(
      XIC('STATE1_IND'),
      XIO('trigger_axes_sb'),
      OTE('trigger_axes_ob'),
    ),
    RUNG(
      XIC('STATE1_IND'),
      OTL('trigger_axes_sb'),
    ),
    RUNG(
      XIO('STATE1_IND'),
      OTU('trigger_axes_sb'),
    ),
    RUNG(
      XIC('trigger_axes_ob'),
      XIO('dont_auto_trigger_axes_in_state_1'),
      MSO('X_axis', 'x_on_mso'),
      MSO('Y_axis', 'y_on_mso'),
      MSO('Z_axis', 'z_on_mso'),
    ),
    RUNG(
      XIC('STATE1_IND'),
      MOV('0', 'ERROR_CODE'),
    ),
    RUNG(
      XIC('STATE1_IND'),
      CMP('MOVE_TYPE=1'),
      XIO('RS1_SetBit[0]'),
      OTE('RS1_OutBit[0]'),
    ),
    RUNG(
      XIC('STATE1_IND'),
      CMP('MOVE_TYPE=1'),
      OTL('RS1_SetBit[0]'),
    ),
    RUNG(
      BRANCH([XIO('STATE1_IND')], [NEQ('MOVE_TYPE', '1')]),
      OTU('RS1_SetBit[0]'),
    ),
    RUNG(
      XIC('RS1_OutBit[0]'),
      CPT('NEXTSTATE', '2'),
    ),
    RUNG(
      XIC('STATE1_IND'),
      CMP('MOVE_TYPE=2'),
      XIO('RS1_SetBit[1]'),
      OTE('RS1_OutBit[1]'),
    ),
    RUNG(
      XIC('STATE1_IND'),
      CMP('MOVE_TYPE=2'),
      OTL('RS1_SetBit[1]'),
    ),
    RUNG(
      BRANCH([XIO('STATE1_IND')], [NEQ('MOVE_TYPE', '2')]),
      OTU('RS1_SetBit[1]'),
    ),
    RUNG(
      XIC('RS1_OutBit[1]'),
      CPT('NEXTSTATE', '3'),
    ),
    RUNG(
      XIC('STATE1_IND'),
      CMP('MOVE_TYPE=3'),
      XIO('RS1_SetBit[2]'),
      OTE('RS1_OutBit[2]'),
    ),
    RUNG(
      XIC('STATE1_IND'),
      CMP('MOVE_TYPE=3'),
      OTL('RS1_SetBit[2]'),
    ),
    RUNG(
      BRANCH([XIO('STATE1_IND')], [NEQ('MOVE_TYPE', '3')]),
      OTU('RS1_SetBit[2]'),
    ),
    RUNG(
      XIC('RS1_OutBit[2]'),
      CPT('NEXTSTATE', '4'),
    ),
    RUNG(
      XIC('STATE1_IND'),
      CMP('MOVE_TYPE=4'),
      XIO('RS1_SetBit[3]'),
      OTE('RS1_OutBit[3]'),
    ),
    RUNG(
      XIC('STATE1_IND'),
      CMP('MOVE_TYPE=4'),
      OTL('RS1_SetBit[3]'),
    ),
    RUNG(
      BRANCH([XIO('STATE1_IND')], [NEQ('MOVE_TYPE', '4')]),
      OTU('RS1_SetBit[3]'),
    ),
    RUNG(
      XIC('RS1_OutBit[3]'),
      CPT('NEXTSTATE', '5'),
    ),
    RUNG(
      XIC('STATE1_IND'),
      CMP('MOVE_TYPE=5'),
      XIO('RS1_SetBit[4]'),
      OTE('RS1_OutBit[4]'),
    ),
    RUNG(
      XIC('STATE1_IND'),
      CMP('MOVE_TYPE=5'),
      OTL('RS1_SetBit[4]'),
    ),
    RUNG(
      BRANCH([XIO('STATE1_IND')], [NEQ('MOVE_TYPE', '5')]),
      OTU('RS1_SetBit[4]'),
    ),
    RUNG(
      XIC('RS1_OutBit[4]'),
      CPT('NEXTSTATE', '6'),
    ),
    RUNG(
      XIC('STATE1_IND'),
      CMP('MOVE_TYPE=6'),
      XIO('RS1_SetBit[5]'),
      OTE('RS1_OutBit[5]'),
    ),
    RUNG(
      XIC('STATE1_IND'),
      CMP('MOVE_TYPE=6'),
      OTL('RS1_SetBit[5]'),
    ),
    RUNG(
      BRANCH([XIO('STATE1_IND')], [NEQ('MOVE_TYPE', '6')]),
      OTU('RS1_SetBit[5]'),
    ),
    RUNG(
      XIC('RS1_OutBit[5]'),
      CPT('NEXTSTATE', '7'),
    ),
    RUNG(
      XIC('STATE1_IND'),
      CMP('MOVE_TYPE=7'),
      XIO('RS1_SetBit[6]'),
      OTE('RS1_OutBit[6]'),
    ),
    RUNG(
      XIC('STATE1_IND'),
      CMP('MOVE_TYPE=7'),
      OTL('RS1_SetBit[6]'),
    ),
    RUNG(
      BRANCH([XIO('STATE1_IND')], [NEQ('MOVE_TYPE', '7')]),
      OTU('RS1_SetBit[6]'),
    ),
    RUNG(
      XIC('RS1_OutBit[6]'),
      CPT('NEXTSTATE', '8'),
    ),
    RUNG(
      XIC('STATE1_IND'),
      CMP('MOVE_TYPE=8'),
      XIO('RS1_SetBit[7]'),
      OTE('RS1_OutBit[7]'),
    ),
    RUNG(
      XIC('STATE1_IND'),
      CMP('MOVE_TYPE=8'),
      OTL('RS1_SetBit[7]'),
    ),
    RUNG(
      BRANCH([XIO('STATE1_IND')], [NEQ('MOVE_TYPE', '8')]),
      OTU('RS1_SetBit[7]'),
    ),
    RUNG(
      XIC('RS1_OutBit[7]'),
      CPT('NEXTSTATE', '9'),
    ),
    RUNG(
      XIC('STATE1_IND'),
      CMP('MOVE_TYPE=11'),
      XIO('RS1_SetBit[8]'),
      OTE('RS1_OutBit[8]'),
    ),
    RUNG(
      XIC('STATE1_IND'),
      CMP('MOVE_TYPE=11'),
      OTL('RS1_SetBit[8]'),
    ),
    RUNG(
      BRANCH([XIO('STATE1_IND')], [NEQ('MOVE_TYPE', '11')]),
      OTU('RS1_SetBit[8]'),
    ),
    RUNG(
      XIC('RS1_OutBit[8]'),
      CPT('NEXTSTATE', '14'),
    ),
    RUNG(
      CMP('STATE=2'),
      CPT('NEXTSTATE', '1'),
    ),
    RUNG(
      XIO('main_xy_move.IP'),
      CMP('STATE=3'),
      BRANCH([XIC('tension_stable_timer.DN')], [XIO('check_tension_stable')], [XIO('TENSION_CONTROL_OK')]),
      BRANCH([BRANCH([XIO('Z_RETRACTED')], [GEQ('Z_axis.ActualPosition', 'MAX_TOLERABLE_Z')]), CPT('ERROR_CODE', '3001'), CPT('NEXTSTATE', '10')], [XIC('Z_RETRACTED'), BRANCH([XIC('APA_IS_VERTICAL')], [XIO('APA_IS_VERTICAL'), CPT('ERROR_CODE', '3005'), CPT('NEXTSTATE', '10')]), OTE('STATE3_IND')]),
    ),
    RUNG(
      XIC('STATE3_IND'),
      XIO('MXY_state3_entry_oneshot_storage'),
      OTE('MXY_state3_entry_oneshot'),
    ),
    RUNG(
      XIC('STATE3_IND'),
      OTL('MXY_state3_entry_oneshot_storage'),
    ),
    RUNG(
      XIO('STATE3_IND'),
      OTU('MXY_state3_entry_oneshot_storage'),
    ),
    RUNG(
      XIC('STATE3_IND'),
      BRANCH([XIC('X_Y.PhysicalAxisFault'), CPT('ERROR_CODE', '3002')], [BRANCH([XIC('X_axis.SafeTorqueOffInhibit')], [XIC('Y_axis.SafeTorqueOffInhibit')]), CPT('ERROR_CODE', '3004')]),
      CPT('NEXTSTATE', '10'),
    ),
    RUNG(
      XIC('MXY_state3_entry_oneshot'),
      BRANCH([MSO('X_axis', 'MXY_x_axis_servo_on_status')], [MSO('Y_axis', 'MXY_y_axis_servo_on_status')]),
    ),
    RUNG(
      XIC('MXY_x_axis_servo_on_status.DN'),
      XIC('MXY_y_axis_servo_on_status.DN'),
      XIO('MXY_axes_servo_ready_oneshot_storage'),
      OTE('MXY_axes_servo_ready_oneshot'),
    ),
    RUNG(
      XIC('MXY_x_axis_servo_on_status.DN'),
      XIC('MXY_y_axis_servo_on_status.DN'),
      OTL('MXY_axes_servo_ready_oneshot_storage'),
    ),
    RUNG(
      BRANCH([XIO('MXY_x_axis_servo_on_status.DN')], [XIO('MXY_y_axis_servo_on_status.DN')]),
      OTU('MXY_axes_servo_ready_oneshot_storage'),
    ),
    RUNG(
      BRANCH([XIC('MXY_axes_servo_ready_oneshot')], [XIC('MXY_x_axis_servo_on_status.DN'), XIC('MXY_y_axis_servo_on_status.DN'), XIC('MXY_state3_entry_oneshot')]),
      XIO('MXY_trigger_xy_move_oneshot_storage'),
      OTE('trigger_xy_move'),
    ),
    RUNG(
      BRANCH([XIC('MXY_axes_servo_ready_oneshot')], [XIC('MXY_x_axis_servo_on_status.DN'), XIC('MXY_y_axis_servo_on_status.DN'), XIC('MXY_state3_entry_oneshot')]),
      OTL('MXY_trigger_xy_move_oneshot_storage'),
    ),
    RUNG(
      BRANCH([XIO('MXY_axes_servo_ready_oneshot')], [BRANCH([XIO('MXY_x_axis_servo_on_status.DN')], [XIO('MXY_y_axis_servo_on_status.DN')], [XIO('MXY_state3_entry_oneshot')])]),
      OTU('MXY_trigger_xy_move_oneshot_storage'),
    ),
    RUNG(
      XIC('trigger_xy_move'),
      MOV('X_axis.ActualPosition', 'starting_x'),
      MOV('Y_axis.ActualPosition', 'starting_y'),
    ),
    RUNG(
      XIC('trigger_xy_move'),
      CPT('dx', 'ABS(starting_x-X_POSITION)'),
      CPT('dy', 'ABS(starting_y-Y_POSITION)'),
      CPT('x_time', 'v_x_max/dx'),
      CPT('y_time', 'v_y_max/dy'),
      BRANCH([LES('x_time', 'y_time'), CPT('k', 'x_time')], [LEQ('y_time', 'x_time'), CPT('k', 'y_time')]),
      CPT('v_max', 'k*SQR(dx*dx+dy*dy)'),
      BRANCH([LES('v_max', 'XY_SPEED'), CPT('XY_SPEED_REQ', 'v_max')], [LEQ('XY_SPEED', 'v_max'), CPT('XY_SPEED_REQ', 'XY_SPEED')]),
    ),
    RUNG(
      CPT('x_dist_to_target', 'X_axis.ActualPosition-X_POSITION'),
      CPT('y_dist_to_target', 'Y_axis.ActualPosition-Y_POSITION'),
      CPT('xy_dist_to_target', 'SQR(x_dist_to_target*x_dist_to_target+y_dist_to_target*y_dist_to_target)'),
    ),
    RUNG(
      MOV('xy_decel_jerk', 'J'),
      MOV('v_xyz', 'v_0'),
      CPT('gamma', 'SQR(accel_xy*accel_xy+4*J*v_0)'),
      CPT('stopping_distance', '(accel_xy+gamma)*(accel_xy+gamma)*(accel_xy+gamma)/(6*J*J)'),
    ),
    RUNG(
      CMP('xy_dist_to_target<stopping_distance*1'),
      OTE('near_ending'),
    ),
    RUNG(
      CMP('STATE=3'),
      CPT('stopping_ratio', 'stopping_distance/xy_dist_to_target'),
    ),
    RUNG(
      XIC('TENSION_CONTROL_OK'),
      XIC('speed_regulator_switch'),
      XIC('trigger_xy_move'),
      MCLM('X_Y', 'main_xy_move', '0', 'X_POSITION', 'v_max', '"Units per sec"', 'xy_regulated_acceleration', '"Units per sec2"', 'xy_regulated_deceleration', '"Units per sec2"', 'S-Curve', 'xy_regulated_accel_jerk', 'xy_decel_jerk', '"Units per sec3"', '0', 'Disabled', 'Programmed', '50', '0', 'None', '0', '0'),
    ),
    RUNG(
      XIC('TENSION_CONTROL_OK'),
      XIC('speed_regulator_switch'),
      XIC('trigger_xy_move'),
      MOV('xy_dt', 'regulator_loop_timer.PRE'),
      MOV('xy_d_dt', 'xy_d_timer.PRE'),
      MOV('0', 'xy_i_term'),
    ),
    RUNG(
      XIC('TENSION_CONTROL_OK'),
      XIC('speed_regulator_switch'),
      XIO('regulator_loop_timer.DN'),
      TON('regulator_loop_timer', '1', '0'),
    ),
    RUNG(
      XIC('TENSION_CONTROL_OK'),
      XIC('speed_regulator_switch'),
      XIO('xy_d_timer.DN'),
      TON('xy_d_timer', '1', '0'),
    ),
    RUNG(
      XIC('TENSION_CONTROL_OK'),
      XIC('speed_regulator_switch'),
      XIC('xy_d_timer.DN'),
      CPT('d_raw', 'xy_kd*(xy_error-xy_error_prev)/xy_d_dt*100'),
      CPT('xy_d_term', 'xy_d_alpha*d_raw+(1-xy_d_alpha)*xy_d_term_prev'),
      MOV('xy_error', 'xy_error_prev'),
      MOV('xy_d_term', 'xy_d_term_prev'),
    ),
    RUNG(
      XIC('TENSION_CONTROL_OK'),
      XIC('speed_regulator_switch'),
      CPT('xy_error', 'speed_tension_setpoint-tension'),
    ),
    RUNG(
      XIC('TENSION_CONTROL_OK'),
      XIC('speed_regulator_switch'),
      XIC('regulator_loop_timer.DN'),
      CPT('xy_p_term', 'xy_kp*xy_error'),
    ),
    RUNG(
      XIC('TENSION_CONTROL_OK'),
      XIC('speed_regulator_switch'),
      XIC('regulator_loop_timer.DN'),
      BRANCH([LES('regulated_speed', 'v_max')], [LES('xy_error', '0')]),
      BRANCH([GRT('regulated_speed', 'min_regulated_speed')], [GRT('xy_error', '0')]),
      CPT('xy_i_term', 'xy_i_term+(xy_ki*xy_error*xy_dt/1000)'),
      BRANCH([LES('xy_i_term', 'min_integral'), MOV('min_integral', 'xy_i_term')], [GRT('xy_i_term', 'max_integral'), MOV('max_integral', 'xy_i_term')]),
    ),
    RUNG(
      XIC('TENSION_CONTROL_OK'),
      XIC('speed_regulator_switch'),
      XIC('regulator_loop_timer.DN'),
      CPT('regulated_speed', 'xy_default_speed+xy_p_term+xy_i_term+xy_d_term'),
      BRANCH([LES('v_max', 'regulated_speed'), MOV('v_max', 'regulated_speed')], [LES('regulated_speed', 'min_regulated_speed'), MOV('min_regulated_speed', 'regulated_speed')]),
    ),
    RUNG(
      BRANCH([XIO('TENSION_CONTROL_OK')], [XIC('TENSION_CONTROL_OK'), XIO('speed_regulator_switch')]),
      XIC('trigger_xy_move'),
      MCLM('X_Y', 'main_xy_move', '0', 'X_POSITION', 'XY_SPEED_REQ', '"Units per sec"', 'XY_ACCELERATION', '"Units per sec2"', 'XY_DECELERATION', '"Units per sec2"', 'S-Curve', '500', '500', '"Units per sec3"', '0', 'Disabled', 'Programmed', '50', '0', 'None', '0', '0'),
    ),
    RUNG(
      XIO('speed_regulator_switch'),
      XIC('MXY_speed_regulator_disabled_oneshot_storage'),
      OTE('MXY_speed_regulator_disabled_oneshot'),
    ),
    RUNG(
      XIC('speed_regulator_switch'),
      OTL('MXY_speed_regulator_disabled_oneshot_storage'),
    ),
    RUNG(
      XIO('speed_regulator_switch'),
      OTU('MXY_speed_regulator_disabled_oneshot_storage'),
    ),
    RUNG(
      XIC('MXY_speed_regulator_disabled_oneshot'),
      XIO('near_ending'),
      MCCD('X_Y', 'MCCD_X_Y_Axis1', '"Coordinated Move"', 'Yes', 'XY_SPEED_REQ', '"Units per sec"', 'Yes', 'XY_ACCELERATION', '"Units per sec2"', 'Yes', 'XY_DECELERATION', '"Units per sec2"', 'No', 'xy_accel_jerk', 'No', 'xy_decel_jerk', '"Units per sec3"', '"Active Motion"'),
    ),
    RUNG(
      BRANCH([XIC('main_xy_move.PC')], [XIC('main_xy_move.ER')]),
      BRANCH([CMP('X_axis.ActualPosition<(X_POSITION+0.1)')], [XIC('STATE3_IND'), CMP('MOVE_TYPE=0'), CPT('ERROR_CODE', '3003')]),
      XIO('MXY_xy_move_done_or_fault_oneshot_storage'),
      OTE('MXY_xy_move_done_or_fault_oneshot'),
    ),
    RUNG(
      BRANCH([XIC('main_xy_move.PC')], [XIC('main_xy_move.ER')]),
      BRANCH([CMP('X_axis.ActualPosition<(X_POSITION+0.1)')], [XIC('STATE3_IND'), CMP('MOVE_TYPE=0'), CPT('ERROR_CODE', '3003')]),
      OTL('MXY_xy_move_done_or_fault_oneshot_storage'),
    ),
    RUNG(
      BRANCH([XIO('main_xy_move.PC')], [XIO('main_xy_move.ER')]),
      OTU('MXY_xy_move_done_or_fault_oneshot_storage'),
    ),
    RUNG(
      XIC('main_xy_move.IP'),
      CMP('MOVE_TYPE=11'),
      CPT('NEXTSTATE', '14'),
    ),
    RUNG(
      XIC('main_xy_move.IP'),
      XIO('ALL_EOT_GOOD'),
      XIO('MXY_eot_triggered_oneshot_storage'),
      OTE('MXY_eot_triggered'),
    ),
    RUNG(
      XIC('main_xy_move.IP'),
      XIO('ALL_EOT_GOOD'),
      OTL('MXY_eot_triggered_oneshot_storage'),
    ),
    RUNG(
      BRANCH([XIO('main_xy_move.IP')], [XIC('ALL_EOT_GOOD')]),
      OTU('MXY_eot_triggered_oneshot_storage'),
    ),
    RUNG(
      XIC('MXY_eot_triggered'),
      MCS('X_Y', 'MXY_eot_stop_status', 'All', 'Yes', '10000', '"Units per sec2"', 'Yes', '1000', '"Units per sec3"'),
      CPT('NEXTSTATE', '11'),
      CPT('MOVE_TYPE', '0'),
    ),
    RUNG(
      XIC('MXY_eot_triggered'),
      MCS('X_Y', 'MXY_eot_stop_status', 'All', 'Yes', '10000', '"Units per sec2"', 'Yes', '1000', '"Units per sec3"'),
      CPT('NEXTSTATE', '11'),
      CPT('MOVE_TYPE', '0'),
    ),
    RUNG(
      XIC('MXY_xy_move_done_or_fault_oneshot'),
      CPT('MOVE_TYPE', '0'),
      CPT('NEXTSTATE', '1'),
    ),
    RUNG(
      BRANCH([XIC('Z_FIXED_LATCHED'), EQU('ACTUATOR_POS', '2')], [XIO('Z_FIXED_LATCHED')]),
      OTE('no_latch_collision'),
    ),
    RUNG(
      BRANCH([XIC('X_XFER_OK')], [XIC('Y_XFER_OK')]),
      OTE('no_apa_collision'),
    ),
    RUNG(
      BRANCH([XIC('X_XFER_OK'), BRANCH([LIM('400', 'X_axis.ActualPosition', '500'), BRANCH([XIC('support_collision_window_bttm'), XIO('FRAME_LOC_HD_BTM')], [XIC('support_collision_window_mid'), XIO('FRAME_LOC_HD_MID')], [XIC('support_collision_window_top'), XIO('FRAME_LOC_HD_TOP')])], [LIM('7100', 'X_axis.ActualPosition', '7200'), BRANCH([XIC('support_collision_window_bttm'), XIO('FRAME_LOC_FT_BTM')], [XIC('support_collision_window_mid'), XIO('FRAME_LOC_FT_MID')], [XIC('support_collision_window_top'), XIO('FRAME_LOC_FT_TOP')])], [XIO('support_collision_window_bttm'), XIO('support_collision_window_mid'), XIO('support_collision_window_top')])], [XIC('Y_XFER_OK')]),
      OTE('no_supports_collision'),
    ),
    RUNG(
      XIC('no_latch_collision'),
      XIC('no_supports_collision'),
      XIC('no_apa_collision'),
      OTE('MASTER_Z_GO'),
    ),
    RUNG(
      CMP('STATE=4'),
      MOV('1', 'NEXTSTATE'),
    ),
    RUNG(
      CMP('STATE=5'),
      XIC('Z_FIXED_LATCHED'),
      XIC('LATCH_ACTUATOR_HOMED'),
      CMP('ACTUATOR_POS<>2'),
      CPT('ERROR_CODE', '5004'),
      CPT('NEXTSTATE', '10'),
    ),
    RUNG(
      CMP('STATE=5'),
      XIC('Z_axis.PhysicalAxisFault'),
      CPT('ERROR_CODE', '5002'),
      CPT('NEXTSTATE', '10'),
    ),
    RUNG(
      CMP('STATE=5'),
      XIO('MASTER_Z_GO'),
      CPT('ERROR_CODE', '5001'),
      CPT('NEXTSTATE', '10'),
    ),
    RUNG(
      CMP('STATE=5'),
      XIC('MASTER_Z_GO'),
      BRANCH([XIC('tension_stable_timer.DN')], [XIO('check_tension_stable')], [XIO('TENSION_CONTROL_OK')], [XIC('Z_FIXED_LATCHED')]),
      OTE('STATE5_IND'),
    ),
    RUNG(
      XIC('STATE5_IND'),
      XIO('Z_axis.DriveEnableStatus'),
      MSO('Z_axis', 'z_axis_mso'),
    ),
    RUNG(
      XIC('STATE5_IND'),
      XIC('Z_axis.DriveEnableStatus'),
      XIO('Z_FIXED_LATCHED'),
      MAM('Z_axis', 'z_axis_main_move', '0', 'Z_POSITION', 'Z_SPEED', '"Units per sec"', 'Z_ACCELERATION', '"Units per sec2"', 'Z_DECELLERATION', '"Units per sec2"', 'S-Curve', 'z_accel_jerk', 'z_decel_jerk', '"Units per sec3"', 'Disabled', 'Programmed', '0', 'None', '0', '0'),
    ),
    RUNG(
      XIC('STATE5_IND'),
      XIC('Z_axis.DriveEnableStatus'),
      XIC('Z_FIXED_LATCHED'),
      MAM('Z_axis', 'z_axis_fast_move', '0', 'Z_POSITION', '1000', '"Units per sec"', '10000', '"Units per sec2"', '10000', '"Units per sec2"', 'S-Curve', '10000', '10000', '"Units per sec3"', 'Disabled', 'Programmed', '0', 'None', '0', '0'),
    ),
    RUNG(
      XIC('Z_axis.MoveStatus'),
      CMP('MOVE_TYPE=11'),
      CPT('NEXTSTATE', '14'),
    ),
    RUNG(
      XIO('ALL_EOT_GOOD'),
      XIC('Z_axis.MoveStatus'),
      MAS('Z_axis', 'eot_stop', 'Jog', 'Yes', '2000', '"Units per sec2"', 'No', '100', '"% of Time"'),
    ),
    RUNG(
      XIC('eot_stop.PC'),
      CPT('ERROR_CODE', '5005'),
      CPT('NEXTSTATE', '11'),
      MOV('0', 'eot_stop.FLAGS'),
    ),
    RUNG(
      CMP('STATE=5'),
      CMP('ABS(Z_axis.ActualPosition-Z_POSITION)<0.1'),
      OTE('z_move_success'),
    ),
    RUNG(
      XIC('z_move_success'),
      CPT('MOVE_TYPE', '0'),
      CPT('NEXTSTATE', '1'),
      OTU('z_move_success'),
      MOV('0', 'z_axis_main_move.FLAGS'),
    ),
    RUNG(
      XIO('Local:1:I.Pt08.Data'),
      OTE('MACHINE_SW_STAT[12]'),
      OTE('LATCH_ACTUATOR_TOP'),
    ),
    RUNG(
      XIO('Local:1:I.Pt09.Data'),
      OTE('MACHINE_SW_STAT[13]'),
      OTE('LATCH_ACTUATOR_MID'),
    ),
    RUNG(
      XIC('LATCH_ACTUATOR_TOP'),
      XIO('LATCH_ACTUATOR_MID'),
      CPT('ACTUATOR_POS', '3'),
      OTE('Z_STAGE_UNLATCHED'),
    ),
    RUNG(
      XIC('LATCH_ACTUATOR_TOP'),
      XIC('LATCH_ACTUATOR_MID'),
      BRANCH([TON('delay_mid_position', '100', '0')], [XIC('delay_mid_position.DN'), CPT('ACTUATOR_POS', '2')]),
      OTE('Z_OK_TO_ENGAGE'),
    ),
    RUNG(
      XIO('LATCH_ACTUATOR_TOP'),
      XIO('LATCH_ACTUATOR_MID'),
      XIO('Z_STAGE_LATCHED'),
      CPT('ACTUATOR_POS', '0'),
    ),
    RUNG(
      XIC('Z_STAGE_LATCHED'),
      BRANCH([TON('Delay_Z_Latched', '1000', '0')], [XIC('Delay_Z_Latched.DN'), CPT('ACTUATOR_POS', '1')]),
    ),
    RUNG(
      XIC('Z_FIXED_LATCHED'),
      BRANCH([TON('Delay_Fixed_Latched', '1000', '0')], [XIC('Delay_Fixed_Latched.DN'), OTE('Z_SAFE_TO_WITHDRAW')]),
    ),
    RUNG(
      XIC('Z_STAGE_PRESENT'),
      XIC('Z_FIXED_PRESENT'),
      XIC('Z_EXTENDED'),
      OTE('ENABLE_ACTUATOR'),
    ),
    RUNG(
      CMP('STATE=6'),
      OTE('STATE6_IND'),
    ),
    RUNG(
      XIC('STATE6_IND'),
      XIO('ENABLE_ACTUATOR'),
      XIO('LAT_state6_enable_missing_oneshot_storage'),
      OTE('LAT_state6_enable_missing_oneshot'),
    ),
    RUNG(
      XIC('STATE6_IND'),
      XIO('ENABLE_ACTUATOR'),
      OTL('LAT_state6_enable_missing_oneshot_storage'),
    ),
    RUNG(
      BRANCH([XIO('STATE6_IND')], [XIC('ENABLE_ACTUATOR')]),
      OTU('LAT_state6_enable_missing_oneshot_storage'),
    ),
    RUNG(
      XIC('LAT_state6_enable_missing_oneshot'),
      CPT('ERROR_CODE', '6001'),
      CPT('NEXTSTATE', '10'),
    ),
    RUNG(
      XIC('STATE6_IND'),
      XIC('ENABLE_ACTUATOR'),
      XIO('LAT_state6_enable_present_oneshot_storage'),
      OTE('LAT_state6_enable_present_oneshot'),
    ),
    RUNG(
      XIC('STATE6_IND'),
      XIC('ENABLE_ACTUATOR'),
      OTL('LAT_state6_enable_present_oneshot_storage'),
    ),
    RUNG(
      BRANCH([XIO('STATE6_IND')], [XIO('ENABLE_ACTUATOR')]),
      OTU('LAT_state6_enable_present_oneshot_storage'),
    ),
    RUNG(
      XIC('LAT_state6_enable_present_oneshot'),
      CPT('PREV_ACT_POS', 'ACTUATOR_POS'),
    ),
    RUNG(
      XIC('LAT_state6_enable_present_oneshot_storage'),
      BRANCH([CMP('PREV_ACT_POS=1')], [CMP('PREV_ACT_POS=3')], [CMP('PREV_ACT_POS=2')], [CMP('PREV_ACT_POS=0')]),
      CPT('MOVE_TYPE', '0'),
      CPT('NEXTSTATE', '1'),
    ),
    RUNG(
      XIC('LAT_state6_enable_present_oneshot_storage'),
      XIO('Latching_pulse_interval.DN'),
      TON('Latching_pulse_duration', '10', '0'),
    ),
    RUNG(
      XIO('LAT_latching_pulse_interval_holdoff_storage'),
      XIC('Latching_pulse_duration.DN'),
      TON('Latching_pulse_interval', '250', '0'),
    ),
    RUNG(
      CMP('STATE=7'),
      OTE('STATE7_IND'),
    ),
    RUNG(
      XIC('STATE7_IND'),
      XIO('LAT_state7_entry_oneshot_storage'),
      OTE('LAT_state7_entry_oneshot'),
    ),
    RUNG(
      XIC('STATE7_IND'),
      OTL('LAT_state7_entry_oneshot_storage'),
    ),
    RUNG(
      XIO('STATE7_IND'),
      OTU('LAT_state7_entry_oneshot_storage'),
    ),
    RUNG(
      XIC('LAT_state7_entry_oneshot'),
      RES('HomeCounter'),
    ),
    RUNG(
      XIC('LAT_state7_entry_oneshot_storage'),
      XIO('HomeCounter.DN'),
      XIO('HomeTimer2.TT'),
      TON('HomeTimer1', '500', '0'),
    ),
    RUNG(
      XIC('LAT_state7_entry_oneshot_storage'),
      XIO('HomeCounter.DN'),
      XIO('HomeTimer1.TT'),
      TON('HomeTimer2', '500', '0'),
    ),
    RUNG(
      XIC('LAT_state7_entry_oneshot_storage'),
      XIO('HomeCounter.DN'),
      XIC('HomeTimer1.TT'),
      CTU('HomeCounter', '100', '0'),
    ),
    RUNG(
      XIC('HomeCounter.DN'),
      XIC('sometag'),
      OTE('Local:3:O.Pt02.Data'),
    ),
    RUNG(
      XIC('HomeCounter.DN'),
      XIO('LAT_home_counter_done_oneshot_storage'),
      OTE('LAT_home_counter_done_oneshot'),
    ),
    RUNG(
      XIC('HomeCounter.DN'),
      OTL('LAT_home_counter_done_oneshot_storage'),
    ),
    RUNG(
      XIO('HomeCounter.DN'),
      OTU('LAT_home_counter_done_oneshot_storage'),
    ),
    RUNG(
      XIC('LAT_home_counter_done_oneshot'),
      XIC('Z_STAGE_LATCHED'),
      OTL('LATCH_ACTUATOR_HOMED'),
    ),
    RUNG(
      XIC('LAT_home_counter_done_oneshot'),
      XIO('Z_STAGE_LATCHED'),
      CPT('ERROR_CODE', '7002'),
      OTL('LATCH_ACTUATOR_HOMED'),
    ),
    RUNG(
      XIC('LATCH_ACTUATOR_HOMED'),
      OTE('MACHINE_SW_STAT[0]'),
    ),
    RUNG(
      XIC('LATCH_ACTUATOR_HOMED'),
      XIO('LAT_latch_actuator_homed_oneshot_storage'),
      OTE('LAT_latch_actuator_homed_oneshot'),
    ),
    RUNG(
      XIC('LATCH_ACTUATOR_HOMED'),
      OTL('LAT_latch_actuator_homed_oneshot_storage'),
    ),
    RUNG(
      XIO('LATCH_ACTUATOR_HOMED'),
      OTU('LAT_latch_actuator_homed_oneshot_storage'),
    ),
    RUNG(
      XIC('LAT_latch_actuator_homed_oneshot'),
      RES('LatchCounter3'),
    ),
    RUNG(
      XIC('LAT_latch_actuator_homed_oneshot_storage'),
      XIO('LatchCounter3.DN'),
      XIO('LatchTimer6.TT'),
      TON('LatchTimer5', '250', '0'),
    ),
    RUNG(
      XIC('LAT_latch_actuator_homed_oneshot_storage'),
      XIO('LatchCounter3.DN'),
      XIO('LatchTimer5.TT'),
      TON('LatchTimer6', '250', '0'),
    ),
    RUNG(
      XIC('LAT_latch_actuator_homed_oneshot_storage'),
      XIO('LatchCounter3.DN'),
      XIC('LatchTimer5.TT'),
      CTU('LatchCounter3', '100', '0'),
    ),
    RUNG(
      XIC('LatchCounter3.DN'),
      XIO('LAT_home_verify_done_oneshot_storage'),
      OTE('LAT_home_verify_done_oneshot'),
    ),
    RUNG(
      XIC('LatchCounter3.DN'),
      OTL('LAT_home_verify_done_oneshot_storage'),
    ),
    RUNG(
      XIO('LatchCounter3.DN'),
      OTU('LAT_home_verify_done_oneshot_storage'),
    ),
    RUNG(
      XIC('STATE7_IND'),
      XIC('LAT_home_verify_done_oneshot'),
      CPT('ERROR_CODE', '7000'),
      OTU('HomeSignal'),
      CPT('MOVE_TYPE', '0'),
      CPT('NEXTSTATE', '1'),
    ),
    RUNG(
      BRANCH([CMP('STATE=8')], [XIC('UNLOCK_LATCH_MOTOR_SHAFT')]),
      OTE('STATE8_IND'),
    ),
    RUNG(
      XIC('STATE8_IND'),
      XIC('sometag'),
      OTE('Local:3:O.Pt02.Data'),
    ),
    RUNG(
      XIC('Local:3:O.Pt02.Data'),
      CPT('ERROR_CODE', '8000'),
    ),
    RUNG(
      XIC('STATE8_IND'),
      XIO('LAT_state8_entry_oneshot_storage'),
      OTE('LAT_state8_entry_oneshot'),
    ),
    RUNG(
      XIC('STATE8_IND'),
      OTL('LAT_state8_entry_oneshot_storage'),
    ),
    RUNG(
      XIO('STATE8_IND'),
      OTU('LAT_state8_entry_oneshot_storage'),
    ),
    RUNG(
      XIC('LAT_state8_entry_oneshot'),
      OTU('LATCH_ACTUATOR_HOMED'),
    ),
    RUNG(
      XIC('LAT_state8_entry_oneshot'),
      RES('LatchCounter2'),
    ),
    RUNG(
      XIC('LAT_state8_entry_oneshot_storage'),
      XIO('LatchCounter2.DN'),
      XIO('LatchTimer4.TT'),
      TON('LatchTimer3', '250', '0'),
    ),
    RUNG(
      XIC('LAT_state8_entry_oneshot_storage'),
      XIO('LatchCounter2.DN'),
      XIO('LatchTimer3.TT'),
      TON('LatchTimer4', '250', '0'),
    ),
    RUNG(
      XIC('LAT_state8_entry_oneshot_storage'),
      XIO('LatchCounter2.DN'),
      XIC('LatchTimer3.TT'),
      CTU('LatchCounter2', '100', '0'),
    ),
    RUNG(
      XIC('STATE8_IND'),
      XIC('LatchCounter2.DN'),
      CMP('MOVE_TYPE=0'),
      CPT('NEXTSTATE', '1'),
    ),
    RUNG(
      BRANCH([XIC('Latching_pulse_duration.TT')], [XIC('LatchTimer4.TT')], [XIC('HomeTimer2.TT')], [XIC('LatchTimer6.TT')]),
      OTE('Local:3:O.Pt01.Data'),
      OTE('latching_signal'),
    ),
    RUNG(
      XIC('Z_STAGE_PRESENT'),
      OTU('gui_latch_pulse'),
    ),
    RUNG(
      XIC('Z_STAGE_PRESENT'),
      XIO('Z_FIXED_PRESENT'),
      OTE('unsafe_to_latch'),
    ),
    RUNG(
      XIC('gui_latch_pulse'),
      XIO('unsafe_to_latch'),
      OTL('Local:3:O.Pt01.Data'),
      TON('gui_latch_pulse_timer', '100', '0'),
    ),
    RUNG(
      XIC('gui_latch_pulse_timer.DN'),
      RES('gui_latch_pulse_timer'),
      OTU('gui_latch_pulse'),
    ),
    RUNG(
      BRANCH([CMP('STATE=6')], [CMP('STATE=7')]),
      XIO('LAT_latching_timeout_monitor_oneshot_storage'),
      OTE('LAT_latching_timeout_monitor_oneshot'),
    ),
    RUNG(
      BRANCH([CMP('STATE=6')], [CMP('STATE=7')]),
      OTL('LAT_latching_timeout_monitor_oneshot_storage'),
    ),
    RUNG(
      BRANCH([NEQ('STATE', '6')], [NEQ('STATE', '7')]),
      OTU('LAT_latching_timeout_monitor_oneshot_storage'),
    ),
    RUNG(
      XIC('LAT_latching_timeout_monitor_oneshot'),
      RES('LatchingTimeoutCounter'),
    ),
    RUNG(
      XIC('LAT_latching_timeout_monitor_oneshot_storage'),
      XIO('LatchingTimeoutCounter.DN'),
      XIO('TimeoutTimer2.TT'),
      TON('TimeoutTimer1', '250', '0'),
    ),
    RUNG(
      XIC('LAT_latching_timeout_monitor_oneshot_storage'),
      XIO('LatchingTimeoutCounter.DN'),
      XIO('TimeoutTimer1.TT'),
      TON('TimeoutTimer2', '250', '0'),
    ),
    RUNG(
      XIC('LAT_latching_timeout_monitor_oneshot_storage'),
      XIO('LatchingTimeoutCounter.DN'),
      XIC('TimeoutTimer1.TT'),
      CTU('LatchingTimeoutCounter', '100', '0'),
    ),
    RUNG(
      XIC('LatchingTimeoutCounter.DN'),
      XIO('LAT_latching_timeout_done_oneshot_storage'),
      OTE('LAT_latching_timeout_done_oneshot'),
    ),
    RUNG(
      XIC('LatchingTimeoutCounter.DN'),
      OTL('LAT_latching_timeout_done_oneshot_storage'),
    ),
    RUNG(
      XIO('LatchingTimeoutCounter.DN'),
      OTU('LAT_latching_timeout_done_oneshot_storage'),
    ),
    RUNG(
      XIC('LAT_latching_timeout_done_oneshot'),
      CMP('STATE=6'),
      CPT('ERROR_CODE', '6002'),
      CPT('NEXTSTATE', '10'),
    ),
    RUNG(
      XIC('INIT_DONE'),
      CMP('STATE=9'),
      OTE('STATE9_IND'),
    ),
    RUNG(
      XIC('STATE9_IND'),
      XIO('US9_state9_entry_oneshot_storage'),
      OTE('US9_state9_entry_oneshot'),
    ),
    RUNG(
      XIC('STATE9_IND'),
      OTL('US9_state9_entry_oneshot_storage'),
    ),
    RUNG(
      XIO('STATE9_IND'),
      OTU('US9_state9_entry_oneshot_storage'),
    ),
    RUNG(
      XIC('STATE9_IND'),
      XIC('US9_state9_entry_oneshot'),
      MSF('X_axis', 'US9_x_axis_unservo_status'),
    ),
    RUNG(
      XIC('STATE9_IND'),
      XIC('US9_state9_entry_oneshot'),
      MSF('Y_axis', 'US9_y_axis_unservo_status'),
    ),
    RUNG(
      XIC('STATE9_IND'),
      XIC('US9_state9_entry_oneshot'),
      MSF('Z_axis', 'US9_z_axis_unservo_status'),
    ),
    RUNG(
      XIC('US9_x_axis_unservo_status.DN'),
      XIO('US9_x_unservo_done_oneshot_storage'),
      OTE('US9_x_unservo_done_oneshot'),
    ),
    RUNG(
      XIC('US9_x_axis_unservo_status.DN'),
      OTL('US9_x_unservo_done_oneshot_storage'),
    ),
    RUNG(
      XIO('US9_x_axis_unservo_status.DN'),
      OTU('US9_x_unservo_done_oneshot_storage'),
    ),
    RUNG(
      XIC('US9_x_unservo_done_oneshot'),
      MAFR('X_axis', 'US9_x_axis_fault_reset_status'),
    ),
    RUNG(
      XIC('US9_y_axis_unservo_status.DN'),
      XIO('US9_y_unservo_done_oneshot_storage'),
      OTE('US9_y_unservo_done_oneshot'),
    ),
    RUNG(
      XIC('US9_y_axis_unservo_status.DN'),
      OTL('US9_y_unservo_done_oneshot_storage'),
    ),
    RUNG(
      XIO('US9_y_axis_unservo_status.DN'),
      OTU('US9_y_unservo_done_oneshot_storage'),
    ),
    RUNG(
      XIC('US9_y_unservo_done_oneshot'),
      MAFR('Y_axis', 'US9_y_axis_fault_reset_status'),
    ),
    RUNG(
      XIC('US9_z_axis_unservo_status.DN'),
      XIO('US9_z_unservo_done_oneshot_storage'),
      OTE('US9_z_unservo_done_oneshot'),
    ),
    RUNG(
      XIC('US9_z_axis_unservo_status.DN'),
      OTL('US9_z_unservo_done_oneshot_storage'),
    ),
    RUNG(
      XIO('US9_z_axis_unservo_status.DN'),
      OTU('US9_z_unservo_done_oneshot_storage'),
    ),
    RUNG(
      XIC('US9_z_unservo_done_oneshot'),
      MAFR('Z_axis', 'US9_z_axis_fault_reset_status'),
    ),
    RUNG(
      XIC('STATE9_IND'),
      XIC('US9_x_axis_fault_reset_status.DN'),
      XIC('US9_y_axis_fault_reset_status.DN'),
      XIC('US9_z_axis_fault_reset_status.DN'),
      CMP('MOVE_TYPE=0'),
      CPT('NEXTSTATE', '1'),
    ),
    RUNG(
      XIC('INIT_DONE'),
      CMP('STATE=10'),
      OTE('STATE10_IND'),
    ),
    RUNG(
      XIC('STATE10_IND'),
      XIO('ERR10_state10_entry_oneshot_storage'),
      OTE('ERR10_state10_entry_oneshot'),
    ),
    RUNG(
      XIC('STATE10_IND'),
      OTL('ERR10_state10_entry_oneshot_storage'),
    ),
    RUNG(
      XIO('STATE10_IND'),
      OTU('ERR10_state10_entry_oneshot_storage'),
    ),
    RUNG(
      XIC('ERR10_state10_entry_oneshot'),
      MCS('X_Y', 'ERR10_xy_group_stop_status', 'All', 'Yes', '1000', '"Units per sec2"', 'Yes', '1000', '"Units per sec3"'),
    ),
    RUNG(
      XIC('ERR10_state10_entry_oneshot'),
      MAS('Z_axis', 'ERR10_z_axis_stop_status', 'All', 'Yes', '1000', '"Units per sec2"', 'No', '10000', '"% of Time"'),
    ),
    RUNG(
      XIC('ERR10_xy_group_stop_status.PC'),
      XIC('ERR10_z_axis_stop_status.PC'),
      XIO('ERR10_motion_stop_done_oneshot_storage'),
      OTE('ERR10_motion_stop_done_oneshot'),
    ),
    RUNG(
      XIC('ERR10_xy_group_stop_status.PC'),
      XIC('ERR10_z_axis_stop_status.PC'),
      OTL('ERR10_motion_stop_done_oneshot_storage'),
    ),
    RUNG(
      BRANCH([XIO('ERR10_xy_group_stop_status.PC')], [XIO('ERR10_z_axis_stop_status.PC')]),
      OTU('ERR10_motion_stop_done_oneshot_storage'),
    ),
    RUNG(
      XIC('ERR10_motion_stop_done_oneshot'),
      XIC('error_servo_off'),
      MSF('X_axis', 'ERR10_x_axis_unservo_status'),
    ),
    RUNG(
      XIC('ERR10_motion_stop_done_oneshot'),
      XIC('error_servo_off'),
      MSF('Y_axis', 'ERR10_y_axis_unservo_status'),
    ),
    RUNG(
      XIC('ERR10_motion_stop_done_oneshot'),
      XIC('error_servo_off'),
      MSF('Z_axis', 'ERR10_z_axis_unservo_status'),
    ),
    RUNG(
      XIC('ERR10_x_axis_unservo_status.DN'),
      XIC('ERR10_y_axis_unservo_status.DN'),
      XIC('ERR10_z_axis_unservo_status.DN'),
      CMP('MOVE_TYPE=0'),
      XIO('ERR10_servo_off_done_oneshot_storage'),
      OTE('ERR10_servo_off_done_oneshot'),
    ),
    RUNG(
      XIC('ERR10_x_axis_unservo_status.DN'),
      XIC('ERR10_y_axis_unservo_status.DN'),
      XIC('ERR10_z_axis_unservo_status.DN'),
      CMP('MOVE_TYPE=0'),
      OTL('ERR10_servo_off_done_oneshot_storage'),
    ),
    RUNG(
      BRANCH([XIO('ERR10_x_axis_unservo_status.DN')], [XIO('ERR10_y_axis_unservo_status.DN')], [XIO('ERR10_z_axis_unservo_status.DN')], [NEQ('MOVE_TYPE', '0')]),
      OTU('ERR10_servo_off_done_oneshot_storage'),
    ),
    RUNG(
      XIC('ERR10_servo_off_done_oneshot'),
      MAFR('Z_axis', 'ERR10_z_axis_fault_reset_status'),
    ),
    RUNG(
      XIC('ERR10_z_axis_fault_reset_status.DN'),
      MAFR('Y_axis', 'ERR10_y_axis_fault_reset_status'),
    ),
    RUNG(
      XIC('ERR10_y_axis_fault_reset_status.DN'),
      MAFR('X_axis', 'ERR10_x_axis_fault_reset_status'),
    ),
    RUNG(
      XIC('ERR10_z_axis_unservo_status.DN'),
      XIC('ERR10_y_axis_unservo_status.DN'),
      XIC('ERR10_x_axis_unservo_status.DN'),
      CMP('MOVE_TYPE=0'),
      CMP('STATE=10'),
      CPT('ERROR_CODE', '0'),
      CPT('NEXTSTATE', '1'),
    ),
    RUNG(
      XIO('ALL_EOT_GOOD'),
      OTE('STATE11_IND'),
    ),
    RUNG(
      XIC('STATE11_IND'),
      XIO('EOT11_state11_entry_oneshot_storage'),
      OTE('EOT11_state11_entry_oneshot'),
    ),
    RUNG(
      XIC('STATE11_IND'),
      OTL('EOT11_state11_entry_oneshot_storage'),
    ),
    RUNG(
      XIO('STATE11_IND'),
      OTU('EOT11_state11_entry_oneshot_storage'),
    ),
    RUNG(
      XIC('EOT11_state11_entry_oneshot'),
      MCS('X_Y', 'EOT11_xy_group_stop_status', 'All', 'Yes', '10000', '"Units per sec2"', 'Yes', '10000', '"Units per sec3"'),
    ),
    RUNG(
      XIC('STATE11_IND'),
      XIC('EOT11_xy_group_stop_status.DN'),
      XIO('EOT11_axes_stopped_oneshot_storage'),
      OTE('EOT11_axes_stopped_oneshot'),
    ),
    RUNG(
      XIC('STATE11_IND'),
      XIC('EOT11_xy_group_stop_status.DN'),
      OTL('EOT11_axes_stopped_oneshot_storage'),
    ),
    RUNG(
      BRANCH([XIO('STATE11_IND')], [XIO('EOT11_xy_group_stop_status.DN')]),
      OTU('EOT11_axes_stopped_oneshot_storage'),
    ),
    RUNG(
      XIC('EOT11_axes_stopped_oneshot'),
      MSO('X_axis', 'EOT11_x_axis_servo_on_status'),
      MSO('Y_axis', 'EOT11_y_axis_servo_on_status'),
      MSO('Z_axis', 'EOT11_z_axis_servo_on_status'),
    ),
    RUNG(
      XIC('EOT11_state11_entry_oneshot'),
      MAS('X_axis', 'EOT11_x_axis_abort_status', 'All', 'Yes', '1000', '"Units per sec2"', 'Yes', '1000', '"Units per sec3"'),
    ),
    RUNG(
      XIC('EOT11_state11_entry_oneshot'),
      MAS('Y_axis', 'EOT11_y_axis_abort_status', 'All', 'Yes', '1000', '"Units per sec2"', 'Yes', '1000', '"Units per sec3"'),
    ),
    RUNG(
      XIC('EOT11_state11_entry_oneshot'),
      MAS('Z_axis', 'EOT11_z_axis_abort_status', 'All', 'Yes', '1000', '"Units per sec2"', 'Yes', '1000', '"Units per sec3"'),
    ),
    RUNG(
      XIC('STATE11_IND'),
      OTE('AbortQueue'),
    ),
    RUNG(
      XIC('STATE11_IND'),
      CPT('MOVE_TYPE', '0'),
    ),
    RUNG(
      XIC('STATE11_IND'),
      XIC('EOT11_xy_group_stop_status.DN'),
      XIC('EOT11_x_axis_servo_on_status.DN'),
      XIC('EOT11_y_axis_servo_on_status.DN'),
      XIC('EOT11_z_axis_servo_on_status.DN'),
      XIO('PLUS_X_EOT'),
      XIC('MINUS_X_EOT'),
      XIO('EOT11_minus_x_recovery_move_status.IP'),
      XIO('EOT11_minus_x_recovery_oneshot_storage'),
      OTE('EOT11_minus_x_recovery_oneshot'),
    ),
    RUNG(
      XIC('STATE11_IND'),
      XIC('EOT11_xy_group_stop_status.DN'),
      XIC('EOT11_x_axis_servo_on_status.DN'),
      XIC('EOT11_y_axis_servo_on_status.DN'),
      XIC('EOT11_z_axis_servo_on_status.DN'),
      XIO('PLUS_X_EOT'),
      XIC('MINUS_X_EOT'),
      XIO('EOT11_minus_x_recovery_move_status.IP'),
      OTL('EOT11_minus_x_recovery_oneshot_storage'),
    ),
    RUNG(
      BRANCH([XIO('STATE11_IND')], [XIO('EOT11_xy_group_stop_status.DN')], [XIO('EOT11_x_axis_servo_on_status.DN')], [XIO('EOT11_y_axis_servo_on_status.DN')], [XIO('EOT11_z_axis_servo_on_status.DN')], [XIC('PLUS_X_EOT')], [XIO('MINUS_X_EOT')], [XIC('EOT11_minus_x_recovery_move_status.IP')]),
      OTU('EOT11_minus_x_recovery_oneshot_storage'),
    ),
    RUNG(
      XIC('EOT11_minus_x_recovery_oneshot'),
      MAM('X_axis', 'EOT11_minus_x_recovery_move_status', '1', '-1', '25', '"Units per sec"', '100', '"Units per sec2"', '100', '"Units per sec2"', 'S-Curve', '100', '100', '"% of Time"', 'Disabled', '0', '0', '0', '0', '0'),
    ),
    RUNG(
      XIC('STATE11_IND'),
      XIC('EOT11_xy_group_stop_status.DN'),
      XIC('EOT11_x_axis_servo_on_status.DN'),
      XIC('EOT11_y_axis_servo_on_status.DN'),
      XIC('EOT11_z_axis_servo_on_status.DN'),
      XIO('MINUS_X_EOT'),
      XIC('PLUS_X_EOT'),
      XIO('EOT11_plus_x_recovery_move_status.IP'),
      XIO('EOT11_plus_x_recovery_oneshot_storage'),
      OTE('EOT11_plus_x_recovery_oneshot'),
    ),
    RUNG(
      XIC('STATE11_IND'),
      XIC('EOT11_xy_group_stop_status.DN'),
      XIC('EOT11_x_axis_servo_on_status.DN'),
      XIC('EOT11_y_axis_servo_on_status.DN'),
      XIC('EOT11_z_axis_servo_on_status.DN'),
      XIO('MINUS_X_EOT'),
      XIC('PLUS_X_EOT'),
      XIO('EOT11_plus_x_recovery_move_status.IP'),
      OTL('EOT11_plus_x_recovery_oneshot_storage'),
    ),
    RUNG(
      BRANCH([XIO('STATE11_IND')], [XIO('EOT11_xy_group_stop_status.DN')], [XIO('EOT11_x_axis_servo_on_status.DN')], [XIO('EOT11_y_axis_servo_on_status.DN')], [XIO('EOT11_z_axis_servo_on_status.DN')], [XIC('MINUS_X_EOT')], [XIO('PLUS_X_EOT')], [XIC('EOT11_plus_x_recovery_move_status.IP')]),
      OTU('EOT11_plus_x_recovery_oneshot_storage'),
    ),
    RUNG(
      XIC('EOT11_plus_x_recovery_oneshot'),
      MAM('X_axis', 'EOT11_plus_x_recovery_move_status', '1', '10', '25', '"Units per sec"', '100', '"Units per sec2"', '100', '"Units per sec2"', 'S-Curve', '100', '100', '"% of Time"', 'Disabled', '0', '0', '0', '0', '0'),
    ),
    RUNG(
      XIC('STATE11_IND'),
      XIC('EOT11_xy_group_stop_status.DN'),
      XIC('EOT11_x_axis_servo_on_status.DN'),
      XIC('EOT11_y_axis_servo_on_status.DN'),
      XIC('EOT11_z_axis_servo_on_status.DN'),
      XIO('PLUS_Y_EOT'),
      XIC('MINUS_Y_EOT'),
      XIO('EOT11_minus_y_recovery_move_status.IP'),
      XIO('EOT11_minus_y_recovery_oneshot_storage'),
      OTE('EOT11_minus_y_recovery_oneshot'),
    ),
    RUNG(
      XIC('STATE11_IND'),
      XIC('EOT11_xy_group_stop_status.DN'),
      XIC('EOT11_x_axis_servo_on_status.DN'),
      XIC('EOT11_y_axis_servo_on_status.DN'),
      XIC('EOT11_z_axis_servo_on_status.DN'),
      XIO('PLUS_Y_EOT'),
      XIC('MINUS_Y_EOT'),
      XIO('EOT11_minus_y_recovery_move_status.IP'),
      OTL('EOT11_minus_y_recovery_oneshot_storage'),
    ),
    RUNG(
      BRANCH([XIO('STATE11_IND')], [XIO('EOT11_xy_group_stop_status.DN')], [XIO('EOT11_x_axis_servo_on_status.DN')], [XIO('EOT11_y_axis_servo_on_status.DN')], [XIO('EOT11_z_axis_servo_on_status.DN')], [XIC('PLUS_Y_EOT')], [XIO('MINUS_Y_EOT')], [XIC('EOT11_minus_y_recovery_move_status.IP')]),
      OTU('EOT11_minus_y_recovery_oneshot_storage'),
    ),
    RUNG(
      XIC('EOT11_minus_y_recovery_oneshot'),
      MAM('Y_axis', 'EOT11_minus_y_recovery_move_status', '1', '-1', '25', '"Units per sec"', '100', '"Units per sec2"', '100', '"Units per sec2"', 'S-Curve', '100', '100', '"% of Time"', 'Disabled', '0', '0', '0', '0', '0'),
    ),
    RUNG(
      XIC('STATE11_IND'),
      XIC('EOT11_xy_group_stop_status.DN'),
      XIC('EOT11_x_axis_servo_on_status.DN'),
      XIC('EOT11_y_axis_servo_on_status.DN'),
      XIC('EOT11_z_axis_servo_on_status.DN'),
      XIO('MINUS_Y_EOT'),
      XIC('PLUS_Y_EOT'),
      XIO('EOT11_plus_y_recovery_move_status.IP'),
      XIO('EOT11_plus_y_recovery_oneshot_storage'),
      OTE('EOT11_plus_y_recovery_oneshot'),
    ),
    RUNG(
      XIC('STATE11_IND'),
      XIC('EOT11_xy_group_stop_status.DN'),
      XIC('EOT11_x_axis_servo_on_status.DN'),
      XIC('EOT11_y_axis_servo_on_status.DN'),
      XIC('EOT11_z_axis_servo_on_status.DN'),
      XIO('MINUS_Y_EOT'),
      XIC('PLUS_Y_EOT'),
      XIO('EOT11_plus_y_recovery_move_status.IP'),
      OTL('EOT11_plus_y_recovery_oneshot_storage'),
    ),
    RUNG(
      BRANCH([XIO('STATE11_IND')], [XIO('EOT11_xy_group_stop_status.DN')], [XIO('EOT11_x_axis_servo_on_status.DN')], [XIO('EOT11_y_axis_servo_on_status.DN')], [XIO('EOT11_z_axis_servo_on_status.DN')], [XIC('MINUS_Y_EOT')], [XIO('PLUS_Y_EOT')], [XIC('EOT11_plus_y_recovery_move_status.IP')]),
      OTU('EOT11_plus_y_recovery_oneshot_storage'),
    ),
    RUNG(
      XIC('EOT11_plus_y_recovery_oneshot'),
      MAM('Y_axis', 'EOT11_plus_y_recovery_move_status', '1', '1', '25', '"Units per sec"', '100', '"Units per sec2"', '100', '"Units per sec2"', 'S-Curve', '100', '100', '"% of Time"', 'Disabled', '0', '0', '0', '0', '0'),
    ),
    RUNG(
      XIC('STATE11_IND'),
      XIC('EOT11_xy_group_stop_status.DN'),
      XIC('EOT11_x_axis_servo_on_status.DN'),
      XIC('EOT11_y_axis_servo_on_status.DN'),
      XIC('EOT11_z_axis_servo_on_status.DN'),
      XIO('Z_EOT'),
      XIO('EOT11_z_clearance_move_status.IP'),
      XIO('EOT11_z_clearance_move_oneshot_storage'),
      OTE('EOT11_z_clearance_move_oneshot'),
    ),
    RUNG(
      XIC('STATE11_IND'),
      XIC('EOT11_xy_group_stop_status.DN'),
      XIC('EOT11_x_axis_servo_on_status.DN'),
      XIC('EOT11_y_axis_servo_on_status.DN'),
      XIC('EOT11_z_axis_servo_on_status.DN'),
      XIO('Z_EOT'),
      XIO('EOT11_z_clearance_move_status.IP'),
      OTL('EOT11_z_clearance_move_oneshot_storage'),
    ),
    RUNG(
      BRANCH([XIO('STATE11_IND')], [XIO('EOT11_xy_group_stop_status.DN')], [XIO('EOT11_x_axis_servo_on_status.DN')], [XIO('EOT11_y_axis_servo_on_status.DN')], [XIO('EOT11_z_axis_servo_on_status.DN')], [XIC('Z_EOT')], [XIC('EOT11_z_clearance_move_status.IP')]),
      OTU('EOT11_z_clearance_move_oneshot_storage'),
    ),
    RUNG(
      XIC('EOT11_z_clearance_move_oneshot'),
      MAM('Z_axis', 'EOT11_z_clearance_move_status', '0', '0', '25', '"Units per sec"', '100', '"Units per sec2"', '100', '"Units per sec2"', 'S-Curve', '100', '100', '"% of Time"', 'Disabled', '0', '0', '0', '0', '0'),
    ),
    RUNG(
      XIC('ALL_EOT_GOOD'),
      XIO('EOT11_z_clearance_move_status.IP'),
      XIO('EOT11_all_eot_good_oneshot_storage'),
      OTE('EOT11_all_eot_good_oneshot'),
    ),
    RUNG(
      XIC('ALL_EOT_GOOD'),
      XIO('EOT11_z_clearance_move_status.IP'),
      OTL('EOT11_all_eot_good_oneshot_storage'),
    ),
    RUNG(
      BRANCH([XIO('ALL_EOT_GOOD')], [XIC('EOT11_z_clearance_move_status.IP')]),
      OTU('EOT11_all_eot_good_oneshot_storage'),
    ),
    RUNG(
      XIC('EOT11_all_eot_good_oneshot'),
      MAS('X_axis', 'EOT11_x_axis_recovery_stop_a_status', 'Move', 'No', '1000', '"Units per sec2"', 'Yes', '1000', '"Units per sec3"'),
    ),
    RUNG(
      XIC('EOT11_all_eot_good_oneshot'),
      MAS('X_axis', 'EOT11_x_axis_recovery_stop_b_status', 'Move', 'No', '1000', '"Units per sec2"', 'Yes', '1000', '"Units per sec3"'),
    ),
    RUNG(
      XIC('EOT11_all_eot_good_oneshot'),
      MAS('Y_axis', 'EOT11_y_axis_recovery_stop_a_status', 'Move', 'No', '1000', '"Units per sec2"', 'Yes', '1000', '"Units per sec3"'),
    ),
    RUNG(
      XIC('EOT11_all_eot_good_oneshot'),
      MAS('Y_axis', 'EOT11_y_axis_recovery_stop_b_status', 'Move', 'No', '1000', '"Units per sec2"', 'Yes', '1000', '"Units per sec3"'),
    ),
    RUNG(
      XIC('EOT11_all_eot_good_oneshot'),
      MAS('Z_axis', 'EOT11_z_axis_recovery_stop_status', 'Move', 'No', '1000', '"Units per sec2"', 'Yes', '1000', '"Units per sec3"'),
    ),
    RUNG(
      XIC('EOT11_all_eot_good_oneshot'),
      CPT('ERROR_CODE', '0'),
      CPT('NEXTSTATE', '1'),
    ),
    RUNG(
      CMP('STATE=12'),
      OTE('STATE12_IND'),
    ),
    RUNG(
      XIC('STATE12_IND'),
      XIO('Y_XFER_OK'),
      CPT('ERROR_CODE', '5003'),
      CPT('MOVE_TYPE', '0'),
      CPT('NEXTSTATE', '10'),
    ),
    RUNG(
      XIC('STATE12_IND'),
      XIC('Y_XFER_OK'),
      XIO('xz_main_move.IP'),
      MCLM('xz', 'xz_main_move', '0', 'xz_position_target', '800', '"Units per sec"', '1000', '"Units per sec2"', '1000', '"Units per sec2"', 'S-Curve', '1000', '1000', '"Units per sec3"', '0', '0', '0', '0', '0', '0', '0', '0'),
    ),
    RUNG(
      XIO('Y_XFER_OK'),
      XIC('xz_main_move.IP'),
      MCS('X_Y', 'XZ_xy_stop', 'All', 'Yes', '4000', '"Units per sec2"', 'Yes', '2000', '"Units per sec3"'),
      MCS('xz', 'xz_stop', 'All', 'Yes', '4000', '"Units per sec2"', 'Yes', '200', '"Units per sec3"'),
      CPT('MOVE_TYPE', '0'),
      CPT('ERROR_CODE', '5003'),
      CPT('NEXTSTATE', '10'),
    ),
    RUNG(
      XIC('STATE12_IND'),
      XIC('xz_main_move.ER'),
      CPT('MOVE_TYPE', '0'),
      CPT('ERROR_CODE', '5003'),
      CPT('NEXTSTATE', '10'),
    ),
    RUNG(
      XIC('STATE12_IND'),
      CMP('ABS(X_axis.ActualPosition-xz_position_target[0])<0.1'),
      CMP('ABS(Z_axis.ActualPosition-xz_position_target[1])<0.1'),
      CPT('MOVE_TYPE', '0'),
      CPT('NEXTSTATE', '1'),
    ),
    RUNG(
      XIC('Y_axis.MoveStatus'),
      XIO('Z_RETRACTED'),
      MAS('Y_axis', 'y_axis_stop', 'All', 'Yes', '4000', '"Units per sec2"', 'Yes', '4000', '"Units per sec3"'),
    ),
    RUNG(
      CMP('STATE=13'),
      OTE('YZ_STATE13_IND'),
    ),
    RUNG(
      XIC('YZ_STATE13_IND'),
      XIO('X_XFER_OK'),
      CPT('ERROR_CODE', '5003'),
      CPT('MOVE_TYPE', '0'),
      CPT('NEXTSTATE', '10'),
    ),
    RUNG(
      XIC('YZ_STATE13_IND'),
      XIC('X_XFER_OK'),
      XIO('yz_main_move.IP'),
      MCLM('xz', 'yz_main_move', '0', 'xz_position_target', '800', '"Units per sec"', '1000', '"Units per sec2"', '1000', '"Units per sec2"', 'S-Curve', '1000', '1000', '"Units per sec3"', '0', '0', '0', '0', '0', '0', '0', '0'),
    ),
    RUNG(
      XIO('Y_XFER_OK'),
      XIC('yz_main_move.IP'),
      MCS('X_Y', 'YZ_xy_stop', 'All', 'Yes', '4000', '"Units per sec2"', 'Yes', '2000', '"Units per sec3"'),
      MCS('xz', 'yz_stop', 'All', 'Yes', '4000', '"Units per sec2"', 'Yes', '200', '"Units per sec3"'),
      CPT('MOVE_TYPE', '0'),
      CPT('ERROR_CODE', '5003'),
      CPT('NEXTSTATE', '10'),
    ),
    RUNG(
      XIC('YZ_STATE13_IND'),
      XIC('yz_main_move.ER'),
      CPT('MOVE_TYPE', '0'),
      CPT('ERROR_CODE', '5003'),
      CPT('NEXTSTATE', '10'),
    ),
    RUNG(
      XIC('YZ_STATE13_IND'),
      CMP('ABS(X_axis.ActualPosition-xz_position_target[0])<0.1'),
      CMP('ABS(Z_axis.ActualPosition-xz_position_target[1])<0.1'),
      CPT('MOVE_TYPE', '0'),
      CPT('NEXTSTATE', '1'),
    ),
    RUNG(
      XIC('X_axis.MoveStatus'),
      XIO('Z_RETRACTED'),
      MAS('X_axis', 'x_axis_stop', 'All', 'Yes', '4000', '"Units per sec2"', 'Yes', '4000', '"Units per sec3"'),
    ),
    RUNG(
      CMP('STATE=14'),
      OTE('STATE14_IND'),
    ),
    RUNG(
      XIC('STATE14_IND'),
      XIO('hmi_stop_entry_sb'),
      OTE('hmi_stop_entry_ob'),
    ),
    RUNG(
      XIC('STATE14_IND'),
      OTL('hmi_stop_entry_sb'),
    ),
    RUNG(
      XIO('STATE14_IND'),
      OTU('hmi_stop_entry_sb'),
    ),
    RUNG(
      XIC('hmi_stop_entry_ob'),
      MCS('X_Y', 'hmi_xy_stop', 'All', 'Yes', '1200', '"Units per sec2"', 'Yes', '1200', '"Units per sec3"'),
    ),
    RUNG(
      XIC('hmi_stop_entry_ob'),
      MCS('xz', 'hmi_xz_stop', 'All', 'Yes', '1200', '"Units per sec2"', 'Yes', '1200', '"Units per sec3"'),
    ),
    RUNG(
      XIC('hmi_stop_entry_ob'),
      MAS('X_axis', 'hmi_x_axis_stop', 'All', 'Yes', '1200', '"Units per sec2"', 'Yes', '1200', '"Units per sec3"'),
    ),
    RUNG(
      XIC('hmi_stop_entry_ob'),
      MAS('Y_axis', 'hmi_y_axis_stop', 'All', 'Yes', '1200', '"Units per sec2"', 'Yes', '1200', '"Units per sec3"'),
    ),
    RUNG(
      XIC('hmi_stop_entry_ob'),
      MAS('Z_axis', 'hmi_z_axis_stop', 'All', 'Yes', '1200', '"Units per sec2"', 'Yes', '1200', '"Units per sec3"'),
    ),
    RUNG(
      XIC('STATE14_IND'),
      OTE('AbortQueue'),
    ),
    RUNG(
      XIC('STATE14_IND'),
      CPT('MOVE_TYPE', '0'),
    ),
    RUNG(
      XIC('STATE14_IND'),
      XIC('hmi_xy_stop.DN'),
      XIC('hmi_xz_stop.DN'),
      XIC('hmi_x_axis_stop.DN'),
      XIC('hmi_y_axis_stop.DN'),
      XIC('hmi_z_axis_stop.DN'),
      XIO('CurIssued'),
      XIO('NextIssued'),
      XIO('X_Y.MovePendingStatus'),
      LEQ('QueueCount', '0'),
      CPT('NEXTSTATE', '1'),
    ),
    RUNG(
      EQU('QueueCtl.POS', '0'),
      OTE('QueueEmpty'),
    ),
    RUNG(
      GEQ('QueueCtl.POS', '32'),
      OTE('QueueFull'),
    ),
    RUNG(
      MOV('QueueCtl.POS', 'QueueCount'),
    ),
    RUNG(
      CMP('MOVE_TYPE=11'),
      OTL('AbortQueue'),
      CPT('NEXTSTATE', '14'),
    ),
    RUNG(
      XIC('QueueStopRequest'),
      BRANCH([XIC('CurIssued')], [XIC('NextIssued')], [XIC('X_Y.MovePendingStatus')]),
      ONS('QueueStopReqONS'),
      MCS('X_Y', 'gui_stop', 'All', 'Yes', '2000', '"Units per sec2"', 'Yes', '1000', '"Units per sec3"'),
    ),
    RUNG(
      XIC('QueueStopRequest'),
      OTL('AbortQueue'),
    ),
    RUNG(
      BRANCH([XIC('AbortQueue')], [XIO('ALL_EOT_GOOD')]),
      OTE('AbortActive'),
    ),
    RUNG(
      NEQ('IncomingSegReqID', 'LastIncomingSegReqID'),
      OTL('EnqueueReq'),
    ),
    RUNG(
      XIC('EnqueueReq'),
      XIC('IncomingSeg.Valid'),
      EQU('IncomingSeg.SegType', '1'),
      GRT('IncomingSeg.Speed', '0.0'),
      GRT('IncomingSeg.Accel', '0.0'),
      GRT('IncomingSeg.Decel', '0.0'),
      GEQ('IncomingSeg.TermType', '0'),
      LEQ('IncomingSeg.TermType', '6'),
      OTE('SegValidLine'),
    ),
    RUNG(
      XIC('EnqueueReq'),
      XIC('IncomingSeg.Valid'),
      EQU('IncomingSeg.SegType', '2'),
      GRT('IncomingSeg.Speed', '0.0'),
      GRT('IncomingSeg.Accel', '0.0'),
      GRT('IncomingSeg.Decel', '0.0'),
      GEQ('IncomingSeg.TermType', '0'),
      LEQ('IncomingSeg.TermType', '6'),
      GEQ('IncomingSeg.CircleType', '0'),
      LEQ('IncomingSeg.CircleType', '3'),
      GEQ('IncomingSeg.Direction', '0'),
      LEQ('IncomingSeg.Direction', '3'),
      OTE('SegValidArc'),
    ),
    RUNG(
      BRANCH([XIC('SegValidLine')], [XIC('SegValidArc')]),
      OTE('SegValid'),
    ),
    RUNG(
      XIC('EnqueueReq'),
      XIC('SegValid'),
      XIO('QueueFull'),
      FFL('IncomingSeg', 'SegQueue[0]', 'QueueCtl', '32', '0'),
    ),
    RUNG(
      XIC('EnqueueReq'),
      XIC('SegValid'),
      XIO('QueueFull'),
      MOV('IncomingSeg.Seq', 'IncomingSegAck'),
    ),
    RUNG(
      XIC('EnqueueReq'),
      XIC('SegValid'),
      XIO('QueueFull'),
      MOV('IncomingSegReqID', 'LastIncomingSegReqID'),
    ),
    RUNG(
      XIC('EnqueueReq'),
      OTU('EnqueueReq'),
    ),
    RUNG(
      XIC('MoveA.ER'),
      MOV('3', 'FaultCode'),
    ),
    RUNG(
      XIC('MoveA.ER'),
      OTL('QueueFault'),
    ),
    RUNG(
      XIC('MoveA.ER'),
      OTL('AbortQueue'),
    ),
    RUNG(
      XIC('MoveA.ER'),
      OTU('MoveA.ER'),
    ),
    RUNG(
      XIC('MoveB.ER'),
      MOV('4', 'FaultCode'),
    ),
    RUNG(
      XIC('MoveB.ER'),
      OTL('QueueFault'),
    ),
    RUNG(
      XIC('MoveB.ER'),
      OTL('AbortQueue'),
    ),
    RUNG(
      XIC('MoveB.ER'),
      OTU('MoveB.ER'),
    ),
    RUNG(
      BRANCH([XIC('QueueFault')], [XIC('MoveA.ER')], [XIC('MoveB.ER')]),
      OTE('MotionFault'),
    ),
    RUNG(
      XIC('CheckCurSeg'),
      XIC('CurSeg.Valid'),
      GRT('CurSeg.Seq', '0'),
      BRANCH([EQU('CurSeg.SegType', '1')], [EQU('CurSeg.SegType', '2')]),
      OTL('PrepCurMove'),
    ),
    RUNG(
      XIC('CheckCurSeg'),
      XIO('CurSeg.Valid'),
      MOV('1', 'FaultCode'),
    ),
    RUNG(
      XIC('CheckCurSeg'),
      XIO('CurSeg.Valid'),
      OTL('QueueFault'),
    ),
    RUNG(
      XIC('CheckCurSeg'),
      XIC('CurSeg.Valid'),
      LEQ('CurSeg.Seq', '0'),
      MOV('6', 'FaultCode'),
    ),
    RUNG(
      XIC('CheckCurSeg'),
      XIC('CurSeg.Valid'),
      LEQ('CurSeg.Seq', '0'),
      OTL('QueueFault'),
    ),
    RUNG(
      XIC('CheckCurSeg'),
      XIC('CurSeg.Valid'),
      GRT('CurSeg.Seq', '0'),
      BRANCH([LES('CurSeg.SegType', '1')], [GRT('CurSeg.SegType', '2')]),
      MOV('7', 'FaultCode'),
    ),
    RUNG(
      XIC('CheckCurSeg'),
      XIC('CurSeg.Valid'),
      GRT('CurSeg.Seq', '0'),
      BRANCH([LES('CurSeg.SegType', '1')], [GRT('CurSeg.SegType', '2')]),
      OTL('QueueFault'),
    ),
    RUNG(
      XIC('CheckCurSeg'),
      OTU('CheckCurSeg'),
    ),
    RUNG(
      XIC('CheckNextSeg'),
      XIC('NextSeg.Valid'),
      GRT('NextSeg.Seq', '0'),
      BRANCH([EQU('NextSeg.SegType', '1')], [EQU('NextSeg.SegType', '2')]),
      OTL('PrepNextMove'),
    ),
    RUNG(
      XIC('CheckNextSeg'),
      XIO('NextSeg.Valid'),
      MOV('2', 'FaultCode'),
    ),
    RUNG(
      XIC('CheckNextSeg'),
      XIO('NextSeg.Valid'),
      OTL('QueueFault'),
    ),
    RUNG(
      XIC('CheckNextSeg'),
      XIC('NextSeg.Valid'),
      LEQ('NextSeg.Seq', '0'),
      MOV('5', 'FaultCode'),
    ),
    RUNG(
      XIC('CheckNextSeg'),
      XIC('NextSeg.Valid'),
      LEQ('NextSeg.Seq', '0'),
      OTL('QueueFault'),
    ),
    RUNG(
      XIC('CheckNextSeg'),
      XIC('NextSeg.Valid'),
      GRT('NextSeg.Seq', '0'),
      BRANCH([LES('NextSeg.SegType', '1')], [GRT('NextSeg.SegType', '2')]),
      MOV('8', 'FaultCode'),
    ),
    RUNG(
      XIC('CheckNextSeg'),
      XIC('NextSeg.Valid'),
      GRT('NextSeg.Seq', '0'),
      BRANCH([LES('NextSeg.SegType', '1')], [GRT('NextSeg.SegType', '2')]),
      OTL('QueueFault'),
    ),
    RUNG(
      XIC('CheckNextSeg'),
      OTU('CheckNextSeg'),
    ),
    RUNG(
      XIO('CurIssued'),
      XIO('NextIssued'),
      XIO('QueueFault'),
      GEQ('QueueCtl.POS', '1'),
      MOV('QueueCtl.POS', 'DINTS[5]'),
    ),
    RUNG(
      BRANCH([XIC('CurIssued')], [XIC('NextIssued')], [XIC('QueueFault')], [LEQ('QueueCtl.POS', '0')]),
      MOV('0', 'DINTS[5]'),
    ),
    RUNG(
      XIO('CurIssued'),
      XIO('NextIssued'),
      XIO('QueueFault'),
      GEQ('QueueCtl.POS', '1'),
      MOV('v_x_max', 'REALS[38]'),
    ),
    RUNG(
      XIO('CurIssued'),
      XIO('NextIssued'),
      XIO('QueueFault'),
      GEQ('QueueCtl.POS', '1'),
      MOV('v_y_max', 'REALS[39]'),
    ),
    RUNG(
      XIO('CurIssued'),
      XIO('NextIssued'),
      XIO('QueueFault'),
      GEQ('QueueCtl.POS', '1'),
      MOV('X_axis.ActualPosition', 'REALS[40]'),
    ),
    RUNG(
      XIO('CurIssued'),
      XIO('NextIssued'),
      XIO('QueueFault'),
      GEQ('QueueCtl.POS', '1'),
      MOV('Y_axis.ActualPosition', 'REALS[41]'),
    ),
    RUNG(
      XIO('CurIssued'),
      XIO('NextIssued'),
      XIO('QueueFault'),
      GEQ('QueueCtl.POS', '1'),
      OTL('BOOLS[7]'),
    ),
    RUNG(
      NEQ('DINTS[5]', '0'),
      JMP('MQ_cap_lbl_else_46'),
    ),
    RUNG(
      JMP('MQ_cap_lbl_CapSegSpeed_end'),
    ),
    RUNG(
      LBL('MQ_cap_lbl_else_46'),
      BRANCH([LEQ('REALS[38]', '0.0')], [LEQ('REALS[39]', '0.0')]),
      OTL('BOOLS[901]'),
    ),
    RUNG(
      GRT('REALS[38]', '0.0'),
      GRT('REALS[39]', '0.0'),
      JMP('MQ_cap_lbl_else_48'),
    ),
    RUNG(
      OTL('BOOLS[8]'),
    ),
    RUNG(
      JMP('MQ_cap_lbl_CapSegSpeed_end'),
    ),
    RUNG(
      LBL('MQ_cap_lbl_else_48'),
      BRANCH([LES('REALS[38]', '3.4028235E+38')], [LES('REALS[39]', '3.4028235E+38')]),
      OTL('BOOLS[902]'),
    ),
    RUNG(
      XIC('BOOLS[902]'),
      JMP('MQ_cap_lbl_else_50'),
    ),
    RUNG(
      JMP('MQ_cap_lbl_CapSegSpeed_end'),
    ),
    RUNG(
      LBL('MQ_cap_lbl_else_50'),
      XIC('BOOLS[7]'),
      JMP('MQ_cap_lbl_else_52'),
    ),
    RUNG(
      MOV('SegQueue[0].XY[0]', 'REALS[42]'),
    ),
    RUNG(
      MOV('SegQueue[0].XY[1]', 'REALS[43]'),
    ),
    RUNG(
      OTL('BOOLS[9]'),
    ),
    RUNG(
      JMP('MQ_cap_lbl_end_53'),
    ),
    RUNG(
      LBL('MQ_cap_lbl_else_52'),
      MOV('REALS[40]', 'REALS[42]'),
    ),
    RUNG(
      MOV('REALS[41]', 'REALS[43]'),
    ),
    RUNG(
      OTU('BOOLS[9]'),
    ),
    RUNG(
      LBL('MQ_cap_lbl_end_53'),
      MOV('0', 'idx_3'),
    ),
    RUNG(
      LBL('MQ_cap_lbl_loop_54'),
      GEQ('idx_3', 'DINTS[5]'),
      JMP('MQ_cap_lbl_loop_end_55'),
    ),
    RUNG(
      BRANCH([NEQ('idx_3', '0')], [XIO('BOOLS[9]')]),
      OTL('BOOLS[903]'),
    ),
    RUNG(
      XIC('BOOLS[903]'),
      JMP('MQ_cap_lbl_else_56'),
    ),
    RUNG(
      LES('REALS[38]', 'REALS[39]'),
      JMP('MQ_cap_lbl_min_a_58'),
    ),
    RUNG(
      MOV('REALS[39]', 'REALS[44]'),
      JMP('MQ_cap_lbl_min_end_59'),
    ),
    RUNG(
      LBL('MQ_cap_lbl_min_a_58'),
      MOV('REALS[38]', 'REALS[44]'),
    ),
    RUNG(
      LBL('MQ_cap_lbl_min_end_59'),
      MOV('1.0', 'REALS[45]'),
    ),
    RUNG(
      MOV('1.0', 'REALS[46]'),
    ),
    RUNG(
      JMP('MQ_cap_lbl_end_57'),
    ),
    RUNG(
      LBL('MQ_cap_lbl_else_56'),
      MOV('REALS[42]', 'REALS[20]'),
    ),
    RUNG(
      MOV('REALS[43]', 'REALS[21]'),
    ),
    RUNG(
      MOV('idx_3', 'idx_2'),
    ),
    RUNG(
      NEQ('SegQueue[idx_2].SegType', '1'),
      JMP('MQ_seg_lbl_else_30'),
    ),
    RUNG(
      CPT('REALS[24]', 'SegQueue[idx_2].XY[0]-REALS[20]'),
    ),
    RUNG(
      CPT('REALS[25]', 'SegQueue[idx_2].XY[1]-REALS[21]'),
    ),
    RUNG(
      CPT('REALS[26]', 'SQR(REALS[24]*REALS[24]+REALS[25]*REALS[25])'),
    ),
    RUNG(
      GRT('REALS[26]', '0.000000001'),
      JMP('MQ_seg_lbl_else_32'),
    ),
    RUNG(
      MOV('0.0', 'REALS[22]'),
    ),
    RUNG(
      MOV('0.0', 'REALS[23]'),
    ),
    RUNG(
      JMP('MQ_seg_lbl_SegTangentBounds_end'),
    ),
    RUNG(
      LBL('MQ_seg_lbl_else_32'),
      CPT('REALS[22]', 'ABS(REALS[24]/REALS[26])'),
    ),
    RUNG(
      CPT('REALS[23]', 'ABS(REALS[25]/REALS[26])'),
    ),
    RUNG(
      JMP('MQ_seg_lbl_SegTangentBounds_end'),
    ),
    RUNG(
      LBL('MQ_seg_lbl_else_30'),
      NEQ('SegQueue[idx_2].SegType', '2'),
      JMP('MQ_seg_lbl_else_34'),
    ),
    RUNG(
      MOV('idx_2', 'idx_0'),
    ),
    RUNG(
      MOV('idx_2', 'idx_1'),
    ),
    RUNG(
      NEQ('REALS[28]', '0'),
      JMP('MQ_seg_lbl_else_36'),
    ),
    RUNG(
      CPT('REALS[31]', 'SQR(REALS[20]-REALS[29]*REALS[20]-REALS[29]+REALS[21]-REALS[30]*REALS[21]-REALS[30])'),
    ),
    RUNG(
      CPT('REALS[32]', 'SQR(SegQueue[idx_2].XY[0]-REALS[29]*SegQueue[idx_2].XY[0]-REALS[29]+SegQueue[idx_2].XY[1]-REALS[30]*SegQueue[idx_2].XY[1]-REALS[30])'),
    ),
    RUNG(
      BRANCH([LEQ('REALS[31]', '0.000000001')], [LEQ('REALS[32]', '0.000000001')]),
      OTL('BOOLS[900]'),
    ),
    RUNG(
      XIC('BOOLS[900]'),
      JMP('MQ_seg_lbl_else_38'),
    ),
    RUNG(
      CPT('REALS[912]', 'REALS[21]-REALS[30]'),
    ),
    RUNG(
      CPT('REALS[913]', 'REALS[20]-REALS[29]'),
    ),
    RUNG(
      GRT('REALS[913]', '0.0'),
      CPT('REALS[33]', 'ATN(REALS[912]/REALS[913])'),
      JMP('MQ_seg_lbl_atan2_done_40'),
    ),
    RUNG(
      LES('REALS[913]', '0.0'),
      GEQ('REALS[912]', '0.0'),
      CPT('REALS[33]', 'ATN(REALS[912]/REALS[913])+3.14159265358979'),
      JMP('MQ_seg_lbl_atan2_done_40'),
    ),
    RUNG(
      LES('REALS[913]', '0.0'),
      LES('REALS[912]', '0.0'),
      CPT('REALS[33]', 'ATN(REALS[912]/REALS[913])-3.14159265358979'),
      JMP('MQ_seg_lbl_atan2_done_40'),
    ),
    RUNG(
      EQU('REALS[913]', '0.0'),
      GRT('REALS[912]', '0.0'),
      MOV('1.5707963267949', 'REALS[33]'),
      JMP('MQ_seg_lbl_atan2_done_40'),
    ),
    RUNG(
      EQU('REALS[913]', '0.0'),
      LES('REALS[912]', '0.0'),
      MOV('-1.5707963267949', 'REALS[33]'),
      JMP('MQ_seg_lbl_atan2_done_40'),
    ),
    RUNG(
      MOV('0.0', 'REALS[33]'),
    ),
    RUNG(
      LBL('MQ_seg_lbl_atan2_done_40'),
      CPT('REALS[914]', 'SegQueue[idx_2].XY[1]-REALS[30]'),
    ),
    RUNG(
      CPT('REALS[915]', 'SegQueue[idx_2].XY[0]-REALS[29]'),
    ),
    RUNG(
      GRT('REALS[915]', '0.0'),
      CPT('REALS[34]', 'ATN(REALS[914]/REALS[915])'),
      JMP('MQ_seg_lbl_atan2_done_41'),
    ),
    RUNG(
      LES('REALS[915]', '0.0'),
      GEQ('REALS[914]', '0.0'),
      CPT('REALS[34]', 'ATN(REALS[914]/REALS[915])+3.14159265358979'),
      JMP('MQ_seg_lbl_atan2_done_41'),
    ),
    RUNG(
      LES('REALS[915]', '0.0'),
      LES('REALS[914]', '0.0'),
      CPT('REALS[34]', 'ATN(REALS[914]/REALS[915])-3.14159265358979'),
      JMP('MQ_seg_lbl_atan2_done_41'),
    ),
    RUNG(
      EQU('REALS[915]', '0.0'),
      GRT('REALS[914]', '0.0'),
      MOV('1.5707963267949', 'REALS[34]'),
      JMP('MQ_seg_lbl_atan2_done_41'),
    ),
    RUNG(
      EQU('REALS[915]', '0.0'),
      LES('REALS[914]', '0.0'),
      MOV('-1.5707963267949', 'REALS[34]'),
      JMP('MQ_seg_lbl_atan2_done_41'),
    ),
    RUNG(
      MOV('0.0', 'REALS[34]'),
    ),
    RUNG(
      LBL('MQ_seg_lbl_atan2_done_41'),
      MOV('REALS[33]', 'REALS[14]'),
    ),
    RUNG(
      MOV('REALS[34]', 'REALS[15]'),
    ),
    RUNG(
      MOV('SegQueue[idx_2].Direction', 'DINTS[4]'),
    ),
    RUNG(
      CPT('REALS[17]', '2.0*3.14159265358979'),
    ),
    RUNG(
      CPT('REALS[910]', 'REALS[15]-REALS[14]'),
    ),
    RUNG(
      MOD('REALS[910]', 'REALS[17]', 'REALS[18]'),
    ),
    RUNG(
      CPT('REALS[911]', 'REALS[14]-REALS[15]'),
    ),
    RUNG(
      MOD('REALS[911]', 'REALS[17]', 'REALS[19]'),
    ),
    RUNG(
      NEQ('DINTS[4]', '0'),
      JMP('MQ_arc_lbl_else_18'),
    ),
    RUNG(
      CPT('REALS[16]', '-REALS[19]'),
    ),
    RUNG(
      JMP('MQ_arc_lbl_ArcSweepRad_end'),
    ),
    RUNG(
      LBL('MQ_arc_lbl_else_18'),
      NEQ('DINTS[4]', '1'),
      JMP('MQ_arc_lbl_else_20'),
    ),
    RUNG(
      MOV('REALS[18]', 'REALS[16]'),
    ),
    RUNG(
      JMP('MQ_arc_lbl_ArcSweepRad_end'),
    ),
    RUNG(
      LBL('MQ_arc_lbl_else_20'),
      NEQ('DINTS[4]', '2'),
      JMP('MQ_arc_lbl_else_22'),
    ),
    RUNG(
      CPT('REALS[16]', '-REALS[19]'),
    ),
    RUNG(
      JMP('MQ_arc_lbl_ArcSweepRad_end'),
    ),
    RUNG(
      LBL('MQ_arc_lbl_else_22'),
      NEQ('DINTS[4]', '3'),
      JMP('MQ_arc_lbl_else_24'),
    ),
    RUNG(
      MOV('REALS[18]', 'REALS[16]'),
    ),
    RUNG(
      JMP('MQ_arc_lbl_ArcSweepRad_end'),
    ),
    RUNG(
      LBL('MQ_arc_lbl_else_24'),
      OTU('BOOLS[3]'),
    ),
    RUNG(
      JMP('MQ_arc_lbl_ArcSweepRad_end'),
    ),
    RUNG(
      LBL('MQ_arc_lbl_ArcSweepRad_end'),
      NOP(),
    ),
    RUNG(
      MOV('REALS[16]', 'REALS[35]'),
    ),
    RUNG(
      XIC('BOOLS[3]'),
      OTL('BOOLS[6]'),
    ),
    RUNG(
      XIO('BOOLS[3]'),
      OTU('BOOLS[6]'),
    ),
    RUNG(
      XIO('BOOLS[6]'),
      JMP('MQ_seg_lbl_else_42'),
    ),
    RUNG(
      MOV('REALS[33]', 'REALS[0]'),
    ),
    RUNG(
      MOV('REALS[35]', 'REALS[1]'),
    ),
    RUNG(
      CPT('REALS[3]', 'REALS[0]+REALS[1]'),
    ),
    RUNG(
      LES('REALS[0]', 'REALS[3]'),
      JMP('MQ_sin_lbl_min_a_0'),
    ),
    RUNG(
      MOV('REALS[3]', 'REALS[4]'),
      JMP('MQ_sin_lbl_min_end_1'),
    ),
    RUNG(
      LBL('MQ_sin_lbl_min_a_0'),
      MOV('REALS[0]', 'REALS[4]'),
    ),
    RUNG(
      LBL('MQ_sin_lbl_min_end_1'),
      GRT('REALS[0]', 'REALS[3]'),
      JMP('MQ_sin_lbl_max_a_2'),
    ),
    RUNG(
      MOV('REALS[3]', 'REALS[5]'),
      JMP('MQ_sin_lbl_max_end_3'),
    ),
    RUNG(
      LBL('MQ_sin_lbl_max_a_2'),
      MOV('REALS[0]', 'REALS[5]'),
    ),
    RUNG(
      LBL('MQ_sin_lbl_max_end_3'),
      CPT('REALS[900]', 'ABS(SIN(REALS[0]))'),
    ),
    RUNG(
      CPT('REALS[901]', 'ABS(SIN(REALS[3]))'),
    ),
    RUNG(
      GRT('REALS[900]', 'REALS[901]'),
      JMP('MQ_sin_lbl_max_a_4'),
    ),
    RUNG(
      MOV('REALS[901]', 'REALS[6]'),
      JMP('MQ_sin_lbl_max_end_5'),
    ),
    RUNG(
      LBL('MQ_sin_lbl_max_a_4'),
      MOV('REALS[900]', 'REALS[6]'),
    ),
    RUNG(
      LBL('MQ_sin_lbl_max_end_5'),
      CPT('REALS[902]', 'REALS[4]-0.5*3.14159265358979/3.14159265358979'),
    ),
    RUNG(
      TRN('REALS[902]', 'DINTS[900]'),
    ),
    RUNG(
      MOV('DINTS[900]', 'REALS[903]'),
    ),
    RUNG(
      GEQ('REALS[903]', 'REALS[902]'),
      JMP('MQ_sin_lbl_ceil_done_6'),
    ),
    RUNG(
      ADD('DINTS[900]', '1', 'DINTS[900]'),
    ),
    RUNG(
      LBL('MQ_sin_lbl_ceil_done_6'),
      MOV('DINTS[900]', 'DINTS[0]'),
    ),
    RUNG(
      CPT('REALS[904]', 'REALS[5]-0.5*3.14159265358979/3.14159265358979'),
    ),
    RUNG(
      TRN('REALS[904]', 'DINTS[1]'),
    ),
    RUNG(
      GRT('DINTS[0]', 'DINTS[1]'),
      JMP('MQ_sin_lbl_else_7'),
    ),
    RUNG(
      MOV('1.0', 'REALS[2]'),
    ),
    RUNG(
      JMP('MQ_sin_lbl_MaxAbsSinSweep_end'),
    ),
    RUNG(
      LBL('MQ_sin_lbl_else_7'),
      MOV('REALS[6]', 'REALS[2]'),
    ),
    RUNG(
      JMP('MQ_sin_lbl_MaxAbsSinSweep_end'),
    ),
    RUNG(
      LBL('MQ_sin_lbl_MaxAbsSinSweep_end'),
      NOP(),
    ),
    RUNG(
      MOV('REALS[2]', 'REALS[36]'),
    ),
    RUNG(
      MOV('REALS[33]', 'REALS[7]'),
    ),
    RUNG(
      MOV('REALS[35]', 'REALS[8]'),
    ),
    RUNG(
      CPT('REALS[10]', 'REALS[7]+REALS[8]'),
    ),
    RUNG(
      LES('REALS[7]', 'REALS[10]'),
      JMP('MQ_cos_lbl_min_a_9'),
    ),
    RUNG(
      MOV('REALS[10]', 'REALS[11]'),
      JMP('MQ_cos_lbl_min_end_10'),
    ),
    RUNG(
      LBL('MQ_cos_lbl_min_a_9'),
      MOV('REALS[7]', 'REALS[11]'),
    ),
    RUNG(
      LBL('MQ_cos_lbl_min_end_10'),
      GRT('REALS[7]', 'REALS[10]'),
      JMP('MQ_cos_lbl_max_a_11'),
    ),
    RUNG(
      MOV('REALS[10]', 'REALS[12]'),
      JMP('MQ_cos_lbl_max_end_12'),
    ),
    RUNG(
      LBL('MQ_cos_lbl_max_a_11'),
      MOV('REALS[7]', 'REALS[12]'),
    ),
    RUNG(
      LBL('MQ_cos_lbl_max_end_12'),
      CPT('REALS[905]', 'ABS(COS(REALS[7]))'),
    ),
    RUNG(
      CPT('REALS[906]', 'ABS(COS(REALS[10]))'),
    ),
    RUNG(
      GRT('REALS[905]', 'REALS[906]'),
      JMP('MQ_cos_lbl_max_a_13'),
    ),
    RUNG(
      MOV('REALS[906]', 'REALS[13]'),
      JMP('MQ_cos_lbl_max_end_14'),
    ),
    RUNG(
      LBL('MQ_cos_lbl_max_a_13'),
      MOV('REALS[905]', 'REALS[13]'),
    ),
    RUNG(
      LBL('MQ_cos_lbl_max_end_14'),
      CPT('REALS[907]', 'REALS[11]/3.14159265358979'),
    ),
    RUNG(
      TRN('REALS[907]', 'DINTS[901]'),
    ),
    RUNG(
      MOV('DINTS[901]', 'REALS[908]'),
    ),
    RUNG(
      GEQ('REALS[908]', 'REALS[907]'),
      JMP('MQ_cos_lbl_ceil_done_15'),
    ),
    RUNG(
      ADD('DINTS[901]', '1', 'DINTS[901]'),
    ),
    RUNG(
      LBL('MQ_cos_lbl_ceil_done_15'),
      MOV('DINTS[901]', 'DINTS[2]'),
    ),
    RUNG(
      CPT('REALS[909]', 'REALS[12]/3.14159265358979'),
    ),
    RUNG(
      TRN('REALS[909]', 'DINTS[3]'),
    ),
    RUNG(
      GRT('DINTS[2]', 'DINTS[3]'),
      JMP('MQ_cos_lbl_else_16'),
    ),
    RUNG(
      MOV('1.0', 'REALS[9]'),
    ),
    RUNG(
      JMP('MQ_cos_lbl_MaxAbsCosSweep_end'),
    ),
    RUNG(
      LBL('MQ_cos_lbl_else_16'),
      MOV('REALS[13]', 'REALS[9]'),
    ),
    RUNG(
      JMP('MQ_cos_lbl_MaxAbsCosSweep_end'),
    ),
    RUNG(
      LBL('MQ_cos_lbl_MaxAbsCosSweep_end'),
      NOP(),
    ),
    RUNG(
      MOV('REALS[9]', 'REALS[37]'),
    ),
    RUNG(
      MOV('REALS[36]', 'REALS[22]'),
    ),
    RUNG(
      MOV('REALS[37]', 'REALS[23]'),
    ),
    RUNG(
      JMP('MQ_seg_lbl_SegTangentBounds_end'),
    ),
    RUNG(
      LBL('MQ_seg_lbl_else_42'),
      NOP(),
    ),
    RUNG(
      LBL('MQ_seg_lbl_else_38'),
      NOP(),
    ),
    RUNG(
      LBL('MQ_seg_lbl_else_36'),
      NOP(),
    ),
    RUNG(
      LBL('MQ_seg_lbl_else_34'),
      CPT('REALS[24]', 'SegQueue[idx_2].XY[0]-REALS[20]'),
    ),
    RUNG(
      CPT('REALS[25]', 'SegQueue[idx_2].XY[1]-REALS[21]'),
    ),
    RUNG(
      CPT('REALS[26]', 'SQR(REALS[24]*REALS[24]+REALS[25]*REALS[25])'),
    ),
    RUNG(
      GRT('REALS[26]', '0.000000001'),
      JMP('MQ_seg_lbl_else_44'),
    ),
    RUNG(
      MOV('0.0', 'REALS[22]'),
    ),
    RUNG(
      MOV('0.0', 'REALS[23]'),
    ),
    RUNG(
      JMP('MQ_seg_lbl_SegTangentBounds_end'),
    ),
    RUNG(
      LBL('MQ_seg_lbl_else_44'),
      CPT('REALS[22]', 'ABS(REALS[24]/REALS[26])'),
    ),
    RUNG(
      CPT('REALS[23]', 'ABS(REALS[25]/REALS[26])'),
    ),
    RUNG(
      JMP('MQ_seg_lbl_SegTangentBounds_end'),
    ),
    RUNG(
      LBL('MQ_seg_lbl_SegTangentBounds_end'),
      NOP(),
    ),
    RUNG(
      MOV('REALS[22]', 'REALS[45]'),
    ),
    RUNG(
      MOV('REALS[23]', 'REALS[46]'),
    ),
    RUNG(
      GRT('REALS[45]', '0.000000001'),
      JMP('MQ_cap_lbl_else_60'),
    ),
    RUNG(
      MOV('3.4028235E+38', 'REALS[47]'),
    ),
    RUNG(
      JMP('MQ_cap_lbl_end_61'),
    ),
    RUNG(
      LBL('MQ_cap_lbl_else_60'),
      CPT('REALS[47]', 'REALS[38]/REALS[45]'),
    ),
    RUNG(
      LBL('MQ_cap_lbl_end_61'),
      GRT('REALS[46]', '0.000000001'),
      JMP('MQ_cap_lbl_else_62'),
    ),
    RUNG(
      MOV('3.4028235E+38', 'REALS[48]'),
    ),
    RUNG(
      JMP('MQ_cap_lbl_end_63'),
    ),
    RUNG(
      LBL('MQ_cap_lbl_else_62'),
      CPT('REALS[48]', 'REALS[39]/REALS[46]'),
    ),
    RUNG(
      LBL('MQ_cap_lbl_end_63'),
      LES('REALS[47]', 'REALS[48]'),
      JMP('MQ_cap_lbl_min_a_64'),
    ),
    RUNG(
      MOV('REALS[48]', 'REALS[44]'),
      JMP('MQ_cap_lbl_min_end_65'),
    ),
    RUNG(
      LBL('MQ_cap_lbl_min_a_64'),
      MOV('REALS[47]', 'REALS[44]'),
    ),
    RUNG(
      LBL('MQ_cap_lbl_min_end_65'),
      NOP(),
    ),
    RUNG(
      LBL('MQ_cap_lbl_end_57'),
      LES('SegQueue[idx_3].Speed', 'REALS[44]'),
      JMP('MQ_cap_lbl_min_a_66'),
    ),
    RUNG(
      MOV('REALS[44]', 'REALS[49]'),
      JMP('MQ_cap_lbl_min_end_67'),
    ),
    RUNG(
      LBL('MQ_cap_lbl_min_a_66'),
      MOV('SegQueue[idx_3].Speed', 'REALS[49]'),
    ),
    RUNG(
      LBL('MQ_cap_lbl_min_end_67'),
      GRT('REALS[49]', '0.0'),
      JMP('MQ_cap_lbl_else_68'),
    ),
    RUNG(
      OTL('BOOLS[8]'),
    ),
    RUNG(
      JMP('MQ_cap_lbl_CapSegSpeed_end'),
    ),
    RUNG(
      LBL('MQ_cap_lbl_else_68'),
      MOV('REALS[49]', 'SegQueue[idx_3].Speed'),
    ),
    RUNG(
      MOV('SegQueue[idx_3].XY[0]', 'REALS[42]'),
    ),
    RUNG(
      MOV('SegQueue[idx_3].XY[1]', 'REALS[43]'),
    ),
    RUNG(
      ADD('idx_3', '1', 'idx_3'),
    ),
    RUNG(
      JMP('MQ_cap_lbl_loop_54'),
    ),
    RUNG(
      LBL('MQ_cap_lbl_loop_end_55'),
      JMP('MQ_cap_lbl_CapSegSpeed_end'),
    ),
    RUNG(
      LBL('MQ_cap_lbl_CapSegSpeed_end'),
      NOP(),
    ),
    RUNG(
      XIC('StartQueuedPath'),
      BRANCH([BRANCH([XIO('Z_RETRACTED')], [GEQ('Z_axis.ActualPosition', 'MAX_TOLERABLE_Z')]), CPT('ERROR_CODE', '3001'), CPT('NEXTSTATE', '10')], [XIC('Z_RETRACTED'), XIO('APA_IS_VERTICAL'), CPT('ERROR_CODE', '3005'), CPT('NEXTSTATE', '10')]),
      OTE('AbortQueue'),
      OTU('StartQueuedPath'),
    ),
    RUNG(
      XIC('StartQueuedPath'),
      XIO('CurIssued'),
      XIO('QueueFault'),
      GEQ('QueueCtl.POS', '1'),
      ONS('StartCurONS'),
      OTL('LoadCurReq'),
    ),
    RUNG(
      XIC('LoadCurReq'),
      OTU('StartQueuedPath'),
    ),
    RUNG(
      XIC('LoadCurReq'),
      FFU('SegQueue[0]', 'CurSeg', 'QueueCtl', '32', '0'),
    ),
    RUNG(
      XIC('LoadCurReq'),
      OTL('CheckCurSeg'),
    ),
    RUNG(
      XIC('LoadCurReq'),
      OTU('LoadCurReq'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIC('UseAasCurrent'),
      COP('CurSeg.XY[0]', 'CmdA_XY[0]', '2'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIC('UseAasCurrent'),
      MOV('CurSeg.Speed', 'CmdA_Speed'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIC('UseAasCurrent'),
      MOV('CurSeg.Accel', 'CmdA_Accel'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIC('UseAasCurrent'),
      MOV('CurSeg.Decel', 'CmdA_Decel'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIC('UseAasCurrent'),
      MOV('CurSeg.JerkAccel', 'CmdA_JerkAccel'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIC('UseAasCurrent'),
      MOV('CurSeg.JerkDecel', 'CmdA_JerkDecel'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIC('UseAasCurrent'),
      MOV('CurSeg.TermType', 'CmdA_TermType'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIC('UseAasCurrent'),
      MOV('CurSeg.SegType', 'CmdA_SegType'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIC('UseAasCurrent'),
      MOV('CurSeg.CircleType', 'CmdA_CircleType'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIC('UseAasCurrent'),
      COP('CurSeg.ViaCenter[0]', 'CmdA_ViaCenter[0]', '2'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIC('UseAasCurrent'),
      MOV('CurSeg.Direction', 'CmdA_Direction'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIC('UseAasCurrent'),
      MOV('CurSeg.Seq', 'ActiveSeq'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIO('UseAasCurrent'),
      COP('CurSeg.XY[0]', 'CmdB_XY[0]', '2'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIO('UseAasCurrent'),
      MOV('CurSeg.Speed', 'CmdB_Speed'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIO('UseAasCurrent'),
      MOV('CurSeg.Accel', 'CmdB_Accel'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIO('UseAasCurrent'),
      MOV('CurSeg.Decel', 'CmdB_Decel'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIO('UseAasCurrent'),
      MOV('CurSeg.JerkAccel', 'CmdB_JerkAccel'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIO('UseAasCurrent'),
      MOV('CurSeg.JerkDecel', 'CmdB_JerkDecel'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIO('UseAasCurrent'),
      MOV('CurSeg.TermType', 'CmdB_TermType'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIO('UseAasCurrent'),
      MOV('CurSeg.SegType', 'CmdB_SegType'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIO('UseAasCurrent'),
      MOV('CurSeg.CircleType', 'CmdB_CircleType'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIO('UseAasCurrent'),
      COP('CurSeg.ViaCenter[0]', 'CmdB_ViaCenter[0]', '2'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIO('UseAasCurrent'),
      MOV('CurSeg.Direction', 'CmdB_Direction'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIO('UseAasCurrent'),
      MOV('CurSeg.Seq', 'ActiveSeq'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIO('APA_IS_VERTICAL'),
      MOV('3005', 'FaultCode'),
      CPT('ERROR_CODE', '3005'),
      CPT('NEXTSTATE', '10'),
      OTL('QueueFault'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIC('APA_IS_VERTICAL'),
      XIC('X_Y.PhysicalAxisFault'),
      MOV('3002', 'FaultCode'),
      CPT('ERROR_CODE', '3002'),
      CPT('NEXTSTATE', '10'),
      OTL('QueueFault'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIC('APA_IS_VERTICAL'),
      XIO('X_Y.PhysicalAxisFault'),
      XIC('X_axis.DriveEnableStatus'),
      XIC('Y_axis.DriveEnableStatus'),
      OTL('IssueCurPulse'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      XIC('APA_IS_VERTICAL'),
      XIO('X_Y.PhysicalAxisFault'),
      BRANCH([XIO('X_axis.DriveEnableStatus')], [XIO('Y_axis.DriveEnableStatus')]),
      OTL('WaitCurAxisOn'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      OTU('PrepCurMove'),
    ),
    RUNG(
      XIC('WaitCurAxisOn'),
      XIO('APA_IS_VERTICAL'),
      MOV('3005', 'FaultCode'),
      CPT('ERROR_CODE', '3005'),
      CPT('NEXTSTATE', '10'),
      OTL('QueueFault'),
      OTU('WaitCurAxisOn'),
    ),
    RUNG(
      XIC('WaitCurAxisOn'),
      XIC('APA_IS_VERTICAL'),
      XIC('X_Y.PhysicalAxisFault'),
      MOV('3002', 'FaultCode'),
      CPT('ERROR_CODE', '3002'),
      CPT('NEXTSTATE', '10'),
      OTL('QueueFault'),
      OTU('WaitCurAxisOn'),
    ),
    RUNG(
      XIC('WaitCurAxisOn'),
      XIC('APA_IS_VERTICAL'),
      XIO('X_Y.PhysicalAxisFault'),
      MSO('X_axis', 'MQ_x_axis_mso'),
      MSO('Y_axis', 'MQ_y_axis_mso'),
    ),
    RUNG(
      XIC('WaitCurAxisOn'),
      XIC('APA_IS_VERTICAL'),
      XIO('X_Y.PhysicalAxisFault'),
      XIC('MQ_x_axis_mso.DN'),
      XIC('MQ_y_axis_mso.DN'),
      OTL('IssueCurPulse'),
    ),
    RUNG(
      XIC('WaitCurAxisOn'),
      XIC('APA_IS_VERTICAL'),
      XIO('X_Y.PhysicalAxisFault'),
      XIC('MQ_x_axis_mso.DN'),
      XIC('MQ_y_axis_mso.DN'),
      OTU('WaitCurAxisOn'),
    ),
    RUNG(
      XIC('PrepCurMove'),
      OTU('PrepCurMove'),
    ),
    RUNG(
      XIC('IssueCurPulse'),
      XIC('UseAasCurrent'),
      EQU('CmdA_SegType', '1'),
      MCLM('X_Y', 'MoveA', '0', 'CmdA_XY[0]', 'CmdA_Speed', '"Units per sec"', 'CmdA_Accel', '"Units per sec2"', 'CmdA_Decel', '"Units per sec2"', 'S-Curve', 'CmdA_JerkAccel', 'CmdA_JerkDecel', '"Units per sec3"', 'CmdA_TermType', 'Disabled', 'Programmed', 'CmdTolerance', '0', 'None', '0', '0'),
    ),
    RUNG(
      XIC('IssueCurPulse'),
      XIC('UseAasCurrent'),
      EQU('CmdA_SegType', '2'),
      MCCM('X_Y', 'MoveA', '0', 'CmdA_XY[0]', 'CmdA_CircleType', 'CmdA_ViaCenter[0]', 'CmdA_Direction', 'CmdA_Speed', '"Units per sec"', 'CmdA_Accel', '"Units per sec2"', 'CmdA_Decel', '"Units per sec2"', 'S-Curve', 'CmdA_JerkAccel', 'CmdA_JerkDecel', '"Units per sec3"', 'CmdA_TermType', 'Disabled', 'Programmed', 'CmdTolerance', '0', 'None', '0', '0'),
    ),
    RUNG(
      XIC('IssueCurPulse'),
      XIO('UseAasCurrent'),
      EQU('CmdB_SegType', '1'),
      MCLM('X_Y', 'MoveB', '0', 'CmdB_XY[0]', 'CmdB_Speed', '"Units per sec"', 'CmdB_Accel', '"Units per sec2"', 'CmdB_Decel', '"Units per sec2"', 'S-Curve', 'CmdB_JerkAccel', 'CmdB_JerkDecel', '"Units per sec3"', 'CmdB_TermType', 'Disabled', 'Programmed', 'CmdTolerance', '0', 'None', '0', '0'),
    ),
    RUNG(
      XIC('IssueCurPulse'),
      XIO('UseAasCurrent'),
      EQU('CmdB_SegType', '2'),
      MCCM('X_Y', 'MoveB', '0', 'CmdB_XY[0]', 'CmdB_CircleType', 'CmdB_ViaCenter[0]', 'CmdB_Direction', 'CmdB_Speed', '"Units per sec"', 'CmdB_Accel', '"Units per sec2"', 'CmdB_Decel', '"Units per sec2"', 'S-Curve', 'CmdB_JerkAccel', 'CmdB_JerkDecel', '"Units per sec3"', 'CmdB_TermType', 'Disabled', 'Programmed', 'CmdTolerance', '0', 'None', '0', '0'),
    ),
    RUNG(
      XIC('IssueCurPulse'),
      OTL('CurIssued'),
    ),
    RUNG(
      XIC('IssueCurPulse'),
      OTU('IssueCurPulse'),
    ),
    RUNG(
      XIC('CurIssued'),
      XIC('UseAasCurrent'),
      XIC('MoveA.IP'),
      XIO('X_Y.MovePendingStatus'),
      XIO('NextIssued'),
      XIO('QueueEmpty'),
      XIO('QueueFault'),
      ONS('StartNextA_ONS'),
      OTL('LoadNextReq'),
    ),
    RUNG(
      XIC('CurIssued'),
      XIO('UseAasCurrent'),
      XIC('MoveB.IP'),
      XIO('X_Y.MovePendingStatus'),
      XIO('NextIssued'),
      XIO('QueueEmpty'),
      XIO('QueueFault'),
      ONS('StartNextB_ONS'),
      OTL('LoadNextReq'),
    ),
    RUNG(
      XIC('LoadNextReq'),
      FFU('SegQueue[0]', 'NextSeg', 'QueueCtl', '32', '0'),
    ),
    RUNG(
      XIC('LoadNextReq'),
      OTL('CheckNextSeg'),
    ),
    RUNG(
      XIC('LoadNextReq'),
      OTU('LoadNextReq'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIC('UseAasCurrent'),
      COP('NextSeg.XY[0]', 'CmdB_XY[0]', '2'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIC('UseAasCurrent'),
      MOV('NextSeg.Speed', 'CmdB_Speed'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIC('UseAasCurrent'),
      MOV('NextSeg.Accel', 'CmdB_Accel'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIC('UseAasCurrent'),
      MOV('NextSeg.Decel', 'CmdB_Decel'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIC('UseAasCurrent'),
      MOV('NextSeg.JerkAccel', 'CmdB_JerkAccel'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIC('UseAasCurrent'),
      MOV('NextSeg.JerkDecel', 'CmdB_JerkDecel'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIC('UseAasCurrent'),
      MOV('NextSeg.TermType', 'CmdB_TermType'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIC('UseAasCurrent'),
      MOV('NextSeg.SegType', 'CmdB_SegType'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIC('UseAasCurrent'),
      MOV('NextSeg.CircleType', 'CmdB_CircleType'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIC('UseAasCurrent'),
      COP('NextSeg.ViaCenter[0]', 'CmdB_ViaCenter[0]', '2'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIC('UseAasCurrent'),
      MOV('NextSeg.Direction', 'CmdB_Direction'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIC('UseAasCurrent'),
      MOV('NextSeg.Seq', 'PendingSeq'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIO('UseAasCurrent'),
      COP('NextSeg.XY[0]', 'CmdA_XY[0]', '2'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIO('UseAasCurrent'),
      MOV('NextSeg.Speed', 'CmdA_Speed'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIO('UseAasCurrent'),
      MOV('NextSeg.Accel', 'CmdA_Accel'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIO('UseAasCurrent'),
      MOV('NextSeg.Decel', 'CmdA_Decel'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIO('UseAasCurrent'),
      MOV('NextSeg.JerkAccel', 'CmdA_JerkAccel'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIO('UseAasCurrent'),
      MOV('NextSeg.JerkDecel', 'CmdA_JerkDecel'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIO('UseAasCurrent'),
      MOV('NextSeg.TermType', 'CmdA_TermType'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIO('UseAasCurrent'),
      MOV('NextSeg.SegType', 'CmdA_SegType'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIO('UseAasCurrent'),
      MOV('NextSeg.CircleType', 'CmdA_CircleType'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIO('UseAasCurrent'),
      COP('NextSeg.ViaCenter[0]', 'CmdA_ViaCenter[0]', '2'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIO('UseAasCurrent'),
      MOV('NextSeg.Direction', 'CmdA_Direction'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIO('UseAasCurrent'),
      MOV('NextSeg.Seq', 'PendingSeq'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIO('APA_IS_VERTICAL'),
      MOV('3005', 'FaultCode'),
      CPT('ERROR_CODE', '3005'),
      CPT('NEXTSTATE', '10'),
      OTL('QueueFault'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIC('APA_IS_VERTICAL'),
      XIC('X_Y.PhysicalAxisFault'),
      MOV('3002', 'FaultCode'),
      CPT('ERROR_CODE', '3002'),
      CPT('NEXTSTATE', '10'),
      OTL('QueueFault'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIC('APA_IS_VERTICAL'),
      XIO('X_Y.PhysicalAxisFault'),
      XIC('X_axis.DriveEnableStatus'),
      XIC('Y_axis.DriveEnableStatus'),
      OTL('MQ_IssueNextPulse'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      XIC('APA_IS_VERTICAL'),
      XIO('X_Y.PhysicalAxisFault'),
      BRANCH([XIO('X_axis.DriveEnableStatus')], [XIO('Y_axis.DriveEnableStatus')]),
      OTL('WaitNextAxisOn'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      OTU('PrepNextMove'),
    ),
    RUNG(
      XIC('WaitNextAxisOn'),
      XIO('APA_IS_VERTICAL'),
      MOV('3005', 'FaultCode'),
      CPT('ERROR_CODE', '3005'),
      CPT('NEXTSTATE', '10'),
      OTL('QueueFault'),
      OTU('WaitNextAxisOn'),
    ),
    RUNG(
      XIC('WaitNextAxisOn'),
      XIC('APA_IS_VERTICAL'),
      XIC('X_Y.PhysicalAxisFault'),
      MOV('3002', 'FaultCode'),
      CPT('ERROR_CODE', '3002'),
      CPT('NEXTSTATE', '10'),
      OTL('QueueFault'),
      OTU('WaitNextAxisOn'),
    ),
    RUNG(
      XIC('WaitNextAxisOn'),
      XIC('APA_IS_VERTICAL'),
      XIO('X_Y.PhysicalAxisFault'),
      MSO('X_axis', 'MQ_x_axis_mso'),
      MSO('Y_axis', 'MQ_y_axis_mso'),
    ),
    RUNG(
      XIC('WaitNextAxisOn'),
      XIC('APA_IS_VERTICAL'),
      XIO('X_Y.PhysicalAxisFault'),
      XIC('MQ_x_axis_mso.DN'),
      XIC('MQ_y_axis_mso.DN'),
      OTL('MQ_IssueNextPulse'),
    ),
    RUNG(
      XIC('WaitNextAxisOn'),
      XIC('APA_IS_VERTICAL'),
      XIO('X_Y.PhysicalAxisFault'),
      XIC('MQ_x_axis_mso.DN'),
      XIC('MQ_y_axis_mso.DN'),
      OTU('WaitNextAxisOn'),
    ),
    RUNG(
      XIC('PrepNextMove'),
      OTU('PrepNextMove'),
    ),
    RUNG(
      XIC('MQ_IssueNextPulse'),
      XIC('UseAasCurrent'),
      EQU('CmdB_SegType', '1'),
      MCLM('X_Y', 'MoveB', '0', 'CmdB_XY[0]', 'CmdB_Speed', '"Units per sec"', 'CmdB_Accel', '"Units per sec2"', 'CmdB_Decel', '"Units per sec2"', 'S-Curve', 'CmdB_JerkAccel', 'CmdB_JerkDecel', '"Units per sec3"', 'CmdB_TermType', 'Disabled', 'Programmed', 'CmdTolerance', '0', 'None', '0', '0'),
    ),
    RUNG(
      XIC('MQ_IssueNextPulse'),
      XIC('UseAasCurrent'),
      EQU('CmdB_SegType', '2'),
      MCCM('X_Y', 'MoveB', '0', 'CmdB_XY[0]', 'CmdB_CircleType', 'CmdB_ViaCenter[0]', 'CmdB_Direction', 'CmdB_Speed', '"Units per sec"', 'CmdB_Accel', '"Units per sec2"', 'CmdB_Decel', '"Units per sec2"', 'S-Curve', 'CmdB_JerkAccel', 'CmdB_JerkDecel', '"Units per sec3"', 'CmdB_TermType', 'Disabled', 'Programmed', 'CmdTolerance', '0', 'None', '0', '0'),
    ),
    RUNG(
      XIC('MQ_IssueNextPulse'),
      XIO('UseAasCurrent'),
      EQU('CmdA_SegType', '1'),
      MCLM('X_Y', 'MoveA', '0', 'CmdA_XY[0]', 'CmdA_Speed', '"Units per sec"', 'CmdA_Accel', '"Units per sec2"', 'CmdA_Decel', '"Units per sec2"', 'S-Curve', 'CmdA_JerkAccel', 'CmdA_JerkDecel', '"Units per sec3"', 'CmdA_TermType', 'Disabled', 'Programmed', 'CmdTolerance', '0', 'None', '0', '0'),
    ),
    RUNG(
      XIC('MQ_IssueNextPulse'),
      XIO('UseAasCurrent'),
      EQU('CmdA_SegType', '2'),
      MCCM('X_Y', 'MoveA', '0', 'CmdA_XY[0]', 'CmdA_CircleType', 'CmdA_ViaCenter[0]', 'CmdA_Direction', 'CmdA_Speed', '"Units per sec"', 'CmdA_Accel', '"Units per sec2"', 'CmdA_Decel', '"Units per sec2"', 'S-Curve', 'CmdA_JerkAccel', 'CmdA_JerkDecel', '"Units per sec3"', 'CmdA_TermType', 'Disabled', 'Programmed', 'CmdTolerance', '0', 'None', '0', '0'),
    ),
    RUNG(
      XIC('MQ_IssueNextPulse'),
      OTL('NextIssued'),
    ),
    RUNG(
      XIC('MQ_IssueNextPulse'),
      OTU('MQ_IssueNextPulse'),
    ),
    RUNG(
      XIC('CurIssued'),
      XIC('NextIssued'),
      XIC('UseAasCurrent'),
      XIO('X_Y.MovePendingStatus'),
      XIC('MoveB.IP'),
      ONS('RotateONS_AtoB'),
      OTL('RotateMoves'),
    ),
    RUNG(
      XIC('CurIssued'),
      XIC('NextIssued'),
      XIO('UseAasCurrent'),
      XIO('X_Y.MovePendingStatus'),
      XIC('MoveA.IP'),
      ONS('RotateONS_BtoA'),
      OTL('RotateMoves'),
    ),
    RUNG(
      XIC('RotateMoves'),
      COP('NextSeg', 'CurSeg', '1'),
    ),
    RUNG(
      XIC('RotateMoves'),
      XIC('UseAasCurrent'),
      OTL('FlipToB'),
    ),
    RUNG(
      XIC('RotateMoves'),
      XIO('UseAasCurrent'),
      OTL('FlipToA'),
    ),
    RUNG(
      XIC('FlipToB'),
      OTU('UseAasCurrent'),
    ),
    RUNG(
      XIC('FlipToA'),
      OTL('UseAasCurrent'),
    ),
    RUNG(
      XIC('RotateMoves'),
      OTU('NextIssued'),
    ),
    RUNG(
      XIC('RotateMoves'),
      MOV('PendingSeq', 'ActiveSeq'),
    ),
    RUNG(
      XIC('RotateMoves'),
      MOV('0', 'PendingSeq'),
    ),
    RUNG(
      XIC('RotateMoves'),
      OTU('RotateMoves'),
    ),
    RUNG(
      XIC('FlipToA'),
      OTU('FlipToA'),
    ),
    RUNG(
      XIC('FlipToB'),
      OTU('FlipToB'),
    ),
    RUNG(
      XIC('CurIssued'),
      XIO('NextIssued'),
      XIC('UseAasCurrent'),
      XIO('X_Y.MovePendingStatus'),
      XIC('MoveA.PC'),
      ONS('DoneONS_A'),
      OTU('CurIssued'),
    ),
    RUNG(
      XIC('CurIssued'),
      XIO('NextIssued'),
      XIO('UseAasCurrent'),
      XIO('X_Y.MovePendingStatus'),
      XIC('MoveB.PC'),
      ONS('DoneONS_B'),
      OTU('CurIssued'),
    ),
    RUNG(
      XIC('AbortActive'),
      RES('CurIssueAckTON'),
    ),
    RUNG(
      XIC('AbortActive'),
      RES('NextIssueAckTON'),
    ),
    RUNG(
      XIC('AbortActive'),
      RES('QueueCtl'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTU('CurIssued'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTU('NextIssued'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTU('LoadCurReq'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTU('LoadNextReq'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTU('PrepCurMove'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTU('PrepNextMove'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTU('IssueCurPulse'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTU('MQ_IssueNextPulse'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTU('WaitCurAxisOn'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTU('WaitNextAxisOn'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTU('QueueStopRequest'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTU('AbortQueue'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTU('EnqueueReq'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTU('RotateMoves'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTU('FlipToA'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTU('FlipToB'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTL('UseAasCurrent'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTU('StartQueuedPath'),
    ),
    RUNG(
      XIC('AbortActive'),
      MOV('0', 'FaultCode'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTU('QueueFault'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTU('CheckCurSeg'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTU('CheckNextSeg'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTU('CurSeg.Valid'),
    ),
    RUNG(
      XIC('AbortActive'),
      MOV('0', 'CurSeg.Seq'),
    ),
    RUNG(
      XIC('AbortActive'),
      OTU('NextSeg.Valid'),
    ),
    RUNG(
      XIC('AbortActive'),
      MOV('0', 'NextSeg.Seq'),
    ),
    RUNG(
      XIC('AbortActive'),
      MOV('IncomingSegReqID', 'LastIncomingSegReqID'),
    ),
    RUNG(
      XIC('AbortActive'),
      MOV('0', 'ActiveSeq'),
    ),
    RUNG(
      XIC('AbortActive'),
      MOV('0', 'PendingSeq'),
    ),
    RUNG(
      XIC('AbortActive'),
      FLL('0', 'SegQueue[0]', '32'),
    ),
  ),
)
