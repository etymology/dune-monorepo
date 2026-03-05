###############################################################################
# Name: Serializable.py
# Uses: Interface class to define an object that can be de/serialized into XML.
# Date: 2016-03-01
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

import os
import tempfile
import xml.dom.minidom


class Serializable:
  # Only the following built-in types are supported.
  # (Basically, anything that can easily be turned to/from a string.)
  SUPPORTED_PRIMITIVES = (int, int, float, complex, str, bool, list, dict, type(None))

  # ---------------------------------------------------------------------
  def __init__(self, includeOnly=None, exclude=None, ignoreMissing=False):
    """
    Constructor.

    Args:
      includeOnly: List of class variables to include in serialization.  None to
        include all, or use exclude list.
      exclude: List of class variables to exclude in serialization.  includeOnly
        must be None for this to have effect.  None to include all class
        variables.
    """

    if includeOnly is not None:
      self._serializeIncludeOnly = includeOnly

    if exclude is not None:
      self._serializeIgnore = exclude
      self._serializeIgnore.append("_serializeIgnore")
      self._serializeIgnore.append("_ignoreMissing")

    self._ignoreMissing = ignoreMissing

  # ---------------------------------------------------------------------
  def getVariableList(self):
    """
    Get a list of class variables that should be serialized.  Protected function.

    Returns:
      List of class variables names.

    Notes:
      The variable names are can be found in self.__dict__.
    """

    # Make a list of the variables that will be saved.
    # There can either be a list of variables to include, or a list to exclude.
    # If neither, all are included.
    variables = list(self.__dict__.keys())
    if "_serializeIncludeOnly" in self.__dict__:
      variables = self._serializeIncludeOnly
    elif "_serializeIgnore" in self.__dict__:
      variables = [x for x in variables if x not in self._serializeIgnore]

    return variables

  # ---------------------------------------------------------------------
  def serializeObject(self, xmlDocument: xml.dom.minidom.Document, variable, value):
    """
    Convert variable/value pair into XML node.  Recursive.

    Args:
      xmlDocument: Instance of xml.dom.minidom.Document.
      variable: String name of variable.
      value: Value to serialize (either a primitive or serializable object).

    Returns:
      XML node.

    Notes:
      This is a recursive function in order to handle lists and dictionaries.
    """

    node = None

    if isinstance(value, (list, dict)):
      # Create child node for the list/dictionary.
      node = xmlDocument.createElement(value.__class__.__name__)
      node.setAttribute("name", str(variable))

      if isinstance(value, list):
        # Turn list into dictionary.
        subVariables = dict(enumerate(value))
      else:
        # Use the dictionary.
        subVariables = value

      for subVariable in subVariables:
        subValue = subVariables[subVariable]
        subNode = self.serializeObject(xmlDocument, subVariable, subValue)
        node.appendChild(subNode)
    else:
      # If this item is serializable, serialize it.
      if isinstance(value, Serializable):
        # Serialize the class add it to the list.
        node = value.serialize(xmlDocument)
        node.setAttribute("name", str(variable))
      # If the object is not serializable, use a string representation.
      elif type(value) in Serializable.SUPPORTED_PRIMITIVES:
        node = xmlDocument.createElement(value.__class__.__name__)
        node.setAttribute("name", str(variable))
        valueNode = xmlDocument.createTextNode(str(value))
        node.appendChild(valueNode)
      # We can't serialize anything other than primitives.
      else:
        raise TypeError("Unable to serialize: " + value.__class__.__name__)

    return node

  # ---------------------------------------------------------------------
  def serialize(self, xmlDocument: xml.dom.minidom.Document, nameOverride=None):
    """
    Convert object into XML node.

    Args:
      xmlDocument: Instance of xml.dom.minidom.Document.
      nameOverride: Top-level XML name.

    Returns:
      Node representing the contents of this object.

    Notes:
      This function can be overridden for custom serialization.

    $$$FUTURE - Verify this works with nested lists.
    """

    # Name the top node after the class.
    name = self.__class__.__name__
    if nameOverride is not None:
      name = nameOverride
    node = xmlDocument.createElement(name)

    variables = self.getVariableList()

    # For each member variable in class...
    for variable in variables:
      # Value of this variable.
      value = self.__dict__[variable]
      # Convert variable into XML node and add it to list.
      subNode = self.serializeObject(xmlDocument, variable, value)
      node.appendChild(subNode)

    return node

  # ---------------------------------------------------------------------
  def unserializeNode(self, node):
    """
    Recursively unserialize node and return result.

    Args:
      node: Node to get.

    Returns:
      Correctly typed value for this node.

    $$$FUTURE - Cannot deal with a list of Serialized objects.
    """

    result = None

    # If we have a dictionary or a list, recursively extract the data...
    if "list" == node.nodeName:
      result = []
      for data in node.childNodes:
        returnValue = self.unserializeNode(data)
        if returnValue is not None:
          result.append(returnValue)
    elif "dict" == node.nodeName:
      result = {}
      for data in node.childNodes:
        returnValue = self.unserializeNode(data)
        if returnValue is not None:
          name = data.getAttribute("name")
          result[name] = returnValue
    # If not a list/dictionary...
    else:
      # Figure out the type by the name and make a cast from the string representation.
      if node.firstChild:
        if "NoneType" == node.nodeName:
          result = None
        elif "float" == node.nodeName:
          result = float(node.firstChild.nodeValue)
        elif "int" == node.nodeName:
          result = int(node.firstChild.nodeValue)
        else:
          result = node.firstChild.nodeValue

    return result

  # ---------------------------------------------------------------------
  def unserialize(self, startingNode):
    """
    Extract state of class variables from XML node.

    Args:
      startingNode: Instance of xml.dom.minidom.Node that contains settings.

    Returns:
      All internal variables may change.
      Nothing is returned.
    """

    # For each child node...
    for node in startingNode.childNodes:
      # If this is an element node (we ignore everything else)...
      if xml.dom.minidom.Node.ELEMENT_NODE == node.nodeType:
        # Name of variable.
        name = node.getAttribute("name")
        # Is this a legitimate class variable?
        if name not in self.__dict__:
          if not self._ignoreMissing:
            raise KeyError(str(name) + " not in class.")
        else:
          if isinstance(self.__dict__[name], Serializable):
            self.__dict__[name].unserialize(node)
          else:
            result = self.unserializeNode(node)
            self.__dict__[name] = result

  # -------------------------------------------------------------------
  def toXML(self, nameOverride=None):
    """
    Serialize class to XML.

    Args:
      nameOverride: Top-level XML name.

    Returns:
      XML document of class.
    """
    # Serialize data into XML.
    xmlDocument = xml.dom.minidom.parseString("<SerializableData/>")

    node = self.serialize(xmlDocument, nameOverride)
    xmlDocument.childNodes[0].appendChild(node)

    return xmlDocument

  # -------------------------------------------------------------------
  def toXML_String(self, nameOverride=None):
    """
    Serialize class to XML string.

    Args:
      nameOverride: Top-level XML name.

    Returns:
      XML string of class.
    """

    xmlDocument = self.toXML(nameOverride)

    # Create text from XML data.
    outputText = xmlDocument.toprettyxml()

    # Strip off extraneous line feeds.
    outputText = (
      "\n".join([line for line in outputText.split("\n") if line.strip()]) + "\n"
    )

    return outputText

  # -------------------------------------------------------------------
  def save(self, filePath, fileName, nameOverride=None):
    """
    Write XML data to disk.

    Args:
      filePath: Directory of file.
      fileName: File name to save in.
      nameOverride: Top-level XML name.
    """

    # Convert to XML string.
    outputText = self.toXML_String(nameOverride)

    fullName = filePath + "/" + fileName

    # Write to a temp file in the same directory, then atomically replace the
    # target.  This ensures the state file is never partially written if the
    # process is killed mid-save.
    fd, tmpName = tempfile.mkstemp(dir=filePath)
    try:
      with os.fdopen(fd, "wb") as outputFile:
        outputFile.write(outputText.encode("utf-8"))
      os.replace(tmpName, fullName)
    except:
      try:
        os.unlink(tmpName)
      except OSError:
        pass
      raise

  # -------------------------------------------------------------------
  def load(self, filePath, fileName, nameOverride=None):
    """
    Load an XML file and return instance.

    Args:
      filePath: Directory of file.
      fileName: File name to load.
      nameOverride: Top-level XML name.
    """

    fullName = filePath + "/" + fileName
    xmlDocument = xml.dom.minidom.parse(fullName)
    name = self.__class__.__name__
    if nameOverride is not None:
      name = nameOverride

    node = xmlDocument.getElementsByTagName(name)

    if node and len(node) > 0:
      self.unserialize(node[0])
    else:
      raise KeyError(self.__class__.__name__ + " not in XML data.")


