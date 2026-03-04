###############################################################################
# Name: VTemplateGCode.py
# Uses: Generate V-layer G-Code from the programmatic specification.
# Date: 2026-03-03
###############################################################################

from __future__ import annotations

import argparse
import re
from pathlib import Path

from dune_winder.library.Recipe import Recipe


WRAP_COUNT = 400
PRE_FINAL_WRAP_COUNT = WRAP_COUNT - 1
Y_PULL_IN = 60.0
X_PULL_IN = 70.0
COMB_PULL_FACTOR = 3.0
PREAMBLE_BOARD_GAP_PULL = 30.0
COMBS = (592, 740, 888, 1043, 1191, 1754, 1902, 2050, 2198)
PIN_MIN = 1
PIN_MAX = 2400
PIN_SPAN = PIN_MAX - PIN_MIN + 1
DEFAULT_OFFSETS = (0.0,) * 12
DEFAULT_V_TEMPLATE_WORKBOOK = None
DEFAULT_V_TEMPLATE_SHEET = None

OFFSET_IDS = (
  "top_b_foot_end",
  "top_a_foot_end",
  "foot_a_corner",
  "foot_b_corner",
  "bottom_b_foot_end",
  "bottom_a_foot_end",
  "top_a_head_end",
  "top_b_head_end",
  "head_b_corner",
  "head_a_corner",
  "bottom_a_head_end",
  "bottom_b_head_end",
)

LEGACY_OFFSET_NAMES = {
  "line 1 (Top B corner - foot end)": 0,
  "line 2 (Top A corner - foot end)": 1,
  "line 3 (Foot A corner)": 2,
  "line 4 (Foot B corner)": 3,
  "line 5 (Bottom B corner - foot end)": 4,
  "line 6 (Bottom A corner - foot end)": 5,
  "line 7 (Top A corner - head end)": 6,
  "line 8 (Top B corner - head end)": 7,
  "line 9 (Head B corner)": 8,
  "line 10 (Head A corner)": 9,
  "line 11 (Bottom A corner - head end)": 10,
  "line 12 (Bottom B corner - head end)": 11,
}

SPECIAL_OFFSET_ALIASES = {
  "foot_a_offset": 2,
  "foot_b_offset": 3,
  "head_b_offset": 8,
  "head_a_offset": 9,
}


class VTemplateInputError(ValueError):
  pass


_PIN_TOKEN_RE = re.compile(r"\b(P[BF])(-?\d+)\b")


def _format_number(value):
  text = "{0:.6f}".format(float(value)).rstrip("0").rstrip(".")
  if text in ("", "-0"):
    return "0"
  return text


def _wrap_pin_number(value):
  pin_number = int(value)
  if pin_number < PIN_MIN:
    return PIN_MAX
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
  raise VTemplateInputError("Expected a boolean-compatible value, got " + repr(value) + ".")


def _coerce_number(value):
  if isinstance(value, bool):
    raise VTemplateInputError("Boolean values are not valid offsets.")
  if isinstance(value, (int, float)):
    return float(value)
  if isinstance(value, str):
    try:
      return float(value.strip())
    except ValueError as exc:
      raise VTemplateInputError("Expected a numeric value, got " + repr(value) + ".") from exc
  raise VTemplateInputError("Expected a numeric value, got " + type(value).__name__ + ".")


def _coerce_offsets(value):
  if value is None:
    return list(DEFAULT_OFFSETS)
  if isinstance(value, str):
    raw_values = [part.strip() for part in value.split(",")]
  else:
    try:
      raw_values = list(value)
    except TypeError as exc:
      raise VTemplateInputError("Offsets must be a 12-item iterable.") from exc
  if len(raw_values) != len(OFFSET_IDS):
    raise VTemplateInputError("Expected 12 V offsets, got " + str(len(raw_values)) + ".")
  return [_coerce_number(item) for item in raw_values]


def _apply_named_input(named_inputs, offsets, transfer_pause):
  current_transfer_pause = transfer_pause
  for key, value in (named_inputs or {}).items():
    if key == "transferPause" or key == "pause at combs":
      current_transfer_pause = _coerce_bool(value)
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
    raise VTemplateInputError("Unknown V named input: " + repr(key))
  return current_transfer_pause


