###############################################################################
# Name: Configuration.py
# Uses: Simple non-volatile configuration.
# Date: 2016-02-23
# Author(s):
#   Andrew Que <aque@bb7.com>
# Notes:
#   Extremely simple configuration file.
# Example:
#   configuration = Configuration( "configuration.xml" )
#   configuration.set( "Name", "Andrew Que" )
#   configuration.set( "e-mail", "aque@bb7.com" )
#   name = configuration.get( "Name" )  # <- 'name' will be "Andrew Que"
###############################################################################

import xml.dom.minidom


class Configuration:
  # ---------------------------------------------------------------------
  def __init__(self, fileName="configuration.xml"):
    """
    Constructor.

    Args:
      fileName: File to use for configuration data.  This is an XML file.
    """
    self._fileName = fileName
    try:
      self._doc = xml.dom.minidom.parse(fileName)
    except IOError:
      self._doc = xml.dom.minidom.parseString("<config/>")

  # ---------------------------------------------------------------------
  def default(self, tag, defaultValue):
    # Try and find this value.
    node = self._doc.getElementsByTagName(tag)

    # If values doesn't exist, we will create it with the default value...
    if [] == node:
      # Create an entry for this value.
      node = self._doc.createElement(tag)
      self._doc.childNodes[0].appendChild(node)

      # Create a node for the value.
      valueNode = self._doc.createTextNode(str(defaultValue))

      # Set the value.
      node.appendChild(valueNode)

  # ---------------------------------------------------------------------
  def save(self):
    """
    Write the configuration to disk.
    """
    outputText = self._doc.toprettyxml()

    # Strip off extraneous line feeds.
    outputText = (
      "\n".join([line for line in outputText.split("\n") if line.strip()]) + "\n"
    )

    with open(self._fileName, "wb") as outputFile:
      outputFile.write(outputText.encode())

  # ---------------------------------------------------------------------
  def set(self, tag, value):
    """
    Set a configuration value.

    Args:
      tag: Name of the configuration value.
      value: New value to set.

    Notes:
      If the tag doesn't exist, it will be created.  The new value is
      saved after being set.
    """

    # Try and find this value.
    node = self._doc.getElementsByTagName(tag)

    # If values doesn't exist...
    if [] == node:
      # Create an entry for this value.
      node = self._doc.createElement(tag)
      self._doc.childNodes[0].appendChild(node)
    else:
      # Select the first instance of this value.
      node = node[0]

      # Remove existing children (values).
      while node.childNodes:
        node.removeChild(node.childNodes[-1])

    # Create a node for the value.
    valueNode = self._doc.createTextNode(str(value))

    # Set the value.
    node.appendChild(valueNode)

    self.save()

  # ---------------------------------------------------------------------
  def get(self, tag):
    """
    Retrieve the value of a configuration tag.

    Returns:
      Value of a configuration tag.  None returned if the tag does not exist.
    """
    # Try and find this value.
    node = self._doc.getElementsByTagName(tag)

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


# ------------------------------------------------------------------------------
# Unit test.
# ------------------------------------------------------------------------------
if __name__ == "__main__":
  config = Configuration("test.xml")
  value = int(config.get("test"))
  value += 1
  config.set("test", value)
  print(config.get("test"))
  config.save()
