from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dune_winder.paths import PLC_ROOT
from dune_winder.plc_manifest import PlcManifest
from dune_winder.plc_tag_values_export import _build_udt_lookup
from dune_winder.plc_tag_values_export import _read_tag_value_with_fallback
from dune_winder.plc_tag_values_export import _read_tag_values


DEFAULT_PLC_PATH = "192.168.140.13"
DEFAULT_MONOROUTINE_ROOT = PLC_ROOT / "Monoroutine"
DEFAULT_REPORT_PATH = DEFAULT_MONOROUTINE_ROOT / "tag_value_sync_report.json"
RENAME_MAP_PATH = DEFAULT_MONOROUTINE_ROOT / "tag_rename_map.json"
MONOROUTINE_PROGRAM_TAGS_PATH = DEFAULT_MONOROUTINE_ROOT / "programTags.json"
DEFAULT_TARGET_PROGRAM_NAME = "monoprogram"


def _load_json(path: Path) -> dict:
  return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
  path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _timestamp() -> str:
  return datetime.now(timezone.utc).isoformat()


def _program_scoped_fqn(program_name: str, tag_name: str) -> str:
  return f"Program:{program_name}.{tag_name}"


def _iter_source_program_paths(plc_root: Path) -> list[Path]:
  return sorted(
    path
    for path in plc_root.glob("*/programTags.json")
    if path.parent.name != "Monoroutine"
  )


def _monoroutine_program_tags_path(plc_root: Path) -> Path:
  return Path(plc_root) / "Monoroutine" / "programTags.json"


def _rename_map_path(plc_root: Path) -> Path:
  return Path(plc_root) / "Monoroutine" / "tag_rename_map.json"


def _build_source_name_index(plc_root: Path) -> tuple[dict[str, list[dict]], list[dict]]:
  by_name: dict[str, list[dict]] = defaultdict(list)
  payloads: list[dict] = []

  for path in _iter_source_program_paths(plc_root):
    payload = _load_json(path)
    payloads.append(payload)
    program_name = str(payload["program_name"])
    for tag in payload.get("program_tags", []):
      entry = {
        "program_name": program_name,
        "tag_name": str(tag["name"]),
        "fully_qualified_name": str(tag["fully_qualified_name"]),
        "tag_definition": tag,
      }
      by_name[entry["tag_name"]].append(entry)

  return by_name, payloads


def _build_reverse_rename_index(rename_payload: dict) -> dict[str, list[dict]]:
  reverse: dict[str, list[dict]] = defaultdict(list)
  for program_name, mapping in rename_payload.get("program_tag_renames", {}).items():
    for old_name, new_name in mapping.items():
      reverse[str(new_name)].append({
        "program_name": str(program_name),
        "tag_name": str(old_name),
      })
  return reverse


def _resolve_monoroutine_sources(plc_root: Path) -> tuple[list[dict], dict]:
  monoroutine_payload = _load_json(_monoroutine_program_tags_path(plc_root))
  rename_payload = _load_json(_rename_map_path(plc_root))
  source_index, source_payloads = _build_source_name_index(plc_root)
  reverse_renames = _build_reverse_rename_index(rename_payload)

  resolved_tags = []
  summary = {
    "matched": 0,
    "ambiguous": 0,
    "unmatched": 0,
  }

  for monoroutine_tag in monoroutine_payload.get("program_tags", []):
    monoroutine_name = str(monoroutine_tag["name"])
    rename_matches = reverse_renames.get(monoroutine_name, [])
    if rename_matches:
      candidates = []
      for match in rename_matches:
        for source_entry in source_index.get(match["tag_name"], []):
          if source_entry["program_name"] == match["program_name"]:
            candidates.append(source_entry)
      match_basis = "rename_map"
    else:
      candidates = list(source_index.get(monoroutine_name, []))
      match_basis = "direct_name"

    unique_candidates = {
      (candidate["program_name"], candidate["tag_name"]): candidate
      for candidate in candidates
    }
    candidate_list = sorted(
      unique_candidates.values(),
      key=lambda entry: (entry["program_name"], entry["tag_name"]),
    )

    resolution = {
      "monoroutine_tag": monoroutine_name,
      "monoroutine_fqn": str(monoroutine_tag["fully_qualified_name"]),
      "match_basis": match_basis,
      "candidate_count": len(candidate_list),
      "candidates": [
        {
          "program_name": candidate["program_name"],
          "tag_name": candidate["tag_name"],
          "fully_qualified_name": candidate["fully_qualified_name"],
        }
        for candidate in candidate_list
      ],
    }

    if len(candidate_list) == 1:
      candidate = candidate_list[0]
      resolution["status"] = "matched"
      resolution["source_program"] = candidate["program_name"]
      resolution["source_tag"] = candidate["tag_name"]
      resolution["source_fqn"] = candidate["fully_qualified_name"]
      summary["matched"] += 1
    elif len(candidate_list) > 1:
      resolution["status"] = "ambiguous"
      summary["ambiguous"] += 1
    else:
      resolution["status"] = "unmatched"
      summary["unmatched"] += 1

    resolved_tags.append(resolution)

  return resolved_tags, {
    "monoroutine_payload": monoroutine_payload,
    "source_payloads": source_payloads,
    "summary": summary,
  }


