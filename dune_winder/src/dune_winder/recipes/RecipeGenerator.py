###############################################################################
# Name: RecipeGenerator.py
# Uses: Base recipe generation class.
# Date: 2016-03-23
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from dune_winder.library.SerializableLocation import SerializableLocation
from dune_winder.library.Recipe import Recipe

from .G_CodeFunctions.PinCenterG_Code import PinCenterG_Code
from .Path3d import Path3d

from dune_winder.machine.LayerCalibration import LayerCalibration


class RecipeGenerator:
  """
  Base recipe class.
  """

  # ---------------------------------------------------------------------
  def __init__(self, geometry):
    """
    Constructor.

    Args:
      geometry: Instance of LayerGeometry (specifically one of its children).
    """
    self.net = []
    self.nodes = {}
    self.gCodePath = None
    self.nodePath = None
    self.z = None

    self.geometry = geometry
    self.headZ = 0
    self.netIndex = 0
    self.centering = {}

    # G-Code path is the motions taken by the machine to wind the layer.
    self.firstHalf = None
    self.secondHalf = None

    # The node path is a path of points that are connect together.  Used to calculate
    # the amount of wire actually dispensed.
    # NOTE: Z is ignored because the hand-offs are independent of offset location.
    self._frameOffset = geometry.apaOffset.add(geometry.apaLocation)
    self._frameOffset.z = 0

    self.basePath = Path3d()
    self.nodePath = Path3d(self._frameOffset)

  # ---------------------------------------------------------------------
  def offsetPin(self, pin, offset):
    """
    Offset to a pin number.  Useful for finding the pin names on either side
    of some pin.

    Args:
      pin: Pin name to offset.
      offset: Amount to offset pin.

    Returns:
      Pin name of offset pin.
    """
    side = pin[0]
    pinNumber = int(pin[1:]) - 1
    pinNumber += offset
    pinNumber %= self.geometry.pins
    pinNumber += 1
    return side + str(pinNumber)

  # ---------------------------------------------------------------------
  def pinNames(self, startPin, direction):
    """
    Return a pair of pin names of two pins next to one an other.

    Args:
      side: 'F' for front, 'B' for back side.
      startPin: First pin number.
      direction: Either -1 or 1 to fetch the pin on either side.

    Returns:
      List of two pin name strings.
    """
    pinA = self.net[startPin]
    pinB = self.offsetPin(pinA, direction)
    return [pinA, pinB]

  # ---------------------------------------------------------------------
  def center(self, startPin, direction):
    """
    Get the center location between two pins.

    Args:
      startPin: Net index of the first pin.
      direction: +1 or -1 to select neighbor for centering.

    Returns:
      Location instance with the center point between these two pins.
    """
    pin = self.net[startPin]
    pinA = self.nodes[pin]

    pin = self.offsetPin(pin, direction)
    pinB = self.nodes[pin]

    return pinA.center(pinB)

  # ---------------------------------------------------------------------
  def location(self, net):
    """
    Get the location of a pin by net index.

    Args:
      net: Net index of the pin.

    Returns:
      Location instance of the net.
    """
    pin = self.net[net]
    return self.nodes[pin]

  # ---------------------------------------------------------------------
  def pinCenterTarget(self, axis="XY", pinNames=None):
    """
    Setup the G-Code function class for targeting the left/right of the next
    pin in the net.  Based on the pin this will figure out which side of the
    pin the wire should target.

    Args:
      axis: Either "X", "Y" or "XY" for which coordinates will be used in the
            targeting.
    Returns:
      An instance of PinCenterG_Code (G_CodeFunction).
    """
    if pinNames is None:
      net = self.net[self.netIndex]
      direction = self.centering[net]
      pinNames = self.pinNames(self.netIndex, direction)

    return PinCenterG_Code(pinNames, axis)

  # ---------------------------------------------------------------------
  def writeRubyBasePath(self, outputFileName, isAppend=True):
    """
    Make the basic wire path.  This is pin-center to pin-center without
    considering diameter of pin.  Debug function.

    Args:
      outputFileName: File name to create.
      enableWire: Show the wire wound on the layer.
      isAppend: True to append file, False to overwrite.
    """
    attributes = "w"
    if isAppend:
      attributes = "a"

    with open(outputFileName, attributes) as rubyFile:
      path3d = Path3d()
      for net in self.net:
        node = self.nodes[net]
        path3d.push(node.x, node.y, node.z)

      path3d.toSketchUpRuby(rubyFile)

  # ---------------------------------------------------------------------
  def writeRubyCode(
    self,
    layerName,
    half,
    outputFileName,
    enablePath=True,
    enablePathLabels=False,
    enableWire=True,
    isAppend=True,
  ):
    """
    Export node paths to Ruby code for import into SketchUp for visual
    verification.  Debug function.

    Args:
      half: 0 for first half, 1 for second half.
      outputFileName: File name to create.
      enablePath: Show the path taken to wind the layer.
      enablePathLabels: Label additional G-Code points.
      enableWire: Show the wire wound on the layer.
      isAppend: True to append the ruby file rather than overwrite it.
    """

    attributes = "w"
    if isAppend:
      attributes = "a"

    with open(outputFileName, attributes) as rubyFile:
      if enablePath:
        if 0 == half:
          if self.firstHalf:
            self.firstHalf.toSketchUpRuby(rubyFile, layerName, "1st", enablePathLabels)
        else:
          if self.secondHalf:
            self.secondHalf.toSketchUpRuby(rubyFile, layerName, "2nd", enablePathLabels)

      if enableWire:
        self.nodePath.toSketchUpRuby(rubyFile, "Path " + layerName)

  # ---------------------------------------------------------------------
  def writeRubyAnimateCode(self, outputFileName, number):
    """
    Create SketchUp ruby code to have an animation with one new path displayed
    in each scene.  Debug function.

    Args:
      outputFileName: Where to write this data.
      number: Number of segments of the path to animate.
    """
    with open(outputFileName, "w") as output:
      for index in range(0, number):
        output.write(
          "layer"
          + str(index)
          + ' = Sketchup.active_model.layers.add "wire'
          + str(index)
          + '"'
        )

        output.write("layer" + str(index) + ".visible = false")
        output.write("Sketchup.active_model.active_layer = layer" + str(index))

        # Convert millimeters to inches.  Sketch-up always works in inches.
        point = self.nodePath.path[index]
        x1 = point.x / 25.4
        y1 = point.y / 25.4
        z1 = point.z / 25.4

        point = self.nodePath.path[index + 1]
        x2 = point.x / 25.4
        y2 = point.y / 25.4
        z2 = point.z / 25.4

        output.write(
          "Sketchup.active_model.entities.add_line "
          + "["
          + str(x1)
          + ","
          + str(z1)
          + ","
          + str(y1)
          + "], "
          + "["
          + str(x2)
          + ","
          + str(z2)
          + ","
          + str(y2)
          + "]"
        )

      for index in range(0, number):
        output.write(
          "page"
          + str(index)
          + ' = Sketchup.active_model.pages.add "page'
          + str(index)
          + '"'
        )

        for indexB in range(0, number):
          visible = "true"
          if indexB > index:
            visible = "false"

          output.write("layer" + str(indexB) + ".visible = " + visible)

  # ---------------------------------------------------------------------
  def writeG_Code(self, outputFileName, outputExtension, layerName):
    """
    Export G-Code to file.

    Args:
      outputFileName: File name to create (less extension).
      outputExtension: Extension of file to create.
      layerName: Name of recipe.

    Note:
      Two files are created with the name <outputFileName>_1<outputExtension>
      and <outputFileName>_2<outputExtension>.
    """

    # Safe G-Code instructions.
    if self.firstHalf:
      with open(outputFileName + "_1." + outputExtension, "w") as gCodeFile:
        self.firstHalf.toG_Code(gCodeFile, layerName + " first half")

      # Create an instance of Recipe to update the header with the correct hash.
      Recipe(outputFileName + "_1." + outputExtension, None)

    if self.secondHalf:
      with open(outputFileName + "_2." + outputExtension, "w") as gCodeFile:
        self.secondHalf.toG_Code(gCodeFile, layerName + " second half")

      # Create an instance of Recipe to update the header with the correct hash.
      Recipe(outputFileName + "_2." + outputExtension, None)

  # ---------------------------------------------------------------------
  def defaultCalibration(self, layerName, geometry, saveCalibration=False):
    """
    Export node list to calibration file.  Debug function.

    Args:
      layerName: Name of recipe.
      geometry: Geometry for layer.
      saveCalibration: True to save calibration file to disk.

    Returns:
      Instance of calibration.
    """

    calibration = LayerCalibration(layerName)
    offset = geometry.apaLocation.add(geometry.apaOffset)
    calibration.offset = SerializableLocation.fromLocation(offset)

    for node in self.nodes:
      calibration.setPinLocation(node, self.nodes[node])

    if saveCalibration:
      calibration.save(".", layerName + "_Calibration.xml")

    return calibration

  # ---------------------------------------------------------------------
  def printStats(self):
    """
    Print some statistics about the layer.
    """

    print("Wire consumed:", "{:,.2f}mm".format(self.nodePath.totalLength()))
    if self.firstHalf:
      print("G-Code lines (1st half):", len(self.firstHalf))

    if self.secondHalf:
      print("G-Code lines (2nd half):", len(self.secondHalf))

  # ---------------------------------------------------------------------
  @staticmethod
  def _pinCompare(pinA, pinB):
    """
    Compare two pin numbers.  Used for sorting a list of pin names.
    Debug function.

    Args:
      pinA: First pin.
      pinB: Second pin.

    Returns:
      0 = pins are identical, 1 = pinA < pinB, -1 = pinA > pinB.
    """
    pinA_Side = pinA[0]
    pinB_Side = pinB[0]
    pinA_Number = int(pinA[1:])
    pinB_Number = int(pinB[1:])

    result = 0
    if pinA_Side < pinB_Side:
      result = 1
    elif pinA_Side > pinB_Side:
      result = -1
    elif pinA_Number < pinB_Number:
      result = -1
    elif pinA_Number > pinB_Number:
      result = 1

    return result

  # ---------------------------------------------------------------------
  def printNodes(self):
    """
    Print a sorted list of all the pin names.  Debug function.
    """
    for node in sorted(self.nodes, cmp=RecipeGenerator._pinCompare):
      side = node[0]
      pin = node[1:]
      location = str(self.nodes[node])[1:-1].replace(" ", "")
      print(side + "," + pin + "," + location)

  # ---------------------------------------------------------------------
  def printNet(self):
    """
    Print the net list (which pin is connected to which) and the location of
    these pins.
    """
    for net in self.net:
      print(net, self.nodes[net])
