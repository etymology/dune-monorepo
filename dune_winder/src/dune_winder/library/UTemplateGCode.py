###############################################################################
# Name: UTemplateGCode.py
# Uses: Generate U-layer G-Code from the programmatic specification.
# Date: 2026-03-04
###############################################################################

from __future__ import annotations

import argparse
import re
from pathlib import Path

from dune_winder.library.RecipeTemplateLanguage import (
  compile_template_script,
  execute_template_script,
)
from dune_winder.library.Recipe import Recipe
from dune_winder.library.TemplateGCodeTransitions import (
  append_motion_to_pause_transition,
  append_pause_to_motion_transition,
  g106_line,
)


WRAP_COUNT = 400
Y_PULL_IN = 60.0
X_PULL_IN = 70.0
COMB_PULL_FACTOR = 3.0
PREAMBLE_X = 7174.0
PREAMBLE_Y = 60.0
PREAMBLE_BOARD_GAP_PULL = -50.0
COMBS = (592, 740, 888, 1043, 1191, 1754, 1902, 2050, 2198)
PIN_MIN = 1
PIN_MAX = 2401
PIN_SPAN = PIN_MAX - PIN_MIN + 1
DEFAULT_OFFSETS = (0.0,) * 12
DEFAULT_U_TEMPLATE_WORKBOOK = None
DEFAULT_U_TEMPLATE_SHEET = None

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

U_WRAP_SCRIPT = compile_template_script(
  (
    "emit (------------------STARTING LOOP ${wrap}------------------)",
    "emit G109 PB${1200 + wrap} PBR G103 PB${2002 - wrap} PB${2003 - wrap} PXY ${offset('PX', offsets[0])} G102 G108 (Top B corner - foot end)",
    "transition transfer_b_to_a",
    "emit G109 PB${1200 + wrap} PLT G103 PB${2002 - wrap} PB${2003 - wrap} PXY ${conditional_offset('PX', offsets[1], 12 + offsets[1])} (Top A corner - foot end)",
    "emit G103 PF${800 + wrap} PF${801 + wrap} PY G105 ${coord('PY', -Y_PULL_IN)}",
    "if near_comb(799 + wrap): emit G103 PF${800 + wrap} PF${801 + wrap} PX G105 ${coord('PX-', Y_PULL_IN * COMB_PULL_FACTOR)}",
    "emit G109 PF${800 + wrap} PLB G103 PF${2402 - wrap} PF${2403 - wrap} PXY ${offset('PY', offsets[2])} G102 G108 (Bottom A corner - head end)",
    "transition transfer_a_to_b",
    "emit G109 PF${2402 - wrap} PBR G103 PB${400 + wrap} PB${401 + wrap} PXY ${offset('PY', offsets[3])} (Bottom B corner - head end, rewind)",
    "emit G103 PB${400 + wrap} PB${401 + wrap} PX G105 ${coord('PY', Y_PULL_IN)}",
    "emit (HEAD RESTART) G109 PB${400 + wrap} PLT G103 PB${401 - wrap} PB${400 - wrap} PXY ${offset('PY', offsets[4])} G102 G108 (Head B corner)",
    "transition transfer_b_to_a",
    "emit G109 PB${401 - wrap} PLT G103 PF${wrap} PF${2400 + wrap} PXY ${offset('PY', offsets[5])} (Head A corner, rewind)",
    "emit G103 PF${1 + wrap} PF${wrap} PY G105 ${coord('PX', X_PULL_IN)} ( BOARD GAP )",
    "emit G109 PF${1 + wrap} PRT G103 PF${800 - wrap} PF${799 - wrap} PXY ${offset('PX', offsets[6])} G102 G108 (Top A corner - head end)",
    "transition transfer_a_to_b",
    "emit G109 PF${800 - wrap} PRT G103 PB${2002 + wrap} PB${2003 + wrap} PXY ${conditional_offset('PX', offsets[7], offsets[7] - 12)} (Top B corner - head end)",
    "emit G103 PB${2002 + wrap} PB${2003 + wrap} PY G105 ${coord('PY', -Y_PULL_IN)}",
    "if near_comb(1999 + wrap): emit G103 PB${2002 + wrap} PB${2003 + wrap} PX G105 ${coord('PX', Y_PULL_IN * COMB_PULL_FACTOR)}",
    "emit G109 PB${2001 + wrap} PRB G103 PB${1201 - wrap} PB${1202 - wrap} PXY ${offset('PY', offsets[8])} G102 G108 (Bottom B corner - foot end)",
    "transition transfer_b_to_a",
    "emit G109 PB${1199 + wrap} PBL G103 PF${1601 + wrap} PF${1602 + wrap} PXY ${offset('PY', offsets[9])} (Bottom A corner - foot end, rewind)",
    "emit G103 PF${1601 + wrap} PF${1602 + wrap} PY G105 ${coord('PY', Y_PULL_IN)}",
    "if near_comb(1601 + wrap): emit G103 PF${1601 + wrap} PF${1602 + wrap} PX G105 ${coord('PX', X_PULL_IN * COMB_PULL_FACTOR)}",
    "emit G109 PF${1601 + wrap} PRT G103 PF${1601 - wrap} PF${1600 - wrap} PXY ${offset('PY', offsets[10])} G102 G108 (Foot A corner)",
    "transition transfer_a_to_b",
    "emit G109 PF${1601 - wrap} PRT G103 PB${1201 + wrap} PB${1200 + wrap} PXY ${offset('PY', offsets[11])} (Foot B corner, rewind)",
    "emit G103 PB${1201 + wrap} PB${1200 + wrap} PX G105 ${coord('PX', -X_PULL_IN)}",
  )
)


