###############################################################################
# Name: ArrayToCSV.py
# Uses: Convert an array to a Comma Separated Values (CSV) file.
# Date: 2017-01-18
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from dune_winder.library.hash import Hash


class ArrayToCSV:
  # ---------------------------------------------------------------------
  @staticmethod
  def saveDictionarySet(data, filePath, fileName, separator=",", isHashed=False):
    """
    Save an array of similarly keyed dictionaries to CSV file.

    Args:
      data: Array of similarly keyed dictionaries.
      filePath: Directory of file.  Omit to use the path specified loading.
      fileName: File name to save in.  Omit to use the name specified loading.
      separator: Field separator (default is a comma).
    Returns:
      Hash string (if requested)
    """

    fullName = filePath + "/" + fileName
    hashValue = ""

    with open(fullName, "w") as outputFile:
      keys = list(data[0].keys())
      for key in keys:
        outputFile.write(str(key) + separator)

      outputFile.write("\n")

      for row in data:
        for key in row:
          item = row[key]
          outputFile.write(str(item) + separator)

        outputFile.write("\n")

      if isHashed:
        hashValue = Hash.singleLine(str(data))
        outputFile.write(hashValue + "\n")

    return hashValue


# Unit test.
if __name__ == "__main__":
  data = [
    {"FirstName": "Jane", "LastName": "Joe", "Address": "123 Main St"},
    {"FirstName": "John", "LastName": "Smith", "Address": "456 Park St"},
    {"FirstName": "Richard", "LastName": "Roe", "Address": "789 High St"},
  ]

  ArrayToCSV.saveDictionarySet(data, ".", "data.csv")
  ArrayToCSV.saveDictionarySet(data, ".", "data2.csv", isHashed=True)
