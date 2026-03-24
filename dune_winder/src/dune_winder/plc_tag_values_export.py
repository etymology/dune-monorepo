import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parents[2] / "plc"
_BATCH_SIZE = 20


def _json_default(value):
  if isinstance(value, (bytes, bytearray)):
    return list(value)
  if hasattr(value, "isoformat"):
    return value.isoformat()
  raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def make_json_safe(value):
  return json.loads(json.dumps(value, default=_json_default))


def _normalize_read_result(read_result, tag_name):
  if read_result is None:
    return None, f"{tag_name}: no response"

  if hasattr(read_result, "error"):
    if read_result.error:
      return None, str(read_result.error)
    return make_json_safe(read_result.value), None

  return make_json_safe(read_result), None


def _is_permission_denied(error):
  return isinstance(error, str) and "permission denied" in error.lower()


def _collect_tag_definitions(payload):
  if "controller_level_tags" in payload:
    return payload["controller_level_tags"]
  if "program_tags" in payload:
    return payload["program_tags"]
  return []


def _build_udt_lookup(payloads):
  udts_by_name = {}
  for payload in payloads:
    for udt in payload.get("udts", []):
      udts_by_name[udt["name"]] = udt
  return udts_by_name


def _index_suffixes(lengths):
  if not lengths:
    return [""]

  suffixes = [""]
  for length in lengths:
    next_suffixes = []
    for suffix in suffixes:
      for index in range(int(length)):
        next_suffixes.append(f"{suffix}[{index}]")
    suffixes = next_suffixes
  return suffixes


def _read_single_tag(driver, tag_name):
  return _normalize_read_result(driver.read(tag_name), tag_name)


def _should_skip_udt_field(field_name):
  normalized = str(field_name).strip().lower()
  return "dead_zone" in normalized or "pad" in normalized


def _read_struct_fields(driver, base_tag_name, udt_name, udts_by_name):
  udt_definition = udts_by_name.get(udt_name)
  if udt_definition is None:
    return None, f"{base_tag_name}: missing UDT definition for {udt_name}"

  value = {}
  field_errors = []
  for field in udt_definition.get("fields", []):
    if _should_skip_udt_field(field["name"]):
      continue
    field_tag_name = f"{base_tag_name}.{field['name']}"
    field_value, field_error = _read_tag_value_with_fallback(
      driver,
      {
        "fully_qualified_name": field_tag_name,
        "tag_type": field.get("tag_type"),
        "data_type_name": field.get("data_type_name"),
        "udt_name": field.get("data_type_name"),
        "dimensions": [field.get("array_length", 0), 0, 0],
        "array_dimensions": 1 if field.get("array_length") else 0,
      },
      udts_by_name,
    )
    value[field["name"]] = field_value
    if field_error is not None:
      field_errors.append(f"{field['name']}: {field_error}")

  if field_errors:
    return value, "; ".join(field_errors)
  return value, None


def _read_struct_array(driver, tag_definition, udts_by_name):
  dimensions = tag_definition.get("dimensions", [])
  array_dimensions = int(tag_definition.get("array_dimensions", 0) or 0)
  index_lengths = [
    dimension
    for dimension in dimensions[:array_dimensions]
    if int(dimension) > 0
  ]

  if not index_lengths:
    return _read_struct_fields(
      driver,
      tag_definition["fully_qualified_name"],
      tag_definition["udt_name"],
      udts_by_name,
    )

  values = []
  element_errors = []
  for suffix in _index_suffixes(index_lengths):
    element_tag_name = f"{tag_definition['fully_qualified_name']}{suffix}"
    element_value, element_error = _read_struct_fields(
      driver,
      element_tag_name,
      tag_definition["udt_name"],
      udts_by_name,
    )
    values.append(element_value)
    if element_error is not None:
      element_errors.append(f"{element_tag_name}: {element_error}")

  if element_errors:
    return values, "; ".join(element_errors)
  return values, None


def _read_tag_value_with_fallback(driver, tag_definition, udts_by_name):
  tag_name = tag_definition["fully_qualified_name"]
  value, error = _read_single_tag(driver, tag_name)
  if (
    error is None
    or not _is_permission_denied(error)
    or tag_definition.get("tag_type") != "struct"
    or not tag_definition.get("udt_name")
  ):
    return value, error

  return _read_struct_array(driver, tag_definition, udts_by_name)


def _read_tag_values(driver, tag_names, batch_size=_BATCH_SIZE):
  values_by_tag = {}
  for start in range(0, len(tag_names), batch_size):
    batch = tag_names[start:start + batch_size]
    if not batch:
      continue

    raw_results = driver.read(*batch)
    if not isinstance(raw_results, list):
      raw_results = [raw_results]

    if len(raw_results) != len(batch):
      raise RuntimeError(
        f"PLC read returned {len(raw_results)} results for {len(batch)} requested tags."
      )

    for tag_name, raw_result in zip(batch, raw_results, strict=True):
      values_by_tag[tag_name] = _normalize_read_result(raw_result, tag_name)

  return values_by_tag


