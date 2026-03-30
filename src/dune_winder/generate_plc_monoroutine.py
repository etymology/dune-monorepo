from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from dune_winder.paths import PLC_ROOT
from dune_winder.plc_ladder import RllEmitter
from dune_winder.plc_ladder import RllParser
from dune_winder.plc_ladder.ast import Branch
from dune_winder.plc_ladder.ast import InstructionCall
from dune_winder.plc_ladder.ast import Node
from dune_winder.plc_ladder.ast import Rung
from dune_winder.plc_ladder.ast import Routine


DEFAULT_OUTPUT_DIR = PLC_ROOT / "Monoroutine"

PROGRAM_ORDER = (
  "Safety",
  "MainProgram",
  "PID_Tension_Servo",
  "Initialize",
  "Ready_State_1",
  "MoveXY_State_2_3",
  "MoveZ_State_4_5",
  "Latch_UnLatch_State_6_7_8",
  "UnServo_9",
  "Error_State_10",
  "EOT_Trip_11",
  "xz_move",
  "yz_move",
  "HMI_Stop_Request_14",
  "motionQueue",
)

PROGRAM_PREFIXES = {
  "Safety": "SF",
  "MainProgram": "MP",
  "PID_Tension_Servo": "PTS",
  "Initialize": "INIT",
  "Ready_State_1": "RS1",
  "MoveXY_State_2_3": "MXY",
  "MoveZ_State_4_5": "MZ",
  "Latch_UnLatch_State_6_7_8": "LAT",
  "UnServo_9": "US9",
  "Error_State_10": "ERR10",
  "EOT_Trip_11": "EOT11",
  "xz_move": "XZ",
  "yz_move": "YZ",
  "HMI_Stop_Request_14": "HMI14",
  "motionQueue": "MQ",
}

SEGQUEUE_FIELD_PATTERN = (
  r"\.[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]+\])*(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]+\])*)*"
)
SEGQUEUE_SPECIAL_PATTERN = re.compile(
  r"^(SegQueueBST)\s+([A-Za-z_][A-Za-z0-9_]*)\s+(BND)\s+(.+)$"
)
SEGQUEUE_RENDER_PATTERN = re.compile(
  rf'"?SegQueueBST\s+([A-Za-z_][A-Za-z0-9_]*)\s+BND\s+({SEGQUEUE_FIELD_PATTERN})"?'
)
IDENTIFIER_PATTERN = re.compile(
  r"(?<![A-Za-z0-9_.])"
  r"([A-Za-z_][A-Za-z0-9_:]*(?:\[[^\]]+\])*(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]+\])*)*)"
)
ROOT_PATTERN = re.compile(r"^([A-Za-z_][A-Za-z0-9_:]*)(.*)$")

MOVE_XY_FALLBACK_RUNG = (
  "BST XIO TENSION_CONTROL_OK NXB XIC TENSION_CONTROL_OK XIO speed_regulator_switch BND "
  "XIC trigger_xy_move MCLM X_Y main_xy_move 0 X_POSITION XY_SPEED_REQ "
  '"Units per sec" XY_ACCELERATION "Units per sec2" XY_DECELERATION "Units per sec2" '
  'S-Curve 500 500 "Units per sec3" 0 Disabled Programmed 50 0 None 0 0'
)


def build_argument_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description=(
      "Generate a single monoroutine PLC export by flattening the checked-in "
      "dune_winder/plc routines into one pasteable.rll plus merged program tags."
    ),
  )
  parser.add_argument(
    "--output-dir",
    type=Path,
    default=DEFAULT_OUTPUT_DIR,
    help="Directory to write the Monoroutine artifacts into.",
  )
  parser.add_argument(
    "--check",
    action="store_true",
    help="Fail if the generated artifacts differ from the checked-in outputs.",
  )
  return parser


def _timestamp() -> str:
  return datetime.now(timezone.utc).isoformat()


def _program_tags_path(program_name: str) -> Path:
  return PLC_ROOT / program_name / "programTags.json"


def _routine_path(program_name: str, routine_name: str) -> Path:
  return PLC_ROOT / program_name / routine_name / "pasteable.rll"


def _load_program_payload(program_name: str) -> dict:
  return json.loads(_program_tags_path(program_name).read_text(encoding="utf-8"))


