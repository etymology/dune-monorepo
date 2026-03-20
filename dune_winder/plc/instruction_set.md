# PLC Ladder Logic Instruction Set

This list was compiled from all `.rll` and `.rllscrap` files under `plc/`.

It includes ladder instructions and built-in math/function operators used in the programs.
It does not include uppercase tag names or status members such as `STATE`, `ERROR_CODE`, `DN`, `ER`, `IP`, `PC`, or `UL`.

The operand notes below describe the operand order seen in this codebase. Some instructions support more options than are shown here.

## Instruction Reference

| Instruction | What it does | Operands used here |
| --- | --- | --- |
| `ABS` | Absolute value function. | `value` -> magnitude of the expression, usually inside `CPT` or `CMP`. |
| `ADD` | Adds two values. | `source_a, source_b, dest` -> `dest = source_a + source_b`. |
| `AFI` | Always-false condition. | No meaningful operands in these files; used as a disabled condition placeholder. |
| `ATN` | Arctangent function. | `value` -> angle of the ratio expression, usually inside `CPT`. |
| `BND` | Ends a branch block. | No data operands; closes a `BST ... NXB ... BND` branch group. |
| `BST` | Begins a branch block. | No data operands; starts a parallel branch group. |
| `CMP` | Evaluates a comparison expression. | `expression` -> boolean test such as `STATE=3` or `xy_dist_to_target<stopping_distance`. |
| `COP` | Copies raw data elements. | `source, dest, length` -> copy `length` elements from source to destination. |
| `COS` | Cosine function. | `value` -> cosine of the expression, usually inside `CPT`. |
| `CPT` | Computes an expression into a destination. | `dest, expression` -> evaluates the expression and stores the result. |
| `CTU` | Count up counter. | `counter_tag, ?, ?` -> counter structure plus preset/accum-related placeholders from the paste format. |
| `EQU` | Equality compare. | `left, right` -> true when equal. |
| `FFL` | FIFO load. | `source, array_start, control, ?, ?` -> pushes one element into the queue controlled by the control tag. |
| `FFU` | FIFO unload. | `array_start, dest, control, ?, ?` -> removes one queued element into `dest`. |
| `FLL` | Fill file. | `value, dest_start, length` -> fills `length` elements with the same value. |
| `GEQ` | Greater-than-or-equal compare. | `left, right` -> true when `left >= right`. |
| `GRT` | Greater-than compare. | `left, right` -> true when `left > right`. |
| `JMP` | Jumps to a label. | `label` -> transfers execution to the named `LBL`. |
| `JSR` | Calls a subroutine or routine. | `routine_name, parameter_block_or_0` -> invokes another routine. |
| `LBL` | Defines a jump target. | `label_name` -> destination for `JMP`. |
| `LEQ` | Less-than-or-equal compare. | `left, right` -> true when `left <= right`. |
| `LES` | Less-than compare. | `left, right` -> true when `left < right`. |
| `LIM` | Inclusive limit test. | `low, test_value, high` -> true when the test value is within the range. |
| `MAFR` | Motion axis fault reset. | `axis, control_tag` -> sends a fault reset command to an axis and tracks status in the control tag. |
| `MAM` | Motion axis move. | `axis, control_tag, move_type, position, speed, speed_units, accel, accel_units, decel, decel_units, profile, accel_jerk, decel_jerk, jerk_units, ...` -> issues a point-to-point move. |
| `MAS` | Motion axis stop. | `axis, control_tag, stop_type, decel_enable, decel, decel_units, jerk_enable, jerk, jerk_units` -> stops axis motion with configured decel/jerk behavior. |
| `MCCD` | Motion coordinated change dynamics. | `coordinate_system, control_tag, scope, speed_enable, speed, speed_units, accel_enable, accel, accel_units, decel_enable, decel, decel_units, accel_jerk_enable, accel_jerk, decel_jerk_enable, decel_jerk, jerk_units, apply_to` -> changes active coordinated-move dynamics. |
| `MCCM` | Motion coordinated circular move. | `coordinate_system, control_tag, move_type, end_xy, circle_type, via_or_center_xy, direction, speed, speed_units, accel, accel_units, decel, decel_units, profile, accel_jerk, decel_jerk, jerk_units, termination_type, ...` -> issues an arc move in a coordinate system. |
| `MCLM` | Motion coordinated linear move. | `coordinate_system, control_tag, move_type, end_position_or_xy, speed, speed_units, accel, accel_units, decel, decel_units, profile, accel_jerk, decel_jerk, jerk_units, termination_type, ...` -> issues a linear coordinated move. |
| `MCS` | Motion coordinated stop. | `coordinate_system, control_tag, stop_type, decel_enable, decel, decel_units, jerk_enable, jerk, jerk_units` -> stops coordinated motion. |
| `MOD` | Modulo function. | `left, right` inside an expression -> remainder after division. |
| `MOV` | Copies one value to another. | `source, dest` -> simple assignment. |
| `MSF` | Motion servo off. | `axis, control_tag` -> removes servo power from an axis and tracks status. |
| `MSO` | Motion servo on. | `axis, control_tag` -> enables servo power on an axis and tracks status. |
| `NEQ` | Not-equal compare. | `left, right` -> true when values differ. |
| `NOP` | No operation. | No data operands; used as an empty target rung or label landing point. |
| `NXB` | Next branch. | No data operands; separates alternatives inside a `BST ... BND` branch group. |
| `ONS` | One-shot rising. | `storage_bit, output_bit` -> pulses `output_bit` for one scan on a false-to-true transition. |
| `OSF` | One-shot falling. | `storage_bit, output_bit` -> pulses `output_bit` for one scan on a true-to-false transition. |
| `OSR` | One-shot rising. | `storage_bit, output_bit` -> pulses `output_bit` for one scan on a false-to-true transition. |
| `OTE` | Output energize. | `dest_bit` -> writes the rung result to a bit while the rung is true. |
| `OTL` | Output latch. | `dest_bit` -> latches a bit on until an `OTU` clears it. |
| `OTU` | Output unlatch. | `dest_bit` -> clears a latched bit. |
| `PID` | PID control instruction. | `control_block, process_variable, tieback, control_variable, ...` -> runs the PID loop using the structure and connected values. |
| `RES` | Reset timer/counter/control. | `tag` -> resets the target instruction structure. |
| `SFX` | Safe feedback instruction. | `control_tag, time_units, ..., position_feedback, velocity_feedback, valid_bit, fault_bit, home_trigger, reset, homed_status, fault_status` -> evaluates safe feedback/home status. |
| `SIN` | Sine function. | `value` -> sine of the expression, usually inside `CPT`. |
| `SLS` | Safely-limited speed instruction. | `control_tag, mode_a, mode_b, speed_limit, active_limit, feedback_tag, request_bit, reset_bit, active_status, limit_status, fault_status` -> configures/monitors safe limited speed. |
| `SQR` | Square root function. | `value` -> square root of the expression. |
| `TON` | Timer on delay. | `timer_tag, ?, ?` -> timer structure plus preset/accum placeholders from the paste format. |
| `XIC` | Examine if closed. | `source_bit` -> true when the referenced bit is on. |
| `XIO` | Examine if open. | `source_bit` -> true when the referenced bit is off. |

## Notes

- `ONS` and `OSR` both appear here and are used as one-shot rising instructions in the pasted ladder text.
- The motion instructions (`MAM`, `MAS`, `MCCD`, `MCCM`, `MCLM`, `MCS`, `MAFR`, `MSF`, `MSO`) have long vendor-defined parameter lists. The table above summarizes the operands that are visible in this project rather than every optional field supported by Studio 5000.
- Math functions such as `ABS`, `ATN`, `COS`, `MOD`, `SIN`, and `SQR` mostly appear inside `CPT` or `CMP` expressions rather than as standalone rungs.
