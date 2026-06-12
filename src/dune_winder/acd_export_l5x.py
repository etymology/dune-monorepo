"""Regenerate the winder/plc/ tree from the Studio 5000 .ACD project file.

This is the PLC import pipeline (see
``plans/llm-friendly-ladder-language-to-l5x.md``). The ACD saved by Studio
5000 is the source of truth for ladder logic and tag *metadata*; the live
controller is the source of truth for tag *values*. One run regenerates
everything that used to be hand-copied out of Studio or exported with
separate scripts:

1. ``<program>/<routine>_Routine_RLL.L5X`` — per-routine L5X (rung text is
   byte-identical to Studio's own "Export Routine" output).
2. ``<program>/<routine-dir>/studio_copy.rllscrap`` — the paren-dialect rung
   text, previously hand-copied from Studio's clipboard. The main routine
   keeps the historical ``main/`` directory name.
3. ``<program>/programTags.json`` and ``controller_level_tags.json`` — tag
   metadata in the same schema the pycomm3 exporters produced (the ladder
   simulator and rung transform read these), built from the ACD's internal
   ``TagInfo.XML``.
4. Live tag values merged into those JSON files via the existing
   ``plc_tag_values_export`` reader (``--offline`` carries values forward
   from the previous export instead).
5. ``pasteable.rll`` + ``manifest.json`` via the existing
   ``convert_plc_rllscrap`` pipeline.
6. ``acd_index.json`` — provenance: which ACD bytes (sha256, save-log entry)
   produced the tree, plus a sha256 for every generated file.

The ACD container stores ladder logic as records in internal databases:
``Comps.Dat`` (component tree: controller -> programs -> routines) and
``SbRegion.Dat`` (rung neutral text with tag operands as ``@<object-id>@``
references). The third-party ``acd-tools`` library extracts those into
SQLite; this module walks the result directly (its high-level L5X builder
is broken for this project).

Known gaps versus the data Studio holds:

- No alias targets (``TagInfo.XML`` lists aliases like ``X_POSITION`` as
  plain tags of the aliased type).
- No rung comments (their linkage inside ``Comments.Dat`` is not reverse
  engineered).
- Pending-edit rungs in the ACD are emitted with L5X ``Type="e"`` and are
  included in the rllscrap output in display order.

Usage:
    uv run plc-acd-export [ACD_FILE] [--plc IP] [--offline] [--output-root DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from sqlite3 import Cursor

from dune_winder.paths import PLC_ROOT

DEFAULT_ACD = PLC_ROOT / "ACD" / "DUNEW2PLC1_py3.ACD"
DEFAULT_PLC_PATH = "192.168.140.13"
INDEX_NAME = "acd_index.json"

#: region_map.seq_no value marking a pending-edit rung (Studio shows these
#: as rung Type="e"; finalized rungs are Type="N").
PENDING_EDIT_SEQ = 0xFFFFFFFF

EXPORT_OPTIONS = (
    "References NoRawData L5KData DecoratedData Context Dependencies "
    "ForceProtectedEncoding AllProjDocTrans"
)

#: Logix atomic types as pycomm3 reports them; everything else is a struct
#: whose layout lives in the udts list.
ATOMIC_TYPES = {
    "BOOL",
    "SINT",
    "INT",
    "DINT",
    "LINT",
    "USINT",
    "UINT",
    "UDINT",
    "ULINT",
    "REAL",
    "LREAL",
    "BYTE",
    "WORD",
    "DWORD",
    "LWORD",
}


@dataclass
class Rung:
    number: int
    rung_type: str  # "N" normal, "e" pending edit
    text: str


@dataclass
class Routine:
    name: str
    routine_type: str
    rungs: list[Rung]


@dataclass
class Program:
    name: str
    routines: list[Routine]

    @property
    def main_routine(self) -> tuple[str | None, str]:
        names = [routine.name for routine in self.routines]
        if "main" in names:
            return "main", "named_main"
        if len(names) == 1:
            return names[0], "single_routine"
        return None, "unresolved"


@dataclass
class AcdProject:
    controller_name: str
    software_revision: str
    programs: list[Program]


@dataclass
class TagInfo:
    """Tag metadata parsed from the ACD's internal TagInfo.XML."""

    data_types: list[dict]
    controller_tags: list[dict]
    program_tags: dict[str, list[dict]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ACD provenance
# ---------------------------------------------------------------------------

SAVE_LOG_PATTERN = re.compile(
    rb"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+): Saved - (V[\d./]+)"
)


def acd_provenance(acd_file: Path) -> dict:
    """Identify the exact ACD that produced an extraction.

    The sha256 pins the bytes; ``last_saved`` is the newest entry of the
    save log Studio keeps in the ACD's text header, which identifies the
    save even after the file is copied around. Studio rewrites the ACD
    while the project is open, so extractions must be traceable to a
    specific save, not just a filename.
    """
    data = acd_file.read_bytes()
    # The header save log is a ring buffer (newest entries overwrite the
    # oldest region), so file order is not chronological — take the max.
    saves = SAVE_LOG_PATTERN.findall(data[:262144])
    last = max(saves, key=lambda s: s[0]) if saves else None
    stat = acd_file.stat()
    return {
        "file": acd_file.name,
        "path": str(acd_file),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(stat.st_mtime)),
        "last_saved": last[0].decode() if last else None,
        "studio_version": last[1].decode() if last else None,
        "save_log_entries": len(saves),
    }


