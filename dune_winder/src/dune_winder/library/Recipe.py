###############################################################################
# Name: Recipe.py
# Uses: G-Code recipe file loader.
# Date: 2016-03-04
# Author(s):
#   Andrew Que <aque@bb7.com>
# Notes:
#     A recipe is for the most part a G-Code file, but with a standard header.
#   This header is a single line--a G-Code comment--that contains a description
#   and one or two hashes.  The first hash is an ID to identify this file.  The
#   second is an optional parent hash that can be used to identify the parent
#   object the file was derived.
#     Hash calculation is done automatically as long as the header line exists.
#   If the hash doesn't match, the existing hash (if there is one) is assumed
#   to be the parent from which the file was derived.  If there is no hash at
#   all, there is no parent.  The file is rewritten with the new heading.
#     Any time a file is loaded, correct hash or not, the archive is checked
#   for a file with by the name of the hash.  If it does not exist, a copy of
#   this file is made in the archive.  This way any recipe that is used is
#   archived.
#     The hash is used as an ID and can be read externally.  The G-Code from
#   the file is also loaded and can be pass to something that can work with
#   the G-Code.
###############################################################################
import os
import re
import os.path
import shutil

from .Hash import Hash


class Recipe:
  DEFAULT_MAX_PERIOD = 1000
  DEFAULT_MIN_CYCLES = 3

  # ---------------------------------------------------------------------
  @staticmethod
  def _normalizeGeneratedLines(lines):
    normalizedLines = []
    for line in lines:
      line = str(line)
      if not line.endswith("\n"):
        line += "\n"
      normalizedLines.append(line)
    return normalizedLines

  # ---------------------------------------------------------------------
  @staticmethod
  def _buildGeneratedHeader(description, bodyHash, parentHash=None):
    header = "( " + str(description) + " " + str(bodyHash)
    if parentHash:
      header += " " + str(parentHash).strip()
    return header + " )\n"

  # ---------------------------------------------------------------------
  @staticmethod
  def writeGeneratedFile(fileName, description, bodyLines, archiveDirectory=None, parentHash=None):
    normalizedLines = Recipe._normalizeGeneratedLines(bodyLines)

    bodyHash = Hash()
    bodyHash += str(description).encode("utf-8")
    for line in normalizedLines:
      bodyHash += line.encode("utf-8")
    bodyHash = str(bodyHash)

    with open(fileName, "w", encoding="utf-8") as outputFile:
      outputFile.write(Recipe._buildGeneratedHeader(description, bodyHash, parentHash=parentHash))
      outputFile.writelines(normalizedLines)

    if archiveDirectory:
      os.makedirs(archiveDirectory, exist_ok=True)
      archiveFile = archiveDirectory + "/" + bodyHash
      if not os.path.isfile(archiveFile):
        shutil.copy2(fileName, archiveFile)

    return bodyHash

  # ---------------------------------------------------------------------
  def __init__(self, fileName, archiveDirectory):
    """
    Constructor.

    Args:
      fileName: File name of recipe to load.
      archiveDirectory: Path to archive directory.
    """
    # Read input file.
    with open(fileName) as inputFile:
      # Read file header.
      header = inputFile.readline()

      # Get the rest of the lines.
      self._lines = inputFile.readlines()

    # Regular expression for header.  Headings must be in the following format:
    #   ( Description hash parentHash )
    # Where the description is a text field ending with a comma, and the hash
    # fields.
    headerCheck = (
      r"\( (.+?)[ ]+(?:"
      + Hash.HASH_PATTERN
      + "[ ]+)?(?:"
      + Hash.HASH_PATTERN
      + r"[ ]+)?\)"
    )

    expression = re.search(headerCheck, header, re.IGNORECASE)

    if not expression:
      self._description = os.path.splitext(os.path.basename(fileName))[0]
      self._headerHash = None
      self._parentHash = None

      if header:
        self._lines.insert(0, header)
    else:
      self._description = expression.group(1)
      self._headerHash = expression.group(2)
      self._parentHash = expression.group(3)

    # Create hash of G-Code, including description.
    bodyHash = Hash()
    bodyHash += self._description.encode("utf-8")
    for line in self._lines:
      bodyHash += line.encode("utf-8")

    # Turn hash into base 32 encoding.
    bodyHash = str(bodyHash)

    # Does the caclulated hash not match the hash from the header?
    if bodyHash != self._headerHash:
      # If there was a hash, it is the parent hash.
      if self._headerHash is None:
        self._headerHash = ""
      else:
        self._headerHash += " "

      # Rewrite the recipe file with the correct header.
      with open(fileName, "w") as outputFile:
        outputFile.write(
          "( " + self._description + " " + bodyHash + " " + self._headerHash + ")\n"
        )
        outputFile.writelines(self._lines)

      # Setup correct current and parent hash.
      self._parentHash = self._headerHash
      self._headerHash = bodyHash

    if archiveDirectory:
      # If this file does not exist in the archive, copy it there.
      archiveFile = archiveDirectory + "/" + bodyHash
      if not os.path.isfile(archiveFile):
        # Make an archive copy of the file.
        shutil.copy2(fileName, archiveFile)

    self._cachedDetectedPeriod = None
    self._hasCachedDetectedPeriod = False

  # ---------------------------------------------------------------------
  @staticmethod
  def _normalizeLineForPeriodDetection(line):
    """
    Normalize a G-Code line to its structural pattern by removing numbers.

    Args:
      line: Raw G-Code line.

    Returns:
      Normalized line string.
    """
    line = line.strip()
    line = re.sub(r"[-+]?\d+(?:\.\d+)?", "", line)
    line = re.sub(r"\s+", " ", line)
    return line.strip()

  # ---------------------------------------------------------------------
  @staticmethod
  def _parseWrapStartNumber(line):
    """
    Extract a wrap number from recipe comments when present.

    Supported comment styles include modern `(12, 1)` style wrap markers and
    legacy `(Wrap 12)` comments.
    """
    expression = re.search(r"\(\s*(\d+)\s*,\s*\d+", line)
    if expression:
      wrapNumber = int(expression.group(1))
      if wrapNumber >= 1:
        return wrapNumber

    expression = re.search(r"\(\s*Wrap\s+(\d+)\s*\)", line, re.IGNORECASE)
    if expression:
      wrapNumber = int(expression.group(1))
      if wrapNumber >= 1:
        return wrapNumber

    return None

  # ---------------------------------------------------------------------
  def _getWrapStartSpacingPeriod(self, minCycles):
    """
    Detect wrap period from the spacing between successive wrap starts.

    When a recipe annotates each wrap explicitly, this is a more stable notion
    of "period" for seeking and forecasting than the generic structural repeat
    detector because it captures the full wrap block length.
    """
    wrapStarts = {}
    for index, line in enumerate(self._lines, start=1):
      wrapNumber = Recipe._parseWrapStartNumber(line)
      if wrapNumber is None or wrapNumber in wrapStarts:
        continue
      wrapStarts[wrapNumber] = index

    if len(wrapStarts) < minCycles:
      return None

    periodCounts = {}
    orderedWraps = sorted(wrapStarts.items())
    for itemIndex in range(len(orderedWraps) - 1):
      wrapNumber, wrapStart = orderedWraps[itemIndex]
      nextWrapNumber, nextWrapStart = orderedWraps[itemIndex + 1]
      if nextWrapNumber != wrapNumber + 1:
        continue

      period = nextWrapStart - wrapStart
      if period <= 0:
        continue

      periodCounts[period] = periodCounts.get(period, 0) + 1

    if len(periodCounts) == 0:
      return None

    bestPeriod = None
    bestCount = 0
    for period, count in periodCounts.items():
      if count > bestCount or (count == bestCount and period < bestPeriod):
        bestPeriod = period
        bestCount = count

    if bestCount < minCycles - 1:
      return None

    return bestPeriod

  # ---------------------------------------------------------------------
  def getDetectedPeriod(self, maxPeriod=None, minCycles=None):
    """
    Detect the repeating line period of this recipe.

    The detector first prefers the spacing between explicit wrap-start comments,
    because that captures the full wrap block when recipes provide wrap labels.
    When such metadata is not available, it falls back to comparing G-Code lines
    after removing numeric values so repeated loop bodies with changing
    coordinates or counters still match.

    Args:
      maxPeriod: Optional maximum candidate period to consider.
      minCycles: Minimum number of repeated cycles required.

    Returns:
      Integer period in lines, or None if no sufficiently strong repetition is
      found.
    """
    if maxPeriod is None:
      maxPeriod = Recipe.DEFAULT_MAX_PERIOD
    if minCycles is None:
      minCycles = Recipe.DEFAULT_MIN_CYCLES

    useCachedResult = (
      maxPeriod == Recipe.DEFAULT_MAX_PERIOD
      and minCycles == Recipe.DEFAULT_MIN_CYCLES
    )
    if useCachedResult and self._hasCachedDetectedPeriod:
      return self._cachedDetectedPeriod

    detectedPeriod = self._getWrapStartSpacingPeriod(minCycles)
    if detectedPeriod is not None and detectedPeriod > maxPeriod:
      detectedPeriod = None

    if detectedPeriod is None:
      normalizedLines = [
        Recipe._normalizeLineForPeriodDetection(line) for line in self._lines
      ]

      lineCount = len(normalizedLines)
      maxCandidatePeriod = min(maxPeriod, lineCount // max(1, minCycles))
      if maxCandidatePeriod < 1:
        if useCachedResult:
          self._cachedDetectedPeriod = None
          self._hasCachedDetectedPeriod = True
        return None

      bestPeriod = None
      bestScore = None
      for period in range(1, maxCandidatePeriod + 1):
        longestRun = 0
        currentRun = 0
        for index in range(lineCount - period):
          if normalizedLines[index] == normalizedLines[index + period]:
            currentRun += 1
            if currentRun > longestRun:
              longestRun = currentRun
          else:
            currentRun = 0

        cycleCount = 0
        if longestRun >= period:
          cycleCount = longestRun // period + 1

        if cycleCount < minCycles:
          continue

        # Prefer the candidate that explains the longest contiguous repeated
        # block. This avoids collapsing to trivial periods like 1 when a file
        # contains many adjacent lines with the same numeric-free shape.
        score = (longestRun, cycleCount, -period)
        if bestScore is None or score > bestScore:
          bestScore = score
          bestPeriod = period

      detectedPeriod = bestPeriod

    if useCachedResult:
      self._cachedDetectedPeriod = detectedPeriod
      self._hasCachedDetectedPeriod = True

    return detectedPeriod

  # ---------------------------------------------------------------------
  def getLines(self):
    """
    Return all recipe G-Code lines.

    Returns:
      All recipe G-Code lines.
    """
    return self._lines

  # ---------------------------------------------------------------------
  def getDescription(self):
    """
    Return the description of this recipe.  Comes from header of G-Code.

    Returns:
      Description of G-Code file.
    """
    return self._description

  # ---------------------------------------------------------------------
  def getID(self):
    """
    Return the unique ID of this recipe.

    Returns:
      ID of G-Code file.

    Notes:
      The ID is a hash that correlates the file to a file in the archive.
    """
    return self._headerHash

  # ---------------------------------------------------------------------
  def getParentID(self):
    """
    Return the unique parent ID of this recipe.

    Returns:
      ID of parent G-Code file.

    Notes:
      Modified G-Code can have a parent which can be traced from this ID.
    """
    return self._parentHash