def _parse_routine(program_name: str, routine_name: str, parser: RllParser) -> Routine:
  path = _routine_path(program_name, routine_name)
  return parser.parse_routine_text(
    routine_name,
    path.read_text(encoding="utf-8"),
    program=program_name,
    source_path=path,
  )


def _iter_nodes(nodes: Iterable[Node]) -> Iterable[InstructionCall]:
  for node in nodes:
    if isinstance(node, InstructionCall):
      yield node
      continue
    if isinstance(node, Branch):
      for branch in node.branches:
        yield from _iter_nodes(branch)


def _collect_collision_names(program_payloads: dict[str, dict]) -> set[str]:
  name_to_programs: dict[str, set[str]] = defaultdict(set)
  for program_name, payload in program_payloads.items():
    for tag in payload.get("program_tags", []):
      name_to_programs[str(tag["name"])].add(program_name)
  return {
    name
    for name, programs in name_to_programs.items()
    if len(programs) > 1
  }


def _build_program_tag_maps(program_payloads: dict[str, dict]) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
  collisions = _collect_collision_names(program_payloads)
  rename_maps: dict[str, dict[str, str]] = {}
  rename_only: dict[str, dict[str, str]] = {}

  for program_name, payload in program_payloads.items():
    prefix = PROGRAM_PREFIXES[program_name]
    program_map: dict[str, str] = {}
    renamed_only_map: dict[str, str] = {}
    for tag in payload.get("program_tags", []):
      name = str(tag["name"])
      new_name = f"{prefix}_{name}" if name in collisions else name
      program_map[name] = new_name
      if new_name != name:
        renamed_only_map[name] = new_name
    rename_maps[program_name] = program_map
    rename_only[program_name] = renamed_only_map
  return rename_maps, rename_only


def _rename_root(token: str, tag_map: dict[str, str]) -> str:
  special_match = SEGQUEUE_SPECIAL_PATTERN.match(token)
  if special_match:
    index_tag = special_match.group(2)
    return " ".join((
      special_match.group(1),
      tag_map.get(index_tag, index_tag),
      special_match.group(3),
      special_match.group(4),
    ))

  match = ROOT_PATTERN.match(token)
  if match is None:
    return token
  root = match.group(1)
  suffix = match.group(2)
  renamed = tag_map.get(root, root)
  return f"{renamed}{suffix}"


def _rename_formula(formula: str, tag_map: dict[str, str]) -> str:
  def replacer(match: re.Match[str]) -> str:
    return _rename_root(match.group(1), tag_map)

  return IDENTIFIER_PATTERN.sub(replacer, formula)


def _rename_operand(
  operand: str,
  *,
  opcode: str,
  operand_index: int,
  tag_map: dict[str, str],
  label_map: dict[str, str],
) -> str:
  if operand in label_map:
    return label_map[operand]

  if opcode == "CMP":
    return _rename_formula(operand, tag_map)
  if opcode == "CPT" and operand_index == 1:
    return _rename_formula(operand, tag_map)
  if opcode in {"JMP", "LBL"}:
    return label_map.get(operand, operand)
  return _rename_root(operand, tag_map)


def _rewrite_nodes(
  nodes: tuple[Node, ...],
  *,
  tag_map: dict[str, str],
  label_map: dict[str, str],
) -> tuple[Node, ...]:
  rewritten: list[Node] = []
  for node in nodes:
    if isinstance(node, Branch):
      rewritten.append(
        Branch(
          branches=tuple(
            _rewrite_nodes(branch, tag_map=tag_map, label_map=label_map)
            for branch in node.branches
          ),
        )
      )
      continue

    rewritten.append(
      InstructionCall(
        opcode=node.opcode,
        operands=tuple(
          _rename_operand(
            operand,
            opcode=node.opcode,
            operand_index=index,
            tag_map=tag_map,
            label_map=label_map,
          )
          for index, operand in enumerate(node.operands)
        ),
      )
    )
  return tuple(rewritten)


def _collect_labels(routine: Routine) -> set[str]:
  labels: set[str] = set()
  for rung in routine.rungs:
    for node in _iter_nodes(rung.nodes):
      if node.opcode == "LBL":
        labels.add(node.operands[0])
  return labels


