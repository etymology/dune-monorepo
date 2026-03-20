import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parents[2] / "plc"


def _load_main_routine_overrides(mapping_path):
  if mapping_path is None:
    return {}

  loaded = json.loads(Path(mapping_path).read_text())
  if not isinstance(loaded, dict):
    raise ValueError("Main routine override file must contain a JSON object.")

  normalized = {}
  for program_name, routine_name in loaded.items():
    if not isinstance(program_name, str) or not isinstance(routine_name, str):
      raise ValueError("Main routine overrides must map strings to strings.")
    normalized[program_name] = routine_name
  return normalized


def infer_main_routine(program_name, routines, overrides=None):
  overrides = overrides or {}
  if program_name in overrides:
    return overrides[program_name], "override"

  ordered_routines = list(dict.fromkeys(routines))
  if not ordered_routines:
    return None, "missing"

  if len(ordered_routines) == 1:
    return ordered_routines[0], "single_routine"

  exact_candidates = [
    program_name,
    f"{program_name}Routine",
    f"{program_name}_routine",
  ]
  for candidate in exact_candidates:
    if candidate in ordered_routines:
      return candidate, "name_match"

  lowered = {routine.lower(): routine for routine in ordered_routines}
  for candidate in exact_candidates + ["main"]:
    routine_name = lowered.get(candidate.lower())
    if routine_name is not None:
      return routine_name, "casefold_name_match"

  return None, "unresolved"


def _parse_program_scoped_name(tag_name):
  if not tag_name.startswith("Program:"):
    return None, tag_name

  scoped_name = tag_name[len("Program:"):]
  program_name, separator, nested_name = scoped_name.partition(".")
  if not separator:
    return program_name, ""
  return program_name, nested_name


def _normalize_field_definition(field_name, field_definition):
  normalized = {
    "name": field_name,
    "tag_type": field_definition.get("tag_type"),
    "data_type_name": field_definition.get("data_type_name"),
  }
  if field_definition.get("array"):
    normalized["array_length"] = field_definition["array"]
  if "bit" in field_definition:
    normalized["bit"] = field_definition["bit"]
  if "offset" in field_definition:
    normalized["offset"] = field_definition["offset"]
  return normalized


def _collect_udts_from_data_type(data_type, udts_by_name):
  if not isinstance(data_type, dict):
    return

  udt_name = data_type.get("name")
  if not udt_name:
    return

  internal_tags = data_type.get("internal_tags", {})
  field_order = data_type.get("attributes") or list(internal_tags.keys())
  if udt_name not in udts_by_name:
    udts_by_name[udt_name] = {
      "name": udt_name,
      "fields": [
        _normalize_field_definition(field_name, internal_tags[field_name])
        for field_name in field_order
        if field_name in internal_tags
      ],
    }

  for field_definition in internal_tags.values():
    nested_data_type = field_definition.get("data_type")
    if isinstance(nested_data_type, dict):
      _collect_udts_from_data_type(nested_data_type, udts_by_name)


def collect_udts(tag_definitions):
  udts_by_name = {}
  for tag_definition in tag_definitions:
    _collect_udts_from_data_type(tag_definition.get("data_type"), udts_by_name)
  return [udts_by_name[name] for name in sorted(udts_by_name)]


def normalize_tag_definition(tag_definition):
  program_name, local_name = _parse_program_scoped_name(tag_definition["tag_name"])
  normalized = {
    "name": local_name if program_name is not None else tag_definition["tag_name"],
    "fully_qualified_name": tag_definition["tag_name"],
    "tag_type": tag_definition.get("tag_type"),
    "data_type_name": tag_definition.get("data_type_name"),
    "alias": tag_definition.get("alias", False),
    "external_access": tag_definition.get("external_access"),
    "dimensions": tag_definition.get("dimensions", []),
    "array_dimensions": tag_definition.get("dim", 0),
  }
  if program_name is not None:
    normalized["program"] = program_name
  if "bit_position" in tag_definition:
    normalized["bit_position"] = tag_definition["bit_position"]
  if tag_definition.get("tag_type") == "struct":
    normalized["udt_name"] = tag_definition["data_type"].get("name")
  return normalized


def split_controller_and_program_tags(tag_definitions):
  controller_tags = []
  program_tags = {}

  for tag_definition in tag_definitions:
    program_name, _ = _parse_program_scoped_name(tag_definition["tag_name"])
    if program_name is None:
      controller_tags.append(tag_definition)
      continue

    program_tags.setdefault(program_name, []).append(tag_definition)

  return controller_tags, program_tags


