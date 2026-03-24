import argparse
import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from dune_winder.library.hash import Hash


MANIFEST_SCHEMA_VERSION = 1
METADATA_EXCLUDED_TOP_KEYS = frozenset({"generated_at", "values_generated_at"})
METADATA_EXCLUDED_TAG_KEYS = frozenset({"value", "read_error"})
DEFAULT_MANIFEST_PATH = Path(__file__).resolve().parents[2] / "plc" / "manifest.json"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _hash_text(text: str) -> str:
  normalized = text.replace("\r", "")
  h = Hash()
  h += normalized.encode("utf-8")
  return str(h)


def _strip_metadata_payload(payload: dict) -> dict:
  stripped = {k: v for k, v in payload.items() if k not in METADATA_EXCLUDED_TOP_KEYS}
  for tag_list_key in ("controller_level_tags", "program_tags"):
    if tag_list_key not in stripped:
      continue
    stripped[tag_list_key] = [
      {k: v for k, v in tag.items() if k not in METADATA_EXCLUDED_TAG_KEYS}
      for tag in stripped[tag_list_key]
    ]
  return stripped


def _compute_metadata_hash_from_payload(payload: dict) -> str:
  stripped = _strip_metadata_payload(payload)
  serialized = json.dumps(stripped, sort_keys=True)
  return _hash_text(serialized)


def _compute_values_hash_from_payload(payload: dict) -> str | None:
  if "values_generated_at" not in payload:
    return None
  tag_list_key = "controller_level_tags" if "controller_level_tags" in payload else "program_tags"
  tags = [
    {
      "fqn": tag["fully_qualified_name"],
      "value": tag.get("value"),
      "read_error": tag.get("read_error"),
    }
    for tag in payload.get(tag_list_key, [])
  ]
  values_payload = {
    "values_generated_at": payload["values_generated_at"],
    "tags": tags,
  }
  serialized = json.dumps(values_payload, sort_keys=True)
  return _hash_text(serialized)


def _now_iso() -> str:
  return datetime.now(timezone.utc).isoformat()


def _file_mtime_iso(path: Path) -> str:
  return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _iter_rllscrap_files(plc_root: Path) -> Iterator[Path]:
  if not plc_root.is_dir():
    return
  for program_dir in sorted(plc_root.iterdir()):
    if not program_dir.is_dir():
      continue
    for routine_dir in sorted(program_dir.iterdir()):
      if not routine_dir.is_dir():
        continue
      rllscrap = routine_dir / "studio_copy.rllscrap"
      if rllscrap.exists():
        yield rllscrap


def _iter_json_files(plc_root: Path) -> Iterator[tuple[str | None, Path]]:
  controller_path = plc_root / "controller_level_tags.json"
  if controller_path.exists():
    yield None, controller_path
  for path in sorted(plc_root.glob("*/programTags.json")):
    yield path.parent.name, path


# ---------------------------------------------------------------------------
# Public hash functions (used by both update methods and status command)
# ---------------------------------------------------------------------------

def compute_metadata_hash(path: Path) -> str | None:
  if not path.exists():
    return None
  payload = json.loads(path.read_text())
  return _compute_metadata_hash_from_payload(payload)


def compute_values_hash(path: Path) -> str | None:
  if not path.exists():
    return None
  payload = json.loads(path.read_text())
  return _compute_values_hash_from_payload(payload)


def compute_rllscrap_hash(path: Path) -> str:
  text = path.read_text(encoding="utf-8", errors="replace")
  return _hash_text(text)


# ---------------------------------------------------------------------------
# StatusRow
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class StatusRow:
  location: str    # "controller" or "motionQueue/main"
  category: str    # "tag_metadata" | "tag_values" | "rllscrap"
  stored_hash: str # "ABC-DEF-1234" or "(none)"
  captured_at: str # ISO timestamp or "(none)"
  state: str       # "ok" | "modified" | "missing" | "new"


def _make_json_status_row(
  location: str,
  category: str,
  entry: dict | None,
  json_path: Path,
  compute_fn,
) -> StatusRow | None:
  stored_hash = entry["hash"] if entry else "(none)"
  captured_at = entry.get("generated_at", "(none)") if entry else "(none)"

  if not json_path.exists():
    if entry is None:
      return None
    state = "missing"
  elif entry is None:
    current = compute_fn(json_path)
    if current is None:
      return None  # file exists but no applicable data (e.g. values not yet exported)
    state = "new"
  else:
    current = compute_fn(json_path)
    if current is None:
      state = "modified"  # had stored hash but data is now gone/inapplicable
    elif current == entry["hash"]:
      state = "ok"
    else:
      state = "modified"

  return StatusRow(
    location=location,
    category=category,
    stored_hash=stored_hash,
    captured_at=captured_at,
    state=state,
  )


# ---------------------------------------------------------------------------
# PlcManifest
# ---------------------------------------------------------------------------

