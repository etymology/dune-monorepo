###############################################################################
# Name: UTemplateGCode.py
# Uses: Generate U-layer G-Code from the programmatic specification.
# Date: 2026-03-04
###############################################################################

from __future__ import annotations

import argparse
from dataclasses import dataclass
import re
from pathlib import Path

from dune_winder.core.manual_calibration import LAYER_METADATA
from dune_winder.recipes.recipe_template_language import (
  compile_template_script,
  execute_template_script,
)
from dune_winder.machine.geometry.uv_wrap_geometry import b_to_a_pin
from dune_winder.recipes.recipe import Recipe
from dune_winder.recipes import template_gcode_common
from dune_winder.gcode.renderer import normalize_line_text
from dune_winder.recipes.template_gcode_transfers import (
  append_a_to_b_transfer,
  append_b_to_a_transfer,
  g106_line,
)


WRAP_COUNT = 400
Y_PULL_IN = 200.0
X_PULL_IN = 200.0
COMB_PULL_FACTOR = 3.0
PREAMBLE_X = 7174.0
PREAMBLE_Y = 60.0
PREAMBLE_BOARD_GAP_PULL = -50.0
COMBS = (596, 744, 892, 1040, 1758, 1906, 2054, 2202)
PIN_MIN = 1
PIN_MAX = 2401
PIN_SPAN = PIN_MAX - PIN_MIN + 1
DEFAULT_OFFSETS = (0.0,) * 12
DEFAULT_U_TEMPLATE_WORKBOOK = None
DEFAULT_U_TEMPLATE_SHEET = None
PULL_IN_IDS = ("Y_PULL_IN", "X_PULL_IN", "Y_HOVER")
DEFAULT_PULL_INS = {
  "Y_PULL_IN": Y_PULL_IN,
  "X_PULL_IN": X_PULL_IN,
  "Y_HOVER": 5.0,
}
PULL_IN_NAME_ALIASES = {
  "Y_PULL_IN": "Y_PULL_IN",
  "X_PULL_IN": "X_PULL_IN",
  "Y_HOVER": "Y_HOVER",
  "y_pull_in": "Y_PULL_IN",
  "x_pull_in": "X_PULL_IN",
  "y_hover": "Y_HOVER",
}

OFFSET_IDS = (
  "top_b_foot_end",
  "top_a_foot_end",
  "bottom_a_head_end",
  "bottom_b_head_end",
  "head_b_corner",
  "head_a_corner",
  "top_a_head_end",
  "top_b_head_end",
  "bottom_b_foot_end",
  "bottom_a_foot_end",
  "foot_a_corner",
  "foot_b_corner",
)

LEGACY_OFFSET_NAMES = {
  "line 1 (Top B corner - foot end)": 0,
  "line 2 (Top A corner - foot end)": 1,
  "line 3 (Bottom A corner - head end)": 2,
  "line 4 (Bottom B corner - head end)": 3,
  "line 5 (Head B corner)": 4,
  "line 6 (Head A corner)": 5,
  "line 7 (Top A corner - head end)": 6,
  "line 8 (Top B corner - head end)": 7,
  "line 9 (Bottom B corner - foot end)": 8,
  "line 10 (Bottom A corner - foot end)": 9,
  "line 11 (Foot A corner)": 10,
  "line 12 (Foot B corner)": 11,
}

SPECIAL_OFFSET_ALIASES = {
  "head_b_offset": 4,
  "head_a_offset": 5,
  "foot_a_offset": 10,
  "foot_b_offset": 11,
}
FOOT_PAUSE_MIN_PIN = 1200
FOOT_PAUSE_MAX_PIN = 1600
_PIN_PAIR_RE = re.compile(r"\bG103\s+(P[AB])(\d+)\s+(P[AB])(\d+)\b")
SCRIPT_VARIANT_DEFAULT = "default"
SCRIPT_VARIANT_WRAPPING = "wrapping"