class UTemplateInputError(ValueError):
  pass


_PIN_TOKEN_RE = re.compile(r"\b(P[BF])(-?\d+)\b")


def _format_number(value):
  text = "{0:.6f}".format(float(value)).rstrip("0").rstrip(".")
  if text in ("", "-0"):
    return "0"
  return text


def _wrap_pin_number(value):
  pin_number = int(value)
  return ((pin_number - PIN_MIN) % PIN_SPAN) + PIN_MIN


def _normalize_pin_tokens(text):
  def replace(match):
    return match.group(1) + str(_wrap_pin_number(match.group(2)))

  return _PIN_TOKEN_RE.sub(replace, text)


def _line(*parts):
  return _normalize_pin_tokens(
    " ".join(str(part) for part in parts if part not in (None, ""))
  )


def _coord(axis, value):
  return axis + _format_number(value)


def _offset_fragment(axis, value):
  if abs(float(value)) < 1e-9:
    return None
  return "G105 " + _coord(axis, value)


def _g106(mode):
  return g106_line(_line, mode)


def _conditional_offset_fragment(axis, condition_value, rendered_value):
  if abs(float(condition_value)) < 1e-9:
    return None
  return "G105 " + _coord(axis, rendered_value)


def _near_comb(pin_number):
  return any(abs(int(pin_number) - comb_pin) <= 5 for comb_pin in COMBS)


def _coerce_bool(value):
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
  raise UTemplateInputError("Expected a boolean-compatible value, got " + repr(value) + ".")


def _coerce_number(value):
  if isinstance(value, bool):
    raise UTemplateInputError("Boolean values are not valid offsets.")
  if isinstance(value, (int, float)):
    return float(value)
  if isinstance(value, str):
    try:
      return float(value.strip())
    except ValueError as exc:
      raise UTemplateInputError("Expected a numeric value, got " + repr(value) + ".") from exc
  raise UTemplateInputError("Expected a numeric value, got " + type(value).__name__ + ".")


def _coerce_offsets(value):
  if value is None:
    return list(DEFAULT_OFFSETS)
  if isinstance(value, str):
    raw_values = [part.strip() for part in value.split(",")]
  else:
    try:
      raw_values = list(value)
    except TypeError as exc:
      raise UTemplateInputError("Offsets must be a 12-item iterable.") from exc
  if len(raw_values) != len(OFFSET_IDS):
    raise UTemplateInputError("Expected 12 U offsets, got " + str(len(raw_values)) + ".")
  return [_coerce_number(item) for item in raw_values]


