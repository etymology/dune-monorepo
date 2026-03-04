###############################################################################
# Name: Hash.py
# Uses: Interface to make a hash out of data.
# Date: 2016-10-03
# Author(s):
#   Andrew Que <aque@bb7.com>
# Notes:
#     Unit created because several other libraries were duplicating this
#   functionality.
# Example:
#   hash = Hash()
#   hash += "String to hash"
#   hash += "An other string to hash"
#   print str( hash )
###############################################################################

import hashlib
import re


class Hash:
  # Selected hashing algorithm.
  ALGORITHM = hashlib.md5
  HASH_PATTERN = "([0-9A-F]{3}-[0-9A-F]{3}-[0-9A-F]{4})"
  IN_PATTERN = r"(.{3})(.{3})(.{4}).*"
  OUT_PATTERN = "\\1-\\2-\\3"

  # -------------------------------------------------------------------
  @staticmethod
  def singleLine(line):
    """
    Return hash of a single line of data.

    Args:
      line: Line to be hashed.

    Returns:
      Hash string of line.
    """
    hash = Hash()
    hash += line.encode("utf-8")
    return str(hash)

  # -------------------------------------------------------------------
  def __init__(self):
    """
    Constructor.
    """

    # Instance of hashing algorithm.
    self._hashValue = Hash.ALGORITHM()

  # -------------------------------------------------------------------
  def __add__(self, data):
    """
    Add data to hash.

    Args:
      data: String or binary data to add.

    Returns:
      Instance of self.

    Notes:
      Modifies internals by hash.
    """
    self._hashValue.update(data)
    return self

  # -------------------------------------------------------------------
  def __str__(self):
    """
    Convert hash to a string.

    Returns:
      String of hash.
    """
    hex = self._hashValue.hexdigest()
    hexString = re.sub(Hash.IN_PATTERN, Hash.OUT_PATTERN, hex).upper()
    return hexString