def _is_missing_tag_error(error: str | None) -> bool:
  return isinstance(error, str) and "tag doesn't exist" in error.lower()


def _read_live_values(
  plc_path: str,
  matched_resolutions: list[dict],
  source_payloads: list[dict],
  *,
  target_program_name: str,
) -> dict[str, tuple[object, str | None]]:
  if not matched_resolutions:
    return {}

  try:
    from pycomm3 import LogixDriver
  except Exception as exception:
    raise RuntimeError(
      "pycomm3 is required to sync Monoroutine tag values from a live controller."
    ) from exception

  preferred_fqns = []
  definitions_by_fqn = {}
  for resolution in matched_resolutions:
    preferred_fqn = _program_scoped_fqn(target_program_name, resolution["monoroutine_tag"])
    resolution["controller_fqn"] = preferred_fqn
    preferred_fqns.append(preferred_fqn)
    definitions_by_fqn[preferred_fqn] = {
      "fully_qualified_name": preferred_fqn,
      "tag_type": resolution.get("tag_type"),
      "data_type_name": resolution.get("data_type_name"),
      "udt_name": resolution.get("udt_name"),
      "dimensions": resolution.get("dimensions", [0, 0, 0]),
      "array_dimensions": resolution.get("array_dimensions", 0),
    }

  udts_by_name = _build_udt_lookup(source_payloads)
  driver = LogixDriver(plc_path)
  try:
    if not driver.open():
      raise RuntimeError(f"Unable to open connection to PLC at {plc_path}.")
    values_by_fqn = _read_tag_values(driver, preferred_fqns)
    for preferred_fqn, tag_definition in definitions_by_fqn.items():
      value, error = values_by_fqn[preferred_fqn]
      if error is None:
        continue
      if tag_definition.get("tag_type") != "struct" or not tag_definition.get("udt_name"):
        continue
      values_by_fqn[preferred_fqn] = _read_tag_value_with_fallback(driver, tag_definition, udts_by_name)

    # Fall back to the legacy source-program tag only when the Monoroutine tag
    # does not exist on the controller.
    for resolution in matched_resolutions:
      preferred_fqn = resolution["controller_fqn"]
      value, error = values_by_fqn[preferred_fqn]
      if not _is_missing_tag_error(error):
        continue

      fallback_definition = {
        "fully_qualified_name": resolution["source_fqn"],
        "tag_type": resolution.get("tag_type"),
        "data_type_name": resolution.get("data_type_name"),
        "udt_name": resolution.get("udt_name"),
        "dimensions": resolution.get("dimensions", [0, 0, 0]),
        "array_dimensions": resolution.get("array_dimensions", 0),
      }
      fallback_value, fallback_error = _read_tag_value_with_fallback(driver, fallback_definition, udts_by_name)
      values_by_fqn[preferred_fqn] = (fallback_value, fallback_error)

    return values_by_fqn
  finally:
    driver.close()


def _apply_values_to_monoroutine(
  monoroutine_payload: dict,
  resolutions: list[dict],
  values_by_fqn: dict[str, tuple[object, str | None]],
  generated_at: str,
) -> dict:
  resolution_by_name = {entry["monoroutine_tag"]: entry for entry in resolutions}
  updated = dict(monoroutine_payload)
  updated["values_generated_at"] = generated_at

  updated_tags = []
  for tag in monoroutine_payload.get("program_tags", []):
    tag_copy = dict(tag)
    resolution = resolution_by_name[str(tag["name"])]
    if resolution["status"] != "matched":
      tag_copy["read_error"] = resolution["status"]
      updated_tags.append(tag_copy)
      continue

    controller_fqn = resolution.get("controller_fqn", resolution["monoroutine_fqn"])
    value, error = values_by_fqn[controller_fqn]
    tag_copy["value"] = value
    if error is None:
      tag_copy.pop("read_error", None)
    else:
      tag_copy["read_error"] = error
    updated_tags.append(tag_copy)

  updated["program_tags"] = updated_tags
  return updated