def _rename_routine(
  routine: Routine,
  *,
  tag_map: dict[str, str],
  label_prefix: str,
) -> Routine:
  labels = _collect_labels(routine)
  label_map = {
    label: f"{label_prefix}_{label}"
    for label in sorted(labels)
  }
  return replace(
    routine,
    rungs=tuple(
      Rung(nodes=_rewrite_nodes(rung.nodes, tag_map=tag_map, label_map=label_map))
      for rung in routine.rungs
    ),
  )


def _prefix_rungs(rungs: tuple[Rung, ...], prefix_rung: Rung) -> tuple[Rung, ...]:
  prefixed = []
  for rung in rungs:
    prefixed.append(Rung(nodes=prefix_rung.nodes + rung.nodes))
  return tuple(prefixed)


def _is_standalone_jsr(rung: Rung, target: str | None = None) -> bool:
  if len(rung.nodes) != 1:
    return False
  node = rung.nodes[0]
  if not isinstance(node, InstructionCall) or node.opcode != "JSR":
    return False
  if target is None:
    return True
  return node.operands and node.operands[0] == target


def _inline_standalone_jsrs(rungs: tuple[Rung, ...], inline_map: dict[str, tuple[Rung, ...]]) -> tuple[Rung, ...]:
  flattened: list[Rung] = []
  for rung in rungs:
    if _is_standalone_jsr(rung):
      target = rung.nodes[0].operands[0]
      if target not in inline_map:
        flattened.append(rung)
        continue
      flattened.extend(inline_map[target])
      continue
    flattened.append(rung)
  return tuple(flattened)


def _prepare_move_xy_main(
  parser: RllParser,
  rename_maps: dict[str, dict[str, str]],
) -> tuple[Rung, ...]:
  main_routine = _rename_routine(
    _parse_routine("MoveXY_State_2_3", "main", parser),
    tag_map=rename_maps["MoveXY_State_2_3"],
    label_prefix="MXY_main",
  )
  xy_reg = _rename_routine(
    _parse_routine("MoveXY_State_2_3", "xy_speed_regulator", parser),
    tag_map=rename_maps["MoveXY_State_2_3"],
    label_prefix="MXY_xyreg",
  )
  prefix_rung = parser.parse_rung("XIC TENSION_CONTROL_OK XIC speed_regulator_switch")
  fallback_rung = parser.parse_rung(MOVE_XY_FALLBACK_RUNG)

  output: list[Rung] = []
  for rung in main_routine.rungs:
    if any(node.opcode == "JSR" and node.operands[0] == "xy_speed_regulator" for node in _iter_nodes(rung.nodes)):
      output.extend(_prefix_rungs(xy_reg.rungs, prefix_rung))
      output.append(fallback_rung)
      continue
    output.append(rung)
  return tuple(output)


def _prepare_motion_queue_main(
  parser: RllParser,
  rename_maps: dict[str, dict[str, str]],
) -> tuple[Rung, ...]:
  arc = _rename_routine(
    _parse_routine("motionQueue", "ArcSweepRad", parser),
    tag_map=rename_maps["motionQueue"],
    label_prefix="MQ_arc",
  )
  max_sin = _rename_routine(
    _parse_routine("motionQueue", "MaxAbsSinSweep", parser),
    tag_map=rename_maps["motionQueue"],
    label_prefix="MQ_sin",
  )
  max_cos = _rename_routine(
    _parse_routine("motionQueue", "MaxAbsCosSweep", parser),
    tag_map=rename_maps["motionQueue"],
    label_prefix="MQ_cos",
  )
  seg = _rename_routine(
    _parse_routine("motionQueue", "SegTangentBounds", parser),
    tag_map=rename_maps["motionQueue"],
    label_prefix="MQ_seg",
  )
  seg_rungs = _inline_standalone_jsrs(
    seg.rungs,
    {
      "CircleCenterForSeg": (),
      "ArcSweepRad": arc.rungs,
      "MaxAbsSinSweep": max_sin.rungs,
      "MaxAbsCosSweep": max_cos.rungs,
    },
  )

  cap = _rename_routine(
    _parse_routine("motionQueue", "CapSegSpeed", parser),
    tag_map=rename_maps["motionQueue"],
    label_prefix="MQ_cap",
  )
  cap_rungs = _inline_standalone_jsrs(cap.rungs, {"SegTangentBounds": seg_rungs})

  main = _rename_routine(
    _parse_routine("motionQueue", "main", parser),
    tag_map=rename_maps["motionQueue"],
    label_prefix="MQ_main",
  )
  return _inline_standalone_jsrs(main.rungs, {"CapSegSpeed": cap_rungs})