U_WRAP_SCRIPT = compile_template_script(
  (
    "emit (------------------STARTING LOOP ${wrap}------------------)",
    "emit G113 PPRECISE G109 PB${1200 + wrap} PBR G103 PB${2002 - wrap} PB${2003 - wrap} PXY ${offset('PX', offsets[0])} G102 G108 (Top B corner - foot end)",
    "transfer b_to_a_transfer",
    "emit G113 PPRECISE G109 PB${2002 - wrap} PLT G103 PA${800 + wrap} PA${801 + wrap} PXY G105 ${coord('PY', Y_HOVER)} ${conditional_offset('PX', offsets[1], offsets[1])} (Top A corner - foot end)",
    "emit G113 PTOLERANT G103 PA${800 + wrap} PA${801 + wrap} PY G105 ${coord('PY', -Y_PULL_IN)}",
    "if near_comb(800 + wrap): emit G113 PTOLERANT G103 PA${800 + wrap} PA${801 + wrap} PX G105 ${coord('PX-', Y_PULL_IN * COMB_PULL_FACTOR)}",
    "emit G113 PPRECISE G109 PA${800 + wrap} PLB G103 PA${2402 - wrap} PA${2403 - wrap} PXY ${offset('PX', offsets[2])} G102 G108 (Bottom A corner - head end)",
    "transfer a_to_b_transfer",
    "emit G113 PPRECISE G109 PA${2402 - wrap} PBR G103 PB${400 + wrap} PB${401 + wrap} PXY G105 ${coord('PY', -Y_HOVER)} ${offset('PX', offsets[3])} (Bottom B corner - head end, rewind)",
    "emit G113 PTOLERANT G103 PB${400 + wrap} PB${401 + wrap} PY G105 ${coord('PY', Y_PULL_IN)}",
    "if near_comb(400 + wrap): emit G113 PTOLERANT G103 PB${400 + wrap} PB${401 + wrap} PX G105 ${coord('PX-', Y_PULL_IN * COMB_PULL_FACTOR)}",
    "emit G113 PPRECISE (HEAD RESTART) G109 PB${400 + wrap} PLT G103 PB${401 - wrap} PB${400 - wrap} PXY ${offset('PY', offsets[4])} G102 G108 (Head B corner)",
    "transfer b_to_a_transfer",
    "emit G113 PTOLERANT G109 PB${401 - wrap} PLT G103 PA${wrap} PA${2400 + wrap} PXY ${offset('PY', offsets[5])} (Head A corner, rewind)",
    "emit G113 PTOLERANT G103 PA${1 + wrap} PA${wrap} PX G105 ${coord('PX', X_PULL_IN)}",
    "emit G113 PPRECISE G109 PA${1 + wrap} PRT G103 PA${800 - wrap} PA${799 - wrap} PXY ${offset('PX', offsets[6])} G102 G108 (Top A corner - head end)",
    "transfer a_to_b_transfer",
    "emit G113 PPRECISE G109 PA${800 - wrap} PRT G103 PB${2002 + wrap} PB${2003 + wrap} PXY G105 ${coord('PY', Y_HOVER)} ${conditional_offset('PX', offsets[7], offsets[7])} (Top B corner - head end)",
    "emit G113 PTOLERANT G103 PB${2002 + wrap} PB${2003 + wrap} PY G105 ${coord('PY', -Y_PULL_IN)}",
    "if near_comb(2002 + wrap): emit G113 PTOLERANT G103 PB${2002 + wrap} PB${2003 + wrap} PX G105 ${coord('PX', Y_PULL_IN * COMB_PULL_FACTOR)}",
    "emit G113 PPRECISE G109 PB${2001 + wrap} PRB G103 PB${1201 - wrap} PB${1202 - wrap} PXY ${offset('PX', offsets[8])} G102 G108 (Bottom B corner - foot end)",
    "transfer b_to_a_transfer",
    "emit G113 PPRECISE G109 PB${1199 + wrap} PBL G103 PA${1601 + wrap} PA${1602 + wrap} PXY G105 ${coord('PY', -Y_HOVER)} ${offset('PX', offsets[9])} (Bottom A corner - foot end, rewind)",
    "emit G113 PTOLERANT G103 PA${1601 + wrap} PA${1602 + wrap} PY G105 ${coord('PY', Y_PULL_IN)}",
    "if near_comb(1601 + wrap): emit G113 PTOLERANT G103 PA${1601 + wrap} PA${1602 + wrap} PX G105 ${coord('PX', X_PULL_IN * COMB_PULL_FACTOR)}",
    "emit G113 PPRECISE G109 PA${1601 + wrap} PRT G103 PA${1601 - wrap} PA${1600 - wrap} PXY ${offset('PY', offsets[10])} G102 G108 (Foot A corner)",
    "transfer a_to_b_transfer",
    "emit G113 PPRECISE G109 PA${1601 - wrap} PRT G103 PB${1201 + wrap} PB${1200 + wrap} PXY ${offset('PY', offsets[11])} (Foot B corner, rewind)",
    "emit G113 PTOLERANT G103 PB${1201 + wrap} PB${1200 + wrap} PX G105 ${coord('PX', -X_PULL_IN)}",
  )
)

U_WRAP_WRAPPING_SCRIPT = compile_template_script(
  (
    "emit G115 ${coord('PX', -X_PULL_IN)} ${coord('PY', 0)}",
    "emit G117 PB${2002 - wrap} (Top B corner - foot end)",
    "emit G118 PB${2002 - wrap} (Top A corner - foot end)",
    "emit G115 ${coord('PX', 0)} ${coord('PY', -Y_PULL_IN)}",
    "if near_comb(2002 - wrap): emit G115 ${coord('PX', -Y_PULL_IN * COMB_PULL_FACTOR)} ${coord('PY', 0)} (comb pull)",
    "emit G118 PB${400 + wrap} (Bottom A corner - head end)",
    "emit G117 PB${400 + wrap} (Bottom B corner - head end)",
    "emit G115 ${coord('PX', 0)} ${coord('PY', Y_PULL_IN)}",
    "if near_comb(400 + wrap): emit G115 ${coord('PX', -Y_PULL_IN * COMB_PULL_FACTOR)} ${coord('PY', 0)} (comb pull)",
    "emit G117 PB${401 - wrap} (Head B corner)",
    "emit G118 PB${401 - wrap} (Head A corner)",
    "emit G115 ${coord('PX', X_PULL_IN)} ${coord('PY', 0)}",
    "emit G118 PB${2001 + wrap} (Top A corner - head end)",
    "emit G117 PB${2001 + wrap} (Top B corner - head end)",
    "emit G115 ${coord('PX', 0)} ${coord('PY', -Y_PULL_IN)}",
    "if near_comb(2001 + wrap): emit G115 ${coord('PX', Y_PULL_IN * COMB_PULL_FACTOR)} ${coord('PY', 0)} (comb pull)",
    "emit G117 PB${1201 - wrap} (Bottom B corner - foot end)",
    "emit G118 PB${1201 - wrap} (Bottom A corner - foot end)",
    "emit G115 ${coord('PX', 0)} ${coord('PY', Y_PULL_IN)}",
    "if near_comb(1201 - wrap): emit G115 ${coord('PX', X_PULL_IN * COMB_PULL_FACTOR)} ${coord('PY', 0)} (comb pull)",
    "emit G118 PB${1201 + wrap} (Foot A corner)",
  )
)