# ---------------------------------------------------------------------------
# ACD database extraction (routines and rungs)
# ---------------------------------------------------------------------------


def _build_database(acd_file: Path, temp_dir: str):
    """Run acd-tools' extraction (ACD -> internal .Dat files -> SQLite).

    Returns the exporter; callers must close ``exporter._db`` so the
    temporary directory can be removed on Windows.
    """
    from acd.l5x.export_l5x import ExportL5x

    return ExportL5x(acd_file, _temp_dir=temp_dir)


def _software_revision(temp_dir: str) -> str:
    quick_info = Path(temp_dir) / "QuickInfo.XML"
    try:
        text = quick_info.read_bytes().decode("utf-16-le", errors="replace")
        match = re.search(r'<DeviceRevision\s+Major="(\d+)"\s+Minor="(\d+)"', text)
        if match:
            return f"{match.group(1)}.{int(match.group(2)):02d}"
        match = re.search(r"V(\d+)\.(\d+)", text)
        if match:
            return f"{match.group(1)}.{match.group(2)}"
    except OSError:
        pass
    return "33.00"


def _resolve_module_refs(cur: Cursor, text: str) -> str:
    """Resolve leftover ``&xxxxxxxx`` references to component names.

    acd-tools resolves most ``@id@`` tag references while loading SbRegion,
    but emits ``&<hex-id>`` when the component is outside the scopes it
    searches (in practice: I/O module references like ``Local:1:I``).
    """

    def replace(match: re.Match[str]) -> str:
        object_id = int(match.group(1), 16)
        row = cur.execute(
            "SELECT comp_name FROM comps WHERE object_id=?", (object_id,)
        ).fetchone()
        return row[0] if row else match.group(0)

    return re.sub(r"&([0-9a-f]{8})", replace, text)


def _routine_type(cur: Cursor, routine_id: int, has_rungs: bool) -> str:
    from acd.generated.comps.rx_generic import RxGeneric
    from acd.l5x.elements import routine_type_enum

    row = cur.execute(
        "SELECT record FROM comps WHERE object_id=?", (routine_id,)
    ).fetchone()
    try:
        generic = RxGeneric.from_bytes(row[0])
        parsed = routine_type_enum(struct.unpack_from("<H", generic.record_buffer, 0x30)[0])
    except Exception:
        parsed = "Typeless"
    if parsed in ("TypeLess", "Typeless") and has_rungs:
        return "RLL"
    return parsed