def _apply_named_input(named_inputs, offsets, transfer_pause, include_lead_mode):
  current_transfer_pause = transfer_pause
  current_include_lead_mode = include_lead_mode
  for key, value in (named_inputs or {}).items():
    if key == "transferPause" or key == "pause at combs":
      current_transfer_pause = _coerce_bool(value)
      continue
    if key in ("includeLeadMode", "include lead mode"):
      current_include_lead_mode = _coerce_bool(value)
      continue
    if key in LEGACY_OFFSET_NAMES:
      offsets[LEGACY_OFFSET_NAMES[key]] = _coerce_number(value)
      continue
    if key in OFFSET_IDS:
      offsets[OFFSET_IDS.index(key)] = _coerce_number(value)
      continue
    if key.endswith("_offset") and key[:-7] in OFFSET_IDS:
      offsets[OFFSET_IDS.index(key[:-7])] = _coerce_number(value)
      continue
    raise UTemplateInputError("Unknown U named input: " + repr(key))
  return current_transfer_pause, current_include_lead_mode


def _apply_special_input(special_inputs, offsets, transfer_pause, include_lead_mode):
  current_transfer_pause = transfer_pause
  current_include_lead_mode = include_lead_mode
  for key, value in (special_inputs or {}).items():
    if key in ("transferPause", "transfer_pause", "pause_at_combs"):
      current_transfer_pause = _coerce_bool(value)
      continue
    if key in ("includeLeadMode", "include_lead_mode", "include_lead"):
      current_include_lead_mode = _coerce_bool(value)
      continue
    if key == "offsets":
      parsed_offsets = _coerce_offsets(value)
      for index, offset in enumerate(parsed_offsets):
        offsets[index] = offset
      continue
    if key in SPECIAL_OFFSET_ALIASES:
      offsets[SPECIAL_OFFSET_ALIASES[key]] = _coerce_number(value)
      continue
    if key in OFFSET_IDS:
      offsets[OFFSET_IDS.index(key)] = _coerce_number(value)
      continue
    if key.endswith("_offset") and key[:-7] in OFFSET_IDS:
      offsets[OFFSET_IDS.index(key[:-7])] = _coerce_number(value)
      continue
    raise UTemplateInputError("Unknown U special input: " + repr(key))
  return current_transfer_pause, current_include_lead_mode


def _resolve_options(named_inputs=None, special_inputs=None, cell_overrides=None):
  if cell_overrides:
    raise UTemplateInputError(
      "Cell overrides are not supported by the programmatic U generator."
    )

  offsets = list(DEFAULT_OFFSETS)
  transfer_pause = False
  include_lead_mode = False
  transfer_pause, include_lead_mode = _apply_named_input(
    named_inputs,
    offsets,
    transfer_pause,
    include_lead_mode,
  )
  transfer_pause, include_lead_mode = _apply_special_input(
    special_inputs,
    offsets,
    transfer_pause,
    include_lead_mode,
  )
  return offsets, transfer_pause, include_lead_mode


def _resolve_render_state(
  *,
  offsets=None,
  transfer_pause=False,
  include_lead_mode=False,
  named_inputs=None,
  special_inputs=None,
  cell_overrides=None,
):
  if offsets is None:
    resolved_offsets, resolved_transfer_pause, resolved_include_lead_mode = _resolve_options(
      named_inputs=named_inputs,
      special_inputs=special_inputs,
      cell_overrides=cell_overrides,
    )
    return (
      resolved_offsets,
      (_coerce_bool(transfer_pause) or resolved_transfer_pause),
      (_coerce_bool(include_lead_mode) or resolved_include_lead_mode),
    )

  resolved_offsets, resolved_transfer_pause, resolved_include_lead_mode = _resolve_options(
    named_inputs=named_inputs,
    special_inputs=special_inputs,
    cell_overrides=cell_overrides,
  )
  for index, value in enumerate(_coerce_offsets(offsets)):
    resolved_offsets[index] = value
  return (
    resolved_offsets,
    (_coerce_bool(transfer_pause) or resolved_transfer_pause),
    (_coerce_bool(include_lead_mode) or resolved_include_lead_mode),
  )


def _wrap_identifier(wrap_number, line_number):
  return "(" + str(wrap_number) + "," + str(line_number) + ")"


def _annotate_wrap_lines(wrap_number, lines):
  return [
    _line(_wrap_identifier(wrap_number, line_number), line)
    for line_number, line in enumerate(lines, start=1)
  ]


def _number_lines(lines):
  return [_line("N" + str(line_number), line) for line_number, line in enumerate(lines)]


