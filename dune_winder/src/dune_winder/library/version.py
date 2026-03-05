###############################################################################
# Name: Version.py
# Uses: Compute and update version information based on hash of file set.
# Date: 2016-05-13
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

import xml.dom.minidom
import re
import os
import datetime
from .hash import Hash


class Version:
  # -------------------------------------------------------------------
  def __init__(self, versionFileName, path=".", includeMask=".*", excludeMask="^$"):
    """
    Constructor.
    """

    self._fileName = os.path.abspath(versionFileName)
    self._path = os.path.abspath(path)
    self._includeMask = includeMask
    self._excludeMask = excludeMask
    self._computedHash = None
    self._isValid = False  # Isn't valid until checked.

    try:
      self._xml = xml.dom.minidom.parse(versionFileName)
    except IOError:
      self._xml = xml.dom.minidom.parseString("<version/>")
      self._set("string", "0.0.0")
      self._set("hash", "")
      self._set("date", "")

  # ---------------------------------------------------------------------
  def _get(self, tag):
    """
    Retrieve the value of a tag.

    Returns:
      Value of a tag.  None returned if the tag does not exist.
    """
    # Try and find this value.
    node = self._xml.getElementsByTagName(tag)

    result = None
    if [] != node:
      node = node[0]
      # Allow for empty values.
      # This isn't None--this is an empty string.
      result = ""

      # If there is a text field...
      if node.firstChild and node.firstChild.nodeValue:
        result = node.firstChild.nodeValue

    return result

  # ---------------------------------------------------------------------
  def _set(self, tag, value):
    """
    Set an XML value.

    Args:
      tag: Name of the value.
      value: New value to set.

    Notes:
      If the tag doesn't exist, it will be created.
    """

    # Try and find this value.
    node = self._xml.getElementsByTagName(tag)

    # If values doesn't exist...
    if [] == node:
      # Create an entry for this value.
      node = self._xml.createElement(tag)
      self._xml.childNodes[0].appendChild(node)
    else:
      # Select the first instance of this value.
      node = node[0]

      # Remove existing children (values).
      while node.childNodes:
        node.removeChild(node.childNodes[-1])

    # Create a node for the value.
    valueNode = self._xml.createTextNode(str(value))

    # Set the value.
    node.appendChild(valueNode)

  # ---------------------------------------------------------------------
  def update(self):
    """
    Update the version information.  Computes the hash and increments version
    number if has does not match.

    Returns:
      True if the version has changed, False if not.
    """
    hasChanged = not self.verify()
    if hasChanged:
      versionString = self._get("string")
      major, minor, build = versionString.split(".")
      build = int(build) + 1
      versionString = str(major) + "." + str(minor) + "." + str(build)
      self._set("string", versionString)
      self._set("hash", self._computedHash)
      self._set("date", str(datetime.datetime.now()))
      self._isValid = True
      self.save()

    return hasChanged

  # ---------------------------------------------------------------------
  def getHash(self):
    """
    Return the version hash.

    Returns:
      Base-32 hash value for version.
    """
    return self._get("hash")

  # ---------------------------------------------------------------------
  def getVersion(self):
    """
    Return version string.

    Returns:
      Version string in m.n.b (major, minor, build) notation.
    """
    return self._get("string")

  # ---------------------------------------------------------------------
  def getDate(self):
    """
    Return the build timestamp.

    Returns:
      Build timestamp in yyyy-mm-dd hh:mm:ss.uuuuuu format.
    """
    return self._get("date")

  # ---------------------------------------------------------------------
  def compute(self):
    """
    Compute a hash value for all files.

    Returns:
      Hash string value for version.
    """
    hashValue = Hash()
    for root, directoryNames, fileNames in os.walk(self._path):
      for fileName in fileNames:
        if re.match(self._includeMask, fileName) and not re.match(
          self._excludeMask, fileName
        ):
          fullName = os.path.join(root, fileName)
          with open(fullName, "rb") as inputFile:
            buffer = inputFile.read()

            # Line-ending workaround.
            # Manually convert DOS-style carriage return, line feed into just
            # a line feed by removing the carriage return.
            # This fixes the fact the version control software can change
            # line ending types upon checkout which would otherwise cause a
            # different hash.

            strBuffer = buffer.decode()
            strBuffer = strBuffer.replace("\r", "")

            hashValue += strBuffer.encode()

    # Turn hash into string.
    self._computedHash = str(hashValue)

    return self._computedHash

  # ---------------------------------------------------------------------
  def verify(self):
    """
    Check to see if the version information on disk matches the computed hash.

    Returns:
      True if the hash matches, False if not.
    """
    versionHash = self.compute()
    self._isValid = versionHash == self.getHash()
    return self._isValid

  # ---------------------------------------------------------------------
  def isValid(self):
    """
    Check to see if the version information is valid.

    Returns:
      True if the hash matches, False if not.

    Notes:
      Does not do any calculations, so 'verify' must be called at some point
      prior.  Otherwise, this function will return False.
    """
    return self._isValid

  # ---------------------------------------------------------------------
  def save(self):
    """
    Write the version data to disk.
    """
    outputText = self._xml.toprettyxml()

    # Strip off extraneous line feeds.
    outputText = (
      "\n".join([line for line in outputText.split("\n") if line.strip()]) + "\n"
    )

    with open(self._fileName, "wb") as outputFile:
      outputFile.write(outputText.encode())


# ------------------------------------------------------------------------------
# Unit test.
# ------------------------------------------------------------------------------
if __name__ == "__main__":
  version = Version("testVersion.xml", ".", ".*\.py")
  print(version.update())
  print(version.getVersion())
  print(version.getDate())
  print(version.verify())