def _apply_special_input(special_inputs, offsets, transfer_pause):
  current_transfer_pause = transfer_pause
  for key, value in (special_inputs or {}).items():
    if key in ("transferPause", "transfer_pause", "pause_at_combs"):
      current_transfer_pause = _coerce_bool(value)
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
    raise VTemplateInputError("Unknown V special input: " + repr(key))
  return current_transfer_pause


def _resolve_options(named_inputs=None, special_inputs=None, cell_overrides=None):
  if cell_overrides:
    raise VTemplateInputError(
      "Cell overrides are not supported by the programmatic V generator."
    )

  offsets = list(DEFAULT_OFFSETS)
  transfer_pause = False
  transfer_pause = _apply_named_input(named_inputs, offsets, transfer_pause)
  transfer_pause = _apply_special_input(special_inputs, offsets, transfer_pause)
  return offsets, transfer_pause


def _resolve_render_state(
  *,
  offsets=None,
  transfer_pause=False,
  named_inputs=None,
  special_inputs=None,
  cell_overrides=None,
):
  if offsets is None:
    return _resolve_options(
      named_inputs=named_inputs,
      special_inputs=special_inputs,
      cell_overrides=cell_overrides,
    )

  resolved_offsets, resolved_transfer_pause = _resolve_options(
    named_inputs=named_inputs,
    special_inputs=special_inputs,
    cell_overrides=cell_overrides,
  )
  for index, value in enumerate(_coerce_offsets(offsets)):
    resolved_offsets[index] = value
  return resolved_offsets, (_coerce_bool(transfer_pause) or resolved_transfer_pause)