def _attach_source_metadata(resolutions: list[dict], monoroutine_payload: dict, plc_root: Path) -> list[dict]:
  source_index, _payloads = _build_source_name_index(plc_root)
  definitions_by_source = {}
  for entries in source_index.values():
    for entry in entries:
      definitions_by_source[(entry["program_name"], entry["tag_name"])] = entry["tag_definition"]

  enriched = []
  for resolution in resolutions:
    updated = dict(resolution)
    if resolution["status"] == "matched":
      tag_definition = definitions_by_source[(resolution["source_program"], resolution["source_tag"])]
      updated["tag_type"] = tag_definition.get("tag_type")
      updated["data_type_name"] = tag_definition.get("data_type_name")
      updated["udt_name"] = tag_definition.get("udt_name")
      updated["dimensions"] = tag_definition.get("dimensions", [0, 0, 0])
      updated["array_dimensions"] = tag_definition.get("array_dimensions", 0)
    enriched.append(updated)
  return enriched


def sync_monoroutine_tag_values(
  plc_path: str,
  *,
  plc_root: Path = PLC_ROOT,
  monoroutine_program_tags_path: Path = MONOROUTINE_PROGRAM_TAGS_PATH,
  report_path: Path | None = DEFAULT_REPORT_PATH,
  target_program_name: str = DEFAULT_TARGET_PROGRAM_NAME,
) -> dict:
  plc_root = Path(plc_root)
  monoroutine_program_tags_path = Path(monoroutine_program_tags_path)

  resolutions, context = _resolve_monoroutine_sources(plc_root)
  resolutions = _attach_source_metadata(resolutions, context["monoroutine_payload"], plc_root)
  matched = [entry for entry in resolutions if entry["status"] == "matched"]

  values_by_fqn = _read_live_values(
    plc_path,
    matched,
    context["source_payloads"],
    target_program_name=target_program_name,
  )
  generated_at = _timestamp()

  updated_payload = _apply_values_to_monoroutine(
    context["monoroutine_payload"],
    resolutions,
    values_by_fqn,
    generated_at,
  )
  _write_json(monoroutine_program_tags_path, updated_payload)

  manifest = PlcManifest(plc_root)
  manifest.load()
  manifest.update_tag_values("Monoroutine")
  manifest.save()

  report = {
    "generated_at": generated_at,
    "plc_path": plc_path,
    "target_program_name": target_program_name,
    "summary": {
      **context["summary"],
      "read_attempted": len(matched),
      "read_errors": sum(1 for value, error in values_by_fqn.values() if error is not None),
    },
    "resolutions": resolutions,
  }
  if report_path is not None:
    _write_json(Path(report_path), report)

  return report


def build_argument_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description=(
      "Read live PLC values for Monoroutine program tags by mapping each "
      "Monoroutine tag back to an unambiguous source routine tag and writing "
      "those values into Monoroutine/programTags.json. The PLC target program "
      f"name defaults to {DEFAULT_TARGET_PROGRAM_NAME}."
    )
  )
  parser.add_argument(
    "plc_path",
    nargs="?",
    default=DEFAULT_PLC_PATH,
    help=f"PLC connection path or IP address (default: {DEFAULT_PLC_PATH}).",
  )
  parser.add_argument(
    "--plc-root",
    type=Path,
    default=PLC_ROOT,
    help="PLC directory containing the original program exports and Monoroutine.",
  )
  parser.add_argument(
    "--report-path",
    type=Path,
    default=DEFAULT_REPORT_PATH,
    help="Optional JSON report path. Use an empty string to skip report output.",
  )
  parser.add_argument(
    "--target-program-name",
    default=DEFAULT_TARGET_PROGRAM_NAME,
    help=(
      "Program name on the PLC that contains the merged routine tags "
      f"(default: {DEFAULT_TARGET_PROGRAM_NAME})."
    ),
  )
  return parser


def main(argv=None) -> int:
  parser = build_argument_parser()
  args = parser.parse_args(argv)
  report_path = None if str(args.report_path).strip() == "" else args.report_path
  report = sync_monoroutine_tag_values(
    args.plc_path,
    plc_root=args.plc_root,
    report_path=report_path,
    target_program_name=args.target_program_name,
  )
  summary = report["summary"]
  print(
    f"synced {summary['matched']} Monoroutine tags from live PLC values; "
    f"skipped {summary['ambiguous']} ambiguous and {summary['unmatched']} unmatched tags"
  )
  if summary["read_errors"]:
    print(f"{summary['read_errors']} live PLC reads returned errors")
  if report_path is not None:
    print(f"wrote {report_path}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
