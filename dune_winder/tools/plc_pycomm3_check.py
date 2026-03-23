from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class WriteRequest:
  tag: str
  value: object


def _parse_value(text: str):
  try:
    return ast.literal_eval(text)
  except (SyntaxError, ValueError):
    lowered = text.strip().lower()
    if lowered == "true":
      return True
    if lowered == "false":
      return False
    return text


def _parse_write_request(text: str) -> WriteRequest:
  if "=" not in text:
    raise argparse.ArgumentTypeError("write must use TAG=VALUE form")
  tag, raw_value = text.split("=", 1)
  tag = tag.strip()
  if not tag:
    raise argparse.ArgumentTypeError("write tag name cannot be empty")
  return WriteRequest(tag=tag, value=_parse_value(raw_value.strip()))


def _normalize_read_result(result):
  return {
    "tag": getattr(result, "tag", None),
    "value": getattr(result, "value", None),
    "type": getattr(result, "type", None),
    "error": str(getattr(result, "error", None)) if getattr(result, "error", None) else None,
  }


def _normalize_write_result(result):
  return {
    "tag": getattr(result, "tag", None),
    "value": getattr(result, "value", None),
    "type": getattr(result, "type", None),
    "error": str(getattr(result, "error", None)) if getattr(result, "error", None) else None,
  }


def _collect_reads(driver, tags: list[str]) -> list[dict[str, object]]:
  if not tags:
    return []
  results = driver.read(*tags)
  if not isinstance(results, list):
    results = [results]
  return [_normalize_read_result(result) for result in results]


def run_check(
  plc_path: str,
  read_tags: list[str],
  write_requests: list[WriteRequest],
  *,
  restore: bool,
  init_tags: bool,
  init_program_tags: bool,
):
  from pycomm3 import LogixDriver

  report: dict[str, object] = {
    "plc_path": plc_path,
    "connected": False,
    "reads_before": [],
    "writes": [],
    "reads_after": [],
    "restores": [],
  }

  with LogixDriver(
    plc_path,
    init_tags=init_tags,
    init_program_tags=init_program_tags,
  ) as driver:
    report["connected"] = bool(driver.connected)
    report["info"] = dict(driver.info or {})

    existing_tags = getattr(driver, "tags", None)
    if existing_tags is not None:
      report["online_tag_count"] = len(existing_tags)

    original_values: dict[str, object] = {}
    if read_tags:
      report["reads_before"] = _collect_reads(driver, read_tags)

    for request in write_requests:
      original = driver.read(request.tag)
      original_values[request.tag] = getattr(original, "value", None)
      write_result = driver.write((request.tag, request.value))
      if isinstance(write_result, list):
        normalized = [_normalize_write_result(item) for item in write_result]
      else:
        normalized = [_normalize_write_result(write_result)]
      report["writes"].append(
        {
          "tag": request.tag,
          "requested_value": request.value,
          "original_value": original_values[request.tag],
          "results": normalized,
        }
      )

    tags_to_verify = list(dict.fromkeys(read_tags + [request.tag for request in write_requests]))
    if tags_to_verify:
      report["reads_after"] = _collect_reads(driver, tags_to_verify)

    if restore:
      for request in write_requests:
        restore_result = driver.write((request.tag, original_values[request.tag]))
        if isinstance(restore_result, list):
          normalized = [_normalize_write_result(item) for item in restore_result]
        else:
          normalized = [_normalize_write_result(restore_result)]
        report["restores"].append(
          {
            "tag": request.tag,
            "restored_value": original_values[request.tag],
            "results": normalized,
          }
        )

  return report


def build_argument_parser():
  parser = argparse.ArgumentParser(
    description="Connect to a Rockwell PLC with pycomm3, read tags, optionally write tags, and optionally restore them.",
  )
  parser.add_argument("plc_path", help="PLC IP or pycomm3 connection path.")
  parser.add_argument(
    "--read",
    dest="read_tags",
    action="append",
    default=[],
    help="Tag to read. Repeat for multiple tags.",
  )
  parser.add_argument(
    "--write",
    dest="write_requests",
    action="append",
    type=_parse_write_request,
    default=[],
    help="Tag write in TAG=VALUE form. VALUE is parsed with Python literal syntax.",
  )
  parser.add_argument(
    "--no-restore",
    dest="restore",
    action="store_false",
    help="Do not restore written tags to their original values.",
  )
  parser.add_argument(
    "--no-init-tags",
    dest="init_tags",
    action="store_false",
    help="Skip pycomm3 tag discovery on connect.",
  )
  parser.add_argument(
    "--no-init-program-tags",
    dest="init_program_tags",
    action="store_false",
    help="Skip pycomm3 program tag discovery on connect.",
  )
  parser.set_defaults(restore=True, init_tags=True, init_program_tags=True)
  return parser


def main(argv=None):
  parser = build_argument_parser()
  args = parser.parse_args(argv)
  report = run_check(
    args.plc_path,
    args.read_tags,
    args.write_requests,
    restore=args.restore,
    init_tags=args.init_tags,
    init_program_tags=args.init_program_tags,
  )
  print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
  main()