def _loop_intro_line(wrap_number, offsets):
  return _line(
    "G109",
    "PB" + str(399 + wrap_number),
    "PRT",
    "G103",
    "PB" + str(1999 - wrap_number),
    "PB" + str(2000 - wrap_number),
    "PXY",
    _offset_fragment("PX", offsets[0]),
    "G102",
    "G108",
    "(Top B corner - foot end)",
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


def _render_wrap_lines(wrap_number, offsets, transfer_pause, final_wrap=False):
  lines = [
    "(------------------STARTING LOOP " + str(wrap_number) + "------------------)",
    _loop_intro_line(wrap_number, offsets),
    "G106 P3",
  ]

  if transfer_pause:
    lines.append("G106 P2")

  lines.extend(
    [
      "G106 P0",
      _line(
        "G109",
        "PB" + str(2000 - wrap_number),
        "PLT",
        "G103",
        "PF" + str(799 + wrap_number),
        "PF" + str(798 + wrap_number),
        "PX",
        _offset_fragment("PX", offsets[1]),
        "(Top A corner - foot end)",
      ),
      _line(
        "G103",
        "PF" + str(799 + wrap_number),
        "PF" + str(798 + wrap_number),
        "PY",
        "G105 " + _coord("PY", -Y_PULL_IN),
      ),
    ]
  )

  if _near_comb(799 + wrap_number):
    lines.append(
      _line(
        "G103",
        "PF" + str(799 + wrap_number),
        "PF" + str(798 + wrap_number),
        "PX",
        "G105 " + _coord("PX", Y_PULL_IN * COMB_PULL_FACTOR),
      )
    )

  lines.extend(
    [
      _line(
        "G109",
        "PF" + str(799 + wrap_number),
        "PRB",
        "G103",
        "PF" + str(1601 - wrap_number),
        "PF" + str(1600 - wrap_number),
        "PXY",
        _offset_fragment("PY", offsets[2]),
        "G102",
        "G108",
        "( BOARD GAP )",
        "(Foot A corner)",
      ),
      "G106 P0",
    ]
  )

  if transfer_pause:
    lines.append("G106 P1")

  lines.extend(
    [
      "G106 P3",
      _line(
        "G109",
        "PF" + str(1600 - wrap_number),
        "PBL",
        "G103",
        "PB" + str(1199 + wrap_number),
        "PB" + str(1200 + wrap_number),
        "PY",
        _offset_fragment("PY", offsets[3]),
        "(Foot B corner)",
      ),
      _line(
        "G103",
        "PB" + str(1199 + wrap_number),
        "PB" + str(1200 + wrap_number),
        "PX",
        "G105 " + _coord("PX", -X_PULL_IN),
      ),
      _line(
        "G109",
        "PB" + str(1199 + wrap_number),
        "PTR",
        "G103",
        "PB" + str(1200 - wrap_number),
        "PB" + str(1199 - wrap_number),
        "PXY",
        _offset_fragment("PX", offsets[4]),
        "G102",
        "G108",
        "(Bottom B corner - foot end)",
      ),
      "G106 P3",
    ]
  )

  if transfer_pause:
    lines.append("G106 P2")

  lines.extend(
    [
      "G106 P0",
      _line(
        "G109",
        "PB" + str(1200 - wrap_number),
        "PBR",
        "G103",
        "PF" + str(1598 + wrap_number),
        "PF" + str(1599 + wrap_number),
        "PX",
        _offset_fragment("PX", offsets[5]),
        "(Bottom A corner - foot end)",
      ),
      _line(
        "G103",
        "PF" + str(1598 + wrap_number),
        "PF" + str(1599 + wrap_number),
        "PY",
        "G105 " + _coord("PY", Y_PULL_IN),
        "( BOARD GAP )",
      ),
      _line(
        "G109",
        "PF" + str(1599 + wrap_number),
        "PLT",
        "G103",
        "PF" + str(800 - wrap_number),
        "PF" + str(799 - wrap_number),
        "PXY",
        _offset_fragment("PX", offsets[6]),
        "G102",
        "G108",
        "(Top A corner - head end)",
      ),
      "G106 P0",
    ]
  )

  if transfer_pause:
    lines.append("G106 P1")

  lines.extend(
    [
      "G106 P3",
      _line(
        "G109",
        "PF" + str(800 - wrap_number),
        "PRT",
        "G103",
        "PB" + str(1998 + wrap_number),
        "PB" + str(1999 + wrap_number),
        "PX",
        _offset_fragment("PX", offsets[7]),
        "(Top B corner - head end)",
      ),
      _line(
        "G103",
        "PB" + str(1998 + wrap_number),
        "PB" + str(1999 + wrap_number),
        "PY",
        "G105 " + _coord("PY", -Y_PULL_IN),
      ),
    ]
  )

  if _near_comb(1999 + wrap_number):
    lines.append(
      _line(
        "G103",
        "PB" + str(1998 + wrap_number),
        "PB" + str(1999 + wrap_number),
        "PX",
        "G105 " + _coord("PX", -Y_PULL_IN * COMB_PULL_FACTOR),
      )
    )

  if final_wrap:
    lines.extend(
      [
        "G103 PB2398 PB2399 PY G105 PY0 G111",
        "X440 Y2315 F300",
        "G106 P0",
        "X440 Y2335",
        "X650 Y2335 G111",
        "X440 Y2335",
      ]
    )
    return _annotate_wrap_lines(wrap_number, lines)

  # vDescription.md contains a stray spreadsheet line label before HEAD RESTART.
  # Treat that token as editorial numbering rather than emitted G-Code.
  lines.extend(
    [
      _line(
        "(HEAD RESTART)",
        "G109",
        "PB" + str(1999 + wrap_number),
        "PLB",
        "G103",
        "PB" + str(401 - wrap_number),
        "PB" + str(400 - wrap_number),
        "PXY",
        _offset_fragment("PY", offsets[8]),
        "G102",
        "G108",
        "( BOARD GAP )",
      ),
      "G106 P3",
    ]
  )

  if transfer_pause:
    lines.append("G106 P2")

  lines.extend(
    [
      "G106 P0",
      _line(
        "G109",
        "PB" + str(400 - wrap_number),
        "PBR",
        "G103",
        "PF" + str(wrap_number),
        "PF" + str(wrap_number + 1),
        "PY",
        _offset_fragment("PY", offsets[9]),
        "(Head A corner)",
      ),
      _line(
        "G103",
        "PF" + str(wrap_number),
        "PF" + str(wrap_number + 1),
        "PX",
        "G105 " + _coord("PX", X_PULL_IN),
      ),
      _line(
        "G109",
        "PF" + str(wrap_number),
        "PTL",
        "G103",
        "PF" + str(2399 - wrap_number),
        "PF" + str(2398 - wrap_number),
        "PXY",
        _offset_fragment("PX", offsets[10]),
        "G102",
        "G108",
        "(Bottom A corner - head end)",
      ),
      "G106 P0",
    ]
  )

  if transfer_pause:
    lines.append("G106 P1")

  lines.extend(
    [
      "G106 P3",
      _line(
        "G109",
        "PF" + str(2399 - wrap_number),
        "PBL",
        "G103",
        "PB" + str(399 + wrap_number),
        "PB" + str(400 + wrap_number),
        _offset_fragment("PX", offsets[11]),
        "PX12",
        "(Bottom B corner - head end)",
      ),
      _line(
        "G103",
        "PB" + str(399 + wrap_number),
        "PB" + str(400 + wrap_number),
        "PY",
        "G105 " + _coord("PY", Y_PULL_IN),
      ),
    ]
  )

  if _near_comb(399 + wrap_number):
    lines.append(
      _line(
        "G103",
        "PB" + str(399 + wrap_number),
        "PB" + str(400 + wrap_number),
        "PX",
        "G105 " + _coord("PX", Y_PULL_IN * COMB_PULL_FACTOR),
      )
    )

  return _annotate_wrap_lines(wrap_number, lines)


def render_v_template_lines(
  *,
  offsets=None,
  transfer_pause=False,
  named_inputs=None,
  special_inputs=None,
  cell_overrides=None,
):
  resolved_offsets, transfer_pause_value = _resolve_render_state(
    offsets=offsets,
    transfer_pause=transfer_pause,
    named_inputs=named_inputs,
    special_inputs=special_inputs,
    cell_overrides=cell_overrides,
  )

  lines = [
    "( V Layer )",
    _line("(HEAD RESTART)",_coord("X", 440), _coord("Y", 0)),
    "G106 P3",
    _line(
      "(0, )",
      "F1000",
      "G103",
      "PB400",
      "PB399",
      "PXY",
      "G105 " + _coord("PY", PREAMBLE_BOARD_GAP_PULL),
      "( BOARD GAP )",
    ),
  ]

  for wrap_number in range(1, PRE_FINAL_WRAP_COUNT + 1):
    lines.extend(_render_wrap_lines(wrap_number, resolved_offsets, transfer_pause_value))

  lines.extend(
    _render_wrap_lines(
      WRAP_COUNT,
      resolved_offsets,
      transfer_pause_value,
      final_wrap=True,
    )
  )
  return _number_lines(lines)


def render_v_template_ac_lines(
  cell_overrides=None,
  *,
  named_inputs=None,
  sheet_path=None,
  special_inputs=None,
):
  _ = sheet_path
  return render_v_template_lines(
    named_inputs=named_inputs,
    special_inputs=special_inputs,
    cell_overrides=cell_overrides,
  )


def read_cached_v_template_ac_lines(workbook_path=None):
  _ = workbook_path
  return render_v_template_ac_lines()


def read_v_template_named_inputs(sheet_path=None):
  _ = sheet_path
  return VTemplateGCodeGenerator().get_named_inputs()


def get_v_recipe_description():
  return "V-layer"


def get_v_recipe_file_name():
  return "V-layer.gc"


def write_v_template_ac_file(
  output_path,
  cell_overrides=None,
  *,
  named_inputs=None,
  sheet_path=None,
  special_inputs=None,
):
  _ = sheet_path
  output = Path(output_path)
  lines = render_v_template_ac_lines(
    cell_overrides,
    named_inputs=named_inputs,
    special_inputs=special_inputs,
  )
  output.write_text("\n".join(lines) + "\n", encoding="utf-8")
  return output


def write_v_template_file(
  output_path,
  *,
  offsets=None,
  transfer_pause=False,
  named_inputs=None,
  special_inputs=None,
  archive_directory=None,
  parent_hash=None,
):
  resolved_offsets, resolved_transfer_pause = _resolve_render_state(
    offsets=offsets,
    transfer_pause=transfer_pause,
    named_inputs=named_inputs,
    special_inputs=special_inputs,
  )
  lines = render_v_template_lines(
    offsets=offsets,
    transfer_pause=transfer_pause,
    named_inputs=named_inputs,
    special_inputs=special_inputs,
  )
  hash_value = Recipe.writeGeneratedFile(
    output_path,
    get_v_recipe_description(),
    lines,
    archiveDirectory=archive_directory,
    parentHash=parent_hash,
  )
  return {
    "description": get_v_recipe_description(),
    "fileName": get_v_recipe_file_name(),
    "hashValue": hash_value,
    "lines": lines,
    "offsets": list(resolved_offsets),
    "transferPause": resolved_transfer_pause,
    "wrapCount": WRAP_COUNT,
  }


class VTemplateGCodeGenerator:
  def __init__(
    self,
    sheet_path=None,
    *,
    named_inputs=None,
    cell_overrides=None,
    special_inputs=None,
  ):
    _ = sheet_path
    self.offsets, self.transfer_pause = _resolve_options(
      named_inputs=named_inputs,
      special_inputs=special_inputs,
      cell_overrides=cell_overrides,
    )
    self._lines = render_v_template_lines(
      offsets=self.offsets,
      transfer_pause=self.transfer_pause,
    )

  def render_lines(self):
    return list(self._lines)

  def render_column_lines(self, column_label):
    if str(column_label).upper() != "AC":
      raise VTemplateInputError("Only AC output is available for VTemplateGCode.")
    return self.render_lines()

  def get_named_inputs(self):
    values = {"transferPause": self.transfer_pause, "pause at combs": self.transfer_pause}
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


def _coerce_cli_value(value):
  normalized = value.strip()
  if "," in normalized:
    return [part.strip() for part in normalized.split(",")]
  if normalized.lower() in ("true", "false", "yes", "no", "on", "off"):
    return _coerce_bool(normalized)
  try:
    return _coerce_number(normalized)
  except VTemplateInputError:
    return normalized


def _parse_assignment(raw_assignment):
  if "=" not in raw_assignment:
    raise VTemplateInputError(
      "Expected KEY=VALUE assignment, got " + repr(raw_assignment) + "."
    )
  key, value = raw_assignment.split("=", 1)
  return key.strip(), _coerce_cli_value(value)


def main(argv=None):
  parser = argparse.ArgumentParser(
    description="Render V-layer G-Code from the programmatic specification."
  )
  parser.add_argument("output", help="Path to the text or recipe file to write.")
  parser.add_argument(
    "--sheet",
    default=None,
    help="Compatibility option. Ignored because the V generator is programmatic.",
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
    help="Named V input override in KEY=VALUE form.",
  )
  parser.add_argument(
    "--special",
    dest="special_assignments",
    action="append",
    default=[],
    help="Special V input override in KEY=VALUE form.",
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
    "--recipe",
    action="store_true",
    help="Write a hashed recipe file with the standard recipe header.",
  )
  args = parser.parse_args(argv)

  if args.assignments:
    raise VTemplateInputError(
      "Cell overrides are not supported by the programmatic V generator."
    )

  named_inputs = dict(_parse_assignment(assignment) for assignment in args.named_assignments)
  special_inputs = dict(
    _parse_assignment(assignment) for assignment in args.special_assignments
  )

  if args.offsets:
    special_inputs["offsets"] = args.offsets
  if args.transfer_pause:
    special_inputs["transferPause"] = True

  if args.recipe:
    write_v_template_file(
      args.output,
      named_inputs=named_inputs,
      special_inputs=special_inputs,
    )
  else:
    write_v_template_ac_file(
      args.output,
      named_inputs=named_inputs,
      special_inputs=special_inputs,
    )
  return 0


DEFAULT_V_TEMPLATE_ROW_COUNT = len(render_v_template_ac_lines())


if __name__ == "__main__":
  raise SystemExit(main())
