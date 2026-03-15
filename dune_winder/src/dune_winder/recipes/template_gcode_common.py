###############################################################################
# Name: template_gcode_common.py
# Uses: Shared helper utilities for programmatic template G-Code generators.
# Date: 2026-03-05
###############################################################################

import re

from dune_winder.gcode.model import CommandWord, FunctionCall, Opcode
from dune_winder.gcode.parser import parse_line_text


_PIN_TOKEN_RE = re.compile(r"\b(P[BF])(-?\d+)\b")


def format_number(value):
  text = "{0:.6f}".format(float(value)).rstrip("0").rstrip(".")
  if text in ("", "-0"):
    return "0"
  return text


def normalize_pin_tokens(text, wrap_pin_number):
  def replace(match):
    return match.group(1) + str(wrap_pin_number(match.group(2)))

  return _PIN_TOKEN_RE.sub(replace, text)


def build_line(parts, normalize_pin_tokens_fn, normalize_line_text_fn):
  text = normalize_pin_tokens_fn(
    " ".join(str(part) for part in parts if part not in (None, ""))
  )
  return normalize_line_text_fn(text)


def coord(axis, value):
  return axis + format_number(value)


def offset_fragment(axis, value, *, coord_fn):
  if abs(float(value)) < 1e-9:
    return None
  return "G105 " + coord_fn(axis, value)


def conditional_offset_fragment(axis, condition_value, rendered_value, *, coord_fn):
  if abs(float(condition_value)) < 1e-9:
    return None
  return "G105 " + coord_fn(axis, rendered_value)


def near_comb(pin_number, combs):
  return any(abs(int(pin_number) - comb_pin) <= 5 for comb_pin in combs)


def coerce_bool(value, *, error_type):
  if isinstance(value, bool):
    return value
  if isinstance(value, (int, float)):
    return 0 != value
  if isinstance(value, str):
    normalized = value.strip().lower()
    if normalized in ("", "0", "false", "no", "off"):
      return False
    if normalized in ("1", "true", "yes", "on"):
      return True
  raise error_type("Expected a boolean-compatible value, got " + repr(value) + ".")


def coerce_number(value, *, error_type):
  if isinstance(value, bool):
    raise error_type("Boolean values are not valid offsets.")
  if isinstance(value, (int, float)):
    return float(value)
  if isinstance(value, str):
    try:
      return float(value.strip())
    except ValueError as exc:
      raise error_type("Expected a numeric value, got " + repr(value) + ".") from exc
  raise error_type("Expected a numeric value, got " + type(value).__name__ + ".")


def coerce_offsets(
  value,
  *,
  default_offsets,
  offset_ids,
  coerce_number_fn,
  error_type,
  layer_name,
):
  if value is None:
    return list(default_offsets)
  if isinstance(value, str):
    raw_values = [part.strip() for part in value.split(",")]
  else:
    try:
      raw_values = list(value)
    except TypeError as exc:
      raise error_type("Offsets must be a 12-item iterable.") from exc
  if len(raw_values) != len(offset_ids):
    raise error_type(
      "Expected "
      + str(len(offset_ids))
      + " "
      + str(layer_name)
      + " offsets, got "
      + str(len(raw_values))
      + "."
    )
  return [coerce_number_fn(item) for item in raw_values]


def apply_named_input(
  named_inputs,
  offsets,
  transfer_pause,
  include_lead_mode,
  *,
  coerce_bool_fn,
  coerce_number_fn,
  legacy_offset_names,
  offset_ids,
  error_type,
  layer_name,
):
  current_transfer_pause = transfer_pause
  current_include_lead_mode = include_lead_mode
  for key, value in (named_inputs or {}).items():
    if key == "transferPause" or key == "pause at combs":
      current_transfer_pause = coerce_bool_fn(value)
      continue
    if key in ("includeLeadMode", "include lead mode"):
      current_include_lead_mode = coerce_bool_fn(value)
      continue
    if key in legacy_offset_names:
      offsets[legacy_offset_names[key]] = coerce_number_fn(value)
      continue
    if key in offset_ids:
      offsets[offset_ids.index(key)] = coerce_number_fn(value)
      continue
    if key.endswith("_offset") and key[:-7] in offset_ids:
      offsets[offset_ids.index(key[:-7])] = coerce_number_fn(value)
      continue
    raise error_type("Unknown " + str(layer_name) + " named input: " + repr(key))
  return current_transfer_pause, current_include_lead_mode


def apply_special_input(
  special_inputs,
  offsets,
  transfer_pause,
  include_lead_mode,
  *,
  coerce_bool_fn,
  coerce_number_fn,
  coerce_offsets_fn,
  special_offset_aliases,
  offset_ids,
  error_type,
  layer_name,
):
  current_transfer_pause = transfer_pause
  current_include_lead_mode = include_lead_mode
  for key, value in (special_inputs or {}).items():
    if key in ("transferPause", "transfer_pause", "pause_at_combs"):
      current_transfer_pause = coerce_bool_fn(value)
      continue
    if key in ("includeLeadMode", "include_lead_mode", "include_lead"):
      current_include_lead_mode = coerce_bool_fn(value)
      continue
    if key == "offsets":
      parsed_offsets = coerce_offsets_fn(value)
      for index, offset in enumerate(parsed_offsets):
        offsets[index] = offset
      continue
    if key in special_offset_aliases:
      offsets[special_offset_aliases[key]] = coerce_number_fn(value)
      continue
    if key in offset_ids:
      offsets[offset_ids.index(key)] = coerce_number_fn(value)
      continue
    if key.endswith("_offset") and key[:-7] in offset_ids:
      offsets[offset_ids.index(key[:-7])] = coerce_number_fn(value)
      continue
    raise error_type("Unknown " + str(layer_name) + " special input: " + repr(key))
  return current_transfer_pause, current_include_lead_mode


