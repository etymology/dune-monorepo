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
  if "controller_level_tags" in payload:
    return [tag["fully_qualified_name"] for tag in payload["controller_level_tags"]]
  if "program_tags" in payload:
    return [tag["fully_qualified_name"] for tag in payload["program_tags"]]
  return []


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
  ordered_unique_tags = []
  seen_tags = set()

  for json_file in json_files:
    payload = _load_json(json_file)
    tag_names = _collect_tag_names(payload)
    tags_by_file[json_file] = (payload, tag_names)
    for tag_name in tag_names:
      if tag_name in seen_tags:
        continue
      seen_tags.add(tag_name)
      ordered_unique_tags.append(tag_name)

  driver = LogixDriver(plc_path)
  try:
    if not driver.open():
      raise RuntimeError(f"Unable to open connection to PLC at {plc_path}.")
    values_by_tag = _read_tag_values(driver, ordered_unique_tags)
  finally:
    driver.close()

  generated_at = datetime.now(timezone.utc).isoformat()
  for json_file, (payload, _) in tags_by_file.items():
    updated_payload = apply_tag_values_to_payload(payload, values_by_tag, generated_at)
    _write_json(json_file, updated_payload)

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