_G113_PARAMS_RE = re.compile(r"G113\s+P\w+\s*")


def _apply_strip_g113_params(lines):
  return [
    re.sub(r"\s{2,}", " ", _G113_PARAMS_RE.sub("", line)).strip() for line in lines
  ]


def _normalize_script_variant(script_variant):
  if script_variant is None:
    return SCRIPT_VARIANT_DEFAULT

  normalized = str(script_variant).strip().lower()
  if normalized in ("", "default", "normal", "standard"):
    return SCRIPT_VARIANT_DEFAULT
  if normalized == SCRIPT_VARIANT_WRAPPING:
    return SCRIPT_VARIANT_WRAPPING
  raise UTemplateInputError("Unsupported U script variant: " + repr(script_variant))


def _are_consecutive_pins(first_pin, second_pin):
  return (
    _wrap_pin_number(first_pin + 1) == second_pin
    or _wrap_pin_number(second_pin + 1) == first_pin
  )


def _should_add_foot_pause(first_prefix, first_pin, second_prefix, second_pin):
  if not _are_consecutive_pins(first_pin, second_pin):
    return False

  if not (
    FOOT_PAUSE_MIN_PIN <= first_pin <= FOOT_PAUSE_MAX_PIN
    or FOOT_PAUSE_MIN_PIN <= second_pin <= FOOT_PAUSE_MAX_PIN
  ):
    return False

  first_board = LAYER_METADATA["U"]["pinToBoard"].get(first_pin)
  second_board = LAYER_METADATA["U"]["pinToBoard"].get(second_pin)
  if first_board is None or second_board is None:
    return False

  if (
    first_prefix == "PA"
    and second_prefix == "PA"
    and first_board["side"] == "foot"
    and second_board["side"] == "foot"
  ):
    # U-layer Foot A corner lines traverse descending A pins. For those lines
    # the physical board gap is reached at the foot-board start pin, one wrap
    # before pinToBoard switches boardIndex.
    lower_pin = min(first_pin, second_pin)
    lower_endpoint = LAYER_METADATA["U"]["endpointInfo"].get(lower_pin)
    return (
      lower_endpoint is not None
      and lower_endpoint["side"] == "foot"
      and lower_endpoint["endpoint"] == "start"
    )

  return first_board["boardIndex"] != second_board["boardIndex"]


def _split_trailing_comments(line):
  body = str(line).rstrip()
  comments = []
  while True:
    match = re.search(r"\s+(\([^()]*\))\s*$", body)
    if match is None:
      break
    comments.insert(0, match.group(1))
    body = body[: match.start()].rstrip()
  return body, comments


def _append_command_before_trailing_comments(line, command):
  body, comments = _split_trailing_comments(line)
  if body.endswith(" " + command) or body == command:
    return str(line)
  if comments:
    return normalize_line_text(" ".join([body, command] + comments))
  return normalize_line_text(body + " " + command)


def _apply_add_foot_pauses(lines):
  updated_lines = []
  for line in lines:
    match = _PIN_PAIR_RE.search(line)
    if match is None:
      updated_lines.append(line)
      continue

    first_prefix = match.group(1)
    first_pin = int(match.group(2))
    second_prefix = match.group(3)
    second_pin = int(match.group(4))
    if _should_add_foot_pause(first_prefix, first_pin, second_prefix, second_pin):
      updated_lines.append(
        _append_command_before_trailing_comments(line, "G111 (board gap)")
      )
      continue

    updated_lines.append(line)
  return updated_lines


class UTemplateInputError(ValueError):
  pass


@dataclass(frozen=True)
class UWrapPrimarySite:
  wrap_number: int
  wrap_line_number: int
  anchor_pin: str
  orientation_token: str
  g103_pin_a: str
  g103_pin_b: str


def _format_number(value):
  return template_gcode_common.format_number(value)


def _wrap_pin_number(value):
  pin_number = int(value)
  return ((pin_number - PIN_MIN) % PIN_SPAN) + PIN_MIN


def _normalize_pin_tokens(text):
  return template_gcode_common.normalize_pin_tokens(text, _wrap_pin_number)


def _line(*parts):
  return template_gcode_common.build_line(
    parts,
    normalize_pin_tokens_fn=_normalize_pin_tokens,
    normalize_line_text_fn=normalize_line_text,
  )


def _coord(axis, value):
  return template_gcode_common.coord(axis, value)


def _offset_fragment(axis, value):
  return template_gcode_common.offset_fragment(axis, value, coord_fn=_coord)


def _g106(mode):
  return g106_line(_line, mode)


def _conditional_offset_fragment(axis, condition_value, rendered_value):
  return template_gcode_common.conditional_offset_fragment(
    axis,
    condition_value,
    rendered_value,
    coord_fn=_coord,
  )


def _near_comb(pin_number):
  return template_gcode_common.near_comb(pin_number, COMBS, "U")


def _coerce_bool(value):
  return template_gcode_common.coerce_bool(value, error_type=UTemplateInputError)


def _coerce_number(value):
  return template_gcode_common.coerce_number(value, error_type=UTemplateInputError)