# Unit test.
if __name__ == "__main__":

  class SomeClass2(Serializable):
    # -------------------------------------------------------------------
    def __init__(self):
      self.aa = None
      self.bb = None
      self.cc = None
      self.dd = None

    def bar():
      pass

  class Unserializable:
    pass

  class SomeClass(Serializable):
    # -------------------------------------------------------------------
    def __init__(self):
      self.a = None
      self.b = None
      self.c = None
      self.d = None
      self.someClass2 = SomeClass2()
      self.e = []
      self.f = {}
      self.g = Unserializable()
      self.h = lambda: 5

      Serializable.__init__(self, exclude=["g", "h"])

    def foo():
      pass

  someClass = SomeClass()
  someClass.a = 11.0
  someClass.b = 12
  someClass.c = 13
  someClass.d = "14"
  someClass.e = [100, 200.0, 300, "400", 3.14e9]
  someClass.f = {"apple": 1, "orange": 2}
  someClass.someClass2.aa = 11
  someClass.someClass2.bb = 22
  someClass.someClass2.cc = 33
  someClass.someClass2.dd = 44
  someClass.save(".", "test.xml")

  someClassCopy = SomeClass()
  someClassCopy.load(".", "test.xml")

  assert someClassCopy.a == someClass.a
  assert someClassCopy.b == someClass.b
  assert someClassCopy.c == someClass.c
  assert someClassCopy.d == someClass.d
  assert someClassCopy.e == someClass.e
  assert someClassCopy.f == someClass.f
  assert someClassCopy.someClass2.aa == someClass.someClass2.aa
  assert someClassCopy.someClass2.bb == someClass.someClass2.bb
  assert someClassCopy.someClass2.cc == someClass.someClass2.cc
  assert someClassCopy.someClass2.dd == someClass.someClass2.dd