class PlcManifest:
  def __init__(self, plc_root: Path):
    self._plc_root = Path(plc_root)
    self._manifest_path = self._plc_root / "manifest.json"
    self._data: dict = {}

  def load(self) -> None:
    if not self._manifest_path.exists():
      self._data = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "last_updated": _now_iso(),
        "controller": {},
        "programs": {},
      }
      return
    self._data = json.loads(self._manifest_path.read_text())

  def save(self) -> None:
    self._data["last_updated"] = _now_iso()
    tmp_path = self._manifest_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(self._data, indent=2, sort_keys=False) + "\n")
    tmp_path.replace(self._manifest_path)

  def _json_path_for(self, program_name: str | None) -> Path:
    if program_name is None:
      return self._plc_root / "controller_level_tags.json"
    return self._plc_root / program_name / "programTags.json"

  def _rllscrap_path_for(self, program_name: str, routine_name: str) -> Path:
    return self._plc_root / program_name / routine_name / "studio_copy.rllscrap"

  def update_tag_metadata(self, program_name: str | None) -> str | None:
    json_path = self._json_path_for(program_name)
    if not json_path.exists():
      return None
    payload = json.loads(json_path.read_text())
    hash_value = _compute_metadata_hash_from_payload(payload)
    generated_at = payload.get("generated_at", "")
    entry = {"hash": hash_value, "generated_at": generated_at}
    if program_name is None:
      self._data.setdefault("controller", {})["tag_metadata"] = entry
    else:
      self._data.setdefault("programs", {}).setdefault(program_name, {})["tag_metadata"] = entry
    return hash_value

  def update_tag_values(self, program_name: str | None) -> str | None:
    json_path = self._json_path_for(program_name)
    if not json_path.exists():
      return None
    payload = json.loads(json_path.read_text())
    hash_value = _compute_values_hash_from_payload(payload)
    if hash_value is None:
      return None
    generated_at = payload.get("values_generated_at", "")
    entry = {"hash": hash_value, "generated_at": generated_at}
    if program_name is None:
      self._data.setdefault("controller", {})["tag_values"] = entry
    else:
      self._data.setdefault("programs", {}).setdefault(program_name, {})["tag_values"] = entry
    return hash_value

  def update_rllscrap(self, program_name: str, routine_name: str) -> str:
    rllscrap_path = self._rllscrap_path_for(program_name, routine_name)
    hash_value = compute_rllscrap_hash(rllscrap_path)
    file_mtime = _file_mtime_iso(rllscrap_path)
    entry = {"hash": hash_value, "hashed_at": _now_iso(), "file_mtime": file_mtime}
    (
      self._data
      .setdefault("programs", {})
      .setdefault(program_name, {})
      .setdefault("routines", {})[routine_name]
    ) = entry
    return hash_value

  def scan_rllscrap(self) -> list[tuple[str, str, str]]:
    results = []
    for rllscrap_path in _iter_rllscrap_files(self._plc_root):
      routine_name = rllscrap_path.parent.name
      program_name = rllscrap_path.parent.parent.name
      hash_value = self.update_rllscrap(program_name, routine_name)
      results.append((program_name, routine_name, hash_value))
    return results

  def status(self) -> list[StatusRow]:
    rows: list[StatusRow] = []

    # Controller
    controller_entry = self._data.get("controller", {})
    controller_json = self._plc_root / "controller_level_tags.json"
    for category, compute_fn in (
      ("tag_metadata", compute_metadata_hash),
      ("tag_values", compute_values_hash),
    ):
      row = _make_json_status_row(
        "controller", category, controller_entry.get(category), controller_json, compute_fn
      )
      if row is not None:
        rows.append(row)

    # Programs — union of manifest entries and filesystem
    all_programs: set[str] = set(self._data.get("programs", {}).keys())
    if self._plc_root.is_dir():
      for program_dir in self._plc_root.iterdir():
        if program_dir.is_dir() and (program_dir / "programTags.json").exists():
          all_programs.add(program_dir.name)

    for program_name in sorted(all_programs):
      program_entry = self._data.get("programs", {}).get(program_name, {})
      json_path = self._plc_root / program_name / "programTags.json"

      for category, compute_fn in (
        ("tag_metadata", compute_metadata_hash),
        ("tag_values", compute_values_hash),
      ):
        row = _make_json_status_row(
          program_name, category, program_entry.get(category), json_path, compute_fn
        )
        if row is not None:
          rows.append(row)

      # Routines — union of manifest entries and filesystem
      all_routines: set[str] = set(program_entry.get("routines", {}).keys())
      program_dir = self._plc_root / program_name
      if program_dir.is_dir():
        for routine_dir in program_dir.iterdir():
          if routine_dir.is_dir() and (routine_dir / "studio_copy.rllscrap").exists():
            all_routines.add(routine_dir.name)

      for routine_name in sorted(all_routines):
        routine_entry = program_entry.get("routines", {}).get(routine_name)
        rllscrap_path = self._plc_root / program_name / routine_name / "studio_copy.rllscrap"

        stored_hash = routine_entry["hash"] if routine_entry else "(none)"
        captured_at = routine_entry.get("hashed_at", "(none)") if routine_entry else "(none)"

        if not rllscrap_path.exists():
          if routine_entry is None:
            continue
          state = "missing"
        elif routine_entry is None:
          state = "new"
        else:
          current_hash = compute_rllscrap_hash(rllscrap_path)
          state = "ok" if current_hash == routine_entry["hash"] else "modified"

        rows.append(StatusRow(
          location=f"{program_name}/{routine_name}",
          category="rllscrap",
          stored_hash=stored_hash,
          captured_at=captured_at,
          state=state,
        ))

    return rows