def _coerce_offsets(value):
  return template_gcode_common.coerce_offsets(
    value,
    default_offsets=DEFAULT_OFFSETS,
    offset_ids=OFFSET_IDS,
    coerce_number_fn=_coerce_number,
    error_type=UTemplateInputError,
    layer_name="U",
  )


def _apply_pull_in_input(key, value, pull_ins):
  pull_in_id = PULL_IN_NAME_ALIASES.get(key)
  if pull_in_id is None:
    return False
  pull_ins[pull_in_id] = _coerce_number(value)
  return True


def _apply_named_input(
  named_inputs,
  offsets,
  transfer_pause,
  add_foot_pauses,
  include_lead_mode,
  pull_ins,
):
  filtered_named_inputs = {}
  for key, value in (named_inputs or {}).items():
    if _apply_pull_in_input(key, value, pull_ins):
      continue
    if key in ("addFootPauses", "add foot pauses"):
      add_foot_pauses = _coerce_bool(value)
      continue
    filtered_named_inputs[key] = value
  transfer_pause, include_lead_mode = template_gcode_common.apply_named_input(
    filtered_named_inputs,
    offsets,
    transfer_pause,
    include_lead_mode,
    coerce_bool_fn=_coerce_bool,
    coerce_number_fn=_coerce_number,
    legacy_offset_names=LEGACY_OFFSET_NAMES,
    offset_ids=OFFSET_IDS,
    error_type=UTemplateInputError,
    layer_name="U",
  )
  return transfer_pause, add_foot_pauses, include_lead_mode


def _apply_special_input(
  special_inputs,
  offsets,
  transfer_pause,
  add_foot_pauses,
  include_lead_mode,
  pull_ins,
):
  filtered_special_inputs = {}
  for key, value in (special_inputs or {}).items():
    if _apply_pull_in_input(key, value, pull_ins):
      continue
    if key in ("addFootPauses", "add_foot_pauses", "add_foot_pause"):
      add_foot_pauses = _coerce_bool(value)
      continue
    filtered_special_inputs[key] = value
  transfer_pause, include_lead_mode = template_gcode_common.apply_special_input(
    filtered_special_inputs,
    offsets,
    transfer_pause,
    include_lead_mode,
    coerce_bool_fn=_coerce_bool,
    coerce_number_fn=_coerce_number,
    coerce_offsets_fn=_coerce_offsets,
    special_offset_aliases=SPECIAL_OFFSET_ALIASES,
    offset_ids=OFFSET_IDS,
    error_type=UTemplateInputError,
    layer_name="U",
  )
  return transfer_pause, add_foot_pauses, include_lead_mode


def _resolve_options(named_inputs=None, special_inputs=None, cell_overrides=None):
  if cell_overrides:
    raise UTemplateInputError(
      "Cell overrides are not supported by the programmatic U generator."
    )

  offsets = list(DEFAULT_OFFSETS)
  transfer_pause = False
  add_foot_pauses = False
  include_lead_mode = False
  pull_ins = dict(DEFAULT_PULL_INS)
  transfer_pause, add_foot_pauses, include_lead_mode = _apply_named_input(
    named_inputs,
    offsets,
    transfer_pause,
    add_foot_pauses,
    include_lead_mode,
    pull_ins,
  )
  transfer_pause, add_foot_pauses, include_lead_mode = _apply_special_input(
    special_inputs,
    offsets,
    transfer_pause,
    add_foot_pauses,
    include_lead_mode,
    pull_ins,
  )
  return offsets, transfer_pause, add_foot_pauses, include_lead_mode, pull_ins


def _resolve_render_state(
  *,
  offsets=None,
  transfer_pause=False,
  add_foot_pauses=False,
  include_lead_mode=False,
  named_inputs=None,
  special_inputs=None,
  cell_overrides=None,
):
  (
    resolved_offsets,
    resolved_transfer_pause,
    resolved_add_foot_pauses,
    resolved_include_lead_mode,
    resolved_pull_ins,
  ) = _resolve_options(
    named_inputs=named_inputs,
    special_inputs=special_inputs,
    cell_overrides=cell_overrides,
  )
  if offsets is not None:
    for index, value in enumerate(_coerce_offsets(offsets)):
      resolved_offsets[index] = value
  return (
    resolved_offsets,
    (_coerce_bool(transfer_pause) or resolved_transfer_pause),
    (_coerce_bool(add_foot_pauses) or resolved_add_foot_pauses),
    (_coerce_bool(include_lead_mode) or resolved_include_lead_mode),
    resolved_pull_ins,
  )


def _wrap_identifier(wrap_number, line_number):
  return template_gcode_common.wrap_identifier(wrap_number, line_number)


def _annotate_wrap_lines(wrap_number, lines):
  return template_gcode_common.annotate_wrap_lines(
    wrap_number,
    lines,
    line_builder=_line,
  )


def _number_lines(lines):
  return template_gcode_common.number_lines(lines, line_builder=_line)


def _token_line(*parts):
  return tuple(_normalize_pin_tokens(str(part)) for part in parts)


def _normalize_pin_token(token):
  normalized = str(token).strip().upper()
  if normalized.startswith("P"):
    normalized = normalized[1:]
  return normalized


