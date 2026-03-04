###############################################################################
# Name: PLC.py
# Uses: Abstract PLC class.
# Date: 2016-02-26
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from dune_winder.io.Devices.IO_Device import IO_Device
from abc import ABCMeta, abstractmethod


class PLC(IO_Device, metaclass=ABCMeta):
  # There is a limit to the length of packets to/from the PLC.  When reading
  # tags the request must be limited.  I have found no documentation as to how
  # to calculate this limit, but found I could read 18 with the tag name sizes
  # currently in the queue.  So 14 seems a safe number.
  MAX_TAG_READS = 14

  # ============================================================================
  class Tag:
    """
    PLC Tag.  System PLC's use to repreent data.
    Notes:
      Use the Attributes subclass to define how the tag behaves.
    """

    # List of all tags.
    instances: list["PLC.Tag"] = []

    # Look-up table to match tag names to instances of Tag.  The look-up is
    # a list of tag instances in case there are multiple Tag instances for the
    # same tag name.
    tag_lookup_table: dict[str, list["PLC.Tag"]] = {}

    # Various attributes an I/O word can have.
    class Attributes:
      canRead = True  # False for write-only.
      canWrite = True  # False for read-only.
      isPolled = False  # True if this tag should be polled regularly.
      defaultValue = None  # Default state if tag is unreadable.

    # end class

    # ---------------------------------------------------------------------
    def __init__(
      self, plc: "PLC", tagName: str, attributes=Attributes(), tagType="DINT"
    ):
      """
      Constructor.

      Args:
        plc: Instance of IO_Device.PLC.
        tagName: Which PLC tag this input is assigned.
        tagType: The type of tag value.
        attributes: Attributes of tag (must be instance of Attributes)
      """

      # Cannot create a tag that cannot be read but is polled.
      assert attributes.canRead or not attributes.isPolled

      PLC.Tag.instances.append(self)

      # Add this tag to the look-up table.
      if tagName in PLC.Tag.tag_lookup_table:
        PLC.Tag.tag_lookup_table[tagName].append(self)
      else:
        PLC.Tag.tag_lookup_table[tagName] = [self]

      self._plc = plc
      self._tagName = tagName
      self._attributes = attributes
      self._type = tagType
      self._value = attributes.defaultValue

    # ---------------------------------------------------------------------
    def getName(self):
      """
      Return name of this tag.

      Args:
        name: Name of this tag.
      """
      return self._tagName

    # ---------------------------------------------------------------------
    def poll(self):
      """
      Update the input by reading the value form PLC.  Call periodically.
      """
      value = self._plc.read(self._tagName)
      if value is not None and not self._plc.isNotFunctional():
        self.updateFromReadTag(value[0])
      else:
        self._value = self._attributes.defaultValue

    # ---------------------------------------------------------------------
    @staticmethod
    def pollAll(plc: "PLC"):
      """
      Update all tags.

      Future:
        All tags could be read at once, which may be useful in reducing
        Ethernet traffic.
      """

      tagList = []
      for tag in PLC.Tag.instances:
        # If this tag is polled...
        if tag._attributes.isPolled:
          tagName = tag.getReadTag()

          # If this tag is not already in the list...
          if tagName not in tagList:
            tagList.append(tagName)

      # Break list into sub-sets of no more than 'maxTagsAtOnce' tags.
      tagSubset = [
        tagList[tag : tag + PLC.MAX_TAG_READS]
        for tag in range(0, len(tagList), PLC.MAX_TAG_READS)
      ]

      # For each tag subset...
      for tagList in tagSubset:
        # Read all the tags in this subset.
        results = plc.read(tagList)

        if results is not None:
          # Distribute the results to the tag objects.
          for result in results:
            # For each object that uses this tag name...
            for tag in PLC.Tag.tag_lookup_table[result[0]]:
              # Send it the result.
              tag.updateFromReadTag(result[1])
        else:
          for tagName in tagList:
            for tag in PLC.Tag.tag_lookup_table[tagName]:
              tag._value = tag._attributes.defaultValue

    # ---------------------------------------------------------------------
    def getReadTag(self):
      """
      Get read tag.  Used when reading multiple tags at once.

      Returns:
        Name of tag for reading.  None if this is a write-only tag.
      """
      result = None
      if self._attributes.canRead:
        result = self._tagName

      return result

    # ---------------------------------------------------------------------
    def updateFromReadTag(self, value):
      """
      Update internal state from tag data.  Used when multiple reads have
      been done at once to feed back data.
      """
      if self._attributes.canRead:
        self._value = value

    # ---------------------------------------------------------------------
    def get(self):
      """
      Fetch last read value of tag.

      Returns:
        Last read value of tag.

      Note:
        Does not reflect any useful value until polled.  If the PLC isn't
        functional, this value returns a default value.
      """
      return self._value

    # ---------------------------------------------------------------------
    def set(self, value):
      """
      Set the value.

      Args:
        value: New data to be written.

      Returns:
          True if there was an error, False if not.
      """
      isError = False

      result = self._plc.write((self._tagName, value))
      if result is None:
        isError = True
      else:
        self._value = value

      return isError

  # end class
  # ============================================================================

  # ---------------------------------------------------------------------
  @abstractmethod
  def initialize(self):
    """
    Try and establish a connection to the PLC.

    Returns:
      True if there was an error, False if connection was made.
    """
    pass

  # ---------------------------------------------------------------------
  @abstractmethod
  def isNotFunctional(self):
    """
    See if the PLC is communicating correctly.

    Returns:
      True there is a problem with hardware, false if not.
    """
    pass

  # ---------------------------------------------------------------------
  @abstractmethod
  def read(self, tag):
    """
    Read a tag(s) from the PLC.

    Args:
      tag: A single or a list of PLC tags.

    Returns:
      Result of the data read, or None if there was a problem.
    """
    pass

  # ---------------------------------------------------------------------
  @abstractmethod
  def write(self, tag, data=None, typeName=None):
    """
    Write a tag(s) to the PLC.

    Args:
      tag: A single or a list of PLC tags.
      data: Data to be written.
      typeName: Type of the tag to write.

    Returns:
        None is returned in case of error otherwise the tag list is returned.
    """
    pass


# end class