def _load_json(path):
  return json.loads(Path(path).read_text())


def _write_json(path, payload):
  path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")


def iter_plc_json_files(output_root):
  root = Path(output_root)
  files = []

  controller_path = root / "controller_level_tags.json"
  if controller_path.exists():
    files.append(controller_path)

  files.extend(sorted(root.glob("*/programTags.json")))
  return files


def _collect_tag_names(payload):
  return [tag["fully_qualified_name"] for tag in _collect_tag_definitions(payload)]


def apply_tag_values_to_payload(payload, values_by_tag, generated_at):
  updated = dict(payload)
  updated["values_generated_at"] = generated_at

  for tag_list_key in ("controller_level_tags", "program_tags"):
    if tag_list_key not in updated:
      continue

    updated_tags = []
    for tag in updated[tag_list_key]:
      tag_copy = dict(tag)
      value, error = values_by_tag[tag["fully_qualified_name"]]
      tag_copy["value"] = value
      if error is None:
        tag_copy.pop("read_error", None)
      else:
        tag_copy["read_error"] = error
      updated_tags.append(tag_copy)
    updated[tag_list_key] = updated_tags

  return updated


def fetch_and_write_tag_values(plc_path, output_root=DEFAULT_OUTPUT_ROOT):
  try:
    from pycomm3 import LogixDriver
  except Exception as exception:
    raise RuntimeError(
      "pycomm3 is required to export PLC tag values from a live controller."
    ) from exception

  json_files = iter_plc_json_files(output_root)
  tags_by_file = {}
  all_payloads = []
  ordered_unique_tags = []
  seen_tags = set()
  tag_definitions_by_name = {}

  for json_file in json_files:
    payload = _load_json(json_file)
    all_payloads.append(payload)
    tag_names = _collect_tag_names(payload)
    tags_by_file[json_file] = (payload, tag_names)
    for tag_definition in _collect_tag_definitions(payload):
      tag_name = tag_definition["fully_qualified_name"]
      tag_definitions_by_name[tag_name] = tag_definition
      if tag_name in seen_tags:
        continue
      seen_tags.add(tag_name)
      ordered_unique_tags.append(tag_name)

  udts_by_name = _build_udt_lookup(all_payloads)

  driver = LogixDriver(plc_path)
  try:
    if not driver.open():
      raise RuntimeError(f"Unable to open connection to PLC at {plc_path}.")
    values_by_tag = _read_tag_values(driver, ordered_unique_tags)
    for tag_name, tag_definition in tag_definitions_by_name.items():
      _, error = values_by_tag[tag_name]
      if not _is_permission_denied(error):
        continue
      values_by_tag[tag_name] = _read_tag_value_with_fallback(
        driver,
        tag_definition,
        udts_by_name,
      )
  finally:
    driver.close()

  generated_at = datetime.now(timezone.utc).isoformat()
  for json_file, (payload, _) in tags_by_file.items():
    updated_payload = apply_tag_values_to_payload(payload, values_by_tag, generated_at)
    _write_json(json_file, updated_payload)

  from dune_winder.plc_manifest import PlcManifest
  manifest = PlcManifest(Path(output_root))
  manifest.load()
  for json_file in json_files:
    program_name = None if json_file.name == "controller_level_tags.json" else json_file.parent.name
    manifest.update_tag_values(program_name)
  manifest.save()

  return {
    "generated_at": generated_at,
    "file_count": len(json_files),
    "tag_count": len(ordered_unique_tags),
  }


def build_argument_parser():
  parser = argparse.ArgumentParser(
    description=(
      "Connect to a Studio 5000 PLC with pycomm3, read every tag listed in the "
      "existing plc/*.json metadata files, and write the live values back into "
      "those JSON files."
    )
  )
  parser.add_argument("plc_path", help="PLC connection path or IP address for pycomm3.")
  parser.add_argument(
    "--output-root",
    type=Path,
    default=DEFAULT_OUTPUT_ROOT,
    help="Directory containing controller_level_tags.json and */programTags.json.",
  )
  return parser


def main(argv=None):
  parser = build_argument_parser()
  args = parser.parse_args(argv)
  result = fetch_and_write_tag_values(args.plc_path, output_root=args.output_root)
  print(
    f"exported values for {result['tag_count']} tags across "
    f"{result['file_count']} JSON files in {args.output_root}"
  )


if __name__ == "__main__":
  main()