def _read_routine(cur: Cursor, routine_id: int, name: str) -> Routine:
    entries = cur.execute(
        "SELECT object_id, unknown, seq_no FROM region_map"
        " WHERE parent_id=? ORDER BY unknown",
        (routine_id,),
    ).fetchall()
    rungs: list[Rung] = []
    for object_id, number, seq_no in entries:
        row = cur.execute(
            "SELECT rung FROM rungs WHERE object_id=?", (object_id,)
        ).fetchone()
        if row is None:
            raise ValueError(
                f"routine {name}: rung object {object_id:#x} missing from SbRegion"
            )
        rung_type = "e" if seq_no == PENDING_EDIT_SEQ else "N"
        rungs.append(Rung(number, rung_type, _resolve_module_refs(cur, row[0])))
    return Routine(name, _routine_type(cur, routine_id, bool(rungs)), rungs)


def read_project(cur: Cursor, software_revision: str) -> AcdProject:
    controller = cur.execute(
        "SELECT object_id, comp_name FROM comps WHERE parent_id=0 AND record_type=256"
    ).fetchone()
    if controller is None:
        raise ValueError("no controller record found in Comps database")
    controller_id, controller_name = controller

    program_collection = cur.execute(
        "SELECT object_id FROM comps"
        " WHERE parent_id=? AND comp_name='RxProgramCollection'",
        (controller_id,),
    ).fetchone()[0]

    programs: list[Program] = []
    for program_id, program_name in cur.execute(
        "SELECT object_id, comp_name FROM comps WHERE parent_id=?"
        " ORDER BY seq_number",
        (program_collection,),
    ).fetchall():
        routine_collection = cur.execute(
            "SELECT object_id FROM comps"
            " WHERE parent_id=? AND comp_name='RxRoutineCollection'",
            (program_id,),
        ).fetchone()
        routines: list[Routine] = []
        if routine_collection is not None:
            for routine_id, routine_name in cur.execute(
                "SELECT object_id, comp_name FROM comps WHERE parent_id=?"
                " ORDER BY seq_number",
                (routine_collection[0],),
            ).fetchall():
                routines.append(_read_routine(cur, routine_id, routine_name))
        programs.append(Program(program_name, routines))
    return AcdProject(controller_name, software_revision, programs)


# ---------------------------------------------------------------------------
# TagInfo.XML parsing
# ---------------------------------------------------------------------------


def _dimensions(element: ET.Element) -> list[int]:
    dims = element.find("Dimensions")
    if dims is None:
        return []
    return [int(dim.get("Size", "0")) for dim in dims.findall("Dim")]


def _description(element: ET.Element) -> str | None:
    desc = element.find("Description")
    if desc is None or desc.text is None:
        return None
    return desc.text.strip()


def _tag_to_dict(tag: ET.Element) -> dict:
    out: dict = {"name": tag.get("Name"), "data_type": tag.get("DataType")}
    dimensions = _dimensions(tag)
    if dimensions:
        out["dimensions"] = dimensions
    description = _description(tag)
    if description:
        out["description"] = description
    return out


def _member_to_dict(member: ET.Element) -> dict:
    out = _tag_to_dict(member)
    out["offset"] = int(member.get("Offset", "0"))
    if member.get("Bit") is not None:
        out["bit"] = int(member.get("Bit"))
    if member.get("Hidden") == "true":
        out["hidden"] = True
    return out


def _data_type_to_dict(data_type: ET.Element) -> dict:
    members = data_type.find("Members")
    return {
        "name": data_type.get("Name"),
        "size": int(data_type.get("Size", "0")),
        "members": [
            _member_to_dict(m) for m in (members if members is not None else [])
        ],
    }


def parse_tag_info(temp_dir: str) -> TagInfo:
    raw = (Path(temp_dir) / "TagInfo.XML").read_bytes()
    root = ET.fromstring(raw.decode("utf-16"))

    data_types_el = root.find("DataTypes")
    data_types = [
        _data_type_to_dict(dt)
        for dt in (data_types_el if data_types_el is not None else [])
    ]

    tags_el = root.find("Tags")
    controller_tags = [
        _tag_to_dict(t) for t in (tags_el if tags_el is not None else [])
    ]

    program_tags: dict[str, list[dict]] = {}
    programs_el = root.find("Programs")
    for program in programs_el if programs_el is not None else []:
        prog_tags_el = program.find("Tags")
        program_tags[program.get("Name", "?")] = [
            _tag_to_dict(t) for t in (prog_tags_el if prog_tags_el is not None else [])
        ]
    return TagInfo(data_types, controller_tags, program_tags)


