###############################################################################
# Name: XGTemplateGCode.py
# Uses: Generate X/G layer G-Code from the programmatic specification.
# Date: 2026-03-03
###############################################################################

from dune_winder.library.Recipe import Recipe


WIRE_SPACING = 230.0 / 48.0
HEAD_TRANSFER_ZONE = 440.0
FOOT_TRANSFER_ZONE = 7165.0
HEAD_PULL_FLAT = 635.0
FOOT_PULL_FLAT = 7016.0
DIAGONAL_CORRECT = 3.0

WRAP_COUNTS = {
  "X": 480,
  "G": 481,
}

REFERENCE_IDS = ("head", "foot")
OFFSET_IDS = ("headA", "headB", "footA", "footB")


def _normalize_layer(layer):
  layer = str(layer).strip().upper()
  if layer not in WRAP_COUNTS:
    raise ValueError("Unsupported X/G layer: " + str(layer))
  return layer


def _format_number(value):
  rounded = round(float(value) * 10.0) / 10.0
  if abs(rounded) < 1e-9:
    rounded = 0.0
  text = "{0:.1f}".format(rounded)
  return text


def _require_wire_y(specialInputs, referenceId):
  try:
    value = specialInputs["references"][referenceId]["wireY"]
  except (KeyError, TypeError):
    raise ValueError("Missing wireY for reference " + referenceId + ".")
  return float(value)


def _require_offset(specialInputs, offsetId):
  try:
    value = specialInputs["offsets"][offsetId]
  except (KeyError, TypeError):
    raise ValueError("Missing offset " + offsetId + ".")
  return float(value)


def _line(*codes):
  return " ".join(str(code) for code in codes if code is not None) + "\n"


def _wrap_line(wrapNumber, wrapLineNumber, *codes, headRestart=False):
  comment = "(" + str(wrapNumber) + "," + str(wrapLineNumber)
  if headRestart:
    comment += " HEAD RESTART"
  comment += ")"
  return _line(comment, *codes)


def _number_lines(lines):
  numberedLines = []
  for lineNumber, line in enumerate(lines):
    numberedLines.append("N" + str(lineNumber) + " " + line.rstrip("\n") + "\n")
  return numberedLines


def get_xg_recipe_description(layer):
  layer = _normalize_layer(layer)
  return layer + "-layer"


def get_xg_recipe_file_name(layer):
  layer = _normalize_layer(layer)
  return layer + "-layer.gc"


def render_xg_template_lines(layer, specialInputs=None):
  layer = _normalize_layer(layer)
  if specialInputs is None:
    specialInputs = {}

  wireHeadY = _require_wire_y(specialInputs, "head")
  wireFootY = _require_wire_y(specialInputs, "foot")
  headAOffset = _require_offset(specialInputs, "headA")
  headBOffset = _require_offset(specialInputs, "headB")
  footAOffset = _require_offset(specialInputs, "footA")
  footBOffset = _require_offset(specialInputs, "footB")
  transferPause = bool(specialInputs.get("transferPause", False))

  lines = [
    _line("X" + _format_number(HEAD_TRANSFER_ZONE), "Y" + _format_number(wireHeadY + headAOffset),),_line("G106", "P0")
  ]

  for wrapNumber in range(1, WRAP_COUNTS[layer] + 1):
    spacingOffset = (wrapNumber - 1) * WIRE_SPACING
    headAValue = wireHeadY + headAOffset + spacingOffset
    if wrapNumber > 1:
      headAValue += DIAGONAL_CORRECT

    wrapLineNumber = 1

    lines.append(
      _wrap_line(
        wrapNumber,
        wrapLineNumber,
        "X" + _format_number(HEAD_PULL_FLAT),
        "Y" + _format_number(headAValue),
      )
    )
    
    wrapLineNumber += 1

    lines.append(
      _wrap_line(
        wrapNumber,
        wrapLineNumber,
        "X" + _format_number(FOOT_TRANSFER_ZONE),
        "Y" + _format_number(wireFootY + footAOffset + spacingOffset),
      )
    )
    wrapLineNumber += 1
    lines.append(_wrap_line(wrapNumber, wrapLineNumber, "G106", "P0"))
    if transferPause:
      wrapLineNumber += 1
      lines.append(_wrap_line(wrapNumber, wrapLineNumber, "G106", "P1"))
    wrapLineNumber += 1
    lines.append(_wrap_line(wrapNumber, wrapLineNumber, "G106", "P3"))
    wrapLineNumber += 1
    lines.append(
      _wrap_line(
        wrapNumber,
        wrapLineNumber,
        "X" + _format_number(FOOT_PULL_FLAT),
        "Y" + _format_number(wireFootY + footBOffset + spacingOffset),
      )
    )
    wrapLineNumber += 1
    lines.append(
      _wrap_line(
        wrapNumber,
        wrapLineNumber,
        "X" + _format_number(HEAD_TRANSFER_ZONE),
        "Y" + _format_number(wireHeadY + headBOffset + spacingOffset),
        headRestart=True,
      )
    )
    if transferPause:
      wrapLineNumber += 1
      lines.append(_wrap_line(wrapNumber, wrapLineNumber, "G106", "P2"))
    wrapLineNumber += 1
    lines.append(_wrap_line(wrapNumber, wrapLineNumber, "G106", "P0"))

  lines.append(
    _line(
      "X" + _format_number(HEAD_PULL_FLAT),
      "Y" + _format_number(wireHeadY + headAOffset + 480.0 * WIRE_SPACING),
    )
  )
  return _number_lines(lines)


def write_xg_template_file(
  layer,
  outputPath,
  specialInputs=None,
  archiveDirectory=None,
  parentHash=None,
):
  layer = _normalize_layer(layer)
  lines = render_xg_template_lines(layer, specialInputs=specialInputs)
  hashValue = Recipe.writeGeneratedFile(
    outputPath,
    get_xg_recipe_description(layer),
    lines,
    archiveDirectory=archiveDirectory,
    parentHash=parentHash,
  )
  return {
    "description": get_xg_recipe_description(layer),
    "fileName": get_xg_recipe_file_name(layer),
    "hashValue": hashValue,
    "lines": lines,
    "wrapCount": WRAP_COUNTS[layer],
    "wireSpacing": WIRE_SPACING,
  }
