###############################################################################
# Name: XGTemplateGCode.py
# Uses: Generate X/G layer G-Code from the programmatic specification.
# Date: 2026-03-03
###############################################################################

from dune_winder.library.Recipe import Recipe
from dune_winder.library.TemplateGCodeTransitions import (
  append_motion_to_pause_transition,
  append_pause_to_motion_transition,
  g106_line,
)


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


def _coord(axis, value):
  return axis + _format_number(value)


def _resolve_special_inputs(special_inputs=None, legacy_special_inputs=None):
  if special_inputs is not None and legacy_special_inputs is not None:
    if special_inputs is not legacy_special_inputs:
      raise ValueError("Specify either special_inputs or specialInputs, not both.")

  if special_inputs is not None:
    return special_inputs
  if legacy_special_inputs is not None:
    return legacy_special_inputs
  return {}


def _resolve_alias_value(snake_case_value, legacy_value, snake_case_name, legacy_name):
  if snake_case_value is not None and legacy_value is not None:
    if snake_case_value != legacy_value:
      raise ValueError(
        "Specify either "
        + snake_case_name
        + " or "
        + legacy_name
        + ", not both."
      )
  if snake_case_value is not None:
    return snake_case_value
  return legacy_value


def _require_wire_y(special_inputs, referenceId):
  try:
    value = special_inputs["references"][referenceId]["wireY"]
  except (KeyError, TypeError):
    raise ValueError("Missing wireY for reference " + referenceId + ".")
  return float(value)


def _require_offset(special_inputs, offsetId):
  try:
    value = special_inputs["offsets"][offsetId]
  except (KeyError, TypeError):
    raise ValueError("Missing offset " + offsetId + ".")
  return float(value)


def _line(*codes):
  return " ".join(str(code) for code in codes if code not in (None, ""))


def _g106(position):
  return g106_line(_line, position)


def _wrap_identifier(wrap_number, line_number, head_restart=False):
  comment = "(" + str(wrap_number) + "," + str(line_number)
  if head_restart:
    comment += " HEAD RESTART"
  comment += ")"
  return comment


def _wrap_step(*codes, head_restart=False):
  return (_line(*codes), head_restart)


def _annotate_wrap_lines(wrap_number, wrap_steps):
  return [
    _line(_wrap_identifier(wrap_number, line_number, head_restart), line)
    for line_number, (line, head_restart) in enumerate(wrap_steps, start=1)
  ]


def _number_lines(lines):
  return [
    _line("N" + str(line_number), line) + "\n"
    for line_number, line in enumerate(lines)
  ]


def _render_wrap_lines(
  wrap_number,
  *,
  wire_head_y,
  wire_foot_y,
  head_a_offset,
  head_b_offset,
  foot_a_offset,
  foot_b_offset,
  transfer_pause,
):
  spacing_offset = (wrap_number - 1) * WIRE_SPACING
  head_a_value = wire_head_y + head_a_offset + spacing_offset
  if wrap_number > 1:
    head_a_value += DIAGONAL_CORRECT

  wrap_steps = [
    _wrap_step(
      _coord("X", HEAD_PULL_FLAT),
      _coord("Y", head_a_value)
    ),
    _wrap_step(
      _coord("X", FOOT_TRANSFER_ZONE),
      _coord("Y", wire_foot_y + foot_a_offset + spacing_offset),
    ),
  ]

  transition_lines = []
  append_motion_to_pause_transition(
    transition_lines,
    line_builder=_line,
    transfer_pause=transfer_pause,
    include_lead_mode=True,
  )
  wrap_steps.extend(_wrap_step(transition_line) for transition_line in transition_lines)

  wrap_steps.extend(
    [
      _wrap_step(
        _coord("X", FOOT_PULL_FLAT),
        _coord("Y", wire_foot_y + foot_b_offset + spacing_offset),
      ),
      _wrap_step(
        _coord("X", HEAD_TRANSFER_ZONE),
        _coord("Y", wire_head_y + head_b_offset + spacing_offset),
        head_restart=True,
      ),
    ]
  )

  transition_lines = []
  append_pause_to_motion_transition(
    transition_lines,
    line_builder=_line,
    transfer_pause=transfer_pause,
    include_lead_mode=True,
  )
  wrap_steps.extend(_wrap_step(transition_line) for transition_line in transition_lines)
  return _annotate_wrap_lines(wrap_number, wrap_steps)


def get_xg_recipe_description(layer):
  layer = _normalize_layer(layer)
  return layer + "-layer"


def get_xg_recipe_file_name(layer):
  layer = _normalize_layer(layer)
  return layer + "-layer.gc"


def render_xg_template_lines(layer, specialInputs=None, *, special_inputs=None):
  layer = _normalize_layer(layer)
  special_inputs = _resolve_special_inputs(
    special_inputs=special_inputs,
    legacy_special_inputs=specialInputs,
  )

  wire_head_y = _require_wire_y(special_inputs, "head")
  wire_foot_y = _require_wire_y(special_inputs, "foot")
  head_a_offset = _require_offset(special_inputs, "headA")
  head_b_offset = _require_offset(special_inputs, "headB")
  foot_a_offset = _require_offset(special_inputs, "footA")
  foot_b_offset = _require_offset(special_inputs, "footB")
  transfer_pause = bool(special_inputs.get("transferPause", True))

  lines = [
    _line(
      _coord("X", HEAD_TRANSFER_ZONE),
      _coord("Y", wire_head_y + head_a_offset),
    ),
    _g106(0),
  ]

  for wrap_number in range(1, WRAP_COUNTS[layer] + 1):
    lines.extend(
      _render_wrap_lines(
        wrap_number,
        wire_head_y=wire_head_y,
        wire_foot_y=wire_foot_y,
        head_a_offset=head_a_offset,
        head_b_offset=head_b_offset,
        foot_a_offset=foot_a_offset,
        foot_b_offset=foot_b_offset,
        transfer_pause=transfer_pause,
      )
    )

  lines.append(
    _line(
      _coord("X", HEAD_PULL_FLAT),
      _coord("Y", wire_head_y + head_a_offset + 480.0 * WIRE_SPACING),
    )
  )
  return _number_lines(lines)


def write_xg_template_file(
  layer,
  outputPath=None,
  specialInputs=None,
  archiveDirectory=None,
  parentHash=None,
  *,
  output_path=None,
  special_inputs=None,
  archive_directory=None,
  parent_hash=None,
):
  layer = _normalize_layer(layer)
  output_path = _resolve_alias_value(
    output_path,
    outputPath,
    "output_path",
    "outputPath",
  )
  archive_directory = _resolve_alias_value(
    archive_directory,
    archiveDirectory,
    "archive_directory",
    "archiveDirectory",
  )
  parent_hash = _resolve_alias_value(
    parent_hash,
    parentHash,
    "parent_hash",
    "parentHash",
  )
  if output_path is None:
    raise ValueError("output_path is required.")

  resolved_special_inputs = _resolve_special_inputs(
    special_inputs=special_inputs,
    legacy_special_inputs=specialInputs,
  )
  lines = render_xg_template_lines(layer, special_inputs=resolved_special_inputs)
  hashValue = Recipe.writeGeneratedFile(
    output_path,
    get_xg_recipe_description(layer),
    lines,
    archiveDirectory=archive_directory,
    parentHash=parent_hash,
  )
  return {
    "description": get_xg_recipe_description(layer),
    "fileName": get_xg_recipe_file_name(layer),
    "hashValue": hashValue,
    "lines": lines,
    "wrapCount": WRAP_COUNTS[layer],
    "wireSpacing": WIRE_SPACING,
  }
