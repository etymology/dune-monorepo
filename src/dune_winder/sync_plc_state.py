"""
Synchronize local PLC metadata and ladder logic with a live PLC controller.

This script orchestrates three operations in sequence to ensure the local codebase
stays in sync with the actual PLC:

1. Regenerate .rll files from .rllscrap sources
   - Applies rung transformations and formula-aware handling
   - Resolves timer/counter arguments from tag definitions
   - Updates manifest with tag metadata

2. Export tag metadata from live PLC
   - Fetches tag definitions and structure from the controller
   - Creates/updates programTags.json for each program
   - Updates controller_level_tags.json

3. Export live tag values from PLC
   - Reads current values for all tags from the controller
   - Populates the "value" field in programTags.json
   - Adds "read_error" field for any tags that couldn't be read

Usage:
  python -m dune_winder.sync_plc_state <PLC_IP>              # full sync
  python -m dune_winder.sync_plc_state <PLC_IP> --dry-run    # preview only
  python -m dune_winder.sync_plc_state <PLC_IP> --rll-only   # regenerate .rll only
"""
import argparse
from pathlib import Path

from dune_winder.paths import PLC_ROOT
from dune_winder.convert_plc_rllscrap import convert_directory as regenerate_rll_files
from dune_winder.plc_metadata_export import (
    fetch_plc_snapshot,
    write_plc_snapshot,
)
from dune_winder.plc_tag_values_export import fetch_and_write_tag_values

DEFAULT_PLC_ROOT = PLC_ROOT


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Synchronize local PLC metadata, ladder logic, and tag values with a live "
            "Studio 5000 PLC. Runs three operations in sequence: (1) regenerate .rll "
            "files from .rllscrap sources, (2) export tag metadata from PLC, "
            "(3) export live tag values from PLC."
        )
    )
    parser.add_argument(
        "plc_path",
        help="PLC connection path or IP address for pycomm3 (e.g., 192.168.140.13).",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_PLC_ROOT,
        help="Directory containing plc/ metadata tree. Defaults to plc/ at repo root.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be synced without writing any files.",
    )
    parser.add_argument(
        "--rll-only",
        action="store_true",
        help="Regenerate .rll files only; skip PLC exports.",
    )
    parser.add_argument(
        "--main-routine-map",
        type=Path,
        default=None,
        help=(
            "Optional JSON file mapping program names to main routine names when "
            "they cannot be inferred automatically. Only used with metadata export."
        ),
    )
    return parser


def sync_plc(plc_path, output_root=DEFAULT_PLC_ROOT, dry_run=False, rll_only=False,
             main_routine_overrides=None):
    """
    Synchronize PLC state: regenerate .rll, export metadata, export tag values.

    Returns a dict with sync summary:
      {
        "rll_regenerated": int,
        "metadata_programs": int,
        "metadata_tags": int,
        "values_exported": int,
        "values_files": int,
      }
    """
    output_root = Path(output_root).resolve()
    if not output_root.is_dir():
        raise FileNotFoundError(f"Output root does not exist: {output_root}")

    result = {
        "rll_regenerated": 0,
        "metadata_programs": 0,
        "metadata_tags": 0,
        "values_exported": 0,
        "values_files": 0,
    }

    # Step 1: Regenerate .rll files from .rllscrap
    print("\n[1/3] Regenerating .rll files from .rllscrap...")
    rll_count = regenerate_rll_files(output_root, dry_run=dry_run)
    result["rll_regenerated"] = rll_count
    if dry_run:
        print(f"would regenerate {rll_count} .rll files")
    else:
        print(f"regenerated {rll_count} .rll files")

    if rll_only:
        print("\n[*] --rll-only specified; skipping PLC exports")
        return result

    # Step 2: Export tag metadata from live PLC
    print("\n[2/3] Exporting tag metadata from PLC...")
    if dry_run:
        try:
            snapshot = fetch_plc_snapshot(plc_path, main_routine_overrides)
            result["metadata_programs"] = len(snapshot["programs"])
            result["metadata_tags"] = len(snapshot["controller_level_tags"])
            print(
                f"would export {result['metadata_tags']} controller-level tags "
                f"and {result['metadata_programs']} programs"
            )
        except Exception as e:
            print(f"error fetching PLC snapshot: {e}")
            return result
    else:
        snapshot = fetch_plc_snapshot(plc_path, main_routine_overrides)
        result["metadata_programs"] = len(snapshot["programs"])
        result["metadata_tags"] = len(snapshot["controller_level_tags"])
        write_plc_snapshot(snapshot, output_root)
        print(
            f"exported {result['metadata_tags']} controller-level tags "
            f"and {result['metadata_programs']} programs"
        )

    # Step 3: Export live tag values from PLC
    print("\n[3/3] Exporting live tag values from PLC...")
    if dry_run:
        print("would read live tag values and update programTags.json")
    else:
        tag_result = fetch_and_write_tag_values(plc_path, output_root=output_root)
        result["values_exported"] = tag_result["tag_count"]
        result["values_files"] = tag_result["file_count"]
        print(
            f"exported values for {result['values_exported']} tags across "
            f"{result['values_files']} JSON files"
        )

    return result


def main(argv=None):
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    main_routine_overrides = None
    if args.main_routine_map:
        import json
        main_routine_overrides = json.loads(args.main_routine_map.read_text())

    try:
        result = sync_plc(
            args.plc_path,
            output_root=args.output_root,
            dry_run=args.dry_run,
            rll_only=args.rll_only,
            main_routine_overrides=main_routine_overrides,
        )

        print("\n" + "=" * 60)
        print("SYNC SUMMARY")
        print("=" * 60)
        print(f"  .rll files regenerated:     {result['rll_regenerated']}")
        print(f"  Programs exported:          {result['metadata_programs']}")
        print(f"  Controller-level tags:      {result['metadata_tags']}")
        print(f"  Tag values updated:         {result['values_exported']}")
        print(f"  JSON files written:         {result['values_files']}")
        if args.dry_run:
            print("\n  (dry-run; no files were modified)")
        print("=" * 60)

    except Exception as e:
        print(f"\nerror during sync: {e}")
        raise


if __name__ == "__main__":
    main()
