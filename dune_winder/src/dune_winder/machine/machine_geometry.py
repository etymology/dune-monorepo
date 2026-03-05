###############################################################################
# Name: MachineGeometry.py
# Uses: Geometry of outer winding machine.
# Date: 2016-03-24
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from dune_winder.library.Geometry.line import Line
from dune_winder.library.Geometry.box import Box


class MachineGeometry(object):
  # -------------------------------------------------------------------
  def __init__(self):
    """
    Constructor.
    """

    # Scale down factor for geometry.
    # Debug only.  Set to 1 for production.
    self.scale = 1

    # Handles on either side of the APA.
    self.handleWidth = 330.2 / self.scale

    # Note: 440/515 is arbitrary.
    self.leftHandle = ((300.764 - 25.4 / 2) - 440) / self.scale
    self.rightHandle = ((7109.333 - 25.4 / 2) - 515) / self.scale

    # Hard machine limits.
    self.limitTop = 2827.752 / self.scale
    self.limitBottom = 0 / self.scale
    self.limitLeft = 0 / self.scale
    self.limitRight = 7360.436 / self.scale
    self.limitRetracted = 0 / self.scale
    self.limitExtended = 450 / self.scale

    # Location of Z-Transfer areas.
    # Top/bottom for Y, left/right for X.
    self.top = 2771.5 / self.scale
    self.bottom = 4 / self.scale
    self.left = (self.leftHandle + self.handleWidth / 2) / self.scale
    self.right = (self.rightHandle + self.handleWidth / 2) / self.scale

    # How big the Z-transfer windows are.
    # The Z-transfer windows start at top/bottom/left/right locations.
    self.zWindow = 20

    # Amount of distance the Z-axis can travel.
    self.zTravel = 434

    # Locations for extended and retracted.
    self.retracted = 0
    self.extended = self.zTravel

    # Distance from the inner pulley edge to the outer roller edge on the
    # winder head arm.
    self.headRollerRadius = 6.35  # 1/4"
    self.headRollerGap = 1.27  # 0.05"
    self.headArmLength = 125.71424938

    # Lines defining the where a Z hand-off can take place.  Used for intercept
    # calculations.
    self.lineTop = Line(0, self.top)
    self.lineBottom = Line(0, self.bottom)
    self.lineLeft = Line(Line.VERTICLE_SLOPE, self.left)
    self.lineRight = Line(Line.VERTICLE_SLOPE, self.right)

    # Box that defines the Z hand-off edges.
    self.edges = Box(self.left, self.top, self.right, self.bottom)