def _extract_primary_site(tokens):
  try:
    g109_index = tokens.index("G109")
    g103_index = tokens.index("G103")
  except ValueError:
    return None
  if g109_index + 2 >= len(tokens) or g103_index + 2 >= len(tokens):
    return None
  anchor_pin = _normalize_pin_token(tokens[g109_index + 1])
  orientation_token = str(tokens[g109_index + 2]).strip().upper()
  pin_a = _normalize_pin_token(tokens[g103_index + 1])
  pin_b = _normalize_pin_token(tokens[g103_index + 2])
  if not anchor_pin or not pin_a or not pin_b:
    return None
  if (
    anchor_pin[:1] not in ("A", "B")
    or pin_a[:1] not in ("A", "B")
    or pin_b[:1] not in ("A", "B")
  ):
    return None
  return (anchor_pin, orientation_token, pin_a, pin_b)


def _extract_g103_segment(tokens):
  try:
    command_index = tokens.index("G103")
  except ValueError:
    return None
  if command_index + 2 >= len(tokens):
    return None
  pin_a = _normalize_pin_token(tokens[command_index + 1])
  pin_b = _normalize_pin_token(tokens[command_index + 2])
  if not pin_a or not pin_b:
    return None
  if pin_a[:1] not in ("A", "B") or pin_b[:1] not in ("A", "B"):
    return None
  return (pin_a, pin_b)


def iter_u_wrap_primary_sites(
  *,
  named_inputs=None,
  special_inputs=None,
  cell_overrides=None,
):
  (
    resolved_offsets,
    transfer_pause_value,
    _add_foot_pauses_value,
    include_lead_mode_value,
    pull_ins,
  ) = _resolve_render_state(
    named_inputs=named_inputs,
    special_inputs=special_inputs,
    cell_overrides=cell_overrides,
  )

  segments = []
  for wrap_number in range(1, WRAP_COUNT + 1):
    wrap_lines = []
    transfers = {
      "b_to_a_transfer": lambda output: append_b_to_a_transfer(
        output,
        line_builder=_token_line,
        transfer_pause=transfer_pause_value,
        include_lead_mode=include_lead_mode_value,
      ),
      "a_to_b_transfer": lambda output: append_a_to_b_transfer(
        output,
        line_builder=_token_line,
        transfer_pause=transfer_pause_value,
        include_lead_mode=include_lead_mode_value,
      ),
    }
    environment = {
      "wrap": wrap_number,
      "offsets": resolved_offsets,
      "coord": _coord,
      "offset": _offset_fragment,
      "conditional_offset": _conditional_offset_fragment,
      "near_comb": _near_comb,
      "Y_PULL_IN": pull_ins["Y_PULL_IN"],
      "X_PULL_IN": pull_ins["X_PULL_IN"],
      "Y_HOVER": pull_ins["Y_HOVER"],
      "COMB_PULL_FACTOR": COMB_PULL_FACTOR,
    }
    execute_template_script(
      U_WRAP_SCRIPT,
      environment=environment,
      output_lines=wrap_lines,
      line_builder=_token_line,
      transfers=transfers,
    )
    for wrap_line_number, tokens in enumerate(wrap_lines, start=1):
      primary_site = _extract_primary_site(tokens)
      if primary_site is None:
        continue
      segments.append(
        UWrapPrimarySite(
          wrap_number=wrap_number,
          wrap_line_number=wrap_line_number,
          anchor_pin=primary_site[0],
          orientation_token=primary_site[1],
          g103_pin_a=primary_site[2],
          g103_pin_b=primary_site[3],
        )
      )

  return tuple(segments)


def _render_wrap_lines(
  wrap_number, offsets, transfer_pause, include_lead_mode, pull_ins
):
  lines = []

  transfers = {
    "b_to_a_transfer": lambda output: append_b_to_a_transfer(
      output,
      line_builder=_line,
      transfer_pause=transfer_pause,
      include_lead_mode=include_lead_mode,
    ),
    "a_to_b_transfer": lambda output: append_a_to_b_transfer(
      output,
      line_builder=_line,
      transfer_pause=transfer_pause,
      include_lead_mode=include_lead_mode,
    ),
  }

  environment = {
    "wrap": wrap_number,
    "offsets": offsets,
    "coord": _coord,
    "offset": _offset_fragment,
    "conditional_offset": _conditional_offset_fragment,
    "near_comb": _near_comb,
    "Y_PULL_IN": pull_ins["Y_PULL_IN"],
    "X_PULL_IN": pull_ins["X_PULL_IN"],
    "Y_HOVER": pull_ins["Y_HOVER"],
    "COMB_PULL_FACTOR": COMB_PULL_FACTOR,
  }

  execute_template_script(
    U_WRAP_SCRIPT,
    environment=environment,
    output_lines=lines,
    line_builder=_line,
    transfers=transfers,
  )

  return _annotate_wrap_lines(wrap_number, lines)