# ---------------------------------------------------------------------------
# Legacy-schema tag metadata (programTags.json / controller_level_tags.json)
# ---------------------------------------------------------------------------


def _legacy_tag_entry(tag: dict, program: str | None) -> dict:
    """Convert a TagInfo tag to the schema the pycomm3 exporters produced.

    Mirrors pycomm3's representation so the ladder simulator and the
    tag-values reader behave identically: BOOL arrays are reported packed
    as DWORD (one element per 32 bits) and dimensions are a 3-list.
    """
    data_type = tag["data_type"]
    dims = list(tag.get("dimensions", []))
    if data_type == "BOOL" and dims:
        data_type = "DWORD"
        dims[0] = max(1, dims[0] // 32)
    name = tag["name"]
    entry: dict = {
        "name": name,
        "fully_qualified_name": f"Program:{program}.{name}" if program else name,
        "tag_type": "atomic" if data_type in ATOMIC_TYPES else "struct",
        "data_type_name": data_type,
        "dimensions": (dims + [0, 0, 0])[:3],
        "array_dimensions": len([d for d in dims if d]),
    }
    if entry["tag_type"] == "struct":
        entry["udt_name"] = data_type
    if program:
        entry["program"] = program
    if tag.get("description"):
        entry["description"] = tag["description"]
    return entry


def _legacy_udt(data_type: dict) -> dict:
    fields = []
    for member in data_type["members"]:
        member_type = member["data_type"]
        entry: dict = {
            "name": member["name"],
            "tag_type": "atomic" if member_type in ATOMIC_TYPES else "struct",
            "data_type_name": member_type,
            "offset": member["offset"],
        }
        if "bit" in member:
            entry["bit"] = member["bit"]
        dims = member.get("dimensions", [])
        if dims:
            entry["array_length"] = dims[0]
        if member.get("hidden"):
            entry["hidden"] = True
        fields.append(entry)
    return {"name": data_type["name"], "fields": fields}


def _carry_forward_values(entries: list[dict], previous: dict | None, key: str) -> str | None:
    """Copy value/read_error from a previous export into fresh entries.

    Used in --offline runs so regeneration does not wipe the values the
    simulator initializes from. Returns the previous values timestamp.
    """
    if not previous:
        return None
    by_name = {
        tag.get("fully_qualified_name"): tag for tag in previous.get(key, [])
    }
    for entry in entries:
        old = by_name.get(entry["fully_qualified_name"])
        if old is None or "value" not in old:
            continue
        entry["value"] = old["value"]
        if "read_error" in old:
            entry["read_error"] = old["read_error"]
    return previous.get("values_generated_at")


def _load_previous(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Artifact rendering
# ---------------------------------------------------------------------------


def _cdata(text: str) -> str:
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def render_routine_l5x(project: AcdProject, program: Program, routine: Routine) -> str:
    """Render one routine as Studio-compatible L5X (sans tag context)."""
    export_date = time.asctime()
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<RSLogix5000Content SchemaRevision="1.0"'
        f' SoftwareRevision="{project.software_revision}"'
        f' TargetName="{routine.name}" TargetType="Routine"'
        f' TargetSubType="{routine.routine_type}" TargetClass="Standard"'
        f' ContainsContext="true" ExportDate="{export_date}"'
        f' ExportOptions="{EXPORT_OPTIONS}">',
        f'<Controller Use="Context" Name="{project.controller_name}">',
        '<Programs Use="Context">',
        f'<Program Use="Context" Name="{program.name}" Class="Standard">',
        '<Routines Use="Context">',
    ]
    if routine.rungs:
        lines.append(
            f'<Routine Use="Target" Name="{routine.name}" Type="{routine.routine_type}">'
        )
        lines.append("<RLLContent>")
        for rung in routine.rungs:
            lines.append(f'<Rung Number="{rung.number}" Type="{rung.rung_type}">')
            lines.append("<Text>")
            lines.append(_cdata(rung.text))
            lines.append("</Text>")
            lines.append("</Rung>")
        lines.append("</RLLContent>")
        lines.append("</Routine>")
    else:
        lines.append(
            f'<Routine Use="Target" Name="{routine.name}" Type="{routine.routine_type}"/>'
        )
    for sibling in program.routines:
        if sibling.name != routine.name:
            lines.append(f'<Routine Use="Reference" Name="{sibling.name}">')
            lines.append("</Routine>")
    lines += ["</Routines>", "</Program>", "</Programs>", "</Controller>", "</RSLogix5000Content>"]
    return "\r\n".join(lines) + "\r\n"


def render_rllscrap(routine: Routine) -> str:
    """Concatenate rung text the way Studio's clipboard copy does."""
    return "   ".join(rung.text for rung in routine.rungs) + "\n"


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_tree(
    project: AcdProject,
    tag_info: TagInfo,
    output_root: Path,
    provenance: dict,
    plc_path: str | None,
    offline: bool,
) -> list[Path]:
    """Write L5X, rllscrap, and tag-metadata JSON for every program."""
    written: list[Path] = []
    generated_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    for program in project.programs:
        program_dir = output_root / program.name
        program_dir.mkdir(parents=True, exist_ok=True)
        main_routine, main_source = program.main_routine

        for routine in program.routines:
            l5x_path = program_dir / f"{routine.name}_Routine_RLL.L5X"
            content = render_routine_l5x(project, program, routine)
            l5x_path.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
            written.append(l5x_path)

            routine_dir = program_dir / (
                "main" if routine.name == main_routine else routine.name
            )
            routine_dir.mkdir(exist_ok=True)
            rllscrap_path = routine_dir / "studio_copy.rllscrap"
            rllscrap_path.write_text(render_rllscrap(routine), encoding="utf-8")
            written.append(rllscrap_path)

        program_tag_entries = [
            _legacy_tag_entry(tag, program.name)
            for tag in tag_info.program_tags.get(program.name, [])
        ]
        referenced_udts = {
            entry["udt_name"]
            for entry in program_tag_entries
            if entry.get("udt_name")
        }
        tags_path = program_dir / "programTags.json"
        previous_values_at = None
        if offline:
            previous_values_at = _carry_forward_values(
                program_tag_entries, _load_previous(tags_path), "program_tags"
            )
        routine_names = sorted(r.name for r in program.routines)
        payload = {
            "schema_version": 1,
            "generated_at": generated_at,
            "plc_path": plc_path,
            "source_acd": provenance,
            "program_name": program.name,
            "main_routine_name": main_routine,
            "main_routine_name_source": main_source,
            "routines": routine_names,
            "subroutines": [n for n in routine_names if n != main_routine],
            "udts": [
                _legacy_udt(dt)
                for dt in tag_info.data_types
                if dt["name"] in referenced_udts
            ],
            "program_tags": program_tag_entries,
        }
        if previous_values_at:
            payload["values_generated_at"] = previous_values_at
        _write_json(tags_path, payload)
        written.append(tags_path)

    controller_entries = [
        _legacy_tag_entry(tag, None) for tag in tag_info.controller_tags
    ]
    controller_path = output_root / "controller_level_tags.json"
    previous_values_at = None
    if offline:
        previous_values_at = _carry_forward_values(
            controller_entries, _load_previous(controller_path), "controller_level_tags"
        )
    payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "plc_path": plc_path,
        "source_acd": provenance,
        "controller": {"name": project.controller_name},
        "udts": [_legacy_udt(dt) for dt in tag_info.data_types],
        "controller_level_tags": controller_entries,
    }
    if previous_values_at:
        payload["values_generated_at"] = previous_values_at
    _write_json(controller_path, payload)
    written.append(controller_path)
    return written


