###############################################################################
# Name: XGTemplateGCode.py
# Uses: Generate X/G layer G-Code from the programmatic specification.
# Date: 2026-03-03
###############################################################################

import re

from dune_winder.recipes.recipe import Recipe
from dune_winder.recipes import template_gcode_common
from dune_winder.recipes.recipe_template_language import (
  compile_template_script,
  execute_template_script,
)
from dune_winder.gcode.renderer import normalize_line_text
from dune_winder.recipes.template_gcode_transfers import (
  append_a_to_b_transfer,
  append_b_to_a_transfer,
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

XG_PREAMBLE_SCRIPT = compile_template_script(
  (
    "emit G113 PPRECISE X${r(HEAD_TRANSFER_ZONE)} Y${r(wire_head_y + head_a_offset)}",
    "emit ${g106(0)}",
  )
)

XG_WRAP_SCRIPT = compile_template_script(
  (
    "emit G113 PPRECISE X${r(HEAD_PULL_FLAT)} Y${r(head_a_value)}",
    "emit G113 PPRECISE X${r(FOOT_TRANSFER_ZONE)} Y${r(wire_foot_y + foot_a_offset + spacing_offset)}",
    "transfer a_to_b_transfer",
    "emit G113 PPRECISE X${r(FOOT_PULL_FLAT)} Y${r(wire_foot_y + foot_b_offset + spacing_offset)}",
    "emit_head_restart G113 PPRECISE X${r(HEAD_TRANSFER_ZONE)} Y${r(wire_head_y + head_b_offset + spacing_offset)}",
    "transfer b_to_a_transfer",
  )
)

XG_POSTAMBLE_SCRIPT = compile_template_script(
  (
    "emit G113 PPRECISE X${r(HEAD_PULL_FLAT)} Y${r(wire_head_y + head_a_offset + 480.0 * WIRE_SPACING)}",
  )
)


_G113_PARAMS_RE = re.compile(r"G113\s+P\w+\s*")


def _apply_strip_g113_params(lines):
  return [
    re.sub(r"\s{2,}", " ", _G113_PARAMS_RE.sub("", line)).strip() for line in lines
  ]


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


def _round_for_motion(value):
  return _format_number(value)


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
    if value is None:
      return 0.0
  except (KeyError, TypeError):
    return 0.0
  return float(value)


def _line(*codes):
  text = " ".join(str(code) for code in codes if code not in (None, ""))
  return normalize_line_text(text)


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
  annotated = []
  for line_number, (line, head_restart) in enumerate(wrap_steps, start=1):
    identifier = _wrap_identifier(wrap_number, line_number, head_restart)
    queue_merge_prefix, remainder = template_gcode_common.split_queue_merge_prefix(line)
    if queue_merge_prefix is None:
      annotated.append(_line(identifier, line))
      continue
    annotated.append(_line(queue_merge_prefix, identifier, remainder))
  return annotated


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
  include_lead_mode,
):
  spacing_offset = (wrap_number - 1) * WIRE_SPACING
  head_a_value = wire_head_y + head_a_offset + spacing_offset
  if wrap_number > 1:
    head_a_value += DIAGONAL_CORRECT

  def append_transfer_steps(output, transfer_function):
    transfer_lines = []
    transfer_function(
      transfer_lines,
      line_builder=_line,
      transfer_pause=transfer_pause,
      include_lead_mode=include_lead_mode,
    )
    output.extend(_wrap_step(transfer_line) for transfer_line in transfer_lines)

  transfers = {
    "a_to_b_transfer": lambda output: append_transfer_steps(
      output,
      append_a_to_b_transfer,
    ),
    "b_to_a_transfer": lambda output: append_transfer_steps(
      output,
      append_b_to_a_transfer,
    ),
  }

  wrap_steps = []
  environment = {
    "r": _round_for_motion,
    "HEAD_PULL_FLAT": HEAD_PULL_FLAT,
    "FOOT_TRANSFER_ZONE": FOOT_TRANSFER_ZONE,
    "FOOT_PULL_FLAT": FOOT_PULL_FLAT,
    "HEAD_TRANSFER_ZONE": HEAD_TRANSFER_ZONE,
    "wire_head_y": wire_head_y,
    "wire_foot_y": wire_foot_y,
    "head_a_offset": head_a_offset,
    "head_b_offset": head_b_offset,
    "foot_a_offset": foot_a_offset,
    "foot_b_offset": foot_b_offset,
    "spacing_offset": spacing_offset,
    "head_a_value": head_a_value,
  }

  def emit_wrap_step(output, line, action):
    output.append(_wrap_step(line, head_restart=(action == "emit_head_restart")))

  execute_template_script(
    XG_WRAP_SCRIPT,
    environment=environment,
    output_lines=wrap_steps,
    line_builder=_line,
    transfers=transfers,
    emit_callback=emit_wrap_step,
  )

  return _annotate_wrap_lines(wrap_number, wrap_steps)


def get_xg_recipe_description(layer):
  layer = _normalize_layer(layer)
  return layer + "-layer"


def get_xg_recipe_file_name(layer):
  layer = _normalize_layer(layer)
  return layer + "-layer.gc"


def render_xg_template_lines(layer, specialInputs=None, *, special_inputs=None, strip_g113_params=False):
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
  include_lead_mode = bool(
    special_inputs.get(
      "includeLeadMode",
      special_inputs.get("include_lead_mode", True),
    )
  )

  lines = []
  base_environment = {
    "r": _round_for_motion,
    "g106": _g106,
    "HEAD_TRANSFER_ZONE": HEAD_TRANSFER_ZONE,
    "HEAD_PULL_FLAT": HEAD_PULL_FLAT,
    "WIRE_SPACING": WIRE_SPACING,
    "wire_head_y": wire_head_y,
    "head_a_offset": head_a_offset,
  }

  execute_template_script(
    XG_PREAMBLE_SCRIPT,
    environment=base_environment,
    output_lines=lines,
    line_builder=_line,
    transfers={},
  )

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
        include_lead_mode=include_lead_mode,
      )
    )

  execute_template_script(
    XG_POSTAMBLE_SCRIPT,
    environment=base_environment,
    output_lines=lines,
    line_builder=_line,
    transfers={},
  )
  if strip_g113_params:
    lines = _apply_strip_g113_params(lines)
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
  strip_g113_params=False,
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
  lines = render_xg_template_lines(layer, special_inputs=resolved_special_inputs, strip_g113_params=strip_g113_params)
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