def _prepare_plain_main(
  parser: RllParser,
  program_name: str,
  rename_maps: dict[str, dict[str, str]],
) -> tuple[Rung, ...]:
  return _rename_routine(
    _parse_routine(program_name, "main", parser),
    tag_map=rename_maps[program_name],
    label_prefix=f"{PROGRAM_PREFIXES[program_name]}_main",
  ).rungs


def _build_monoroutine(parser: RllParser, rename_maps: dict[str, dict[str, str]]) -> Routine:
  rungs: list[Rung] = []
  for program_name in PROGRAM_ORDER:
    if program_name == "MoveXY_State_2_3":
      rungs.extend(_prepare_move_xy_main(parser, rename_maps))
      continue
    if program_name == "motionQueue":
      rungs.extend(_prepare_motion_queue_main(parser, rename_maps))
      continue
    rungs.extend(_prepare_plain_main(parser, program_name, rename_maps))
  return Routine(name="main", rungs=tuple(rungs), program="Monoroutine")


def _merge_udts(program_payloads: dict[str, dict]) -> list[dict]:
  merged: dict[str, dict] = {}
  for payload in program_payloads.values():
    for raw_udt in payload.get("udts", []):
      name = str(raw_udt["name"])
      merged.setdefault(name, raw_udt)
  return [merged[name] for name in sorted(merged)]


def _collect_array_index_usage(routine_text: str, tag_name: str) -> tuple[set[int], bool]:
  pattern = re.compile(rf"(?<![A-Za-z0-9_.]){re.escape(tag_name)}\[([^\]]+)\]")
  literal_indexes: set[int] = set()
  saw_non_literal = False
  for match in pattern.finditer(routine_text):
    index_text = match.group(1).strip()
    if index_text.isdigit():
      literal_indexes.add(int(index_text))
    else:
      saw_non_literal = True
  return literal_indexes, saw_non_literal


def _trim_tag_dimensions(raw_tag: dict, new_name: str, routine_text: str) -> dict:
  trimmed = dict(raw_tag)
  array_dimensions = int(trimmed.get("array_dimensions", 0) or 0)
  dimensions = list(trimmed.get("dimensions", [0, 0, 0]))
  if array_dimensions <= 0 or not dimensions or int(dimensions[0]) <= 0:
    return trimmed

  literal_indexes, saw_non_literal = _collect_array_index_usage(routine_text, new_name)
  if saw_non_literal or not literal_indexes:
    return trimmed

  required_length = max(literal_indexes) + 1
  if required_length >= int(dimensions[0]):
    return trimmed

  dimensions[0] = required_length
  trimmed["dimensions"] = dimensions
  return trimmed


def _merge_program_tags(
  program_payloads: dict[str, dict],
  rename_maps: dict[str, dict[str, str]],
  routine_text: str,
) -> list[dict]:
  merged = []
  seen_names: set[str] = set()

  for program_name in PROGRAM_ORDER:
    payload = program_payloads[program_name]
    rename_map = rename_maps[program_name]
    for raw_tag in payload.get("program_tags", []):
      renamed = dict(raw_tag)
      old_name = str(raw_tag["name"])
      new_name = rename_map[old_name]
      if new_name in seen_names:
        raise ValueError(f"duplicate monoroutine tag name after merge: {new_name}")
      seen_names.add(new_name)
      renamed = _trim_tag_dimensions(renamed, new_name, routine_text)
      renamed["name"] = new_name
      renamed["program"] = "Monoroutine"
      renamed["fully_qualified_name"] = f"Program:Monoroutine.{new_name}"
      merged.append(renamed)
  return merged


def _generate_program_tags_payload(
  program_payloads: dict[str, dict],
  rename_maps: dict[str, dict[str, str]],
  routine_text: str,
) -> dict:
  sample = next(iter(program_payloads.values()))
  return {
    "schema_version": 1,
    "generated_at": _timestamp(),
    "plc_path": sample.get("plc_path"),
    "program_name": "Monoroutine",
    "main_routine_name": "main",
    "main_routine_name_source": "single_routine",
    "routines": ["main"],
    "subroutines": [],
    "udts": _merge_udts(program_payloads),
    "program_tags": _merge_program_tags(program_payloads, rename_maps, routine_text),
  }


