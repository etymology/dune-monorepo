# End to end change to diagonal layer workflow and

The desired UV workflow is similar to the one we do today but different mainly in the area of solving for the machine calibration, in the nature of the calibration artifacts stored and how they are used.

Today the UV calibration routines save json files with the winder coordinates (i.e. "camera coordinates") plus the camera wire offset. These adjusted positions are then used by the solver called by the ~anchorToTarget macro to determine the command position of the winder in order to stretch a wire from the anchor pin to the target pin, tangent to both pins on the correct sides of the pins, and taking into account that the wire does not actually go to the camera position but to a position displaced from the camera position by a certain amount. This displacement is the "camera wire offset" plus the "arm correction" which will be explained in further detail below.

The desired workflow will save the calibration files as raw winder coordinates captured without adding the camera wire offset, and 