def write_index(
    output_root: Path,
    project: AcdProject,
    tag_info: TagInfo,
    provenance: dict,
    generated_files: list[Path],
) -> Path:
    index: dict = {
        "controller": project.controller_name,
        "software_revision": project.software_revision,
        "source_acd": provenance,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "data_types": len(tag_info.data_types),
        "controller_tags": len(tag_info.controller_tags),
        "programs": {
            program.name: {
                "tags": len(tag_info.program_tags.get(program.name, [])),
                "main_routine": program.main_routine[0],
                "routines": {
                    routine.name: {
                        "type": routine.routine_type,
                        "rungs": sum(1 for r in routine.rungs if r.rung_type == "N"),
                        "pending_edit_rungs": sum(
                            1 for r in routine.rungs if r.rung_type == "e"
                        ),
                    }
                    for routine in program.routines
                },
            }
            for program in project.programs
        },
        "files": {
            path.relative_to(output_root).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted(set(generated_files))
            if path.exists()
        },
    }
    index_path = output_root / INDEX_NAME
    _write_json(index_path, index)
    return index_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("acd_file", nargs="?", type=Path, default=DEFAULT_ACD)
    parser.add_argument(
        "--plc",
        default=DEFAULT_PLC_PATH,
        help=f"PLC connection path for the tag-values read (default: {DEFAULT_PLC_PATH})",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="skip the live tag-values read; carry values forward from the previous export",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PLC_ROOT,
        help=f"root of the generated PLC tree (default: {PLC_ROOT})",
    )
    args = parser.parse_args(argv)

    if not args.acd_file.exists():
        parser.error(f"ACD file not found: {args.acd_file}")

    print(f"Reading {args.acd_file} (extracting internal databases, ~1 min)...")
    provenance = acd_provenance(args.acd_file)
    if provenance["last_saved"]:
        print(
            f"ACD last saved {provenance['last_saved']}"
            f" (sha256 {provenance['sha256'][:12]}...)"
        )
    with tempfile.TemporaryDirectory(
        prefix="acd_export_", ignore_cleanup_errors=True
    ) as temp_dir:
        exporter = _build_database(args.acd_file, temp_dir)
        try:
            project = read_project(exporter._cur, _software_revision(temp_dir))
        finally:
            exporter._db.close()
        tag_info = parse_tag_info(temp_dir)

    # Studio rewrites the ACD while the project is open in it; refuse to
    # index an extraction whose source bytes changed mid-run.
    current_sha = hashlib.sha256(args.acd_file.read_bytes()).hexdigest()
    if current_sha != provenance["sha256"]:
        print(
            "ERROR: the ACD was re-saved while this extraction ran"
            " (likely by an open Studio 5000 session). Re-run to get a"
            " consistent snapshot.",
            file=sys.stderr,
        )
        return 2

    n_routines = sum(len(p.routines) for p in project.programs)
    n_rungs = sum(len(r.rungs) for p in project.programs for r in p.routines)
    n_tags = len(tag_info.controller_tags) + sum(
        len(t) for t in tag_info.program_tags.values()
    )
    print(
        f"Controller {project.controller_name}: {len(project.programs)} programs,"
        f" {n_routines} routines, {n_rungs} rungs,"
        f" {n_tags} tags, {len(tag_info.data_types)} data types"
    )

    plc_path = None if args.offline else args.plc
    generated = write_tree(
        project, tag_info, args.output_root, provenance, plc_path, args.offline
    )
    print(f"Wrote {len(generated)} L5X/rllscrap/tag files under {args.output_root}")

    values_ok = False
    if args.offline:
        print("Offline: carried tag values forward from the previous export")
    else:
        from dune_winder.plc_tag_values_export import fetch_and_write_tag_values

        print(f"Reading live tag values from {args.plc}...")
        result = fetch_and_write_tag_values(args.plc, output_root=args.output_root)
        print(
            f"Read values for {result['tag_count']} tags"
            f" across {result['file_count']} files"
        )
        values_ok = True

    from dune_winder.convert_plc_rllscrap import convert_directory

    converted = convert_directory(args.output_root)
    print(f"Regenerated {converted} pasteable.rll files")

    # Index everything the run produced (including the derived files).
    derived = [
        p.with_name("pasteable.rll")
        for p in args.output_root.rglob("studio_copy.rllscrap")
    ]
    manifest = args.output_root / "manifest.json"
    if manifest.exists():
        derived.append(manifest)
    index_path = write_index(
        args.output_root, project, tag_info, provenance, generated + derived
    )
    print(f"Provenance index written to {index_path}")

    if not args.offline and not values_ok:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