def _generate_rename_map_payload(rename_only: dict[str, dict[str, str]]) -> dict:
  return {
    "generated_at": _timestamp(),
    "program_tag_renames": {
      program_name: rename_only[program_name]
      for program_name in PROGRAM_ORDER
      if rename_only[program_name]
    },
  }


def _generate_import_notes(rename_only: dict[str, dict[str, str]]) -> str:
  lines = [
    "# Monoroutine Import Notes",
    "",
    "This export assumes the controller-level tags and hardware configuration already exist on the PLC.",
    "Only the Monoroutine program-scoped tags need to be created/imported alongside the routine text.",
    "",
    "## Included Scan Order",
    "",
  ]
  for index, program_name in enumerate(PROGRAM_ORDER, start=1):
    lines.append(f"{index}. `{program_name}/main`")
  lines.extend([
    "",
    "## Omitted Or Flattened",
    "",
    "- `Camera/main` is empty and was omitted.",
    "- `MoveXY_State_2_3/xy_speed_regulator` was flattened into `MoveXY_State_2_3/main`.",
    "- `motionQueue` helper routines were flattened into `motionQueue/main`.",
    "- `motionQueue/CircleCenterForSeg` was not emitted separately because the checked-in routine is a no-op.",
    "",
    "## Renamed Routine-Level Tags",
    "",
  ])
  for program_name in PROGRAM_ORDER:
    renamed = rename_only[program_name]
    if not renamed:
      continue
    lines.append(f"### {program_name}")
    lines.append("")
    for old_name, new_name in sorted(renamed.items()):
      lines.append(f"- `{old_name}` -> `{new_name}`")
    lines.append("")
  return "\n".join(lines).rstrip() + "\n"


def _normalize_segqueue_rendering(text: str) -> str:
  return SEGQUEUE_RENDER_PATTERN.sub(
    lambda match: f"SegQueue[{match.group(1)}]{match.group(2)}",
    text,
  )


def _write_or_check(path: Path, content: str, *, check: bool) -> list[str]:
  if check:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if existing != content:
      return [f"generated output differs: {path}"]
    return []

  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(content, encoding="utf-8")
  return [f"wrote {path}"]


def _normalize_generated_at(value):
  if isinstance(value, dict):
    return {
      key: _normalize_generated_at(inner)
      for key, inner in value.items()
      if key != "generated_at"
    }
  if isinstance(value, list):
    return [_normalize_generated_at(item) for item in value]
  return value


def _write_or_check_json(path: Path, payload: dict, *, check: bool) -> list[str]:
  content = json.dumps(payload, indent=2) + "\n"
  if check:
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if _normalize_generated_at(existing) != _normalize_generated_at(payload):
      return [f"generated output differs: {path}"]
    return []
  return _write_or_check(path, content, check=check)


def main(argv=None) -> int:
  args = build_argument_parser().parse_args(argv)
  parser = RllParser()
  emitter = RllEmitter()

  program_payloads = {
    program_name: _load_program_payload(program_name)
    for program_name in PROGRAM_ORDER
  }
  rename_maps, rename_only = _build_program_tag_maps(program_payloads)

  monoroutine = _build_monoroutine(parser, rename_maps)
  monoroutine_text = _normalize_segqueue_rendering(emitter.emit_routine(monoroutine))
  if "JSR " in monoroutine_text:
    raise ValueError("generated monoroutine still contains JSR instructions")
  parser.parse_routine_text("main", monoroutine_text, program="Monoroutine")

  output_dir = Path(args.output_dir)
  messages: list[str] = []
  messages.extend(
    _write_or_check(
      output_dir / "main" / "pasteable.rll",
      monoroutine_text,
      check=args.check,
    )
  )
  messages.extend(
    _write_or_check_json(
      output_dir / "programTags.json",
      _generate_program_tags_payload(program_payloads, rename_maps, monoroutine_text),
      check=args.check,
    )
  )
  messages.extend(
    _write_or_check_json(
      output_dir / "tag_rename_map.json",
      _generate_rename_map_payload(rename_only),
      check=args.check,
    )
  )
  messages.extend(
    _write_or_check(
      output_dir / "IMPORT_NOTES.md",
      _generate_import_notes(rename_only),
      check=args.check,
    )
  )

  for message in messages:
    print(message)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
