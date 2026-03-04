###############################################################################
# Name: G_Codes.py
# Uses: List of G-Code function numbers.
# Date: 2016-03-31
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################


class G_Codes:
  LATCH = 100  # No parameters.
  WIRE_LENGTH = 101  # Amount of wire (in mm) used in move.
  SEEK_TRANSFER = 102  # No parameters.
  PIN_CENTER = 103  # Pin 1, Pin 2, Axises (X/Y/XY).
  CLIP = 104  # No parameters.
  OFFSET = 105  # Axis (X/Y) and a number.  Can have multiple parameters.
  HEAD_LOCATION = 106  # 0=front, 1=level front, 2=level back, 3=back.
  DELAY = 107  # Time (milliseconds).
  ARM_CORRECT = 108  # No parameters.
  ANCHOR_POINT = 109  # Anchor pin, orientation (0/TR/TL/RB/RT/BL/BR/LT/LB).
  TRANSFER_CORRECT = 110  # Axis (X/Y).
  BREAK_POINT = 111  # No parameters.
  TENSION_TESTING = 112  # Tension testing script