def _render_wrapping_wrap_lines(wrap_number, pull_ins, offsets):
  n = int(wrap_number) - 1

  def b_pin(pin_number):
    return "B" + str(_wrap_pin_number(pin_number))

  def a_from_b(pin_number):
    return b_to_a_pin("U", b_pin(pin_number))

  def anchor_to_target(anchor_pin, target_pin, label=None, offset=None, hover=False):
    call = f"~anchorToTarget({anchor_pin},{target_pin}"
    if offset is not None:
      offset_x, offset_y = offset
      if abs(float(offset_x)) >= 1e-9 or abs(float(offset_y)) >= 1e-9:
        call += (
          ",offset=("
          + _coord("", offset_x)
          + ","
          + _coord("", offset_y)
          + ")"
        )
    if hover:
      call += ",hover=True"
    call += ")"
    parts = [call]
    if label:
      parts.append("(" + str(label) + ")")
    return _line(*parts)

  lines = [
    anchor_to_target(
      a_from_b(1201 + n),
      b_pin(1201 + n),
      "Foot B corner",
      offset=(0.0, offsets[11]),
    ),
    _line("~increment(" + _coord("", -pull_ins["X_PULL_IN"]) + ",0)"),
    anchor_to_target(
      b_pin(1201 + n),
      b_pin(1602 + (399 - n)),
      "Top B corner - foot end",
      offset=(offsets[0], 0.0),
    ),
    anchor_to_target(
      b_pin(1602 + (399 - n)),
      a_from_b(1602 + (399 - n)),
      "Top A corner - foot end",
      offset=(offsets[1], 0.0),
      hover=True,
    ),
    _line("~increment(0," + _coord("", -pull_ins["Y_PULL_IN"]) + ")"),
  ]
  if _near_comb(1602 + (399 - n)):
    lines.append(
      _line(
        "~increment(" + _coord("", -(pull_ins["Y_PULL_IN"] * COMB_PULL_FACTOR)) + ",0)",
        "(comb pull)",
      )
    )
  lines.extend(
    [
      anchor_to_target(
        a_from_b(1602 + (399 - n)),
        a_from_b(401 + n),
        "Bottom A corner - head end",
        offset=(offsets[2], 0.0),
      ),
      anchor_to_target(
        a_from_b(401 + n),
        b_pin(401 + n),
        "Bottom B corner - head end",
        offset=(offsets[3], 0.0),
        hover=True,
      ),
      _line("~increment(0," + _coord("", pull_ins["Y_PULL_IN"]) + ")"),
    ]
  )
  if _near_comb(401 + n):
    lines.append(
      _line(
        "~increment(" + _coord("", -(pull_ins["Y_PULL_IN"] * COMB_PULL_FACTOR)) + ",0)",
        "(comb pull)",
      )
    )
  lines.extend(
    [
      anchor_to_target(
        b_pin(401 + n),
        b_pin(400 - n),
        "Head B corner",
        offset=(0.0, offsets[4]),
      ),
      anchor_to_target(
        b_pin(400 - n),
        a_from_b(400 - n),
        "Head A corner",
        offset=(0.0, offsets[5]),
      ),
      _line("~increment(" + _coord("", pull_ins["X_PULL_IN"]) + ",0)"),
      anchor_to_target(
        a_from_b(400 - n),
        a_from_b(n - 399),
        "Top A corner - head end",
        offset=(offsets[6], 0.0),
      ),
      anchor_to_target(
        a_from_b(n - 399),
        b_pin(n - 399),
        "Top B corner - head end",
        offset=(offsets[7], 0.0),
        hover=True,
      ),
      _line("~increment(0," + _coord("", -pull_ins["Y_PULL_IN"]) + ")"),
    ]
  )
  if _near_comb(_wrap_pin_number(n - 399)):
    lines.append(
      _line(
        "~increment(" + _coord("", (pull_ins["Y_PULL_IN"] * COMB_PULL_FACTOR)) + ",0)",
        "(comb pull)",
      )
    )
  lines.extend(
    [
      anchor_to_target(
        b_pin(1 - 399 + n),
        b_pin(1200 - n),
        "Bottom B corner - foot end",
        offset=(0.0, offsets[8]),
      ),
      anchor_to_target(
        b_pin(1200 - n),
        a_from_b(1200 - n),
        "Bottom A corner - foot end",
        offset=(0.0, offsets[9]),
        hover=True,
      ),
      _line("~increment(0," + _coord("", pull_ins["Y_PULL_IN"]) + ")"),
    ]
  )
  if _near_comb(_wrap_pin_number(1200 - n)):
    lines.append(
      _line(
        "~increment(" + _coord("", (pull_ins["Y_PULL_IN"] * COMB_PULL_FACTOR)) + ",0)",
        "(comb pull)",
      )
    )
  lines.append(
    anchor_to_target(
      a_from_b(1200 - n),
      a_from_b(1201 + n + 1),
      "Foot A corner",
      offset=(0.0, offsets[10]),
    )
  )
  return _annotate_wrap_lines(wrap_number, lines)


def render_u_template_lines(
  *,
  offsets=None,
  transfer_pause=False,
  add_foot_pauses=False,
  include_lead_mode=False,
  strip_g113_params=False,
  script_variant=SCRIPT_VARIANT_DEFAULT,
  named_inputs=None,
  special_inputs=None,
  cell_overrides=None,
):
  (
    resolved_offsets,
    transfer_pause_value,
    add_foot_pauses_value,
    include_lead_mode_value,
    pull_ins,
  ) = _resolve_render_state(
    offsets=offsets,
    transfer_pause=transfer_pause,
    add_foot_pauses=add_foot_pauses,
    include_lead_mode=include_lead_mode,
    named_inputs=named_inputs,
    special_inputs=special_inputs,
    cell_overrides=cell_overrides,
  )
  script_variant = _normalize_script_variant(script_variant)

  if script_variant == SCRIPT_VARIANT_WRAPPING:
    final_anchor_pin = b_to_a_pin("U", "B1601")
    lines = [
      "( U Layer )",
      _line("~goto(" + _coord("", PREAMBLE_X) + ",0)"),
    ]
    for wrap_number in range(1, WRAP_COUNT + 1):
      lines.extend(_render_wrapping_wrap_lines(wrap_number, pull_ins, resolved_offsets))
    lines.extend(
      [
        _line("~anchorToTarget(" + final_anchor_pin + ",B1601)"),
        _line("~increment(" + _coord("", pull_ins["X_PULL_IN"]) + ",0)"),
      ]
    )
  else:
    lines = [
      "( U Layer )",
      _line(
        "G113 PPRECISE",
        _coord("X", PREAMBLE_X),
        _coord("Y", PREAMBLE_Y),
        "F300",
        "(load new calibration file)",
      ),
      _line("F300", _g106(3)),
      _line(
        "G113 PPRECISE",
        "(0, )",
        "F300",
        "G103",
        "PB1201",
        "PB1200",
        "PXY",
        "G105 " + _coord("PX", PREAMBLE_BOARD_GAP_PULL),
      ),
    ]

    for wrap_number in range(1, WRAP_COUNT + 1):
      lines.extend(
        _render_wrap_lines(
          wrap_number,
          resolved_offsets,
          transfer_pause_value,
          include_lead_mode_value,
          pull_ins,
        )
      )

  if add_foot_pauses_value:
    lines = _apply_add_foot_pauses(lines)

  lines = _number_lines(lines)
  if strip_g113_params:
    lines = _apply_strip_g113_params(lines)
  return lines


