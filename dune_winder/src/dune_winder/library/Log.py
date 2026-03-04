###############################################################################
# Name: Log.py
# Uses: Class for creating log files.
# Date: 2016-02-04
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################
import threading
import os.path
import os
import collections


class Log:
  # ---------------------------------------------------------------------
  def _getTimestamp(self):
    """
    Get a timestamp.

    Returns:
      String of current system time.
    """

    return str(self._systemTime.get())

  # ---------------------------------------------------------------------
  def __init__(self, systemTime, outputFileName=None, localEcho=True):
    """
    Constructor.

    Args:
      outputFileName: Name of file to log messages.
      localEcho: True if message is also printed to stdout.
    """

    self._systemTime = systemTime
    self._lock = threading.Lock()
    self._recent = collections.deque(maxlen=30)
    self._outputFiles = []
    self._outputFileList = {}
    if outputFileName:
      self.attach(outputFileName)

    self._localEcho = localEcho
    if self._localEcho:
      print("Time                       Message")

  # ---------------------------------------------------------------------
  def attach(self, outputFileName):
    """
    Add an other file to log messages.

    Args:
      outputFileName: File to append.
    """
    self._lock.acquire()

    # Create the path if it does not exist.
    path = os.path.dirname(outputFileName)
    if not os.path.exists(path):
      os.makedirs(path)

    needsHeader = not os.path.isfile(outputFileName)
    outputFile = open(outputFileName, "a")

    if needsHeader:
      outputFile.write("Time\tModule\tType\tMessage\n")

    self._outputFileList[outputFileName] = outputFile
    self._outputFiles.append(outputFile)
    self._lock.release()

  # ---------------------------------------------------------------------
  def detach(self, outputFileName):
    """
    Remove log file from getting log messages.

    Args:
      outputFileName: Log file previously attached.
    """
    self._lock.acquire()
    if outputFileName in self._outputFileList:
      outputFile = self._outputFileList[outputFileName]
      self._outputFileList.pop(outputFileName)
      outputFile.close()
    self._lock.release()

  # ---------------------------------------------------------------------
  def getRecent(self):
    """
    Return the most recent lines of the log file.

    Returns:
      The most recent lines of the log file.
    """
    self._lock.acquire()
    result = list(self._recent)
    self._lock.release()
    return result

  # ---------------------------------------------------------------------
  def _tail(self, inputFile, lines):
    """
    Return the last n lines from an open file.

    Args:
      inputFile - File to read from.  Must be open and readable.
      lines - Number of lines to read.
    Returns:
      Array of lines.
    Notes:
      Reads from the end in binary mode so it works on Windows, where
      text-mode files do not support nonzero end-relative seeks.
    """
    assert lines >= 0

    if 0 == lines:
      return []

    inputFile.seek(0, os.SEEK_END)
    position = inputFile.tell()
    blockSize = 4096
    blocks = []
    lineCount = 0

    while position > 0 and lineCount <= lines:
      readSize = min(blockSize, position)
      position -= readSize
      inputFile.seek(position, os.SEEK_SET)
      block = inputFile.read(readSize)
      blocks.append(block)
      lineCount += block.count(b"\n")

    text = b"".join(reversed(blocks)).decode("utf-8", errors="replace")
    result = text.splitlines()

    # If we did not reach the start of the file, the first entry is partial.
    if position > 0 and len(result) > 0:
      result = result[1:]

    # Skip the log header when it is present.
    if len(result) > 0 and "Time\tModule\tType\tMessage" == result[0]:
      result = result[1:]

    return result[-lines:]

  # ---------------------------------------------------------------------
  def getAll(self, numberOfLines=-1):
    """
    Get the entire log file.

    Return:
      An array of each line of the log file.
    """

    fileName = list(self._outputFileList.keys())[0]

    if -1 == numberOfLines:
      with open(fileName) as inputFile:
        # Red and ignore header.
        inputFile.readline()

        # Read remaining lines.
        lines = inputFile.readlines()

      # Remove line feeds.
      for index, line in enumerate(lines):
        lines[index] = line.replace("\n", "")
    else:
      with open(fileName, "rb") as inputFile:
        lines = self._tail(inputFile, numberOfLines)

    return lines

  # ---------------------------------------------------------------------
  def add(self, module, typeName, message, parameters=None):
    """
    Add a message to log file.

    Args:
      module: Which module. Use "self.__class__.__name__".
      typeName: Message type.
      message: Human readable message.
      parameters: A list of all data associated with entry.
    """

    currentTime = self._getTimestamp()
    line = str(currentTime) + "\t" + str(module) + "\t" + str(typeName) + "\t" + message

    if parameters is None:
      parameters = []

    for parameter in parameters:
      line += "\t" + str(parameter)

    # Write the message to each open log file.
    self._lock.acquire()
    self._recent.append(line)
    for _, outputFile in self._outputFileList.items():
      outputFile.write(line + "\n")
      outputFile.flush()
    self._lock.release()

    # Local echo if requested.
    if self._localEcho:
      line = str(currentTime) + " " + message
      isFirst = True
      parameterLine = ""
      for parameter in parameters:
        if not isFirst:
          parameterLine += ", "
        isFirst = False
        parameterLine += str(parameter)

      if "" != parameterLine:
        parameterLine = " [" + parameterLine + "]"

      line += parameterLine

      print(line)
