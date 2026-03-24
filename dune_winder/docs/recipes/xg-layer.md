# X/G Layer Recipe Description

Let B960 calibration be cameraHead and B1 calibration camreaFoot (cartesian)

Then let the wire locations be defined as wireHead = cameraHead + cameraOfffset and wireFoot = cameraFoot + cameraOffset

Where cameraOffset is a vector representing the distance between the camera and the wire.
let wireSpacing = 230/48

let headTransferZone = 440
let footTransferZone = 7165
let headPullFlat = 635
let footPullFlat = 7016
let diagonalCorrect = 3

let there be 4 configurable parameters headBoffset, footBoffset, headAoffset, footAoffset
let another configurable parameter be transferPause in {True, False}

let the preamble be
X{headTransferZone} Y{wireHead+headAoffset}
G106 P0

Then let wrap the first consist of the following steps:

X{headTransferZone} Y{wireHead+headAoffset + if(n>1, diagonalCorrect,0) + (n-1)*wireSpacing}
X{headPullFlat}
X{footTransferZone} Y{wireFoot+footAoffset+ (n-1)*wireSpacing}
G106 P0
G106 P1 (optionally, if transferPause is True)
G106 P3
X{footPullFlat} Y{wireFoot+footBoffset+ (n-1)*wireSpacing}
X{headTransferZone} Y{wireHead+headBoffset + (n-1)*wireSpacing}
G106 P2 (optionally, if transferPause is True)
G106 P0

and a recipe consists of this 480 times for n in 1...480 for X layer and 481 times for G layer.
followed by the postamble:
X{headPullFlat} Y{wireHead+headAoffset + 480*wireSpacing}

The recipe is a file of type .gc called X-layer.gc or G-layer.gc with the header ( X-layer ) or ( G-layer )
