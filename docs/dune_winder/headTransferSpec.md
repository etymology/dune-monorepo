# head transfer spec

The head transfer is a special state of the winder

## the latching state
The latching state is a state of the winder interface in which we pulse gui_latch_pulse and await the latch moving to the desired position.

the relevant tags are:

- Z_STAGE_PRESENT bool
- Z_FIXED_PRESENT bool
- Z_FIXED_LATCHED bool
- Z_STAGE_LATCHED bool
- Z_RETRACTED bool
- Z_EXTENDED bool
- Z_axis (cip motion control axis, including Z_axis.ActualPosition)

- ACTUATOR_POS in [0,1,2,3]

The latch has two cycles: when Z_STAGE_PRESENT is not true, the latch cycles in 0 3 2.

When Z_STAGE_PRESENT and Z_FIXED_PRESENT are both true, the latch moves between 3 2 1.

In a transfer command we 