def render_u_template_text_lines(
  cell_overrides=None,
  *,
  add_foot_pauses=False,
  script_variant=SCRIPT_VARIANT_DEFAULT,
  named_inputs=None,
  special_inputs=None,
):
  return render_u_template_lines(
    add_foot_pauses=add_foot_pauses,
    script_variant=script_variant,
    named_inputs=named_inputs,
    special_inputs=special_inputs,
    cell_overrides=cell_overrides,
  )


# Legacy compatibility wrappers that preserve spreadsheet-era symbol names.
def render_u_template_ac_lines(
  cell_overrides=None,
  *,
  add_foot_pauses=False,
  named_inputs=None,
  sheet_path=None,
  special_inputs=None,
):
  _ = sheet_path
  return render_u_template_text_lines(
    add_foot_pauses=add_foot_pauses,
    cell_overrides=cell_overrides,
    named_inputs=named_inputs,
    special_inputs=special_inputs,
  )


def render_default_u_template_text_lines(workbook_path=None):
  _ = workbook_path
  return render_u_template_text_lines()


def read_cached_u_template_ac_lines(workbook_path=None):
  _ = workbook_path
  return render_default_u_template_text_lines()


def get_u_template_named_inputs_snapshot(sheet_path=None):
  _ = sheet_path
  return UTemplateProgrammaticGenerator().get_named_inputs()


def read_u_template_named_inputs(sheet_path=None):
  _ = sheet_path
  return get_u_template_named_inputs_snapshot()


def get_u_recipe_description():
  return "U-layer"


def get_u_recipe_file_name():
  return "U-layer.gc"


def write_u_template_text_file(
  output_path,
  cell_overrides=None,
  *,
  add_foot_pauses=False,
  script_variant=SCRIPT_VARIANT_DEFAULT,
  named_inputs=None,
  special_inputs=None,
):
  output = Path(output_path)
  lines = render_u_template_text_lines(
    add_foot_pauses=add_foot_pauses,
    script_variant=script_variant,
    cell_overrides=cell_overrides,
    named_inputs=named_inputs,
    special_inputs=special_inputs,
  )
  output.write_text("\n".join(lines) + "\n", encoding="utf-8")
  return output


def write_u_template_ac_file(
  output_path,
  cell_overrides=None,
  *,
  add_foot_pauses=False,
  named_inputs=None,
  sheet_path=None,
  special_inputs=None,
):
  _ = sheet_path
  return write_u_template_text_file(
    output_path,
    cell_overrides=cell_overrides,
    add_foot_pauses=add_foot_pauses,
    named_inputs=named_inputs,
    special_inputs=special_inputs,
  )


def write_u_template_file(
  output_path,
  *,
  offsets=None,
  transfer_pause=False,
  add_foot_pauses=False,
  include_lead_mode=False,
  strip_g113_params=False,
  script_variant=SCRIPT_VARIANT_DEFAULT,
  named_inputs=None,
  special_inputs=None,
  archive_directory=None,
  parent_hash=None,
):
  resolved_script_variant = _normalize_script_variant(script_variant)
  (
    resolved_offsets,
    resolved_transfer_pause,
    resolved_add_foot_pauses,
    resolved_include_lead_mode,
    resolved_pull_ins,
  ) = _resolve_render_state(
    offsets=offsets,
    transfer_pause=transfer_pause,
    add_foot_pauses=add_foot_pauses,
    include_lead_mode=include_lead_mode,
    named_inputs=named_inputs,
    special_inputs=special_inputs,
  )
  lines = render_u_template_lines(
    offsets=offsets,
    transfer_pause=transfer_pause,
    add_foot_pauses=add_foot_pauses,
    include_lead_mode=include_lead_mode,
    strip_g113_params=strip_g113_params,
    script_variant=resolved_script_variant,
    named_inputs=named_inputs,
    special_inputs=special_inputs,
  )
  hash_value = Recipe.writeGeneratedFile(
    output_path,
    get_u_recipe_description(),
    lines,
    archiveDirectory=archive_directory,
    parentHash=parent_hash,
  )
  return {
    "description": get_u_recipe_description(),
    "fileName": get_u_recipe_file_name(),
    "hashValue": hash_value,
    "lines": lines,
    "offsets": list(resolved_offsets),
    "transferPause": resolved_transfer_pause,
    "addFootPauses": resolved_add_foot_pauses,
    "includeLeadMode": resolved_include_lead_mode,
    "pullIns": dict(resolved_pull_ins),
    "scriptVariant": resolved_script_variant,
    "wrapCount": WRAP_COUNT,
  }