def resolve_options(
  named_inputs=None,
  special_inputs=None,
  cell_overrides=None,
  *,
  default_offsets,
  apply_named_input_fn,
  apply_special_input_fn,
  error_type,
  cell_overrides_error_message,
):
  if cell_overrides:
    raise error_type(cell_overrides_error_message)

  offsets = list(default_offsets)
  transfer_pause = False
  include_lead_mode = False
  transfer_pause, include_lead_mode = apply_named_input_fn(
    named_inputs,
    offsets,
    transfer_pause,
    include_lead_mode,
  )
  transfer_pause, include_lead_mode = apply_special_input_fn(
    special_inputs,
    offsets,
    transfer_pause,
    include_lead_mode,
  )
  return offsets, transfer_pause, include_lead_mode


def resolve_render_state(
  *,
  offsets=None,
  transfer_pause=False,
  include_lead_mode=False,
  named_inputs=None,
  special_inputs=None,
  cell_overrides=None,
  resolve_options_fn,
  coerce_offsets_fn,
  coerce_bool_fn,
):
  if offsets is None:
    resolved_offsets, resolved_transfer_pause, resolved_include_lead_mode = (
      resolve_options_fn(
        named_inputs=named_inputs,
        special_inputs=special_inputs,
        cell_overrides=cell_overrides,
      )
    )
    return (
      resolved_offsets,
      (coerce_bool_fn(transfer_pause) or resolved_transfer_pause),
      (coerce_bool_fn(include_lead_mode) or resolved_include_lead_mode),
    )

  resolved_offsets, resolved_transfer_pause, resolved_include_lead_mode = (
    resolve_options_fn(
      named_inputs=named_inputs,
      special_inputs=special_inputs,
      cell_overrides=cell_overrides,
    )
  )
  for index, value in enumerate(coerce_offsets_fn(offsets)):
    resolved_offsets[index] = value
  return (
    resolved_offsets,
    (coerce_bool_fn(transfer_pause) or resolved_transfer_pause),
    (coerce_bool_fn(include_lead_mode) or resolved_include_lead_mode),
  )


def wrap_identifier(wrap_number, line_number):
  return "(" + str(wrap_number) + "," + str(line_number) + ")"


def annotate_wrap_lines(wrap_number, lines, *, line_builder):
  return [
    line_builder(wrap_identifier(wrap_number, line_number), line)
    for line_number, line in enumerate(lines, start=1)
  ]


def number_lines(lines, *, line_builder):
  return [line_builder("N" + str(line_number), line) for line_number, line in enumerate(lines)]


def line_emits_xy_target(text: str) -> bool:
  line = parse_line_text(text)
  for item in line.items:
    if isinstance(item, CommandWord) and item.letter in ("X", "Y"):
      return True
    if not isinstance(item, FunctionCall):
      continue
    opcode = item.opcode_as_int()
    if opcode == int(Opcode.QUEUE_MERGE):
      continue
    if opcode in (
      int(Opcode.SEEK_TRANSFER),
      int(Opcode.CLIP),
      int(Opcode.ARM_CORRECT),
    ):
      return True
    if opcode == int(Opcode.PIN_CENTER):
      axes = str(item.parameters[-1]).upper() if item.parameters else ""
      if "X" in axes or "Y" in axes:
        return True
    if opcode == int(Opcode.OFFSET):
      for parameter in item.parameters:
        axis = str(parameter)[:1].upper()
        if axis in ("X", "Y"):
          return True
  return False


def add_precise_merge_marker(line: str, *, normalize_line_text_fn):
  parsed = parse_line_text(line)
  for item in parsed.items:
    if isinstance(item, FunctionCall) and item.opcode_as_int() == int(Opcode.QUEUE_MERGE):
      return normalize_line_text_fn(line)
  if not line_emits_xy_target(line):
    return normalize_line_text_fn(line)
  return normalize_line_text_fn("G113 PPRECISE " + line)


def mark_precise_merge_lines(lines, *, normalize_line_text_fn):
  return [
    add_precise_merge_marker(line, normalize_line_text_fn=normalize_line_text_fn)
    for line in lines
  ]


def coerce_cli_value(value, *, coerce_bool_fn, coerce_number_fn, input_error_type):
  normalized = value.strip()
  if "," in normalized:
    return [part.strip() for part in normalized.split(",")]
  if normalized.lower() in ("true", "false", "yes", "no", "on", "off"):
    return coerce_bool_fn(normalized)
  try:
    return coerce_number_fn(normalized)
  except input_error_type:
    return normalized


def parse_assignment(raw_assignment, *, coerce_cli_value_fn, input_error_type):
  if "=" not in raw_assignment:
    raise input_error_type(
      "Expected KEY=VALUE assignment, got " + repr(raw_assignment) + "."
    )
  key, value = raw_assignment.split("=", 1)
  return key.strip(), coerce_cli_value_fn(value)