def fetch_plc_snapshot(plc_path, main_routine_overrides=None):
  try:
    from pycomm3 import LogixDriver
  except Exception as exception:
    raise RuntimeError(
      "pycomm3 is required to export PLC metadata from a live controller."
    ) from exception

  driver = LogixDriver(plc_path, init_tags=False, init_program_tags=False)
  try:
    if not driver.open():
      raise RuntimeError(f"Unable to open connection to PLC at {plc_path}.")

    all_tags = driver.get_tag_list(program="*", cache=False)
    info = dict(driver.info)
  finally:
    driver.close()

  controller_tags, program_tags = split_controller_and_program_tags(all_tags)
  program_definitions = {}
  program_info = info.get("programs", {})

  for program_name in sorted(program_info):
    routines = sorted(program_info[program_name].get("routines", []))
    main_routine_name, main_routine_source = infer_main_routine(
      program_name,
      routines,
      overrides=main_routine_overrides,
    )
    program_tag_definitions = program_tags.get(program_name, [])
    program_definitions[program_name] = {
      "program_name": program_name,
      "main_routine_name": main_routine_name,
      "main_routine_name_source": main_routine_source,
      "routines": routines,
      "subroutines": [
        routine_name
        for routine_name in routines
        if routine_name != main_routine_name
      ],
      "program_tags": [
        normalize_tag_definition(tag)
        for tag in program_tag_definitions
      ],
      "udts": collect_udts(program_tag_definitions),
    }

  return {
    "schema_version": 1,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "plc_path": plc_path,
    "controller": {
      key: info.get(key)
      for key in (
        "vendor",
        "product_type",
        "product_code",
        "revision",
        "serial",
        "product_name",
        "keyswitch",
        "name",
      )
    },
    "controller_level_tags": [
      normalize_tag_definition(tag)
      for tag in controller_tags
    ],
    "controller_udts": collect_udts(controller_tags),
    "programs": program_definitions,
  }


def _write_json(path, payload):
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")


def _ensure_rllscrap_placeholder(path):
  path.parent.mkdir(parents=True, exist_ok=True)
  if not path.exists():
    path.write_text("")


def write_plc_snapshot(snapshot, output_root):
  root = Path(output_root)
  root.mkdir(parents=True, exist_ok=True)

  controller_payload = {
    "schema_version": snapshot["schema_version"],
    "generated_at": snapshot["generated_at"],
    "plc_path": snapshot["plc_path"],
    "controller": snapshot["controller"],
    "udts": snapshot["controller_udts"],
    "controller_level_tags": snapshot["controller_level_tags"],
  }
  _write_json(root / "controller_level_tags.json", controller_payload)

  for program_name, program_definition in snapshot["programs"].items():
    program_root = root / program_name
    program_payload = {
      "schema_version": snapshot["schema_version"],
      "generated_at": snapshot["generated_at"],
      "plc_path": snapshot["plc_path"],
      "program_name": program_definition["program_name"],
      "main_routine_name": program_definition["main_routine_name"],
      "main_routine_name_source": program_definition["main_routine_name_source"],
      "routines": program_definition["routines"],
      "subroutines": program_definition["subroutines"],
      "udts": program_definition["udts"],
      "program_tags": program_definition["program_tags"],
    }
    _write_json(program_root / "programTags.json", program_payload)

    _ensure_rllscrap_placeholder(program_root / "main" / "studio_copy.rllscrap")
    for subroutine_name in program_definition["subroutines"]:
      _ensure_rllscrap_placeholder(
        program_root / subroutine_name / "studio_copy.rllscrap"
      )


def build_argument_parser():
  parser = argparse.ArgumentParser(
    description=(
      "Connect to a Studio 5000 PLC with pycomm3 and scaffold a plc/ metadata "
      "tree containing controller-level tags, per-program tags, and empty "
      "studio_copy.rllscrap placeholders for main routines and subroutines."
    )
  )
  parser.add_argument("plc_path", help="PLC connection path or IP address for pycomm3.")
  parser.add_argument(
    "--output-root",
    type=Path,
    default=DEFAULT_OUTPUT_ROOT,
    help="Directory to populate. Defaults to plc/ at the repo root.",
  )
  parser.add_argument(
    "--main-routine-map",
    type=Path,
    default=None,
    help=(
      "Optional JSON file mapping program names to main routine names when "
      "they cannot be inferred automatically."
    ),
  )
  parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Fetch and summarize PLC metadata without writing files.",
  )
  return parser


def main(argv=None):
  parser = build_argument_parser()
  args = parser.parse_args(argv)

  overrides = _load_main_routine_overrides(args.main_routine_map)
  snapshot = fetch_plc_snapshot(args.plc_path, main_routine_overrides=overrides)

  if args.dry_run:
    print(
      f"would export {len(snapshot['controller_level_tags'])} controller-level tags "
      f"and {len(snapshot['programs'])} programs to {args.output_root}"
    )
    for program_name in sorted(snapshot["programs"]):
      program_definition = snapshot["programs"][program_name]
      print(
        f"{program_name}: main={program_definition['main_routine_name']} "
        f"subroutines={len(program_definition['subroutines'])} "
        f"program_tags={len(program_definition['program_tags'])}"
      )
    return

  write_plc_snapshot(snapshot, args.output_root)
  print(
    f"exported {len(snapshot['controller_level_tags'])} controller-level tags "
    f"and {len(snapshot['programs'])} programs to {args.output_root}"
  )


if __name__ == "__main__":
  main()