class UTemplateProgrammaticGenerator:
  def __init__(
    self,
    sheet_path=None,
    *,
    named_inputs=None,
    cell_overrides=None,
    special_inputs=None,
  ):
    _ = sheet_path
    (
      self.offsets,
      self.transfer_pause,
      self.add_foot_pauses,
      self.include_lead_mode,
      self.pull_ins,
    ) = _resolve_options(
      named_inputs=named_inputs,
      special_inputs=special_inputs,
      cell_overrides=cell_overrides,
    )
    self._lines = render_u_template_lines(
      offsets=self.offsets,
      transfer_pause=self.transfer_pause,
      add_foot_pauses=self.add_foot_pauses,
      include_lead_mode=self.include_lead_mode,
      named_inputs=self.pull_ins,
    )

  def render_lines(self):
    return list(self._lines)

  def render_column_lines(self, column_label):
    if str(column_label).upper() != "AC":
      raise UTemplateInputError(
        "Only AC compatibility output is available for UTemplateGCode."
      )
    return self.render_lines()

  def get_named_inputs(self):
    values = {
      "transferPause": self.transfer_pause,
      "pause at combs": self.transfer_pause,
      "addFootPauses": self.add_foot_pauses,
      "add foot pauses": self.add_foot_pauses,
      "includeLeadMode": self.include_lead_mode,
      "include lead mode": self.include_lead_mode,
      "Y_PULL_IN": self.pull_ins["Y_PULL_IN"],
      "X_PULL_IN": self.pull_ins["X_PULL_IN"],
      "y_pull_in": self.pull_ins["Y_PULL_IN"],
      "x_pull_in": self.pull_ins["X_PULL_IN"],
    }
    for index, offset_id in enumerate(OFFSET_IDS):
      values[offset_id] = self.offsets[index]
      values[offset_id + "_offset"] = self.offsets[index]
    for legacy_name, index in LEGACY_OFFSET_NAMES.items():
      values[legacy_name] = self.offsets[index]
    for alias_name, index in SPECIAL_OFFSET_ALIASES.items():
      values[alias_name] = self.offsets[index]
    return values

  def get_value(self, column_label, row_number):
    if str(column_label).upper() != "AC":
      return ""
    if row_number < 1 or row_number > len(self._lines):
      return ""
    return self._lines[row_number - 1]


# Backward-compatible class alias.
UTemplateGCodeGenerator = UTemplateProgrammaticGenerator


def _coerce_cli_value(value):
  return template_gcode_common.coerce_cli_value(
    value,
    coerce_bool_fn=_coerce_bool,
    coerce_number_fn=_coerce_number,
    input_error_type=UTemplateInputError,
  )


def _parse_assignment(raw_assignment):
  return template_gcode_common.parse_assignment(
    raw_assignment,
    coerce_cli_value_fn=_coerce_cli_value,
    input_error_type=UTemplateInputError,
  )


def main(argv=None):
  parser = argparse.ArgumentParser(
    description="Render U-layer G-Code from the programmatic specification."
  )
  parser.add_argument("output", help="Path to the text or recipe file to write.")
  parser.add_argument(
    "--sheet",
    default=None,
    help="Compatibility option. Ignored because the U generator is programmatic.",
  )
  parser.add_argument(
    "--set",
    dest="assignments",
    action="append",
    default=[],
    help="Compatibility option for the removed spreadsheet path. Unsupported.",
  )
  parser.add_argument(
    "--named-set",
    dest="named_assignments",
    action="append",
    default=[],
    help="Named U input override in KEY=VALUE form.",
  )
  parser.add_argument(
    "--special",
    dest="special_assignments",
    action="append",
    default=[],
    help="Special U input override in KEY=VALUE form.",
  )
  parser.add_argument(
    "--offsets",
    help="Comma-separated list of the 12 line offsets.",
  )
  parser.add_argument(
    "--transfer-pause",
    action="store_true",
    help="Insert the optional transfer pause lines.",
  )
  parser.add_argument(
    "--include-lead-mode",
    action="store_true",
    help="Include lead-mode G106 lines during transfer sequences.",
  )
  parser.add_argument(
    "--recipe",
    action="store_true",
    help="Write a hashed recipe file with the standard recipe header.",
  )
  args = parser.parse_args(argv)

  if args.assignments:
    raise UTemplateInputError(
      "Cell overrides are not supported by the programmatic U generator."
    )

  named_inputs = dict(
    _parse_assignment(assignment) for assignment in args.named_assignments
  )
  special_inputs = dict(
    _parse_assignment(assignment) for assignment in args.special_assignments
  )

  if args.offsets:
    special_inputs["offsets"] = args.offsets
  if args.transfer_pause:
    special_inputs["transferPause"] = True
  if args.include_lead_mode:
    special_inputs["includeLeadMode"] = True

  if args.recipe:
    write_u_template_file(
      args.output,
      named_inputs=named_inputs,
      special_inputs=special_inputs,
    )
  else:
    write_u_template_text_file(
      args.output,
      named_inputs=named_inputs,
      special_inputs=special_inputs,
    )
  return 0


DEFAULT_U_TEMPLATE_ROW_COUNT = len(render_u_template_text_lines())


if __name__ == "__main__":
  raise SystemExit(main())
