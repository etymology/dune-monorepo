"""Unified PLC sync entry point.

Three phases, each independently skippable:

1. Tag metadata: pull tag/UDT/program definitions from a live PLC into
   ``controller_level_tags.json`` and ``<program>/programTags.json``.
2. Tag values: pull current tag values into the same JSON files.
3. RLL conversion: regenerate every ``pasteable.rll`` from its sibling
   ``studio_copy.rllscrap`` and refresh ``manifest.json``.

The ``--offline`` mode runs only phase 3 — it is the one agents and the
pre-commit hook need when ``studio_copy.rllscrap`` files are edited
without live PLC access.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dune_winder.convert_plc_rllscrap import convert_directory
from dune_winder.paths import PLC_ROOT
from dune_winder.plc_manifest import PlcManifest


DEFAULT_PLC_PATH = "192.168.140.13"


def _run_metadata(
    plc_path: str, output_root: Path, main_routine_map: Path | None
) -> None:
    from dune_winder.plc_metadata_export import (
        _load_main_routine_overrides,
        fetch_plc_snapshot,
        write_plc_snapshot,
    )

    overrides = _load_main_routine_overrides(main_routine_map)
    snapshot = fetch_plc_snapshot(plc_path, main_routine_overrides=overrides)
    write_plc_snapshot(snapshot, output_root)
    print(
        f"metadata: {len(snapshot['controller_level_tags'])} controller tags, "
        f"{len(snapshot['programs'])} programs -> {output_root}"
    )


def _run_values(plc_path: str, output_root: Path) -> None:
    from dune_winder.plc_tag_values_export import fetch_and_write_tag_values

    result = fetch_and_write_tag_values(plc_path, output_root=output_root)
    print(
        f"values: {result['tag_count']} tags across {result['file_count']} JSON files"
    )


def _run_convert(plc_root: Path, dry_run: bool) -> int:
    converted = convert_directory(plc_root, dry_run=dry_run)
    print(f"convert: {converted} routine(s) processed")
    return converted


def _refresh_manifest(plc_root: Path) -> None:
    manifest = PlcManifest(plc_root)
    manifest.load()
    manifest.scan_rllscrap()
    manifest.save()


def _print_status(plc_root: Path) -> None:
    manifest = PlcManifest(plc_root)
    manifest.load()
    rows = manifest.status()
    drift = [r for r in rows if r.state not in ("ok",)]
    if not drift:
        print("status: all artifacts current")
        return
    print("status: drift detected")
    for row in drift:
        print(f"  {row.location:<40} {row.category:<14} {row.state}")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Sync PLC tag metadata, tag values, and regenerate pasteable.rll "
            "files from studio_copy.rllscrap."
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
        help="plc/ directory to populate. Defaults to dune_winder/plc/.",
    )
    parser.add_argument(
        "--main-routine-map",
        type=Path,
        default=None,
        help="Optional JSON file mapping program names to main routine names.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Skip the live PLC fetch. Only convert studio_copy.rllscrap files "
            "and refresh the manifest. Use this in agent / pre-commit flows."
        ),
    )
    parser.add_argument(
        "--no-metadata",
        action="store_true",
        help="Skip the tag metadata fetch (still fetches values unless --offline).",
    )
    parser.add_argument(
        "--no-values",
        action="store_true",
        help="Skip the tag values fetch (still fetches metadata unless --offline).",
    )
    parser.add_argument(
        "--no-convert",
        action="store_true",
        help="Skip the studio_copy.rllscrap -> pasteable.rll conversion.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing files.",
    )
    return parser


def main(argv=None) -> None:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    plc_root = args.plc_root.resolve()

    run_metadata = not args.offline and not args.no_metadata
    run_values = not args.offline and not args.no_values
    run_convert = not args.no_convert

    if run_metadata:
        if args.dry_run:
            print(f"would fetch metadata from {args.plc_path} -> {plc_root}")
        else:
            _run_metadata(args.plc_path, plc_root, args.main_routine_map)

    if run_values:
        if args.dry_run:
            print(f"would fetch tag values from {args.plc_path} -> {plc_root}")
        else:
            _run_values(args.plc_path, plc_root)

    if run_convert:
        _run_convert(plc_root, args.dry_run)
        if not args.dry_run:
            _refresh_manifest(plc_root)

    _print_status(plc_root)


if __name__ == "__main__":
    main()