# ---------------------------------------------------------------------------
# Best-effort rllscrap manifest update (called from plc_rung_transform)
# ---------------------------------------------------------------------------

def _try_update_rllscrap_manifest(input_path: Path) -> None:
  try:
    parts = list(input_path.resolve().parts)
    lowered = [p.lower() for p in parts]
    plc_index = next((i for i, p in enumerate(lowered) if p == "plc"), None)
    if plc_index is None or len(parts) - plc_index < 4:
      return
    plc_root = Path(*parts[:plc_index + 1])
    program_name = parts[plc_index + 1]
    routine_name = parts[plc_index + 2]
    manifest = PlcManifest(plc_root)
    manifest.load()
    manifest.update_rllscrap(program_name, routine_name)
    manifest.save()
  except Exception:
    pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_status_table(rows: list[StatusRow]) -> None:
  if not rows:
    print("No artifacts tracked.")
    return
  headers = ("Location", "Category", "Hash", "Captured At", "State")
  col_widths = [len(h) for h in headers]
  for row in rows:
    col_widths[0] = max(col_widths[0], len(row.location))
    col_widths[1] = max(col_widths[1], len(row.category))
    col_widths[2] = max(col_widths[2], len(row.stored_hash))
    col_widths[3] = max(col_widths[3], len(row.captured_at))
    col_widths[4] = max(col_widths[4], len(row.state))
  fmt = "  ".join(f"{{:<{w}}}" for w in col_widths)
  print(fmt.format(*headers))
  print("  ".join("-" * w for w in col_widths))
  for row in rows:
    print(fmt.format(row.location, row.category, row.stored_hash, row.captured_at, row.state))


def main(argv=None):
  parser = argparse.ArgumentParser(
    description="Manage PLC artifact hashes and freshness manifest."
  )
  subparsers = parser.add_subparsers(dest="command", required=True)

  scan_parser = subparsers.add_parser("scan", help="Hash all .rllscrap files and update manifest.")
  scan_parser.add_argument(
    "--plc-root",
    type=Path,
    default=DEFAULT_MANIFEST_PATH.parent,
    help="plc/ directory to scan.",
  )

  status_parser = subparsers.add_parser("status", help="Print artifact freshness table.")
  status_parser.add_argument(
    "--plc-root",
    type=Path,
    default=DEFAULT_MANIFEST_PATH.parent,
    help="plc/ directory to check.",
  )

  sync_parser = subparsers.add_parser(
    "sync",
    help="Auto-sync tag metadata and values from PLC, then report rllscrap gaps.",
  )
  sync_parser.add_argument("plc_path", help="PLC IP address or connection path.")
  sync_parser.add_argument(
    "--plc-root",
    type=Path,
    default=DEFAULT_MANIFEST_PATH.parent,
    help="plc/ directory to populate.",
  )

  args = parser.parse_args(argv)

  if args.command == "scan":
    manifest = PlcManifest(args.plc_root)
    manifest.load()
    results = manifest.scan_rllscrap()
    for program_name, routine_name, hash_value in results:
      print(f"updated {program_name}/{routine_name}  {hash_value}")
    manifest.save()

  elif args.command == "status":
    manifest = PlcManifest(args.plc_root)
    manifest.load()
    rows = manifest.status()
    _print_status_table(rows)

  elif args.command == "sync":
    from dune_winder.plc_metadata_export import fetch_plc_snapshot, write_plc_snapshot
    from dune_winder.plc_tag_values_export import fetch_and_write_tag_values

    print(f"Fetching tag metadata from {args.plc_path}...")
    snapshot = fetch_plc_snapshot(args.plc_path)
    write_plc_snapshot(snapshot, args.plc_root)
    print(
      f"  exported {len(snapshot['controller_level_tags'])} controller-level tags "
      f"and {len(snapshot['programs'])} programs"
    )

    print("Fetching tag values...")
    result = fetch_and_write_tag_values(args.plc_path, output_root=args.plc_root)
    print(
      f"  exported values for {result['tag_count']} tags "
      f"across {result['file_count']} JSON files"
    )

    manifest = PlcManifest(args.plc_root)
    manifest.load()
    rows = manifest.status()
    gaps = [r for r in rows if r.category == "rllscrap" and r.state in ("new", "modified", "missing")]
    if gaps:
      print("\nRLL scrap files requiring manual Studio 5000 paste:")
      for row in gaps:
        print(f"  {row.location}  [{row.state}]")
    else:
      print("\nAll rllscrap files are current.")


if __name__ == "__main__":
  main()