def _render_wrap_lines(wrap_number, offsets, transfer_pause, include_lead_mode):
  lines = []

  transitions = {
    "transfer_b_to_a": lambda output: append_pause_to_motion_transition(
      output,
      line_builder=_line,
      transfer_pause=transfer_pause,
      include_lead_mode=include_lead_mode,
    ),
    "transfer_a_to_b": lambda output: append_motion_to_pause_transition(
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
    "Y_PULL_IN": Y_PULL_IN,
    "X_PULL_IN": X_PULL_IN,
    "COMB_PULL_FACTOR": COMB_PULL_FACTOR,
  }

  execute_template_script(
    U_WRAP_SCRIPT,
    environment=environment,
    output_lines=lines,
    line_builder=_line,
    transitions=transitions,
  )

  return _annotate_wrap_lines(wrap_number, lines)


def render_u_template_lines(
  *,
  offsets=None,
  transfer_pause=False,
  include_lead_mode=False,
  named_inputs=None,
  special_inputs=None,
  cell_overrides=None,
):
  resolved_offsets, transfer_pause_value, include_lead_mode_value = _resolve_render_state(
    offsets=offsets,
    transfer_pause=transfer_pause,
    include_lead_mode=include_lead_mode,
    named_inputs=named_inputs,
    special_inputs=special_inputs,
    cell_overrides=cell_overrides,
  )

  lines = [
    "( U Layer )",
    _line(
      _coord("X", PREAMBLE_X),
      _coord("Y", PREAMBLE_Y),
      "F300",
      "(load new calibration file)",
    ),
    _line("F300", _g106(3)),
    _line(
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
      )
    )

  return _number_lines(lines)


def render_u_template_text_lines(
  cell_overrides=None,
  *,
  named_inputs=None,
  special_inputs=None,
):
  return render_u_template_lines(
    named_inputs=named_inputs,
    special_inputs=special_inputs,
    cell_overrides=cell_overrides,
  )


# Legacy compatibility wrappers that preserve spreadsheet-era symbol names.
def render_u_template_ac_lines(
  cell_overrides=None,
  *,
  named_inputs=None,
  sheet_path=None,
  special_inputs=None,
):
  _ = sheet_path
  return render_u_template_text_lines(
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
  named_inputs=None,
  special_inputs=None,
):
  output = Path(output_path)
  lines = render_u_template_text_lines(
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
  named_inputs=None,
  sheet_path=None,
  special_inputs=None,
):
  _ = sheet_path
  return write_u_template_text_file(
    output_path,
    cell_overrides=cell_overrides,
    named_inputs=named_inputs,
    special_inputs=special_inputs,
  )


def write_u_template_file(
  output_path,
  *,
  offsets=None,
  transfer_pause=False,
  include_lead_mode=False,
  named_inputs=None,
  special_inputs=None,
  archive_directory=None,
  parent_hash=None,
):
  resolved_offsets, resolved_transfer_pause, resolved_include_lead_mode = _resolve_render_state(
    offsets=offsets,
    transfer_pause=transfer_pause,
    include_lead_mode=include_lead_mode,
    named_inputs=named_inputs,
    special_inputs=special_inputs,
  )
  lines = render_u_template_lines(
    offsets=offsets,
    transfer_pause=transfer_pause,
    include_lead_mode=include_lead_mode,
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
    "includeLeadMode": resolved_include_lead_mode,
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
    self.offsets, self.transfer_pause, self.include_lead_mode = _resolve_options(
      named_inputs=named_inputs,
      special_inputs=special_inputs,
      cell_overrides=cell_overrides,
    )
    self._lines = render_u_template_lines(
      offsets=self.offsets,
      transfer_pause=self.transfer_pause,
      include_lead_mode=self.include_lead_mode,
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
      "includeLeadMode": self.include_lead_mode,
      "include lead mode": self.include_lead_mode,
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
  normalized = value.strip()
  if "," in normalized:
    return [part.strip() for part in normalized.split(",")]
  if normalized.lower() in ("true", "false", "yes", "no", "on", "off"):
    return _coerce_bool(normalized)
  try:
    return _coerce_number(normalized)
  except UTemplateInputError:
    return normalized


def _parse_assignment(raw_assignment):
  if "=" not in raw_assignment:
    raise UTemplateInputError(
      "Expected KEY=VALUE assignment, got " + repr(raw_assignment) + "."
    )
  key, value = raw_assignment.split("=", 1)
  return key.strip(), _coerce_cli_value(value)


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
    help="Include lead-mode G106 lines during transition sequences.",
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

  named_inputs = dict(_parse_assignment(assignment) for assignment in args.named_assignments)
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
